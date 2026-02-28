"""
Reviewer Agent — single responsibility: review coder output against the
original plan and request.

Provides a confidence score and list of issues.
Outputs JSON-only via ReviewerOutput schema.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.orchestrator.contracts.schemas import (
    AgentConstraints,
    AgentContract,
    AgentRole,
    ReviewerInput,
    ReviewerOutput,
    ReviewIssue,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Contract
# ------------------------------------------------------------------

REVIEWER_CONTRACT = AgentContract(
    role=AgentRole.REVIEWER,
    description="Reviews coder output against the original plan. Provides confidence score and issues.",
    input_schema=ReviewerInput.model_json_schema(),
    output_schema=ReviewerOutput.model_json_schema(),
    constraints=AgentConstraints(
        max_context_tokens=6000,
        temperature=0.2,
        max_reflection_passes=0,
        max_output_tokens=2048,
        timeout_seconds=60.0,
    ),
)

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

REVIEWER_SYSTEM_PROMPT = """\
You are a code review agent. Your ONLY job is to review the coder's output \
against the original plan and user request.

Rules:
- Output ONLY valid JSON matching the output schema.
- Set approved=true only if the implementation correctly addresses the plan.
- List any issues with severity: "info", "warning", or "error".
- Provide a confidence_score (0.0 to 1.0) reflecting your certainty.
- Include brief reasoning.
- Do NOT reference chat history, memory, or other agents.

Output schema:
{
  "approved": true|false,
  "issues": [{"severity": "...", "file": "...", "message": "..."}],
  "confidence_score": 0.85,
  "reasoning": "brief explanation"
}
"""


class ReviewerAgent:
    """
    Stateless reviewer agent. Reviews coder output, returns structured feedback.
    """

    def __init__(self) -> None:
        self.contract = REVIEWER_CONTRACT

    def build_prompt(self, validated_input: ReviewerInput) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) from validated input."""
        user_parts: list[str] = []

        user_parts.append(f"Original user request: {validated_input.original_request}")

        # Plan summary
        plan = validated_input.plan
        user_parts.append(f"\nPlan ({len(plan.steps)} steps, complexity={plan.estimated_complexity.value}):")
        for step in plan.steps:
            user_parts.append(f"  Step {step.step_id}: {step.description}")

        # Coder output
        coder = validated_input.coder_output
        user_parts.append(f"\nCoder result: success={coder.success}")
        if coder.error:
            user_parts.append(f"Coder error: {coder.error}")
        if coder.changes:
            user_parts.append(f"File changes ({len(coder.changes)}):")
            for fc in coder.changes:
                preview = fc.content[:500] if fc.content else "(empty)"
                user_parts.append(f"  {fc.action} {fc.path}: {preview}")
        if coder.commands:
            user_parts.append(f"Commands: {coder.commands}")
        if coder.reasoning:
            user_parts.append(f"Coder reasoning: {coder.reasoning}")

        if validated_input.context_summary:
            user_parts.append(f"\nContext:\n{validated_input.context_summary}")

        return REVIEWER_SYSTEM_PROMPT, "\n".join(user_parts)

    def parse_output(self, raw_text: str) -> ReviewerOutput:
        """Parse LLM response into validated ReviewerOutput."""
        cleaned = self._extract_json(raw_text)
        try:
            data = json.loads(cleaned)
            return ReviewerOutput.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("reviewer parse_failed raw_len=%d error=%s", len(raw_text), exc)
            return ReviewerOutput(
                approved=False,
                confidence_score=0.0,
                reasoning=f"Failed to parse reviewer output: {exc}",
                issues=[ReviewIssue(severity="error", message="Output parsing failed")],
            )

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{"):
                    return stripped
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text
