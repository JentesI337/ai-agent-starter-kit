from __future__ import annotations

from app.services.tool_arg_validator import ToolArgValidator


def _validator(block_commands: bool = False) -> ToolArgValidator:
    return ToolArgValidator(violates_command_policy=lambda command: block_commands and "rm -rf" in command)


def test_has_known_and_unknown_validator() -> None:
    validator = _validator()

    assert validator.has_validator("read_file") is True
    assert validator.has_validator("unknown_tool") is False


def test_validate_command_blocks_policy_violation() -> None:
    validator = _validator(block_commands=True)
    args = {"command": "rm -rf /"}

    error = validator.validate("run_command", args)

    assert error == "command blocked by policy"


def test_validate_write_file_accepts_expected_payload() -> None:
    validator = _validator()
    args = {"path": "notes/todo.txt", "content": "ok"}

    error = validator.validate("write_file", args)

    assert error is None
    assert args["path"] == "notes/todo.txt"
    assert args["content"] == "ok"


def test_validate_web_fetch_applies_default_max_chars() -> None:
    validator = _validator()
    args = {"url": "https://example.com"}

    error = validator.validate("web_fetch", args)

    assert error is None
    assert args["max_chars"] == 12000


def test_validate_web_search_applies_default_max_results() -> None:
    validator = _validator()
    args = {"query": "capital of france"}

    error = validator.validate("web_search", args)

    assert error is None
    assert args["max_results"] == 5


def test_validate_path_rejects_null_byte() -> None:
    validator = _validator()
    args = {"path": "foo\x00bar"}

    error = validator.validate("read_file", args)

    assert error == "path is not plausible"


def test_validate_spawn_subrun_rejects_invalid_mode() -> None:
    validator = _validator()
    args = {"message": "analyze", "mode": "invalid"}

    error = validator.validate("spawn_subrun", args)

    assert error == "argument 'mode' must be 'run' or 'session'"
