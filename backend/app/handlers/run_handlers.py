from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.interfaces import RequestContext
from app.control_models import (
    ControlRunsAuditRequest,
    ControlRunsEventsRequest,
    ControlRunsGetRequest,
    ControlRunsListRequest,
    ControlRunStartRequest,
    ControlRunWaitRequest,
)
from app.orchestrator.events import build_lifecycle_event
from app.services.request_normalization import normalize_idempotency_key, normalize_preset
from app.tool_policy import ToolPolicyDict, tool_policy_to_dict


@dataclass
class RunHandlerDependencies:
    logger: logging.Logger
    settings: Any
    runtime_manager: Any
    state_store: Any
    agent: Any
    active_run_tasks: dict[str, asyncio.Task]
    idempotency_mgr: Any
    resolve_agent: Callable[[str | None], tuple[str, Any, Any]]
    effective_orchestrator_agent_ids: Callable[[], set[str]]
    build_run_start_fingerprint: Callable[..., str]
    extract_also_allow: Callable[[ToolPolicyDict | None], list[str] | None]


_deps: RunHandlerDependencies | None = None


def configure(deps: RunHandlerDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> RunHandlerDependencies:
    if _deps is None:
        raise RuntimeError("run_handlers is not configured")
    return _deps


def _normalize_tool_policy_payload(value) -> ToolPolicyDict | None:
    return tool_policy_to_dict(value, include_also_allow=True)


def _remove_active_task(run_id: str) -> None:
    deps = _require_deps()
    deps.active_run_tasks.pop(run_id, None)


def normalize_contract_run_status(status: str | None) -> str | None:
    normalized = (status or "").strip().lower()
    if not normalized:
        return None
    if normalized == "failed":
        return "error"
    return normalized


def _is_terminal_run_status(status: str | None) -> bool:
    normalized = (status or "").strip().lower()
    return normalized in {"completed", "failed", "timed_out", "cancelled"}


def extract_final_message(run_state: dict) -> str | None:
    events = run_state.get("events") or []
    for event in reversed(events):
        if event.get("type") == "final" and event.get("message"):
            return event.get("message")
    return None


def _build_wait_payload(run_id: str, run_state: dict, *, wait_status: str | None = None) -> dict:
    run_status_raw = run_state.get("status")
    run_status = normalize_contract_run_status(run_status_raw)
    started_at = run_state.get("created_at")
    ended_at = run_state.get("updated_at") if _is_terminal_run_status(run_status_raw) else None

    if wait_status is None:
        if run_status_raw == "completed":
            wait_status = "ok"
        elif run_status_raw in {"failed", "timed_out", "cancelled"}:
            wait_status = "error"
        else:
            wait_status = "timeout"

    payload = {
        "status": wait_status,
        "runId": run_id,
        "runStatus": run_status,
        "run_status": run_status,
        "startedAt": started_at,
        "started_at": started_at,
        "endedAt": ended_at,
        "ended_at": ended_at,
        "error": run_state.get("error"),
    }

    if wait_status in {"ok", "error"}:
        payload["final"] = extract_final_message(run_state)

    return payload


def lifecycle_status_from_stage(stage: str) -> str | None:
    normalized = (stage or "").strip().lower()
    if not normalized:
        return None
    if normalized.endswith(("_received", "_accepted", "_requested")):
        return "accepted"
    if normalized.endswith(("_started", "_dispatched")):
        return "running"
    if normalized.endswith(("_completed", "_done")):
        return "completed"
    if normalized.endswith("_timeout") or "timeout" in normalized:
        return "timed_out"
    if normalized.endswith("_cancelled"):
        return "cancelled"
    if normalized.endswith(("_failed", "_rejected")):
        return "failed"
    return None


def state_append_event_safe(run_id: str, event: dict) -> None:
    deps = _require_deps()
    try:
        deps.state_store.append_event(run_id=run_id, event=event)
    except Exception:
        deps.logger.debug("state_append_event_failed run_id=%s", run_id, exc_info=True)


def state_mark_failed_safe(run_id: str, error: str) -> None:
    deps = _require_deps()
    try:
        deps.state_store.mark_failed(run_id=run_id, error=error)
    except Exception:
        deps.logger.debug("state_mark_failed_failed run_id=%s", run_id, exc_info=True)


def state_mark_completed_safe(run_id: str) -> None:
    deps = _require_deps()
    try:
        deps.state_store.mark_completed(run_id=run_id)
    except Exception:
        deps.logger.debug("state_mark_completed_failed run_id=%s", run_id, exc_info=True)


def _find_idempotent_run_or_raise(
    *,
    idempotency_key: str | None,
    fingerprint: str,
) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="run",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different request payload.",
        replay_builder=lambda key, existing: {
            "status": "accepted",
            "runId": existing.get("run_id"),
            "sessionId": existing.get("session_id"),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_run(
    *,
    idempotency_key: str | None,
    fingerprint: str,
    run_id: str,
    session_id: str,
) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="run",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={
            "run_id": run_id,
            "session_id": session_id,
        },
    )


async def _run_background_message(
    *,
    agent_id: str | None,
    run_id: str,
    session_id: str,
    message: str,
    model: str | None,
    preset: str | None,
    tool_policy: ToolPolicyDict | None,
) -> None:
    deps = _require_deps()

    async def collect_event(payload: dict) -> None:
        state_append_event_safe(run_id=run_id, event=payload)

    try:
        resolved_agent_id, selected_agent, selected_orchestrator = deps.resolve_agent(agent_id)
        applied_preset = normalize_preset(preset)
        deps.state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="active")
        state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_started",
                details={"preset": applied_preset, "agent_id": resolved_agent_id},
                agent=selected_agent.name,
            ),
        )

        runtime_state = deps.runtime_manager.get_state()
        selected_model = (model or "").strip() or runtime_state.model

        selected_agent.configure_runtime(
            base_url=runtime_state.base_url,
            model=runtime_state.model,
        )

        if runtime_state.runtime == "local":
            selected_model = await deps.runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
        else:
            selected_model = await deps.runtime_manager.resolve_api_request_model(selected_model)

        await selected_orchestrator.run_user_message(
            user_message=message,
            send_event=collect_event,
            request_context=RequestContext(
                session_id=session_id,
                request_id=run_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=tool_policy,
                also_allow=deps.extract_also_allow(tool_policy),
                agent_id=resolved_agent_id,
                depth=0,
                preset=applied_preset,
                orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
            ),
        )
        state_mark_completed_safe(run_id=run_id)
        state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_completed",
                details={"agent_id": resolved_agent_id},
                agent=selected_agent.name,
            ),
        )
    except Exception as exc:
        state_mark_failed_safe(run_id=run_id, error=str(exc))
        state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_failed",
                details={"error": str(exc)},
                agent=(selected_agent.name if "selected_agent" in locals() else deps.agent.name),
            ),
        )
        deps.logger.exception("background_run_failed run_id=%s session_id=%s", run_id, session_id)
    finally:
        _remove_active_task(run_id)


