from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.contracts.agent_contract import AgentContract, SendEvent
from app.errors import GuardrailViolation
from app.model_routing import ModelRouter
from app.model_routing.context_window_guard import evaluate_context_window_guard
from app.model_routing.router import ModelRouteDecision
from app.orchestration.events import LifecycleStage, build_lifecycle_event
from app.orchestration.fallback_state_machine import FallbackRuntimeConfig, FallbackStateMachine
from app.orchestration.recovery_strategy import (
    PriorityRecoveryMetadata,
    RecoveryContext,
    RecoveryStrategyResolution,
    RecoveryStrategyResolver,
)
from app.orchestration.step_types import PipelineStep
from app.services.circuit_breaker import CircuitBreakerRegistry
from app.services.model_health_tracker import ModelHealthTracker
from app.state import StateStore
from app.tool_policy import ToolPolicyDict

RecoveryPriorityResolution = tuple[tuple[str, ...], bool, bool, str, bool, bool]

FAILOVER_REASON_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "context_overflow",
        (
            "context overflow",
            "context window",
            "too large for the model",
            "maximum context length",
            "prompt too long",
        ),
    ),
    ("truncation_required", ("truncat", "truncated", "token limit", "max tokens")),
    (
        "role_ordering",
        (
            "roles must alternate",
            "incorrect role information",
            "role ordering",
        ),
    ),
    ("model_not_found", ("model", "not found")),
    ("rate_limited", ("rate limit", "too many requests", "429")),
    ("timeout", ("timeout", "timed out")),
    ("temporary_unavailable", ("temporarily unavailable", "service unavailable", "503")),
    ("network_error", ("connection", "network", "dns")),
    (
        "resource_exhausted",
        (
            "requires more system memory",
            "out of memory",
            "insufficient memory",
            "not enough memory",
            "cuda out of memory",
            "gpu memory",
        ),
    ),
)

NON_RETRYABLE_FAIL_FAST_BRANCH_BY_REASON: dict[str, str] = {
    "context_overflow": "fail_fast_context_overflow",
    "compaction_failure": "fail_fast_compaction_failure",
    "truncation_required": "fail_fast_truncation_required",
}


@dataclass(frozen=True)
class AdaptiveInferenceResolution:
    route: ModelRouteDecision
    degraded: bool
    reason: str
    selected_model: str
    requested_model: str
    cost_budget_max: float
    latency_budget_ms: int


