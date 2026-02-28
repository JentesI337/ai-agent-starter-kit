from __future__ import annotations

from app.contracts.agent_contract import AgentContract, SendEvent
from app.interfaces.request_context import RequestContext
from app.orchestrator.pipeline_runner import PipelineRunner
from app.state import StateStore


class OrchestratorApi:
    def __init__(self, agent: AgentContract, state_store: StateStore):
        self._runner = PipelineRunner(agent=agent, state_store=state_store)

    async def run_user_message(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        request_context: RequestContext,
    ) -> str:
        return await self._runner.run(
            user_message=user_message,
            send_event=send_event,
            session_id=request_context.session_id,
            request_id=request_context.request_id,
            runtime=request_context.runtime,
            model=request_context.model,
        )
