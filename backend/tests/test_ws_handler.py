from __future__ import annotations

import asyncio
import os

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient
from tests.async_test_guards import receive_json_with_timeout
from tests.mock_contract_guards import assert_agent_run_mock_signature_compatible

from app.main import agent, agent_registry, app, runtime_manager, subrun_lane
from app.transport.runtime_manager import RuntimeState


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


def test_ws_handler_routes_code_requests_to_coder_agent(monkeypatch) -> None:
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
        await send_event({"type": "final", "agent": "head-agent", "message": "head-should-not-handle"})
        return "head-should-not-handle"

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
        await send_event({"type": "final", "agent": "coder-agent", "message": f"coder:{user_message}"})
        return f"coder:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_head_run)
    assert_agent_run_mock_signature_compatible(fake_coder_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_head_run)
    monkeypatch.setattr(agent_registry["coder-agent"], "run", fake_coder_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "user_message", "content": "write a python script", "agent_id": "head-agent"})

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


def test_ws_handler_subrun_spawn_emits_accepted_with_default_mode(monkeypatch) -> None:
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

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "subrun_spawn", "content": "background"})

        accepted_event = None
        for _ in range(24):
            evt = _unwrap_event(receive_json_with_timeout(ws))
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
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "subrun_spawn", "content": "blocked child", "agent_id": "coder-agent"})

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
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
        first = _unwrap_event(receive_json_with_timeout(ws))
        assert first.get("type") == "status"

    with client.websocket_connect("/ws/agent") as ws:
        second = _unwrap_event(receive_json_with_timeout(ws))
        assert second.get("type") == "status"


def test_ws_handler_unsupported_type_emits_rejection_lifecycle() -> None:
    _set_local_runtime()
    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "unknown_type", "content": "hello", "agent_id": "head-agent"})

        events = []
        for _ in range(12):
            evt = _unwrap_event(receive_json_with_timeout(ws))
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


def test_ws_handler_user_messages_are_queued_and_processed_in_order(monkeypatch) -> None:
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
        if user_message == "first":
            await asyncio.sleep(0.05)
        await send_event({"type": "final", "agent": "head-agent", "message": f"done:{user_message}"})
        return f"done:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "user_message", "content": "first", "agent_id": "head-agent"})
        ws.send_json({"type": "user_message", "content": "second", "agent_id": "head-agent"})

        finals = []
        for _ in range(60):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            if evt.get("type") == "final":
                finals.append(evt.get("message"))
                if len(finals) == 2:
                    break

    assert finals == ["done:first", "done:second"]


def test_ws_handler_follow_up_is_deferred_behind_wait(monkeypatch) -> None:
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
        if user_message == "first-wait":
            await asyncio.sleep(0.05)
        await send_event({"type": "final", "agent": "head-agent", "message": f"done:{user_message}"})
        return f"done:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "user_message", "content": "first-wait", "agent_id": "head-agent", "queue_mode": "wait"})
        ws.send_json({"type": "user_message", "content": "second-follow", "agent_id": "head-agent", "queue_mode": "follow_up"})
        ws.send_json({"type": "user_message", "content": "third-wait", "agent_id": "head-agent", "queue_mode": "wait"})

        finals = []
        for _ in range(90):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            if evt.get("type") == "final":
                finals.append(evt.get("message"))
                if len(finals) == 3:
                    break

    assert finals == ["done:first-wait", "done:third-wait", "done:second-follow"]


def test_ws_handler_steer_interrupts_running_request(monkeypatch) -> None:
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
                "stage": "tool_completed",
                "request_id": request_id,
                "session_id": session_id,
                "details": {"tool": "read_file"},
            }
        )
        if callable(should_steer_interrupt) and should_steer_interrupt():
            await send_event(
                {
                    "type": "lifecycle",
                    "stage": "steer_detected",
                    "request_id": request_id,
                    "session_id": session_id,
                    "details": {"checkpoint_stage": "tool_completed"},
                }
            )
            await send_event(
                {
                    "type": "lifecycle",
                    "stage": "steer_applied",
                    "request_id": request_id,
                    "session_id": session_id,
                    "details": {"checkpoint_stage": "tool_completed"},
                }
            )
            return ""
        await send_event({"type": "final", "agent": "head-agent", "message": f"done:{user_message}"})
        return f"done:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json({"type": "user_message", "content": "first", "agent_id": "head-agent", "queue_mode": "steer"})
        ws.send_json({"type": "user_message", "content": "second", "agent_id": "head-agent", "queue_mode": "steer"})

        events = []
        for _ in range(80):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            finals = [item for item in events if item.get("type") == "final"]
            if len(finals) >= 1 and any(item.get("stage") == "steer_applied" for item in events if item.get("type") == "lifecycle"):
                break

    steer_applied = [
        evt for evt in events if evt.get("type") == "lifecycle" and evt.get("stage") == "steer_applied"
    ]
    final_messages = [evt.get("message") for evt in events if evt.get("type") == "final"]

    assert steer_applied
    assert "done:second" in final_messages


def test_ws_handler_applies_directive_overrides_and_strips_prefix(monkeypatch) -> None:
    _set_local_runtime()

    observed: dict[str, object] = {}

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        observed["ensure_model"] = model_name
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
        observed["user_message"] = user_message
        observed["model"] = model
        await send_event({"type": "final", "agent": "head-agent", "message": f"done:{user_message}"})
        return f"done:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "agent_id": "head-agent",
                "content": "/queue steer\n/model qwen3-coder:480b-cloud\n/verbose on\nstatus update",
            }
        )

        events = []
        for _ in range(50):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert observed.get("ensure_model") == "qwen3-coder:480b-cloud"
    assert observed.get("model") == "qwen3-coder:480b-cloud"
    assert observed.get("user_message") == "status update"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "request_received"
        and evt.get("details", {}).get("queue_mode") == "steer"
        and evt.get("details", {}).get("reasoning_visibility") == "summary"
        for evt in events
    )


def test_ws_handler_subrun_spawn_uses_directive_clean_content_and_model_override(monkeypatch) -> None:
    _set_local_runtime()

    observed: dict[str, object] = {}

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        observed["ensure_model"] = model_name
        return model_name

    async def fake_spawn(
        parent_request_id,
        parent_session_id,
        user_message,
        runtime,
        model,
        timeout_seconds,
        tool_policy,
        send_event,
        agent_id,
        mode,
        preset,
        orchestrator_agent_ids,
        orchestrator_api,
    ):
        observed["user_message"] = user_message
        observed["model"] = model
        observed["agent_id"] = agent_id
        observed["mode"] = mode
        return "subrun-123"

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(subrun_lane, "spawn", fake_spawn)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "subrun_spawn",
                "agent_id": "head-agent",
                "content": "/model qwen3-coder:480b-cloud\nbackground task",
            }
        )

        events = []
        for _ in range(30):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert observed.get("ensure_model") == "qwen3-coder:480b-cloud"
    assert observed.get("model") == "qwen3-coder:480b-cloud"
    assert observed.get("user_message") == "background task"
    assert observed.get("agent_id") == "head-agent"
    assert observed.get("mode") == "run"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "request_received"
        and evt.get("details", {}).get("chars") == len("background task")
        and evt.get("details", {}).get("directives_applied") == ["/model"]
        for evt in events
    )
