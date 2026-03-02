from __future__ import annotations

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

    async def run(self, user_message, send_event, session_id, request_id, model=None, tool_policy=None):
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
