from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import WebSocket, WebSocketDisconnect

from app.errors import (
    GuardrailViolation,
    LlmClientError,
    PolicyApprovalCancelledError,
    RuntimeSwitchError,
    ToolExecutionError,
)
from app.interfaces import RequestContext
from app.models import SUPPORTED_WS_INBOUND_TYPES, WsInboundEnvelope, parse_ws_inbound_message, peek_ws_inbound_type
from app.orchestrator.events import build_lifecycle_event, classify_error
from app.services.directive_parser import (
    normalize_reasoning_level,
    normalize_reasoning_visibility,
    parse_directives_from_message,
)
from app.services.request_normalization import normalize_prompt_mode, normalize_queue_mode
from app.services.session_inbox_service import SessionInboxService
from app.tool_policy import ToolPolicyDict, tool_policy_to_dict

EventPayload = dict[str, Any]
AsyncSendEvent = Callable[[EventPayload], Awaitable[None]]


class RuntimeStateLike(Protocol):
    runtime: str
    base_url: str
    model: str


class LoggerLike(Protocol):
    def info(self, msg: str, *args: object) -> None: ...

    def debug(self, msg: str, *args: object) -> None: ...

    def exception(self, msg: str, *args: object) -> None: ...


class RuntimeManagerLike(Protocol):
    def get_state(self) -> RuntimeStateLike: ...

    async def switch_runtime(self, target: str, send_event: AsyncSendEvent, session_id: str) -> RuntimeStateLike: ...

    async def ensure_model_ready(self, send_event: AsyncSendEvent, session_id: str, selected_model: str) -> str: ...

    async def resolve_api_request_model(self, selected_model: str) -> str: ...

    def set_active_model(self, model_name: str) -> None: ...


class StateStoreLike(Protocol):
    def init_run(
        self,
        run_id: str,
        session_id: str,
        request_id: str,
        user_message: str,
        runtime: str,
        model: str,
    ) -> None: ...

    def set_task_status(self, run_id: str, task_id: str, label: str, status: str) -> None: ...


class AgentLike(Protocol):
    name: str

    def configure_runtime(self, base_url: str, model: str) -> None: ...


class OrchestratorLike(Protocol):
    async def run_user_message(
        self,
        user_message: str,
        send_event: AsyncSendEvent,
        request_context: RequestContext,
    ) -> None: ...


class SubrunLaneLike(Protocol):
    async def spawn(
        self,
        parent_request_id: str,
        parent_session_id: str,
        user_message: str,
        runtime: str,
        model: str,
        timeout_seconds: float,
        tool_policy: ToolPolicyDict | None,
        send_event: AsyncSendEvent,
        agent_id: str,
        mode: str,
        preset: str | None,
        orchestrator_agent_ids: list[str] | None,
        orchestrator_api: OrchestratorLike,
    ) -> str: ...


class SettingsLike(Protocol):
    subrun_timeout_seconds: float
    queue_mode_default: str
    prompt_mode_default: str
    session_inbox_max_queue_length: int
    session_inbox_ttl_seconds: int
    session_follow_up_max_deferrals: int


class PolicyApprovalServiceLike(Protocol):
    async def decide(self, approval_id: str, decision: str, scope: str | None = None) -> dict | None: ...

    async def clear_session_overrides(self, session_id: str | None) -> None: ...


@dataclass
class WsHandlerDependencies:
    logger: LoggerLike
    settings: SettingsLike
    agent: AgentLike
    agent_registry: dict[str, AgentLike]
    runtime_manager: RuntimeManagerLike
    state_store: StateStoreLike
    subrun_lane: SubrunLaneLike
    sync_custom_agents: Callable[[], None]
    normalize_agent_id: Callable[[str | None], str]
    effective_orchestrator_agent_ids: Callable[[], set[str]]
    looks_like_review_request: Callable[[str], bool]
    looks_like_coding_request: Callable[[str], bool]
    route_agent_for_message: Callable[[str | None, str, str | None], tuple[str, str | None, tuple[str, ...], list[dict[str, object]]]]
    resolve_agent: Callable[[str | None], tuple[str, AgentLike, OrchestratorLike]]
    state_append_event_safe: Callable[[str, EventPayload], None]
    state_mark_failed_safe: Callable[[str, str], None]
    state_mark_completed_safe: Callable[[str], None]
    lifecycle_status_from_stage: Callable[[str], str | None]
    primary_agent_id: str
    coder_agent_id: str
    review_agent_id: str
    policy_approval_service: PolicyApprovalServiceLike | None = None


