from __future__ import annotations

import asyncio

from app.agents.planner_agent import PlannerAgent
from app.contracts.schemas import PlannerInput


class _FakePlannerClient:
    def __init__(self) -> None:
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None

    async def complete_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return "- step 1\n- step 2"


def _payload(message: str) -> PlannerInput:
    return PlannerInput(
        user_message=message,
        reduced_context="ctx",
    )


def test_planner_adds_hard_contract_instructions_when_required() -> None:
    client = _FakePlannerClient()
    agent = PlannerAgent(client=client, system_prompt="sys")

    message = (
        "Erstelle eine Analyse mit Architektur-Risiken, Performance-Hotspots, Guardrail-Lücken "
        "und Rollout-Plan in 3 Phasen."
    )

    async def _run() -> None:
        await agent.execute(_payload(message), model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "Mandatory response contract" in client.last_user_prompt
    assert "Priorisierte Maßnahmen (Top 10)" in client.last_user_prompt


def test_planner_keeps_normal_prompt_for_non_hard_request() -> None:
    client = _FakePlannerClient()
    agent = PlannerAgent(client=client, system_prompt="sys")

    async def _run() -> None:
        await agent.execute(_payload("Sag kurz hallo"), model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "Mandatory response contract" not in client.last_user_prompt
