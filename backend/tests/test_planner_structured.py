from __future__ import annotations

import asyncio

from app.agents.planner_agent import PlannerAgent
from app.contracts.schemas import PlannerInput


class _FakeStructuredClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def complete_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        _ = (system_prompt, user_prompt, model, temperature)
        return self.response


def _payload() -> PlannerInput:
    return PlannerInput(user_message="Implement endpoint", reduced_context="ctx", prompt_mode="minimal")


def test_execute_structured_parses_plan_graph() -> None:
    client = _FakeStructuredClient(
        '{"goal":"Build API","complexity":"moderate","steps":[{"step_id":"s1","action":"Read docs","tool":"read_file","depends_on":[],"fallback":"ask user"}]}'
    )
    agent = PlannerAgent(client=client, system_prompt="sys")

    async def _run():
        return await agent.execute_structured(_payload(), model=None)

    graph = asyncio.run(_run())

    assert graph.goal == "Build API"
    assert graph.complexity == "moderate"
    assert len(graph.steps) == 1
    assert graph.steps[0].step_id == "s1"


def test_execute_structured_extracts_embedded_json() -> None:
    client = _FakeStructuredClient(
        'Here is your plan:\n```json\n{"goal":"Do work","complexity":"trivial","steps":[{"step_id":"s1","action":"Answer","tool":"none","depends_on":[],"fallback":null}]}\n```'
    )
    agent = PlannerAgent(client=client, system_prompt="sys")

    async def _run():
        return await agent.execute_structured(_payload(), model=None)

    graph = asyncio.run(_run())

    assert graph.goal == "Do work"
    assert graph.steps[0].action == "Answer"
