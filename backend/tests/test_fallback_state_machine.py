from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.errors import LlmClientError
from app.orchestrator.fallback_state_machine import FallbackRuntimeConfig, FallbackStateMachine
from app.orchestrator.recovery_strategy import RecoveryContext, RecoveryStrategyResolution


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

    async def run(self, *, user_message, send_event, session_id, request_id, model=None, tool_policy=None):
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
    def __init__(self, agent: _FakeAgent, *, retryable: bool = True) -> None:
        self.agent = agent
        self.retryable = retryable
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
            recovery_strategy="none",
            current_user_message=ctx.current_user_message,
            overflow_fallback_retry_attempts=ctx.overflow_fallback_retry_attempts,
            compaction_failure_recovery_attempts=ctx.compaction_failure_recovery_attempts,
            truncation_recovery_attempts=ctx.truncation_recovery_attempts,
            prompt_compaction_attempts=ctx.prompt_compaction_attempts,
            payload_truncation_attempts=ctx.payload_truncation_attempts,
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
    )


def test_state_machine_retries_with_fallback_model_and_succeeds() -> None:
    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback"],
        profile=_RouteProfile(),
    )
    agent = _FakeAgent(fail_first_attempt=True)
    hooks = _Hooks(agent, retryable=True)
    emitted: list[dict] = []

    async def _send_event(payload: dict) -> None:
        emitted.append(payload)

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        send_event=_send_event,
        session_id="s-1",
        request_id="r-1",
        tool_policy=None,
        max_attempts=3,
        config=_runtime_config(),
    )

    result = asyncio.run(machine.run())

    assert result == "ok:model-fallback"
    assert agent.calls == ["model-primary", "model-fallback"]
    assert any(event.get("type") == "status" for event in emitted)
    assert hooks.summary_events[-1]["final_outcome"] == "success"


def test_state_machine_fails_fast_when_not_retryable() -> None:
    route = _Route(
        primary_model="model-primary",
        fallback_models=["model-fallback"],
        profile=_RouteProfile(),
    )
    agent = _FakeAgent(fail_first_attempt=True)
    hooks = _Hooks(agent, retryable=False)

    async def _send_event(_payload: dict) -> None:
        return None

    machine = FallbackStateMachine(
        hooks=hooks,
        route=route,
        runtime="api",
        user_message="please do task",
        send_event=_send_event,
        session_id="s-2",
        request_id="r-2",
        tool_policy=None,
        max_attempts=3,
        config=_runtime_config(),
    )

    with pytest.raises(LlmClientError):
        asyncio.run(machine.run())

    assert agent.calls == ["model-primary"]
    assert hooks.summary_events[-1]["final_outcome"] == "failure"
