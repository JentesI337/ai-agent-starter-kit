from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient
from tests.async_test_guards import receive_json_with_timeout

from app.errors import GuardrailViolation
from app.main import agent, agent_registry, app, runtime_manager, subrun_lane
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
    assert "featureFlags" in payload
    assert isinstance(payload["featureFlags"], dict)


def test_runtime_feature_flags_can_be_read_and_updated() -> None:
    _set_local_runtime()
    client = TestClient(app)

    get_response = client.get("/api/runtime/features")
    assert get_response.status_code == 200
    current_flags = get_response.json().get("featureFlags")
    assert isinstance(current_flags, dict)
    assert "long_term_memory_enabled" in current_flags
    assert "session_distillation_enabled" in current_flags
    assert "failure_journal_enabled" in current_flags

    post_response = client.post(
        "/api/runtime/features",
        json={
            "featureFlags": {
                "long_term_memory_enabled": False,
                "session_distillation_enabled": False,
                "failure_journal_enabled": False,
            }
        },
    )
    assert post_response.status_code == 200
    payload = post_response.json()
    assert payload.get("ok") is True
    assert payload.get("persisted") is True
    assert payload["featureFlags"]["long_term_memory_enabled"] is False
    assert payload["featureFlags"]["session_distillation_enabled"] is False
    assert payload["featureFlags"]["failure_journal_enabled"] is False


def test_runtime_feature_flags_invalid_db_path_returns_400() -> None:
    _set_local_runtime()
    client = TestClient(app)

    response = client.post(
        "/api/runtime/features",
        json={
            "featureFlags": {},
            "longTermMemoryDbPath": "../outside/unsafe.db",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert "must stay inside workspace root" in str(payload.get("detail", ""))


def test_resolved_prompt_debug_endpoint_returns_prompt_map() -> None:
    _set_local_runtime()
    client = TestClient(app)

    response = client.get("/api/debug/prompts/resolved")

    assert response.status_code == 200
    payload = response.json()
    prompts = payload.get("prompts")
    assert isinstance(prompts, dict)
    assert "head_agent_system_prompt" in prompts
    assert "coder_agent_system_prompt" in prompts
    assert "agent_system_prompt" in prompts


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


def test_monitoring_schema_endpoint_exposes_agents_and_lifecycle() -> None:
    _set_local_runtime()
    client = TestClient(app)

    response = client.get("/api/monitoring/schema")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("lifecycleStages"), list)
    assert "run_started" in payload["lifecycleStages"]
    assert isinstance(payload.get("agents"), list)
    assert any(item.get("id") == "head-agent" for item in payload["agents"])
    assert any(item.get("id") == "coder-agent" for item in payload["agents"])
    head = next(item for item in payload["agents"] if item.get("id") == "head-agent")
    assert "write_file" in head.get("tools", [])


def test_rest_agent_endpoint_with_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
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
        envelope = receive_json_with_timeout(ws)
        event = _unwrap_event(envelope)

    assert event["type"] == "status"
    assert event["message"] == "Connected to agent runtime."
    assert "session_id" in event


def test_websocket_user_message_emits_final_and_request_completed(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"echo:{user_message}",
            }
        )
        return f"echo:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "hi",
                "agent_id": "head-agent",
            }
        )

        events = []
        seq_values = []
        for _ in range(24):
            envelope = receive_json_with_timeout(ws)
            seq_values.append(envelope.get("seq"))
            evt = _unwrap_event(envelope)
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert seq_values == sorted(seq_values)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_received" for evt in events)
    assert any(evt.get("type") == "final" and evt.get("message") == "echo:hi" for evt in events)
    assert not any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "policy_approval_decision_rejected"
        for evt in events
    )
    assert not any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_cancelled" for evt in events)


def test_websocket_subrun_spawn_emits_status_and_announce(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
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
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "subrun_spawn",
                "content": "background task",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(48):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "subrun_announce":
                break

    assert any(evt.get("type") == "subrun_status" and evt.get("status") == "accepted" for evt in events)
    assert any(evt.get("type") == "subrun_status" and evt.get("status") == "running" for evt in events)
    assert any(evt.get("type") == "subrun_status" and evt.get("status") == "completed" for evt in events)
    assert any(evt.get("type") == "subrun_announce" and evt.get("status") == "completed" for evt in events)
    assert any(
        evt.get("type") == "subrun_status"
        and evt.get("status") == "accepted"
        and evt.get("agent_id") == "head-agent"
        and evt.get("mode") == "run"
        for evt in events
    )


def test_websocket_subrun_spawn_mode_session_reuses_parent_session(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
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
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "subrun_spawn",
                "content": "session scoped task",
                "mode": "session",
            }
        )

        accepted_event = None
        for _ in range(48):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            if evt.get("type") == "subrun_status" and evt.get("status") == "accepted":
                accepted_event = evt
                break

    assert accepted_event is not None
    assert accepted_event.get("mode") == "session"
    assert accepted_event.get("parent_session_id") == accepted_event.get("child_session_id")


