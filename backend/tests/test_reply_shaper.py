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


def test_sanitize_keeps_non_directive_tool_mapping_text() -> None:
    shaper = ReplyShaper()

    sanitized = shaper.sanitize("Example mapping inline: {tool => read_file} should stay.")

    assert "{tool => read_file}" in sanitized


def test_shape_suppresses_trivial_ack_after_tools() -> None:
    shaper = ReplyShaper()

    result = shaper.shape(
        final_text="done",
        tool_results="[read_file]\ncontent",
        tool_markers=TOOL_MARKERS,
    )

    assert result.text == ""
    assert result.was_suppressed is True
    assert result.suppression_reason == "irrelevant_ack_after_tools"
    assert result.removed_tokens == []
    assert result.dedup_lines_removed == 0


def test_shape_deduplicates_tool_confirmation_lines() -> None:
    shaper = ReplyShaper()

    result = shaper.shape(
        final_text="read_file done\nread_file done\nkept",
        tool_results=None,
        tool_markers=TOOL_MARKERS,
    )

    assert result.was_suppressed is False
    assert result.suppression_reason is None
    assert result.removed_tokens == []
    assert result.dedup_lines_removed == 1
    assert result.text == "read_file done\nkept"


def test_shape_only_deduplicates_adjacent_tool_confirmation_lines() -> None:
    shaper = ReplyShaper()

    result = shaper.shape(
        final_text="read_file completed\nintermediate\nread_file completed",
        tool_results=None,
        tool_markers=TOOL_MARKERS,
    )

    assert result.was_suppressed is False
    assert result.dedup_lines_removed == 0
    assert result.text.count("read_file completed") == 2


def test_shape_does_not_deduplicate_inside_fenced_code_blocks() -> None:
    shaper = ReplyShaper()

    result = shaper.shape(
        final_text="""
```text
read_file completed successfully
read_file completed successfully
```
read_file completed successfully
read_file completed successfully
""".strip(),
        tool_results="[read_file]\ncontent",
        tool_markers=TOOL_MARKERS,
    )

    assert result.was_suppressed is False
    assert result.dedup_lines_removed == 1
    assert "```text" in result.text


def test_validate_section_contract_passes_with_required_sections_and_bullets() -> None:
    shaper = ReplyShaper()

    validation = shaper.validate_section_contract(
        """
Answer
- concise answer

Key points
- point one

Next step
1. do this next
""".strip(),
        ("Answer", "Key points", "Next step"),
    )

    assert validation.is_valid is True
    assert validation.missing_sections == []
    assert validation.sections_without_bullets == []


def test_validate_section_contract_passes_with_inline_header_content() -> None:
    """BUG-1: LLMs write headers with trailing content on the same line."""
    shaper = ReplyShaper()

    validation = shaper.validate_section_contract(
        """
**Answer**: The root cause is a misconfiguration
- concise answer

**Key points:**
- point one

**Next step**: run the tests again
1. do this next
""".strip(),
        ("Answer", "Key points", "Next step"),
    )

    assert validation.is_valid is True
    assert validation.missing_sections == []
    assert validation.sections_without_bullets == []


def test_validate_section_contract_no_false_prefix_match() -> None:
    """BUG-1 fix safety: 'Answering' must not match section 'Answer'."""
    shaper = ReplyShaper()

    validation = shaper.validate_section_contract(
        """
Answering your question about the issue
- some bullet
""".strip(),
        ("Answer",),
    )

    assert validation.is_valid is False
    assert validation.missing_sections == ["Answer"]


def test_validate_section_contract_detects_missing_and_bullet_failures() -> None:
    shaper = ReplyShaper()

    validation = shaper.validate_section_contract(
        """
Answer
No bullet here

Key points
- one
""".strip(),
        ("Answer", "Key points", "Next step"),
    )

    assert validation.is_valid is False
    assert validation.missing_sections == ["Next step"]
    assert validation.sections_without_bullets == ["Answer"]
