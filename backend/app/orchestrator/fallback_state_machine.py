from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import random
from collections.abc import Callable
from typing import Protocol

from app.contracts.agent_contract import AgentContract, SendEvent
from app.errors import LlmClientError
from app.model_routing.router import ModelRouteDecision
from app.orchestrator.events import LifecycleStage, build_lifecycle_event
from app.orchestrator.recovery_strategy import RecoveryContext, RecoveryStrategyResolution
from app.tool_policy import ToolPolicyDict


class FallbackHooks(Protocol):
    @property
    def agent(self) -> AgentContract: ...

    def _classify_failover_reason(self, message: str) -> str: ...

    def _is_retryable_failover_reason(self, reason: str) -> bool: ...

    def _resolve_recovery_branch(self, reason: str) -> str: ...

    def _resolve_recovery_strategy(self, *, ctx: RecoveryContext) -> RecoveryStrategyResolution: ...

    async def _emit_recovery_summary_event(self, **kwargs) -> None: ...

    def _record_recovery_metric(self, *, model_id: str, reason: str, strategy: str, outcome: str) -> None: ...


@dataclass
class FallbackAttemptState:
    attempts: int = 0
    max_attempts: int = 1
    current_user_message: str = ""
    last_error: Exception | None = None
    last_reason: str = "unknown"
    reason_streak: int = 0
    previous_reason: str = ""
    pending_recovery_outcome: tuple[str, str, str] | None = None
    overflow_fallback_retry_attempts: int = 0
    compaction_failure_recovery_attempts: int = 0
    truncation_recovery_attempts: int = 0
    prompt_compaction_attempts: int = 0
    payload_truncation_attempts: int = 0
    recovery_failures_total: int = 0
    recovery_reason_counts: dict[str, int] | None = None
    recovery_branch_counts: dict[str, int] | None = None
    recovery_strategy_counts: dict[str, int] | None = None
    recovery_strategy_applied_total: int = 0
    recovery_signal_priority_applied_total: int = 0
    recovery_signal_priority_not_applied_disabled_total: int = 0
    recovery_signal_priority_not_applied_not_applicable_total: int = 0
    recovery_signal_priority_not_applied_no_reorder_total: int = 0
    recovery_strategy_feedback_applied_total: int = 0
    recovery_strategy_feedback_not_applied_disabled_total: int = 0
    recovery_strategy_feedback_not_applied_not_applicable_total: int = 0
    recovery_strategy_feedback_not_applied_no_reorder_total: int = 0
    recovery_persistent_priority_applied_total: int = 0
    recovery_persistent_priority_not_applied_disabled_total: int = 0
    recovery_persistent_priority_not_applied_not_applicable_total: int = 0
    recovery_persistent_priority_not_applied_no_reorder_total: int = 0
    recovery_overflow_retry_applied_total: int = 0
    recovery_compaction_recovery_applied_total: int = 0
    recovery_truncation_recovery_applied_total: int = 0
    recovery_prompt_compaction_applied_total: int = 0
    recovery_payload_truncation_applied_total: int = 0
    last_failed_strategy_by_reason: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.recovery_reason_counts is None:
            self.recovery_reason_counts = {}
        if self.recovery_branch_counts is None:
            self.recovery_branch_counts = {}
        if self.recovery_strategy_counts is None:
            self.recovery_strategy_counts = {}
        if self.last_failed_strategy_by_reason is None:
            self.last_failed_strategy_by_reason = {}


@dataclass
class FallbackRuntimeConfig:
    overflow_fallback_retry_enabled: bool
    overflow_fallback_retry_max_attempts: int
    compaction_failure_recovery_enabled: bool
    compaction_failure_recovery_max_attempts: int
    truncation_recovery_enabled: bool
    truncation_recovery_max_attempts: int
    prompt_compaction_enabled: bool
    prompt_compaction_max_attempts: int
    prompt_compaction_ratio: float
    prompt_compaction_min_chars: int
    payload_truncation_enabled: bool
    payload_truncation_max_attempts: int
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
    recovery_backoff_enabled: bool
    recovery_backoff_base_ms: int
    recovery_backoff_max_ms: int
    recovery_backoff_multiplier: float
    recovery_backoff_jitter: bool


