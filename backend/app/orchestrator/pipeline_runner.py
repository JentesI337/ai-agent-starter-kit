from __future__ import annotations

from app.contracts.agent_contract import AgentContract, SendEvent
from app.config import settings
from app.errors import GuardrailViolation, LlmClientError
from app.model_routing.context_window_guard import evaluate_context_window_guard
from app.model_routing import ModelRouter
from app.orchestrator.events import LifecycleStage, build_lifecycle_event
from app.orchestrator.step_types import PipelineStep
from app.state import StateStore


class PipelineRunner:
    def __init__(self, agent: AgentContract, state_store: StateStore):
        self.agent = agent
        self.state_store = state_store
        self.model_router = ModelRouter()

    async def run(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        runtime: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
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
        route,
        tool_policy: dict[str, list[str]] | None,
    ) -> str:
        models = [route.primary_model, *route.fallback_models]
        last_error: Exception | None = None
        last_reason = "unknown"

        for index, candidate_model in enumerate(models):
            try:
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
                            details={"to": candidate_model, "reason": last_reason},
                            agent=self.agent.name,
                        )
                    )

                return await self.agent.run(
                    user_message=user_message,
                    send_event=send_event,
                    session_id=session_id,
                    request_id=request_id,
                    model=candidate_model,
                    tool_policy=tool_policy,
                )
            except LlmClientError as exc:
                last_error = exc
                reason = self._classify_failover_reason(str(exc))
                last_reason = reason
                retryable = self._is_retryable_failover_reason(reason)
                has_fallback = index < len(models) - 1

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

                if index >= len(models) - 1:
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
            raise last_error
        raise LlmClientError("Model routing failed before execution.")

    def _classify_failover_reason(self, message: str) -> str:
        text = (message or "").lower()
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
