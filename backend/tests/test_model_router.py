from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract
from app.errors import LlmClientError
from app.model_routing.router import ModelRouter
from app.orchestrator.pipeline_runner import PipelineRunner
from app.state import StateStore


class _FakeInput(BaseModel):
    text: str = ""


class _FakeOutput(BaseModel):
    text: str = ""


class _FakeAgent(AgentContract):
    role = "fake"
    input_schema = _FakeInput
    output_schema = _FakeOutput
    constraints = AgentConstraints(
        max_context=2048,
        temperature=0.3,
        reasoning_depth=1,
        reflection_passes=0,
        combine_steps=False,
    )

    def __init__(self, *, failure_messages: list[str] | None = None):
        self.calls: list[str] = []
        self.user_messages: list[str] = []
        self.failure_messages = list(failure_messages or ["model not found"])

    @property
    def name(self) -> str:
        return "fake-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        return

    async def run(
        self,
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        active_model = model or ""
        self.calls.append(active_model)
        self.user_messages.append(str(user_message or ""))
        failure_index = len(self.calls) - 1
        if failure_index < len(self.failure_messages):
            raise LlmClientError(self.failure_messages[failure_index])
        return "ok"


class _FakeRouteProfile:
    def __init__(self, *, health_score: float, expected_latency_ms: int, cost_score: float = 0.5):
        self.max_context = 120000
        self.reasoning_depth = 1
        self.health_score = health_score
        self.expected_latency_ms = expected_latency_ms
        self.cost_score = cost_score


class _FakeRouteDecision:
    def __init__(
        self,
        *,
        primary_model: str,
        fallback_models: list[str],
        health_score: float,
        expected_latency_ms: int,
        cost_score: float = 0.5,
    ):
        self.primary_model = primary_model
        self.fallback_models = fallback_models
        self.profile = _FakeRouteProfile(
            health_score=health_score,
            expected_latency_ms=expected_latency_ms,
            cost_score=cost_score,
        )
        self.scores = {primary_model: 1.0, **dict.fromkeys(fallback_models, 0.8)}


def test_model_router_prefers_requested_then_runtime_defaults() -> None:
    router = ModelRouter()

    decision = router.route(runtime="local", requested_model="custom-model")

    assert decision.primary_model == "custom-model"
    assert len(decision.fallback_models) >= 1
    assert "custom-model" in decision.scores


def test_model_router_prefers_runtime_optimized_model_when_not_requested() -> None:
    router = ModelRouter()

    local_decision = router.route(runtime="local", requested_model=None)
    api_decision = router.route(runtime="api", requested_model=None)

    assert local_decision.primary_model != ""
    assert api_decision.primary_model != ""


def test_model_router_reasoning_level_changes_scoring_bias() -> None:
    router = ModelRouter()

    high_reasoning = router.route(runtime="api", requested_model=None, reasoning_level="high")
    low_reasoning = router.route(runtime="api", requested_model=None, reasoning_level="low")

    assert high_reasoning.primary_model != ""
    assert low_reasoning.primary_model != ""
    assert high_reasoning.profile.reasoning_depth >= 0
    assert low_reasoning.profile.reasoning_depth >= 0


def test_pipeline_runner_retries_on_model_not_found(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent()
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-1"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    async def send_event(_: dict):
        return

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2


def test_pipeline_runner_emits_inference_budget_degraded_when_primary_exceeds_budget(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=[])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-budget"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="api",
        model="qwen3-coder:480b-cloud",
    )

    monkeypatch.setattr(settings, "adaptive_inference_enabled", True, raising=False)
    monkeypatch.setattr(settings, "adaptive_inference_cost_budget_max", 0.2, raising=False)
    monkeypatch.setattr(settings, "adaptive_inference_latency_budget_ms", 700, raising=False)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="analyze and respond",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="api",
            model="qwen3-coder:480b-cloud",
            reasoning_level="low",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle" and evt.get("stage") == "inference_budget_degraded"
        for evt in events
    )