class FallbackState(Enum):
    INIT = "init"
    SELECT_MODEL = "select_model"
    EXECUTE_ATTEMPT = "execute_attempt"
    HANDLE_SUCCESS = "handle_success"
    HANDLE_FAILURE = "handle_failure"
    FINALIZE_FAILURE = "finalize_failure"


class FallbackStateMachine:
    def __init__(
        self,
        *,
        hooks: FallbackHooks,
        route: ModelRouteDecision,
        runtime: str,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        tool_policy: ToolPolicyDict | None,
        prompt_mode: str | None,
        should_steer_interrupt: Callable[[], bool] | None,
        max_attempts: int,
        config: FallbackRuntimeConfig,
    ) -> None:
        self._hooks = hooks
        self._route = route
        self._runtime = runtime
        self._send_event = send_event
        self._session_id = session_id
        self._request_id = request_id
        self._tool_policy = tool_policy
        self._prompt_mode = prompt_mode
        self._should_steer_interrupt = should_steer_interrupt
        self._models = [route.primary_model, *route.fallback_models]
        self._config = config
        self._state = FallbackState.INIT
        self._current_model_index = 0
        self._current_candidate_model = self._models[0]
        self._current_result = ""
        self._current_exception: LlmClientError | None = None
        self._attempt = FallbackAttemptState(
            attempts=0,
            max_attempts=max(1, int(max_attempts)),
            current_user_message=user_message,
        )

    async def run(self) -> str:
        while True:
            if self._state == FallbackState.INIT:
                self._state = FallbackState.SELECT_MODEL
                continue

            if self._state == FallbackState.SELECT_MODEL:
                if self._attempt.attempts >= self._attempt.max_attempts:
                    await self._emit_recovery_summary(
                        final_outcome="failure",
                        final_model=self._models[min(self._current_model_index, len(self._models) - 1)],
                        final_reason=self._attempt.last_reason,
                    )
                    await self._send_event(
                        build_lifecycle_event(
                            request_id=self._request_id,
                            session_id=self._session_id,
                            stage="model_fallback_retry_limit_reached",
                            details={
                                "attempts": self._attempt.attempts,
                                "max_attempts": self._attempt.max_attempts,
                                "last_reason": self._attempt.last_reason,
                            },
                            agent=self._hooks.agent.name,
                        )
                    )
                    self._state = FallbackState.FINALIZE_FAILURE
                    continue

                if self._current_model_index >= len(self._models):
                    self._state = FallbackState.FINALIZE_FAILURE
                    continue

                self._current_candidate_model = self._models[self._current_model_index]
                self._state = FallbackState.EXECUTE_ATTEMPT
                continue

            if self._state == FallbackState.EXECUTE_ATTEMPT:
                try:
                    self._attempt.attempts += 1
                    if self._current_model_index > 0:
                        await self._send_event(
                            {
                                "type": "status",
                                "agent": self._hooks.agent.name,
                                "message": f"Retrying with fallback model '{self._current_candidate_model}'.",
                            }
                        )
                        await self._send_event(
                            build_lifecycle_event(
                                request_id=self._request_id,
                                session_id=self._session_id,
                                stage=LifecycleStage.MODEL_FALLBACK_RETRY,
                                details={
                                    "to": self._current_candidate_model,
                                    "reason": self._attempt.last_reason,
                                    "attempt": self._attempt.attempts,
                                    "max_attempts": self._attempt.max_attempts,
                                },
                                agent=self._hooks.agent.name,
                            )
                        )

                    self._current_result = await self._hooks.agent.run(
                        user_message=self._attempt.current_user_message,
                        send_event=self._send_event,
                        session_id=self._session_id,
                        request_id=self._request_id,
                        model=self._current_candidate_model,
                        tool_policy=self._tool_policy,
                        prompt_mode=self._prompt_mode,
                        should_steer_interrupt=self._should_steer_interrupt,
                    )
                    self._state = FallbackState.HANDLE_SUCCESS
                    continue
                except LlmClientError as exc:
                    self._current_exception = exc
                    self._state = FallbackState.HANDLE_FAILURE
                    continue

            if self._state == FallbackState.HANDLE_SUCCESS:
                if self._attempt.pending_recovery_outcome is not None:
                    model_id, recorded_reason, recorded_strategy = self._attempt.pending_recovery_outcome
                    self._hooks._record_recovery_metric(
                        model_id=model_id,
                        reason=recorded_reason,
                        strategy=recorded_strategy,
                        outcome="success",
                    )
                    self._attempt.pending_recovery_outcome = None
                await self._emit_recovery_summary(
                    final_outcome="success",
                    final_model=self._current_candidate_model,
                    final_reason=self._attempt.last_reason,
                )
                return self._current_result

            if self._state == FallbackState.HANDLE_FAILURE:
                assert self._current_exception is not None
                if self._attempt.pending_recovery_outcome is not None:
                    model_id, recorded_reason, recorded_strategy = self._attempt.pending_recovery_outcome
                    self._hooks._record_recovery_metric(
                        model_id=model_id,
                        reason=recorded_reason,
                        strategy=recorded_strategy,
                        outcome="failure",
                    )
                    self._attempt.pending_recovery_outcome = None

                self._attempt.last_error = self._current_exception
                reason = self._hooks._classify_failover_reason(str(self._current_exception))
                self._attempt.last_reason = reason
                if reason == self._attempt.previous_reason:
                    self._attempt.reason_streak += 1
                else:
                    self._attempt.reason_streak = 1
                    self._attempt.previous_reason = reason

                has_fallback = self._current_model_index < len(self._models) - 1
                retryable = self._hooks._is_retryable_failover_reason(reason)
                recovery_branch = self._hooks._resolve_recovery_branch(reason)

                recovery_resolution = self._hooks._resolve_recovery_strategy(
                    ctx=RecoveryContext(
                        reason=reason,
                        runtime=self._runtime,
                        candidate_model=self._current_candidate_model,
                        has_fallback=has_fallback,
                        reason_streak=self._attempt.reason_streak,
                        current_user_message=self._attempt.current_user_message,
                        retryable=retryable,
                        recovery_branch=recovery_branch,
                        overflow_fallback_retry_enabled=self._config.overflow_fallback_retry_enabled,
                        overflow_fallback_retry_max_attempts=self._config.overflow_fallback_retry_max_attempts,
                        overflow_fallback_retry_attempts=self._attempt.overflow_fallback_retry_attempts,
                        compaction_failure_recovery_enabled=self._config.compaction_failure_recovery_enabled,
                        compaction_failure_recovery_max_attempts=self._config.compaction_failure_recovery_max_attempts,
                        compaction_failure_recovery_attempts=self._attempt.compaction_failure_recovery_attempts,
                        truncation_recovery_enabled=self._config.truncation_recovery_enabled,
                        truncation_recovery_max_attempts=self._config.truncation_recovery_max_attempts,
                        truncation_recovery_attempts=self._attempt.truncation_recovery_attempts,
                        prompt_compaction_enabled=self._config.prompt_compaction_enabled,
                        prompt_compaction_max_attempts=self._config.prompt_compaction_max_attempts,
                        prompt_compaction_attempts=self._attempt.prompt_compaction_attempts,
                        prompt_compaction_ratio=self._config.prompt_compaction_ratio,
                        prompt_compaction_min_chars=self._config.prompt_compaction_min_chars,
                        payload_truncation_enabled=self._config.payload_truncation_enabled,
                        payload_truncation_max_attempts=self._config.payload_truncation_max_attempts,
                        payload_truncation_attempts=self._attempt.payload_truncation_attempts,
                        payload_truncation_target_chars=self._config.payload_truncation_target_chars,
                        payload_truncation_min_chars=self._config.payload_truncation_min_chars,
                        recovery_priority_flip_enabled=self._config.recovery_priority_flip_enabled,
                        recovery_priority_flip_threshold=self._config.recovery_priority_flip_threshold,
                        signal_priority_enabled=self._config.signal_priority_enabled,
                        signal_low_health_threshold=self._config.signal_low_health_threshold,
                        signal_high_latency_ms=self._config.signal_high_latency_ms,
                        signal_high_cost_threshold=self._config.signal_high_cost_threshold,
                        strategy_feedback_enabled=self._config.strategy_feedback_enabled,
                        persistent_priority_enabled=self._config.persistent_priority_enabled,
                        persistent_priority_min_samples=self._config.persistent_priority_min_samples,
                        last_failed_strategy_by_reason=self._attempt.last_failed_strategy_by_reason or {},
                        health_score=float(self._route.profile.health_score or 0.0),
                        expected_latency_ms=int(self._route.profile.expected_latency_ms or 0),
                        cost_score=float(self._route.profile.cost_score or 0.0),
                    )
                )

                retryable = recovery_resolution.retryable
                recovery_branch = recovery_resolution.recovery_branch
                recovery_strategy = recovery_resolution.recovery_strategy
                self._attempt.current_user_message = recovery_resolution.current_user_message
                self._attempt.overflow_fallback_retry_attempts = recovery_resolution.overflow_fallback_retry_attempts
                self._attempt.compaction_failure_recovery_attempts = recovery_resolution.compaction_failure_recovery_attempts
                self._attempt.truncation_recovery_attempts = recovery_resolution.truncation_recovery_attempts
                self._attempt.prompt_compaction_attempts = recovery_resolution.prompt_compaction_attempts
                self._attempt.payload_truncation_attempts = recovery_resolution.payload_truncation_attempts

                self._attempt.recovery_failures_total += 1
                assert self._attempt.recovery_reason_counts is not None
                assert self._attempt.recovery_branch_counts is not None
                assert self._attempt.recovery_strategy_counts is not None
                assert self._attempt.last_failed_strategy_by_reason is not None
                self._attempt.recovery_reason_counts[reason] = int(self._attempt.recovery_reason_counts.get(reason, 0) or 0) + 1
                self._attempt.recovery_branch_counts[recovery_branch] = int(self._attempt.recovery_branch_counts.get(recovery_branch, 0) or 0) + 1
                if ":" in recovery_strategy:
                    strategy_name = recovery_strategy.split(":", 1)[1]
                    self._attempt.recovery_strategy_counts[strategy_name] = int(self._attempt.recovery_strategy_counts.get(strategy_name, 0) or 0) + 1
                    self._attempt.recovery_strategy_applied_total += 1
                    self._attempt.last_failed_strategy_by_reason[reason] = strategy_name
                    if retryable and has_fallback:
                        self._attempt.pending_recovery_outcome = (self._current_candidate_model, reason, strategy_name)

                if recovery_resolution.signal_priority_applied:
                    self._attempt.recovery_signal_priority_applied_total += 1
                else:
                    self._increment_priority_not_applied_bucket(
                        prefix="recovery_signal_priority",
                        reason=recovery_resolution.signal_priority_reason,
                    )
                if recovery_resolution.strategy_feedback_applied:
                    self._attempt.recovery_strategy_feedback_applied_total += 1
                else:
                    self._increment_priority_not_applied_bucket(
                        prefix="recovery_strategy_feedback",
                        reason=recovery_resolution.strategy_feedback_reason,
                    )
                if recovery_resolution.persistent_priority_applied:
                    self._attempt.recovery_persistent_priority_applied_total += 1
                else:
                    self._increment_priority_not_applied_bucket(
                        prefix="recovery_persistent_priority",
                        reason=recovery_resolution.persistent_priority_reason,
                    )
                if recovery_resolution.overflow_retry_applied:
                    self._attempt.recovery_overflow_retry_applied_total += 1
                if recovery_resolution.compaction_recovery_applied:
                    self._attempt.recovery_compaction_recovery_applied_total += 1
                if recovery_resolution.truncation_recovery_applied:
                    self._attempt.recovery_truncation_recovery_applied_total += 1
                if recovery_resolution.prompt_compaction_applied:
                    self._attempt.recovery_prompt_compaction_applied_total += 1
                if recovery_resolution.payload_truncation_applied:
                    self._attempt.recovery_payload_truncation_applied_total += 1

                await self._send_event(
                    build_lifecycle_event(
                        request_id=self._request_id,
                        session_id=self._session_id,
                        stage="model_fallback_classified",
                        details={
                            "model": self._current_candidate_model,
                            "reason": reason,
                            "reason_class": self._reason_class(reason),
                            "retry_policy": self._retry_policy_label(retryable),
                            "retryable": retryable,
                            "has_fallback": has_fallback,
                        },
                        agent=self._hooks.agent.name,
                    )
                )

                await self._send_event(
                    build_lifecycle_event(
                        request_id=self._request_id,
                        session_id=self._session_id,
                        stage="model_recovery_branch_selected",
                        details={
                            "model": self._current_candidate_model,
                            "reason": reason,
                            "branch": recovery_branch,
                            "retryable": retryable,
                            "has_fallback": has_fallback,
                            "overflow_retry_applied": recovery_resolution.overflow_retry_applied,
                            "overflow_retry_attempts": self._attempt.overflow_fallback_retry_attempts,
                            "overflow_retry_max_attempts": self._config.overflow_fallback_retry_max_attempts,
                            "compaction_recovery_applied": recovery_resolution.compaction_recovery_applied,
                            "compaction_recovery_attempts": self._attempt.compaction_failure_recovery_attempts,
                            "compaction_recovery_max_attempts": self._config.compaction_failure_recovery_max_attempts,
                            "truncation_recovery_applied": recovery_resolution.truncation_recovery_applied,
                            "truncation_recovery_attempts": self._attempt.truncation_recovery_attempts,
                            "truncation_recovery_max_attempts": self._config.truncation_recovery_max_attempts,
                            "prompt_compaction_applied": recovery_resolution.prompt_compaction_applied,
                            "prompt_compaction_attempts": self._attempt.prompt_compaction_attempts,
                            "prompt_compaction_max_attempts": self._config.prompt_compaction_max_attempts,
                            "prompt_compaction_previous_chars": recovery_resolution.prompt_compaction_previous_chars,
                            "prompt_compaction_new_chars": recovery_resolution.prompt_compaction_new_chars,
                            "payload_truncation_applied": recovery_resolution.payload_truncation_applied,
                            "payload_truncation_attempts": self._attempt.payload_truncation_attempts,
                            "payload_truncation_max_attempts": self._config.payload_truncation_max_attempts,
                            "payload_truncation_previous_chars": recovery_resolution.payload_truncation_previous_chars,
                            "payload_truncation_new_chars": recovery_resolution.payload_truncation_new_chars,
                            "recovery_strategy": recovery_strategy,
                            "reason_streak": self._attempt.reason_streak,
                            "recovery_priority_overridden": recovery_resolution.recovery_priority_overridden,
                            "signal_priority_applied": recovery_resolution.signal_priority_applied,
                            "signal_priority_reason": recovery_resolution.signal_priority_reason,
                            "strategy_feedback_applied": recovery_resolution.strategy_feedback_applied,
                            "strategy_feedback_reason": recovery_resolution.strategy_feedback_reason,
                            "persistent_priority_applied": recovery_resolution.persistent_priority_applied,
                            "persistent_priority_reason": recovery_resolution.persistent_priority_reason,
                        },
                        agent=self._hooks.agent.name,
                    )
                )

                await self._send_event(
                    build_lifecycle_event(
                        request_id=self._request_id,
                        session_id=self._session_id,
                        stage="model_recovery_action",
                        details={
                            "model": self._current_candidate_model,
                            "reason": reason,
                            "branch": recovery_branch,
                            "action": "retry_fallback" if (retryable and has_fallback) else "fail_fast",
                            "overflow_retry_applied": recovery_resolution.overflow_retry_applied,
                            "compaction_recovery_applied": recovery_resolution.compaction_recovery_applied,
                            "truncation_recovery_applied": recovery_resolution.truncation_recovery_applied,
                            "prompt_compaction_applied": recovery_resolution.prompt_compaction_applied,
                            "payload_truncation_applied": recovery_resolution.payload_truncation_applied,
                            "recovery_strategy": recovery_strategy,
                            "reason_streak": self._attempt.reason_streak,
                            "recovery_priority_overridden": recovery_resolution.recovery_priority_overridden,
                            "signal_priority_applied": recovery_resolution.signal_priority_applied,
                            "signal_priority_reason": recovery_resolution.signal_priority_reason,
                            "strategy_feedback_applied": recovery_resolution.strategy_feedback_applied,
                            "strategy_feedback_reason": recovery_resolution.strategy_feedback_reason,
                            "persistent_priority_applied": recovery_resolution.persistent_priority_applied,
                            "persistent_priority_reason": recovery_resolution.persistent_priority_reason,
                        },
                        agent=self._hooks.agent.name,
                    )
                )

                if recovery_resolution.prompt_compaction_applied or recovery_resolution.payload_truncation_applied:
                    transform_type = "prompt_compaction" if recovery_resolution.prompt_compaction_applied else "payload_truncation"
                    previous_chars = (
                        recovery_resolution.prompt_compaction_previous_chars
                        if recovery_resolution.prompt_compaction_applied
                        else recovery_resolution.payload_truncation_previous_chars
                    )
                    new_chars = (
                        recovery_resolution.prompt_compaction_new_chars
                        if recovery_resolution.prompt_compaction_applied
                        else recovery_resolution.payload_truncation_new_chars
                    )
                    chars_reduced = max(0, int(previous_chars) - int(new_chars))
                    await self._send_event(
                        build_lifecycle_event(
                            request_id=self._request_id,
                            session_id=self._session_id,
                            stage="model_recovery_transform_applied",
                            details={
                                "model": self._current_candidate_model,
                                "reason": reason,
                                "reason_class": self._reason_class(reason),
                                "transform_type": transform_type,
                                "previous_chars": int(previous_chars),
                                "new_chars": int(new_chars),
                                "chars_reduced": chars_reduced,
                                "recovery_strategy": recovery_strategy,
                            },
                            agent=self._hooks.agent.name,
                        )
                    )

                if self._current_model_index >= len(self._models) - 1:
                    await self._emit_recovery_summary(
                        final_outcome="failure",
                        final_model=self._current_candidate_model,
                        final_reason=reason,
                    )
                    await self._send_event(
                        build_lifecycle_event(
                            request_id=self._request_id,
                            session_id=self._session_id,
                            stage="model_fallback_exhausted",
                            details={
                                "model": self._current_candidate_model,
                                "reason": reason,
                            },
                            agent=self._hooks.agent.name,
                        )
                    )
                    self._state = FallbackState.FINALIZE_FAILURE
                    continue

                if not retryable:
                    await self._emit_recovery_summary(
                        final_outcome="failure",
                        final_model=self._current_candidate_model,
                        final_reason=reason,
                    )
                    await self._send_event(
                        build_lifecycle_event(
                            request_id=self._request_id,
                            session_id=self._session_id,
                            stage="model_fallback_not_retryable",
                            details={
                                "model": self._current_candidate_model,
                                "reason": reason,
                            },
                            agent=self._hooks.agent.name,
                        )
                    )
                    self._state = FallbackState.FINALIZE_FAILURE
                    continue

                if self._config.recovery_backoff_enabled:
                    delay_seconds = self._compute_retry_backoff_seconds(
                        attempt_index=self._attempt.attempts,
                        base_ms=self._config.recovery_backoff_base_ms,
                        max_ms=self._config.recovery_backoff_max_ms,
                        multiplier=self._config.recovery_backoff_multiplier,
                    )
                    if self._config.recovery_backoff_jitter and delay_seconds > 0:
                        delay_seconds = delay_seconds * random.uniform(0.8, 1.2)
                    delay_ms = max(0, int(delay_seconds * 1000))
                    await self._send_event(
                        build_lifecycle_event(
                            request_id=self._request_id,
                            session_id=self._session_id,
                            stage="model_recovery_backoff",
                            details={
                                "model": self._current_candidate_model,
                                "reason": reason,
                                "reason_class": self._reason_class(reason),
                                "delay_ms": delay_ms,
                                "attempt": self._attempt.attempts,
                                "max_attempts": self._attempt.max_attempts,
                            },
                            agent=self._hooks.agent.name,
                        )
                    )
                    if delay_seconds > 0:
                        await asyncio.sleep(delay_seconds)

                self._current_model_index += 1
                self._state = FallbackState.SELECT_MODEL
                continue

            if self._state == FallbackState.FINALIZE_FAILURE:
                if isinstance(self._attempt.last_error, LlmClientError):
                    raise self._attempt.last_error
                raise LlmClientError("Model routing failed before execution.")

    async def _emit_recovery_summary(self, *, final_outcome: str, final_model: str, final_reason: str) -> None:
        await self._hooks._emit_recovery_summary_event(
            send_event=self._send_event,
            request_id=self._request_id,
            session_id=self._session_id,
            attempts=self._attempt.attempts,
            max_attempts=self._attempt.max_attempts,
            recovery_failures_total=self._attempt.recovery_failures_total,
            recovery_reason_counts=self._attempt.recovery_reason_counts or {},
            recovery_branch_counts=self._attempt.recovery_branch_counts or {},
            recovery_strategy_counts=self._attempt.recovery_strategy_counts or {},
            recovery_strategy_applied_total=self._attempt.recovery_strategy_applied_total,
            recovery_signal_priority_applied_total=self._attempt.recovery_signal_priority_applied_total,
            recovery_signal_priority_not_applied_disabled_total=self._attempt.recovery_signal_priority_not_applied_disabled_total,
            recovery_signal_priority_not_applied_not_applicable_total=self._attempt.recovery_signal_priority_not_applied_not_applicable_total,
            recovery_signal_priority_not_applied_no_reorder_total=self._attempt.recovery_signal_priority_not_applied_no_reorder_total,
            recovery_strategy_feedback_applied_total=self._attempt.recovery_strategy_feedback_applied_total,
            recovery_strategy_feedback_not_applied_disabled_total=self._attempt.recovery_strategy_feedback_not_applied_disabled_total,
            recovery_strategy_feedback_not_applied_not_applicable_total=self._attempt.recovery_strategy_feedback_not_applied_not_applicable_total,
            recovery_strategy_feedback_not_applied_no_reorder_total=self._attempt.recovery_strategy_feedback_not_applied_no_reorder_total,
            recovery_persistent_priority_applied_total=self._attempt.recovery_persistent_priority_applied_total,
            recovery_persistent_priority_not_applied_disabled_total=self._attempt.recovery_persistent_priority_not_applied_disabled_total,
            recovery_persistent_priority_not_applied_not_applicable_total=self._attempt.recovery_persistent_priority_not_applied_not_applicable_total,
            recovery_persistent_priority_not_applied_no_reorder_total=self._attempt.recovery_persistent_priority_not_applied_no_reorder_total,
            recovery_overflow_retry_applied_total=self._attempt.recovery_overflow_retry_applied_total,
            recovery_compaction_recovery_applied_total=self._attempt.recovery_compaction_recovery_applied_total,
            recovery_truncation_recovery_applied_total=self._attempt.recovery_truncation_recovery_applied_total,
            recovery_prompt_compaction_applied_total=self._attempt.recovery_prompt_compaction_applied_total,
            recovery_payload_truncation_applied_total=self._attempt.recovery_payload_truncation_applied_total,
            final_outcome=final_outcome,
            final_model=final_model,
            final_reason=final_reason,
        )

    def _increment_priority_not_applied_bucket(self, *, prefix: str, reason: str) -> None:
        normalized_reason = (reason or "").strip().lower()
        if normalized_reason == "disabled":
            bucket = "disabled"
        elif normalized_reason == "not_applicable":
            bucket = "not_applicable"
        else:
            bucket = "no_reorder"

        field_name = f"{prefix}_not_applied_{bucket}_total"
        current = int(getattr(self._attempt, field_name, 0) or 0)
        setattr(self._attempt, field_name, current + 1)

    @staticmethod
    def _reason_class(reason: str) -> str:
        normalized = (reason or "").strip().lower()
        if normalized in {"rate_limited", "timeout", "temporary_unavailable", "network_error"}:
            return "transient"
        if normalized in {"context_overflow", "truncation_required", "compaction_failure"}:
            return "capacity"
        if normalized == "model_not_found":
            return "configuration"
        return "unknown"

    @staticmethod
    def _retry_policy_label(retryable: bool) -> str:
        return "bounded_retry" if retryable else "fail_fast"

    @staticmethod
    def _compute_retry_backoff_seconds(*, attempt_index: int, base_ms: int, max_ms: int, multiplier: float) -> float:
        bounded_attempt = max(1, int(attempt_index))
        bounded_base = max(0, int(base_ms))
        bounded_max = max(bounded_base, int(max_ms))
        bounded_multiplier = max(1.0, float(multiplier))

        delay_ms = float(bounded_base) * (bounded_multiplier ** max(0, bounded_attempt - 1))
        return max(0.0, min(delay_ms, float(bounded_max)) / 1000.0)