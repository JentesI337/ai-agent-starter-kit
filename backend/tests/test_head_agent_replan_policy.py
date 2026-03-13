from __future__ import annotations

from app.agent import HeadAgent

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