def test_pipeline_runner_retries_on_timeout_reason(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["request timed out"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-timeout"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_fallback_classified"
        and evt.get("details", {}).get("reason") == "timeout"
        for evt in events
    )


def test_pipeline_runner_does_not_retry_on_unknown_reason(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["schema mismatch in request payload"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-unknown"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    try:
        asyncio.run(
            runner.run(
                user_message="hello",
                send_event=send_event,
                session_id="sess-1",
                request_id=request_id,
                runtime="local",
                model="custom-model",
            )
        )
        raise AssertionError("expected LlmClientError")
    except LlmClientError:
        pass

    assert len(agent.calls) == 1
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_fallback_not_retryable"
        and evt.get("details", {}).get("reason") == "unknown"
        for evt in events
    )


def test_pipeline_runner_enforces_retry_attempt_limit(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["request timed out", "request timed out"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-limit"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_max_attempts", 1)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    try:
        asyncio.run(
            runner.run(
                user_message="hello",
                send_event=send_event,
                session_id="sess-1",
                request_id=request_id,
                runtime="local",
                model="custom-model",
            )
        )
        raise AssertionError("expected LlmClientError")
    except LlmClientError:
        pass

    assert len(agent.calls) == 1
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_fallback_retry_limit_reached"
        and evt.get("details", {}).get("max_attempts") == 1
        for evt in events
    )


def test_pipeline_runner_classifies_context_overflow_as_non_retryable(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["Context overflow: prompt too large for the model."])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    try:
        asyncio.run(
            runner.run(
                user_message="hello",
                send_event=send_event,
                session_id="sess-1",
                request_id=request_id,
                runtime="local",
                model="custom-model",
            )
        )
        raise AssertionError("expected LlmClientError")
    except LlmClientError:
        pass

    assert len(agent.calls) == 1
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_fallback_classified"
        and evt.get("details", {}).get("reason") == "context_overflow"
        and evt.get("details", {}).get("retryable") is False
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "fail_fast_context_overflow"
        for evt in events
    )


def test_pipeline_runner_classifies_compaction_failure_as_non_retryable(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["compaction failed: timed out"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-compaction"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    try:
        asyncio.run(
            runner.run(
                user_message="hello",
                send_event=send_event,
                session_id="sess-1",
                request_id=request_id,
                runtime="local",
                model="custom-model",
            )
        )
        raise AssertionError("expected LlmClientError")
    except LlmClientError:
        pass

    assert len(agent.calls) == 1
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_fallback_classified"
        and evt.get("details", {}).get("reason") == "compaction_failure"
        and evt.get("details", {}).get("retryable") is False
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "fail_fast_compaction_failure"
        for evt in events
    )


def test_pipeline_runner_guarded_context_overflow_retry_with_fallback(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-overflow-guarded"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_max_attempts", 1)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
        and evt.get("details", {}).get("overflow_retry_applied") is True
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_action"
        and evt.get("details", {}).get("action") == "retry_fallback"
        and evt.get("details", {}).get("overflow_retry_applied") is True
        for evt in events
    )


def test_pipeline_runner_guarded_compaction_failure_recovery_with_fallback(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["compaction failed: timeout"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-compaction-guarded"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_compaction_failure_recovery_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_compaction_failure_recovery_max_attempts", 1)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_compaction_failure_recovery"
        and evt.get("details", {}).get("compaction_recovery_applied") is True
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_action"
        and evt.get("details", {}).get("action") == "retry_fallback"
        and evt.get("details", {}).get("compaction_recovery_applied") is True
        for evt in events
    )


def test_pipeline_runner_classifies_truncation_required_as_non_retryable(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-truncation"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    try:
        asyncio.run(
            runner.run(
                user_message="hello",
                send_event=send_event,
                session_id="sess-1",
                request_id=request_id,
                runtime="local",
                model="custom-model",
            )
        )
        raise AssertionError("expected LlmClientError")
    except LlmClientError:
        pass

    assert len(agent.calls) == 1
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_fallback_classified"
        and evt.get("details", {}).get("reason") == "truncation_required"
        and evt.get("details", {}).get("retryable") is False
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "fail_fast_truncation_required"
        for evt in events
    )


def test_pipeline_runner_guarded_truncation_recovery_with_fallback(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-truncation-guarded"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_max_attempts", 1)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_truncation_recovery"
        and evt.get("details", {}).get("truncation_recovery_applied") is True
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_action"
        and evt.get("details", {}).get("action") == "retry_fallback"
        and evt.get("details", {}).get("truncation_recovery_applied") is True
        for evt in events
    )


