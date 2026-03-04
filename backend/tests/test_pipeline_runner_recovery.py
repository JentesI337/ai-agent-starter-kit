from __future__ import annotations

import asyncio

import pytest

from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract
from app.orchestrator.pipeline_runner import PipelineRunner, RecoveryContext
from app.state import StateStore
from pydantic import BaseModel


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
        temperature=0.0,
        reasoning_depth=1,
        reflection_passes=0,
        combine_steps=False,
    )

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
        return "ok"


def _runner(tmp_path) -> PipelineRunner:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    return PipelineRunner(agent=_FakeAgent(), state_store=store)


def _resolve(runner: PipelineRunner, **overrides):
    params = {
        "reason": "context_overflow",
        "runtime": "local",
        "candidate_model": "model-a",
        "has_fallback": True,
        "reason_streak": 1,
        "current_user_message": "x" * 200,
        "retryable": False,
        "recovery_branch": "none",
        "overflow_fallback_retry_enabled": True,
        "overflow_fallback_retry_max_attempts": 2,
        "overflow_fallback_retry_attempts": 0,
        "compaction_failure_recovery_enabled": True,
        "compaction_failure_recovery_max_attempts": 2,
        "compaction_failure_recovery_attempts": 0,
        "truncation_recovery_enabled": True,
        "truncation_recovery_max_attempts": 2,
        "truncation_recovery_attempts": 0,
        "prompt_compaction_enabled": True,
        "prompt_compaction_max_attempts": 2,
        "prompt_compaction_attempts": 0,
        "prompt_compaction_ratio": 0.5,
        "prompt_compaction_min_chars": 20,
        "payload_truncation_enabled": True,
        "payload_truncation_max_attempts": 2,
        "payload_truncation_attempts": 0,
        "payload_truncation_target_chars": 80,
        "payload_truncation_min_chars": 20,
        "recovery_priority_flip_enabled": False,
        "recovery_priority_flip_threshold": 2,
        "signal_priority_enabled": False,
        "signal_low_health_threshold": 0.5,
        "signal_high_latency_ms": 400,
        "signal_high_cost_threshold": 0.8,
        "strategy_feedback_enabled": False,
        "persistent_priority_enabled": False,
        "persistent_priority_min_samples": 3,
        "last_failed_strategy_by_reason": {},
        "health_score": 0.9,
        "expected_latency_ms": 100,
        "cost_score": 0.2,
    }
    params.update(overrides)
    return runner._resolve_recovery_strategy(ctx=RecoveryContext(**params))


