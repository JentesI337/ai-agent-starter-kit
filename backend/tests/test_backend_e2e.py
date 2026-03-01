from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient

from app.main import app, agent, runtime_manager, subrun_lane
from app.errors import GuardrailViolation
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
    assert "apiSupportedModels" in payload
    assert "minimax-m2:cloud" in payload["apiSupportedModels"]
    assert "gpt-oss:20b-cloud" in payload["apiSupportedModels"]
    assert "qwen3-coder:480b-cloud" in payload["apiSupportedModels"]
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

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
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
        envelope = ws.receive_json()
        event = _unwrap_event(envelope)

    assert event["type"] == "status"
    assert event["message"] == "Connected to head agent."
    assert "session_id" in event


def test_websocket_user_message_emits_final_and_request_completed(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
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
        _ = _unwrap_event(ws.receive_json())
        ws.send_json(
            {
                "type": "user_message",
                "content": "hi",
                "agent_id": "head-coder",
            }
        )

        events = []
        seq_values = []
        for _ in range(12):
            envelope = ws.receive_json()
            seq_values.append(envelope.get("seq"))
            evt = _unwrap_event(envelope)
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert seq_values == sorted(seq_values)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_received" for evt in events)
    assert any(evt.get("type") == "final" and evt.get("message") == "echo:hi" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed" for evt in events)


def test_websocket_subrun_spawn_emits_status_and_announce(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-coder",
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
        ws.send_json(
            {
                "type": "subrun_spawn",
                "content": "background task",
                "agent_id": "head-coder",
            }
        )

        events = []
        for _ in range(24):
            evt = _unwrap_event(ws.receive_json())
            events.append(evt)
            if evt.get("type") == "subrun_announce":
                break

    assert any(evt.get("type") == "subrun_status" and evt.get("status") == "accepted" for evt in events)
    assert any(evt.get("type") == "subrun_status" and evt.get("status") == "running" for evt in events)
    assert any(evt.get("type") == "subrun_status" and evt.get("status") == "completed" for evt in events)
    assert any(evt.get("type") == "subrun_announce" and evt.get("status") == "completed" for evt in events)


def test_runs_start_and_wait_returns_ok(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-coder",
                "message": f"echo:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    start = client.post("/api/runs/start", json={"message": "hello"})
    assert start.status_code == 200
    run_id = start.json()["runId"]

    wait = client.get(f"/api/runs/{run_id}/wait", params={"timeout_ms": 3000, "poll_interval_ms": 50})
    assert wait.status_code == 200
    payload = wait.json()
    assert payload["status"] == "ok"
    assert payload["runStatus"] == "completed"
    assert payload["final"] == "echo:hello"


def test_subrun_management_endpoints(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-coder",
                "message": f"subrun:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"subrun:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    subrun_id = None
    parent_session_id = None
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "subrun_spawn", "content": "mgmt", "agent_id": "head-coder"})

        for _ in range(24):
            evt = _unwrap_event(ws.receive_json())
            if evt.get("type") == "subrun_status" and evt.get("status") == "accepted":
                subrun_id = evt.get("run_id")
                parent_session_id = evt.get("parent_session_id")
            if evt.get("type") == "subrun_announce":
                break

    assert subrun_id
    assert parent_session_id

    list_resp = client.get("/api/subruns")
    assert list_resp.status_code == 200
    assert any(item.get("run_id") == subrun_id for item in list_resp.json()["items"])

    info_resp = client.get(
        f"/api/subruns/{subrun_id}",
        params={"requester_session_id": parent_session_id, "visibility_scope": "tree"},
    )
    assert info_resp.status_code == 200
    assert info_resp.json()["run_id"] == subrun_id

    log_resp = client.get(
        f"/api/subruns/{subrun_id}/log",
        params={"requester_session_id": parent_session_id, "visibility_scope": "tree"},
    )
    assert log_resp.status_code == 200
    assert isinstance(log_resp.json()["events"], list)


def test_websocket_subrun_spawn_policy_rejected_emits_specific_lifecycle(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_spawn(**kwargs):
        raise GuardrailViolation("depth limit exceeded")

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(subrun_lane, "spawn", fake_spawn)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "subrun_spawn", "content": "blocked", "agent_id": "head-coder"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(ws.receive_json())
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_policy":
                break

    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "subrun_rejected_policy" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_policy" for evt in events)


def test_websocket_reply_shaping_suppression_emits_lifecycle(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event(
            {
                "type": "lifecycle",
                "stage": "reply_shaping_started",
                "request_id": request_id,
                "session_id": session_id,
                "details": {"input_chars": 8},
            }
        )
        await send_event(
            {
                "type": "lifecycle",
                "stage": "reply_shaping_completed",
                "request_id": request_id,
                "session_id": session_id,
                "details": {"suppressed": True, "reason": "no_reply_token"},
            }
        )
        await send_event(
            {
                "type": "lifecycle",
                "stage": "reply_suppressed",
                "request_id": request_id,
                "session_id": session_id,
                "details": {"reason": "no_reply_token"},
            }
        )
        await send_event(
            {
                "type": "status",
                "agent": "head-coder",
                "message": "Reply suppressed by shaping: no_reply_token",
            }
        )
        return ""

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "user_message", "content": "hi", "agent_id": "head-coder"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(ws.receive_json())
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "reply_shaping_started" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "reply_shaping_completed" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "reply_suppressed" for evt in events)


def test_subrun_visibility_scope_self_denies_and_tree_allows(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        await send_event(
            {
                "type": "final",
                "agent": "head-coder",
                "message": f"subrun:{user_message}",
                "request_id": request_id,
                "session_id": session_id,
            }
        )
        return f"subrun:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    subrun_id = None
    parent_session_id = None
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(ws.receive_json())
        ws.send_json({"type": "subrun_spawn", "content": "visible", "agent_id": "head-coder"})

        for _ in range(24):
            evt = _unwrap_event(ws.receive_json())
            if evt.get("type") == "subrun_status" and evt.get("status") == "accepted":
                subrun_id = evt.get("run_id")
                parent_session_id = evt.get("parent_session_id")
            if evt.get("type") == "subrun_announce":
                break

    assert subrun_id
    assert parent_session_id

    denied = client.get(
        f"/api/subruns/{subrun_id}",
        params={"requester_session_id": "some-other-session", "visibility_scope": "self"},
    )
    assert denied.status_code == 403

    allowed = client.get(
        f"/api/subruns/{subrun_id}",
        params={"requester_session_id": parent_session_id, "visibility_scope": "tree"},
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["run_id"] == subrun_id
    assert payload["visibility_decision"]["allowed"] is True
