from __future__ import annotations

import os

os.environ.setdefault("OLLAMA_BIN", "python")

from fastapi.testclient import TestClient
from tests.async_test_guards import receive_json_with_timeout

from app.main import agent_registry, app, runtime_manager
from app.orchestrator.step_executors import PlannerStepExecutor, SynthesizeStepExecutor
from app.runtime_manager import RuntimeState
from app.services.reflection_service import ReflectionVerdict


def _set_local_runtime() -> None:
    runtime_manager._state = RuntimeState(
        runtime="local",
        base_url="http://localhost:11434/v1",
        model="llama3.3:70b-instruct-q4_K_M",
    )


def _unwrap_event(envelope: dict) -> dict:
    assert "event" in envelope
    return envelope["event"]


def test_reflection_loop_retries_synthesis_when_score_is_low(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        _ = (send_event, session_id)
        return model_name

    def fake_configure_runtime(base_url: str, model: str) -> None:
        _ = (base_url, model)
        return

    delegate = agent_registry["head-agent"]._delegate
    synth_calls: list[object] = []

    class _FakeReflectionService:
        def __init__(self) -> None:
            self.calls = 0

        async def reflect(self, *, user_message, plan_text, tool_results, final_answer, model=None, task_type=None):
            _ = (user_message, plan_text, tool_results, final_answer, model, task_type)
            self.calls += 1
            if self.calls == 1:
                return ReflectionVerdict(
                    score=0.4,
                    goal_alignment=0.5,
                    completeness=0.4,
                    factual_grounding=0.3,
                    issues=["Missing direct answer to requested command."],
                    suggested_fix="Provide explicit command result summary.",
                    should_retry=True,
                )
            return ReflectionVerdict(
                score=0.95,
                goal_alignment=0.95,
                completeness=0.95,
                factual_grounding=0.95,
                issues=[],
                suggested_fix=None,
                should_retry=False,
            )

    async def fake_plan_execute(payload, model=None):
        _ = (payload, model)
        return "review tool results and summarize"

    async def fake_synthesize_execute(payload, send_event, session_id, request_id, model=None):
        _ = (send_event, session_id, request_id, model)
        synth_calls.append(payload)
        if len(synth_calls) == 1:
            return "draft answer"
        return "refined final answer"

    async def fake_tool_execute(
        payload,
        session_id,
        request_id,
        send_event,
        model,
        allowed_tools,
        should_steer_interrupt=None,
    ):
        _ = (payload, session_id, request_id, send_event, model, allowed_tools, should_steer_interrupt)
        return "[read_file] [OK] command output: hello"

    reflection_service = _FakeReflectionService()
    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "configure_runtime", fake_configure_runtime)
    monkeypatch.setattr(delegate, "plan_step_executor", PlannerStepExecutor(execute_fn=fake_plan_execute))
    monkeypatch.setattr(delegate, "tool_step_executor", delegate.tool_step_executor.__class__(execute_fn=fake_tool_execute))
    monkeypatch.setattr(delegate, "synthesize_step_executor", SynthesizeStepExecutor(execute_fn=fake_synthesize_execute))
    monkeypatch.setattr(
        delegate.synthesizer_agent,
        "constraints",
        delegate.synthesizer_agent.constraints.model_copy(update={"reflection_passes": 2}),
    )
    monkeypatch.setattr(delegate, "_reflection_service", reflection_service)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "summarize the command output",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(80):
            envelope = receive_json_with_timeout(ws, timeout_seconds=0.75, fail_on_timeout=False)
            if envelope is None:
                break
            evt = _unwrap_event(envelope)
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert reflection_service.calls == 2
    assert len(synth_calls) == 2
    assert "[REFLECTION FEEDBACK]" in str(getattr(synth_calls[1], "tool_results", ""))
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "reflection_completed"
        and evt.get("details", {}).get("pass") == 1
        and evt.get("details", {}).get("should_retry") is True
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "reflection_completed"
        and evt.get("details", {}).get("pass") == 2
        and evt.get("details", {}).get("should_retry") is False
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("message") == "refined final answer" for evt in events)