def test_context_overflow_applies_prompt_compaction(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(runner)

    assert resolution.prompt_compaction_applied is True
    assert resolution.recovery_strategy == "context_overflow:prompt_compaction"
    assert resolution.recovery_branch == "guarded_prompt_compaction_recovery"
    assert resolution.prompt_compaction_new_chars < resolution.prompt_compaction_previous_chars


def test_truncation_required_applies_payload_truncation(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_truncation_priority_local",
        ["payload_truncation", "truncation_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(
        runner,
        reason="truncation_required",
        payload_truncation_target_chars=60,
        current_user_message="y" * 200,
    )

    assert resolution.payload_truncation_applied is True
    assert resolution.recovery_strategy == "truncation_required:payload_truncation"
    assert resolution.recovery_branch == "guarded_payload_truncation_recovery"
    assert resolution.payload_truncation_new_chars < resolution.payload_truncation_previous_chars


def test_signal_priority_prefers_fallback_on_low_health(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(
        runner,
        signal_priority_enabled=True,
        health_score=0.2,
        signal_low_health_threshold=0.5,
    )

    assert resolution.overflow_retry_applied is True
    assert resolution.recovery_strategy == "context_overflow:fallback_retry"
    assert resolution.signal_priority_applied is True
    assert resolution.signal_priority_reason == "low_health_prefer_fallback"


def test_signal_priority_reason_none_when_no_reordering_needed(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(
        runner,
        signal_priority_enabled=True,
        expected_latency_ms=900,
        signal_high_latency_ms=400,
    )

    assert resolution.prompt_compaction_applied is True
    assert resolution.signal_priority_applied is False
    assert resolution.signal_priority_reason == "none"


def test_strategy_feedback_demotes_last_failed_strategy(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(
        runner,
        strategy_feedback_enabled=True,
        last_failed_strategy_by_reason={"context_overflow": "prompt_compaction"},
    )

    assert resolution.overflow_retry_applied is True
    assert resolution.strategy_feedback_applied is True
    assert resolution.strategy_feedback_reason == "demote:prompt_compaction"


def test_strategy_feedback_reason_none_when_failed_strategy_already_last(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(
        runner,
        strategy_feedback_enabled=True,
        last_failed_strategy_by_reason={"context_overflow": "overflow_fallback_retry"},
    )

    assert resolution.prompt_compaction_applied is True
    assert resolution.strategy_feedback_applied is False
    assert resolution.strategy_feedback_reason == "none"


def test_priority_flip_switches_order_when_streak_threshold_reached(monkeypatch, tmp_path) -> None:
    runner = _runner(tmp_path)
    monkeypatch.setattr(
        settings,
        "pipeline_runner_context_overflow_priority_local",
        ["prompt_compaction", "overflow_fallback_retry"],
        raising=False,
    )

    resolution = _resolve(
        runner,
        recovery_priority_flip_enabled=True,
        recovery_priority_flip_threshold=2,
        reason_streak=2,
    )

    assert resolution.overflow_retry_applied is True
    assert resolution.recovery_priority_overridden is True


def test_compaction_failure_recovery_uses_fallback_retry(tmp_path) -> None:
    runner = _runner(tmp_path)

    resolution = _resolve(
        runner,
        reason="compaction_failure",
        compaction_failure_recovery_enabled=True,
        compaction_failure_recovery_attempts=0,
        compaction_failure_recovery_max_attempts=2,
    )

    assert resolution.compaction_recovery_applied is True
    assert resolution.recovery_strategy == "compaction_failure:fallback_retry"
    assert resolution.recovery_branch == "guarded_compaction_failure_recovery"


@pytest.mark.parametrize(
    "message,expected_reason",
    [
        ("Request failed: context window exceeded", "context_overflow"),
        ("provider said truncation required due to token limit", "truncation_required"),
        ("Bad request: roles must alternate between user and assistant", "role_ordering"),
        ("HTTP 429 too many requests", "rate_limited"),
        ("upstream model not found", "model_not_found"),
        ("request timed out", "timeout"),
        ("service unavailable (503)", "temporary_unavailable"),
        ("network dns failure", "network_error"),
        ("unknown weird failure", "unknown"),
    ],
)
def test_classify_failover_reason_mapping(tmp_path, message: str, expected_reason: str) -> None:
    runner = _runner(tmp_path)

    assert runner._classify_failover_reason(message) == expected_reason


@pytest.mark.parametrize(
    "reason,expected_branch",
    [
        ("context_overflow", "fail_fast_context_overflow"),
        ("compaction_failure", "fail_fast_compaction_failure"),
        ("truncation_required", "fail_fast_truncation_required"),
        ("role_ordering", "retry_with_fallback"),
        ("rate_limited", "retry_with_fallback"),
        ("unknown", "fail_fast_non_retryable"),
    ],
)
def test_resolve_recovery_branch_mapping(tmp_path, reason: str, expected_branch: str) -> None:
    runner = _runner(tmp_path)

    assert runner._resolve_recovery_branch(reason) == expected_branch


def test_compact_user_message_reduces_size_and_adds_suffix(tmp_path) -> None:
    runner = _runner(tmp_path)

    compacted = runner._compact_user_message("z" * 200, target_ratio=0.5, min_chars=20)

    assert len(compacted) < 200
    assert "context compacted by pipeline runner" in compacted


def test_truncate_payload_for_retry_reduces_size_and_adds_suffix(tmp_path) -> None:
    runner = _runner(tmp_path)

    truncated = runner._truncate_payload_for_retry("w" * 200, target_chars=80, min_chars=20)

    assert len(truncated) < 200
    assert "payload truncated by pipeline runner" in truncated


def test_recovery_summary_includes_applied_vs_not_applied_metrics(tmp_path) -> None:
    runner = _runner(tmp_path)
    events: list[dict] = []

    async def _send_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(
        runner._emit_recovery_summary_event(
            send_event=_send_event,
            request_id="req-1",
            session_id="sess-1",
            attempts=2,
            max_attempts=3,
            recovery_failures_total=2,
            recovery_reason_counts={"context_overflow": 2},
            recovery_branch_counts={"guarded_prompt_compaction_recovery": 1, "guarded_context_overflow_fallback_retry": 1},
            recovery_strategy_counts={"prompt_compaction": 1, "overflow_fallback_retry": 1},
            recovery_strategy_applied_total=2,
            recovery_signal_priority_applied_total=1,
            recovery_signal_priority_not_applied_disabled_total=0,
            recovery_signal_priority_not_applied_not_applicable_total=1,
            recovery_signal_priority_not_applied_no_reorder_total=0,
            recovery_strategy_feedback_applied_total=0,
            recovery_strategy_feedback_not_applied_disabled_total=1,
            recovery_strategy_feedback_not_applied_not_applicable_total=0,
            recovery_strategy_feedback_not_applied_no_reorder_total=1,
            recovery_persistent_priority_applied_total=1,
            recovery_persistent_priority_not_applied_disabled_total=0,
            recovery_persistent_priority_not_applied_not_applicable_total=0,
            recovery_persistent_priority_not_applied_no_reorder_total=1,
            recovery_overflow_retry_applied_total=1,
            recovery_compaction_recovery_applied_total=0,
            recovery_truncation_recovery_applied_total=0,
            recovery_prompt_compaction_applied_total=1,
            recovery_payload_truncation_applied_total=0,
            final_outcome="success",
            final_model="model-a",
            final_reason="context_overflow",
        )
    )

    assert len(events) == 1
    payload = events[0]
    assert payload.get("type") == "lifecycle"
    assert payload.get("stage") == "model_recovery_summary"
    details = payload.get("details", {})

    assert details.get("signal_priority_applied_vs_not_applied") == {"applied": 1, "not_applied": 1}
    assert details.get("signal_priority_not_applied_breakdown") == {
        "disabled": 0,
        "not_applicable": 1,
        "no_reorder": 0,
    }
    assert details.get("strategy_feedback_applied_vs_not_applied") == {"applied": 0, "not_applied": 2}
    assert details.get("strategy_feedback_not_applied_breakdown") == {
        "disabled": 1,
        "not_applicable": 0,
        "no_reorder": 1,
    }
    assert details.get("persistent_priority_applied_vs_not_applied") == {"applied": 1, "not_applied": 1}
    assert details.get("persistent_priority_not_applied_breakdown") == {
        "disabled": 0,
        "not_applicable": 0,
        "no_reorder": 1,
    }
    assert details.get("recovered_successfully") is True
    assert details.get("terminal_reason") == "recovered"


def test_recovery_summary_contains_monitoring_required_keys(tmp_path) -> None:
    runner = _runner(tmp_path)
    events: list[dict] = []

    async def _send_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(
        runner._emit_recovery_summary_event(
            send_event=_send_event,
            request_id="req-2",
            session_id="sess-2",
            attempts=1,
            max_attempts=3,
            recovery_failures_total=1,
            recovery_reason_counts={"context_overflow": 1},
            recovery_branch_counts={"guarded_prompt_compaction_recovery": 1},
            recovery_strategy_counts={"prompt_compaction": 1},
            recovery_strategy_applied_total=1,
            recovery_signal_priority_applied_total=0,
            recovery_signal_priority_not_applied_disabled_total=0,
            recovery_signal_priority_not_applied_not_applicable_total=1,
            recovery_signal_priority_not_applied_no_reorder_total=0,
            recovery_strategy_feedback_applied_total=0,
            recovery_strategy_feedback_not_applied_disabled_total=1,
            recovery_strategy_feedback_not_applied_not_applicable_total=0,
            recovery_strategy_feedback_not_applied_no_reorder_total=0,
            recovery_persistent_priority_applied_total=0,
            recovery_persistent_priority_not_applied_disabled_total=1,
            recovery_persistent_priority_not_applied_not_applicable_total=0,
            recovery_persistent_priority_not_applied_no_reorder_total=0,
            recovery_overflow_retry_applied_total=0,
            recovery_compaction_recovery_applied_total=0,
            recovery_truncation_recovery_applied_total=0,
            recovery_prompt_compaction_applied_total=1,
            recovery_payload_truncation_applied_total=0,
            final_outcome="success",
            final_model="model-a",
            final_reason="context_overflow",
        )
    )

    details = events[0].get("details", {})
    required_keys = {
        "attempts",
        "max_attempts",
        "failures_total",
        "final_outcome",
        "final_model",
        "final_reason",
        "recovered_successfully",
        "terminal_reason",
        "reason_counts",
        "branch_counts",
        "strategy_counts",
        "signal_priority_applied_vs_not_applied",
        "strategy_feedback_applied_vs_not_applied",
        "persistent_priority_applied_vs_not_applied",
        "signal_priority_not_applied_breakdown",
        "strategy_feedback_not_applied_breakdown",
        "persistent_priority_not_applied_breakdown",
    }
    assert required_keys.issubset(set(details.keys()))

    for key in (
        "signal_priority_not_applied_breakdown",
        "strategy_feedback_not_applied_breakdown",
        "persistent_priority_not_applied_breakdown",
    ):
        breakdown = details.get(key, {})
        assert {"disabled", "not_applicable", "no_reorder"}.issubset(set(breakdown.keys()))


def test_recovery_summary_sets_terminal_reason_for_failure(tmp_path) -> None:
    runner = _runner(tmp_path)
    events: list[dict] = []

    async def _send_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(
        runner._emit_recovery_summary_event(
            send_event=_send_event,
            request_id="req-3",
            session_id="sess-3",
            attempts=2,
            max_attempts=2,
            recovery_failures_total=2,
            recovery_reason_counts={"rate_limited": 2},
            recovery_branch_counts={"retry_with_fallback": 2},
            recovery_strategy_counts={"overflow_fallback_retry": 2},
            recovery_strategy_applied_total=2,
            recovery_signal_priority_applied_total=0,
            recovery_signal_priority_not_applied_disabled_total=1,
            recovery_signal_priority_not_applied_not_applicable_total=0,
            recovery_signal_priority_not_applied_no_reorder_total=1,
            recovery_strategy_feedback_applied_total=0,
            recovery_strategy_feedback_not_applied_disabled_total=1,
            recovery_strategy_feedback_not_applied_not_applicable_total=0,
            recovery_strategy_feedback_not_applied_no_reorder_total=1,
            recovery_persistent_priority_applied_total=0,
            recovery_persistent_priority_not_applied_disabled_total=1,
            recovery_persistent_priority_not_applied_not_applicable_total=0,
            recovery_persistent_priority_not_applied_no_reorder_total=1,
            recovery_overflow_retry_applied_total=2,
            recovery_compaction_recovery_applied_total=0,
            recovery_truncation_recovery_applied_total=0,
            recovery_prompt_compaction_applied_total=0,
            recovery_payload_truncation_applied_total=0,
            final_outcome="failure",
            final_model="model-fallback",
            final_reason="rate_limited",
        )
    )

    details = events[0].get("details", {})
    assert details.get("recovered_successfully") is False
    assert details.get("terminal_reason") == "rate_limited"


def test_pipeline_runner_emits_terminal_wait_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "context_window_warn_below_tokens", 8000, raising=False)
    monkeypatch.setattr(settings, "context_window_hard_min_tokens", 4000, raising=False)
    runner = _runner(tmp_path)
    events: list[dict] = []

    runner.state_store.init_run(
        run_id="req-1",
        session_id="sess-1",
        request_id="req-1",
        user_message="hello",
        runtime="local",
        model="openai:gpt-5",
    )

    async def _send_event(payload: dict) -> None:
        events.append(payload)

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=_send_event,
            session_id="sess-1",
            request_id="req-1",
            runtime="local",
            model=None,
            tool_policy=None,
        )
    )

    assert result == "ok"
    lifecycle_stages = [
        evt.get("stage")
        for evt in events
        if evt.get("type") == "lifecycle"
    ]
    assert "terminal_wait_started" in lifecycle_stages
    assert "terminal_wait_completed" in lifecycle_stages
    assert lifecycle_stages.index("terminal_wait_started") < lifecycle_stages.index("terminal_wait_completed")