def test_pipeline_runner_guarded_prompt_compaction_recovery_with_fallback(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-prompt-compaction"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_ratio", 0.5)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_min_chars", 80)

    long_message = "x" * 600
    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message=long_message,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
    assert len(agent.user_messages) == 2
    assert len(agent.user_messages[1]) < len(agent.user_messages[0])
    assert "context compacted by pipeline runner" in agent.user_messages[1]
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_prompt_compaction_recovery"
        and evt.get("details", {}).get("prompt_compaction_applied") is True
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_action"
        and evt.get("details", {}).get("prompt_compaction_applied") is True
        and evt.get("details", {}).get("action") == "retry_fallback"
        for evt in events
    )


def test_pipeline_runner_guarded_payload_truncation_recovery_with_fallback(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-payload-truncation"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_target_chars", 300)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_min_chars", 100)

    long_message = "y" * 1000
    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message=long_message,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
    assert len(agent.user_messages) == 2
    assert len(agent.user_messages[1]) < len(agent.user_messages[0])
    assert "payload truncated by pipeline runner" in agent.user_messages[1]
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_payload_truncation_recovery"
        and evt.get("details", {}).get("payload_truncation_applied") is True
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_action"
        and evt.get("details", {}).get("payload_truncation_applied") is True
        and evt.get("details", {}).get("action") == "retry_fallback"
        for evt in events
    )


def test_pipeline_runner_prioritizes_prompt_compaction_over_overflow_fallback_retry(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-priority-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_ratio", 0.5)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_min_chars", 80)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_max_attempts", 1)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="z" * 800,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_prompt_compaction_recovery"
        and evt.get("details", {}).get("prompt_compaction_applied") is True
        and evt.get("details", {}).get("overflow_retry_applied") is False
        and evt.get("details", {}).get("recovery_strategy") == "context_overflow:prompt_compaction"
        for evt in events
    )


def test_pipeline_runner_prioritizes_payload_truncation_over_truncation_retry(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-priority-truncation"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_target_chars", 300)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_min_chars", 100)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_max_attempts", 1)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="t" * 1000,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_payload_truncation_recovery"
        and evt.get("details", {}).get("payload_truncation_applied") is True
        and evt.get("details", {}).get("truncation_recovery_applied") is False
        and evt.get("details", {}).get("recovery_strategy") == "truncation_required:payload_truncation"
        for evt in events
    )


def test_pipeline_runner_api_prefers_overflow_fallback_retry_over_prompt_compaction(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-api-priority-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="api",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_max_attempts", 1)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_api",
        ["overflow_fallback_retry", "prompt_compaction"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="k" * 900,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="api",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.user_messages) == 2
    assert agent.user_messages[1] == agent.user_messages[0]
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
        and evt.get("details", {}).get("prompt_compaction_applied") is False
        and evt.get("details", {}).get("overflow_retry_applied") is True
        and evt.get("details", {}).get("recovery_strategy") == "context_overflow:fallback_retry"
        for evt in events
    )


def test_pipeline_runner_api_prefers_truncation_fallback_retry_over_payload_truncation(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-api-priority-truncation"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="api",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_max_attempts", 1)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_truncation_priority_api",
        ["truncation_fallback_retry", "payload_truncation"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="m" * 1000,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="api",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.user_messages) == 2
    assert agent.user_messages[1] == agent.user_messages[0]
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_truncation_recovery"
        and evt.get("details", {}).get("payload_truncation_applied") is False
        and evt.get("details", {}).get("truncation_recovery_applied") is True
        and evt.get("details", {}).get("recovery_strategy") == "truncation_required:fallback_retry"
        for evt in events
    )


