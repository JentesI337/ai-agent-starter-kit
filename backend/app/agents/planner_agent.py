from __future__ import annotations

import json

from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import PlannerInput, PlannerOutput
from app.llm_client import LlmClient
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.request_normalization import normalize_prompt_mode
from app.tool_policy import ToolPolicyDict


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

    def __init__(self, client: LlmClient, system_prompt: str):
        self.client = client
        self.system_prompt = system_prompt
        self._kernel_builder = PromptKernelBuilder()

    @property
    def name(self) -> str:
        return "planner-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        self.client = LlmClient(base_url=base_url, model=model)

    @staticmethod
    def _requires_hard_research_structure(user_message: str) -> bool:
        normalized = (user_message or "").lower()
        return (
            "architektur-risiken" in normalized
            and "performance-hotspots" in normalized
            and "guardrail-lücken" in normalized
            and "rollout-plan" in normalized
            and "3 phasen" in normalized
        )

    async def execute(self, payload: PlannerInput, model: str | None = None) -> PlannerOutput:
        planner_instructions = (
            "Create a short execution plan (2-5 bullets) for the user's request.\n"
            "If the request is simple (greeting, small talk, or direct question), keep the plan minimal.\n"
            "If the request is technical or coding-related, include actionable implementation steps."
        )
        prompt_mode = normalize_prompt_mode(payload.prompt_mode, default="full")
        sections = {
            "instructions": planner_instructions,
            "reduced_context": payload.reduced_context,
            "current_task": payload.user_message,
        }
        if self._requires_hard_research_structure(payload.user_message):
            sections["hard_contract"] = (
                "Mandatory response contract for this request:\n"
                "- Ensure final answer contains these sections exactly once: "
                "Architektur-Risiken, Performance-Hotspots, Guardrail-Lücken, "
                "Priorisierte Maßnahmen (Top 10), Messbare KPIs, Rollout-Plan.\n"
                "- Include Top 10 numbered items in the measures section.\n"
                "- Include rollout phases explicitly named 'Phase 1', 'Phase 2', 'Phase 3'.\n"
                "- Include at least two KPI lines with measurable values (% or ms or s)."
            )
        kernel = self._kernel_builder.build(
            prompt_type="planning",
            prompt_mode=prompt_mode,
            sections=sections,
        )
        plan = await self.client.complete_chat(
            self.system_prompt,
            kernel.rendered,
            model=model,
            temperature=self.constraints.temperature,
        )
        return PlannerOutput(plan_text=plan)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        prompt_mode: str | None = None,
    ) -> str:
        payload = PlannerInput.model_validate_json(user_message)
        if prompt_mode:
            payload = payload.model_copy(update={"prompt_mode": prompt_mode})
        result = await self.execute(payload, model=model)
        return json.dumps(result.model_dump(), ensure_ascii=False)
