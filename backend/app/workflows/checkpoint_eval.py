"""Checkpoint evaluation — assert mode and agent (LLM) mode.

Two evaluation strategies for recipe checkpoints:
- evaluate_assert: uses transforms.evaluate_condition() for concrete boolean assertions
- evaluate_agent: single LLM call asking if evidence satisfies a rubric
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_assert(expression: str, context: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate a boolean assertion expression against context.

    Returns (passed, explanation).
    """
    from app.workflows.transforms import evaluate_condition

    try:
        result = evaluate_condition(expression, context)
        return result, f"Assertion '{expression}' evaluated to {result}"
    except (ValueError, Exception) as exc:
        return False, f"Assertion evaluation failed: {exc}"


async def evaluate_agent(
    rubric: str,
    evidence: str,
    context: dict[str, Any],
    llm_client: Any,
) -> tuple[bool, str]:
    """Use an LLM call to evaluate whether evidence satisfies a rubric.

    Returns (passed, explanation).
    """
    system_prompt = (
        "You are a checkpoint evaluator. Given a rubric and evidence, "
        "determine whether the evidence satisfies the rubric.\n\n"
        "Respond with EXACTLY one line in this format:\n"
        "PASS: <brief explanation>\n"
        "or\n"
        "FAIL: <brief explanation>\n\n"
        "Nothing else."
    )

    user_prompt = (
        f"Rubric: {rubric}\n\n"
        f"Evidence: {evidence}\n\n"
        f"Does the evidence satisfy the rubric?"
    )

    try:
        response = await llm_client.complete_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
        )
        response_stripped = response.strip()
        passed = response_stripped.upper().startswith("PASS")
        return passed, response_stripped
    except Exception as exc:
        logger.error("checkpoint_eval_agent_failed error=%s", exc)
        return False, f"Agent evaluation failed: {exc}"
