from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.contracts.agent_contract import AgentContract, SendEvent
from app.config import settings
from app.errors import GuardrailViolation, LlmClientError
from app.model_routing.context_window_guard import evaluate_context_window_guard
from app.model_routing import ModelRouter
from app.orchestrator.events import LifecycleStage, build_lifecycle_event
from app.orchestrator.step_types import PipelineStep
from app.state import StateStore
from app.tool_policy import ToolPolicyDict


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


class PipelineRunner:
    def __init__(self, agent: AgentContract, state_store: StateStore):
        self.agent = agent
        self.state_store = state_store
        self.model_router = ModelRouter()
        self._recovery_metrics_file = Path(self.state_store.persist_dir) / "pipeline_recovery_metrics.json"
        self._recovery_metrics = self._load_recovery_metrics()

    async def run(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        runtime: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
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

        route = self.model_router.route(runtime=runtime, requested_model=model)
        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage=LifecycleStage.MODEL_ROUTE_SELECTED,
                details={
                    "primary": route.primary_model,
                    "fallbacks": route.fallback_models,
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

        final_text = await self._run_with_fallback(
            user_message=user_message,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            runtime=runtime,
            route=route,
            tool_policy=tool_policy,
        )

        for step in (PipelineStep.PLAN, PipelineStep.TOOL_SELECT, PipelineStep.TOOL_EXECUTE, PipelineStep.SYNTHESIZE):
            self.state_store.set_task_status(
                run_id=request_id,
                task_id=str(step),
                label=str(step),
                status="completed",
            )

        return final_text

    async def _run_with_fallback(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        runtime: str,
        route,
        tool_policy: ToolPolicyDict | None,
    ) -> str:
        models = [route.primary_model, *route.fallback_models]
        current_user_message = user_message
        last_error: Exception | None = None
        last_reason = "unknown"
        max_attempts = max(1, int(getattr(settings, "pipeline_runner_max_attempts", 16)))
        attempts = 0
        overflow_fallback_retry_enabled = bool(
            getattr(settings, "pipeline_runner_context_overflow_fallback_retry_enabled", False)
        )
        overflow_fallback_retry_max_attempts = max(
            0,
            int(getattr(settings, "pipeline_runner_context_overflow_fallback_retry_max_attempts", 1)),
        )
        overflow_fallback_retry_attempts = 0
        compaction_failure_recovery_enabled = bool(
            getattr(settings, "pipeline_runner_compaction_failure_recovery_enabled", False)
        )
        compaction_failure_recovery_max_attempts = max(
            0,
            int(getattr(settings, "pipeline_runner_compaction_failure_recovery_max_attempts", 1)),
        )
        compaction_failure_recovery_attempts = 0
        truncation_recovery_enabled = bool(
            getattr(settings, "pipeline_runner_truncation_recovery_enabled", False)
        )
        truncation_recovery_max_attempts = max(
            0,
            int(getattr(settings, "pipeline_runner_truncation_recovery_max_attempts", 1)),
        )
        truncation_recovery_attempts = 0
        prompt_compaction_enabled = bool(
            getattr(settings, "pipeline_runner_prompt_compaction_enabled", False)
        )
        prompt_compaction_max_attempts = max(
            0,
            int(getattr(settings, "pipeline_runner_prompt_compaction_max_attempts", 1)),
        )
        prompt_compaction_attempts = 0
        prompt_compaction_ratio = float(
            getattr(settings, "pipeline_runner_prompt_compaction_ratio", 0.7)
        )
        prompt_compaction_min_chars = max(
            64,
            int(getattr(settings, "pipeline_runner_prompt_compaction_min_chars", 200)),
        )
        payload_truncation_enabled = bool(
            getattr(settings, "pipeline_runner_payload_truncation_enabled", False)
        )
        payload_truncation_max_attempts = max(
            0,
            int(getattr(settings, "pipeline_runner_payload_truncation_max_attempts", 1)),
        )
        payload_truncation_attempts = 0
        payload_truncation_target_chars = max(
            64,
            int(getattr(settings, "pipeline_runner_payload_truncation_target_chars", 1200)),
        )
        payload_truncation_min_chars = max(
            32,
            int(getattr(settings, "pipeline_runner_payload_truncation_min_chars", 120)),
        )
        recovery_priority_flip_enabled = bool(
            getattr(settings, "pipeline_runner_recovery_priority_flip_enabled", True)
        )
        recovery_priority_flip_threshold = max(
            2,
            int(getattr(settings, "pipeline_runner_recovery_priority_flip_threshold", 2)),
        )
        signal_priority_enabled = bool(
            getattr(settings, "pipeline_runner_signal_priority_enabled", True)
        )
        signal_low_health_threshold = float(
            getattr(settings, "pipeline_runner_signal_low_health_threshold", 0.55)
        )
        signal_high_latency_ms = max(
            1,
            int(getattr(settings, "pipeline_runner_signal_high_latency_ms", 2500)),
        )
        signal_high_cost_threshold = float(
            getattr(settings, "pipeline_runner_signal_high_cost_threshold", 0.75)
        )
        strategy_feedback_enabled = bool(
            getattr(settings, "pipeline_runner_strategy_feedback_enabled", True)
        )
        persistent_priority_enabled = bool(
            getattr(settings, "pipeline_runner_persistent_priority_enabled", True)
        )
        persistent_priority_min_samples = max(
            1,
            int(getattr(settings, "pipeline_runner_persistent_priority_min_samples", 3)),
        )
        reason_streak = 0
        previous_reason = ""
        last_failed_strategy_by_reason: dict[str, str] = {}
        pending_recovery_outcome: tuple[str, str, str] | None = None
        recovery_failures_total = 0
        recovery_reason_counts: dict[str, int] = {}
        recovery_branch_counts: dict[str, int] = {}
        recovery_strategy_counts: dict[str, int] = {}
        recovery_strategy_applied_total = 0
        recovery_signal_priority_applied_total = 0
        recovery_strategy_feedback_applied_total = 0
        recovery_persistent_priority_applied_total = 0
        recovery_overflow_retry_applied_total = 0
        recovery_compaction_recovery_applied_total = 0
        recovery_truncation_recovery_applied_total = 0
        recovery_prompt_compaction_applied_total = 0
        recovery_payload_truncation_applied_total = 0

        async def emit_recovery_summary(final_outcome: str, final_model: str, final_reason: str) -> None:
            if recovery_failures_total <= 0:
                return
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
                        "strategy_feedback_applied_total": recovery_strategy_feedback_applied_total,
                        "persistent_priority_applied_total": recovery_persistent_priority_applied_total,
                        "overflow_retry_applied_total": recovery_overflow_retry_applied_total,
                        "compaction_recovery_applied_total": recovery_compaction_recovery_applied_total,
                        "truncation_recovery_applied_total": recovery_truncation_recovery_applied_total,
                        "prompt_compaction_applied_total": recovery_prompt_compaction_applied_total,
                        "payload_truncation_applied_total": recovery_payload_truncation_applied_total,
                        "final_outcome": final_outcome,
                        "final_model": final_model,
                        "final_reason": final_reason,
                    },
                    agent=self.agent.name,
                )
            )

        for index, candidate_model in enumerate(models):
            if attempts >= max_attempts:
                await emit_recovery_summary("failure", models[min(index, len(models) - 1)], last_reason)
                await send_event(
                    build_lifecycle_event(
                        request_id=request_id,
                        session_id=session_id,
                        stage="model_fallback_retry_limit_reached",
                        details={
                            "attempts": attempts,
                            "max_attempts": max_attempts,
                            "last_reason": last_reason,
                        },
                        agent=self.agent.name,
                    )
                )
                if isinstance(last_error, LlmClientError):
                    raise last_error
                raise LlmClientError(
                    f"Model fallback retry limit reached ({attempts}/{max_attempts})."
                )

            try:
                attempts += 1
                if index > 0:
                    await send_event(
                        {
                            "type": "status",
                            "agent": self.agent.name,
                            "message": f"Retrying with fallback model '{candidate_model}'.",
                        }
                    )
                    await send_event(
                        build_lifecycle_event(
                            request_id=request_id,
                            session_id=session_id,
                            stage=LifecycleStage.MODEL_FALLBACK_RETRY,
                            details={
                                "to": candidate_model,
                                "reason": last_reason,
                                "attempt": attempts,
                                "max_attempts": max_attempts,
                            },
                            agent=self.agent.name,
                        )
                    )

                result = await self.agent.run(
                    user_message=current_user_message,
                    send_event=send_event,
                    session_id=session_id,
                    request_id=request_id,
                    model=candidate_model,
                    tool_policy=tool_policy,
                )
                if pending_recovery_outcome is not None:
                    model_id, recorded_reason, recorded_strategy = pending_recovery_outcome
                    self._record_recovery_metric(
                        model_id=model_id,
                        reason=recorded_reason,
                        strategy=recorded_strategy,
                        outcome="success",
                    )
                    pending_recovery_outcome = None
                await emit_recovery_summary("success", candidate_model, last_reason)
                return result
            except LlmClientError as exc:
                if pending_recovery_outcome is not None:
                    model_id, recorded_reason, recorded_strategy = pending_recovery_outcome
                    self._record_recovery_metric(
                        model_id=model_id,
                        reason=recorded_reason,
                        strategy=recorded_strategy,
                        outcome="failure",
                    )
                    pending_recovery_outcome = None
                last_error = exc
                reason = self._classify_failover_reason(str(exc))
                last_reason = reason
                if reason == previous_reason:
                    reason_streak += 1
                else:
                    reason_streak = 1
                    previous_reason = reason
                has_fallback = index < len(models) - 1
                retryable = self._is_retryable_failover_reason(reason)
                recovery_branch = self._resolve_recovery_branch(reason)
                recovery_resolution = self._resolve_recovery_strategy(
                    reason=reason,
                    runtime=runtime,
                    candidate_model=candidate_model,
                    has_fallback=has_fallback,
                    reason_streak=reason_streak,
                    current_user_message=current_user_message,
                    retryable=retryable,
                    recovery_branch=recovery_branch,
                    overflow_fallback_retry_enabled=overflow_fallback_retry_enabled,
                    overflow_fallback_retry_max_attempts=overflow_fallback_retry_max_attempts,
                    overflow_fallback_retry_attempts=overflow_fallback_retry_attempts,
                    compaction_failure_recovery_enabled=compaction_failure_recovery_enabled,
                    compaction_failure_recovery_max_attempts=compaction_failure_recovery_max_attempts,
                    compaction_failure_recovery_attempts=compaction_failure_recovery_attempts,
                    truncation_recovery_enabled=truncation_recovery_enabled,
                    truncation_recovery_max_attempts=truncation_recovery_max_attempts,
                    truncation_recovery_attempts=truncation_recovery_attempts,
                    prompt_compaction_enabled=prompt_compaction_enabled,
                    prompt_compaction_max_attempts=prompt_compaction_max_attempts,
                    prompt_compaction_attempts=prompt_compaction_attempts,
                    prompt_compaction_ratio=prompt_compaction_ratio,
                    prompt_compaction_min_chars=prompt_compaction_min_chars,
                    payload_truncation_enabled=payload_truncation_enabled,
                    payload_truncation_max_attempts=payload_truncation_max_attempts,
                    payload_truncation_attempts=payload_truncation_attempts,
                    payload_truncation_target_chars=payload_truncation_target_chars,
                    payload_truncation_min_chars=payload_truncation_min_chars,
                    recovery_priority_flip_enabled=recovery_priority_flip_enabled,
                    recovery_priority_flip_threshold=recovery_priority_flip_threshold,
                    signal_priority_enabled=signal_priority_enabled,
                    signal_low_health_threshold=signal_low_health_threshold,
                    signal_high_latency_ms=signal_high_latency_ms,
                    signal_high_cost_threshold=signal_high_cost_threshold,
                    strategy_feedback_enabled=strategy_feedback_enabled,
                    persistent_priority_enabled=persistent_priority_enabled,
                    persistent_priority_min_samples=persistent_priority_min_samples,
                    last_failed_strategy_by_reason=last_failed_strategy_by_reason,
                    health_score=float(getattr(route.profile, "health_score", 0.0) or 0.0),
                    expected_latency_ms=int(getattr(route.profile, "expected_latency_ms", 0) or 0),
                    cost_score=float(getattr(route.profile, "cost_score", 0.0) or 0.0),
                )

                retryable = recovery_resolution.retryable
                recovery_branch = recovery_resolution.recovery_branch
                recovery_strategy = recovery_resolution.recovery_strategy
                current_user_message = recovery_resolution.current_user_message
                overflow_fallback_retry_attempts = recovery_resolution.overflow_fallback_retry_attempts
                compaction_failure_recovery_attempts = recovery_resolution.compaction_failure_recovery_attempts
                truncation_recovery_attempts = recovery_resolution.truncation_recovery_attempts
                prompt_compaction_attempts = recovery_resolution.prompt_compaction_attempts
                payload_truncation_attempts = recovery_resolution.payload_truncation_attempts

                overflow_retry_applied = recovery_resolution.overflow_retry_applied
                compaction_recovery_applied = recovery_resolution.compaction_recovery_applied
                truncation_recovery_applied = recovery_resolution.truncation_recovery_applied
                prompt_compaction_applied = recovery_resolution.prompt_compaction_applied
                payload_truncation_applied = recovery_resolution.payload_truncation_applied
                recovery_priority_overridden = recovery_resolution.recovery_priority_overridden
                signal_priority_applied = recovery_resolution.signal_priority_applied
                signal_priority_reason = recovery_resolution.signal_priority_reason
                strategy_feedback_applied = recovery_resolution.strategy_feedback_applied
                strategy_feedback_reason = recovery_resolution.strategy_feedback_reason
                persistent_priority_applied = recovery_resolution.persistent_priority_applied
                persistent_priority_reason = recovery_resolution.persistent_priority_reason
                prompt_compaction_previous_chars = recovery_resolution.prompt_compaction_previous_chars
                prompt_compaction_new_chars = recovery_resolution.prompt_compaction_new_chars
                payload_truncation_previous_chars = recovery_resolution.payload_truncation_previous_chars
                payload_truncation_new_chars = recovery_resolution.payload_truncation_new_chars

                recovery_failures_total += 1
                recovery_reason_counts[reason] = int(recovery_reason_counts.get(reason, 0) or 0) + 1
                recovery_branch_counts[recovery_branch] = int(recovery_branch_counts.get(recovery_branch, 0) or 0) + 1
                if ":" in recovery_strategy:
                    strategy_name = recovery_strategy.split(":", 1)[1]
                    recovery_strategy_counts[strategy_name] = int(recovery_strategy_counts.get(strategy_name, 0) or 0) + 1
                    recovery_strategy_applied_total += 1
                if signal_priority_applied:
                    recovery_signal_priority_applied_total += 1
                if strategy_feedback_applied:
                    recovery_strategy_feedback_applied_total += 1
                if persistent_priority_applied:
                    recovery_persistent_priority_applied_total += 1
                if overflow_retry_applied:
                    recovery_overflow_retry_applied_total += 1
                if compaction_recovery_applied:
                    recovery_compaction_recovery_applied_total += 1
                if truncation_recovery_applied:
                    recovery_truncation_recovery_applied_total += 1
                if prompt_compaction_applied:
                    recovery_prompt_compaction_applied_total += 1
                if payload_truncation_applied:
                    recovery_payload_truncation_applied_total += 1

                await send_event(
                    build_lifecycle_event(
                        request_id=request_id,
                        session_id=session_id,
                        stage="model_fallback_classified",
                        details={
                            "model": candidate_model,
                            "reason": reason,
                            "retryable": retryable,
                            "has_fallback": has_fallback,
                        },
                        agent=self.agent.name,
                    )
                )

                await send_event(
                    build_lifecycle_event(
                        request_id=request_id,
                        session_id=session_id,
                        stage="model_recovery_branch_selected",
                        details={
                            "model": candidate_model,
                            "reason": reason,
                            "branch": recovery_branch,
                            "retryable": retryable,
                            "has_fallback": has_fallback,
                            "overflow_retry_applied": overflow_retry_applied,
                            "overflow_retry_attempts": overflow_fallback_retry_attempts,
                            "overflow_retry_max_attempts": overflow_fallback_retry_max_attempts,
                            "compaction_recovery_applied": compaction_recovery_applied,
                            "compaction_recovery_attempts": compaction_failure_recovery_attempts,
                            "compaction_recovery_max_attempts": compaction_failure_recovery_max_attempts,
                            "truncation_recovery_applied": truncation_recovery_applied,
                            "truncation_recovery_attempts": truncation_recovery_attempts,
                            "truncation_recovery_max_attempts": truncation_recovery_max_attempts,
                            "prompt_compaction_applied": prompt_compaction_applied,
                            "prompt_compaction_attempts": prompt_compaction_attempts,
                            "prompt_compaction_max_attempts": prompt_compaction_max_attempts,
                            "prompt_compaction_previous_chars": prompt_compaction_previous_chars,
                            "prompt_compaction_new_chars": prompt_compaction_new_chars,
                            "payload_truncation_applied": payload_truncation_applied,
                            "payload_truncation_attempts": payload_truncation_attempts,
                            "payload_truncation_max_attempts": payload_truncation_max_attempts,
                            "payload_truncation_previous_chars": payload_truncation_previous_chars,
                            "payload_truncation_new_chars": payload_truncation_new_chars,
                            "recovery_strategy": recovery_strategy,
                            "reason_streak": reason_streak,
                            "recovery_priority_overridden": recovery_priority_overridden,
                            "signal_priority_applied": signal_priority_applied,
                            "signal_priority_reason": signal_priority_reason,
                            "strategy_feedback_applied": strategy_feedback_applied,
                            "strategy_feedback_reason": strategy_feedback_reason,
                            "persistent_priority_applied": persistent_priority_applied,
                            "persistent_priority_reason": persistent_priority_reason,
                        },
                        agent=self.agent.name,
                    )
                )

                await send_event(
                    build_lifecycle_event(
                        request_id=request_id,
                        session_id=session_id,
                        stage="model_recovery_action",
                        details={
                            "model": candidate_model,
                            "reason": reason,
                            "branch": recovery_branch,
                            "action": "retry_fallback" if (retryable and has_fallback) else "fail_fast",
                            "overflow_retry_applied": overflow_retry_applied,
                            "compaction_recovery_applied": compaction_recovery_applied,
                            "truncation_recovery_applied": truncation_recovery_applied,
                            "prompt_compaction_applied": prompt_compaction_applied,
                            "payload_truncation_applied": payload_truncation_applied,
                            "recovery_strategy": recovery_strategy,
                            "reason_streak": reason_streak,
                            "recovery_priority_overridden": recovery_priority_overridden,
                            "signal_priority_applied": signal_priority_applied,
                            "signal_priority_reason": signal_priority_reason,
                            "strategy_feedback_applied": strategy_feedback_applied,
                            "strategy_feedback_reason": strategy_feedback_reason,
                            "persistent_priority_applied": persistent_priority_applied,
                            "persistent_priority_reason": persistent_priority_reason,
                        },
                        agent=self.agent.name,
                    )
                )

                if ":" in recovery_strategy:
                    strategy_name = recovery_strategy.split(":", 1)[1]
                    last_failed_strategy_by_reason[reason] = strategy_name
                    if retryable and has_fallback:
                        pending_recovery_outcome = (candidate_model, reason, strategy_name)

                if index >= len(models) - 1:
                    await emit_recovery_summary("failure", candidate_model, reason)
                    await send_event(
                        build_lifecycle_event(
                            request_id=request_id,
                            session_id=session_id,
                            stage="model_fallback_exhausted",
                            details={
                                "model": candidate_model,
                                "reason": reason,
                            },
                            agent=self.agent.name,
                        )
                    )
                    raise

                if not retryable:
                    await emit_recovery_summary("failure", candidate_model, reason)
                    await send_event(
                        build_lifecycle_event(
                            request_id=request_id,
                            session_id=session_id,
                            stage="model_fallback_not_retryable",
                            details={
                                "model": candidate_model,
                                "reason": reason,
                            },
                            agent=self.agent.name,
                        )
                    )
                    raise

        if isinstance(last_error, LlmClientError):
            await emit_recovery_summary("failure", models[-1], last_reason)
            raise last_error
        raise LlmClientError("Model routing failed before execution.")

    def _classify_failover_reason(self, message: str) -> str:
        text = (message or "").lower()
        if (
            "context overflow" in text
            or "context window" in text
            or "too large for the model" in text
            or "maximum context length" in text
            or "prompt too long" in text
        ):
            return "context_overflow"
        if "compaction" in text and (
            "failed" in text
            or "timeout" in text
            or "timed out" in text
        ):
            return "compaction_failure"
        if (
            "truncat" in text
            or "truncated" in text
            or "token limit" in text
            or "max tokens" in text
        ):
            return "truncation_required"
        if "model" in text and "not found" in text:
            return "model_not_found"
        if "rate limit" in text or "too many requests" in text or "429" in text:
            return "rate_limited"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "temporarily unavailable" in text or "service unavailable" in text or "503" in text:
            return "temporary_unavailable"
        if "connection" in text or "network" in text or "dns" in text:
            return "network_error"
        return "unknown"

    def _is_retryable_failover_reason(self, reason: str) -> bool:
        return reason in {
            "model_not_found",
            "rate_limited",
            "timeout",
            "temporary_unavailable",
            "network_error",
        }

    def _resolve_recovery_branch(self, reason: str) -> str:
        if reason == "context_overflow":
            return "fail_fast_context_overflow"
        if reason == "compaction_failure":
            return "fail_fast_compaction_failure"
        if reason == "truncation_required":
            return "fail_fast_truncation_required"
        if self._is_retryable_failover_reason(reason):
            return "retry_with_fallback"
        return "fail_fast_non_retryable"

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

    def _resolve_recovery_strategy(
        self,
        *,
        reason: str,
        runtime: str,
        candidate_model: str,
        has_fallback: bool,
        reason_streak: int,
        current_user_message: str,
        retryable: bool,
        recovery_branch: str,
        overflow_fallback_retry_enabled: bool,
        overflow_fallback_retry_max_attempts: int,
        overflow_fallback_retry_attempts: int,
        compaction_failure_recovery_enabled: bool,
        compaction_failure_recovery_max_attempts: int,
        compaction_failure_recovery_attempts: int,
        truncation_recovery_enabled: bool,
        truncation_recovery_max_attempts: int,
        truncation_recovery_attempts: int,
        prompt_compaction_enabled: bool,
        prompt_compaction_max_attempts: int,
        prompt_compaction_attempts: int,
        prompt_compaction_ratio: float,
        prompt_compaction_min_chars: int,
        payload_truncation_enabled: bool,
        payload_truncation_max_attempts: int,
        payload_truncation_attempts: int,
        payload_truncation_target_chars: int,
        payload_truncation_min_chars: int,
        recovery_priority_flip_enabled: bool,
        recovery_priority_flip_threshold: int,
        signal_priority_enabled: bool,
        signal_low_health_threshold: float,
        signal_high_latency_ms: int,
        signal_high_cost_threshold: float,
        strategy_feedback_enabled: bool,
        persistent_priority_enabled: bool,
        persistent_priority_min_samples: int,
        last_failed_strategy_by_reason: dict[str, str],
        health_score: float,
        expected_latency_ms: int,
        cost_score: float,
    ) -> RecoveryStrategyResolution:
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

        if reason == "context_overflow" and has_fallback:
            (
                priority_steps,
                recovery_priority_overridden,
                persistent_priority_applied,
                persistent_priority_reason,
            ) = self._resolve_recovery_priority_steps(
                reason=reason,
                runtime=runtime,
                model_id=candidate_model,
                reason_streak=reason_streak,
                flip_enabled=recovery_priority_flip_enabled,
                flip_threshold=recovery_priority_flip_threshold,
                signal_priority_enabled=signal_priority_enabled,
                health_score=health_score,
                expected_latency_ms=expected_latency_ms,
                cost_score=cost_score,
                low_health_threshold=signal_low_health_threshold,
                high_latency_ms=signal_high_latency_ms,
                high_cost_threshold=signal_high_cost_threshold,
                strategy_feedback_enabled=strategy_feedback_enabled,
                last_failed_strategy_by_reason=last_failed_strategy_by_reason,
                persistent_priority_enabled=persistent_priority_enabled,
                persistent_priority_min_samples=persistent_priority_min_samples,
            )
            signal_priority_reason = self._resolve_signal_priority_reason(
                reason=reason,
                health_score=health_score,
                expected_latency_ms=expected_latency_ms,
                cost_score=cost_score,
                low_health_threshold=signal_low_health_threshold,
                high_latency_ms=signal_high_latency_ms,
                high_cost_threshold=signal_high_cost_threshold,
                enabled=signal_priority_enabled,
            )
            signal_priority_applied = signal_priority_reason in {
                "low_health_prefer_fallback",
                "high_latency_prefer_transform",
                "high_cost_prefer_transform",
            }
            strategy_feedback_reason = self._resolve_strategy_feedback_reason(
                reason=reason,
                last_failed_strategy_by_reason=last_failed_strategy_by_reason,
                enabled=strategy_feedback_enabled,
            )
            strategy_feedback_applied = strategy_feedback_reason.startswith("demote:")

            for step in priority_steps:
                if step == "prompt_compaction":
                    if not (
                        prompt_compaction_enabled and prompt_compaction_attempts < prompt_compaction_max_attempts
                    ):
                        continue
                    compacted_message = self._compact_user_message(
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
                        overflow_fallback_retry_enabled
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

        elif reason == "truncation_required" and has_fallback:
            (
                priority_steps,
                recovery_priority_overridden,
                persistent_priority_applied,
                persistent_priority_reason,
            ) = self._resolve_recovery_priority_steps(
                reason=reason,
                runtime=runtime,
                model_id=candidate_model,
                reason_streak=reason_streak,
                flip_enabled=recovery_priority_flip_enabled,
                flip_threshold=recovery_priority_flip_threshold,
                signal_priority_enabled=signal_priority_enabled,
                health_score=health_score,
                expected_latency_ms=expected_latency_ms,
                cost_score=cost_score,
                low_health_threshold=signal_low_health_threshold,
                high_latency_ms=signal_high_latency_ms,
                high_cost_threshold=signal_high_cost_threshold,
                strategy_feedback_enabled=strategy_feedback_enabled,
                last_failed_strategy_by_reason=last_failed_strategy_by_reason,
                persistent_priority_enabled=persistent_priority_enabled,
                persistent_priority_min_samples=persistent_priority_min_samples,
            )
            signal_priority_reason = self._resolve_signal_priority_reason(
                reason=reason,
                health_score=health_score,
                expected_latency_ms=expected_latency_ms,
                cost_score=cost_score,
                low_health_threshold=signal_low_health_threshold,
                high_latency_ms=signal_high_latency_ms,
                high_cost_threshold=signal_high_cost_threshold,
                enabled=signal_priority_enabled,
            )
            signal_priority_applied = signal_priority_reason in {
                "low_health_prefer_fallback",
                "high_latency_prefer_transform",
                "high_cost_prefer_transform",
            }
            strategy_feedback_reason = self._resolve_strategy_feedback_reason(
                reason=reason,
                last_failed_strategy_by_reason=last_failed_strategy_by_reason,
                enabled=strategy_feedback_enabled,
            )
            strategy_feedback_applied = strategy_feedback_reason.startswith("demote:")
            for step in priority_steps:
                if step == "payload_truncation":
                    if not (
                        payload_truncation_enabled
                        and payload_truncation_attempts < payload_truncation_max_attempts
                    ):
                        continue
                    truncated_message = self._truncate_payload_for_retry(
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
                        truncation_recovery_enabled and truncation_recovery_attempts < truncation_recovery_max_attempts
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
    ) -> tuple[tuple[str, ...], bool, bool, str]:
        normalized_runtime = (runtime or "").strip().lower()
        is_api = normalized_runtime == "api"

        if reason == "context_overflow":
            raw_priority = (
                getattr(settings, "pipeline_runner_context_overflow_priority_api", [])
                if is_api
                else getattr(settings, "pipeline_runner_context_overflow_priority_local", [])
            )
            fallback = (
                ("overflow_fallback_retry", "prompt_compaction")
                if is_api
                else ("prompt_compaction", "overflow_fallback_retry")
            )
            base = self._normalize_recovery_priority(
                raw_priority,
                allowed={"prompt_compaction", "overflow_fallback_retry"},
                fallback=fallback,
            )
            signal_adjusted, signal_applied = self._apply_signal_priority(
                reason=reason,
                steps=base,
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
            return final_steps, overridden, persistent_applied, persistent_reason

        if reason == "truncation_required":
            raw_priority = (
                getattr(settings, "pipeline_runner_truncation_priority_api", [])
                if is_api
                else getattr(settings, "pipeline_runner_truncation_priority_local", [])
            )
            fallback = (
                ("truncation_fallback_retry", "payload_truncation")
                if is_api
                else ("payload_truncation", "truncation_fallback_retry")
            )
            base = self._normalize_recovery_priority(
                raw_priority,
                allowed={"payload_truncation", "truncation_fallback_retry"},
                fallback=fallback,
            )
            signal_adjusted, signal_applied = self._apply_signal_priority(
                reason=reason,
                steps=base,
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
            return final_steps, overridden, persistent_applied, persistent_reason

        return tuple(), False, False, "not_applicable"

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
            elif expected_latency_ms >= high_latency_ms:
                preferred_step = "prompt_compaction"
            elif cost_score >= high_cost_threshold:
                preferred_step = "prompt_compaction"
        elif reason == "truncation_required":
            if health_score < low_health_threshold:
                preferred_step = "truncation_fallback_retry"
            elif expected_latency_ms >= high_latency_ms:
                preferred_step = "payload_truncation"
            elif cost_score >= high_cost_threshold:
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
    ) -> str:
        if not enabled:
            return "disabled"
        if reason not in {"context_overflow", "truncation_required"}:
            return "not_applicable"
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
    ) -> str:
        if not enabled:
            return "disabled"
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
        if getattr(settings, "pipeline_runner_persistent_priority_decay_enabled", True):
            half_life = max(
                1,
                int(getattr(settings, "pipeline_runner_persistent_priority_decay_half_life_seconds", 86400)),
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
            int(getattr(settings, "pipeline_runner_persistent_priority_window_max_age_seconds", 604800)),
        )
        window_size = max(
            1,
            int(getattr(settings, "pipeline_runner_persistent_priority_window_size", 50)),
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
        decay_enabled = bool(getattr(settings, "pipeline_runner_persistent_priority_decay_enabled", True))
        half_life = max(
            1,
            int(getattr(settings, "pipeline_runner_persistent_priority_decay_half_life_seconds", 86400)),
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
