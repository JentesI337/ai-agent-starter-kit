from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.quality.reflection_service import _REFLECTION_SYSTEM_PROMPT, ReflectionService


class _FakeClient:
    def __init__(self, response: str):
        self.response = response
        self.last_system_prompt: str | None = None

    async def complete_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        self.last_system_prompt = system_prompt
        _ = (system_prompt, user_prompt, model, temperature)
        return self.response


def test_reflection_service_parses_json_verdict_and_threshold() -> None:
    service = ReflectionService(
        client=_FakeClient(
            '{"goal_alignment": 0.9, "completeness": 0.6, "factual_grounding": 0.3, "issues": ["missing evidence"], "suggested_fix": "cite source"}'
        ),
        threshold=0.7,
    )

    verdict = asyncio.run(
        service.reflect(
            user_message="What changed?",
            plan_text="Check files and summarize.",
            tool_results="[read_file] [OK] updated agent.py",
            final_answer="I changed things.",
        )
    )

    assert verdict.goal_alignment == 0.9
    assert verdict.completeness == 0.6
    assert verdict.factual_grounding == 0.3
    assert verdict.score == (0.9 + 0.6 + 0.3) / 3
    assert verdict.issues == ["missing evidence"]
    assert verdict.suggested_fix == "cite source"
    assert verdict.should_retry is True


def test_reflection_service_fallback_when_verdict_unparseable() -> None:
    service = ReflectionService(client=_FakeClient("not-json-output"), threshold=0.5)

    verdict = service._parse_verdict("not-json-output")

    assert verdict.score == 0.0
    assert verdict.should_retry is True
    assert verdict.issues == ["Unable to parse reflection verdict from model output."]


def test_reflection_service_extracts_embedded_json_object() -> None:
    service = ReflectionService(
        client=_FakeClient(
            "Model analysis:\n"
            '{"goal_alignment":0.7,"completeness":0.8,"factual_grounding":0.9,'
            '"issues":[],"suggested_fix":null}'
        ),
        threshold=0.79,
    )

    verdict = asyncio.run(
        service.reflect(
            user_message="Summarize changes",
            plan_text="Read git diff and summarize.",
            tool_results="[OK] read_file: agent.py",
            final_answer="Summary generated.",
        )
    )

    assert verdict.goal_alignment == 0.7
    assert verdict.completeness == 0.8
    assert verdict.factual_grounding == 0.9
    assert verdict.score == (0.7 + 0.8 + 0.9) / 3
    assert verdict.should_retry is False


def test_hard_gate_triggers_retry_when_fg_below_min() -> None:
    client = _FakeClient(
        '{"goal_alignment": 0.9, "completeness": 0.9, "factual_grounding": 0.3, '
        '"issues": ["hallucinated PID"], "suggested_fix": null}'
    )
    service = ReflectionService(client=client, threshold=0.6, factual_grounding_hard_min=0.4)

    verdict = asyncio.run(
        service.reflect(
            user_message="check process",
            plan_text="run netstat",
            tool_results="no output",
            final_answer="PID 1234 is listening on port 8080",
        )
    )

    assert verdict.hard_factual_fail is True
    assert verdict.should_retry is True
    assert verdict.score == pytest.approx(0.7, abs=0.01)


def test_hard_gate_not_triggered_when_fg_at_min() -> None:
    client = _FakeClient(
        '{"goal_alignment": 0.8, "completeness": 0.8, "factual_grounding": 0.4, '
        '"issues": [], "suggested_fix": null}'
    )
    service = ReflectionService(client=client, threshold=0.6, factual_grounding_hard_min=0.4)

    verdict = asyncio.run(
        service.reflect(
            user_message="q",
            plan_text="p",
            tool_results="t",
            final_answer="a",
        )
    )

    assert verdict.hard_factual_fail is False


def test_hard_factual_fail_field_exists_on_verdict() -> None:
    client = _FakeClient(
        '{"goal_alignment": 1.0, "completeness": 1.0, "factual_grounding": 1.0, '
        '"issues": [], "suggested_fix": null}'
    )
    service = ReflectionService(client=client)

    verdict = asyncio.run(
        service.reflect(
            user_message="q",
            plan_text="p",
            tool_results="t",
            final_answer="a",
        )
    )

    assert hasattr(verdict, "hard_factual_fail")
    assert verdict.hard_factual_fail is False


def test_prompt_uses_configurable_tool_results_limit() -> None:
    service = ReflectionService(client=MagicMock(), tool_results_max_chars=200)
    long_output = "x" * 5000

    prompt = service._build_reflection_prompt(
        user_message="q",
        plan_text="p",
        tool_results=long_output,
        final_answer="a",
    )

    assert "x" * 500 in prompt
    assert "x" * 501 not in prompt


def test_prompt_uses_configurable_plan_limit() -> None:
    service = ReflectionService(client=MagicMock(), plan_max_chars=100)
    long_plan = "p" * 5000

    prompt = service._build_reflection_prompt(
        user_message="q",
        plan_text=long_plan,
        tool_results="t",
        final_answer="a",
    )

    assert "p" * 200 in prompt
    assert "p" * 201 not in prompt


def test_default_tool_results_limit_is_8000() -> None:
    service = ReflectionService(client=MagicMock())
    assert service.tool_results_max_chars == 8000


def test_reflection_system_prompt_contains_factual_grounding_directive() -> None:
    assert "factual_grounding" in _REFLECTION_SYSTEM_PROMPT.lower()
    assert "0.4" in _REFLECTION_SYSTEM_PROMPT
    assert "verbatim" in _REFLECTION_SYSTEM_PROMPT.lower()


def test_reflect_passes_directive_system_prompt() -> None:
    client = _FakeClient(
        '{"goal_alignment": 0.8, "completeness": 0.8, "factual_grounding": 0.8, '
        '"issues": [], "suggested_fix": null}'
    )
    service = ReflectionService(client=client)

    asyncio.run(
        service.reflect(
            user_message="q",
            plan_text="p",
            tool_results="t",
            final_answer="a",
        )
    )

    assert client.last_system_prompt == _REFLECTION_SYSTEM_PROMPT
