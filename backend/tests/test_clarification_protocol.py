from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient

from app.main import app, agent, agent_registry, runtime_manager
from app.runtime_manager import RuntimeState
from backend.tests.async_test_guards import receive_json_with_timeout
from backend.tests.mock_contract_guards import assert_agent_run_mock_signature_compatible


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


def test_clarification_protocol_round_trip_over_websocket(monkeypatch) -> None:
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
        _ = (session_id, request_id, model, tool_policy, prompt_mode, should_steer_interrupt)
        if user_message == "fix it":
            await send_event(
                {
                    "type": "clarification_needed",
                    "agent": "head-agent",
                    "message": "What specifically should I fix?",
                }
            )
            return "What specifically should I fix?"

        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"done:{user_message}",
            }
        )
        return f"done:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)
    monkeypatch.setattr(agent_registry["coder-agent"], "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))

        ws.send_json(
            {
                "type": "user_message",
                "content": "fix it",
                "agent_id": "head-agent",
            }
        )

        first_leg_events = []
        for _ in range(40):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            first_leg_events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "clarification_waiting_response":
                break

        ws.send_json(
            {
                "type": "clarification_response",
                "content": "the failing websocket test in ws_handler",
                "agent_id": "head-agent",
            }
        )

        second_leg_events = []
        for _ in range(60):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            second_leg_events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert any(evt.get("type") == "clarification_needed" for evt in first_leg_events)
    assert any(
        evt.get("type") == "lifecycle" and evt.get("stage") == "clarification_waiting_response"
        for evt in first_leg_events
    )
    assert any(
        evt.get("type") == "final"
        and "fix it\n\nClarification: the failing websocket test in ws_handler" in str(evt.get("message", ""))
        for evt in second_leg_events
    )
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed" for evt in second_leg_events)


def test_clarification_response_without_pending_is_rejected(monkeypatch) -> None:
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
        _ = (user_message, send_event, session_id, request_id, model, tool_policy, prompt_mode, should_steer_interrupt)
        return "noop"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))

        ws.send_json(
            {
                "type": "clarification_response",
                "content": "more details",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "clarification_response_rejected":
                break

    assert any(
        evt.get("type") == "status"
        and "no pending clarification" in str(evt.get("message", "")).lower()
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "clarification_response_rejected"
        and evt.get("details", {}).get("reason") == "no_pending_clarification"
        for evt in events
    )


def test_new_user_message_clears_stale_pending_clarification(monkeypatch) -> None:
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
        _ = (session_id, request_id, model, tool_policy, prompt_mode, should_steer_interrupt)
        if user_message == "fix it":
            await send_event(
                {
                    "type": "clarification_needed",
                    "agent": "head-agent",
                    "message": "What specifically should I fix?",
                }
            )
            return "What specifically should I fix?"

        await send_event(
            {
                "type": "final",
                "agent": "head-agent",
                "message": f"done:{user_message}",
            }
        )
        return f"done:{user_message}"

    assert_agent_run_mock_signature_compatible(fake_run)

    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent, "run", fake_run)
    monkeypatch.setattr(agent_registry["head-agent"], "run", fake_run)
    monkeypatch.setattr(agent_registry["coder-agent"], "run", fake_run)

    client = TestClient(app)

    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))

        ws.send_json({"type": "user_message", "content": "fix it", "agent_id": "head-agent"})
        for _ in range(40):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            if evt.get("type") == "lifecycle" and evt.get("stage") == "clarification_waiting_response":
                break

        ws.send_json({"type": "user_message", "content": "new task", "agent_id": "head-agent"})
        for _ in range(40):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

        ws.send_json({"type": "clarification_response", "content": "late clarification", "agent_id": "head-agent"})
        rejection_events = []
        for _ in range(20):
            evt = _unwrap_event(receive_json_with_timeout(ws))
            rejection_events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "clarification_response_rejected":
                break

    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "clarification_response_rejected"
        and evt.get("details", {}).get("reason") == "no_pending_clarification"
        for evt in rejection_events
    )
