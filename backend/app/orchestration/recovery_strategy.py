from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RecoveryStrategyResolution:
    retryable: bool
    recovery_branch: str
    recovery_strategy: str
    current_user_message: str
    overflow_fallback_retry_attempts: int
    compaction_failure_recovery_attempts: int
    truncation_recovery_attempts: int
    prompt_compaction_attempts: int
    payload_truncation_attempts: int
    overflow_retry_applied: bool = False
    compaction_recovery_applied: bool = False
    truncation_recovery_applied: bool = False
    prompt_compaction_applied: bool = False
    payload_truncation_applied: bool = False
    recovery_priority_overridden: bool = False
    signal_priority_applied: bool = False
    signal_priority_reason: str = "none"
    strategy_feedback_applied: bool = False
    strategy_feedback_reason: str = "none"
    persistent_priority_applied: bool = False
    persistent_priority_reason: str = "none"
    prompt_compaction_previous_chars: int = 0
    prompt_compaction_new_chars: int = 0
    payload_truncation_previous_chars: int = 0
    payload_truncation_new_chars: int = 0


@dataclass
class RecoveryContext:
    reason: str
    runtime: str
    candidate_model: str
    has_fallback: bool
    reason_streak: int
    current_user_message: str
    retryable: bool
    recovery_branch: str
    overflow_fallback_retry_enabled: bool
    overflow_fallback_retry_max_attempts: int
    overflow_fallback_retry_attempts: int
    compaction_failure_recovery_enabled: bool
    compaction_failure_recovery_max_attempts: int
    compaction_failure_recovery_attempts: int
    truncation_recovery_enabled: bool
    truncation_recovery_max_attempts: int
    truncation_recovery_attempts: int
    prompt_compaction_enabled: bool
    prompt_compaction_max_attempts: int
    prompt_compaction_attempts: int
    prompt_compaction_ratio: float
    prompt_compaction_min_chars: int
    payload_truncation_enabled: bool
    payload_truncation_max_attempts: int
    payload_truncation_attempts: int
    payload_truncation_target_chars: int
    payload_truncation_min_chars: int
    recovery_priority_flip_enabled: bool
    recovery_priority_flip_threshold: int
    signal_priority_enabled: bool
    signal_low_health_threshold: float
    signal_high_latency_ms: int
    signal_high_cost_threshold: float
    strategy_feedback_enabled: bool
    persistent_priority_enabled: bool
    persistent_priority_min_samples: int
    last_failed_strategy_by_reason: dict[str, str]
    health_score: float
    expected_latency_ms: int
    cost_score: float


@dataclass(frozen=True)
class PriorityRecoveryMetadata:
    priority_steps: tuple[str, ...]
    recovery_priority_overridden: bool
    persistent_priority_applied: bool
    persistent_priority_reason: str
    signal_priority_applied: bool
    signal_priority_reason: str
    strategy_feedback_applied: bool
    strategy_feedback_reason: str


class RecoveryStrategyHooks(Protocol):
    def _resolve_priority_recovery_metadata(self, *, ctx: RecoveryContext) -> PriorityRecoveryMetadata: ...

    def _compact_user_message(self, user_message: str, *, target_ratio: float, min_chars: int) -> str: ...

    def _truncate_payload_for_retry(self, user_message: str, *, target_chars: int, min_chars: int) -> str: ...


