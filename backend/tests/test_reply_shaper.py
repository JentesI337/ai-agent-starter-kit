from __future__ import annotations

from app.services.reply_shaper import ReplyShaper


TOOL_MARKERS = {"read_file", "write_file", "run_command"}


def test_sanitize_removes_tool_call_artifacts() -> None:
    shaper = ReplyShaper()

    sanitized = shaper.sanitize("Done\n[TOOL_CALL]{tool => x}[/TOOL_CALL]\nNext")

    assert "[TOOL_CALL]" not in sanitized
    assert "tool =>" not in sanitized
    assert "Done" in sanitized
    assert "Next" in sanitized


def test_shape_suppresses_trivial_ack_after_tools() -> None:
    shaper = ReplyShaper()

    text, suppressed, reason, removed_tokens, deduped_lines = shaper.shape(
        final_text="done",
        tool_results="[read_file]\ncontent",
        tool_markers=TOOL_MARKERS,
    )

    assert text == ""
    assert suppressed is True
    assert reason == "irrelevant_ack_after_tools"
    assert removed_tokens == []
    assert deduped_lines == 0


def test_shape_deduplicates_tool_confirmation_lines() -> None:
    shaper = ReplyShaper()

    text, suppressed, reason, removed_tokens, deduped_lines = shaper.shape(
        final_text="read_file done\nread_file done\nkept",
        tool_results=None,
        tool_markers=TOOL_MARKERS,
    )

    assert suppressed is False
    assert reason is None
    assert removed_tokens == []
    assert deduped_lines == 1
    assert text == "read_file done\nkept"