def test_pipeline_runner_flips_context_overflow_priority_on_reason_streak(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(
        failure_messages=[
            "context overflow: prompt too long",
            "context overflow: prompt too long",
        ]
    )
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-overflow-flip"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 5)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_max_attempts", 5)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_threshold", 2)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="q" * 1200,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    branch_events = [
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "model_recovery_branch_selected"
    ]
    assert len(branch_events) >= 2
    assert branch_events[0].get("details", {}).get("branch") == "guarded_prompt_compaction_recovery"
    assert branch_events[0].get("details", {}).get("recovery_priority_overridden") is False
    assert branch_events[1].get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
    assert branch_events[1].get("details", {}).get("recovery_priority_overridden") is True
    assert branch_events[1].get("details", {}).get("reason_streak") == 2


def test_pipeline_runner_flips_truncation_priority_on_reason_streak(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(
        failure_messages=[
            "response truncated due to max tokens",
            "response truncated due to max tokens",
        ]
    )
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-truncation-flip"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_max_attempts", 5)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_max_attempts", 5)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_threshold", 2)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_truncation_priority_local",
        ["payload_truncation", "truncation_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="r" * 1500,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    branch_events = [
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "model_recovery_branch_selected"
    ]
    assert len(branch_events) >= 2
    assert branch_events[0].get("details", {}).get("branch") == "guarded_payload_truncation_recovery"
    assert branch_events[0].get("details", {}).get("recovery_priority_overridden") is False
    assert branch_events[1].get("details", {}).get("branch") == "guarded_truncation_recovery"
    assert branch_events[1].get("details", {}).get("recovery_priority_overridden") is True
    assert branch_events[1].get("details", {}).get("reason_streak") == 2


def test_pipeline_runner_signal_low_health_prefers_fallback_for_context_overflow(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    monkeypatch.setattr(
        runner.model_router,
        "route",
        lambda runtime, requested_model=None: _FakeRouteDecision(
            primary_model=requested_model or "custom-model",
            fallback_models=["fallback-model"],
            health_score=0.2,
            expected_latency_ms=300,
        ),
    )

    request_id = "req-signal-low-health-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="api",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_signal_low_health_threshold", 0.6)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_api",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="w" * 900,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="api",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
        and evt.get("details", {}).get("signal_priority_reason") == "low_health_prefer_fallback"
        for evt in events
    )


def test_pipeline_runner_signal_high_latency_prefers_transform_for_truncation(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    monkeypatch.setattr(
        runner.model_router,
        "route",
        lambda runtime, requested_model=None: _FakeRouteDecision(
            primary_model=requested_model or "custom-model",
            fallback_models=["fallback-model"],
            health_score=0.95,
            expected_latency_ms=6000,
        ),
    )

    request_id = "req-signal-high-latency-truncation"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="api",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_signal_high_latency_ms", 2000)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_target_chars", 300)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_min_chars", 120)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_enabled", True)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_truncation_priority_api",
        ["truncation_fallback_retry", "payload_truncation"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="n" * 1200,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="api",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_payload_truncation_recovery"
        and evt.get("details", {}).get("signal_priority_reason") == "high_latency_prefer_transform"
        for evt in events
    )


def test_pipeline_runner_signal_high_cost_prefers_transform_for_context_overflow(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    monkeypatch.setattr(
        runner.model_router,
        "route",
        lambda runtime, requested_model=None: _FakeRouteDecision(
            primary_model=requested_model or "custom-model",
            fallback_models=["fallback-model"],
            health_score=0.9,
            expected_latency_ms=500,
            cost_score=0.95,
        ),
    )

    request_id = "req-signal-high-cost-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="api",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_signal_high_cost_threshold", 0.8)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_api",
        ["overflow_fallback_retry", "prompt_compaction"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="c" * 900,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="api",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_prompt_compaction_recovery"
        and evt.get("details", {}).get("signal_priority_reason") == "high_cost_prefer_transform"
        for evt in events
    )


