from __future__ import annotations

from app.agent import HeadCodingAgent
from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import HeadCoderInput, HeadCoderOutput


class HeadCoderAgentAdapter(AgentContract):
    role = "coding-head-agent"
    input_schema = HeadCoderInput
    output_schema = HeadCoderOutput
    constraints = AgentConstraints(
        max_context=settings.max_user_message_length,
        temperature=0.3,
        reasoning_depth=2,
        reflection_passes=0,
        combine_steps=False,
    )

    def __init__(self, delegate: HeadCodingAgent | None = None):
        self._delegate = delegate or HeadCodingAgent()

    @property
    def name(self) -> str:
        return self._delegate.name

    def configure_runtime(self, base_url: str, model: str) -> None:
        self._delegate.configure_runtime(base_url=base_url, model=model)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
    ) -> str:
        payload = self.input_schema(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            model=model,
        )
        final_text = await self._delegate.run(
            payload.user_message,
            send_event,
            session_id=payload.session_id,
            request_id=payload.request_id,
            model=payload.model,
        )
        output = self.output_schema(final_text=final_text)
        return output.final_text
