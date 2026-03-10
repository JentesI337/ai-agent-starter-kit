"""Cron-based workflow scheduler.

Scans all workflows with ``schedule`` triggers and executes them when due.
Runs as a background ``asyncio.Task`` started during application startup.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

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
        return it.get_next(datetime).replace(tzinfo=timezone.utc)
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
        from app.handlers import workflow_handlers
        deps = workflow_handlers._require_deps()
    except RuntimeError:
        return  # system not ready yet

    deps.sync_custom_agents()
    now = datetime.now(timezone.utc)

    for workflow in deps.custom_agent_store.list():
        triggers = getattr(workflow, "triggers", []) or []
        for idx, t in enumerate(triggers):
            t_type = t.get("type") if isinstance(t, dict) else getattr(t, "type", None)
            if t_type != "schedule":
                continue

            cron_expr = (
                t.get("cron_expression") if isinstance(t, dict)
                else getattr(t, "cron_expression", None)
            )
            if not cron_expr:
                continue

            next_run_raw = (
                t.get("next_run_at") if isinstance(t, dict)
                else getattr(t, "next_run_at", None)
            )

            # Compute next_run_at if not yet set
            if not next_run_raw:
                next_dt = _next_cron_time(cron_expr, now)
                if next_dt is None:
                    continue
                _update_trigger_times(t, last_run=None, next_run=next_dt.isoformat())
                _persist_triggers(deps, workflow)
                continue

            try:
                next_dt = datetime.fromisoformat(next_run_raw)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if now < next_dt:
                continue  # not due yet

            # --- Fire! ---
            logger.info(
                "schedule_trigger_firing workflow_id=%s cron=%s",
                workflow.id, cron_expr,
            )
            await _execute_scheduled_workflow(workflow, deps)

            # Update timestamps
            new_next = _next_cron_time(cron_expr, now)
            _update_trigger_times(
                t,
                last_run=now.isoformat(),
                next_run=new_next.isoformat() if new_next else None,
            )
            _persist_triggers(deps, workflow)


def _update_trigger_times(
    trigger: Any,
    last_run: str | None,
    next_run: str | None,
) -> None:
    """Set ``last_run_at`` / ``next_run_at`` on a trigger (dict or object)."""
    if isinstance(trigger, dict):
        if last_run is not None:
            trigger["last_run_at"] = last_run
        if next_run is not None:
            trigger["next_run_at"] = next_run
    else:
        if last_run is not None:
            trigger.last_run_at = last_run
        if next_run is not None:
            trigger.next_run_at = next_run


def _persist_triggers(deps: Any, workflow: Any) -> None:
    """Save trigger timestamp changes back to the store."""
    try:
        from types import SimpleNamespace
        triggers = getattr(workflow, "triggers", []) or []
        trigger_dicts = [
            t if isinstance(t, dict) else t.model_dump() if hasattr(t, "model_dump") else vars(t)
            for t in triggers
        ]
        patch = SimpleNamespace(triggers=trigger_dicts)
        deps.custom_agent_store.upsert(patch, merge_id=workflow.id)
    except Exception:
        logger.debug("trigger_persist_failed workflow_id=%s", workflow.id, exc_info=True)


async def _execute_scheduled_workflow(workflow: Any, deps: Any) -> None:
    """Execute a workflow that is due according to its schedule trigger."""
    from app.control_models import ControlWorkflowsExecuteRequest
    from app.handlers import workflow_handlers

    execute_request = ControlWorkflowsExecuteRequest(
        workflow_id=workflow.id,
        message=f"Scheduled execution at {datetime.now(timezone.utc).isoformat()}",
    )
    try:
        result = await workflow_handlers.api_control_workflows_execute(
            request_data=execute_request.model_dump(),
            idempotency_key_header=None,
        )
        run_id = result.get("runId") or result.get("run_id") or "?"
        logger.info("schedule_trigger_executed workflow_id=%s run_id=%s", workflow.id, run_id)
    except Exception:
        logger.exception("schedule_trigger_execute_failed workflow_id=%s", workflow.id)


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
