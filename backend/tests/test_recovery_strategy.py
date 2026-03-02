from __future__ import annotations

from app.orchestrator.recovery_strategy import (
    PriorityRecoveryMetadata,
    RecoveryContext,
    RecoveryStrategyResolver,
)


class _Hooks:
    def __init__(
        self,
        *,
        priority_steps: tuple[str, ...],
        compacted_message: str | None = None,
        truncated_message: str | None = None,
    ) -> None:
        self.priority_steps = priority_steps
        self.compacted_message = compacted_message
        self.truncated_message = truncated_message
        self.compact_calls = 0
        self.truncate_calls = 0

    def _resolve_priority_recovery_metadata(self, *, ctx: RecoveryContext) -> PriorityRecoveryMetadata:
        _ = ctx
        return PriorityRecoveryMetadata(
            priority_steps=self.priority_steps,
            recovery_priority_overridden=False,
            persistent_priority_applied=False,
            persistent_priority_reason="none",
            signal_priority_applied=False,
            signal_priority_reason="none",
            strategy_feedback_applied=False,
            strategy_feedback_reason="none",
        )

    def _compact_user_message(self, user_message: str, *, target_ratio: float, min_chars: int) -> str:
        _ = (target_ratio, min_chars)
        self.compact_calls += 1
        if self.compacted_message is None:
            return user_message
        return self.compacted_message

    def _truncate_payload_for_retry(self, user_message: str, *, target_chars: int, min_chars: int) -> str:
        _ = (target_chars, min_chars)
        self.truncate_calls += 1
        if self.truncated_message is None:
            return user_message
        return self.truncated_message


def _context(**overrides) -> RecoveryContext:
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
    return RecoveryContext(**params)


def test_resolver_applies_prompt_compaction_first() -> None:
    hooks = _Hooks(
        priority_steps=("prompt_compaction", "overflow_fallback_retry"),
        compacted_message="short message",
    )
    resolver = RecoveryStrategyResolver(hooks)

    resolution = resolver.resolve(ctx=_context())

    assert hooks.compact_calls == 1
    assert resolution.prompt_compaction_applied is True
    assert resolution.recovery_strategy == "context_overflow:prompt_compaction"
    assert resolution.recovery_branch == "guarded_prompt_compaction_recovery"
    assert resolution.current_user_message == "short message"
    assert resolution.prompt_compaction_attempts == 1


def test_resolver_falls_back_to_overflow_retry_when_compaction_noop() -> None:
    hooks = _Hooks(
        priority_steps=("prompt_compaction", "overflow_fallback_retry"),
        compacted_message=None,
    )
    resolver = RecoveryStrategyResolver(hooks)

    resolution = resolver.resolve(ctx=_context())

    assert hooks.compact_calls == 1
    assert resolution.prompt_compaction_applied is False
    assert resolution.overflow_retry_applied is True
    assert resolution.recovery_strategy == "context_overflow:fallback_retry"
    assert resolution.overflow_fallback_retry_attempts == 1


def test_resolver_applies_payload_truncation_for_truncation_reason() -> None:
    hooks = _Hooks(
        priority_steps=("payload_truncation", "truncation_fallback_retry"),
        truncated_message="truncated message",
    )
    resolver = RecoveryStrategyResolver(hooks)

    resolution = resolver.resolve(
        ctx=_context(
            reason="truncation_required",
            current_user_message="y" * 200,
            payload_truncation_target_chars=60,
        )
    )

    assert hooks.truncate_calls == 1
    assert resolution.payload_truncation_applied is True
    assert resolution.recovery_strategy == "truncation_required:payload_truncation"
    assert resolution.recovery_branch == "guarded_payload_truncation_recovery"
    assert resolution.current_user_message == "truncated message"


def test_resolver_handles_compaction_failure_via_fallback_retry() -> None:
    hooks = _Hooks(priority_steps=("prompt_compaction", "overflow_fallback_retry"))
    resolver = RecoveryStrategyResolver(hooks)

    resolution = resolver.resolve(
        ctx=_context(
            reason="compaction_failure",
            compaction_failure_recovery_enabled=True,
            compaction_failure_recovery_attempts=0,
            compaction_failure_recovery_max_attempts=2,
        )
    )

    assert resolution.compaction_recovery_applied is True
    assert resolution.recovery_strategy == "compaction_failure:fallback_retry"
    assert resolution.recovery_branch == "guarded_compaction_failure_recovery"