def start_run_background(
    *,
    agent_id: str | None,
    message: str,
    session_id: str,
    model: str | None,
    preset: str | None,
    tool_policy: ToolPolicyDict | None,
    meta: dict | None = None,
) -> str:
    deps = _require_deps()
    runtime_state = deps.runtime_manager.get_state()
    run_id = str(uuid.uuid4())

    deps.state_store.init_run(
        run_id=run_id,
        session_id=session_id,
        request_id=run_id,
        user_message=message or "",
        runtime=runtime_state.runtime,
        model=model or runtime_state.model,
        meta={"source": "rest", "async": True, **(meta or {})},
    )
    deps.state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="pending")
    state_append_event_safe(
        run_id=run_id,
        event=build_lifecycle_event(
            request_id=run_id,
            session_id=session_id,
            stage="accepted",
            details={"source": "api", "chars": len(message or "")},
            agent=deps.agent.name,
        ),
    )

    task = asyncio.create_task(
        _run_background_message(
            agent_id=agent_id,
            run_id=run_id,
            session_id=session_id,
            message=message,
            model=model,
            preset=preset,
            tool_policy=tool_policy,
        )
    )
    deps.active_run_tasks[run_id] = task
    return run_id


async def wait_for_run_result(run_id: str, timeout_ms: int | None = None, poll_interval_ms: int | None = None) -> dict:
    deps = _require_deps()
    run_state = deps.state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    timeout = max(0, int(timeout_ms if timeout_ms is not None else deps.settings.run_wait_default_timeout_ms))
    poll = max(10, int(poll_interval_ms if poll_interval_ms is not None else deps.settings.run_wait_poll_interval_ms))
    elapsed = 0

    while elapsed <= timeout:
        run_state = deps.state_store.get_run(run_id)
        if run_state is None:
            raise HTTPException(status_code=404, detail="Run not found")

        status = run_state.get("status")
        if status in {"completed", "failed"}:
            return _build_wait_payload(
                run_id=run_id,
                run_state=run_state,
                wait_status="ok" if status == "completed" else "error",
            )

        task = deps.active_run_tasks.get(run_id)
        if task and task.done():
            refreshed = deps.state_store.get_run(run_id)
            refreshed_state = refreshed or run_state
            return _build_wait_payload(
                run_id=run_id,
                run_state=refreshed_state,
                wait_status="ok" if refreshed_state.get("status") == "completed" else "error",
            )

        await asyncio.sleep(poll / 1000.0)
        elapsed += poll

    timed_out_state = deps.state_store.get_run(run_id) or run_state
    return _build_wait_payload(
        run_id=run_id,
        run_state=timed_out_state,
        wait_status="timeout",
    )


