from __future__ import annotations

from app.agent import HeadAgent


def test_build_root_cause_replan_prompt_contains_required_sections() -> None:
    agent = HeadAgent()

    prompt = agent._build_root_cause_replan_prompt(
        user_message="Fix failing integration tests",
        previous_plan="1. run tests\n2. patch code",
        tool_results="[run_command] ERROR: pytest failed",
    )

    assert "ROOT CAUSE" in prompt
    assert "LESSON LEARNED" in prompt
    assert "NEW PLAN" in prompt
    assert "Fix failing integration tests" in prompt
