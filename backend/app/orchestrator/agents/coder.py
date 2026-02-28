"""
Coder Agent — single responsibility: execute a plan step by producing
file changes and/or commands.

Receives a state slice (plan step + file context), never the full store.
Outputs JSON-only via CoderOutput schema.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.orchestrator.contracts.schemas import (
    AgentConstraints,
    AgentContract,
    AgentRole,
    CoderInput,
    CoderOutput,
    FileChange,
    TaskComplexity,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Contract
# ------------------------------------------------------------------

CODER_CONTRACT = AgentContract(
    role=AgentRole.CODER,
    description="Executes a single plan step by generating file changes and/or shell commands.",
    input_schema=CoderInput.model_json_schema(),
    output_schema=CoderOutput.model_json_schema(),
    constraints=AgentConstraints(
        max_context_tokens=6000,
        temperature=0.2,
        max_reflection_passes=0,
        max_output_tokens=4096,
        timeout_seconds=90.0,
    ),
)

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

CODER_SYSTEM_PROMPT = """\
You are a coding agent. Your ONLY job is to implement a single plan step.

Rules:
- Output ONLY valid JSON matching the output schema.
- For file changes, provide the full file content (not diffs).
- Each FileChange has: path (str), action ("write"|"delete"), content (str).
- For shell commands, provide them in the "commands" list.
- Set success=true if you completed the step, false if you encountered an error.
- Include brief reasoning in the "reasoning" field.
- Do NOT reference chat history, memory, or other agents.

Output schema:
{
  "changes": [{"path": "...", "action": "write", "content": "..."}],
  "commands": ["..."],
  "reasoning": "brief explanation",
  "success": true,
  "error": null
}
"""


class CoderAgent:
    """
    Stateless coder agent. Receives a plan step + context, returns changes.
    All state lives in the orchestrator.
    """

    def __init__(self) -> None:
        self.contract = CODER_CONTRACT

    def build_prompt(self, validated_input: CoderInput) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) from validated input."""
        user_parts: list[str] = []

        step = validated_input.plan_step
        user_parts.append(f"Plan step #{step.step_id}: {step.description}")
        if step.tool:
            user_parts.append(f"Suggested tool: {step.tool}")
        if step.tool_args:
            user_parts.append(f"Tool args: {json.dumps(step.tool_args)}")

        if validated_input.context_summary:
            user_parts.append(f"\nContext:\n{validated_input.context_summary}")

        if validated_input.file_contents:
            user_parts.append("\nRelevant files:")
            for path, content in validated_input.file_contents.items():
                # Truncate large files
                preview = content[:3000]
                if len(content) > 3000:
                    preview += "\n... [truncated]"
                user_parts.append(f"\n--- {path} ---\n{preview}")

        if validated_input.evidence:
            user_parts.append(f"\nAdditional evidence:\n{validated_input.evidence}")

        return CODER_SYSTEM_PROMPT, "\n".join(user_parts)

    def parse_output(self, raw_text: str) -> CoderOutput:
        """Parse LLM response into validated CoderOutput."""
        cleaned = self._extract_json(raw_text)
        try:
            data = json.loads(cleaned)
            return CoderOutput.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("coder parse_failed raw_len=%d error=%s", len(raw_text), exc)
            return CoderOutput(
                success=False,
                error=f"Failed to parse coder output: {exc}",
                reasoning=raw_text[:500],
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
