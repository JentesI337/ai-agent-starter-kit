"""Handlers for agents.config.* control endpoints."""
from __future__ import annotations
from typing import Any
from app.agents.agent_config_store import get_agent_config_store


def handle_agents_config_list(request: dict[str, Any]) -> dict[str, Any]:
    store = get_agent_config_store()
    configs = store.get_all()
    return {
        "configs": {
            agent_id: config.model_dump()
            for agent_id, config in configs.items()
        },
    }


def handle_agents_config_get(request: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(request.get("agentId") or "").strip()
    if not agent_id:
        return {"error": "agentId is required"}
    store = get_agent_config_store()
    config = store.get(agent_id)
    return {"config": config.model_dump()}


def handle_agents_config_update(request: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(request.get("agentId") or "").strip()
    updates = request.get("updates")
    if not agent_id:
        return {"error": "agentId is required"}
    if not isinstance(updates, dict) or not updates:
        return {"error": "updates must be a non-empty object"}
    store = get_agent_config_store()
    try:
        config = store.update(agent_id, updates)
        return {"ok": True, "config": config.model_dump()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def handle_agents_config_reset(request: dict[str, Any]) -> dict[str, Any]:
    agent_id = str(request.get("agentId") or "").strip()
    if not agent_id:
        return {"error": "agentId is required"}
    store = get_agent_config_store()
    config = store.reset(agent_id)
    return {"ok": True, "config": config.model_dump()}