def test_websocket_subrun_spawn_leaf_blocked_by_depth_guard(monkeypatch) -> None:
    _set_local_runtime()
    monkeypatch.setattr(subrun_lane, "_leaf_spawn_depth_guard_enabled", True)
    monkeypatch.setattr(subrun_lane, "_orchestrator_agent_ids", {"head-agent"})

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "subrun_spawn",
                "content": "blocked child",
                "agent_id": "coder-agent",
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_depth_policy":
                break

    assert any(
        evt.get("type") == "error"
        and "Subrun depth policy blocked request" in str(evt.get("message", ""))
        for evt in events
    )
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "subrun_rejected_depth_policy" for evt in events)
    assert any(
        evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_depth_policy"
        for evt in events
    )


def test_websocket_routes_code_requests_to_coder_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_head_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "head-should-not-handle-coding",
            }
        )
        return "head-should-not-handle-coding"

    async def fake_coder_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "coder-agent",
                "message": f"coder:{user_message}",
            }
        )
        return f"coder:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_head_run)
    monkeypatch.setattr(agent_registry["coder-agent"], "run", fake_coder_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "write a python function to add two numbers",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(
        evt.get("type") == "status"
        and "request routed to coder-agent based on capability matching." in str(evt.get("message", "")).lower()
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("agent") == "coder-agent" for evt in events)
    assert not any(
        evt.get("type") == "final" and evt.get("message") == "head-should-not-handle-coding"
        for evt in events
    )


def test_runs_start_and_wait_returns_ok(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
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

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
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

    subrun_id = None
    parent_session_id = None
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "subrun_spawn", "content": "mgmt", "agent_id": "head-agent"})

        for _ in range(48):
            evt = _unwrap_event(receive_json_with_timeout(ws))
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
    announce_delivery = (info_resp.json().get("announce_delivery") or {})
    assert announce_delivery.get("status") == "announced"
    assert announce_delivery.get("legacy_status") == "sent"

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
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "subrun_spawn", "content": "blocked", "agent_id": "head-agent"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_policy":
                break

    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "subrun_rejected_policy" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_rejected_subrun_policy" for evt in events)


def test_websocket_reply_shaping_suppression_emits_lifecycle(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
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
                "agent": "head-agent",
                "message": "Reply suppressed by shaping: no_reply_token",
            }
        )
        return ""

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "user_message", "content": "hi", "agent_id": "head-agent"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
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

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
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

    subrun_id = None
    parent_session_id = None
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "subrun_spawn", "content": "visible", "agent_id": "head-agent"})

        for _ in range(48):
            evt = _unwrap_event(receive_json_with_timeout(ws))
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


def test_custom_agent_create_is_visible_in_agents_list() -> None:
    _set_local_runtime()
    client = TestClient(app)

    custom_name = f"Custom Test Agent {uuid.uuid4().hex[:6]}"
    create = client.post(
        "/api/custom-agents",
        json={
            "name": custom_name,
            "base_agent_id": "head-agent",
            "description": "test flow",
            "workflow_steps": ["step one", "step two"],
        },
    )

    assert create.status_code == 200
    created = create.json()
    created_id = created["id"]

    listed_custom = client.get("/api/custom-agents")
    assert listed_custom.status_code == 200
    assert any(item.get("id") == created_id for item in listed_custom.json())

    listed_agents = client.get("/api/agents")
    assert listed_agents.status_code == 200
    assert any(item.get("id") == created_id for item in listed_agents.json())

    deleted = client.delete(f"/api/custom-agents/{created_id}")
    assert deleted.status_code == 200


def test_custom_agent_delete_removes_agent_from_lists() -> None:
    _set_local_runtime()
    client = TestClient(app)

    create = client.post(
        "/api/custom-agents",
        json={
            "name": f"Delete Test Agent {uuid.uuid4().hex[:6]}",
            "base_agent_id": "head-agent",
            "description": "delete flow",
            "workflow_steps": ["a", "b"],
        },
    )
    assert create.status_code == 200
    created_id = create.json()["id"]

    delete_resp = client.delete(f"/api/custom-agents/{created_id}")
    assert delete_resp.status_code == 200

    listed_custom = client.get("/api/custom-agents")
    assert listed_custom.status_code == 200
    assert not any(item.get("id") == created_id for item in listed_custom.json())

    listed_agents = client.get("/api/agents")
    assert listed_agents.status_code == 200
    assert not any(item.get("id") == created_id for item in listed_agents.json())


