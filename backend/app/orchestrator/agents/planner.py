"""
Planner Agent — single responsibility: decompose a user request into
a structured plan of discrete steps.

Receives a state slice, never the full store.
Outputs JSON-only via PlannerOutput schema.
No cross-agent implicit knowledge.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.orchestrator.contracts.schemas import (
    AgentConstraints,
    AgentContract,
    AgentRole,
    PlannerInput,
    PlannerOutput,
    PlanStep,
    TaskComplexity,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Contract definition
# ------------------------------------------------------------------

PLANNER_CONTRACT = AgentContract(
    role=AgentRole.PLANNER,
    description="Decomposes user requests into structured, executable plan steps.",
    input_schema=PlannerInput.model_json_schema(),
    output_schema=PlannerOutput.model_json_schema(),
    constraints=AgentConstraints(
        max_context_tokens=4000,
        temperature=0.3,
        max_reflection_passes=0,  # Linear, deterministic in Phase 1
        max_output_tokens=2048,
        timeout_seconds=60.0,
    ),
)

# ------------------------------------------------------------------
# System prompt (clean — no state logic)
# ------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are a planning agent. Your ONLY job is to decompose a user request into a \
structured list of plan steps.

Rules:
- Output ONLY valid JSON matching the output schema.
- Each step has: step_id (int), description (str), tool (str|null), tool_args (dict), depends_on (list[int]).
- Available tools: list_dir, read_file, write_file, run_command.
- Steps must be atomic — one clear action each.
- Set depends_on to reference earlier step_ids when ordering matters.
- Estimate task complexity: simple, moderate, or complex.
- Do NOT include reasoning outside the JSON object.
- Do NOT reference chat history, memory, or prior sessions.

Output schema:
{
  "steps": [...],
  "estimated_complexity": "simple" | "moderate" | "complex",
  "reasoning": "brief explanation"
}
"""


class PlannerAgent:
    """
    Stateless planner agent. Receives input, returns structured output.
    All state lives in the orchestrator, not here.
    """

    def __init__(self) -> None:
        self.contract = PLANNER_CONTRACT

    def build_prompt(self, validated_input: PlannerInput) -> tuple[str, str]:
        """
        Build (system_prompt, user_prompt) from validated input.
        The model receives a *slice* — only what it needs.
        """
        user_parts = [f"User request: {validated_input.user_message}"]

        if validated_input.context_summary:
            user_parts.append(f"\nContext summary:\n{validated_input.context_summary}")

        if validated_input.evidence:
            user_parts.append(f"\nEvidence from exploration:\n{validated_input.evidence}")

        user_parts.append(f"\nTask complexity hint: {validated_input.task_complexity.value}")

        return PLANNER_SYSTEM_PROMPT, "\n".join(user_parts)

    def parse_output(self, raw_text: str) -> PlannerOutput:
        """
        Parse LLM response into validated PlannerOutput.
        Handles common issues (markdown fences, trailing text).
        """
        cleaned = self._extract_json(raw_text)
        try:
            data = json.loads(cleaned)
            return PlannerOutput.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("planner parse_failed raw_len=%d error=%s", len(raw_text), exc)
            # Fallback: single step with the raw text as description
            return PlannerOutput(
                steps=[PlanStep(step_id=1, description=raw_text[:500])],
                estimated_complexity=TaskComplexity.SIMPLE,
                reasoning="Failed to parse structured output; created fallback single step.",
            )

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip markdown fences and extra text around JSON."""
        text = text.strip()
        # Remove ```json ... ``` blocks
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{"):
                    return stripped
        # Try to find raw JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text