def test_reflection_loop_hard_factual_fail_forces_retry(monkeypatch) -> None:
    _set_local_runtime()

    async def fake_ensure_model_ready(send_event, session_id, model_name):
        _ = (send_event, session_id)
        return model_name

    def fake_configure_runtime(base_url: str, model: str) -> None:
        _ = (base_url, model)
        return

    delegate = agent_registry["head-agent"]._delegate
    synth_calls: list[object] = []

    class _FakeReflectionService:
        def __init__(self) -> None:
            self.calls = 0

        async def reflect(self, *, user_message, plan_text, tool_results, final_answer, model=None, task_type=None):
            _ = (user_message, plan_text, tool_results, final_answer, model, task_type)
            self.calls += 1
            if self.calls == 1:
                return ReflectionVerdict(
                    score=(0.9 + 0.8 + 0.35) / 3,
                    goal_alignment=0.9,
                    completeness=0.8,
                    factual_grounding=0.35,
                    issues=["PIDs mentioned are not present in netstat output"],
                    suggested_fix="Use only PIDs from tool output.",
                    should_retry=True,
                    hard_factual_fail=True,
                )
            return ReflectionVerdict(
                score=0.95,
                goal_alignment=0.95,
                completeness=0.95,
                factual_grounding=0.95,
                issues=[],
                suggested_fix=None,
                should_retry=False,
                hard_factual_fail=False,
            )

    async def fake_plan_execute(payload, model=None):
        _ = (payload, model)
        return "review tool results and summarize"

    async def fake_synthesize_execute(payload, send_event, session_id, request_id, model=None):
        _ = (send_event, session_id, request_id, model)
        synth_calls.append(payload)
        if len(synth_calls) == 1:
            return "draft answer"
        return "refined final answer"

    async def fake_tool_execute(
        payload,
        session_id,
        request_id,
        send_event,
        model,
        allowed_tools,
        should_steer_interrupt=None,
    ):
        _ = (payload, session_id, request_id, send_event, model, allowed_tools, should_steer_interrupt)
        return "[read_file] [OK] command output: hello"

    reflection_service = _FakeReflectionService()
    monkeypatch.setattr(runtime_manager, "ensure_model_ready", fake_ensure_model_ready)
    monkeypatch.setattr(agent_registry["head-agent"], "configure_runtime", fake_configure_runtime)
    monkeypatch.setattr(delegate, "plan_step_executor", PlannerStepExecutor(execute_fn=fake_plan_execute))
    monkeypatch.setattr(delegate, "tool_step_executor", delegate.tool_step_executor.__class__(execute_fn=fake_tool_execute))
    monkeypatch.setattr(delegate, "synthesize_step_executor", SynthesizeStepExecutor(execute_fn=fake_synthesize_execute))
    monkeypatch.setattr(
        delegate.synthesizer_agent,
        "constraints",
        delegate.synthesizer_agent.constraints.model_copy(update={"reflection_passes": 2}),
    )
    monkeypatch.setattr(delegate, "_reflection_service", reflection_service)

    client = TestClient(app)
    with client.websocket_connect("/ws/agent") as ws:
        _ = _unwrap_event(receive_json_with_timeout(ws))
        ws.send_json(
            {
                "type": "user_message",
                "content": "summarize the command output",
                "agent_id": "head-agent",
            }
        )

        events = []
        for _ in range(80):
            envelope = receive_json_with_timeout(ws, timeout_seconds=0.75, fail_on_timeout=False)
            if envelope is None:
                break
            evt = _unwrap_event(envelope)
            events.append(evt)
            if evt.get("type") == "lifecycle" and evt.get("stage") == "request_completed":
                break

    assert reflection_service.calls == 2
    assert len(synth_calls) == 2
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "reflection_completed"
        and evt.get("details", {}).get("pass") == 1
        and evt.get("details", {}).get("should_retry") is True
        and evt.get("details", {}).get("hard_factual_fail") is True
        and evt.get("details", {}).get("factual_grounding") == 0.35
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "reflection_completed"
        and evt.get("details", {}).get("pass") == 2
        and evt.get("details", {}).get("should_retry") is False
        and evt.get("details", {}).get("hard_factual_fail") is False
        for evt in events
    )
    assert any(evt.get("type") == "final" and evt.get("message") == "refined final answer" for evt in events)
