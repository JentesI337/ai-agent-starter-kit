from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import SynthesizerInput, SynthesizerOutput
from app.llm_client import LlmClient

EmitLifecycleFn = Callable[[SendEvent, str, str, str, dict | None], Awaitable[None]]


class SynthesizerAgent(AgentContract):
    role = "synthesizer-agent"
    input_schema = SynthesizerInput
    output_schema = SynthesizerOutput
    constraints = AgentConstraints(
        max_context=8192,
        temperature=0.3,
        reasoning_depth=2,
        reflection_passes=0,
        combine_steps=True,
    )

    def __init__(self, *, client: LlmClient, agent_name: str, emit_lifecycle_fn: EmitLifecycleFn):
        self.client = client
        self.agent_name = agent_name
        self._emit_lifecycle_fn = emit_lifecycle_fn

    @property
    def name(self) -> str:
        return "synthesizer-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        self.client = LlmClient(base_url=base_url, model=model)

    async def execute(
        self,
        payload: SynthesizerInput,
        *,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None,
    ) -> SynthesizerOutput:
        final_prompt = (
            "User request:\n"
            f"{payload.user_message}\n\n"
            "Plan:\n"
            f"{payload.plan_text}\n\n"
            "Tool outputs:\n"
            f"{payload.tool_results or '(no tool outputs)'}\n\n"
            "Relevant memory:\n"
            f"{payload.reduced_context}\n\n"
            "Generate a concise, helpful final answer.\n"
            "For general requests, respond naturally without forcing implementation steps.\n"
            "For coding/technical requests, include concrete next implementation steps.\n"
            "If Tool outputs include web_fetch data, you MUST ground the answer in that data.\n"
            "When web_fetch data exists, do not claim browsing is unavailable and do not ignore fetched content.\n"
            "Include a short 'Sources used' section with source_url values found in tool outputs when available.\n"
            "Do not emit tool directives, no [TOOL_CALL] blocks, and no pseudo tool syntax.\n"
            "Only report completed actions and clear next steps."
        )

        await self._emit_lifecycle_fn(
            send_event,
            "streaming_started",
            request_id,
            session_id,
            None,
        )

        output_parts: list[str] = []
        async for token in self.client.stream_chat_completion(
            settings.agent_final_prompt,
            final_prompt,
            model=model,
        ):
            output_parts.append(token)
            await send_event({"type": "token", "agent": self.agent_name, "token": token})

        final_text = "".join(output_parts).strip()
        await self._emit_lifecycle_fn(
            send_event,
            "streaming_completed",
            request_id,
            session_id,
            {"output_chars": len(final_text)},
        )

        return SynthesizerOutput(final_text=final_text)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
    ) -> str:
        payload = SynthesizerInput.model_validate_json(user_message)
        result = await self.execute(
            payload,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            model=model,
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)
