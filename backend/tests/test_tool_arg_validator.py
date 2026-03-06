from __future__ import annotations

import pytest

from app.services.tool_arg_validator import ToolArgValidator


def _validator(block_commands: bool = False) -> ToolArgValidator:
    return ToolArgValidator(violates_command_policy=lambda command: block_commands and "rm -rf" in command)


def test_has_known_and_unknown_validator() -> None:
    validator = _validator()

    assert validator.has_validator("read_file") is True
    assert validator.has_validator("mcp_anything") is True
    assert validator.has_validator("unknown_tool") is False


def test_validate_unknown_and_mcp_tool() -> None:
    validator = _validator()

    assert validator.validate("unknown_tool", {}) == "tool validator missing"
    assert validator.validate("mcp_custom", {"anything": 1}) is None


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


def test_validate_path_only_optional_and_invalid_type() -> None:
    validator = _validator()

    assert validator.validate("list_dir", {}) is None
    assert validator.validate("list_dir", {"path": 123}) == "argument 'path' must be a string"


def test_validate_write_file_rejects_too_large_content() -> None:
    validator = _validator()
    args = {"path": "notes/todo.txt", "content": "x" * 350001}

    error = validator.validate("write_file", args)

    assert error == "argument 'content' too long"


def test_validate_command_tool_cwd_validation_and_normalization() -> None:
    validator = _validator()

    ok_args = {"command": "echo hi", "cwd": " ./repo "}
    assert validator.validate("start_background_command", ok_args) is None
    assert ok_args["command"] == "echo hi"
    assert ok_args["cwd"] == " ./repo "

    bad_args = {"command": "echo hi", "cwd": 42}
    assert validator.validate("run_command", bad_args) == "argument 'cwd' must be a string"


def test_validate_analyze_image_applies_prompt_optional() -> None:
    validator = _validator()
    args = {"image_path": "screenshots/ui.png", "prompt": "Find CTA buttons"}

    error = validator.validate("analyze_image", args)

    assert error is None
    assert args["image_path"] == "screenshots/ui.png"
    assert args["prompt"] == "Find CTA buttons"


def test_validate_code_execute_applies_defaults() -> None:
    validator = _validator()
    args = {"code": "print('hi')"}

    error = validator.validate("code_execute", args)

    assert error is None
    assert args["language"] == "python"
    assert args["timeout"] == 30
    assert args["max_output_chars"] == 10000
    assert args["strategy"] == "process"


def test_validate_code_execute_rejects_invalid_language() -> None:
    validator = _validator()
    args = {"code": "puts 'hi'", "language": "ruby"}

    error = validator.validate("code_execute", args)

    assert error == "argument 'language' must be one of: python, javascript, js"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"code": "print('x')", "timeout": "10"}, "argument 'timeout' must be an integer"),
        ({"code": "print('x')", "timeout": 0}, "argument 'timeout' out of range"),
        ({"code": "print('x')", "max_output_chars": 100}, "argument 'max_output_chars' out of range"),
        ({"code": "print('x')", "strategy": "invalid"}, "argument 'strategy' must be one of: process, direct, docker"),
    ],
)
def test_validate_code_execute_rejects_invalid_numeric_and_strategy(args: dict, expected: str) -> None:
    validator = _validator()

    assert validator.validate("code_execute", args) == expected


def test_validate_code_execute_normalizes_language_and_strategy() -> None:
    validator = _validator()
    args = {"code": "console.log('x')", "language": " JS ", "strategy": " DIRECT "}

    error = validator.validate("code_execute", args)

    assert error is None
    assert args["language"] == "js"
    assert args["strategy"] == "direct"


def test_validate_apply_patch_and_replace_all_type() -> None:
    validator = _validator()
    ok_args = {"path": "a.txt", "search": "x", "replace": "y"}
    assert validator.validate("apply_patch", ok_args) is None
    assert ok_args["replace_all"] is False

    bad_args = {"path": "a.txt", "search": "x", "replace": "y", "replace_all": "yes"}
    assert validator.validate("apply_patch", bad_args) == "argument 'replace_all' must be a boolean"