class PipelineRunner:
    def __init__(
        self,
        agent: AgentContract,
        state_store: StateStore,
        health_tracker: ModelHealthTracker | None = None,
        circuit_breaker: CircuitBreakerRegistry | None = None,
    ):
        self.agent = agent
        self.state_store = state_store
        self._health_tracker = health_tracker
        self._circuit_breaker = circuit_breaker
        self.model_router = ModelRouter(health_tracker=health_tracker)
        self._recovery_metrics_file = Path(self.state_store.persist_dir) / "pipeline_recovery_metrics.json"
        self._recovery_metrics = self._load_recovery_metrics()
        self._recovery_strategy_resolver = RecoveryStrategyResolver(self)

    async def run(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        runtime: str,
        model: str | None = None,
        reasoning_level: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        prompt_mode: str | None = None,
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        for step in (PipelineStep.PLAN, PipelineStep.TOOL_SELECT, PipelineStep.TOOL_EXECUTE, PipelineStep.SYNTHESIZE):
            self.state_store.set_task_status(
                run_id=request_id,
                task_id=str(step),
                label=str(step),
                status="pending",
            )

        self.state_store.set_task_status(
            run_id=request_id,
            task_id=str(PipelineStep.PLAN),
            label=str(PipelineStep.PLAN),
            status="active",
        )

        try:
            route: ModelRouteDecision = self.model_router.route(
                runtime=runtime,
                requested_model=model,
                reasoning_level=reasoning_level,
            )
        except TypeError as exc:
            if "reasoning_level" not in str(exc):
                raise
            route = self.model_router.route(runtime=runtime, requested_model=model)
        adaptive_resolution = self._resolve_adaptive_inference(
            route=route,
            runtime=runtime,
            reasoning_level=reasoning_level,
        )
        route = adaptive_resolution.route
        if adaptive_resolution.degraded:
            await send_event(
                build_lifecycle_event(
                    request_id=request_id,
                    session_id=session_id,
                    stage="inference_budget_degraded",
                    details={
                        "reason": adaptive_resolution.reason,
                        "selected_model": adaptive_resolution.selected_model,
                        "requested_model": adaptive_resolution.requested_model,
                        "cost_budget_max": adaptive_resolution.cost_budget_max,
                        "latency_budget_ms": adaptive_resolution.latency_budget_ms,
                        "reasoning_level": reasoning_level,
                    },
                    agent=self.agent.name,
                )
            )
        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage=LifecycleStage.MODEL_ROUTE_SELECTED,
                details={
                    "primary": route.primary_model,
                    "fallbacks": route.fallback_models,
                    "reasoning_level": reasoning_level,
                    "adaptive_inference_enabled": bool(settings.adaptive_inference_enabled),
                    "max_context": route.profile.max_context,
                    "reasoning_depth": route.profile.reasoning_depth,
                    "health_score": route.profile.health_score,
                    "expected_latency_ms": route.profile.expected_latency_ms,
                    "cost_score": route.profile.cost_score,
                    "scores": route.scores,
                },
                agent=self.agent.name,
            )
        )

        if settings.context_window_guard_enabled:
            guard = evaluate_context_window_guard(
                tokens=route.profile.max_context,
                warn_below_tokens=settings.context_window_warn_below_tokens,
                hard_min_tokens=settings.context_window_hard_min_tokens,
            )
            if guard.should_warn:
                await send_event(
                    build_lifecycle_event(
                        request_id=request_id,
                        session_id=session_id,
                        stage="context_window_warn",
                        details={
                            "model": route.primary_model,
                            "tokens": guard.tokens,
                            "warn_below_tokens": settings.context_window_warn_below_tokens,
                            "hard_min_tokens": settings.context_window_hard_min_tokens,
                        },
                        agent=self.agent.name,
                    )
                )
            if guard.should_block:
                await send_event(
                    build_lifecycle_event(
                        request_id=request_id,
                        session_id=session_id,
                        stage="context_window_blocked",
                        details={
                            "model": route.primary_model,
                            "tokens": guard.tokens,
                            "warn_below_tokens": settings.context_window_warn_below_tokens,
                            "hard_min_tokens": settings.context_window_hard_min_tokens,
                        },
                        agent=self.agent.name,
                    )
                )
                raise GuardrailViolation(
                    f"Model context window too small ({guard.tokens} tokens, min {settings.context_window_hard_min_tokens})."
                )

        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage="terminal_wait_started",
                details={
                    "scope": "pipeline",
                    "reason": "await_agent_terminal_state",
                },
                agent=self.agent.name,
            )
        )

        try:
            final_text = await self._run_with_fallback(
                user_message=user_message,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                runtime=runtime,
                route=route,
                tool_policy=tool_policy,
                prompt_mode=prompt_mode,
                should_steer_interrupt=should_steer_interrupt,
            )
        except Exception:
            for step in (PipelineStep.PLAN, PipelineStep.TOOL_SELECT, PipelineStep.TOOL_EXECUTE, PipelineStep.SYNTHESIZE):
                with contextlib.suppress(Exception):
                    self.state_store.set_task_status(
                        run_id=request_id,
                        task_id=str(step),
                        label=str(step),
                        status="failed",
                    )
            raise

        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage="terminal_wait_completed",
                details={
                    "scope": "pipeline",
                    "terminal_stage": "agent_run_completed",
                },
                agent=self.agent.name,
            )
        )

        for step in (PipelineStep.PLAN, PipelineStep.TOOL_SELECT, PipelineStep.TOOL_EXECUTE, PipelineStep.SYNTHESIZE):
            self.state_store.set_task_status(
                run_id=request_id,
                task_id=str(step),
                label=str(step),
                status="completed",
            )

        return final_text

    def _resolve_adaptive_inference(
        self,
        *,
        route: ModelRouteDecision,
        runtime: str,
        reasoning_level: str | None,
    ) -> AdaptiveInferenceResolution:
        _ = runtime
        cost_budget_max = max(0.0, min(1.0, float(settings.adaptive_inference_cost_budget_max)))
        latency_budget_ms = max(1, int(settings.adaptive_inference_latency_budget_ms))
        selected_profile = route.profile
        selected_model = route.primary_model

        if not bool(settings.adaptive_inference_enabled):
            return AdaptiveInferenceResolution(
                route=route,
                degraded=False,
                reason="adaptive_inference_disabled",
                selected_model=selected_model,
                requested_model=route.primary_model,
                cost_budget_max=cost_budget_max,
                latency_budget_ms=latency_budget_ms,
            )

        normalized_reasoning = str(reasoning_level or "").strip().lower()
        if normalized_reasoning in {"high", "ultrathink"}:
            effective_cost_budget_max = min(1.0, cost_budget_max + 0.15)
            effective_latency_budget_ms = int(latency_budget_ms * 1.25)
        elif normalized_reasoning == "low":
            effective_cost_budget_max = max(0.1, cost_budget_max - 0.15)
            effective_latency_budget_ms = max(200, int(latency_budget_ms * 0.75))
        else:
            effective_cost_budget_max = cost_budget_max
            effective_latency_budget_ms = latency_budget_ms

        is_within_budget = (
            float(selected_profile.cost_score) <= effective_cost_budget_max
            and int(selected_profile.expected_latency_ms) <= effective_latency_budget_ms
        )
        if is_within_budget:
            return AdaptiveInferenceResolution(
                route=route,
                degraded=False,
                reason="within_budget",
                selected_model=selected_model,
                requested_model=route.primary_model,
                cost_budget_max=effective_cost_budget_max,
                latency_budget_ms=effective_latency_budget_ms,
            )

        candidates = [route.primary_model, *route.fallback_models]
        budget_candidates: list[tuple[str, float]] = []
        for candidate in candidates:
            profile = self.model_router.registry.resolve(candidate)
            if (
                float(profile.cost_score) <= effective_cost_budget_max
                and int(profile.expected_latency_ms) <= effective_latency_budget_ms
            ):
                budget_candidates.append((candidate, route.scores.get(candidate, float("-inf"))))

        if budget_candidates:
            budget_candidates.sort(key=lambda item: item[1], reverse=True)
            selected_model = budget_candidates[0][0]
            reason = "budget_compliant_candidate"
        else:
            fallback_rank = sorted(
                candidates,
                key=lambda candidate: (
                    self.model_router.registry.resolve(candidate).cost_score,
                    self.model_router.registry.resolve(candidate).expected_latency_ms,
                ),
            )
            selected_model = fallback_rank[0]
            reason = "graceful_degradation_lowest_cost"

        if selected_model == route.primary_model:
            return AdaptiveInferenceResolution(
                route=route,
                degraded=False,
                reason="primary_retained",
                selected_model=selected_model,
                requested_model=route.primary_model,
                cost_budget_max=effective_cost_budget_max,
                latency_budget_ms=effective_latency_budget_ms,
            )

        selected_profile = self.model_router.registry.resolve(selected_model)
        selected_fallbacks = [item for item in candidates if item != selected_model]
        adapted_route = ModelRouteDecision(
            primary_model=selected_model,
            fallback_models=selected_fallbacks,
            profile=selected_profile,
            scores=route.scores,
        )
        return AdaptiveInferenceResolution(
            route=adapted_route,
            degraded=True,
            reason=reason,
            selected_model=selected_model,
            requested_model=route.primary_model,
            cost_budget_max=effective_cost_budget_max,
            latency_budget_ms=effective_latency_budget_ms,
        )

    async def _run_with_fallback(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        runtime: str,
        route: ModelRouteDecision,
        tool_policy: ToolPolicyDict | None,
        prompt_mode: str | None,
        should_steer_interrupt: Callable[[], bool] | None,
    ) -> str:
        max_attempts = max(1, int(settings.pipeline_runner_max_attempts))
        machine = FallbackStateMachine(
            hooks=self,
            route=route,
            runtime=runtime,
            user_message=user_message,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            tool_policy=tool_policy,
            prompt_mode=prompt_mode,
            should_steer_interrupt=should_steer_interrupt,
            max_attempts=max_attempts,
            config=FallbackRuntimeConfig(
                overflow_fallback_retry_enabled=bool(settings.pipeline_runner_context_overflow_fallback_retry_enabled),
                overflow_fallback_retry_max_attempts=max(
                    0,
                    int(settings.pipeline_runner_context_overflow_fallback_retry_max_attempts),
                ),
                compaction_failure_recovery_enabled=bool(settings.pipeline_runner_compaction_failure_recovery_enabled),
                compaction_failure_recovery_max_attempts=max(
                    0,
                    int(settings.pipeline_runner_compaction_failure_recovery_max_attempts),
                ),
                truncation_recovery_enabled=bool(settings.pipeline_runner_truncation_recovery_enabled),
                truncation_recovery_max_attempts=max(
                    0,
                    int(settings.pipeline_runner_truncation_recovery_max_attempts),
                ),
                prompt_compaction_enabled=bool(settings.pipeline_runner_prompt_compaction_enabled),
                prompt_compaction_max_attempts=max(
                    0,
                    int(settings.pipeline_runner_prompt_compaction_max_attempts),
                ),
                prompt_compaction_ratio=float(settings.pipeline_runner_prompt_compaction_ratio),
                prompt_compaction_min_chars=max(
                    64,
                    int(settings.pipeline_runner_prompt_compaction_min_chars),
                ),
                payload_truncation_enabled=bool(settings.pipeline_runner_payload_truncation_enabled),
                payload_truncation_max_attempts=max(
                    0,
                    int(settings.pipeline_runner_payload_truncation_max_attempts),
                ),
                payload_truncation_target_chars=max(
                    64,
                    int(settings.pipeline_runner_payload_truncation_target_chars),
                ),
                payload_truncation_min_chars=max(
                    32,
                    int(settings.pipeline_runner_payload_truncation_min_chars),
                ),
                recovery_priority_flip_enabled=bool(settings.pipeline_runner_recovery_priority_flip_enabled),
                recovery_priority_flip_threshold=max(
                    2,
                    int(settings.pipeline_runner_recovery_priority_flip_threshold),
                ),
                signal_priority_enabled=bool(settings.pipeline_runner_signal_priority_enabled),
                signal_low_health_threshold=float(settings.pipeline_runner_signal_low_health_threshold),
                signal_high_latency_ms=max(
                    1,
                    int(settings.pipeline_runner_signal_high_latency_ms),
                ),
                signal_high_cost_threshold=float(settings.pipeline_runner_signal_high_cost_threshold),
                strategy_feedback_enabled=bool(settings.pipeline_runner_strategy_feedback_enabled),
                persistent_priority_enabled=bool(settings.pipeline_runner_persistent_priority_enabled),
                persistent_priority_min_samples=max(
                    1,
                    int(settings.pipeline_runner_persistent_priority_min_samples),
                ),
                recovery_backoff_enabled=bool(settings.pipeline_runner_recovery_backoff_enabled),
                recovery_backoff_base_ms=max(0, int(settings.pipeline_runner_recovery_backoff_base_ms)),
                recovery_backoff_max_ms=max(
                    0,
                    int(settings.pipeline_runner_recovery_backoff_max_ms),
                ),
                recovery_backoff_multiplier=max(
                    1.0,
                    float(settings.pipeline_runner_recovery_backoff_multiplier),
                ),
                recovery_backoff_jitter=bool(settings.pipeline_runner_recovery_backoff_jitter),
            ),
            circuit_breaker=self._circuit_breaker,
            health_tracker=self._health_tracker,
        )
        return await machine.run()

    def _classify_failover_reason(self, message: str) -> str:
        text = (message or "").lower()
        if "compaction" in text and (
            "failed" in text
            or "timeout" in text
            or "timed out" in text
        ):
            return "compaction_failure"

        for reason, markers in FAILOVER_REASON_PATTERNS:
            if reason == "model_not_found":
                if "model" in text and "not found" in text:
                    return reason
                continue
            if any(marker in text for marker in markers):
                return reason
        return "unknown"

    def _is_retryable_failover_reason(self, reason: str) -> bool:
        return reason in {
            "model_not_found",
            "rate_limited",
            "timeout",
            "temporary_unavailable",
            "network_error",
            "role_ordering",
            "resource_exhausted",
        }

    def _resolve_recovery_branch(self, reason: str) -> str:
        fail_fast_branch = NON_RETRYABLE_FAIL_FAST_BRANCH_BY_REASON.get(reason)
        if fail_fast_branch:
            return fail_fast_branch
        if self._is_retryable_failover_reason(reason):
            return "retry_with_fallback"
        return "fail_fast_non_retryable"

    async def _emit_recovery_summary_event(
        self,
        *,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
        attempts: int,
        max_attempts: int,
        recovery_failures_total: int,
        recovery_reason_counts: dict[str, int],
        recovery_branch_counts: dict[str, int],
        recovery_strategy_counts: dict[str, int],
        recovery_strategy_applied_total: int,
        recovery_signal_priority_applied_total: int,
        recovery_signal_priority_not_applied_disabled_total: int,
        recovery_signal_priority_not_applied_not_applicable_total: int,
        recovery_signal_priority_not_applied_no_reorder_total: int,
        recovery_strategy_feedback_applied_total: int,
        recovery_strategy_feedback_not_applied_disabled_total: int,
        recovery_strategy_feedback_not_applied_not_applicable_total: int,
        recovery_strategy_feedback_not_applied_no_reorder_total: int,
        recovery_persistent_priority_applied_total: int,
        recovery_persistent_priority_not_applied_disabled_total: int,
        recovery_persistent_priority_not_applied_not_applicable_total: int,
        recovery_persistent_priority_not_applied_no_reorder_total: int,
        recovery_overflow_retry_applied_total: int,
        recovery_compaction_recovery_applied_total: int,
        recovery_truncation_recovery_applied_total: int,
        recovery_prompt_compaction_applied_total: int,
        recovery_payload_truncation_applied_total: int,
        final_outcome: str,
        final_model: str,
        final_reason: str,
    ) -> None:
        if recovery_failures_total <= 0:
            return

        normalized_final_outcome = (final_outcome or "").strip().lower()
        recovered_successfully = normalized_final_outcome == "success"
        terminal_reason = "recovered" if recovered_successfully else (final_reason or "unknown")

        signal_not_applied_total = (
            recovery_signal_priority_not_applied_disabled_total
            + recovery_signal_priority_not_applied_not_applicable_total
            + recovery_signal_priority_not_applied_no_reorder_total
        )
        strategy_feedback_not_applied_total = (
            recovery_strategy_feedback_not_applied_disabled_total
            + recovery_strategy_feedback_not_applied_not_applicable_total
            + recovery_strategy_feedback_not_applied_no_reorder_total
        )
        persistent_priority_not_applied_total = (
            recovery_persistent_priority_not_applied_disabled_total
            + recovery_persistent_priority_not_applied_not_applicable_total
            + recovery_persistent_priority_not_applied_no_reorder_total
        )

        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage="model_recovery_summary",
                details={
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "failures_total": recovery_failures_total,
                    "unique_reasons": len(recovery_reason_counts),
                    "reason_counts": recovery_reason_counts,
                    "branch_counts": recovery_branch_counts,
                    "strategy_counts": recovery_strategy_counts,
                    "recovery_strategy_applied_total": recovery_strategy_applied_total,
                    "signal_priority_applied_total": recovery_signal_priority_applied_total,
                    "signal_priority_applied_vs_not_applied": {
                        "applied": recovery_signal_priority_applied_total,
                        "not_applied": signal_not_applied_total,
                    },
                    "signal_priority_not_applied_breakdown": {
                        "disabled": recovery_signal_priority_not_applied_disabled_total,
                        "not_applicable": recovery_signal_priority_not_applied_not_applicable_total,
                        "no_reorder": recovery_signal_priority_not_applied_no_reorder_total,
                    },
                    "strategy_feedback_applied_total": recovery_strategy_feedback_applied_total,
                    "strategy_feedback_applied_vs_not_applied": {
                        "applied": recovery_strategy_feedback_applied_total,
                        "not_applied": strategy_feedback_not_applied_total,
                    },
                    "strategy_feedback_not_applied_breakdown": {
                        "disabled": recovery_strategy_feedback_not_applied_disabled_total,
                        "not_applicable": recovery_strategy_feedback_not_applied_not_applicable_total,
                        "no_reorder": recovery_strategy_feedback_not_applied_no_reorder_total,
                    },
                    "persistent_priority_applied_total": recovery_persistent_priority_applied_total,
                    "persistent_priority_applied_vs_not_applied": {
                        "applied": recovery_persistent_priority_applied_total,
                        "not_applied": persistent_priority_not_applied_total,
                    },
                    "persistent_priority_not_applied_breakdown": {
                        "disabled": recovery_persistent_priority_not_applied_disabled_total,
                        "not_applicable": recovery_persistent_priority_not_applied_not_applicable_total,
                        "no_reorder": recovery_persistent_priority_not_applied_no_reorder_total,
                    },
                    "overflow_retry_applied_total": recovery_overflow_retry_applied_total,
                    "compaction_recovery_applied_total": recovery_compaction_recovery_applied_total,
                    "truncation_recovery_applied_total": recovery_truncation_recovery_applied_total,
                    "prompt_compaction_applied_total": recovery_prompt_compaction_applied_total,
                    "payload_truncation_applied_total": recovery_payload_truncation_applied_total,
                    "final_outcome": final_outcome,
                    "final_model": final_model,
                    "final_reason": final_reason,
                    "recovered_successfully": recovered_successfully,
                    "terminal_reason": terminal_reason,
                },
                agent=self.agent.name,
            )
        )

    def _resolve_priority_recovery_metadata(self, *, ctx: RecoveryContext) -> PriorityRecoveryMetadata:
        (
            priority_steps,
            recovery_priority_overridden,
            persistent_priority_applied,
            persistent_priority_reason,
            signal_priority_applied,
            strategy_feedback_applied,
        ) = self._resolve_recovery_priority_steps(
            reason=ctx.reason,
            runtime=ctx.runtime,
            model_id=ctx.candidate_model,
            reason_streak=ctx.reason_streak,
            flip_enabled=ctx.recovery_priority_flip_enabled,
            flip_threshold=ctx.recovery_priority_flip_threshold,
            signal_priority_enabled=ctx.signal_priority_enabled,
            health_score=ctx.health_score,
            expected_latency_ms=ctx.expected_latency_ms,
            cost_score=ctx.cost_score,
            low_health_threshold=ctx.signal_low_health_threshold,
            high_latency_ms=ctx.signal_high_latency_ms,
            high_cost_threshold=ctx.signal_high_cost_threshold,
            strategy_feedback_enabled=ctx.strategy_feedback_enabled,
            last_failed_strategy_by_reason=ctx.last_failed_strategy_by_reason,
            persistent_priority_enabled=ctx.persistent_priority_enabled,
            persistent_priority_min_samples=ctx.persistent_priority_min_samples,
        )
        signal_priority_reason = self._resolve_signal_priority_reason(
            reason=ctx.reason,
            health_score=ctx.health_score,
            expected_latency_ms=ctx.expected_latency_ms,
            cost_score=ctx.cost_score,
            low_health_threshold=ctx.signal_low_health_threshold,
            high_latency_ms=ctx.signal_high_latency_ms,
            high_cost_threshold=ctx.signal_high_cost_threshold,
            enabled=ctx.signal_priority_enabled,
            applied=signal_priority_applied,
        )
        strategy_feedback_reason = self._resolve_strategy_feedback_reason(
            reason=ctx.reason,
            last_failed_strategy_by_reason=ctx.last_failed_strategy_by_reason,
            enabled=ctx.strategy_feedback_enabled,
            applied=strategy_feedback_applied,
        )
        return PriorityRecoveryMetadata(
            priority_steps=priority_steps,
            recovery_priority_overridden=recovery_priority_overridden,
            persistent_priority_applied=persistent_priority_applied,
            persistent_priority_reason=persistent_priority_reason,
            signal_priority_applied=signal_priority_applied,
            signal_priority_reason=signal_priority_reason,
            strategy_feedback_applied=strategy_feedback_applied,
            strategy_feedback_reason=strategy_feedback_reason,
        )

    def _compact_user_message(self, user_message: str, *, target_ratio: float, min_chars: int) -> str:
        text = (user_message or "").strip()
        if not text:
            return text

        bounded_ratio = min(0.95, max(0.2, float(target_ratio)))
        target_length = int(len(text) * bounded_ratio)
        target_length = max(min_chars, target_length)
        if target_length >= len(text):
            return text

        compacted = text[:target_length].rstrip()
        suffix = "\n\n[context compacted by pipeline runner due to context_overflow]"
        if len(compacted) + len(suffix) > len(text):
            return compacted
        return compacted + suffix

    def _truncate_payload_for_retry(self, user_message: str, *, target_chars: int, min_chars: int) -> str:
        text = (user_message or "").strip()
        if not text:
            return text

        bounded_target = max(min_chars, int(target_chars))
        if bounded_target >= len(text):
            return text

        truncated = text[:bounded_target].rstrip()
        suffix = "\n\n[payload truncated by pipeline runner due to truncation_required]"
        if len(truncated) + len(suffix) > len(text):
            return truncated
        return truncated + suffix

    def _resolve_recovery_strategy(self, *, ctx: RecoveryContext) -> RecoveryStrategyResolution:
        return self._recovery_strategy_resolver.resolve(ctx=ctx)

    def _resolve_recovery_priority_steps(
        self,
        *,
        reason: str,
        runtime: str,
        model_id: str,
        reason_streak: int,
        flip_enabled: bool,
        flip_threshold: int,
        signal_priority_enabled: bool,
        health_score: float,
        expected_latency_ms: int,
        cost_score: float,
        low_health_threshold: float,
        high_latency_ms: int,
        high_cost_threshold: float,
        strategy_feedback_enabled: bool,
        last_failed_strategy_by_reason: dict[str, str],
        persistent_priority_enabled: bool,
        persistent_priority_min_samples: int,
    ) -> RecoveryPriorityResolution:
        """Resolve ordered recovery strategies and metadata for priority decisions."""
        normalized_runtime = (runtime or "").strip().lower()
        is_api = normalized_runtime == "api"
        priority_config = self._resolve_reason_priority_config(reason=reason, is_api=is_api)
        if priority_config is None:
            return (), False, False, "not_applicable", False, False

        raw_priority, allowed_steps, fallback_steps = priority_config
        base = self._normalize_recovery_priority(
            raw_priority,
            allowed=allowed_steps,
            fallback=fallback_steps,
        )
        return self._apply_priority_recovery_pipeline(
            reason=reason,
            model_id=model_id,
            base_steps=base,
            reason_streak=reason_streak,
            flip_enabled=flip_enabled,
            flip_threshold=flip_threshold,
            signal_priority_enabled=signal_priority_enabled,
            health_score=health_score,
            expected_latency_ms=expected_latency_ms,
            cost_score=cost_score,
            low_health_threshold=low_health_threshold,
            high_latency_ms=high_latency_ms,
            high_cost_threshold=high_cost_threshold,
            strategy_feedback_enabled=strategy_feedback_enabled,
            last_failed_strategy_by_reason=last_failed_strategy_by_reason,
            persistent_priority_enabled=persistent_priority_enabled,
            persistent_priority_min_samples=persistent_priority_min_samples,
        )

    def _resolve_reason_priority_config(
        self,
        *,
        reason: str,
        is_api: bool,
    ) -> tuple[object, set[str], tuple[str, ...]] | None:
        """Return reason/runtime-specific priority source, allowed steps and fallback order."""
        if reason == "context_overflow":
            raw_priority = (
                settings.pipeline_runner_context_overflow_priority_api
                if is_api
                else settings.pipeline_runner_context_overflow_priority_local
            )
            fallback = (
                ("overflow_fallback_retry", "prompt_compaction")
                if is_api
                else ("prompt_compaction", "overflow_fallback_retry")
            )
            return raw_priority, {"prompt_compaction", "overflow_fallback_retry"}, fallback

        if reason == "truncation_required":
            raw_priority = (
                settings.pipeline_runner_truncation_priority_api
                if is_api
                else settings.pipeline_runner_truncation_priority_local
            )
            fallback = (
                ("truncation_fallback_retry", "payload_truncation")
                if is_api
                else ("payload_truncation", "truncation_fallback_retry")
            )
            return raw_priority, {"payload_truncation", "truncation_fallback_retry"}, fallback

        return None

    def _apply_priority_recovery_pipeline(
        self,
        *,
        reason: str,
        model_id: str,
        base_steps: tuple[str, ...],
        reason_streak: int,
        flip_enabled: bool,
        flip_threshold: int,
        signal_priority_enabled: bool,
        health_score: float,
        expected_latency_ms: int,
        cost_score: float,
        low_health_threshold: float,
        high_latency_ms: int,
        high_cost_threshold: float,
        strategy_feedback_enabled: bool,
        last_failed_strategy_by_reason: dict[str, str],
        persistent_priority_enabled: bool,
        persistent_priority_min_samples: int,
    ) -> RecoveryPriorityResolution:
        """Apply signal, feedback, persistent metrics and optional flip in one shared path."""
        signal_adjusted, signal_applied = self._apply_signal_priority(
            reason=reason,
            steps=base_steps,
            enabled=signal_priority_enabled,
            health_score=health_score,
            expected_latency_ms=expected_latency_ms,
            cost_score=cost_score,
            low_health_threshold=low_health_threshold,
            high_latency_ms=high_latency_ms,
            high_cost_threshold=high_cost_threshold,
        )
        feedback_adjusted, feedback_applied = self._apply_strategy_feedback(
            reason=reason,
            steps=signal_adjusted,
            enabled=strategy_feedback_enabled,
            last_failed_strategy_by_reason=last_failed_strategy_by_reason,
        )
        persistent_adjusted, persistent_applied, persistent_reason = self._apply_persistent_metrics_priority(
            reason=reason,
            model_id=model_id,
            steps=feedback_adjusted,
            enabled=persistent_priority_enabled,
            min_samples=persistent_priority_min_samples,
        )
        final_steps, overridden = self._apply_priority_flip(
            persistent_adjusted,
            reason_streak=reason_streak,
            enabled=flip_enabled,
            threshold=flip_threshold,
            already_overridden=(signal_applied or feedback_applied or persistent_applied),
        )
        return final_steps, overridden, persistent_applied, persistent_reason, signal_applied, feedback_applied

    def _normalize_recovery_priority(
        self,
        raw_priority,
        *,
        allowed: set[str],
        fallback: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        source = raw_priority if isinstance(raw_priority, list) else []
        for value in source:
            if not isinstance(value, str):
                continue
            entry = value.strip().lower()
            if not entry or entry not in allowed or entry in seen:
                continue
            seen.add(entry)
            normalized.append(entry)
        if normalized:
            return tuple(normalized)
        return fallback

    def _apply_priority_flip(
        self,
        steps: tuple[str, ...],
        *,
        reason_streak: int,
        enabled: bool,
        threshold: int,
        already_overridden: bool,
    ) -> tuple[tuple[str, ...], bool]:
        if already_overridden:
            return steps, True
        if not enabled or reason_streak < max(2, int(threshold)):
            return steps, False
        if len(steps) < 2:
            return steps, False
        rotated = (*steps[1:], steps[0])
        return rotated, True

    def _apply_signal_priority(
        self,
        *,
        reason: str,
        steps: tuple[str, ...],
        enabled: bool,
        health_score: float,
        expected_latency_ms: int,
        cost_score: float,
        low_health_threshold: float,
        high_latency_ms: int,
        high_cost_threshold: float,
    ) -> tuple[tuple[str, ...], bool]:
        if not enabled or len(steps) < 2:
            return steps, False

        preferred_step = ""
        if reason == "context_overflow":
            if health_score < low_health_threshold:
                preferred_step = "overflow_fallback_retry"
            elif expected_latency_ms >= high_latency_ms or cost_score >= high_cost_threshold:
                preferred_step = "prompt_compaction"
        elif reason == "truncation_required":
            if health_score < low_health_threshold:
                preferred_step = "truncation_fallback_retry"
            elif expected_latency_ms >= high_latency_ms or cost_score >= high_cost_threshold:
                preferred_step = "payload_truncation"

        if not preferred_step or preferred_step not in steps:
            return steps, False
        if steps[0] == preferred_step:
            return steps, False

        reordered = [preferred_step, *[item for item in steps if item != preferred_step]]
        return tuple(reordered), True

    def _resolve_signal_priority_reason(
        self,
        *,
        reason: str,
        health_score: float,
        expected_latency_ms: int,
        cost_score: float,
        low_health_threshold: float,
        high_latency_ms: int,
        high_cost_threshold: float,
        enabled: bool,
        applied: bool,
    ) -> str:
        if not enabled:
            return "disabled"
        if reason not in {"context_overflow", "truncation_required"}:
            return "not_applicable"
        if not applied:
            return "none"
        if health_score < low_health_threshold:
            return "low_health_prefer_fallback"
        if expected_latency_ms >= high_latency_ms:
            return "high_latency_prefer_transform"
        if cost_score >= high_cost_threshold:
            return "high_cost_prefer_transform"
        return "none"

    def _apply_strategy_feedback(
        self,
        *,
        reason: str,
        steps: tuple[str, ...],
        enabled: bool,
        last_failed_strategy_by_reason: dict[str, str],
    ) -> tuple[tuple[str, ...], bool]:
        if not enabled or len(steps) < 2:
            return steps, False
        failed_strategy = str(last_failed_strategy_by_reason.get(reason, "") or "").strip()
        if not failed_strategy or failed_strategy not in steps:
            return steps, False
        if steps[-1] == failed_strategy:
            return steps, False
        reordered = tuple([item for item in steps if item != failed_strategy] + [failed_strategy])
        return reordered, True

    def _resolve_strategy_feedback_reason(
        self,
        *,
        reason: str,
        last_failed_strategy_by_reason: dict[str, str],
        enabled: bool,
        applied: bool,
    ) -> str:
        if not enabled:
            return "disabled"
        if not applied:
            return "none"
        failed_strategy = str(last_failed_strategy_by_reason.get(reason, "") or "").strip()
        if not failed_strategy:
            return "none"
        return f"demote:{failed_strategy}"

    def _apply_persistent_metrics_priority(
        self,
        *,
        reason: str,
        model_id: str,
        steps: tuple[str, ...],
        enabled: bool,
        min_samples: int,
    ) -> tuple[tuple[str, ...], bool, str]:
        if not enabled:
            return steps, False, "disabled"
        if len(steps) < 2:
            return steps, False, "none"

        candidate_stats: list[tuple[str, int, float]] = []
        required_samples = max(1, int(min_samples))
        for step in steps:
            weighted_success, weighted_failure, samples = self._read_recovery_metric(
                model_id=model_id,
                reason=reason,
                strategy=step,
            )
            if samples < required_samples:
                continue
            denominator = weighted_success + weighted_failure
            if denominator <= 0:
                continue
            score = float(weighted_success) / float(denominator)
            candidate_stats.append((step, samples, score))

        if not candidate_stats:
            return steps, False, "insufficient_samples"

        candidate_stats.sort(key=lambda item: (item[2], item[1]), reverse=True)
        best_step = candidate_stats[0][0]
        if steps[0] == best_step:
            return steps, False, f"metrics_keep:{best_step}"

        reordered = [best_step, *[item for item in steps if item != best_step]]
        return tuple(reordered), True, f"metrics_prefer:{best_step}"

    def _load_recovery_metrics(self) -> dict[str, object]:
        try:
            if not self._recovery_metrics_file.exists():
                return {"version": 1, "metrics": {}}
            payload = json.loads(self._recovery_metrics_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"version": 1, "metrics": {}}
            metrics = payload.get("metrics")
            if not isinstance(metrics, dict):
                payload["metrics"] = {}
            if "version" not in payload:
                payload["version"] = 1
            return payload
        except Exception:
            return {"version": 1, "metrics": {}}

    def _persist_recovery_metrics(self) -> None:
        try:
            self._recovery_metrics_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self._recovery_metrics_file.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(self._recovery_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_file.replace(self._recovery_metrics_file)
        except Exception:
            return

    def _record_recovery_metric(self, *, model_id: str, reason: str, strategy: str, outcome: str) -> None:
        normalized_model = str(model_id or "").strip().lower()
        normalized_reason = str(reason or "").strip().lower()
        normalized_strategy = str(strategy or "").strip().lower()
        normalized_outcome = str(outcome or "").strip().lower()
        if normalized_outcome not in {"success", "failure"}:
            return
        if not normalized_model or not normalized_reason or not normalized_strategy:
            return

        metrics_root = self._recovery_metrics.get("metrics")
        if not isinstance(metrics_root, dict):
            metrics_root = {}
            self._recovery_metrics["metrics"] = metrics_root

        reason_bucket = metrics_root.setdefault(normalized_reason, {})
        if not isinstance(reason_bucket, dict):
            reason_bucket = {}
            metrics_root[normalized_reason] = reason_bucket

        model_bucket = reason_bucket.setdefault(normalized_model, {})
        if not isinstance(model_bucket, dict):
            model_bucket = {}
            reason_bucket[normalized_model] = model_bucket

        strategy_bucket = model_bucket.setdefault(normalized_strategy, {"success": 0, "failure": 0})
        if not isinstance(strategy_bucket, dict):
            strategy_bucket = {"success": 0, "failure": 0}
            model_bucket[normalized_strategy] = strategy_bucket

        current = int(strategy_bucket.get(normalized_outcome, 0) or 0)
        strategy_bucket[normalized_outcome] = current + 1
        now_ts = time.time()
        strategy_bucket["last_updated_ts"] = now_ts

        raw_events = strategy_bucket.get("events")
        events = raw_events if isinstance(raw_events, list) else []
        events.append({"outcome": normalized_outcome, "ts": now_ts})
        pruned_events, _ = self._prune_metric_events(events)
        strategy_bucket["events"] = pruned_events
        self._persist_recovery_metrics()

    def _read_recovery_metric(self, *, model_id: str, reason: str, strategy: str) -> tuple[float, float, int]:
        metrics_root = self._recovery_metrics.get("metrics")
        if not isinstance(metrics_root, dict):
            return 0.0, 0.0, 0

        reason_bucket = metrics_root.get(str(reason or "").strip().lower())
        if not isinstance(reason_bucket, dict):
            return 0.0, 0.0, 0

        model_bucket = reason_bucket.get(str(model_id or "").strip().lower())
        if not isinstance(model_bucket, dict):
            return 0.0, 0.0, 0

        strategy_bucket = model_bucket.get(str(strategy or "").strip().lower())
        if not isinstance(strategy_bucket, dict):
            return 0.0, 0.0, 0

        raw_events = strategy_bucket.get("events")
        events = raw_events if isinstance(raw_events, list) else []
        pruned_events, was_pruned = self._prune_metric_events(events)
        if pruned_events:
            weighted_success, weighted_failure = self._compute_weighted_event_stats(pruned_events)
            if was_pruned or pruned_events is not events:
                strategy_bucket["events"] = pruned_events
                self._persist_recovery_metrics()
            return weighted_success, weighted_failure, len(pruned_events)

        if was_pruned and raw_events is not None:
            strategy_bucket["events"] = pruned_events
            self._persist_recovery_metrics()

        success = int(strategy_bucket.get("success", 0) or 0)
        failure = int(strategy_bucket.get("failure", 0) or 0)
        success = max(0, success)
        failure = max(0, failure)
        samples = success + failure
        if samples <= 0:
            return 0.0, 0.0, 0

        weighted_success = float(success)
        weighted_failure = float(failure)
        if settings.pipeline_runner_persistent_priority_decay_enabled:
            half_life = max(
                1,
                int(settings.pipeline_runner_persistent_priority_decay_half_life_seconds),
            )
            last_updated_raw = strategy_bucket.get("last_updated_ts", 0)
            try:
                last_updated_ts = float(last_updated_raw)
            except (TypeError, ValueError):
                last_updated_ts = 0.0
            if last_updated_ts > 0:
                age_seconds = max(0.0, time.time() - last_updated_ts)
                decay_factor = 0.5 ** (age_seconds / float(half_life))
                weighted_success *= decay_factor
                weighted_failure *= decay_factor

        return weighted_success, weighted_failure, samples

    def _prune_metric_events(self, events: list[object]) -> tuple[list[dict[str, object]], bool]:
        if not events:
            return [], False

        max_age_seconds = max(
            1,
            int(settings.pipeline_runner_persistent_priority_window_max_age_seconds),
        )
        window_size = max(
            1,
            int(settings.pipeline_runner_persistent_priority_window_size),
        )
        now_ts = time.time()
        cutoff = now_ts - float(max_age_seconds)

        filtered: list[dict[str, object]] = []
        changed = False
        for item in events:
            if not isinstance(item, dict):
                changed = True
                continue
            outcome = str(item.get("outcome", "")).strip().lower()
            if outcome not in {"success", "failure"}:
                changed = True
                continue
            ts_raw = item.get("ts")
            try:
                ts = float(ts_raw)
            except (TypeError, ValueError):
                changed = True
                continue
            if ts <= 0 or ts < cutoff:
                changed = True
                continue
            filtered.append({"outcome": outcome, "ts": ts})

        filtered.sort(key=lambda event: float(event.get("ts", 0.0)))
        if len(filtered) > window_size:
            filtered = filtered[-window_size:]
            changed = True

        if len(filtered) != len(events):
            changed = True
        return filtered, changed

    def _compute_weighted_event_stats(self, events: list[dict[str, object]]) -> tuple[float, float]:
        weighted_success = 0.0
        weighted_failure = 0.0
        decay_enabled = bool(settings.pipeline_runner_persistent_priority_decay_enabled)
        half_life = max(
            1,
            int(settings.pipeline_runner_persistent_priority_decay_half_life_seconds),
        )
        now_ts = time.time()

        for event in events:
            outcome = str(event.get("outcome", "")).strip().lower()
            if outcome not in {"success", "failure"}:
                continue
            ts_raw = event.get("ts")
            try:
                ts = float(ts_raw)
            except (TypeError, ValueError):
                continue
            if ts <= 0:
                continue

            if decay_enabled:
                age_seconds = max(0.0, now_ts - ts)
                weight = 0.5 ** (age_seconds / float(half_life))
            else:
                weight = 1.0

            if outcome == "success":
                weighted_success += weight
            else:
                weighted_failure += weight

        return weighted_success, weighted_failure