async def handle_ws_agent(websocket: WebSocket, deps: WsHandlerDependencies) -> None:
    await websocket.accept()
    connection_session_id = str(uuid.uuid4())
    runtime_state = deps.runtime_manager.get_state()
    sequence_number = 0
    session_inbox = SessionInboxService(
        max_queue_length=deps.settings.session_inbox_max_queue_length,
        ttl_seconds=deps.settings.session_inbox_ttl_seconds,
    )
    pending_clarifications: dict[str, dict[str, Any]] = {}
    session_workers: dict[str, Any] = {}
    follow_up_deferrals: dict[str, int] = {}
    used_session_ids: set[str] = {connection_session_id}
    deps.logger.info(
        "ws_connected session_id=%s runtime=%s model=%s",
        connection_session_id,
        runtime_state.runtime,
        runtime_state.model,
    )
    active_agent_name_cv: ContextVar[str] = ContextVar('active_agent_name', default=deps.agent.name)
    active_agent_name_cv.set(deps.agent.name)

    class ClientDisconnectedError(Exception):
        pass

    _send_lock = asyncio.Lock()

    async def send_event(payload: dict):
        nonlocal sequence_number
        async with _send_lock:
            try:
                sequence_number += 1
                if "session_id" not in payload:
                    payload["session_id"] = connection_session_id
                if payload.get("type") == "lifecycle":
                    request_id = str(payload.get("request_id") or "").strip()
                    if request_id:
                        deps.state_append_event_safe(
                            run_id=request_id,
                            event=payload,
                        )
                envelope = {
                    "seq": sequence_number,
                    "event": payload,
                }
                deps.logger.debug(
                    "ws_send_event session_id=%s seq=%s type=%s request_id=%s",
                    payload.get("session_id", connection_session_id),
                    sequence_number,
                    payload.get("type"),
                    payload.get("request_id"),
                )
                if payload.get("type") == "clarification_needed":
                    pending_session_id = str(payload.get("session_id") or connection_session_id)
                    question = str(payload.get("message") or "").strip()
                    if question:
                        pending_clarifications.setdefault(pending_session_id, {})["question"] = question
                await websocket.send_text(json.dumps(envelope))
            except (WebSocketDisconnect, RuntimeError) as exc:
                deps.logger.info(
                    "ws_send_event_disconnected session_id=%s type=%s",
                    payload.get("session_id", connection_session_id),
                    payload.get("type"),
                )
                raise ClientDisconnectedError() from exc

    await send_event(
        {
            "type": "status",
            "agent": deps.agent.name,
            "message": "Connected to agent runtime.",
            "session_id": connection_session_id,
            "runtime": runtime_state.runtime,
            "model": runtime_state.model,
        }
    )

    async def send_lifecycle(stage: str, request_id: str, session_id: str, details: dict | None = None, agent_name: str | None = None):
        lifecycle_event = build_lifecycle_event(
            request_id=request_id,
            session_id=session_id,
            stage=stage,
            details=details,
            agent=agent_name or active_agent_name_cv.get(deps.agent.name),
        )
        lifecycle_status = deps.lifecycle_status_from_stage(stage)
        if lifecycle_status is not None:
            lifecycle_event["status"] = lifecycle_status
            lifecycle_event["run_status"] = lifecycle_status
        if stage in {"request_received", "run_started"}:
            lifecycle_event["started_at"] = lifecycle_event.get("ts")
        if lifecycle_status in {"completed", "failed", "timed_out", "cancelled"}:
            lifecycle_event["ended_at"] = lifecycle_event.get("ts")
        await send_event(
            lifecycle_event
        )

    async def handle_request_failure(*, request_id: str, session_id: str, exc: Exception) -> None:
        if isinstance(exc, PolicyApprovalCancelledError):
            await send_event(
                {
                    "type": "status",
                    "agent": deps.agent.name,
                    "message": str(exc),
                    "request_id": request_id,
                    "session_id": session_id,
                }
            )
            await send_lifecycle(
                stage="request_cancelled",
                request_id=request_id,
                session_id=session_id,
                details={"reason": "policy_approval_cancelled", "error": str(exc)},
            )
            deps.state_mark_failed_safe(run_id=request_id, error="policy_approval_cancelled")
            return
        if isinstance(exc, GuardrailViolation):
            deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
            await send_event(
                {
                    "type": "error",
                    "agent": deps.agent.name,
                    "message": f"Guardrail blocked request: {exc}",
                    "error_category": classify_error(exc),
                }
            )
            await send_lifecycle(
                stage="request_failed_guardrail",
                request_id=request_id,
                session_id=session_id,
                details={"error": str(exc), "error_category": classify_error(exc)},
            )
            return
        if isinstance(exc, ToolExecutionError):
            deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
            await send_event(
                {
                    "type": "error",
                    "agent": deps.agent.name,
                    "message": f"Toolchain error: {exc}",
                    "error_category": classify_error(exc),
                }
            )
            await send_lifecycle(
                stage="request_failed_toolchain",
                request_id=request_id,
                session_id=session_id,
                details={"error": str(exc), "error_category": classify_error(exc)},
            )
            return
        if isinstance(exc, RuntimeSwitchError):
            deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
            await send_event(
                {
                    "type": "runtime_switch_error",
                    "session_id": session_id,
                    "message": str(exc),
                    "error_category": classify_error(exc),
                }
            )
            await send_lifecycle(
                stage="runtime_switch_failed",
                request_id=request_id,
                session_id=session_id,
                details={"error": str(exc), "error_category": classify_error(exc)},
            )
            return
        if isinstance(exc, LlmClientError):
            deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
            await send_event(
                {
                    "type": "error",
                    "agent": deps.agent.name,
                    "message": f"LLM error: {exc}",
                    "error_category": classify_error(exc),
                }
            )
            await send_lifecycle(
                stage="request_failed_llm",
                request_id=request_id,
                session_id=session_id,
                details={"error": str(exc), "error_category": classify_error(exc)},
            )
            return

        deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
        deps.logger.exception(
            "ws_unhandled_error request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        await send_event(
            {
                "type": "error",
                "agent": deps.agent.name,
                "message": f"Request error: {exc}",
                "error_category": classify_error(exc),
            }
        )
        await send_lifecycle(
            stage="request_failed",
            request_id=request_id,
            session_id=session_id,
            details={"error": str(exc), "error_category": classify_error(exc)},
        )

    async def execute_user_message_job(job: dict[str, Any]) -> None:
        request_id = str(job.get("request_id") or "")
        session_id = str(job.get("session_id") or connection_session_id)
        used_session_ids.add(session_id)
        content = str(job.get("content") or "")
        model = job.get("model")
        requested_agent_id = str(job.get("requested_agent_id") or deps.primary_agent_id)
        tool_policy = job.get("tool_policy")
        if not isinstance(tool_policy, dict):
            tool_policy = None
        queue_mode = str(job.get("queue_mode") or deps.settings.queue_mode_default)
        prompt_mode = str(job.get("prompt_mode") or deps.settings.prompt_mode_default)
        reasoning_level = normalize_reasoning_level(str(job.get("reasoning_level") or ""))
        reasoning_visibility = normalize_reasoning_visibility(str(job.get("reasoning_visibility") or ""))
        applied_preset = (str(job.get("preset") or "").strip().lower() or None)
        incoming_also_allow = None
        if isinstance(tool_policy, dict):
            raw_also_allow = tool_policy.get("also_allow")
            if isinstance(raw_also_allow, list):
                incoming_also_allow = [
                    str(item).strip()
                    for item in raw_also_allow
                    if isinstance(item, str) and str(item).strip()
                ]

        def should_steer_interrupt() -> bool:
            return queue_mode == "steer" and session_inbox.has_newer_than(session_id, request_id)

        effective_agent_id, routing_reason, required_capabilities, ranked_capability_matches = deps.route_agent_for_message(
            requested_agent_id=requested_agent_id,
            message=content,
            preset=applied_preset,
        )

        resolved_agent_id, selected_agent, selected_orchestrator = deps.resolve_agent(effective_agent_id)
        active_agent_name_cv.set(selected_agent.name)

        if routing_reason:
            if resolved_agent_id == "review-agent" and routing_reason in {"review_intent", "preset_review"}:
                routing_message = "Delegated this request to review-agent."
            else:
                routing_message = f"Request routed to {resolved_agent_id} based on capability matching."
            await send_event(
                {
                    "type": "status",
                    "agent": deps.agent.name,
                    "message": routing_message,
                    "routing_reason": routing_reason,
                    "requested_agent_id": requested_agent_id,
                    "effective_agent_id": resolved_agent_id,
                }
            )

        await send_lifecycle(
            stage="request_dispatched",
            request_id=request_id,
            session_id=session_id,
            details={
                "model": model,
                "requested_agent_id": requested_agent_id,
                "effective_agent_id": resolved_agent_id,
                "routing_reason": routing_reason,
                "routing_capabilities": list(required_capabilities),
                "routing_matches": ranked_capability_matches,
                "preset": applied_preset,
                "queue_mode": queue_mode,
                "prompt_mode": prompt_mode,
                "reasoning_level": reasoning_level,
                "reasoning_visibility": reasoning_visibility,
            },
        )

        runtime_state = deps.runtime_manager.get_state()
        deps.logger.info(
            "ws_request_dispatch request_id=%s session_id=%s runtime=%s active_model=%s",
            request_id,
            session_id,
            runtime_state.runtime,
            runtime_state.model,
        )

        selected_agent.configure_runtime(
            base_url=runtime_state.base_url,
            model=runtime_state.model,
        )

        selected_model = (str(model or "")).strip() or runtime_state.model
        if runtime_state.runtime == "local":
            resolved_model = await deps.runtime_manager.ensure_model_ready(send_event, session_id, selected_model)
            if resolved_model != selected_model:
                await send_event(
                    {
                        "type": "status",
                        "agent": selected_agent.name,
                        "message": f"Model '{selected_model}' not available. Using '{resolved_model}'.",
                    }
                )
                selected_model = resolved_model
                if runtime_state.model != resolved_model:
                    deps.runtime_manager.set_active_model(resolved_model)
        else:
            resolved_model = await deps.runtime_manager.resolve_api_request_model(selected_model)
            if resolved_model != selected_model:
                await send_event(
                    {
                        "type": "status",
                        "agent": selected_agent.name,
                        "message": f"API model '{selected_model}' not available. Using '{resolved_model}'.",
                    }
                )
                selected_model = resolved_model
                if runtime_state.model != resolved_model:
                    deps.runtime_manager.set_active_model(resolved_model)

        deps.logger.info(
            "ws_agent_run_start request_id=%s session_id=%s selected_model=%s",
            request_id,
            session_id,
            selected_model,
        )
        clarification_requested = False

        async def send_event_wrapped(payload: EventPayload) -> None:
            nonlocal clarification_requested
            if payload.get("type") == "clarification_needed":
                clarification_requested = True
                pending_clarifications[session_id] = {
                    "original_message": content,
                    "question": str(payload.get("message") or "").strip(),
                    "request_id": request_id,
                    "agent_id": resolved_agent_id,
                }
            await send_event(payload)

        await selected_orchestrator.run_user_message(
            user_message=content,
            send_event=send_event_wrapped,
            request_context=RequestContext(
                session_id=session_id,
                request_id=request_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=tool_policy,
                also_allow=incoming_also_allow,
                agent_id=resolved_agent_id,
                depth=0,
                preset=applied_preset,
                orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
                queue_mode=queue_mode,
                prompt_mode=prompt_mode,
                reasoning_level=reasoning_level,
                reasoning_visibility=reasoning_visibility,
                should_steer_interrupt=should_steer_interrupt,
            ),
        )
        deps.logger.info(
            "ws_agent_run_done request_id=%s session_id=%s selected_model=%s",
            request_id,
            session_id,
            selected_model,
        )
        if clarification_requested:
            await send_lifecycle(
                stage="clarification_waiting_response",
                request_id=request_id,
                session_id=session_id,
                details={"queue_size": session_inbox.size(session_id)},
            )
            return
        await send_lifecycle(
            stage="request_completed",
            request_id=request_id,
            session_id=session_id,
        )
        deps.state_mark_completed_safe(run_id=request_id)

    async def drain_session_queue(session_id: str) -> None:
        current_task = asyncio.current_task()
        try:
            while True:
                max_follow_up_deferrals = max(1, int(getattr(deps.settings, "session_follow_up_max_deferrals", 2)))
                current_deferrals = int(follow_up_deferrals.get(session_id, 0))
                dequeued, deferred_follow_up = session_inbox.dequeue_prioritized(
                    session_id,
                    force_follow_up=current_deferrals >= max_follow_up_deferrals,
                )
                if dequeued is None:
                    return
                request_id = str(dequeued.meta.get("request_id") or dequeued.run_id or "")
                queue_mode = str(dequeued.meta.get("queue_mode") or deps.settings.queue_mode_default)
                prompt_mode = str(dequeued.meta.get("prompt_mode") or deps.settings.prompt_mode_default)
                if deferred_follow_up:
                    current_deferrals += 1
                    follow_up_deferrals[session_id] = current_deferrals
                    await send_lifecycle(
                        stage="follow_up_deferred",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "deferred_count": current_deferrals,
                            "max_deferrals": max_follow_up_deferrals,
                            "queue_size": session_inbox.size(session_id),
                        },
                    )
                elif queue_mode == "follow_up":
                    follow_up_deferrals[session_id] = 0
                    await send_lifecycle(
                        stage="follow_up_scheduled",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "deferred_count": current_deferrals,
                            "queue_size": session_inbox.size(session_id),
                        },
                    )
                else:
                    follow_up_deferrals[session_id] = 0
                await send_lifecycle(
                    stage="run_dequeued",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "queue_mode": queue_mode,
                        "prompt_mode": prompt_mode,
                        "queue_size": session_inbox.size(session_id),
                    },
                )
                try:
                    await execute_user_message_job(dict(dequeued.meta))
                except Exception as exc:
                    await handle_request_failure(request_id=request_id, session_id=session_id, exc=exc)
        finally:
            worker = session_workers.get(session_id)
            if worker is current_task:
                session_workers.pop(session_id, None)
            follow_up_deferrals.pop(session_id, None)

    def ensure_session_worker(session_id: str) -> None:
        existing = session_workers.get(session_id)
        if existing is not None and not existing.done():
            return
        session_workers[session_id] = asyncio.create_task(drain_session_queue(session_id))

    try:
        while True:
            request_id = str(uuid.uuid4())
            session_id = connection_session_id
            active_agent_name_cv.set(deps.agent.name)
            try:
                raw = await websocket.receive_text()
                inbound_type = peek_ws_inbound_type(raw)
                if inbound_type not in SUPPORTED_WS_INBOUND_TYPES:
                    envelope = WsInboundEnvelope.model_validate_json(raw)
                    deps.sync_custom_agents()
                    session_id = envelope.session_id or connection_session_id
                    deps.logger.info(
                        "ws_message_received request_id=%s session_id=%s type=%s agent_id=%s content_len=%s requested_model=%s",
                        request_id,
                        session_id,
                        envelope.type,
                        deps.normalize_agent_id(envelope.agent_id),
                        len(envelope.content or ""),
                        envelope.model,
                    )
                    requested_agent_id = deps.normalize_agent_id(envelope.agent_id)
                    if requested_agent_id not in deps.agent_registry:
                        await send_event(
                            {
                                "type": "status",
                                "agent": deps.agent.name,
                                "message": f"Unsupported agent: {envelope.agent_id}",
                            }
                        )
                        await send_lifecycle(
                            stage="request_rejected_unsupported_agent",
                            request_id=request_id,
                            session_id=session_id,
                            details={"agent_id": envelope.agent_id},
                        )
                        continue

                    deps.state_store.init_run(
                        run_id=request_id,
                        session_id=session_id,
                        request_id=request_id,
                        user_message=envelope.content or "",
                        runtime=deps.runtime_manager.get_state().runtime,
                        model=envelope.model or deps.runtime_manager.get_state().model,
                    )
                    deps.state_store.set_task_status(
                        run_id=request_id,
                        task_id="request",
                        label="request",
                        status="active",
                    )
                    await send_lifecycle(
                        stage="request_received",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "chars": len(envelope.content),
                            "requested_agent_id": requested_agent_id,
                            "effective_agent_id": requested_agent_id,
                            "routing_reason": None,
                            "preset": (envelope.preset or "").strip().lower() or None,
                        },
                    )
                    await send_event(
                        {
                            "type": "status",
                            "agent": deps.agent.name,
                            "message": f"Unsupported message type: {envelope.type}",
                        }
                    )
                    await send_lifecycle(
                        stage="request_rejected_unsupported_type",
                        request_id=request_id,
                        session_id=session_id,
                        details={"type": envelope.type},
                    )
                    deps.state_mark_failed_safe(run_id=request_id, error=f"unsupported_type:{envelope.type}")
                    continue

                data = parse_ws_inbound_message(raw)
                deps.sync_custom_agents()
                session_id = data.session_id or connection_session_id
                used_session_ids.add(session_id)

                if data.type == "policy_decision":
                    approval_id = str(getattr(data, "approval_id", "") or "").strip()
                    decision = str(getattr(data, "decision", "") or "").strip().lower()
                    if not approval_id:
                        await send_event(
                            {
                                "type": "status",
                                "agent": deps.agent.name,
                                "message": "Policy decision rejected: missing approval_id.",
                                "session_id": session_id,
                            }
                        )
                        await send_lifecycle(
                            stage="policy_approval_decision_rejected",
                            request_id=request_id,
                            session_id=session_id,
                            details={"reason": "missing_approval_id"},
                        )
                        continue

                    mapped_scope: str | None = None
                    mapped_decision = decision
                    if decision == "allow_session":
                        mapped_decision = "allow_session"
                        mapped_scope = "session_tool"

                    if deps.policy_approval_service is None:
                        await send_event(
                            {
                                "type": "status",
                                "agent": deps.agent.name,
                                "message": "Policy decision rejected: policy approval service unavailable.",
                                "session_id": session_id,
                            }
                        )
                        await send_lifecycle(
                            stage="policy_approval_decision_rejected",
                            request_id=request_id,
                            session_id=session_id,
                            details={"reason": "service_unavailable", "approval_id": approval_id},
                        )
                        continue

                    updated = await deps.policy_approval_service.decide(
                        approval_id=approval_id,
                        decision=mapped_decision,
                        scope=mapped_scope,
                    )
                    if updated is None:
                        await send_event(
                            {
                                "type": "status",
                                "agent": deps.agent.name,
                                "message": "Policy decision rejected: approval request not found.",
                                "session_id": session_id,
                            }
                        )
                        await send_lifecycle(
                            stage="policy_approval_decision_rejected",
                            request_id=request_id,
                            session_id=session_id,
                            details={"reason": "approval_not_found", "approval_id": approval_id},
                        )
                        continue

                    target_request_id = str(updated.get("run_id") or request_id)
                    target_session_id = str(updated.get("session_id") or session_id)
                    await send_event(
                        {
                            "type": "policy_approval_updated",
                            "agent": deps.agent.name,
                            "request_id": target_request_id,
                            "session_id": target_session_id,
                            "approval": updated,
                        }
                    )
                    await send_lifecycle(
                        stage="policy_approval_decision",
                        request_id=target_request_id,
                        session_id=target_session_id,
                        details={
                            "approval_id": approval_id,
                            "decision": str(updated.get("decision") or ""),
                            "status": str(updated.get("status") or ""),
                            "duplicate": bool(updated.get("duplicate_decision")),
                            "duplicate_matches_existing": bool(updated.get("duplicate_matches_existing")),
                        },
                    )
                    if bool(updated.get("duplicate_decision")) and not bool(updated.get("duplicate_matches_existing")):
                        await send_lifecycle(
                            stage="policy_approval_decision_noop",
                            request_id=target_request_id,
                            session_id=target_session_id,
                            details={
                                "approval_id": approval_id,
                                "reason": "duplicate_conflict_ignored",
                                "incoming_decision": mapped_decision,
                                "effective_decision": str(updated.get("decision") or ""),
                                "status": str(updated.get("status") or ""),
                            },
                        )
                    continue

                deps.logger.info(
                    "ws_message_received request_id=%s session_id=%s type=%s agent_id=%s content_len=%s requested_model=%s",
                    request_id,
                    session_id,
                    data.type,
                    deps.normalize_agent_id(data.agent_id),
                    len(data.content or ""),
                    data.model,
                )
                requested_agent_id = deps.normalize_agent_id(data.agent_id)
                if requested_agent_id not in deps.agent_registry:
                    await send_event(
                        {
                            "type": "status",
                            "agent": deps.agent.name,
                            "message": f"Unsupported agent: {data.agent_id}",
                        }
                    )
                    await send_lifecycle(
                        stage="request_rejected_unsupported_agent",
                        request_id=request_id,
                        session_id=session_id,
                        details={"agent_id": data.agent_id},
                    )
                    continue

                directive_result = parse_directives_from_message(
                    data.content or "",
                    queue_mode_default=deps.settings.queue_mode_default,
                )
                content = directive_result.clean_content
                queue_mode = normalize_queue_mode(
                    data.queue_mode or directive_result.overrides.queue_mode,
                    default=deps.settings.queue_mode_default,
                )
                prompt_mode = normalize_prompt_mode(data.prompt_mode, default=deps.settings.prompt_mode_default)
                requested_model = (data.model or directive_result.overrides.model or "").strip() or None
                reasoning_level = normalize_reasoning_level(directive_result.overrides.reasoning_level)
                reasoning_visibility = normalize_reasoning_visibility(directive_result.overrides.reasoning_visibility)
                if data.type in {"user_message", "clarification_response"}:
                    if data.type == "user_message":
                        pending_clarifications.pop(session_id, None)
                    if data.type == "clarification_response":
                        pending = pending_clarifications.get(session_id)
                        if not isinstance(pending, dict):
                            await send_event(
                                {
                                    "type": "status",
                                    "agent": deps.agent.name,
                                    "message": "No pending clarification found for this session.",
                                }
                            )
                            await send_lifecycle(
                                stage="clarification_response_rejected",
                                request_id=request_id,
                                session_id=session_id,
                                details={"reason": "no_pending_clarification"},
                            )
                            continue

                        original_message = str(pending.get("original_message") or "").strip()
                        clarification = content.strip()
                        if not original_message:
                            await send_event(
                                {
                                    "type": "status",
                                    "agent": deps.agent.name,
                                    "message": "Pending clarification is missing the original message.",
                                }
                            )
                            await send_lifecycle(
                                stage="clarification_response_rejected",
                                request_id=request_id,
                                session_id=session_id,
                                details={"reason": "missing_original_message"},
                            )
                            continue

                        content = f"{original_message}\n\nClarification: {clarification}"
                        pending_agent_id = str(pending.get("agent_id") or "").strip()
                        if pending_agent_id and pending_agent_id in deps.agent_registry:
                            requested_agent_id = pending_agent_id
                        pending_clarifications.pop(session_id, None)

                    current_runtime_state = deps.runtime_manager.get_state()
                    deps.state_store.init_run(
                        run_id=request_id,
                        session_id=session_id,
                        request_id=request_id,
                        user_message=content,
                        runtime=current_runtime_state.runtime,
                        model=requested_model or current_runtime_state.model,
                    )
                    deps.state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")
                    await send_lifecycle(
                        stage="request_received",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "chars": len(content),
                            "requested_agent_id": requested_agent_id,
                            "effective_agent_id": requested_agent_id,
                            "routing_reason": None,
                            "preset": (data.preset or "").strip().lower() or None,
                            "queue_mode": queue_mode,
                            "prompt_mode": prompt_mode,
                            "reasoning_level": reasoning_level,
                            "reasoning_visibility": reasoning_visibility,
                            "directives_applied": list(directive_result.applied),
                            "source_type": data.type,
                        },
                    )

                    incoming_tool_policy = tool_policy_to_dict(data.tool_policy, include_also_allow=True)
                    try:
                        session_inbox.enqueue(
                            session_id=session_id,
                            run_id=request_id,
                            message=content,
                            meta={
                                "request_id": request_id,
                                "session_id": session_id,
                                "content": content,
                                "model": requested_model,
                                "preset": data.preset,
                                "tool_policy": incoming_tool_policy,
                                "requested_agent_id": requested_agent_id,
                                "queue_mode": queue_mode,
                                "prompt_mode": prompt_mode,
                                "reasoning_level": reasoning_level,
                                "reasoning_visibility": reasoning_visibility,
                            },
                        )
                    except OverflowError:
                        deps.state_mark_failed_safe(run_id=request_id, error="session_queue_overflow")
                        await send_lifecycle(
                            stage="queue_overflow",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "queue_mode": queue_mode,
                                "max_queue_length": deps.settings.session_inbox_max_queue_length,
                            },
                        )
                        await send_lifecycle(
                            stage="request_failed_queue_overflow",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "queue_mode": queue_mode,
                                "max_queue_length": deps.settings.session_inbox_max_queue_length,
                                "error": "session_queue_overflow",
                            },
                        )
                        await send_event(
                            {
                                "type": "error",
                                "agent": deps.agent.name,
                                "message": "Session queue overflow. Please retry shortly.",
                            }
                        )
                        continue

                    await send_lifecycle(
                        stage="inbox_enqueued",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "queue_mode": queue_mode,
                            "prompt_mode": prompt_mode,
                            "queue_size": session_inbox.size(session_id),
                        },
                    )
                    ensure_session_worker(session_id)
                    continue

                incoming_tool_policy = tool_policy_to_dict(data.tool_policy, include_also_allow=True)
                incoming_also_allow = None
                if isinstance(incoming_tool_policy, dict):
                    raw_also_allow = incoming_tool_policy.get("also_allow")
                    if isinstance(raw_also_allow, list):
                        incoming_also_allow = [
                            str(item).strip()
                            for item in raw_also_allow
                            if isinstance(item, str) and str(item).strip()
                        ]
                applied_preset = (data.preset or "").strip().lower() or None

                effective_agent_id, routing_reason, required_capabilities, ranked_capability_matches = deps.route_agent_for_message(
                    requested_agent_id=requested_agent_id,
                    message=content,
                    preset=applied_preset,
                )

                resolved_agent_id, selected_agent, selected_orchestrator = deps.resolve_agent(effective_agent_id)
                active_agent_name_cv.set(selected_agent.name)

                if routing_reason:
                    if resolved_agent_id == "review-agent" and routing_reason in {"review_intent", "preset_review"}:
                        routing_message = "Delegated this request to review-agent."
                    else:
                        routing_message = f"Request routed to {resolved_agent_id} based on capability matching."
                    await send_event(
                        {
                            "type": "status",
                            "agent": deps.agent.name,
                            "message": routing_message,
                            "routing_reason": routing_reason,
                            "requested_agent_id": requested_agent_id,
                            "effective_agent_id": resolved_agent_id,
                        }
                    )
                current_runtime_state = deps.runtime_manager.get_state()
                deps.state_store.init_run(
                    run_id=request_id,
                    session_id=session_id,
                    request_id=request_id,
                    user_message=content,
                    runtime=current_runtime_state.runtime,
                    model=requested_model or current_runtime_state.model,
                )
                deps.state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")
                await send_lifecycle(
                    stage="request_received",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "chars": len(content),
                        "requested_agent_id": requested_agent_id,
                        "effective_agent_id": resolved_agent_id,
                        "routing_reason": routing_reason,
                        "routing_capabilities": list(required_capabilities),
                        "routing_matches": ranked_capability_matches,
                        "preset": applied_preset,
                        "queue_mode": queue_mode,
                        "prompt_mode": prompt_mode,
                        "reasoning_level": reasoning_level,
                        "reasoning_visibility": reasoning_visibility,
                        "directives_applied": list(directive_result.applied),
                    },
                )

                if data.type == "runtime_switch_request":
                    target = (data.runtime_target or "").strip().lower()
                    await send_lifecycle(
                        stage="runtime_switch_requested",
                        request_id=request_id,
                        session_id=session_id,
                        details={"target": target},
                    )
                    state = await deps.runtime_manager.switch_runtime(target, send_event, session_id)
                    await send_event(
                        {
                            "type": "runtime_switch_done",
                            "session_id": session_id,
                            "runtime": state.runtime,
                            "model": state.model,
                            "base_url": state.base_url,
                        }
                    )
                    await send_lifecycle(
                        stage="request_completed",
                        request_id=request_id,
                        session_id=session_id,
                    )
                    deps.state_mark_completed_safe(run_id=request_id)
                    continue

                if data.type == "subrun_spawn":
                    runtime_state = deps.runtime_manager.get_state()
                    selected_model = (requested_model or "").strip() or runtime_state.model
                    if runtime_state.runtime == "local":
                        selected_model = await deps.runtime_manager.ensure_model_ready(send_event, session_id, selected_model)
                    else:
                        selected_model = await deps.runtime_manager.resolve_api_request_model(selected_model)

                    spawn_target_agent_id = (
                        deps.normalize_agent_id(data.agent_id) if data.agent_id else resolved_agent_id
                    )
                    spawn_agent_id, _, spawn_orchestrator = deps.resolve_agent(spawn_target_agent_id)
                    spawn_mode = (data.mode or "run").strip().lower() or "run"

                    try:
                        run_id = await deps.subrun_lane.spawn(
                            parent_request_id=request_id,
                            parent_session_id=session_id,
                            user_message=content,
                            runtime=runtime_state.runtime,
                            model=selected_model,
                            timeout_seconds=deps.settings.subrun_timeout_seconds,
                            tool_policy=incoming_tool_policy,
                            send_event=send_event,
                            agent_id=spawn_agent_id,
                            mode=spawn_mode,
                            preset=applied_preset,
                            orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
                            orchestrator_api=spawn_orchestrator,
                        )
                    except GuardrailViolation as exc:
                        error_text = str(exc)
                        deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
                        await send_event(
                            {
                                "type": "error",
                                "agent": deps.agent.name,
                                "message": f"Subrun policy blocked request: {exc}",
                                "error_category": classify_error(exc),
                            }
                        )
                        if error_text.startswith("Subrun depth policy blocked request:"):
                            await send_lifecycle(
                                stage="subrun_rejected_depth_policy",
                                request_id=request_id,
                                session_id=session_id,
                                details={
                                    "error": error_text,
                                    "requester_agent_id": resolved_agent_id,
                                },
                            )
                            await send_lifecycle(
                                stage="request_rejected_subrun_depth_policy",
                                request_id=request_id,
                                session_id=session_id,
                                details={
                                    "error": error_text,
                                    "requester_agent_id": resolved_agent_id,
                                },
                            )
                            continue
                        await send_lifecycle(
                            stage="subrun_rejected_policy",
                            request_id=request_id,
                            session_id=session_id,
                            details={"error": str(exc), "error_category": classify_error(exc)},
                        )
                        await send_lifecycle(
                            stage="request_rejected_subrun_policy",
                            request_id=request_id,
                            session_id=session_id,
                            details={"error": str(exc), "error_category": classify_error(exc)},
                        )
                        continue

                    await send_lifecycle(
                        stage="subrun_accepted",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "subrun_id": run_id,
                            "model": selected_model,
                            "agent_id": spawn_agent_id,
                            "mode": spawn_mode,
                        },
                    )
                    await send_lifecycle(
                        stage="request_completed",
                        request_id=request_id,
                        session_id=session_id,
                        details={"spawned_subrun_id": run_id},
                    )
                    deps.state_mark_completed_safe(run_id=request_id)
                    continue

                await send_lifecycle(
                    stage="request_dispatched",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "model": requested_model,
                        "requested_agent_id": requested_agent_id,
                        "effective_agent_id": resolved_agent_id,
                        "routing_reason": routing_reason,
                        "preset": applied_preset,
                        "reasoning_level": reasoning_level,
                        "reasoning_visibility": reasoning_visibility,
                    },
                )

                runtime_state = deps.runtime_manager.get_state()
                deps.logger.info(
                    "ws_request_dispatch request_id=%s session_id=%s runtime=%s active_model=%s",
                    request_id,
                    session_id,
                    runtime_state.runtime,
                    runtime_state.model,
                )

                selected_agent.configure_runtime(
                    base_url=runtime_state.base_url,
                    model=runtime_state.model,
                )

                selected_model = (requested_model or "").strip() or runtime_state.model
                if runtime_state.runtime == "local":
                    resolved_model = await deps.runtime_manager.ensure_model_ready(send_event, session_id, selected_model)
                    if resolved_model != selected_model:
                        await send_event(
                            {
                                "type": "status",
                                "agent": selected_agent.name,
                                "message": f"Model '{selected_model}' not available. Using '{resolved_model}'.",
                            }
                        )
                        selected_model = resolved_model
                        if runtime_state.model != resolved_model:
                            deps.runtime_manager.set_active_model(resolved_model)
                else:
                    resolved_model = await deps.runtime_manager.resolve_api_request_model(selected_model)
                    if resolved_model != selected_model:
                        await send_event(
                            {
                                "type": "status",
                                "agent": selected_agent.name,
                                "message": f"API model '{selected_model}' not available. Using '{resolved_model}'.",
                            }
                        )
                        selected_model = resolved_model
                        if runtime_state.model != resolved_model:
                            deps.runtime_manager.set_active_model(resolved_model)

                deps.logger.info(
                    "ws_agent_run_start request_id=%s session_id=%s selected_model=%s",
                    request_id,
                    session_id,
                    selected_model,
                )
                await selected_orchestrator.run_user_message(
                    user_message=content,
                    send_event=send_event,
                    request_context=RequestContext(
                        session_id=session_id,
                        request_id=request_id,
                        runtime=runtime_state.runtime,
                        model=selected_model,
                        tool_policy=incoming_tool_policy,
                        also_allow=incoming_also_allow,
                        agent_id=resolved_agent_id,
                        depth=0,
                        preset=applied_preset,
                        orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
                        queue_mode=queue_mode,
                        prompt_mode=prompt_mode,
                        reasoning_level=reasoning_level,
                        reasoning_visibility=reasoning_visibility,
                    ),
                )
                deps.logger.info(
                    "ws_agent_run_done request_id=%s session_id=%s selected_model=%s",
                    request_id,
                    session_id,
                    selected_model,
                )
                await send_lifecycle(
                    stage="request_completed",
                    request_id=request_id,
                    session_id=session_id,
                )
                deps.state_mark_completed_safe(run_id=request_id)
            except (WebSocketDisconnect, ClientDisconnectedError):
                deps.logger.info("ws_disconnected session_id=%s", session_id)
                break
            except PolicyApprovalCancelledError as exc:
                await send_event(
                    {
                        "type": "status",
                        "agent": deps.agent.name,
                        "message": str(exc),
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                )
                await send_lifecycle(
                    stage="request_cancelled",
                    request_id=request_id,
                    session_id=session_id,
                    details={"reason": "policy_approval_cancelled", "error": str(exc)},
                )
                deps.state_mark_failed_safe(run_id=request_id, error="policy_approval_cancelled")
            except GuardrailViolation as exc:
                deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "error",
                        "agent": deps.agent.name,
                        "message": f"Guardrail blocked request: {exc}",
                        "error_category": classify_error(exc),
                    }
                )
                await send_lifecycle(
                    stage="request_failed_guardrail",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc), "error_category": classify_error(exc)},
                )
            except ToolExecutionError as exc:
                deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "error",
                        "agent": deps.agent.name,
                        "message": f"Toolchain error: {exc}",
                        "error_category": classify_error(exc),
                    }
                )
                await send_lifecycle(
                    stage="request_failed_toolchain",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc), "error_category": classify_error(exc)},
                )
            except RuntimeSwitchError as exc:
                deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "runtime_switch_error",
                        "session_id": session_id,
                        "message": str(exc),
                        "error_category": classify_error(exc),
                    }
                )
                await send_lifecycle(
                    stage="runtime_switch_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc), "error_category": classify_error(exc)},
                )
            except LlmClientError as exc:
                deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "error",
                        "agent": deps.agent.name,
                        "message": f"LLM error: {exc}",
                        "error_category": classify_error(exc),
                    }
                )
                await send_lifecycle(
                    stage="request_failed_llm",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc), "error_category": classify_error(exc)},
                )
            except Exception as exc:
                deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
                deps.logger.exception(
                    "ws_unhandled_error request_id=%s session_id=%s",
                    request_id,
                    session_id,
                )
                await send_event(
                    {
                        "type": "error",
                        "agent": deps.agent.name,
                        "message": f"Request error: {exc}",
                        "error_category": classify_error(exc),
                    }
                )
                await send_lifecycle(
                    stage="request_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc), "error_category": classify_error(exc)},
                )
    except WebSocketDisconnect:
        deps.logger.info("ws_outer_disconnect session_id=%s", connection_session_id)
        return
    except ClientDisconnectedError:
        deps.logger.info("ws_outer_client_disconnected session_id=%s", connection_session_id)
        return
    except Exception as exc:
        deps.logger.exception("ws_server_error session_id=%s", connection_session_id)
        try:
            await send_event(
                {
                    "type": "error",
                    "agent": deps.agent.name,
                    "message": f"Server error: {exc}",
                }
            )
        except ClientDisconnectedError:
            return
    finally:
        if deps.policy_approval_service is not None:
            for _cleanup_sid in used_session_ids:
                try:
                    await deps.policy_approval_service.clear_session_overrides(_cleanup_sid)
                except Exception:
                    deps.logger.debug("policy_session_override_cleanup_failed session_id=%s", _cleanup_sid, exc_info=True)
        workers = [task for task in session_workers.values() if task is not None and not task.done()]
        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)