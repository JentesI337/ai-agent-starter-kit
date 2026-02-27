from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.agent import HeadCodingAgent
from app.errors import GuardrailViolation, LlmClientError, RuntimeAuthRequiredError, RuntimeSwitchError, ToolExecutionError
from app.models import WsInboundMessage
from app.runtime_manager import RuntimeManager

app = FastAPI(title="AI Agent Starter Kit")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = HeadCodingAgent()
runtime_manager = RuntimeManager()


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
    return {
        "runtime": state.runtime,
        "baseUrl": state.base_url,
        "model": state.model,
        "authenticated": bool(state.api_key),
    }


@app.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket):
    await websocket.accept()
    connection_session_id = str(uuid.uuid4())
    pending_runtime_target: str | None = None
    await websocket.send_json(
        {
            "type": "status",
            "agent": agent.name,
            "message": "Connected to head agent.",
            "session_id": connection_session_id,
        }
    )

    async def send_event(payload: dict):
        await websocket.send_text(json.dumps(payload))

    async def send_lifecycle(stage: str, request_id: str, session_id: str, details: dict | None = None):
        await send_event(
            {
                "type": "lifecycle",
                "agent": agent.name,
                "stage": stage,
                "request_id": request_id,
                "session_id": session_id,
                "ts": datetime.now(timezone.utc).isoformat(),
                "details": details or {},
            }
        )

    try:
        while True:
            request_id = str(uuid.uuid4())
            session_id = connection_session_id
            try:
                raw = await websocket.receive_text()
                data = WsInboundMessage.model_validate_json(raw)
                session_id = data.session_id or connection_session_id
                await send_lifecycle(
                    stage="request_received",
                    request_id=request_id,
                    session_id=session_id,
                    details={"chars": len(data.content), "agent_id": data.agent_id or "head-coder"},
                )

                if data.type == "runtime_switch_request":
                    target = (data.runtime_target or "").strip().lower()
                    pending_runtime_target = target
                    await send_lifecycle(
                        stage="runtime_switch_requested",
                        request_id=request_id,
                        session_id=session_id,
                        details={"target": target},
                    )
                    try:
                        state = await runtime_manager.switch_runtime(target, send_event, session_id)
                        pending_runtime_target = None
                        await send_event(
                            {
                                "type": "runtime_switch_done",
                                "session_id": session_id,
                                "runtime": state.runtime,
                                "model": state.model,
                                "base_url": state.base_url,
                            }
                        )
                    except RuntimeAuthRequiredError as exc:
                        await send_event(
                            {
                                "type": "runtime_auth_required",
                                "session_id": session_id,
                                "auth_url": exc.auth_url,
                                "message": "Authentication required before switching to API runtime.",
                            }
                        )
                    continue

                if data.type == "runtime_auth_complete":
                    api_key = (data.api_key or "").strip()
                    if api_key:
                        runtime_manager.set_api_key(api_key)
                    if pending_runtime_target:
                        try:
                            state = await runtime_manager.switch_runtime(pending_runtime_target, send_event, session_id)
                            pending_runtime_target = None
                            await send_event(
                                {
                                    "type": "runtime_switch_done",
                                    "session_id": session_id,
                                    "runtime": state.runtime,
                                    "model": state.model,
                                    "base_url": state.base_url,
                                }
                            )
                        except RuntimeAuthRequiredError as exc:
                            await send_event(
                                {
                                    "type": "runtime_auth_required",
                                    "session_id": session_id,
                                    "auth_url": exc.auth_url,
                                    "message": "Authentication still required.",
                                }
                            )
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
                agent.configure_runtime(
                    base_url=runtime_state.base_url,
                    api_key=runtime_state.api_key,
                    model=runtime_state.model,
                )

                await agent.run(
                    data.content,
                    send_event,
                    session_id=session_id,
                    request_id=request_id,
                    model=data.model,
                )
                await send_lifecycle(
                    stage="request_completed",
                    request_id=request_id,
                    session_id=session_id,
                )
            except GuardrailViolation as exc:
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
                        "message": f"Guardrail blocked request: {exc}",
                    }
                )
                await send_lifecycle(
                    stage="request_failed_guardrail",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)},
                )
            except ToolExecutionError as exc:
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
                        "message": f"Toolchain error: {exc}",
                    }
                )
                await send_lifecycle(
                    stage="request_failed_toolchain",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)},
                )
            except RuntimeSwitchError as exc:
                await send_event(
                    {
                        "type": "runtime_switch_error",
                        "session_id": session_id,
                        "message": str(exc),
                    }
                )
                await send_lifecycle(
                    stage="runtime_switch_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)},
                )
            except LlmClientError as exc:
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
                        "message": f"LLM error: {exc}",
                    }
                )
                await send_lifecycle(
                    stage="request_failed_llm",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)},
                )
            except Exception as exc:
                await send_event(
                    {
                        "type": "error",
                        "agent": agent.name,
                        "message": f"Request error: {exc}",
                    }
                )
                await send_lifecycle(
                    stage="request_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)},
                )
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await send_event(
            {
                "type": "error",
                "agent": agent.name,
                "message": f"Server error: {exc}",
            }
        )
