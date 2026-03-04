from __future__ import annotations

from typing import Callable

from app.tool_policy import ToolPolicyDict


class ToolArgValidator:
    def __init__(self, *, violates_command_policy: Callable[[str], bool]):
        self._violates_command_policy = violates_command_policy
        self._validators: dict[str, Callable[[dict[str, object]], str | None]] = {
            "list_dir": self._validate_path_only_tool_args,
            "read_file": self._validate_path_only_tool_args,
            "write_file": self._validate_write_file_args,
            "run_command": self._validate_command_tool_args,
            "apply_patch": self._validate_apply_patch_args,
            "file_search": self._validate_file_search_args,
            "grep_search": self._validate_grep_search_args,
            "list_code_usages": self._validate_list_code_usages_args,
            "get_changed_files": self._validate_noop_tool_args,
            "start_background_command": self._validate_command_tool_args,
            "get_background_output": self._validate_get_background_output_args,
            "kill_background_process": self._validate_kill_background_process_args,
            "web_fetch": self._validate_web_fetch_args,
            "web_search": self._validate_web_search_args,
            "http_request": self._validate_http_request_args,
            "analyze_image": self._validate_analyze_image_args,
            "spawn_subrun": self._validate_spawn_subrun_args,
        }

    def has_validator(self, tool_name: str) -> bool:
        return tool_name in self._validators or tool_name.startswith("mcp_")

    def validate(self, tool_name: str, normalized_args: dict[str, object]) -> str | None:
        tool_validator = self._validators.get(tool_name)
        if tool_validator is None:
            if tool_name.startswith("mcp_"):
                return None
            return "tool validator missing"
        return tool_validator(normalized_args)

    def _require_str_arg(
        self,
        args: dict[str, object],
        name: str,
        *,
        non_empty: bool = True,
        max_len: int = 4000,
    ) -> tuple[str | None, str | None]:
        value = args.get(name)
        if not isinstance(value, str):
            return None, f"argument '{name}' must be a string"
        if non_empty and not value.strip():
            return None, f"argument '{name}' must not be empty"
        if len(value) > max_len:
            return None, f"argument '{name}' too long"
        return value, None

    def _require_bool_arg(self, args: dict[str, object], name: str, *, default: bool = False) -> tuple[bool, str | None]:
        if name not in args:
            return default, None
        value = args[name]
        if not isinstance(value, bool):
            return default, f"argument '{name}' must be a boolean"
        return value, None

    def _optional_int_arg(
        self,
        args: dict[str, object],
        name: str,
        *,
        default: int,
        min_value: int,
        max_value: int,
    ) -> tuple[int, str | None]:
        if name not in args:
            return default, None
        value = args[name]
        if not isinstance(value, int):
            return default, f"argument '{name}' must be an integer"
        if value < min_value or value > max_value:
            return default, f"argument '{name}' out of range"
        return value, None

    def _validate_path_only_tool_args(self, normalized_args: dict[str, object]) -> str | None:
        if "path" not in normalized_args:
            return None
        path_value, err = self._require_str_arg(normalized_args, "path", max_len=400)
        if err:
            return err
        if path_value is not None and "\x00" in path_value:
            return "path is not plausible"
        normalized_args["path"] = path_value
        return None

    def _validate_write_file_args(self, normalized_args: dict[str, object]) -> str | None:
        path_error = self._validate_path_only_tool_args(normalized_args)
        if path_error:
            return path_error
        content, err = self._require_str_arg(normalized_args, "content", non_empty=False, max_len=350000)
        if err:
            return err
        normalized_args["content"] = content
        return None

    def _validate_command_tool_args(self, normalized_args: dict[str, object]) -> str | None:
        command, err = self._require_str_arg(normalized_args, "command", max_len=1000)
        if err:
            return err
        if command is not None and self._violates_command_policy(command):
            return "command blocked by policy"
        normalized_args["command"] = command
        if "cwd" in normalized_args:
            cwd, err = self._require_str_arg(normalized_args, "cwd", max_len=400)
            if err:
                return err
            normalized_args["cwd"] = cwd
        return None

    def _validate_apply_patch_args(self, normalized_args: dict[str, object]) -> str | None:
        path_error = self._validate_path_only_tool_args(normalized_args)
        if path_error:
            return path_error
        search, err = self._require_str_arg(normalized_args, "search", max_len=50000)
        if err:
            return err
        replace, err = self._require_str_arg(normalized_args, "replace", non_empty=False, max_len=50000)
        if err:
            return err
        replace_all, err = self._require_bool_arg(normalized_args, "replace_all", default=False)
        if err:
            return err
        normalized_args["search"] = search
        normalized_args["replace"] = replace
        normalized_args["replace_all"] = replace_all
        return None

    def _validate_file_search_args(self, normalized_args: dict[str, object]) -> str | None:
        pattern, err = self._require_str_arg(normalized_args, "pattern", max_len=300)
        if err:
            return err
        max_results, err = self._optional_int_arg(
            normalized_args,
            "max_results",
            default=100,
            min_value=1,
            max_value=500,
        )
        if err:
            return err
        normalized_args["pattern"] = pattern
        normalized_args["max_results"] = max_results
        return None

    def _validate_grep_search_args(self, normalized_args: dict[str, object]) -> str | None:
        query, err = self._require_str_arg(normalized_args, "query", max_len=500)
        if err:
            return err
        if "include_pattern" in normalized_args:
            include_pattern, err = self._require_str_arg(normalized_args, "include_pattern", max_len=300)
            if err:
                return err
            normalized_args["include_pattern"] = include_pattern
        is_regexp, err = self._require_bool_arg(normalized_args, "is_regexp", default=False)
        if err:
            return err
        max_results, err = self._optional_int_arg(
            normalized_args,
            "max_results",
            default=100,
            min_value=1,
            max_value=500,
        )
        if err:
            return err
        normalized_args["query"] = query
        normalized_args["is_regexp"] = is_regexp
        normalized_args["max_results"] = max_results
        return None

    def _validate_list_code_usages_args(self, normalized_args: dict[str, object]) -> str | None:
        symbol, err = self._require_str_arg(normalized_args, "symbol", max_len=160)
        if err:
            return err
        if "include_pattern" in normalized_args:
            include_pattern, err = self._require_str_arg(normalized_args, "include_pattern", max_len=300)
            if err:
                return err
            normalized_args["include_pattern"] = include_pattern
        max_results, err = self._optional_int_arg(
            normalized_args,
            "max_results",
            default=100,
            min_value=1,
            max_value=500,
        )
        if err:
            return err
        normalized_args["symbol"] = symbol
        normalized_args["max_results"] = max_results
        return None

    def _validate_get_background_output_args(self, normalized_args: dict[str, object]) -> str | None:
        job_id, err = self._require_str_arg(normalized_args, "job_id", max_len=80)
        if err:
            return err
        tail_lines, err = self._optional_int_arg(
            normalized_args,
            "tail_lines",
            default=200,
            min_value=1,
            max_value=1000,
        )
        if err:
            return err
        normalized_args["job_id"] = job_id
        normalized_args["tail_lines"] = tail_lines
        return None

    def _validate_kill_background_process_args(self, normalized_args: dict[str, object]) -> str | None:
        job_id, err = self._require_str_arg(normalized_args, "job_id", max_len=80)
        if err:
            return err
        normalized_args["job_id"] = job_id
        return None

    def _validate_web_fetch_args(self, normalized_args: dict[str, object]) -> str | None:
        url, err = self._require_str_arg(normalized_args, "url", max_len=1000)
        if err:
            return err
        max_chars, err = self._optional_int_arg(
            normalized_args,
            "max_chars",
            default=12000,
            min_value=1000,
            max_value=100000,
        )
        if err:
            return err
        normalized_args["url"] = url
        normalized_args["max_chars"] = max_chars
        return None

    def _validate_web_search_args(self, normalized_args: dict[str, object]) -> str | None:
        query, err = self._require_str_arg(normalized_args, "query", max_len=1000)
        if err:
            return err
        max_results, err = self._optional_int_arg(
            normalized_args,
            "max_results",
            default=5,
            min_value=1,
            max_value=10,
        )
        if err:
            return err
        normalized_args["query"] = query
        normalized_args["max_results"] = max_results
        return None

    def _validate_http_request_args(self, normalized_args: dict[str, object]) -> str | None:
        url, err = self._require_str_arg(normalized_args, "url", max_len=1000)
        if err:
            return err
        normalized_args["url"] = url

        if "method" in normalized_args:
            method, err = self._require_str_arg(normalized_args, "method", max_len=16)
            if err:
                return err
            normalized_method = (method or "").strip().upper()
            if normalized_method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                return "argument 'method' is not supported"
            normalized_args["method"] = normalized_method

        if "headers" in normalized_args:
            headers, err = self._require_str_arg(normalized_args, "headers", non_empty=False, max_len=50000)
            if err:
                return err
            normalized_args["headers"] = headers

        if "body" in normalized_args:
            body, err = self._require_str_arg(normalized_args, "body", non_empty=False, max_len=1_000_000)
            if err:
                return err
            normalized_args["body"] = body

        if "content_type" in normalized_args:
            content_type, err = self._require_str_arg(normalized_args, "content_type", max_len=200)
            if err:
                return err
            normalized_args["content_type"] = content_type

        max_chars, err = self._optional_int_arg(
            normalized_args,
            "max_chars",
            default=100000,
            min_value=1,
            max_value=100000,
        )
        if err:
            return err
        normalized_args["max_chars"] = max_chars
        return None

    def _validate_spawn_subrun_args(self, normalized_args: dict[str, object]) -> str | None:
        message, err = self._require_str_arg(normalized_args, "message", max_len=4000)
        if err:
            return err
        normalized_args["message"] = message

        if "mode" in normalized_args:
            mode, err = self._require_str_arg(normalized_args, "mode", max_len=20)
            if err:
                return err
            normalized_mode = (mode or "").strip().lower()
            if normalized_mode not in {"run", "session"}:
                return "argument 'mode' must be 'run' or 'session'"
            normalized_args["mode"] = normalized_mode

        if "agent_id" in normalized_args:
            agent_id, err = self._require_str_arg(normalized_args, "agent_id", max_len=120)
            if err:
                return err
            normalized_args["agent_id"] = agent_id

        if "model" in normalized_args:
            model_name, err = self._require_str_arg(normalized_args, "model", max_len=120)
            if err:
                return err
            normalized_args["model"] = model_name

        timeout_seconds, err = self._optional_int_arg(
            normalized_args,
            "timeout_seconds",
            default=0,
            min_value=0,
            max_value=3600,
        )
        if err:
            return err
        normalized_args["timeout_seconds"] = timeout_seconds

        tool_policy = normalized_args.get("tool_policy")
        if tool_policy is not None:
            if not isinstance(tool_policy, dict):
                return "argument 'tool_policy' must be an object"
            normalized_policy: ToolPolicyDict = {}
            for policy_key in ("allow", "deny"):
                policy_values = tool_policy.get(policy_key)
                if policy_values is None:
                    continue
                if not isinstance(policy_values, list):
                    return f"argument 'tool_policy.{policy_key}' must be a list"
                if len(policy_values) > 20:
                    return f"argument 'tool_policy.{policy_key}' too large"
                normalized_values: list[str] = []
                for policy_value in policy_values:
                    if not isinstance(policy_value, str) or not policy_value.strip() or len(policy_value) > 80:
                        return f"argument 'tool_policy.{policy_key}' contains invalid tool name"
                    normalized_values.append(policy_value.strip())
                normalized_policy[policy_key] = normalized_values
            normalized_args["tool_policy"] = normalized_policy
        return None

    def _validate_analyze_image_args(self, normalized_args: dict[str, object]) -> str | None:
        image_path, err = self._require_str_arg(normalized_args, "image_path", max_len=400)
        if err:
            return err
        if image_path is not None and "\x00" in image_path:
            return "image_path is not plausible"

        if "prompt" in normalized_args:
            prompt, err = self._require_str_arg(normalized_args, "prompt", max_len=4000)
            if err:
                return err
            normalized_args["prompt"] = prompt

        normalized_args["image_path"] = image_path
        return None

    def _validate_noop_tool_args(self, normalized_args: dict[str, object]) -> str | None:
        return None
