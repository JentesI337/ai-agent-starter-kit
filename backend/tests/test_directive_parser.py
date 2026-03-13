from __future__ import annotations

import pytest

from app.reasoning.directive_parser import parse_directives_from_message
from app.shared.errors import GuardrailViolation


def test_parse_directives_extracts_overrides_and_strips_prefix() -> None:
    result = parse_directives_from_message(
        "/queue steer\n/model qwen3-coder:480b-cloud\n/reasoning high\n/verbose stream\nplease run tests"
    )

    assert result.clean_content == "please run tests"
    assert result.overrides.queue_mode == "steer"
    assert result.overrides.model == "qwen3-coder:480b-cloud"
    assert result.overrides.reasoning_level == "high"
    assert result.overrides.reasoning_visibility == "stream"
    assert result.applied == ("/queue", "/model", "/reasoning", "/verbose")


def test_parse_directives_rejects_unknown_prefix_directive() -> None:
    with pytest.raises(GuardrailViolation, match="Unsupported directive"):
        parse_directives_from_message("/unknown value\nreal task")


def test_parse_directives_rejects_directive_only_message() -> None:
    with pytest.raises(GuardrailViolation, match="Directive-only"):
        parse_directives_from_message("/queue wait\n/model gpt-oss")


def test_parse_directives_does_not_apply_inline_directive_in_text() -> None:
    source = "please do this, /queue steer should be treated as plain text"
    result = parse_directives_from_message(source)

    assert result.clean_content == source
    assert result.overrides.queue_mode is None
    assert result.applied == ()
