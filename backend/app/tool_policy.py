from __future__ import annotations

from typing import TypeAlias, TypedDict

from pydantic import BaseModel

ToolPolicyDict: TypeAlias = dict[str, object]


class AgentToolPolicyEntry(TypedDict, total=False):
    allow: list[str]
    deny: list[str]
    also_allow: list[str]


class ExtendedToolPolicyDict(TypedDict, total=False):
    allow: list[str]
    deny: list[str]
    also_allow: list[str]
    agents: dict[str, AgentToolPolicyEntry]


class ToolPolicyPayload(BaseModel):
    allow: list[str] | None = None
    deny: list[str] | None = None
    also_allow: list[str] | None = None
    agents: dict[str, AgentToolPolicyEntry] | None = None

    def to_policy_dict(
        self,
        *,
        include_also_allow: bool = True,
        include_agents: bool = True,
    ) -> ToolPolicyDict | None:
        payload: ToolPolicyDict = {}
        if self.allow:
            payload["allow"] = [item for item in self.allow if isinstance(item, str) and item.strip()]
        if self.deny:
            payload["deny"] = [item for item in self.deny if isinstance(item, str) and item.strip()]
        if include_also_allow and self.also_allow:
            payload["also_allow"] = [item for item in self.also_allow if isinstance(item, str) and item.strip()]
        if include_agents and self.agents:
            normalized_agents: dict[str, AgentToolPolicyEntry] = {}
            for raw_agent_id, raw_policy in self.agents.items():
                if not isinstance(raw_agent_id, str):
                    continue
                agent_id = raw_agent_id.strip().lower()
                if not agent_id or not isinstance(raw_policy, dict):
                    continue
                normalized_entry: AgentToolPolicyEntry = {}
                for key in ("allow", "deny", "also_allow"):
                    values = raw_policy.get(key)
                    if not isinstance(values, list):
                        continue
                    normalized_values = [item for item in values if isinstance(item, str) and item.strip()]
                    if normalized_values:
                        normalized_entry[key] = normalized_values
                if normalized_entry:
                    normalized_agents[agent_id] = normalized_entry
            if normalized_agents:
                payload["agents"] = normalized_agents
        return payload or None


def tool_policy_to_dict(
    value: ToolPolicyPayload | ToolPolicyDict | None,
    *,
    include_also_allow: bool = True,
    include_agents: bool = True,
) -> ToolPolicyDict | None:
    if value is None:
        return None
    if isinstance(value, ToolPolicyPayload):
        return value.to_policy_dict(
            include_also_allow=include_also_allow,
            include_agents=include_agents,
        )

    payload: ToolPolicyDict = {}
    for key in ("allow", "deny", "also_allow"):
        if key == "also_allow" and not include_also_allow:
            continue
        values = value.get(key)
        if not isinstance(values, list):
            continue
        normalized = [item for item in values if isinstance(item, str) and item.strip()]
        if normalized:
            payload[key] = normalized
    if include_agents:
        raw_agents = value.get("agents")
        if isinstance(raw_agents, dict):
            normalized_agents: dict[str, AgentToolPolicyEntry] = {}
            for raw_agent_id, raw_policy in raw_agents.items():
                if not isinstance(raw_agent_id, str):
                    continue
                agent_id = raw_agent_id.strip().lower()
                if not agent_id or not isinstance(raw_policy, dict):
                    continue
                normalized_entry: AgentToolPolicyEntry = {}
                for key in ("allow", "deny", "also_allow"):
                    values = raw_policy.get(key)
                    if not isinstance(values, list):
                        continue
                    normalized_values = [item for item in values if isinstance(item, str) and item.strip()]
                    if normalized_values:
                        normalized_entry[key] = normalized_values
                if normalized_entry:
                    normalized_agents[agent_id] = normalized_entry
            if normalized_agents:
                payload["agents"] = normalized_agents
    return payload or None


# ---------------------------------------------------------------------------
# L1.3  Tool-Profile Sets – named allow-lists for common scenarios
# ---------------------------------------------------------------------------
# Each profile maps to a *frozen* set of tool names.  Agent code can
# reference ``TOOL_PROFILES["read_only"]`` instead of hard-coding lists.

TOOL_PROFILES: dict[str, frozenset[str] | None] = {
    # Strictly non-mutating; safe for any context.
    "read_only": frozenset({
        "list_dir",
        "read_file",
        "file_search",
        "grep_search",
        "list_code_usages",
        "get_changed_files",
        "get_background_output",
        "analyze_image",
        "parse_pdf",
        "git_log",
        "git_diff",
        "git_blame",
        "git_show",
        "parse_errors",
    }),
    # Read-only + web access (no code execution, no file writes).
    "research": frozenset({
        "list_dir",
        "read_file",
        "file_search",
        "grep_search",
        "list_code_usages",
        "get_changed_files",
        "get_background_output",
        "analyze_image",
        "parse_pdf",
        "transcribe_audio",
        "web_search",
        "web_fetch",
        "http_request",
        "browser_open",
        "browser_screenshot",
        "browser_read_dom",
        "git_log",
        "git_diff",
        "git_blame",
        "git_show",
        "parse_errors",
        "dependency_audit",
        "dependency_outdated",
        "dependency_tree",
        "secrets_scan",
        "security_check",
        "api_call",
        "api_list_connectors",
    }),
    # Code-editing profile – enables write/execute but not web.
    "coding": frozenset({
        "list_dir",
        "read_file",
        "write_file",
        "apply_patch",
        "run_command",
        "code_execute",
        "file_search",
        "grep_search",
        "list_code_usages",
        "get_changed_files",
        "start_background_command",
        "get_background_output",
        "kill_background_process",
        "analyze_image",
        "parse_pdf",
        "transcribe_audio",
        "generate_image",
        "export_pdf",
        "browser_open",
        "browser_click",
        "browser_type",
        "browser_screenshot",
        "browser_read_dom",
        "browser_evaluate_js",
        "git_log",
        "git_diff",
        "git_blame",
        "git_show",
        "git_stash",
        "run_tests",
        "lint_check",
        "test_coverage",
        "parse_errors",
        "dependency_audit",
        "dependency_outdated",
        "dependency_tree",
        "secrets_scan",
        "security_check",
        "api_call",
        "api_list_connectors",
        "api_auth",
    }),
    # All available tools — resolves to None (no restriction) so that
    # dynamically registered tools (MCP, plugins) are automatically
    # included without manual sync.
    "full": None,
}


def resolve_tool_profile(
    profile_name: str | None,
    *,
    extra_allow: list[str] | None = None,
    extra_deny: list[str] | None = None,
) -> frozenset[str] | None:
    """Return the effective tool set for *profile_name*.

    If *profile_name* is ``None`` or unknown, returns ``None`` (= no
    restriction).  A profile mapped to ``None`` (e.g. ``"full"``) also
    returns ``None``.  *extra_allow* / *extra_deny* let callers
    fine-tune the profile without duplicating the definition.
    """
    if profile_name is None:
        return None
    if profile_name not in TOOL_PROFILES:
        return None
    base = TOOL_PROFILES[profile_name]
    if base is None:
        # "full" or any unrestricted profile → no restriction
        return None
    result = set(base)
    if extra_allow:
        result.update(t for t in extra_allow if t)
    if extra_deny:
        result -= set(extra_deny)
    return frozenset(result)
