from __future__ import annotations

from app.agent import HeadAgent


def test_classify_tool_results_state_variants() -> None:
    agent = HeadAgent()

    assert agent._classify_tool_results_state(None) == "empty"
    assert agent._classify_tool_results_state("") == "empty"
    assert agent._classify_tool_results_state("[run_command] ERROR: blocked") == "error_only"
    assert agent._classify_tool_results_state("[read_file] OK: content") == "usable"
    assert agent._classify_tool_results_state("[read_file] OK\n[run_command] ERROR: blocked") == "usable"
    blocked_payload = agent._encode_blocked_tool_result(
        blocked_with_reason="policy_block",
        message="blocked",
    )
    assert agent._classify_tool_results_state(blocked_payload) == "blocked"


def test_resolve_replan_reason_uses_regular_budget_first() -> None:
    agent = HeadAgent()

    reason = agent._resolve_replan_reason(
        tool_results_state="error_only",
        iteration=0,
        max_replan_iterations=2,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=0,
    )

    assert reason == "tool_results_invalidated_plan"


def test_resolve_replan_reason_allows_single_empty_fallback_after_regular_budget() -> None:
    agent = HeadAgent()

    first = agent._resolve_replan_reason(
        tool_results_state="empty",
        iteration=0,
        max_replan_iterations=1,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=0,
    )
    second = agent._resolve_replan_reason(
        tool_results_state="empty",
        iteration=1,
        max_replan_iterations=1,
        empty_tool_replan_attempts_used=1,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=0,
    )

    assert first == "tool_selection_empty_replan"
    assert second is None


def test_resolve_replan_reason_uses_bounded_error_only_budget() -> None:
    agent = HeadAgent()

    first = agent._resolve_replan_reason(
        tool_results_state="error_only",
        iteration=0,
        max_replan_iterations=1,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=1,
    )
    second = agent._resolve_replan_reason(
        tool_results_state="error_only",
        iteration=1,
        max_replan_iterations=1,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=1,
        max_error_tool_replan_attempts=1,
    )

    assert first == "tool_selection_error_replan"
    assert second is None
