from __future__ import annotations

from collections.abc import Callable

from app.tools.policy import ToolPolicyDict


class ToolArgValidator:
    def __init__(self, *, violates_command_policy: Callable[[str], bool]):
        self._violates_command_policy = violates_command_policy
        self._validators: dict[str, Callable[[dict[str, object]], str | None]] = {
            "list_dir": self._validate_path_only_tool_args,
            "read_file": self._validate_path_only_tool_args,
            "write_file": self._validate_write_file_args,
            "run_command": self._validate_command_tool_args,
            "code_execute": self._validate_code_execute_args,
            "code_reset": self._validate_session_id_only_args,
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
            "browser_open": self._validate_browser_open_args,
            "browser_click": self._validate_browser_selector_args,
            "browser_type": self._validate_browser_type_args,
            "browser_screenshot": self._validate_session_id_only_args,
            "browser_read_dom": self._validate_browser_read_dom_args,
            "browser_evaluate_js": self._validate_browser_evaluate_js_args,
            "emit_visualization": self._validate_emit_visualization_args,
            "spawn_subrun": self._validate_spawn_subrun_args,
            "create_workflow": self._validate_create_workflow_args,
            "delete_workflow": self._validate_delete_workflow_args,
            "build_workflow": self._validate_build_workflow_args,
            "explore_connector": self._validate_explore_connector_args,
            # Agent management tools
            "create_agent": self._validate_create_agent_args,
            "list_agents": self._validate_noop_tool_args,
            # Multimodal tools
            "parse_pdf": self._validate_parse_pdf_args,
            "transcribe_audio": self._validate_transcribe_audio_args,
            "generate_image": self._validate_generate_image_args,
            "generate_audio": self._validate_generate_audio_args,
            "export_pdf": self._validate_export_pdf_args,
            # DevOps tools
            "git_log": self._validate_git_log_args,
            "git_diff": self._validate_git_diff_args,
            "git_blame": self._validate_git_blame_args,
            "git_show": self._validate_git_show_args,
            "git_stash": self._validate_git_stash_args,
            "run_tests": self._validate_run_tests_args,
            "lint_check": self._validate_lint_check_args,
            "test_coverage": self._validate_test_coverage_args,
            "dependency_audit": self._validate_dependency_audit_args,
            "dependency_outdated": self._validate_dependency_manager_args,
            "dependency_tree": self._validate_dependency_tree_args,
            "parse_errors": self._validate_parse_errors_args,
            "secrets_scan": self._validate_secrets_scan_args,
            "security_check": self._validate_security_check_args,
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
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            lower = value.strip().lower()
            if lower in {"true", "1", "yes"}:
                args[name] = True
                return True, None
            if lower in {"false", "0", "no"}:
                args[name] = False
                return False, None
        if isinstance(value, int) and value in (0, 1):
            coerced = bool(value)
            args[name] = coerced
            return coerced, None
        return default, f"argument '{name}' must be a boolean"

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
        if isinstance(value, bool):
            # bool is a subclass of int; reject it to avoid silent coercion
            return default, f"argument '{name}' must be an integer"
        if not isinstance(value, int):
            if isinstance(value, (str, float)):
                try:
                    value = int(value)
                    args[name] = value
                except (ValueError, TypeError):
                    return default, f"argument '{name}' must be an integer"
            else:
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

    def _validate_code_execute_args(self, normalized_args: dict[str, object]) -> str | None:
        code, err = self._require_str_arg(normalized_args, "code", max_len=200000)
        if err:
            return err
        normalized_args["code"] = code

        if "language" in normalized_args:
            language, err = self._require_str_arg(normalized_args, "language", max_len=32)
            if err:
                return err
            normalized_language = (language or "").strip().lower()
            if normalized_language not in {"python", "javascript", "js"}:
                return "argument 'language' must be one of: python, javascript, js"
            normalized_args["language"] = normalized_language
        else:
            normalized_args["language"] = "python"

        timeout, err = self._optional_int_arg(
            normalized_args,
            "timeout",
            default=30,
            min_value=1,
            max_value=60,
        )
        if err:
            return err
        normalized_args["timeout"] = timeout

        max_output_chars, err = self._optional_int_arg(
            normalized_args,
            "max_output_chars",
            default=10000,
            min_value=500,
            max_value=20000,
        )
        if err:
            return err
        normalized_args["max_output_chars"] = max_output_chars

        if "strategy" in normalized_args:
            strategy, err = self._require_str_arg(normalized_args, "strategy", max_len=32)
            if err:
                return err
            normalized_strategy = (strategy or "").strip().lower()
            if normalized_strategy not in {"process", "direct", "docker"}:
                return "argument 'strategy' must be one of: process, direct, docker"
            normalized_args["strategy"] = normalized_strategy
        else:
            normalized_args["strategy"] = "process"

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
        if tool_policy is not None and not isinstance(tool_policy, dict):
            # Coerce invalid type to None instead of hard-blocking the tool call.
            # tool_policy is optional; a wrong type should not abort spawn_subrun.
            normalized_args["tool_policy"] = None
            tool_policy = None
        if tool_policy is not None:
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

    def _validate_emit_visualization_args(self, normalized_args: dict[str, object]) -> str | None:
        viz_type, err = self._require_str_arg(normalized_args, "viz_type", max_len=20)
        if err:
            return err
        if viz_type not in ("mermaid", "svg"):
            return "viz_type must be 'mermaid' or 'svg'"
        normalized_args["viz_type"] = viz_type

        code, err = self._require_str_arg(normalized_args, "code", max_len=50_000)
        if err:
            return err
        normalized_args["code"] = code

        if "title" in normalized_args:
            title, err = self._require_str_arg(normalized_args, "title", max_len=200, non_empty=False)
            if err:
                return err
            normalized_args["title"] = title

        return None

    def _validate_create_workflow_args(self, normalized_args: dict[str, object]) -> str | None:
        name, err = self._require_str_arg(normalized_args, "name", max_len=120)
        if err:
            return err
        normalized_args["name"] = name

        description, err = self._require_str_arg(normalized_args, "description", max_len=500)
        if err:
            return err
        normalized_args["description"] = description

        steps = normalized_args.get("steps")
        if isinstance(steps, str):
            parts = [s.strip() for s in steps.split(",") if s.strip()]
            if not parts:
                return "argument 'steps' must contain at least one step"
            normalized_args["steps"] = parts
        elif isinstance(steps, list):
            if not steps:
                return "argument 'steps' must contain at least one step"
            if len(steps) > 20:
                return "argument 'steps' has too many items"
            for i, s in enumerate(steps):
                if not isinstance(s, str) or not s.strip():
                    return f"argument 'steps[{i}]' must be a non-empty string"
        else:
            return "argument 'steps' must be a list or comma-separated string"

        if "base_agent_id" in normalized_args:
            base_agent_id, err = self._require_str_arg(normalized_args, "base_agent_id", max_len=120)
            if err:
                return err
            normalized_args["base_agent_id"] = base_agent_id

        return None

    def _validate_delete_workflow_args(self, normalized_args: dict[str, object]) -> str | None:
        workflow_id, err = self._require_str_arg(normalized_args, "workflow_id", max_len=120)
        if err:
            return err
        normalized_args["workflow_id"] = workflow_id
        return None

    # ------------------------------------------------------------------
    # Workflow tools (build_workflow, explore_connector)
    # ------------------------------------------------------------------

    def _validate_build_workflow_args(self, normalized_args: dict[str, object]) -> str | None:
        name, err = self._require_str_arg(normalized_args, "name", max_len=120)
        if err:
            return err
        normalized_args["name"] = name
        steps_desc, err = self._require_str_arg(normalized_args, "steps_description", max_len=5000)
        if err:
            return err
        normalized_args["steps_description"] = steps_desc
        if "description" in normalized_args:
            desc, err = self._require_str_arg(normalized_args, "description", max_len=500)
            if err:
                return err
            normalized_args["description"] = desc
        if "execution_mode" in normalized_args:
            mode, err = self._require_str_arg(normalized_args, "execution_mode", max_len=20)
            if err:
                return err
            normalized_args["execution_mode"] = mode
        return None

    def _validate_explore_connector_args(self, normalized_args: dict[str, object]) -> str | None:
        cid, err = self._require_str_arg(normalized_args, "connector_id", max_len=120)
        if err:
            return err
        normalized_args["connector_id"] = cid
        return None

    # ------------------------------------------------------------------
    # Agent management tools
    # ------------------------------------------------------------------

    def _validate_create_agent_args(self, normalized_args: dict[str, object]) -> str | None:
        name, err = self._require_str_arg(normalized_args, "name", max_len=120)
        if err:
            return err
        normalized_args["name"] = name
        desc, err = self._require_str_arg(normalized_args, "description", max_len=500)
        if err:
            return err
        normalized_args["description"] = desc
        if "role" in normalized_args:
            role, err = self._require_str_arg(normalized_args, "role", max_len=32)
            if err:
                return err
            if role not in ("specialist", "reviewer", "researcher", "coordinator"):
                return "argument 'role' must be one of: specialist, reviewer, researcher, coordinator"
            normalized_args["role"] = role
        if "specialization" in normalized_args:
            spec, err = self._require_str_arg(normalized_args, "specialization", max_len=200)
            if err:
                return err
            normalized_args["specialization"] = spec
        if "system_prompt" in normalized_args:
            sp, err = self._require_str_arg(normalized_args, "system_prompt", max_len=4000)
            if err:
                return err
            normalized_args["system_prompt"] = sp
        return None

    # ------------------------------------------------------------------
    # Session-id-only tools (code_reset, browser_screenshot)
    # ------------------------------------------------------------------

    def _validate_session_id_only_args(self, normalized_args: dict[str, object]) -> str | None:
        if "session_id" in normalized_args:
            session_id, err = self._require_str_arg(normalized_args, "session_id", max_len=120)
            if err:
                return err
            normalized_args["session_id"] = session_id
        return None

    # ------------------------------------------------------------------
    # Browser tool validators
    # ------------------------------------------------------------------

    def _validate_browser_open_args(self, normalized_args: dict[str, object]) -> str | None:
        url, err = self._require_str_arg(normalized_args, "url", max_len=2000)
        if err:
            return err
        normalized_args["url"] = url
        if "session_id" in normalized_args:
            session_id, err = self._require_str_arg(normalized_args, "session_id", max_len=120)
            if err:
                return err
            normalized_args["session_id"] = session_id
        return None

    def _validate_browser_selector_args(self, normalized_args: dict[str, object]) -> str | None:
        selector, err = self._require_str_arg(normalized_args, "selector", max_len=500)
        if err:
            return err
        normalized_args["selector"] = selector
        if "session_id" in normalized_args:
            session_id, err = self._require_str_arg(normalized_args, "session_id", max_len=120)
            if err:
                return err
            normalized_args["session_id"] = session_id
        return None

    def _validate_browser_type_args(self, normalized_args: dict[str, object]) -> str | None:
        selector, err = self._require_str_arg(normalized_args, "selector", max_len=500)
        if err:
            return err
        normalized_args["selector"] = selector
        text, err = self._require_str_arg(normalized_args, "text", non_empty=False, max_len=4000)
        if err:
            return err
        normalized_args["text"] = text
        if "session_id" in normalized_args:
            session_id, err = self._require_str_arg(normalized_args, "session_id", max_len=120)
            if err:
                return err
            normalized_args["session_id"] = session_id
        return None

    def _validate_browser_read_dom_args(self, normalized_args: dict[str, object]) -> str | None:
        if "selector" in normalized_args:
            selector, err = self._require_str_arg(normalized_args, "selector", max_len=500)
            if err:
                return err
            normalized_args["selector"] = selector
        if "session_id" in normalized_args:
            session_id, err = self._require_str_arg(normalized_args, "session_id", max_len=120)
            if err:
                return err
            normalized_args["session_id"] = session_id
        return None

    def _validate_browser_evaluate_js_args(self, normalized_args: dict[str, object]) -> str | None:
        code, err = self._require_str_arg(normalized_args, "code", max_len=50000)
        if err:
            return err
        normalized_args["code"] = code
        if "session_id" in normalized_args:
            session_id, err = self._require_str_arg(normalized_args, "session_id", max_len=120)
            if err:
                return err
            normalized_args["session_id"] = session_id
        return None

    # ------------------------------------------------------------------
    # Multimodal tool validators
    # ------------------------------------------------------------------

    def _validate_parse_pdf_args(self, normalized_args: dict[str, object]) -> str | None:
        path, err = self._require_str_arg(normalized_args, "path", max_len=400)
        if err:
            return err
        if path is not None and "\x00" in path:
            return "path is not plausible"
        normalized_args["path"] = path
        return None

    def _validate_transcribe_audio_args(self, normalized_args: dict[str, object]) -> str | None:
        path, err = self._require_str_arg(normalized_args, "path", max_len=400)
        if err:
            return err
        if path is not None and "\x00" in path:
            return "path is not plausible"
        normalized_args["path"] = path
        return None

    def _validate_generate_image_args(self, normalized_args: dict[str, object]) -> str | None:
        prompt, err = self._require_str_arg(normalized_args, "prompt", max_len=1000)
        if err:
            return err
        normalized_args["prompt"] = prompt
        if "size" in normalized_args:
            size, err = self._require_str_arg(normalized_args, "size", max_len=20)
            if err:
                return err
            normalized_args["size"] = size
        return None

    def _validate_generate_audio_args(self, normalized_args: dict[str, object]) -> str | None:
        text, err = self._require_str_arg(normalized_args, "text", max_len=4096)
        if err:
            return err
        normalized_args["text"] = text
        if "voice" in normalized_args:
            voice, err = self._require_str_arg(normalized_args, "voice", max_len=20)
            if err:
                return err
            normalized_voice = (voice or "").strip().lower()
            if normalized_voice not in {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}:
                return "argument 'voice' must be one of: alloy, echo, fable, onyx, nova, shimmer"
            normalized_args["voice"] = normalized_voice
        return None

    def _validate_export_pdf_args(self, normalized_args: dict[str, object]) -> str | None:
        content, err = self._require_str_arg(normalized_args, "content", non_empty=True, max_len=200000)
        if err:
            return err
        normalized_args["content"] = content
        if "path" in normalized_args:
            path, err = self._require_str_arg(normalized_args, "path", max_len=400)
            if err:
                return err
            if path is not None and "\x00" in path:
                return "path is not plausible"
            normalized_args["path"] = path
        return None

    # ------------------------------------------------------------------
    # DevOps tool validators
    # ------------------------------------------------------------------

    def _validate_optional_path(self, normalized_args: dict[str, object]) -> str | None:
        if "path" in normalized_args:
            path_value, err = self._require_str_arg(normalized_args, "path", max_len=400)
            if err:
                return err
            if path_value is not None and "\x00" in path_value:
                return "path is not plausible"
            normalized_args["path"] = path_value
        return None

    def _validate_optional_enum(
        self, normalized_args: dict[str, object], name: str, valid: set[str], default: str,
    ) -> str | None:
        if name not in normalized_args:
            normalized_args[name] = default
            return None
        value, err = self._require_str_arg(normalized_args, name, max_len=32)
        if err:
            return err
        normalized_value = (value or "").strip().lower()
        if normalized_value not in valid:
            return f"argument '{name}' must be one of: {', '.join(sorted(valid))}"
        normalized_args[name] = normalized_value
        return None

    def _validate_git_log_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_path(normalized_args)
        if err:
            return err
        max_count, err = self._optional_int_arg(normalized_args, "max_count", default=20, min_value=1, max_value=100)
        if err:
            return err
        normalized_args["max_count"] = max_count
        if "author" in normalized_args:
            author, err = self._require_str_arg(normalized_args, "author", max_len=200)
            if err:
                return err
            normalized_args["author"] = author
        if "since" in normalized_args:
            since, err = self._require_str_arg(normalized_args, "since", max_len=100)
            if err:
                return err
            normalized_args["since"] = since
        return self._validate_optional_enum(
            normalized_args, "format", {"oneline", "short", "full"}, "short",
        )

    def _validate_git_diff_args(self, normalized_args: dict[str, object]) -> str | None:
        if "target" in normalized_args:
            target, err = self._require_str_arg(normalized_args, "target", max_len=400)
            if err:
                return err
            normalized_args["target"] = target
        if "base" in normalized_args:
            base, err = self._require_str_arg(normalized_args, "base", max_len=400)
            if err:
                return err
            normalized_args["base"] = base
        _, err = self._require_bool_arg(normalized_args, "stat_only", default=False)
        return err

    def _validate_git_blame_args(self, normalized_args: dict[str, object]) -> str | None:
        path, err = self._require_str_arg(normalized_args, "path", max_len=400)
        if err:
            return err
        if path is not None and "\x00" in path:
            return "path is not plausible"
        normalized_args["path"] = path
        if "start_line" in normalized_args:
            _, err = self._optional_int_arg(normalized_args, "start_line", default=1, min_value=1, max_value=999999)
            if err:
                return err
        if "end_line" in normalized_args:
            _, err = self._optional_int_arg(normalized_args, "end_line", default=999999, min_value=1, max_value=999999)
            if err:
                return err
        return None

    def _validate_git_show_args(self, normalized_args: dict[str, object]) -> str | None:
        ref, err = self._require_str_arg(normalized_args, "ref", max_len=200)
        if err:
            return err
        normalized_args["ref"] = ref
        _, err = self._require_bool_arg(normalized_args, "stat_only", default=False)
        return err

    def _validate_git_stash_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "action", {"save", "pop", "list", "drop"}, "save",
        )
        if err:
            return err
        if "message" in normalized_args:
            message, err = self._require_str_arg(normalized_args, "message", max_len=200)
            if err:
                return err
            normalized_args["message"] = message
        return None

    def _validate_run_tests_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "runner", {"auto", "pytest", "jest", "mocha", "go", "cargo"}, "auto",
        )
        if err:
            return err
        err = self._validate_optional_path(normalized_args)
        if err:
            return err
        if "filter" in normalized_args:
            filt, err = self._require_str_arg(normalized_args, "filter", max_len=300)
            if err:
                return err
            normalized_args["filter"] = filt
        _, err = self._require_bool_arg(normalized_args, "verbose", default=False)
        return err

    def _validate_lint_check_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "tool", {"auto", "eslint", "ruff", "flake8", "mypy", "pyright", "tsc"}, "auto",
        )
        if err:
            return err
        err = self._validate_optional_path(normalized_args)
        if err:
            return err
        _, err = self._require_bool_arg(normalized_args, "fix", default=False)
        return err

    def _validate_test_coverage_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "runner", {"auto", "pytest", "jest"}, "auto",
        )
        if err:
            return err
        return self._validate_optional_path(normalized_args)

    def _validate_dependency_audit_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "manager", {"auto", "npm", "pip"}, "auto",
        )
        if err:
            return err
        return self._validate_optional_enum(
            normalized_args, "severity", {"low", "moderate", "high", "critical"}, "moderate",
        )

    def _validate_dependency_manager_args(self, normalized_args: dict[str, object]) -> str | None:
        return self._validate_optional_enum(
            normalized_args, "manager", {"auto", "npm", "pip"}, "auto",
        )

    def _validate_dependency_tree_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "manager", {"auto", "npm", "pip"}, "auto",
        )
        if err:
            return err
        if "package" in normalized_args:
            pkg, err = self._require_str_arg(normalized_args, "package", max_len=200)
            if err:
                return err
            normalized_args["package"] = pkg
        return None

    def _validate_parse_errors_args(self, normalized_args: dict[str, object]) -> str | None:
        error_text, err = self._require_str_arg(normalized_args, "error_text", max_len=50000)
        if err:
            return err
        normalized_args["error_text"] = error_text
        return self._validate_optional_enum(
            normalized_args, "language", {"auto", "python", "javascript", "go", "rust"}, "auto",
        )

    def _validate_secrets_scan_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_path(normalized_args)
        if err:
            return err
        return self._validate_optional_enum(
            normalized_args, "tool", {"auto", "gitleaks", "builtin"}, "auto",
        )

    def _validate_security_check_args(self, normalized_args: dict[str, object]) -> str | None:
        err = self._validate_optional_enum(
            normalized_args, "tool", {"auto", "bandit", "semgrep"}, "auto",
        )
        if err:
            return err
        err = self._validate_optional_path(normalized_args)
        if err:
            return err
        if "severity" in normalized_args:
            return self._validate_optional_enum(
                normalized_args, "severity", {"low", "medium", "high"}, "low",
            )
        return None