def test_validate_file_search_and_list_code_usages_bounds() -> None:
    validator = _validator()

    assert validator.validate("file_search", {"pattern": "*.py", "max_results": 600}) == "argument 'max_results' out of range"
    assert validator.validate("list_code_usages", {"symbol": "x", "include_pattern": 3}) == "argument 'include_pattern' must be a string"


def test_validate_grep_search_optional_fields() -> None:
    validator = _validator()

    bad = {"query": "needle", "is_regexp": "yes"}
    assert validator.validate("grep_search", bad) == "argument 'is_regexp' must be a boolean"

    ok = {"query": "needle", "include_pattern": "src/**/*.py", "is_regexp": True, "max_results": 10}
    assert validator.validate("grep_search", ok) is None
    assert ok["is_regexp"] is True


def test_validate_background_job_args() -> None:
    validator = _validator()

    assert validator.validate("get_background_output", {"job_id": "abc", "tail_lines": 0}) == "argument 'tail_lines' out of range"
    assert validator.validate("kill_background_process", {"job_id": " "}) == "argument 'job_id' must not be empty"


def test_validate_web_fetch_and_web_search_bounds() -> None:
    validator = _validator()

    assert validator.validate("web_fetch", {"url": "https://x", "max_chars": 50}) == "argument 'max_chars' out of range"
    assert validator.validate("web_search", {"query": "x", "max_results": 11}) == "argument 'max_results' out of range"


def test_validate_http_request_variants() -> None:
    validator = _validator()

    invalid_method = {"url": "https://x", "method": "TRACE"}
    assert validator.validate("http_request", invalid_method) == "argument 'method' is not supported"

    invalid_headers = {"url": "https://x", "headers": {"a": "b"}}
    assert validator.validate("http_request", invalid_headers) == "argument 'headers' must be a string"

    ok = {
        "url": "https://x",
        "method": "post",
        "headers": "{\"x\":\"1\"}",
        "body": "{}",
        "content_type": "application/json",
        "max_chars": 999,
    }
    assert validator.validate("http_request", ok) is None
    assert ok["method"] == "POST"


def test_validate_spawn_subrun_tool_policy_normalization_and_errors() -> None:
    validator = _validator()

    args = {
        "message": "analyze",
        "mode": "RUN",
        "agent_id": "coder-agent",
        "model": "gpt",
        "timeout_seconds": 30,
        "tool_policy": {"allow": [" read_file ", "run_command"], "deny": ["code_execute"]},
    }
    assert validator.validate("spawn_subrun", args) is None
    assert args["mode"] == "run"
    assert args["tool_policy"]["allow"] == ["read_file", "run_command"]

    # tool_policy with an invalid type is coerced to None instead of hard-blocking.
    invalid_policy_args: dict = {"message": "x", "tool_policy": "invalid"}
    assert validator.validate("spawn_subrun", invalid_policy_args) is None
    assert invalid_policy_args["tool_policy"] is None
    assert (
        validator.validate("spawn_subrun", {"message": "x", "tool_policy": {"allow": "read_file"}})
        == "argument 'tool_policy.allow' must be a list"
    )
    assert (
        validator.validate(
            "spawn_subrun",
            {"message": "x", "tool_policy": {"allow": [" "]}},
        )
        == "argument 'tool_policy.allow' contains invalid tool name"
    )


def test_validate_spawn_subrun_tool_policy_too_large_and_timeout_range() -> None:
    validator = _validator()

    too_large = {"message": "x", "tool_policy": {"deny": [f"tool{i}" for i in range(21)]}}
    assert validator.validate("spawn_subrun", too_large) == "argument 'tool_policy.deny' too large"

    assert validator.validate("spawn_subrun", {"message": "x", "timeout_seconds": 4000}) == "argument 'timeout_seconds' out of range"


