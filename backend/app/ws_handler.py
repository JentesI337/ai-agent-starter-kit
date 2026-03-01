from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import WebSocket, WebSocketDisconnect

from app.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError
from app.interfaces import RequestContext
from app.models import WsInboundMessage
from app.orchestrator.events import build_lifecycle_event, classify_error


ToolPolicy = dict[str, list[str]]
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
        tool_policy: ToolPolicy | None,
        send_event: AsyncSendEvent,
        agent_id: str,
        mode: str,
        preset: str | None,
        orchestrator_agent_ids: list[str] | None,
        orchestrator_api: OrchestratorLike,
    ) -> str: ...


class SettingsLike(Protocol):
    subrun_timeout_seconds: float


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
    resolve_agent: Callable[[str | None], tuple[str, AgentLike, OrchestratorLike]]
    state_append_event_safe: Callable[[str, EventPayload], None]
    state_mark_failed_safe: Callable[[str, str], None]
    state_mark_completed_safe: Callable[[str], None]
    lifecycle_status_from_stage: Callable[[str], str | None]
    primary_agent_id: str
    coder_agent_id: str
    review_agent_id: str


async def handle_ws_agent(websocket: WebSocket, deps: WsHandlerDependencies) -> None:
    await websocket.accept()
    connection_session_id = str(uuid.uuid4())
    runtime_state = deps.runtime_manager.get_state()
    sequence_number = 0
    deps.logger.info(
        "ws_connected session_id=%s runtime=%s model=%s",
        connection_session_id,
        runtime_state.runtime,
        runtime_state.model,
    )
    active_event_agent_name = deps.agent.name

    class ClientDisconnectedError(Exception):
        pass

    async def send_event(payload: dict):
        nonlocal sequence_number
        try:
            sequence_number += 1
            if "session_id" not in payload:
                payload["session_id"] = connection_session_id
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

    async def send_lifecycle(stage: str, request_id: str, session_id: str, details: dict | None = None):
        lifecycle_event = build_lifecycle_event(
            request_id=request_id,
            session_id=session_id,
            stage=stage,
            details=details,
            agent=active_event_agent_name,
        )
        lifecycle_status = deps.lifecycle_status_from_stage(stage)
        if lifecycle_status is not None:
            lifecycle_event["status"] = lifecycle_status
            lifecycle_event["run_status"] = lifecycle_status
        if stage in {"request_received", "run_started"}:
            lifecycle_event["started_at"] = lifecycle_event.get("ts")
        if lifecycle_status in {"completed", "failed", "timed_out", "cancelled"}:
            lifecycle_event["ended_at"] = lifecycle_event.get("ts")
        deps.state_append_event_safe(
            run_id=request_id,
            event=lifecycle_event,
        )
        await send_event(
            lifecycle_event
        )

    try:
        while True:
            request_id = str(uuid.uuid4())
            session_id = connection_session_id
            active_event_agent_name = deps.agent.name
            try:
                raw = await websocket.receive_text()
                data = WsInboundMessage.model_validate_json(raw)
                deps.sync_custom_agents()
                session_id = data.session_id or connection_session_id
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

                incoming_tool_policy = data.tool_policy.model_dump(exclude_none=True) if data.tool_policy else None
                applied_preset = (data.preset or "").strip().lower() or None

                effective_agent_id = requested_agent_id
                routing_reason: str | None = None
                if requested_agent_id == deps.primary_agent_id:
                    if applied_preset == "review":
                        effective_agent_id = deps.review_agent_id
                        routing_reason = "preset_review"
                    elif deps.looks_like_review_request(data.content or ""):
                        effective_agent_id = deps.review_agent_id
                        routing_reason = "review_intent"
                    elif deps.looks_like_coding_request(data.content or ""):
                        effective_agent_id = deps.coder_agent_id
                        routing_reason = "coding_intent"

                resolved_agent_id, selected_agent, selected_orchestrator = deps.resolve_agent(effective_agent_id)
                active_event_agent_name = selected_agent.name

                if routing_reason:
                    await send_event(
                        {
                            "type": "status",
                            "agent": deps.agent.name,
                            "message": f"Head agent delegated this request to {resolved_agent_id}.",
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
                    user_message=data.content or "",
                    runtime=current_runtime_state.runtime,
                    model=data.model or current_runtime_state.model,
                )
                deps.state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")
                await send_lifecycle(
                    stage="request_received",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "chars": len(data.content),
                        "requested_agent_id": requested_agent_id,
                        "effective_agent_id": resolved_agent_id,
                        "routing_reason": routing_reason,
                        "preset": applied_preset,
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
                    continue

                if data.type == "subrun_spawn":
                    runtime_state = deps.runtime_manager.get_state()
                    selected_model = (data.model or "").strip() or runtime_state.model
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
                            user_message=data.content,
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

                if data.type != "user_message":
                    await send_event(
                        {
                            "type": "status",
                            "agent": deps.agent.name,
                            "message": f"Unsupported message type: {data.type}",
                        }
                    )
                    await send_lifecycle(
                        stage="request_rejected_unsupported_type",
                        request_id=request_id,
                        session_id=session_id,
                        details={"type": data.type},
                    )
                    continue

                await send_lifecycle(
                    stage="request_dispatched",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "model": data.model,
                        "requested_agent_id": requested_agent_id,
                        "effective_agent_id": resolved_agent_id,
                        "routing_reason": routing_reason,
                        "preset": applied_preset,
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

                selected_model = (data.model or "").strip() or runtime_state.model
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
                    user_message=data.content,
                    send_event=send_event,
                    request_context=RequestContext(
                        session_id=session_id,
                        request_id=request_id,
                        runtime=runtime_state.runtime,
                        model=selected_model,
                        tool_policy=incoming_tool_policy,
                        agent_id=resolved_agent_id,
                        depth=0,
                        preset=applied_preset,
                        orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
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