from __future__ import annotations

import json
from typing import Protocol

from app.config import settings
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import PlannerInput, PlannerOutput
from app.llm_client import LlmClient
from app.services.plan_graph import PlanGraph
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.request_normalization import normalize_prompt_mode
from app.tool_policy import ToolPolicyDict


class FailureRetrieverContract(Protocol):
    def retrieve(self, query: str, *, sources: tuple[str, ...], top_k: int) -> list[object]:
        ...


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

    def __init__(self, client: LlmClient, system_prompt: str, failure_retriever: FailureRetrieverContract | None = None):
        self.client = client
        self.system_prompt = system_prompt
        self._kernel_builder = PromptKernelBuilder()
        self._failure_retriever = failure_retriever

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
        if self._failure_retriever is not None and settings.failure_context_enabled:
            similar_failures = self._failure_retriever.retrieve(
                payload.user_message,
                sources=("failure_journal",),
                top_k=3,
            )
            if similar_failures:
                sections["failure_context"] = self._format_failure_context(similar_failures)
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

    @staticmethod
    def _format_failure_context(similar_failures: list[object]) -> str:
        lines: list[str] = []
        for item in similar_failures[:3]:
            task_description = str(getattr(item, "task_description", "") or "").strip()
            root_cause = str(getattr(item, "root_cause", "") or "").strip()
            solution = str(getattr(item, "solution", "") or "").strip()
            tags = getattr(item, "tags", [])
            tags_text = ", ".join(str(tag).strip() for tag in (tags or []) if str(tag).strip())
            lines.append(
                f"- Task: {task_description[:180]} | Root cause: {root_cause[:180]} | "
                f"Fix: {solution[:180]} | Tags: {tags_text[:120]}"
            )
        return "\n".join(lines)

    async def execute_structured(self, payload: PlannerInput, model: str | None = None) -> PlanGraph:
        structured_instructions = (
            "Analyze this request and create a structured execution plan.\n"
            "Return JSON with this schema:\n"
            '{"goal": "...", "complexity": "trivial|moderate|complex", '
            '"steps": [{"step_id": "s1", "action": "...", "tool": "...|none", '
            '"depends_on": [], "fallback": "..."|null}], '
            '"clarification_needed": "..."|null}\n\n'
            "Rules:\n"
            "- trivial requests (greetings, simple questions): 1 step, tool='none'\n"
            "- moderate requests: 1-3 steps with specific tools\n"
            "- complex requests: 3-7 steps with dependency graph\n"
            "- Always include fallback strategies for steps that might fail\n"
            "- Mark steps that can run in parallel (no dependencies between them)"
        )
        prompt_mode = normalize_prompt_mode(payload.prompt_mode, default="minimal")
        kernel = self._kernel_builder.build(
            prompt_type="planning",
            prompt_mode=prompt_mode,
            sections={
                "instructions": structured_instructions,
                "reduced_context": payload.reduced_context,
                "current_task": payload.user_message,
            },
        )
        raw_plan = await self.client.complete_chat(
            self.system_prompt,
            kernel.rendered,
            model=model,
            temperature=self.constraints.temperature,
        )
        return self._parse_structured_plan(raw_plan)

    def _parse_structured_plan(self, raw_plan: str) -> PlanGraph:
        try:
            payload = json.loads(raw_plan)
        except Exception:
            payload = None

        if not isinstance(payload, dict):
            extracted = self._extract_json_object(raw_plan)
            if extracted is not None:
                payload = extracted

        if isinstance(payload, dict):
            return PlanGraph.from_dict(payload, max_steps=max(1, int(settings.plan_max_steps)))

        return PlanGraph(
            goal="Execution plan",
            complexity="moderate",
            steps=[
                PlanGraph.from_dict(
                    {
                        "steps": [
                            {
                                "step_id": "s1",
                                "action": (raw_plan or "Provide direct answer").strip()[:300],
                                "tool": "none",
                                "depends_on": [],
                                "fallback": "Ask for clarification if needed",
                            }
                        ]
                    }
                ).steps[0]
            ],
        )

    @staticmethod
    def _extract_json_object(raw_plan: str) -> dict | None:
        text = (raw_plan or "").strip()
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            return None
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

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
