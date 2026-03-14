"""Cron-based workflow scheduler.

Scans all workflows with ``schedule`` triggers and executes them when due.
Also handles recipe scheduling and run lifecycle management.
Runs as a background ``asyncio.Task`` started during application startup.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task[None] | None = None
_CHECK_INTERVAL_SECONDS = 30
_last_retention_check: datetime | None = None


def _next_cron_time(cron_expr: str, after: datetime) -> datetime | None:
    """Compute next run time for *cron_expr* after *after*.

    Uses ``croniter`` if available; otherwise returns ``None``
    (effectively disabling schedule triggers when the library is missing).
    """
    try:
        from croniter import croniter  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("croniter not installed — schedule triggers disabled")
        return None

    try:
        it = croniter(cron_expr, after)
        return it.get_next(datetime).replace(tzinfo=UTC)
    except (ValueError, KeyError) as exc:
        logger.warning("invalid_cron_expression expr=%s error=%s", cron_expr, exc)
        return None


async def _scheduler_loop() -> None:
    """Background loop that checks for due schedule triggers every 30 s."""
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("workflow_scheduler_tick_error")
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)


async def _tick() -> None:
    """Single scheduler tick — scan recipes and manage lifecycle.

    The old workflow scheduling loop has been removed — workflows are
    superseded by recipes.  Only recipe scheduling remains.
    """
    await _tick_recipes()
    await _tick_lifecycle()


async def _tick_recipes() -> None:
    """Scan recipes with schedule triggers and fire any that are due."""
    try:
        from app.recipes.recipe_store import get_recipe_store
        from app.recipes import recipe_handlers

        store = get_recipe_store()
    except RuntimeError:
        return  # recipe system not ready

    now = datetime.now(UTC)

    for recipe in store.list():
        for t in recipe.triggers:
            if not isinstance(t, dict) or t.get("type") != "schedule":
                continue
            cron_expr = t.get("cron_expression")
            if not cron_expr:
                continue

            next_run_at = t.get("next_run_at")
            if not next_run_at:
                next_dt = _next_cron_time(cron_expr, now)
                if next_dt:
                    t["next_run_at"] = next_dt.isoformat()
                    try:
                        store.update(recipe.id, recipe)
                    except Exception:
                        logger.debug("recipe_trigger_persist_failed recipe_id=%s", recipe.id, exc_info=True)
                continue

            try:
                next_dt = datetime.fromisoformat(next_run_at)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue

            if now < next_dt:
                continue

            # Fire
            logger.info("recipe_schedule_firing recipe_id=%s cron=%s", recipe.id, cron_expr)
            try:
                recipe_handlers.api_control_recipes_execute({
                    "recipe_id": recipe.id,
                    "message": f"Scheduled execution at {now.isoformat()}",
                })
            except Exception:
                logger.exception("recipe_schedule_execute_failed recipe_id=%s", recipe.id)

            new_next = _next_cron_time(cron_expr, next_dt)
            t["last_run_at"] = now.isoformat()
            t["next_run_at"] = new_next.isoformat() if new_next else None
            try:
                store.update(recipe.id, recipe)
            except Exception:
                logger.debug("recipe_trigger_persist_failed recipe_id=%s", recipe.id, exc_info=True)


async def _tick_lifecycle() -> None:
    """Manage run lifecycle: auto-cancel overdue runs, paused TTL, history retention."""
    global _last_retention_check

    try:
        from app.recipes.recipe_store import get_recipe_run_store
        run_store = get_recipe_run_store()
    except RuntimeError:
        return

    now = datetime.now(UTC)
    paused_ttl_hours = int(os.environ.get("RECIPE_PAUSED_TTL_HOURS", "24"))

    try:
        active_runs = run_store.list_active_runs()
    except Exception:
        logger.debug("lifecycle_list_active_failed", exc_info=True)
        return

    for run in active_runs:
        # Auto-cancel overdue runs
        max_duration = run.context.get("_max_duration_seconds")
        if max_duration and run.started_at:
            try:
                started_dt = datetime.fromisoformat(run.started_at)
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=UTC)
                elapsed = (now - started_dt).total_seconds()
                if elapsed > max_duration * 2:
                    logger.info("auto_cancel_overdue run_id=%s elapsed=%.0f max=%d", run.run_id, elapsed, max_duration)
                    run_store.cancel_run(run.run_id)
                    continue
            except (ValueError, TypeError):
                pass

        # Paused run TTL
        if run.status == "paused" and run.paused_at:
            try:
                paused_dt = datetime.fromisoformat(run.paused_at)
                if paused_dt.tzinfo is None:
                    paused_dt = paused_dt.replace(tzinfo=UTC)
                if (now - paused_dt).total_seconds() > paused_ttl_hours * 3600:
                    logger.info("auto_cancel_paused_ttl run_id=%s paused_at=%s", run.run_id, run.paused_at)
                    run_store.cancel_run(run.run_id)
            except (ValueError, TypeError):
                pass

    # History retention — throttled to once per hour
    if _last_retention_check is None or (now - _last_retention_check).total_seconds() > 3600:
        _last_retention_check = now
        cutoff = (now - timedelta(days=30)).isoformat()
        try:
            deleted = run_store.cleanup_old_runs(cutoff)
            if deleted:
                logger.info("recipe_run_retention cleaned=%d", deleted)
        except Exception:
            logger.debug("recipe_retention_cleanup_failed", exc_info=True)


def start_workflow_scheduler() -> None:
    """Start the background scheduler task (idempotent)."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="workflow-scheduler")
    logger.info("workflow_scheduler_started interval=%ds", _CHECK_INTERVAL_SECONDS)


def stop_workflow_scheduler() -> None:
    """Cancel the background scheduler task."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("workflow_scheduler_stopped")
    _scheduler_task = None
