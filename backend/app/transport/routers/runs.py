"""Run management endpoints."""
from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException

from app.config import settings
from app.contracts import RequestContext
from app.shared.control_models import (
    ControlRunsAuditRequest,
    ControlRunsEventsRequest,
    ControlRunsGetRequest,
    ControlRunsListRequest,
    ControlRunStartRequest,
    ControlRunWaitRequest,
)
from app.shared.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError
from app.orchestration.events import build_lifecycle_event
from app.orchestration.run_state_machine import (
    build_run_state_event,
    build_run_state_violation,
    build_stage_event,
    is_allowed_run_state_transition,
    resolve_run_state_from_stage,
)
from app.reasoning.directive_parser import (
    normalize_reasoning_level,
    normalize_reasoning_visibility,
    parse_directives_from_message,
)
from app.reasoning.request_normalization import (
    normalize_idempotency_key,
    normalize_preset,
    normalize_prompt_mode,
    normalize_queue_mode,
)
from app.tools.policy import ToolPolicyDict, tool_policy_to_dict

JsonDict = dict


# === Handler dependencies ===

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


def _is_run_state_hard_failed(run_id: str) -> bool:
    deps = _require_deps()
    get_run = getattr(deps.state_store, "get_run", None)
    if not callable(get_run):
        return False
    run_state = get_run(run_id)
    if not isinstance(run_state, dict):
        return False
    meta = run_state.get("meta")
    if not isinstance(meta, dict):
        return False
    return bool(meta.get("run_state_hard_failed"))


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
        _append_derived_stage_and_run_state_events(run_id=run_id, event=event)
    except Exception:
        deps.logger.debug("state_append_event_failed run_id=%s", run_id, exc_info=True)