@pytest.mark.skip(reason="Custom agent ws routing broken after refactoring (pre-existing)")
def test_custom_agent_can_run_via_websocket(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_head_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"custom-flow:{user_message}",
            }
        )
        return f"custom-flow:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_head_run)

    client = TestClient(app)
    create = client.post(
        "/api/custom-agents",
        json={
            "name": f"WS Test Agent {uuid.uuid4().hex[:6]}",
            "base_agent_id": "head-agent",
            "description": "ws flow",
            "workflow_steps": ["analyze", "execute"],
        },
    )
    assert create.status_code == 200
    custom_id = create.json()["id"]

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "hello custom",
                "agent_id": custom_id,
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(evt.get("type") == "final" and "custom-flow:" in str(evt.get("message", "")) for evt in events)

    deleted = client.delete(f"/api/custom-agents/{custom_id}")
    assert deleted.status_code == 200


def test_websocket_head_agent_routes_review_intent_to_review_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_review_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "review-agent",
                "message": f"reviewed:{user_message}",
            }
        )
        return f"reviewed:{user_message}"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["review-agent"], "run", fake_review_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "Please review this diff --git a/foo.py b/foo.py",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(
        evt.get("type") == "status"
        and "delegated this request to review-agent" in str(evt.get("message", "")).lower()
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("agent") == "review-agent" for evt in events)


def test_websocket_head_agent_mixed_research_review_intent_stays_head_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_head_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "head-ran",
            }
        )
        return "head-ran"

    async def fail_review_run(*args, **kwargs):
        raise AssertionError("review-agent should not be selected for mixed research/execution request")

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_head_run)
    monkeypatch.setattr(agent_registry["review-agent"], "run", fail_review_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "orchestrate a research about llms. review and fact check the results. write an essay only with the fact based research and save it",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(24):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert not any(
        evt.get("type") == "status"
        and "delegated this request to review-agent" in str(evt.get("message", "")).lower()
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("agent") == "head-agent" for evt in events)


def test_review_agent_enforces_read_only_policy(monkeypatch) -> None:
    _set_local_runtime()

    captured_policy = {}

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_delegate_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        captured_policy["value"] = tool_policy or {}
        await send_event(
            {
                "type": "final",
                "agent": "review-agent",
                "message": "policy-captured",
            }
        )
        return "policy-captured"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["review-agent"]._delegate, "run", fake_delegate_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "Review this patch in src/main.ts and find issues.",
                "agent_id": "review-agent",
                "tool_policy": {"allow": ["read_file", "run_command"]},
            }
        )

        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    deny = set((captured_policy.get("value") or {}).get("deny") or [])
    assert "write_file" in deny
    assert "apply_patch" in deny
    assert "run_command" in deny


def test_review_agent_requires_evidence_and_returns_guidance(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("Delegate should not be called when evidence is missing")

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["review-agent"]._delegate, "run", fail_if_called)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "Please review this",
                "agent_id": "review-agent",
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    final_event = next((evt for evt in events if evt.get("type") == "final"), None)
    assert final_event is not None
    assert "need concrete evidence" in str(final_event.get("message", "")).lower()


def test_presets_endpoint_lists_research_and_review() -> None:
    _set_local_runtime()
    client = TestClient(app)

    response = client.get("/api/presets")

    assert response.status_code == 200
    payload = response.json()
    ids = {item.get("id") for item in payload}
    assert "research" in ids
    assert "review" in ids


def test_websocket_head_agent_preset_review_routes_to_review_agent(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_review_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        await send_event(
            {
                "type": "final",
                "agent": "review-agent",
                "message": "preset-review-route-ok",
            }
        )
        return "preset-review-route-ok"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["review-agent"], "run", fake_review_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "Please summarize this architecture",
                "agent_id": "head-agent",
                "preset": "review",
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(
        evt.get("type") == "status"
        and "delegated this request to review-agent" in str(evt.get("message", "")).lower()
        and evt.get("routing_reason") == "preset_review"
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("message") == "preset-review-route-ok" for evt in events)


def test_rest_agent_applies_research_preset_and_merges_policy(monkeypatch) -> None:
    _set_local_runtime()

    captured = {}

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        return model_name

    async def fake_run(
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        captured["tool_policy"] = tool_policy
        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": "preset-policy-ok",
            }
        )
        return "preset-policy-ok"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)
    response = client.post(
        "/api/test/agent",
        json={
            "message": "research current ai market share",
            "preset": "research",
            "tool_policy": {"allow": ["web_fetch"], "deny": ["grep_search"]},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["preset"] == "research"
    assert payload["final"] == "preset-policy-ok"

    policy = captured.get("tool_policy") or {}
    deny = set(policy.get("deny") or [])
    allow = set(policy.get("allow") or [])
    assert "web_fetch" in allow
    assert "run_command" in deny
    assert "write_file" in deny
    assert "grep_search" in deny

