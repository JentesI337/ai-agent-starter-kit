from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.head_coder_adapter import HeadCoderAgentAdapter
from app.config import settings
from app.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError
from app.interfaces import OrchestratorApi, RequestContext
from app.models import WsInboundMessage
from app.orchestrator.events import build_lifecycle_event, classify_error
from app.orchestrator.subrun_lane import SubrunLane
from app.runtime_manager import RuntimeManager
from app.state import StateStore

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app.main")

app = FastAPI(title="AI Agent Starter Kit")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = HeadCoderAgentAdapter()
runtime_manager = RuntimeManager()
state_store = StateStore(persist_dir=settings.orchestrator_state_dir)
orchestrator_api = OrchestratorApi(agent=agent, state_store=state_store)
subrun_lane = SubrunLane(
    orchestrator_api=orchestrator_api,
    state_store=state_store,
    max_concurrent=settings.subrun_max_concurrent,
    max_spawn_depth=settings.subrun_max_spawn_depth,
    max_children_per_parent=settings.subrun_max_children_per_parent,
    announce_retry_max_attempts=settings.subrun_announce_retry_max_attempts,
    announce_retry_base_delay_ms=settings.subrun_announce_retry_base_delay_ms,
    announce_retry_max_delay_ms=settings.subrun_announce_retry_max_delay_ms,
    announce_retry_jitter=settings.subrun_announce_retry_jitter,
)
active_run_tasks: dict[str, asyncio.Task] = {}


def _remove_active_task(run_id: str) -> None:
    active_run_tasks.pop(run_id, None)


def _state_append_event_safe(run_id: str, event: dict) -> None:
    try:
        state_store.append_event(run_id=run_id, event=event)
    except Exception:
        logger.debug("state_append_event_failed run_id=%s", run_id, exc_info=True)


def _state_mark_failed_safe(run_id: str, error: str) -> None:
    try:
        state_store.mark_failed(run_id=run_id, error=error)
    except Exception:
        logger.debug("state_mark_failed_failed run_id=%s", run_id, exc_info=True)


def _state_mark_completed_safe(run_id: str) -> None:
    try:
        state_store.mark_completed(run_id=run_id)
    except Exception:
        logger.debug("state_mark_completed_failed run_id=%s", run_id, exc_info=True)


class AgentTestRequest(BaseModel):
    message: str = "hi"
    model: str | None = None
    tool_policy: dict[str, list[str]] | None = None


class RunStartRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None
    tool_policy: dict[str, list[str]] | None = None


class KillAllSubrunsRequest(BaseModel):
    parent_session_id: str | None = None
    parent_request_id: str | None = None
    cascade: bool = True
    requester_session_id: str | None = None
    visibility_scope: str | None = None


def _normalize_visibility_scope(value: str | None) -> str:
    scope = (value or settings.session_visibility_default or "tree").strip().lower()
    if scope not in {"self", "tree", "agent", "all"}:
        return "tree"
    return scope


def _enforce_subrun_visibility_or_403(run_id: str, requester_session_id: str | None, visibility_scope: str | None) -> dict:
    scope = _normalize_visibility_scope(visibility_scope)
    allowed, decision = subrun_lane.evaluate_visibility(
        run_id,
        requester_session_id=(requester_session_id or ""),
        visibility_scope=scope,
    )

    _state_append_event_safe(
        run_id=run_id,
        event={
            "type": "visibility_decision",
            "decision": decision,
        },
    )

    if not allowed:
        raise HTTPException(status_code=403, detail={"message": "Subrun visibility denied", "decision": decision})
    return decision


def _extract_final_message(run_state: dict) -> str | None:
    events = run_state.get("events") or []
    for event in reversed(events):
        if event.get("type") == "final" and event.get("message"):
            return event.get("message")
    return None


