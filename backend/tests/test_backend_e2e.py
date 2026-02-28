from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient

from app.main import app, agent, runtime_manager
from app.runtime_manager import RuntimeState


def _set_local_runtime() -> None:
    runtime_manager._state = RuntimeState(
        runtime="local",
        base_url="http://localhost:11434/v1",
        model="llama3.3:70b-instruct-q4_K_M",
    )


def test_runtime_status_endpoint_includes_api_model_health_fields() -> None:
    _set_local_runtime()
    client = TestClient(app)

    response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"] in ("local", "api")
    assert "baseUrl" in payload
    assert "model" in payload
    assert "authenticated" in payload
    assert "apiModelsAvailable" in payload
    assert "apiModelsCount" in payload
    assert "apiModelsError" in payload


def test_rest_ping_endpoint_without_agent() -> None:
    _set_local_runtime()
    client = TestClient(app)

    response = client.get("/api/test/ping")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "backend"
    assert payload["runtime"] in ("local", "api")
    assert isinstance(payload.get("ts"), str)


def test_rest_agent_endpoint_with_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-coder",
                "message": f"echo:{user_message}",
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)
    response = client.post(
        "/api/test/agent",
        json={"message": "hi", "model": "llama3.3:70b-instruct-q4_K_M"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["runtime"] == "local"
    assert payload["model"] == "llama3.3:70b-instruct-q4_K_M"
    assert payload["final"] == "echo:hi"
    assert payload["eventCount"] >= 1


def test_websocket_connect_emits_status_event() -> None:
    _set_local_runtime()
    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        event = ws.receive_json()

    assert event["type"] == "status"
    assert event["message"] == "Connected to head agent."
    assert "session_id" in event


def test_websocket_user_message_emits_final_and_request_completed(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-coder",
                "message": f"echo:{user_message}",
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = ws.receive_json()
        ws.send_json(
            {
                "type": "user_message",
                "content": "hi",
                "agent_id": "head-coder",
            }
        )

        events = []
        for _ in range(12):
            evt = ws.receive_json()
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_received" for evt in events)
    assert any(evt.get("type") == "final" and evt.get("message") == "echo:hi" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed" for evt in events)
