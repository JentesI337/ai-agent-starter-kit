from __future__ import annotations

from dataclasses import dataclass

import pytest
from tests.async_test_guards import run_async_with_timeout

from app.orchestration.fallback_state_machine import FallbackRuntimeConfig, FallbackStateMachine
from app.orchestration.recovery_strategy import RecoveryContext, RecoveryStrategyResolution
from app.shared.errors import GuardrailViolation, LlmClientError


@dataclass
class _RouteProfile:
    health_score: float = 0.9
    expected_latency_ms: int = 100
    cost_score: float = 0.1


@dataclass
class _Route:
    primary_model: str
    fallback_models: list[str]
    profile: _RouteProfile


class _FakeAgent:
    def __init__(self, fail_first_attempt: bool = True) -> None:
        self.name = "fake-agent"
        self._fail_first_attempt = fail_first_attempt
        self.calls: list[str] = []

    async def run(
        self,
        *,
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        _ = (user_message, send_event, session_id, request_id, tool_policy)
        model_name = str(model or "")
        self.calls.append(model_name)
        if self._fail_first_attempt and len(self.calls) == 1:
            raise LlmClientError("HTTP 429 rate limit")
        raise_on = model_name == "model-primary"
        if raise_on and self._fail_first_attempt:
            raise LlmClientError("temporary failure")
        return f"ok:{model_name}"


class _Hooks:
    def __init__(
        self,
        agent: _FakeAgent,
        *,
        retryable: bool = True,
        signal_priority_applied: bool = False,
        signal_priority_reason: str = "none",
        strategy_feedback_applied: bool = False,
        strategy_feedback_reason: str = "none",
        persistent_priority_applied: bool = False,
        persistent_priority_reason: str = "none",
        prompt_compaction_applied: bool = False,
        payload_truncation_applied: bool = False,
        recovery_strategy: str = "none",
    ) -> None:
        self.agent = agent
        self.retryable = retryable
        self.signal_priority_applied = signal_priority_applied
        self.signal_priority_reason = signal_priority_reason
        self.strategy_feedback_applied = strategy_feedback_applied
        self.strategy_feedback_reason = strategy_feedback_reason
        self.persistent_priority_applied = persistent_priority_applied
        self.persistent_priority_reason = persistent_priority_reason
        self.prompt_compaction_applied = prompt_compaction_applied
        self.payload_truncation_applied = payload_truncation_applied
        self.recovery_strategy = recovery_strategy
        self.summary_events: list[dict] = []
        self.metrics: list[tuple[str, str, str, str]] = []

    def _classify_failover_reason(self, message: str) -> str:
        _ = message
        return "rate_limited"

    def _is_retryable_failover_reason(self, reason: str) -> bool:
        _ = reason
        return self.retryable

    def _resolve_recovery_branch(self, reason: str) -> str:
        _ = reason
        return "retry_with_fallback" if self.retryable else "fail_fast_non_retryable"

    def _resolve_recovery_strategy(self, *, ctx: RecoveryContext) -> RecoveryStrategyResolution:
        return RecoveryStrategyResolution(
            retryable=self.retryable,
            recovery_branch="retry_with_fallback" if self.retryable else "fail_fast_non_retryable",
            recovery_strategy=self.recovery_strategy,
            current_user_message=ctx.current_user_message,
            overflow_fallback_retry_attempts=ctx.overflow_fallback_retry_attempts,
            compaction_failure_recovery_attempts=ctx.compaction_failure_recovery_attempts,
            truncation_recovery_attempts=ctx.truncation_recovery_attempts,
            prompt_compaction_attempts=ctx.prompt_compaction_attempts,
            payload_truncation_attempts=ctx.payload_truncation_attempts,
            signal_priority_applied=self.signal_priority_applied,
            signal_priority_reason=self.signal_priority_reason,
            strategy_feedback_applied=self.strategy_feedback_applied,
            strategy_feedback_reason=self.strategy_feedback_reason,
            persistent_priority_applied=self.persistent_priority_applied,
            persistent_priority_reason=self.persistent_priority_reason,
            prompt_compaction_applied=self.prompt_compaction_applied,
            payload_truncation_applied=self.payload_truncation_applied,
            prompt_compaction_previous_chars=len(ctx.current_user_message),
            prompt_compaction_new_chars=max(0, len(ctx.current_user_message) - 20),
            payload_truncation_previous_chars=len(ctx.current_user_message),
            payload_truncation_new_chars=max(0, len(ctx.current_user_message) - 30),
        )

    async def _emit_recovery_summary_event(self, **kwargs) -> None:
        self.summary_events.append(kwargs)

    def _record_recovery_metric(self, *, model_id: str, reason: str, strategy: str, outcome: str) -> None:
        self.metrics.append((model_id, reason, strategy, outcome))


def _runtime_config() -> FallbackRuntimeConfig:
    return FallbackRuntimeConfig(
        overflow_fallback_retry_enabled=True,
        overflow_fallback_retry_max_attempts=2,
        compaction_failure_recovery_enabled=True,
        compaction_failure_recovery_max_attempts=2,
        truncation_recovery_enabled=True,
        truncation_recovery_max_attempts=2,
        prompt_compaction_enabled=True,
        prompt_compaction_max_attempts=2,
        prompt_compaction_ratio=0.5,
        prompt_compaction_min_chars=20,
        payload_truncation_enabled=True,
        payload_truncation_max_attempts=2,
        payload_truncation_target_chars=80,
        payload_truncation_min_chars=20,
        recovery_priority_flip_enabled=True,
        recovery_priority_flip_threshold=2,
        signal_priority_enabled=True,
        signal_low_health_threshold=0.5,
        signal_high_latency_ms=400,
        signal_high_cost_threshold=0.8,
        strategy_feedback_enabled=True,
        persistent_priority_enabled=True,
        persistent_priority_min_samples=3,
        recovery_backoff_enabled=True,
        recovery_backoff_base_ms=1,
        recovery_backoff_max_ms=2,
        recovery_backoff_multiplier=2.0,
        recovery_backoff_jitter=False,
    )


def test_state_machine_retries_with_fallback_model_and_succeeds() -> None:
    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback"],
        profile=_RouteProfile(),
    )
    agent = _FakeAgent(fail_first_attempt=True)
    hooks = _Hooks(
        agent,
        retryable=True,
        signal_priority_reason="not_applicable",
        strategy_feedback_reason="disabled",
        persistent_priority_reason="insufficient_samples",
    )
    emitted: list[dict] = []

    async def _send_event(payload: dict) -> None:
        emitted.append(payload)

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        prompt_mode="full",
        send_event=_send_event,
        session_id="s-1",
        request_id="r-1",
        should_steer_interrupt=None,
        tool_policy=None,
        max_attempts=3,
        config=_runtime_config(),
    )

    result = run_async_with_timeout(machine.run(), timeout_seconds=2.0)

    assert result == "ok:model-fallback"
    assert agent.calls == ["model-primary", "model-fallback"]
    assert any(event.get("type") == "status" for event in emitted)
    branch_event = next(
        event
        for event in emitted
        if event.get("type") == "lifecycle" and event.get("stage") == "model_recovery_branch_selected"
    )
    branch_details = branch_event.get("details", {})
    required_branch_keys = {
        "model",
        "reason",
        "branch",
        "retryable",
        "has_fallback",
        "recovery_strategy",
        "reason_streak",
        "recovery_priority_overridden",
        "signal_priority_applied",
        "signal_priority_reason",
        "strategy_feedback_applied",
        "strategy_feedback_reason",
        "persistent_priority_applied",
        "persistent_priority_reason",
    }
    assert required_branch_keys.issubset(set(branch_details.keys()))
    assert branch_details.get("reason") == "rate_limited"
    assert branch_details.get("branch") == "retry_with_fallback"
    assert branch_details.get("retryable") is True
    assert branch_details.get("has_fallback") is True
    assert branch_details.get("recovery_strategy") == "none"

    action_event = next(
        event
        for event in emitted
        if event.get("type") == "lifecycle" and event.get("stage") == "model_recovery_action"
    )
    action_details = action_event.get("details", {})
    required_action_keys = {
        "model",
        "reason",
        "branch",
        "action",
        "recovery_strategy",
        "reason_streak",
        "recovery_priority_overridden",
        "signal_priority_applied",
        "signal_priority_reason",
        "strategy_feedback_applied",
        "strategy_feedback_reason",
        "persistent_priority_applied",
        "persistent_priority_reason",
    }
    assert required_action_keys.issubset(set(action_details.keys()))
    assert action_details.get("reason") == "rate_limited"
    assert action_details.get("branch") == "retry_with_fallback"
    assert action_details.get("action") == "retry_fallback"
    assert action_details.get("recovery_strategy") == "none"
    summary = hooks.summary_events[-1]
    assert summary["final_outcome"] == "success"
    assert summary["final_reason"] == "rate_limited"
    assert summary["recovery_signal_priority_not_applied_not_applicable_total"] == 1
    assert summary["recovery_strategy_feedback_not_applied_disabled_total"] == 1
    assert summary["recovery_persistent_priority_not_applied_no_reorder_total"] == 1
    backoff_event = next(
        event
        for event in emitted
        if event.get("type") == "lifecycle" and event.get("stage") == "model_recovery_backoff"
    )
    backoff_details = backoff_event.get("details", {})
    assert backoff_details.get("reason") == "rate_limited"
    assert backoff_details.get("reason_class") == "transient"
    assert isinstance(backoff_details.get("delay_ms"), int)