async def _run_background_message(
    *,
    run_id: str,
    session_id: str,
    message: str,
    model: str | None,
    tool_policy: dict[str, list[str]] | None,
) -> None:
    async def collect_event(payload: dict) -> None:
        _state_append_event_safe(run_id=run_id, event=payload)

    try:
        state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="active")
        _state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_started",
                details={},
                agent=agent.name,
            ),
        )

        runtime_state = runtime_manager.get_state()
        selected_model = (model or "").strip() or runtime_state.model

        agent.configure_runtime(
            base_url=runtime_state.base_url,
            model=runtime_state.model,
        )

        if runtime_state.runtime == "local":
            selected_model = await runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
        else:
            selected_model = await runtime_manager.resolve_api_request_model(selected_model)

        await orchestrator_api.run_user_message(
            user_message=message,
            send_event=collect_event,
            request_context=RequestContext(
                session_id=session_id,
                request_id=run_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=tool_policy,
            ),
        )
        _state_mark_completed_safe(run_id=run_id)
        _state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_completed",
                details={},
                agent=agent.name,
            ),
        )
    except Exception as exc:
        _state_mark_failed_safe(run_id=run_id, error=str(exc))
        _state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_failed",
                details={"error": str(exc)},
                agent=agent.name,
            ),
        )
        logger.exception("background_run_failed run_id=%s session_id=%s", run_id, session_id)
    finally:
        _remove_active_task(run_id)


@app.get("/api/agents")
async def get_agents():
    active = runtime_manager.get_state()
    return [
        {
            "id": "head-coder",
            "name": "Head Coding Agent",
            "role": "coding-head-agent",
            "status": "ready",
            "defaultModel": active.model,
        }
    ]


@app.get("/api/runtime/status")
async def get_runtime_status():
    state = runtime_manager.get_state()
    api_models = await runtime_manager.get_api_models_summary()
    return {
        "runtime": state.runtime,
        "baseUrl": state.base_url,
        "model": state.model,
        "authenticated": runtime_manager.is_runtime_authenticated(),
        "apiSupportedModels": settings.api_supported_models,
        "apiModelsAvailable": api_models["available"],
        "apiModelsCount": api_models["count"],
        "apiModelsError": api_models["error"],
    }


