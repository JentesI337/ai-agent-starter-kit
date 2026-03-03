from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient

from app.main import app, agent, agent_registry, runtime_manager, subrun_lane
from app.runtime_manager import RuntimeState


def _set_local_runtime() -> None:
    runtime_manager._state = RuntimeState(
        runtime="local",
        base_url="http://localhost:11434/v1",
        model="llama3.3:70b-instruct-q4_K_M",
    )


def _unwrap_event(envelope: dict) -> dict:
    assert "seq" in envelope
    assert isinstance(envelope["seq"], int)
    assert "event" in envelope
    return envelope["event"]


def test_ws_handler_routes_coding_intent_to_coder_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_head_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event({"type": "final", "agent": "head-agent", "message": "head-should-not-handle"})
        return "head-should-not-handle"

    async def fake_coder_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event({"type": "final", "agent": "coder-agent", "message": f"coder:{user_message}"})
        return f"coder:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_head_run)
    monkeypatch.setattr(agent_registry["coder-agent"], "run", fake_coder_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "user_message", "content": "write a python script", "agent_id": "head-agent"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(ws.receive_json())
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(
        evt.get("type") == "status"
        and "delegated this request to coder-agent" in str(evt.get("message", "")).lower()
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("agent") == "coder-agent" for evt in events)


def test_ws_handler_subrun_spawn_emits_accepted_with_default_mode(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"subrun:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"subrun:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "subrun_spawn", "content": "background"})

        accepted_event = None
        for _ in range(24):
            evt = _unwrap_event(ws.receive_json())
            if evt.get("type") == "subrun_status" and evt.get("status") == "accepted":
                accepted_event = evt
                break

    assert accepted_event is not None
    assert accepted_event.get("mode") == "run"
    assert accepted_event.get("agent_id") == "head-agent"


def test_ws_handler_guardrail_depth_rejection_emits_error_and_lifecycle(monkeypatch) -> None:
    _set_local_runtime()
    monkeypatch.setattr(subrun_lane, "_leaf_spawn_depth_guard_enabled", True)
    monkeypatch.setattr(subrun_lane, "_orchestrator_agent_ids", {"head-agent"})

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "subrun_spawn", "content": "blocked child", "agent_id": "coder-agent"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(ws.receive_json())
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_depth_policy":
                break

    assert any(
        evt.get("type") == "error" and "Subrun depth policy blocked request" in str(evt.get("message", ""))
        for evt in events
    )
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "subrun_rejected_depth_policy" for evt in events)
    assert any(
        evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_depth_policy"
        for evt in events
    )


def test_ws_handler_disconnect_is_graceful_and_reconnects() -> None:
    _set_local_runtime()
    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        first = _unwrap_event(ws.receive_json())
        assert first.get("type") == "status"

    with client.websocket_connect("/ws/agent") as ws:
        second = _unwrap_event(ws.receive_json())
        assert second.get("type") == "status"


def test_ws_handler_unsupported_type_emits_rejection_lifecycle() -> None:
    _set_local_runtime()
    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "unknown_type", "content": "hello", "agent_id": "head-agent"})

        events = []
        for _ in range(12):
            evt = _unwrap_event(ws.receive_json())
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_unsupported_type":
                break

    assert any(
        evt.get("type") == "status" and "unsupported message type" in str(evt.get("message", "")).lower()
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_unsupported_type"
        for evt in events
    )
