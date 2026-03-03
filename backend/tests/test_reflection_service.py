from __future__ import annotations

import asyncio

from app.services.reflection_service import ReflectionService


class _FakeClient:
    def __init__(self, response: str):
        self.response = response

    async def complete_chat(self, system_prompt: str, user_prompt: str, model: str | None = None, temperature: float | None = None) -> str:
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
    assert verdict.issues
