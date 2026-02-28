from __future__ import annotations

from app.contracts.agent_contract import AgentContract, SendEvent
from app.errors import LlmClientError
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

        final_text = await self._run_with_fallback(
            user_message=user_message,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            route=route,
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
    ) -> str:
        models = [route.primary_model, *route.fallback_models]
        last_error: Exception | None = None

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
                            details={"to": candidate_model},
                            agent=self.agent.name,
                        )
                    )

                return await self.agent.run(
                    user_message=user_message,
                    send_event=send_event,
                    session_id=session_id,
                    request_id=request_id,
                    model=candidate_model,
                )
            except LlmClientError as exc:
                last_error = exc
                if index >= len(models) - 1:
                    raise
                if not self._is_model_not_found_error(str(exc)):
                    raise

        if isinstance(last_error, LlmClientError):
            raise last_error
        raise LlmClientError("Model routing failed before execution.")

    def _is_model_not_found_error(self, message: str) -> bool:
        text = (message or "").lower()
        return "model" in text and "not found" in text
