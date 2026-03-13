"""Cron-based workflow scheduler.

Scans all workflows with ``schedule`` triggers and executes them when due.
Runs as a background ``asyncio.Task`` started during application startup.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task[None] | None = None
_CHECK_INTERVAL_SECONDS = 30


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
    """Single scheduler tick — scan workflows and fire any that are due."""
    try:
        from app.workflows.handlers import _require_deps
        deps = _require_deps()
    except RuntimeError:
        return  # system not ready yet

    now = datetime.now(UTC)

    for record in deps.workflow_store.list():
        for t in record.triggers:
            if t.type != "schedule":
                continue
            if not t.cron_expression:
                continue

            # Compute next_run_at if not yet set
            if not t.next_run_at:
                next_dt = _next_cron_time(t.cron_expression, now)
                if next_dt is None:
                    continue
                t.next_run_at = next_dt.isoformat()
                _persist_triggers(deps, record)
                continue

            try:
                next_dt = datetime.fromisoformat(t.next_run_at)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                continue

            if now < next_dt:
                continue  # not due yet

            # --- Fire! ---
            logger.info(
                "schedule_trigger_firing workflow_id=%s cron=%s",
                record.id, t.cron_expression,
            )
            await _execute_scheduled_workflow(record)

            # Update timestamps
            new_next = _next_cron_time(t.cron_expression, next_dt)
            t.last_run_at = now.isoformat()
            t.next_run_at = new_next.isoformat() if new_next else None
            _persist_triggers(deps, record)


def _persist_triggers(deps, record) -> None:
    """Save trigger timestamp changes back to the workflow store."""
    try:
        deps.workflow_store.update(record.id, record)
    except Exception:
        logger.debug("trigger_persist_failed workflow_id=%s", record.id, exc_info=True)


async def _execute_scheduled_workflow(record) -> None:
    """Execute a workflow that is due according to its schedule trigger."""
    from app.control_models import ControlWorkflowsExecuteRequest
    from app.workflows.handlers import api_control_workflows_execute

    execute_request = ControlWorkflowsExecuteRequest(
        workflow_id=record.id,
        message=f"Scheduled execution at {datetime.now(UTC).isoformat()}",
    )
    try:
        result = await api_control_workflows_execute(
            request_data=execute_request.model_dump(),
            idempotency_key_header=None,
        )
        run_id = result.get("runId") or result.get("run_id") or "?"
        logger.info("schedule_trigger_executed workflow_id=%s run_id=%s", record.id, run_id)
    except Exception:
        logger.exception("schedule_trigger_execute_failed workflow_id=%s", record.id)


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
