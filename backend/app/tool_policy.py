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