def test_state_machine_fails_fast_when_not_retryable() -> None:
    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback"],
        profile=_RouteProfile(),
    )
    agent = _FakeAgent(fail_first_attempt=True)
    hooks = _Hooks(agent, retryable=False)
    emitted: list[dict] = []

    async def _send_event(payload: dict) -> None:
        emitted.append(payload)

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        prompt_mode="full",
        send_event=_send_event,
        session_id="s-2",
        request_id="r-2",
        should_steer_interrupt=None,
        tool_policy=None,
        max_attempts=3,
        config=_runtime_config(),
    )

    with pytest.raises(LlmClientError):
        run_async_with_timeout(machine.run(), timeout_seconds=2.0)

    assert agent.calls == ["model-primary"]
    action_event = next(
        event
        for event in emitted
        if event.get("type") == "lifecycle" and event.get("stage") == "model_recovery_action"
    )
    action_details = action_event.get("details", {})
    assert action_details.get("reason") == "rate_limited"
    assert action_details.get("branch") == "fail_fast_non_retryable"
    assert action_details.get("action") == "fail_fast"
    assert action_details.get("recovery_strategy") == "none"
    assert hooks.summary_events[-1]["final_outcome"] == "failure"
    assert hooks.summary_events[-1]["final_reason"] == "rate_limited"
    branch_event = next(
        event
        for event in emitted
        if event.get("type") == "lifecycle" and event.get("stage") == "model_fallback_classified"
    )
    branch_details = branch_event.get("details", {})
    assert branch_details.get("reason_class") == "transient"
    assert branch_details.get("retry_policy") == "fail_fast"