class RecoveryStrategyResolver:
    def __init__(self, hooks: RecoveryStrategyHooks):
        self._hooks = hooks

    def resolve(self, *, ctx: RecoveryContext) -> RecoveryStrategyResolution:
        reason = ctx.reason
        has_fallback = ctx.has_fallback
        current_user_message = ctx.current_user_message
        retryable = ctx.retryable
        recovery_branch = ctx.recovery_branch
        overflow_fallback_retry_enabled = ctx.overflow_fallback_retry_enabled
        overflow_fallback_retry_max_attempts = ctx.overflow_fallback_retry_max_attempts
        overflow_fallback_retry_attempts = ctx.overflow_fallback_retry_attempts
        compaction_failure_recovery_enabled = ctx.compaction_failure_recovery_enabled
        compaction_failure_recovery_max_attempts = ctx.compaction_failure_recovery_max_attempts
        compaction_failure_recovery_attempts = ctx.compaction_failure_recovery_attempts
        truncation_recovery_enabled = ctx.truncation_recovery_enabled
        truncation_recovery_max_attempts = ctx.truncation_recovery_max_attempts
        truncation_recovery_attempts = ctx.truncation_recovery_attempts
        prompt_compaction_enabled = ctx.prompt_compaction_enabled
        prompt_compaction_max_attempts = ctx.prompt_compaction_max_attempts
        prompt_compaction_attempts = ctx.prompt_compaction_attempts
        prompt_compaction_ratio = ctx.prompt_compaction_ratio
        prompt_compaction_min_chars = ctx.prompt_compaction_min_chars
        payload_truncation_enabled = ctx.payload_truncation_enabled
        payload_truncation_max_attempts = ctx.payload_truncation_max_attempts
        payload_truncation_attempts = ctx.payload_truncation_attempts
        payload_truncation_target_chars = ctx.payload_truncation_target_chars
        payload_truncation_min_chars = ctx.payload_truncation_min_chars
        prompt_compaction_previous_chars = len(current_user_message or "")
        prompt_compaction_new_chars = prompt_compaction_previous_chars
        payload_truncation_previous_chars = len(current_user_message or "")
        payload_truncation_new_chars = payload_truncation_previous_chars
        recovery_strategy = "none"
        recovery_priority_overridden = False
        signal_priority_applied = False
        signal_priority_reason = "none"
        strategy_feedback_applied = False
        strategy_feedback_reason = "none"
        persistent_priority_applied = False
        persistent_priority_reason = "none"
        overflow_retry_applied = False
        compaction_recovery_applied = False
        truncation_recovery_applied = False
        prompt_compaction_applied = False
        payload_truncation_applied = False

        if reason == "context_overflow":
            metadata = self._hooks._resolve_priority_recovery_metadata(ctx=ctx)
            priority_steps = metadata.priority_steps
            recovery_priority_overridden = metadata.recovery_priority_overridden
            persistent_priority_applied = metadata.persistent_priority_applied
            persistent_priority_reason = metadata.persistent_priority_reason
            signal_priority_applied = metadata.signal_priority_applied
            signal_priority_reason = metadata.signal_priority_reason
            strategy_feedback_applied = metadata.strategy_feedback_applied
            strategy_feedback_reason = metadata.strategy_feedback_reason

            for step in priority_steps:
                if step == "prompt_compaction":
                    if not (
                        prompt_compaction_enabled and prompt_compaction_attempts < prompt_compaction_max_attempts
                    ):
                        continue
                    compacted_message = self._hooks._compact_user_message(
                        current_user_message,
                        target_ratio=prompt_compaction_ratio,
                        min_chars=prompt_compaction_min_chars,
                    )
                    if compacted_message == current_user_message:
                        continue
                    prompt_compaction_attempts += 1
                    current_user_message = compacted_message
                    retryable = True
                    prompt_compaction_applied = True
                    prompt_compaction_new_chars = len(current_user_message)
                    recovery_branch = "guarded_prompt_compaction_recovery"
                    recovery_strategy = "context_overflow:prompt_compaction"
                    break
                if step == "overflow_fallback_retry":
                    if not (
                        has_fallback
                        and overflow_fallback_retry_enabled
                        and overflow_fallback_retry_attempts < overflow_fallback_retry_max_attempts
                    ):
                        continue
                    overflow_fallback_retry_attempts += 1
                    retryable = True
                    overflow_retry_applied = True
                    recovery_branch = "guarded_context_overflow_fallback_retry"
                    recovery_strategy = "context_overflow:fallback_retry"
                    break

        elif (
            reason == "compaction_failure"
            and has_fallback
            and compaction_failure_recovery_enabled
            and compaction_failure_recovery_attempts < compaction_failure_recovery_max_attempts
        ):
            compaction_failure_recovery_attempts += 1
            retryable = True
            compaction_recovery_applied = True
            recovery_branch = "guarded_compaction_failure_recovery"
            recovery_strategy = "compaction_failure:fallback_retry"

        elif reason == "truncation_required":
            metadata = self._hooks._resolve_priority_recovery_metadata(ctx=ctx)
            priority_steps = metadata.priority_steps
            recovery_priority_overridden = metadata.recovery_priority_overridden
            persistent_priority_applied = metadata.persistent_priority_applied
            persistent_priority_reason = metadata.persistent_priority_reason
            signal_priority_applied = metadata.signal_priority_applied
            signal_priority_reason = metadata.signal_priority_reason
            strategy_feedback_applied = metadata.strategy_feedback_applied
            strategy_feedback_reason = metadata.strategy_feedback_reason
            for step in priority_steps:
                if step == "payload_truncation":
                    if not (
                        payload_truncation_enabled
                        and payload_truncation_attempts < payload_truncation_max_attempts
                    ):
                        continue
                    truncated_message = self._hooks._truncate_payload_for_retry(
                        current_user_message,
                        target_chars=payload_truncation_target_chars,
                        min_chars=payload_truncation_min_chars,
                    )
                    if truncated_message == current_user_message:
                        continue
                    payload_truncation_attempts += 1
                    current_user_message = truncated_message
                    retryable = True
                    payload_truncation_applied = True
                    payload_truncation_new_chars = len(current_user_message)
                    recovery_branch = "guarded_payload_truncation_recovery"
                    recovery_strategy = "truncation_required:payload_truncation"
                    break
                if step == "truncation_fallback_retry":
                    if not (
                        has_fallback
                        and truncation_recovery_enabled and truncation_recovery_attempts < truncation_recovery_max_attempts
                    ):
                        continue
                    truncation_recovery_attempts += 1
                    retryable = True
                    truncation_recovery_applied = True
                    recovery_branch = "guarded_truncation_recovery"
                    recovery_strategy = "truncation_required:fallback_retry"
                    break

        return RecoveryStrategyResolution(
            retryable=retryable,
            recovery_branch=recovery_branch,
            recovery_strategy=recovery_strategy,
            current_user_message=current_user_message,
            overflow_fallback_retry_attempts=overflow_fallback_retry_attempts,
            compaction_failure_recovery_attempts=compaction_failure_recovery_attempts,
            truncation_recovery_attempts=truncation_recovery_attempts,
            prompt_compaction_attempts=prompt_compaction_attempts,
            payload_truncation_attempts=payload_truncation_attempts,
            overflow_retry_applied=overflow_retry_applied,
            compaction_recovery_applied=compaction_recovery_applied,
            truncation_recovery_applied=truncation_recovery_applied,
            prompt_compaction_applied=prompt_compaction_applied,
            payload_truncation_applied=payload_truncation_applied,
            recovery_priority_overridden=recovery_priority_overridden,
            signal_priority_applied=signal_priority_applied,
            signal_priority_reason=signal_priority_reason,
            strategy_feedback_applied=strategy_feedback_applied,
            strategy_feedback_reason=strategy_feedback_reason,
            persistent_priority_applied=persistent_priority_applied,
            persistent_priority_reason=persistent_priority_reason,
            prompt_compaction_previous_chars=prompt_compaction_previous_chars,
            prompt_compaction_new_chars=prompt_compaction_new_chars,
            payload_truncation_previous_chars=payload_truncation_previous_chars,
            payload_truncation_new_chars=payload_truncation_new_chars,
        )
