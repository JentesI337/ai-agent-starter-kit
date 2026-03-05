from __future__ import annotations

from app.agent import HeadAgent


def test_classify_tool_results_state_variants() -> None:
    agent = HeadAgent()

    assert agent._classify_tool_results_state(None) == "empty"
    assert agent._classify_tool_results_state("") == "empty"
    assert agent._classify_tool_results_state("[run_command] ERROR: blocked") == "error_only"
    assert agent._classify_tool_results_state("[read_file] OK: content") == "usable"
    # D-11: mixed OK + ERROR → partial_error (was "usable" before D-11)
    assert agent._classify_tool_results_state("[read_file] OK\n[run_command] ERROR: blocked") == "partial_error"
    blocked_payload = agent._encode_blocked_tool_result(
        blocked_with_reason="policy_block",
        message="blocked",
    )
    assert agent._classify_tool_results_state(blocked_payload) == "blocked"


def test_resolve_replan_reason_uses_regular_budget_first() -> None:
    agent = HeadAgent()

    # When error_tool budget is exhausted (0/0), error_only state should NOT
    # fall through to the generic replan path — that would cause infinite
    # error retry loops (M-1 fix).
    reason = agent._resolve_replan_reason(
        tool_results_state="error_only",
        iteration=0,
        max_replan_iterations=2,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=0,
    )

    assert reason is None


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


# ── D-11: new replan states ──────────────────────────────────────────


def test_classify_partial_error() -> None:
    agent = HeadAgent()
    assert agent._classify_tool_results_state(
        "[read_file] OK: data\n[run_command] ERROR: permission denied"
    ) == "partial_error"


def test_classify_all_suspicious() -> None:
    agent = HeadAgent()
    # No OK or ERROR markers, but suspicious placeholder output
    assert agent._classify_tool_results_state("no output") == "all_suspicious"
    assert agent._classify_tool_results_state("{}") == "all_suspicious"
    assert agent._classify_tool_results_state("[]") == "all_suspicious"


def test_classify_suspicious_with_ok_is_usable() -> None:
    agent = HeadAgent()
    # Suspicious keyword present but has OK → still usable
    assert agent._classify_tool_results_state("[read_file] OK: no output") == "usable"


def test_resolve_partial_error_replan() -> None:
    agent = HeadAgent()

    reason = agent._resolve_replan_reason(
        tool_results_state="partial_error",
        iteration=0,
        max_replan_iterations=2,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=1,
    )
    assert reason == "tool_selection_partial_error_replan"


def test_resolve_partial_error_budget_exhausted() -> None:
    agent = HeadAgent()

    reason = agent._resolve_replan_reason(
        tool_results_state="partial_error",
        iteration=0,
        max_replan_iterations=2,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=1,
        max_error_tool_replan_attempts=1,
    )
    assert reason is None


def test_resolve_suspicious_replan() -> None:
    agent = HeadAgent()

    reason = agent._resolve_replan_reason(
        tool_results_state="all_suspicious",
        iteration=0,
        max_replan_iterations=2,
        empty_tool_replan_attempts_used=0,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=0,
    )
    assert reason == "tool_selection_suspicious_replan"


def test_resolve_suspicious_budget_exhausted() -> None:
    agent = HeadAgent()

    reason = agent._resolve_replan_reason(
        tool_results_state="all_suspicious",
        iteration=0,
        max_replan_iterations=2,
        empty_tool_replan_attempts_used=1,
        max_empty_tool_replan_attempts=1,
        error_tool_replan_attempts_used=0,
        max_error_tool_replan_attempts=0,
    )
    assert reason is None