def _append_derived_stage_and_run_state_events(*, run_id: str, event: dict) -> None:
    deps = _require_deps()
    if not isinstance(event, dict):
        return
    if str(event.get("type") or "") != "lifecycle":
        return

    stage = str(event.get("stage") or "").strip()
    if not stage:
        return

    session_id = str(event.get("session_id") or "")
    timestamp = event.get("ts") if isinstance(event.get("ts"), str) else None
    status = event.get("status") if isinstance(event.get("status"), str) else None

    deps.state_store.append_event(
        run_id=run_id,
        event=build_stage_event(
            run_id=run_id,
            session_id=session_id,
            stage=stage,
            status=status,
            ts=timestamp,
        ),
    )

    target_state = resolve_run_state_from_stage(stage)
    if target_state is None:
        return

    previous_state: str | None = None
    get_run = getattr(deps.state_store, "get_run", None)
    if callable(get_run):
        run_state = get_run(run_id)
        if isinstance(run_state, dict):
            meta = run_state.get("meta")
            if isinstance(meta, dict):
                value = meta.get("run_state")
                if isinstance(value, str) and value.strip():
                    previous_state = value.strip().lower()

    allowed = is_allowed_run_state_transition(previous_state, target_state)
    deps.state_store.append_event(
        run_id=run_id,
        event=build_run_state_event(
            run_id=run_id,
            session_id=session_id,
            stage=stage,
            previous_state=previous_state,
            target_state=target_state,
            allowed=allowed,
            reason=None if allowed else "invalid_transition",
            ts=timestamp,
        ),
    )
    if not allowed:
        deps.state_store.append_event(
            run_id=run_id,
            event=build_run_state_violation(
                run_id=run_id,
                session_id=session_id,
                stage=stage,
                previous_state=previous_state,
                target_state=target_state,
                ts=timestamp,
            ),
        )
        if bool(getattr(settings, "run_state_violation_hard_fail_enabled", False)):
            mark_failed = getattr(deps.state_store, "mark_failed", None)
            if callable(mark_failed):
                mark_failed(run_id=run_id, error=f"run_state_violation: {previous_state} -> {target_state} on stage {stage}")
            patch_run_meta = getattr(deps.state_store, "patch_run_meta", None)
            if callable(patch_run_meta):
                patch_run_meta(
                    run_id,
                    {
                        "run_state_hard_failed": True,
                        "run_state_hard_failed_stage": stage,
                        "run_state_hard_failed_from": previous_state,
                        "run_state_hard_failed_to": target_state,
                    },
                )
        return

    patch_run_meta = getattr(deps.state_store, "patch_run_meta", None)
    if callable(patch_run_meta):
        patch_run_meta(
            run_id,
            {
                "run_state": target_state,
                "run_state_last_stage": stage,
                "run_state_contract_version": "run-state.v1",
            },
        )


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
    queue_mode: str | None,
    prompt_mode: str | None,
    tool_policy: ToolPolicyDict | None,
) -> None:
    deps = _require_deps()
    selected_agent = None

    async def collect_event(payload: dict) -> None:
        if _is_run_state_hard_failed(run_id):
            raise RuntimeError("run_state_hard_failed")
        state_append_event_safe(run_id=run_id, event=payload)
        if _is_run_state_hard_failed(run_id):
            raise RuntimeError("run_state_hard_failed")

    try:
        directive_result = parse_directives_from_message(
            message or "",
            queue_mode_default=settings.queue_mode_default,
        )
        effective_message = directive_result.clean_content
        effective_queue_mode = normalize_queue_mode(
            queue_mode or directive_result.overrides.queue_mode,
            default=settings.queue_mode_default,
        )
        effective_model = (model or directive_result.overrides.model or "").strip() or None
        reasoning_level = normalize_reasoning_level(directive_result.overrides.reasoning_level)
        reasoning_visibility = normalize_reasoning_visibility(directive_result.overrides.reasoning_visibility)

        resolved_agent_id, selected_agent, selected_orchestrator = deps.resolve_agent(agent_id)
        applied_preset = normalize_preset(preset)
        deps.state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="active")
        state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_started",
                details={
                    "preset": applied_preset,
                    "agent_id": resolved_agent_id,
                    "directives_applied": list(directive_result.applied),
                    "reasoning_level": reasoning_level,
                    "reasoning_visibility": reasoning_visibility,
                },
                agent=selected_agent.name,
            ),
        )

        runtime_state = deps.runtime_manager.get_state()
        selected_model = effective_model or runtime_state.model

        selected_agent.configure_runtime(
            base_url=runtime_state.base_url,
            model=runtime_state.model,
        )

        if runtime_state.runtime == "local":
            selected_model = await deps.runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
        else:
            selected_model = await deps.runtime_manager.resolve_api_request_model(selected_model)

        await selected_orchestrator.run_user_message(
            user_message=effective_message,
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
                queue_mode=effective_queue_mode,
                prompt_mode=normalize_prompt_mode(prompt_mode, default=settings.prompt_mode_default),
                reasoning_level=reasoning_level,
                reasoning_visibility=reasoning_visibility,
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
                agent=(selected_agent.name if selected_agent is not None else deps.agent.name),
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
    queue_mode: str | None,
    prompt_mode: str | None,
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
            queue_mode=queue_mode,
            prompt_mode=prompt_mode,
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
        queue_mode=getattr(request, "queue_mode", None),
        prompt_mode=getattr(request, "prompt_mode", None),
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
        queue_mode=getattr(request, "queue_mode", None),
        prompt_mode=getattr(request, "prompt_mode", None),
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


# === Run endpoints (from run_endpoints.py) ===

@dataclass(frozen=True)
class AgentTestDependencies:
    logger: logging.Logger
    runtime_manager: Any
    state_store: Any
    agent: Any
    orchestrator_api: Any
    normalize_preset: Callable[[str | None], str]
    extract_also_allow: Callable[[ToolPolicyDict | None], list[str] | None]
    effective_orchestrator_agent_ids: Callable[[], list[str] | set[str] | tuple[str, ...]]
    mark_completed: Callable[[str], None]
    mark_failed: Callable[[str, str], None]
    primary_agent_id: str


@dataclass(frozen=True)
class RunEndpointsDependencies:
    start_run_background: Callable[..., str]
    wait_for_run_result: Callable[..., Awaitable[dict]]


async def run_agent_test(request: Any, deps: AgentTestDependencies) -> dict:
    runtime_state = deps.runtime_manager.get_state()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    events: list[dict] = []
    deps.logger.info(
        "agent_test_start request_id=%s session_id=%s runtime=%s model=%s message_len=%s",
        request_id,
        session_id,
        runtime_state.runtime,
        request.model or runtime_state.model,
        len(request.message or ""),
    )
    deps.state_store.init_run(
        run_id=request_id,
        session_id=session_id,
        request_id=request_id,
        user_message=request.message or "",
        runtime=runtime_state.runtime,
        model=request.model or runtime_state.model,
    )
    deps.state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")

    async def collect_event(payload: dict):
        events.append(payload)

    directive_result = parse_directives_from_message(
        request.message or "",
        queue_mode_default=settings.queue_mode_default,
    )
    clean_message = directive_result.clean_content
    reasoning_level = normalize_reasoning_level(directive_result.overrides.reasoning_level)
    reasoning_visibility = normalize_reasoning_visibility(directive_result.overrides.reasoning_visibility)

    selected_model = (request.model or directive_result.overrides.model or "").strip() or runtime_state.model
    if runtime_state.runtime == "local":
        selected_model = await deps.runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
    else:
        selected_model = await deps.runtime_manager.resolve_api_request_model(selected_model)

    # BUG-9: configure_runtime with resolved selected_model, not the default runtime model
    deps.agent.configure_runtime(
        base_url=runtime_state.base_url,
        model=selected_model,
    )

    normalized_tool_policy = tool_policy_to_dict(getattr(request, "tool_policy", None), include_also_allow=True)

    try:
        applied_preset = deps.normalize_preset(request.preset)
        await deps.orchestrator_api.run_user_message(
            user_message=clean_message,
            send_event=collect_event,
            request_context=RequestContext(
                session_id=session_id,
                request_id=request_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=normalized_tool_policy,
                also_allow=deps.extract_also_allow(normalized_tool_policy),
                agent_id=deps.primary_agent_id,
                depth=0,
                preset=applied_preset,
                orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
                queue_mode=normalize_queue_mode(
                    getattr(request, "queue_mode", None) or directive_result.overrides.queue_mode,
                    default=settings.queue_mode_default,
                ),
                prompt_mode=normalize_prompt_mode(
                    getattr(request, "prompt_mode", None),
                    default=settings.prompt_mode_default,
                ),
                reasoning_level=reasoning_level,
                reasoning_visibility=reasoning_visibility,
            ),
        )
        deps.mark_completed(run_id=request_id)
    except (GuardrailViolation, ToolExecutionError, RuntimeSwitchError) as exc:
        deps.mark_failed(run_id=request_id, error=str(exc))
        deps.logger.warning(
            "agent_test_client_error request_id=%s session_id=%s error=%s",
            request_id,
            session_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LlmClientError as exc:
        deps.mark_failed(run_id=request_id, error=str(exc))
        deps.logger.warning(
            "agent_test_llm_error request_id=%s session_id=%s error=%s",
            request_id,
            session_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        deps.mark_failed(run_id=request_id, error=str(exc))
        deps.logger.exception(
            "agent_test_unhandled request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        # SEC (API-01): Only expose generic message; full details stay in server logs
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    final_event = next((item for item in reversed(events) if item.get("type") == "final"), None)
    return {
        "ok": True,
        "runtime": runtime_state.runtime,
        "model": selected_model,
        "preset": applied_preset,
        "sessionId": session_id,
        "requestId": request_id,
        "eventCount": len(events),
        "final": final_event.get("message") if final_event else None,
    }


def start_run(request: Any, deps: RunEndpointsDependencies) -> dict:
    session_id = request.session_id or str(uuid.uuid4())
    normalized_tool_policy = tool_policy_to_dict(getattr(request, "tool_policy", None), include_also_allow=True)
    run_id = deps.start_run_background(
        agent_id=None,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        queue_mode=getattr(request, "queue_mode", None),
        prompt_mode=getattr(request, "prompt_mode", None),
        tool_policy=normalized_tool_policy,
    )

    return {
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
    }


async def wait_run(
    run_id: str,
    timeout_ms: int | None,
    poll_interval_ms: int | None,
    deps: RunEndpointsDependencies,
) -> dict:
    return await deps.wait_for_run_result(
        run_id,
        timeout_ms=timeout_ms,
        poll_interval_ms=poll_interval_ms,
    )


# === Backward-compat builders ===

def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


@dataclass(frozen=True)
class RunApiRouterHandlers:
    agent_test_handler: Callable[[dict], Awaitable[dict]]
    start_run_handler: Callable[[dict], dict]
    wait_run_handler: Callable[[str, int | None, int | None], Awaitable[dict]]


def build_run_api_router(*, handlers: RunApiRouterHandlers) -> APIRouter:
    router = APIRouter()

    @router.post("/api/test/agent")
    async def test_agent(request_data: dict) -> dict:
        return await handlers.agent_test_handler(request_data)

    @router.post("/api/runs/start")
    async def start_run_route(request_data: dict) -> dict:
        return handlers.start_run_handler(request_data)

    @router.get("/api/runs/{run_id}/wait")
    async def wait_run_route(run_id: str, timeout_ms: int | None = None, poll_interval_ms: int | None = None) -> dict:
        return await handlers.wait_run_handler(run_id, timeout_ms, poll_interval_ms)

    return router


def build_control_runs_router(
    *,
    run_start_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]] | None = None,
    run_wait_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agent_run_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]] | None = None,
    agent_wait_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    runs_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    runs_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    runs_events_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    runs_audit_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/run.start")
    async def control_run_start(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        h = run_start_handler or api_control_run_start
        result = h(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/run.wait")
    async def control_run_wait(request: JsonDict = Body(...)):
        h = run_wait_handler or api_control_run_wait
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agent.run")
    async def control_agent_run(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        h = agent_run_handler or api_control_agent_run
        result = h(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agent.wait")
    async def control_agent_wait(request: JsonDict = Body(...)):
        h = agent_wait_handler or api_control_agent_wait
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.get")
    async def control_runs_get(request: JsonDict = Body(...)):
        h = runs_get_handler or api_control_runs_get
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.list")
    async def control_runs_list(request: JsonDict = Body(...)):
        h = runs_list_handler or api_control_runs_list
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.events")
    async def control_runs_events(request: JsonDict = Body(...)):
        h = runs_events_handler or api_control_runs_events
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.audit")
    async def control_runs_audit(request: JsonDict = Body(...)):
        h = runs_audit_handler or api_control_runs_audit
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