def test_validate_analyze_image_prompt_type_and_null_byte() -> None:
    validator = _validator()

    assert validator.validate("analyze_image", {"image_path": "img\x00.png"}) == "image_path is not plausible"
    assert validator.validate("analyze_image", {"image_path": "img.png", "prompt": 123}) == "argument 'prompt' must be a string"


def test_validate_noop_tool_always_passes() -> None:
    validator = _validator()

    assert validator.validate("get_changed_files", {"any": "thing"}) is None


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        ("write_file", {"path": 1, "content": "x"}, "argument 'path' must be a string"),
        ("run_command", {"command": 1}, "argument 'command' must be a string"),
        ("code_execute", {"code": 1}, "argument 'code' must be a string"),
        ("code_execute", {"code": "print(1)", "language": 1}, "argument 'language' must be a string"),
        ("code_execute", {"code": "print(1)", "strategy": 1}, "argument 'strategy' must be a string"),
        ("apply_patch", {"path": 1, "search": "a", "replace": "b"}, "argument 'path' must be a string"),
        ("apply_patch", {"path": "a", "search": 1, "replace": "b"}, "argument 'search' must be a string"),
        ("apply_patch", {"path": "a", "search": "a", "replace": 1}, "argument 'replace' must be a string"),
        ("file_search", {"pattern": 1}, "argument 'pattern' must be a string"),
        ("grep_search", {"query": 1}, "argument 'query' must be a string"),
        ("grep_search", {"query": "x", "include_pattern": 1}, "argument 'include_pattern' must be a string"),
        ("grep_search", {"query": "x", "max_results": 0}, "argument 'max_results' out of range"),
        ("list_code_usages", {"symbol": 1}, "argument 'symbol' must be a string"),
        ("web_fetch", {"url": 1}, "argument 'url' must be a string"),
        ("web_search", {"query": 1}, "argument 'query' must be a string"),
        ("http_request", {"url": 1}, "argument 'url' must be a string"),
        ("http_request", {"url": "https://x", "method": 1}, "argument 'method' must be a string"),
        ("http_request", {"url": "https://x", "body": 1}, "argument 'body' must be a string"),
        ("http_request", {"url": "https://x", "content_type": 1}, "argument 'content_type' must be a string"),
        ("http_request", {"url": "https://x", "max_chars": 0}, "argument 'max_chars' out of range"),
        ("spawn_subrun", {"message": 1}, "argument 'message' must be a string"),
        ("spawn_subrun", {"message": "x", "mode": 1}, "argument 'mode' must be a string"),
        ("spawn_subrun", {"message": "x", "agent_id": 1}, "argument 'agent_id' must be a string"),
        ("spawn_subrun", {"message": "x", "model": 1}, "argument 'model' must be a string"),
        ("analyze_image", {"image_path": 1}, "argument 'image_path' must be a string"),
    ],
)
def test_validator_error_branches(tool: str, args: dict, expected: str) -> None:
    validator = _validator()
    assert validator.validate(tool, args) == expected


def test_validator_success_branches_for_remaining_paths() -> None:
    validator = _validator()

    file_search_args = {"pattern": "*.py", "max_results": 7}
    assert validator.validate("file_search", file_search_args) is None
    assert file_search_args["pattern"] == "*.py"
    assert file_search_args["max_results"] == 7

    list_usage_args = {"symbol": "ToolArgValidator", "include_pattern": "tests/*.py", "max_results": 8}
    assert validator.validate("list_code_usages", list_usage_args) is None
    assert list_usage_args["include_pattern"] == "tests/*.py"
    assert list_usage_args["symbol"] == "ToolArgValidator"
    assert list_usage_args["max_results"] == 8

    background_args = {"job_id": "job-1", "tail_lines": 50}
    assert validator.validate("get_background_output", background_args) is None
    assert background_args["job_id"] == "job-1"
    assert background_args["tail_lines"] == 50

    kill_args = {"job_id": "job-2"}
    assert validator.validate("kill_background_process", kill_args) is None
    assert kill_args["job_id"] == "job-2"