def test_state_machine_emits_transform_event_when_compaction_applied() -> None:
    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback"],
        profile=_RouteProfile(),
    )
    agent = _FakeAgent(fail_first_attempt=True)
    hooks = _Hooks(
        agent,
        retryable=True,
        prompt_compaction_applied=True,
        recovery_strategy="context_overflow:prompt_compaction",
    )
    emitted: list[dict] = []

    async def _send_event(payload: dict) -> None:
        emitted.append(payload)

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        prompt_mode="full",
        send_event=_send_event,
        session_id="s-3",
        request_id="r-3",
        should_steer_interrupt=None,
        tool_policy=None,
        max_attempts=3,
        config=_runtime_config(),
    )

    result = run_async_with_timeout(machine.run(), timeout_seconds=2.0)

    assert result == "ok:model-fallback"
    transform_event = next(
        event
        for event in emitted
        if event.get("type") == "lifecycle" and event.get("stage") == "model_recovery_transform_applied"
    )
    transform_details = transform_event.get("details", {})
    assert transform_details.get("transform_type") == "prompt_compaction"
    assert transform_details.get("reason_class") == "transient"
    assert transform_details.get("recovery_strategy") == "context_overflow:prompt_compaction"
    assert int(transform_details.get("chars_reduced", 0)) >= 0


def test_state_machine_terminates_when_fallbacks_exhausted() -> None:
    class _AlwaysFailAgent:
        def __init__(self) -> None:
            self.name = "always-fail-agent"
            self.calls: list[str] = []

        async def run(
            self,
            *,
            user_message,
            send_event,
            session_id,
            request_id,
            model=None,
            tool_policy=None,
            prompt_mode=None,
            should_steer_interrupt=None,
        ):
            _ = (user_message, send_event, session_id, request_id, tool_policy, prompt_mode, should_steer_interrupt)
            model_name = str(model or "")
            self.calls.append(model_name)
            raise LlmClientError("temporary failure")

    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback-a", "model-fallback-b"],
        profile=_RouteProfile(),
    )
    agent = _AlwaysFailAgent()
    hooks = _Hooks(agent, retryable=True)

    async def _send_event(payload: dict) -> None:
        _ = payload

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        prompt_mode="full",
        send_event=_send_event,
        session_id="s-4",
        request_id="r-4",
        should_steer_interrupt=None,
        tool_policy=None,
        max_attempts=6,
        config=_runtime_config(),
    )

    with pytest.raises(LlmClientError):
        run_async_with_timeout(machine.run(), timeout_seconds=2.0)

    assert agent.calls == ["model-primary", "model-fallback-a", "model-fallback-b"]


def test_guardrail_violation_releases_half_open_probe_and_reraises() -> None:
    class _GuardrailAgent:
        def __init__(self) -> None:
            self.name = "guardrail-agent"

        async def run(
            self,
            *,
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
            raise GuardrailViolation("guardrail blocked")

    class _StubCircuitBreaker:
        def __init__(self) -> None:
            self.release_calls: list[str] = []

        async def allow_request(self, model_id: str):
            return True, None

        async def release_probe(self, model_id: str) -> None:
            self.release_calls.append(model_id)

    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback"],
        profile=_RouteProfile(),
    )
    agent = _GuardrailAgent()
    hooks = _Hooks(agent, retryable=True)
    cb = _StubCircuitBreaker()

    async def _send_event(payload: dict) -> None:
        _ = payload

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        prompt_mode="full",
        send_event=_send_event,
        session_id="s-guardrail",
        request_id="r-guardrail",
        should_steer_interrupt=None,
        tool_policy=None,
        max_attempts=3,
        config=_runtime_config(),
        circuit_breaker=cb,
    )

    with pytest.raises(GuardrailViolation):
        run_async_with_timeout(machine.run(), timeout_seconds=2.0)

    assert cb.release_calls == ["model-primary"]
