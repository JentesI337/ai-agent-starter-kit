"""Handlers for agents.config.* control endpoints.

Now delegates to UnifiedAgentStore instead of the removed AgentConfigStore.
"""
from __future__ import annotations

from typing import Any


# Lazy import to avoid circular dependencies
def _get_store():
    from app.agents.agent_store import UnifiedAgentStore
    # Use the module-level agent_store proxy from main
    from app.main import agent_store
    return agent_store


def handle_agents_config_list(request: dict[str, Any]) -> dict[str, Any]:
    store = _get_store()
    records = store.list_all()
    configs: dict[str, dict] = {}
    for record in records:
        configs[record.agent_id] = {
            "agent_id": record.agent_id,
            **record.constraints.model_dump(),
            "read_only": record.tool_policy.read_only,
            "mandatory_deny_tools": record.tool_policy.mandatory_deny,
            "additional_deny_tools": record.tool_policy.additional_deny,
            "additional_allow_tools": record.tool_policy.additional_allow,
        }
    return {"configs": configs}


def handle_agents_config_get(request: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(request.get("agentId") or "").strip()
    if not agent_id:
        return {"error": "agentId is required"}
    store = _get_store()
    record = store.get(agent_id)
    if record is None:
        return {"error": f"Agent not found: {agent_id}"}
    return {
        "config": {
            "agent_id": record.agent_id,
            **record.constraints.model_dump(),
            "read_only": record.tool_policy.read_only,
            "mandatory_deny_tools": record.tool_policy.mandatory_deny,
            "additional_deny_tools": record.tool_policy.additional_deny,
            "additional_allow_tools": record.tool_policy.additional_allow,
        }
    }


def handle_agents_config_update(request: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(request.get("agentId") or "").strip()
    updates = request.get("updates")
    if not agent_id:
        return {"error": "agentId is required"}
    if not isinstance(updates, dict) or not updates:
        return {"error": "updates must be a non-empty object"}

    store = _get_store()

    # Map flat config fields to nested UnifiedAgentRecord structure
    patch: dict[str, Any] = {}
    constraint_keys = {"temperature", "reflection_passes", "reasoning_depth", "max_context", "combine_steps"}
    constraint_patch = {k: v for k, v in updates.items() if k in constraint_keys}
    if constraint_patch:
        patch["constraints"] = constraint_patch

    tp_keys = {"read_only", "mandatory_deny_tools", "additional_deny_tools", "additional_allow_tools"}
    tp_patch: dict[str, Any] = {}
    if "read_only" in updates:
        tp_patch["read_only"] = updates["read_only"]
    if "mandatory_deny_tools" in updates:
        tp_patch["mandatory_deny"] = updates["mandatory_deny_tools"]
    if "additional_deny_tools" in updates:
        tp_patch["additional_deny"] = updates["additional_deny_tools"]
    if "additional_allow_tools" in updates:
        tp_patch["additional_allow"] = updates["additional_allow_tools"]
    if tp_patch:
        patch["tool_policy"] = tp_patch

    try:
        record = store.update(agent_id, patch)
        return {
            "ok": True,
            "config": {
                "agent_id": record.agent_id,
                **record.constraints.model_dump(),
                "read_only": record.tool_policy.read_only,
                "mandatory_deny_tools": record.tool_policy.mandatory_deny,
                "additional_deny_tools": record.tool_policy.additional_deny,
                "additional_allow_tools": record.tool_policy.additional_allow,
            },
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def handle_agents_config_reset(request: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(request.get("agentId") or "").strip()
    if not agent_id:
        return {"error": "agentId is required"}
    store = _get_store()
    try:
        record = store.reset(agent_id)
        return {
            "ok": True,
            "config": {
                "agent_id": record.agent_id,
                **record.constraints.model_dump(),
                "read_only": record.tool_policy.read_only,
                "mandatory_deny_tools": record.tool_policy.mandatory_deny,
                "additional_deny_tools": record.tool_policy.additional_deny,
                "additional_allow_tools": record.tool_policy.additional_allow,
            },
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
