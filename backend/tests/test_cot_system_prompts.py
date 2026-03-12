from __future__ import annotations

from pathlib import Path


def test_default_prompt_templates_contain_cot_keywords() -> None:
    config_path = Path(__file__).resolve().parents[1] / "app" / "config" / "settings.py"
    source = config_path.read_text(encoding="utf-8")

    assert "head_agent_system_prompt" in source
    assert "head_agent_plan_prompt" in source
    assert "head_agent_final_prompt" in source
    assert "coder_agent_system_prompt" in source
    assert "coder_agent_plan_prompt" in source
    assert "coder_agent_final_prompt" in source
    assert "agent_system_prompt" in source
    assert "agent_plan_prompt" in source
    assert "agent_final_prompt" in source

    assert "UNDERSTAND: Restate the user's goal" in source
    assert "CLASSIFY the request" in source
    assert "Before writing your answer, internally verify" in source
    assert "CLARIFICATION_NEEDED" in source
