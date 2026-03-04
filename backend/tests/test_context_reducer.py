from __future__ import annotations

from app.agent import HeadAgent
from app.state.context_reducer import ContextReducer


def test_context_reducer_honors_token_budget() -> None:
    reducer = ContextReducer()
    user_message = "implement feature x"
    memory = ["memory item " + ("a" * 400)] * 8
    tools = ["tool output " + ("b" * 700)] * 4

    reduced = reducer.reduce(
        budget_tokens=300,
        user_message=user_message,
        memory_lines=memory,
        tool_outputs=tools,
    )

    assert reduced.budget_tokens == 300
    assert reduced.used_tokens <= 300
    assert "Current task:" in reduced.rendered


def test_agent_step_budgets_sum_to_total_context() -> None:
    agent = HeadAgent()

    budgets = agent._step_budgets(8000)

    assert budgets["plan"] == 2000
    assert budgets["tool"] == 2400
    assert budgets["final"] == 3600
    assert sum(budgets.values()) == 8000


def test_context_reducer_token_estimation_is_token_based() -> None:
    reducer = ContextReducer()

    tokens = reducer.estimate_tokens("alpha beta, gamma!")

    assert tokens >= 5
