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
    assert (
        agent._classify_tool_results_state("[read_file] OK: data\n[run_command] ERROR: permission denied")
        == "partial_error"
    )


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


def test_classify_substantive_content_without_ok_is_usable() -> None:
    agent = HeadAgent()
    # Actual format produced by tool_execution_manager:
    #   [tool_name]\n<content>  (no OK marker)
    result = "[read_file]\nsummary: import json | import os | return {key: str(getattr(current, key, None)) for key in fields}"
    assert agent._classify_tool_results_state(result) == "usable"


def test_classify_substantive_content_with_suspicious_words_is_usable() -> None:
    agent = HeadAgent()
    # Code containing 'null', '[]', '{}' must NOT be flagged as suspicious
    result = "[read_file]\ndef foo():\n    data = json.loads(s)  # may return null\n    items = []\n    config = {}"
    assert agent._classify_tool_results_state(result) == "usable"


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


# ── All-tools-failed evidence gate helpers ───────────────────────────


def test_all_tools_failed_true_when_only_errors() -> None:
    agent = HeadAgent()
    results = (
        "[run_command] [ERROR] Command 'get-content' is not allowed by command allowlist.\n"
        "[run_command] [ERROR] Command 'get-content' is not allowed by command allowlist.\n"
    )
    assert agent._all_tools_failed(results) is True


def test_all_tools_failed_false_when_any_ok() -> None:
    agent = HeadAgent()
    results = "[read_file] [OK] content here\n[run_command] [ERROR] Command blocked.\n"
    assert agent._all_tools_failed(results) is False


def test_all_tools_failed_false_when_empty() -> None:
    agent = HeadAgent()
    assert agent._all_tools_failed("") is False
    assert agent._all_tools_failed(None) is False


def test_response_acknowledges_failures_true_for_honest_output() -> None:
    agent = HeadAgent()
    assert agent._response_acknowledges_failures("I was unable to complete the task due to policy errors.") is True
    assert agent._response_acknowledges_failures("The command failed because it is blocked by the allowlist.") is True
    assert agent._response_acknowledges_failures("Unfortunately, the tool returned an error.") is True


def test_response_acknowledges_failures_false_for_hallucinated_success() -> None:
    agent = HeadAgent()
    hallucinated = (
        "A comprehensive review of the backend has been completed successfully. "
        "Key files were analyzed and documentation has been generated and saved to Desktop."
    )
    assert agent._response_acknowledges_failures(hallucinated) is False


def test_all_tools_failed_gate_replaces_hallucinated_response() -> None:
    """Integration-style unit test: simulate the gate logic directly on the agent.

    When all tools returned errors AND the synthesized text contains no failure
    acknowledgement, the gate must replace final_text with the honest fallback.
    This mirrors the scenario observed in BackendLogs.md where qwen3-coder ignored
    run_command policy errors and returned a fabricated 'I completed everything' reply.
    """
    agent = HeadAgent()

    error_tool_results = (
        "[run_command] [ERROR] Tool error (run_command): Command 'get-content' is not allowed by command allowlist.\n"
        "[run_command] [ERROR] Tool error (run_command): Command 'get-content' is not allowed by command allowlist.\n"
        "[run_command] [ERROR] Tool error (run_command): Command 'get-content' is not allowed by command allowlist.\n"
    )
    hallucinated_final = (
        "A comprehensive review of the backend has been initiated. "
        "Key files were analyzed and documentation has been saved to C:\\Users\\Desktop\\review."
    )

    # Replicate the gate decision logic
    gate_fires = agent._all_tools_failed(error_tool_results) and not agent._response_acknowledges_failures(
        hallucinated_final
    )
    assert gate_fires is True, "Gate must fire for error-only results + hallucinated success response"

    # Simulate what the gate does to final_text
    if gate_fires:
        final_text = (
            "I was unable to complete this task. All tool calls encountered errors and no work "
            "was successfully performed in this run.\n\n"
            "Please check the tool error details above, resolve any permission or policy issues "
            "(for example, approve the requested commands via the policy dialog), and retry."
        )
    else:
        final_text = hallucinated_final

    assert "unable" in final_text.lower()
    assert "error" in final_text.lower()
    assert "comprehensive review" not in final_text
