from __future__ import annotations

from app.services.tool_result_context_guard import enforce_tool_result_context_budget


def test_tool_result_context_guard_clips_oversized_result() -> None:
    tool_results = "[run_command]\n" + ("x" * 200_000)

    clipped, result = enforce_tool_result_context_budget(
        tool_results=tool_results,
        context_window_tokens=8_000,
    )

    assert result.modified is True
    assert result.reason in {"context_budget", "single_result_share"}
    assert result.reduced_chars < result.original_chars
    assert "[truncated: tool output exceeded context budget" in clipped or "[compacted: tool output removed to free context]" in clipped


def test_tool_result_context_guard_single_share_enforced() -> None:
    tool_results = "[read_file]\n" + ("a" * 30_000) + "\n[grep_search]\nshort"

    clipped, result = enforce_tool_result_context_budget(
        tool_results=tool_results,
        context_window_tokens=8_000,
    )

    assert result.modified is True
    assert result.reduced_chars < result.original_chars
    assert "[read_file]" in clipped
    assert "[grep_search]" in clipped


def test_tool_result_context_guard_no_op_for_small_result() -> None:
    tool_results = "[read_file]\nsmall output"

    clipped, result = enforce_tool_result_context_budget(
        tool_results=tool_results,
        context_window_tokens=8_000,
    )

    assert clipped == tool_results
    assert result.modified is False
    assert result.reason == "none"


def test_tool_result_context_guard_never_exceeds_budget_after_suffix() -> None:
    tool_results = "[run_command]\n" + ("x" * 500_000)
    context_window_tokens = 200
    headroom_ratio = 0.3
    chars_per_token = 4.0
    max_input_chars = int(context_window_tokens * chars_per_token * headroom_ratio)

    clipped, result = enforce_tool_result_context_budget(
        tool_results=tool_results,
        context_window_tokens=context_window_tokens,
        context_input_headroom_ratio=headroom_ratio,
        chars_per_token_estimate=chars_per_token,
    )

    assert result.modified is True
    assert len(clipped) <= max_input_chars
