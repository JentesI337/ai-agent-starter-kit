from __future__ import annotations

import json

from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import PlannerInput, PlannerOutput
from app.llm_client import LlmClient


class PlannerAgent(AgentContract):
    role = "planner-agent"
    input_schema = PlannerInput
    output_schema = PlannerOutput
    constraints = AgentConstraints(
        max_context=4096,
        temperature=0.2,
        reasoning_depth=2,
        reflection_passes=0,
        combine_steps=False,
    )

    def __init__(self, client: LlmClient):
        self.client = client

    @property
    def name(self) -> str:
        return "planner-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        self.client = LlmClient(base_url=base_url, model=model)

    async def execute(self, payload: PlannerInput, model: str | None = None) -> PlannerOutput:
        planner_prompt = (
            "Create a short execution plan (2-5 bullets) for the user's request.\n"
            "If the request is simple (greeting, small talk, or direct question), keep the plan minimal.\n"
            "If the request is technical or coding-related, include actionable implementation steps.\n\n"
            "Reduced context:\n"
            f"{payload.reduced_context}\n\n"
            "Current task:\n"
            f"{payload.user_message}"
        )
        plan = await self.client.complete_chat(
            settings.agent_plan_prompt,
            planner_prompt,
            model=model,
        )
        return PlannerOutput(plan_text=plan)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
    ) -> str:
        payload = PlannerInput.model_validate_json(user_message)
        result = await self.execute(payload, model=model)
        return json.dumps(result.model_dump(), ensure_ascii=False)
