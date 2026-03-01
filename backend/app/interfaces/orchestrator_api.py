from __future__ import annotations

from app.config import settings
from app.contracts.agent_contract import AgentContract, SendEvent
from app.interfaces.request_context import RequestContext
from app.orchestrator.events import build_lifecycle_event
from app.orchestrator.pipeline_runner import PipelineRunner
from app.orchestrator.session_lane_manager import SessionLaneManager
from app.state import StateStore


class OrchestratorApi:
    def __init__(self, agent: AgentContract, state_store: StateStore):
        self._runner = PipelineRunner(agent=agent, state_store=state_store)
        self._lane_manager = SessionLaneManager(
            global_max_concurrent=settings.session_lane_global_max_concurrent,
        )

    async def run_user_message(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        request_context: RequestContext,
    ) -> str:
        await send_event(
            build_lifecycle_event(
                request_id=request_context.request_id,
                session_id=request_context.session_id,
                stage="queued",
                details={},
                agent=self._runner.agent.name,
            )
        )

        async def on_lane_acquired(details: dict) -> None:
            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="lane_acquired",
                    details=details,
                    agent=self._runner.agent.name,
                )
            )

        async def on_lane_released(details: dict) -> None:
            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="lane_released",
                    details=details,
                    agent=self._runner.agent.name,
                )
            )

        async def run_in_lane() -> str:
            return await self._runner.run(
                user_message=user_message,
                send_event=send_event,
                session_id=request_context.session_id,
                request_id=request_context.request_id,
                runtime=request_context.runtime,
                model=request_context.model,
                tool_policy=request_context.tool_policy,
            )

        return await self._lane_manager.run_in_lane(
            session_id=request_context.session_id,
            on_acquired=on_lane_acquired,
            run=run_in_lane,
            on_released=on_lane_released,
        )