def _get_run_minimal(*, run_id: str) -> dict:
    deps = _require_deps()
    run_state = deps.state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    events = run_state.get("events") or []
    lifecycle_events = [event for event in events if event.get("type") == "lifecycle"]
    return {
        "schema": "runs.get.v1",
        "run": {
            "run_id": run_state.get("run_id"),
            "request_id": run_state.get("request_id"),
            "session_id": run_state.get("session_id"),
            "status": normalize_contract_run_status(run_state.get("status")),
            "runtime": run_state.get("runtime"),
            "model": run_state.get("model"),
            "created_at": run_state.get("created_at"),
            "updated_at": run_state.get("updated_at"),
            "error": run_state.get("error"),
            "final": extract_final_message(run_state),
            "event_count": len(events),
            "lifecycle_count": len(lifecycle_events),
        },
    }


def _list_runs_minimal(*, limit: int, session_id: str | None) -> dict:
    deps = _require_deps()
    capped_limit = max(1, min(limit, 200))
    session_filter = (session_id or "").strip()

    runs = deps.state_store.list_runs(limit=max(capped_limit * 5, 200))
    items: list[dict] = []

    for run in runs:
        if session_filter and str(run.get("session_id", "")).strip() != session_filter:
            continue

        items.append(
            {
                "run_id": run.get("run_id"),
                "request_id": run.get("request_id"),
                "session_id": run.get("session_id"),
                "status": normalize_contract_run_status(run.get("status")),
                "runtime": run.get("runtime"),
                "model": run.get("model"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "error": run.get("error"),
                "final": extract_final_message(run),
            }
        )

        if len(items) >= capped_limit:
            break

    return {
        "schema": "runs.list.v1",
        "count": len(items),
        "items": items,
    }


def _list_run_events_minimal(*, run_id: str, limit: int) -> dict:
    deps = _require_deps()
    run_state = deps.state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    capped_limit = max(1, min(limit, 1000))
    events = list(run_state.get("events") or [])
    items = events[-capped_limit:]

    return {
        "schema": "runs.events.v1",
        "run_id": run_id,
        "count": len(items),
        "total_count": len(events),
        "items": items,
    }


def _get_run_audit_minimal(*, run_id: str) -> dict:
    deps = _require_deps()
    run_state = deps.state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    events = list(run_state.get("events") or [])
    lifecycle_events = [event for event in events if event.get("type") == "lifecycle"]
    lifecycle_stage_counts: dict[str, int] = {}
    blocked_with_reason_counts: dict[str, int] = {}
    tool_selection_empty_reason_counts: dict[str, int] = {}
    last_tool_audit_summary: dict = {}
    for event in lifecycle_events:
        stage = str(event.get("stage") or "").strip()
        if not stage:
            continue
        lifecycle_stage_counts[stage] = lifecycle_stage_counts.get(stage, 0) + 1

        details = event.get("details")
        if not isinstance(details, dict):
            details = {}

        blocked_with_reason = details.get("blocked_with_reason")
        if isinstance(blocked_with_reason, str) and blocked_with_reason.strip():
            key = blocked_with_reason.strip()
            blocked_with_reason_counts[key] = blocked_with_reason_counts.get(key, 0) + 1

        if stage == "tool_selection_empty":
            reason = details.get("reason")
            if isinstance(reason, str) and reason.strip():
                key = reason.strip()
                tool_selection_empty_reason_counts[key] = tool_selection_empty_reason_counts.get(key, 0) + 1

        if stage == "tool_audit_summary":
            last_tool_audit_summary = dict(details)

    return {
        "schema": "runs.audit.v1",
        "run": {
            "run_id": run_state.get("run_id"),
            "session_id": run_state.get("session_id"),
            "status": normalize_contract_run_status(run_state.get("status")),
            "created_at": run_state.get("created_at"),
            "updated_at": run_state.get("updated_at"),
        },
        "telemetry": {
            "event_count": len(events),
            "lifecycle_count": len(lifecycle_events),
            "lifecycle_stages": lifecycle_stage_counts,
            "blocked_with_reason": blocked_with_reason_counts,
            "tool_selection_empty_reasons": tool_selection_empty_reason_counts,
            "tool_started": lifecycle_stage_counts.get("tool_started", 0),
            "tool_completed": lifecycle_stage_counts.get("tool_completed", 0),
            "tool_failed": lifecycle_stage_counts.get("tool_failed", 0),
            "tool_loop_warn": lifecycle_stage_counts.get("tool_loop_warn", 0),
            "tool_loop_blocked": lifecycle_stage_counts.get("tool_loop_blocked", 0),
            "tool_budget_exceeded": lifecycle_stage_counts.get("tool_budget_exceeded", 0),
            "tool_audit_summary": lifecycle_stage_counts.get("tool_audit_summary", 0),
            "guardrail_summary": {
                "loop_warn_count": lifecycle_stage_counts.get("tool_loop_warn", 0),
                "loop_blocked_count": lifecycle_stage_counts.get("tool_loop_blocked", 0),
                "budget_exceeded_count": lifecycle_stage_counts.get("tool_budget_exceeded", 0),
                "tool_audit": {
                    "tool_calls": int(last_tool_audit_summary.get("tool_calls", 0) or 0),
                    "tool_errors": int(last_tool_audit_summary.get("tool_errors", 0) or 0),
                    "loop_blocked": int(last_tool_audit_summary.get("loop_blocked", 0) or 0),
                    "budget_blocked": int(last_tool_audit_summary.get("budget_blocked", 0) or 0),
                    "elapsed_ms": int(last_tool_audit_summary.get("elapsed_ms", 0) or 0),
                    "call_cap": int(last_tool_audit_summary.get("call_cap", 0) or 0),
                    "time_cap_seconds": float(last_tool_audit_summary.get("time_cap_seconds", 0.0) or 0.0),
                    "loop_warn_threshold": int(last_tool_audit_summary.get("loop_warn_threshold", 0) or 0),
                    "loop_critical_threshold": int(last_tool_audit_summary.get("loop_critical_threshold", 0) or 0),
                },
            },
        },
    }


async def api_control_run_start(request_data: dict, idempotency_key_header: str | None) -> dict:
    deps = _require_deps()
    request = ControlRunStartRequest.model_validate(request_data)
    runtime_state = deps.runtime_manager.get_state()
    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)
    idempotency_key = normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    session_id = request.session_id or str(uuid.uuid4())

    fingerprint = deps.build_run_start_fingerprint(
        message=request.message,
        session_id=request.session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_run_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return {
            "schema": "run.start.v1",
            **existing,
        }

    run_id = start_run_background(
        agent_id=None,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
    )
    _register_idempotent_run(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        run_id=run_id,
        session_id=session_id,
    )

    return {
        "schema": "run.start.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }


async def api_control_run_wait(request_data: dict) -> dict:
    request = ControlRunWaitRequest.model_validate(request_data)
    payload = await wait_for_run_result(
        request.run_id,
        timeout_ms=request.timeout_ms,
        poll_interval_ms=request.poll_interval_ms,
    )
    return {
        "schema": "run.wait.v1",
        **payload,
    }


async def api_control_agent_run(request_data: dict, idempotency_key_header: str | None) -> dict:
    payload = await api_control_run_start(request_data=request_data, idempotency_key_header=idempotency_key_header)
    return {
        "schema": "agent.run.v1",
        **{key: value for key, value in payload.items() if key != "schema"},
    }


async def api_control_agent_wait(request_data: dict) -> dict:
    payload = await api_control_run_wait(request_data=request_data)
    return {
        "schema": "agent.wait.v1",
        **{key: value for key, value in payload.items() if key != "schema"},
    }


def api_control_runs_get(request_data: dict) -> dict:
    request = ControlRunsGetRequest.model_validate(request_data)
    return _get_run_minimal(run_id=request.run_id)


def api_control_runs_list(request_data: dict) -> dict:
    request = ControlRunsListRequest.model_validate(request_data)
    return _list_runs_minimal(limit=request.limit, session_id=request.session_id)


def api_control_runs_events(request_data: dict) -> dict:
    request = ControlRunsEventsRequest.model_validate(request_data)
    return _list_run_events_minimal(run_id=request.run_id, limit=request.limit)


def api_control_runs_audit(request_data: dict) -> dict:
    request = ControlRunsAuditRequest.model_validate(request_data)
    return _get_run_audit_minimal(run_id=request.run_id)