@app.get("/api/test/ping")
async def test_ping():
    state = runtime_manager.get_state()
    return {
        "ok": True,
        "service": "backend",
        "runtime": state.runtime,
        "model": state.model,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/test/agent")
async def test_agent(request: AgentTestRequest):
    runtime_state = runtime_manager.get_state()
    session_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    events: list[dict] = []
    logger.info(
        "agent_test_start request_id=%s session_id=%s runtime=%s model=%s message_len=%s",
        request_id,
        session_id,
        runtime_state.runtime,
        request.model or runtime_state.model,
        len(request.message or ""),
    )
    state_store.init_run(
        run_id=request_id,
        session_id=session_id,
        request_id=request_id,
        user_message=request.message or "",
        runtime=runtime_state.runtime,
        model=request.model or runtime_state.model,
    )
    state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")

    async def collect_event(payload: dict):
        events.append(payload)

    agent.configure_runtime(
        base_url=runtime_state.base_url,
        model=runtime_state.model,
    )

    selected_model = (request.model or "").strip() or runtime_state.model
    if runtime_state.runtime == "local":
        selected_model = await runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
    else:
        selected_model = await runtime_manager.resolve_api_request_model(selected_model)

    try:
        await orchestrator_api.run_user_message(
            user_message=request.message,
            send_event=collect_event,
            request_context=RequestContext(
                session_id=session_id,
                request_id=request_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=request.tool_policy,
            ),
        )
        _state_mark_completed_safe(run_id=request_id)
    except (GuardrailViolation, ToolExecutionError, RuntimeSwitchError) as exc:
        _state_mark_failed_safe(run_id=request_id, error=str(exc))
        logger.warning(
            "agent_test_client_error request_id=%s session_id=%s error=%s",
            request_id,
            session_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LlmClientError as exc:
        _state_mark_failed_safe(run_id=request_id, error=str(exc))
        logger.warning(
            "agent_test_llm_error request_id=%s session_id=%s error=%s",
            request_id,
            session_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        _state_mark_failed_safe(run_id=request_id, error=str(exc))
        logger.exception(
            "agent_test_unhandled request_id=%s session_id=%s",
            request_id,
            session_id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    final_event = next((item for item in reversed(events) if item.get("type") == "final"), None)
    return {
        "ok": True,
        "runtime": runtime_state.runtime,
        "model": selected_model,
        "sessionId": session_id,
        "requestId": request_id,
        "eventCount": len(events),
        "final": final_event.get("message") if final_event else None,
    }


@app.post("/api/runs/start")
async def start_run(request: RunStartRequest):
    runtime_state = runtime_manager.get_state()
    run_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    state_store.init_run(
        run_id=run_id,
        session_id=session_id,
        request_id=run_id,
        user_message=request.message or "",
        runtime=runtime_state.runtime,
        model=request.model or runtime_state.model,
        meta={"source": "rest", "async": True},
    )
    state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="pending")
    _state_append_event_safe(
        run_id=run_id,
        event=build_lifecycle_event(
            request_id=run_id,
            session_id=session_id,
            stage="accepted",
            details={"source": "api", "chars": len(request.message or "")},
            agent=agent.name,
        ),
    )

    task = asyncio.create_task(
        _run_background_message(
            run_id=run_id,
            session_id=session_id,
            message=request.message,
            model=request.model,
            tool_policy=request.tool_policy,
        )
    )
    active_run_tasks[run_id] = task

    return {
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
    }


@app.get("/api/runs/{run_id}/wait")
async def wait_run(run_id: str, timeout_ms: int | None = None, poll_interval_ms: int | None = None):
    run_state = state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    timeout = max(0, int(timeout_ms if timeout_ms is not None else settings.run_wait_default_timeout_ms))
    poll = max(10, int(poll_interval_ms if poll_interval_ms is not None else settings.run_wait_poll_interval_ms))
    elapsed = 0

    while elapsed <= timeout:
        run_state = state_store.get_run(run_id)
        if run_state is None:
            raise HTTPException(status_code=404, detail="Run not found")

        status = run_state.get("status")
        if status in {"completed", "failed"}:
            return {
                "status": "ok" if status == "completed" else "error",
                "runId": run_id,
                "runStatus": status,
                "error": run_state.get("error"),
                "final": _extract_final_message(run_state),
            }

        task = active_run_tasks.get(run_id)
        if task and task.done():
            refreshed = state_store.get_run(run_id)
            return {
                "status": "ok" if (refreshed or {}).get("status") == "completed" else "error",
                "runId": run_id,
                "runStatus": (refreshed or {}).get("status"),
                "error": (refreshed or {}).get("error"),
                "final": _extract_final_message(refreshed or {}),
            }

        await asyncio.sleep(poll / 1000.0)
        elapsed += poll

    return {
        "status": "timeout",
        "runId": run_id,
        "runStatus": (state_store.get_run(run_id) or {}).get("status"),
    }


@app.get("/api/subruns")
async def list_subruns(
    parent_session_id: str | None = None,
    parent_request_id: str | None = None,
    requester_session_id: str | None = None,
    visibility_scope: str | None = None,
    limit: int = 100,
):
    scope = _normalize_visibility_scope(visibility_scope)
    return {
        "items": subrun_lane.list_runs(
            parent_session_id=parent_session_id,
            parent_request_id=parent_request_id,
            requester_session_id=requester_session_id,
            visibility_scope=scope,
            limit=limit,
        ),
        "visibility_scope": scope,
        "requester_session_id": requester_session_id,
    }


@app.get("/api/subruns/{run_id}")
async def get_subrun_info(run_id: str, requester_session_id: str, visibility_scope: str | None = None):
    decision = _enforce_subrun_visibility_or_403(run_id, requester_session_id, visibility_scope)
    info = subrun_lane.get_info(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Subrun not found")
    info["visibility_decision"] = decision
    return info


@app.get("/api/subruns/{run_id}/log")
async def get_subrun_log(run_id: str, requester_session_id: str, visibility_scope: str | None = None):
    decision = _enforce_subrun_visibility_or_403(run_id, requester_session_id, visibility_scope)
    log = subrun_lane.get_log(run_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Subrun not found")
    return {"runId": run_id, "events": log, "visibility_decision": decision}


@app.post("/api/subruns/{run_id}/kill")
async def kill_subrun(
    run_id: str,
    requester_session_id: str,
    visibility_scope: str | None = None,
    cascade: bool = True,
):
    decision = _enforce_subrun_visibility_or_403(run_id, requester_session_id, visibility_scope)
    killed = await subrun_lane.kill(run_id, cascade=cascade)
    if not killed:
        raise HTTPException(status_code=404, detail="Subrun not running or not found")
    return {"runId": run_id, "killed": True, "cascade": cascade, "visibility_decision": decision}


@app.post("/api/subruns/kill-all")
async def kill_all_subruns(request: KillAllSubrunsRequest):
    scope = _normalize_visibility_scope(request.visibility_scope)
    killed_count = await subrun_lane.kill_all(
        parent_session_id=request.parent_session_id,
        parent_request_id=request.parent_request_id,
        cascade=request.cascade,
    )
    return {
        "killed": killed_count,
        "parent_session_id": request.parent_session_id,
        "parent_request_id": request.parent_request_id,
        "cascade": request.cascade,
        "requester_session_id": request.requester_session_id,
        "visibility_scope": scope,
    }


@app.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket):
    await websocket.accept()
    connection_session_id = str(uuid.uuid4())
    runtime_state = runtime_manager.get_state()
    sequence_number = 0
    logger.info(
        "ws_connected session_id=%s runtime=%s model=%s",
        connection_session_id,
        runtime_state.runtime,
        runtime_state.model,
    )

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
            logger.debug(
                "ws_send_event session_id=%s seq=%s type=%s request_id=%s",
                payload.get("session_id", connection_session_id),
                sequence_number,
                payload.get("type"),
                payload.get("request_id"),
            )
            await websocket.send_text(json.dumps(envelope))
        except (WebSocketDisconnect, RuntimeError) as exc:
            logger.info(
                "ws_send_event_disconnected session_id=%s type=%s",
                payload.get("session_id", connection_session_id),
                payload.get("type"),
            )
            raise ClientDisconnectedError() from exc

    await send_event(
        {
            "type": "status",
            "agent": agent.name,
            "message": "Connected to head agent.",
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
            agent=agent.name,
        )
        _state_append_event_safe(
            run_id=request_id,
            event={"stage": stage, "session_id": session_id, "details": details or {}},
        )
        await send_event(
            lifecycle_event
        )

    try:
        while True:
            request_id = str(uuid.uuid4())
            session_id = connection_session_id
            try:
                raw = await websocket.receive_text()
                data = WsInboundMessage.model_validate_json(raw)
                session_id = data.session_id or connection_session_id
                logger.info(
                    "ws_message_received request_id=%s session_id=%s type=%s agent_id=%s content_len=%s requested_model=%s",
                    request_id,
                    session_id,
                    data.type,
                    data.agent_id or "head-coder",
                    len(data.content or ""),
                    data.model,
                )
                current_runtime_state = runtime_manager.get_state()
                state_store.init_run(
                    run_id=request_id,
                    session_id=session_id,
                    request_id=request_id,
                    user_message=data.content or "",
                    runtime=current_runtime_state.runtime,
                    model=data.model or current_runtime_state.model,
                )
                state_store.set_task_status(run_id=request_id, task_id="request", label="request", status="active")
                await send_lifecycle(
                    stage="request_received",
                    request_id=request_id,
                    session_id=session_id,
                    details={"chars": len(data.content), "agent_id": data.agent_id or "head-coder"},
                )

                if data.type == "runtime_switch_request":
                    target = (data.runtime_target or "").strip().lower()
                    await send_lifecycle(
                        stage="runtime_switch_requested",
                        request_id=request_id,
                        session_id=session_id,
                        details={"target": target},
                    )
                    state = await runtime_manager.switch_runtime(target, send_event, session_id)
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
                    runtime_state = runtime_manager.get_state()
                    selected_model = (data.model or "").strip() or runtime_state.model
                    if runtime_state.runtime == "local":
                        selected_model = await runtime_manager.ensure_model_ready(send_event, session_id, selected_model)
                    else:
                        selected_model = await runtime_manager.resolve_api_request_model(selected_model)

                    try:
                        run_id = await subrun_lane.spawn(
                            parent_request_id=request_id,
                            parent_session_id=session_id,
                            user_message=data.content,
                            runtime=runtime_state.runtime,
                            model=selected_model,
                            timeout_seconds=settings.subrun_timeout_seconds,
                            tool_policy=data.tool_policy.model_dump(exclude_none=True) if data.tool_policy else None,
                            send_event=send_event,
                        )
                    except GuardrailViolation as exc:
                        _state_mark_failed_safe(run_id=request_id, error=str(exc))
                        await send_event(
                            {
                                "type": "error",
                                "agent": agent.name,
                                "message": f"Subrun policy blocked request: {exc}",
                                "error_category": classify_error(exc),
                            }
                        )
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
                        details={"subrun_id": run_id, "model": selected_model},
                    )
                    await send_lifecycle(
                        stage="request_completed",
                        request_id=request_id,
                        session_id=session_id,
                        details={"spawned_subrun_id": run_id},
                    )
                    _state_mark_completed_safe(run_id=request_id)
                    continue

                if data.type != "user_message":
                    await send_event(
                        {
                            "type": "status",
                            "agent": agent.name,
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

                if data.agent_id and data.agent_id != "head-coder":
                    await send_event(
                        {
                            "type": "status",
                            "agent": agent.name,
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

                await send_lifecycle(
                    stage="request_dispatched",
                    request_id=request_id,
                    session_id=session_id,
                    details={"model": data.model},
                )

                runtime_state = runtime_manager.get_state()
                logger.info(
                    "ws_request_dispatch request_id=%s session_id=%s runtime=%s active_model=%s",
                    request_id,
                    session_id,
                    runtime_state.runtime,
                    runtime_state.model,
                )

                agent.configure_runtime(
                    base_url=runtime_state.base_url,
                    model=runtime_state.model,
                )

                selected_model = (data.model or "").strip() or runtime_state.model
                if runtime_state.runtime == "local":
                    resolved_model = await runtime_manager.ensure_model_ready(send_event, session_id, selected_model)
                    if resolved_model != selected_model:
                        await send_event(
                            {
                                "type": "status",
                                "agent": agent.name,
                                "message": f"Model '{selected_model}' not available. Using '{resolved_model}'.",
                            }
                        )
                        selected_model = resolved_model
                        if runtime_state.model != resolved_model:
                            runtime_manager.set_active_model(resolved_model)
                else:
                    resolved_model = await runtime_manager.resolve_api_request_model(selected_model)
                    if resolved_model != selected_model:
                        await send_event(
                            {
                                "type": "status",
                                "agent": agent.name,
                                "message": f"API model '{selected_model}' not available. Using '{resolved_model}'.",
                            }
                        )
                        selected_model = resolved_model
                        if runtime_state.model != resolved_model:
                            runtime_manager.set_active_model(resolved_model)

                logger.info(
                    "ws_agent_run_start request_id=%s session_id=%s selected_model=%s",
                    request_id,
                    session_id,
                    selected_model,
                )
                await orchestrator_api.run_user_message(
                    user_message=data.content,
                    send_event=send_event,
                    request_context=RequestContext(
                        session_id=session_id,
                        request_id=request_id,
                        runtime=runtime_state.runtime,
                        model=selected_model,
                        tool_policy=data.tool_policy.model_dump(exclude_none=True) if data.tool_policy else None,
                    ),
                )
                logger.info(
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
                _state_mark_completed_safe(run_id=request_id)
            except (WebSocketDisconnect, ClientDisconnectedError):
                logger.info("ws_disconnected session_id=%s", session_id)
                break
            except GuardrailViolation as exc:
                _state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
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
                _state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
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
                _state_mark_failed_safe(run_id=request_id, error=str(exc))
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
                _state_mark_failed_safe(run_id=request_id, error=str(exc))
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
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
                _state_mark_failed_safe(run_id=request_id, error=str(exc))
                logger.exception(
                    "ws_unhandled_error request_id=%s session_id=%s",
                    request_id,
                    session_id,
                )
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
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
        logger.info("ws_outer_disconnect session_id=%s", connection_session_id)
        return
    except ClientDisconnectedError:
        logger.info("ws_outer_client_disconnected session_id=%s", connection_session_id)
        return
    except Exception as exc:
        logger.exception("ws_server_error session_id=%s", connection_session_id)
        try:
            await send_event(
                {
                    "type": "error",
                    "agent": agent.name,
                    "message": f"Server error: {exc}",
                }
            )
        except ClientDisconnectedError:
            return