def test_pipeline_runner_strategy_feedback_demotes_last_failed_strategy(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(
        failure_messages=[
            "context overflow: prompt too long",
            "context overflow: prompt too long",
        ]
    )
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-strategy-feedback-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 5)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_max_attempts", 5)
    monkeypatch.setattr(settings, "pipeline_runner_strategy_feedback_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="s" * 1200,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    branch_events = [
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "model_recovery_branch_selected"
    ]
    assert len(branch_events) >= 2
    assert branch_events[0].get("details", {}).get("branch") == "guarded_prompt_compaction_recovery"
    assert branch_events[1].get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
    assert branch_events[1].get("details", {}).get("strategy_feedback_applied") is True
    assert branch_events[1].get("details", {}).get("strategy_feedback_reason") == "demote:prompt_compaction"


def test_pipeline_runner_persistent_metrics_prefer_fallback_for_context_overflow(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = state_dir / "pipeline_recovery_metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "version": 1,
                "metrics": {
                    "context_overflow": {
                        "custom-model": {
                            "prompt_compaction": {"success": 1, "failure": 5},
                            "overflow_fallback_retry": {"success": 5, "failure": 1},
                        }
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    store = StateStore(persist_dir=str(state_dir))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-persistent-priority-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_min_samples", 3)
    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_strategy_feedback_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="p" * 1200,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
        and evt.get("details", {}).get("persistent_priority_applied") is True
        and evt.get("details", {}).get("persistent_priority_reason") == "metrics_prefer:overflow_fallback_retry"
        for evt in events
    )


def test_pipeline_runner_persistent_metrics_prefer_transform_for_truncation(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = state_dir / "pipeline_recovery_metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "version": 1,
                "metrics": {
                    "truncation_required": {
                        "custom-model": {
                            "payload_truncation": {"success": 6, "failure": 1},
                            "truncation_fallback_retry": {"success": 1, "failure": 6},
                        }
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    store = StateStore(persist_dir=str(state_dir))
    agent = _FakeAgent(failure_messages=["response truncated due to max tokens"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-persistent-priority-truncation"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_min_samples", 3)
    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_strategy_feedback_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_target_chars", 300)
    monkeypatch.setattr(settings, "pipeline_runner_payload_truncation_min_chars", 100)
    monkeypatch.setattr(settings, "pipeline_runner_truncation_recovery_enabled", True)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_truncation_priority_local",
        ["truncation_fallback_retry", "payload_truncation"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="u" * 1200,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_payload_truncation_recovery"
        and evt.get("details", {}).get("persistent_priority_applied") is True
        and evt.get("details", {}).get("persistent_priority_reason") == "metrics_prefer:payload_truncation"
        for evt in events
    )


def test_pipeline_runner_persistent_metrics_decay_prefers_recent_signal(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = state_dir / "pipeline_recovery_metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "version": 1,
                "metrics": {
                    "context_overflow": {
                        "custom-model": {
                            "prompt_compaction": {
                                "success": 6,
                                "failure": 2,
                                "events": [
                                    {"outcome": "success", "ts": 100.0},
                                    {"outcome": "success", "ts": 101.0},
                                    {"outcome": "success", "ts": 102.0},
                                    {"outcome": "success", "ts": 103.0},
                                    {"outcome": "success", "ts": 104.0},
                                    {"outcome": "success", "ts": 105.0},
                                    {"outcome": "failure", "ts": 990.0},
                                    {"outcome": "failure", "ts": 991.0},
                                ],
                            },
                            "overflow_fallback_retry": {
                                "success": 3,
                                "failure": 1,
                                "events": [
                                    {"outcome": "success", "ts": 995.0},
                                    {"outcome": "success", "ts": 996.0},
                                    {"outcome": "success", "ts": 997.0},
                                    {"outcome": "failure", "ts": 998.0},
                                ],
                            },
                        }
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("app.orchestrator.pipeline_runner.time.time", lambda: 1000.0)

    store = StateStore(persist_dir=str(state_dir))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-persistent-decay-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_min_samples", 3)
    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_strategy_feedback_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_decay_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_decay_half_life_seconds", 100)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_window_size", 50)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_window_max_age_seconds", 5000)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="p" * 1400,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
        and evt.get("details", {}).get("persistent_priority_applied") is True
        and evt.get("details", {}).get("persistent_priority_reason") == "metrics_prefer:overflow_fallback_retry"
        for evt in events
    )


def test_pipeline_runner_persistent_metrics_window_prefers_recent_trend(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = state_dir / "pipeline_recovery_metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "version": 1,
                "metrics": {
                    "context_overflow": {
                        "custom-model": {
                            "prompt_compaction": {
                                "success": 4,
                                "failure": 1,
                                "events": [
                                    {"outcome": "success", "ts": 901.0},
                                    {"outcome": "success", "ts": 902.0},
                                    {"outcome": "success", "ts": 903.0},
                                    {"outcome": "success", "ts": 904.0},
                                    {"outcome": "failure", "ts": 905.0},
                                ],
                            },
                            "overflow_fallback_retry": {
                                "success": 3,
                                "failure": 2,
                                "events": [
                                    {"outcome": "failure", "ts": 901.0},
                                    {"outcome": "failure", "ts": 902.0},
                                    {"outcome": "success", "ts": 903.0},
                                    {"outcome": "success", "ts": 904.0},
                                    {"outcome": "success", "ts": 905.0},
                                ],
                            },
                        }
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("app.orchestrator.pipeline_runner.time.time", lambda: 1000.0)

    store = StateStore(persist_dir=str(state_dir))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-persistent-window-overflow"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_min_samples", 3)
    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_strategy_feedback_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_decay_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_window_size", 3)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_window_max_age_seconds", 5000)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="p" * 1400,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "model_recovery_branch_selected"
        and evt.get("details", {}).get("branch") == "guarded_context_overflow_fallback_retry"
        and evt.get("details", {}).get("persistent_priority_applied") is True
        and evt.get("details", {}).get("persistent_priority_reason") == "metrics_prefer:overflow_fallback_retry"
        for evt in events
    )

    payload = json.loads(metrics_file.read_text(encoding="utf-8"))
    prompt_events = payload["metrics"]["context_overflow"]["custom-model"]["prompt_compaction"]["events"]
    fallback_events = payload["metrics"]["context_overflow"]["custom-model"]["overflow_fallback_retry"]["events"]
    assert len(prompt_events) == 3
    assert len(fallback_events) == 3


def test_pipeline_runner_emits_recovery_summary_on_success(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["context overflow: prompt too long"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-recovery-summary-success"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_recovery_priority_flip_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_strategy_feedback_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_enabled", True)
    monkeypatch.setattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 1)
    monkeypatch.setattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", False)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
    )

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="p" * 1600,
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    summary = next(
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "model_recovery_summary"
    )
    details = summary.get("details", {})
    assert details.get("final_outcome") == "success"
    assert details.get("failures_total") == 1
    assert details.get("reason_counts", {}).get("context_overflow") == 1
    assert details.get("strategy_counts", {}).get("prompt_compaction") == 1


def test_pipeline_runner_emits_recovery_summary_on_fail_fast(tmp_path, monkeypatch) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent(failure_messages=["compaction failed due to timeout"])
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-recovery-summary-failure"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    monkeypatch.setattr(settings, "pipeline_runner_compaction_failure_recovery_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_signal_priority_enabled", False)
    monkeypatch.setattr(settings, "pipeline_runner_persistent_priority_enabled", False)

    events: list[dict] = []

    async def send_event(payload: dict):
        events.append(payload)

    try:
        asyncio.run(
            runner.run(
                user_message="p" * 900,
                send_event=send_event,
                session_id="sess-1",
                request_id=request_id,
                runtime="local",
                model="custom-model",
            )
        )
        raise AssertionError("expected LlmClientError")
    except LlmClientError:
        pass

    summary = next(
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "model_recovery_summary"
    )
    details = summary.get("details", {})
    assert details.get("final_outcome") == "failure"
    assert details.get("failures_total") == 1
    assert details.get("reason_counts", {}).get("compaction_failure") == 1
    assert details.get("branch_counts", {}).get("fail_fast_compaction_failure") == 1
