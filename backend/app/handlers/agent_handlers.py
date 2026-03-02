from __future__ import annotations

import uuid
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.custom_agents import CustomAgentCreateRequest, CustomAgentDefinition
from app.orchestrator.events import LifecycleStage
from app.services import PRESET_TOOL_POLICIES


@dataclass
class AgentHandlerDependencies:
    runtime_manager: Any
    agent_registry: MutableMapping[str, Any]
    custom_agent_store: Any
    sync_custom_agents: Callable[[], None]
    normalize_agent_id: Callable[[str | None], str]
    get_agent_tools: Callable[[Any], list[str]]
    primary_agent_id: str
    coder_agent_id: str
    review_agent_id: str


_deps: AgentHandlerDependencies | None = None


def configure(deps: AgentHandlerDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> AgentHandlerDependencies:
    if _deps is None:
        raise RuntimeError("agent_handlers is not configured")
    return _deps


def api_agents_list() -> list[dict]:
    deps = _require_deps()
    deps.sync_custom_agents()
    active = deps.runtime_manager.get_state()
    items: list[dict] = []
    for agent_id, agent_instance in deps.agent_registry.items():
        items.append(
            {
                "id": agent_id,
                "name": agent_instance.name,
                "role": getattr(agent_instance, "role", "agent"),
                "status": "ready",
                "defaultModel": active.model,
            }
        )
    items.sort(key=lambda item: item["id"])
    return items


def api_presets_list() -> list[dict]:
    items: list[dict] = []
    for preset_id in sorted(PRESET_TOOL_POLICIES.keys()):
        policy = PRESET_TOOL_POLICIES[preset_id]
        items.append(
            {
                "id": preset_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
        )
    return items


def api_custom_agents_list() -> list[CustomAgentDefinition]:
    deps = _require_deps()
    return deps.custom_agent_store.list()


def api_custom_agents_create(request_data: dict) -> CustomAgentDefinition:
    deps = _require_deps()
    request = CustomAgentCreateRequest.model_validate(request_data)
    base_agent_id = deps.normalize_agent_id(request.base_agent_id)
    if base_agent_id not in deps.agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    created = deps.custom_agent_store.upsert(
        request,
        id_factory=lambda name: f"custom-{name}-{str(uuid.uuid4())[:8]}",
    )
    deps.sync_custom_agents()
    return created


def api_custom_agents_delete(agent_id: str) -> dict:
    deps = _require_deps()
    normalized = deps.normalize_agent_id(agent_id)
    if normalized in {deps.primary_agent_id, deps.coder_agent_id, deps.review_agent_id}:
        raise HTTPException(status_code=400, detail="Built-in agents cannot be deleted")

    deleted = deps.custom_agent_store.delete(normalized)
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom agent not found")

    deps.sync_custom_agents()
    return {"ok": True, "deletedId": normalized}


def api_monitoring_schema() -> dict:
    deps = _require_deps()
    deps.sync_custom_agents()
    return {
        "lifecycleStages": [stage.value for stage in LifecycleStage],
        "eventTypes": [
            "status",
            "lifecycle",
            "agent_step",
            "token",
            "final",
            "error",
            "subrun_status",
            "subrun_announce",
            "runtime_switch_done",
            "runtime_switch_error",
        ],
        "reasoningVisibility": {
            "chainOfThought": "hidden",
            "observableTrace": "available_via_lifecycle_and_tool_events",
        },
        "agents": [
            {
                "id": agent_id,
                "name": agent_instance.name,
                "role": getattr(agent_instance, "role", "agent"),
                "tools": deps.get_agent_tools(agent_instance),
            }
            for agent_id, agent_instance in deps.agent_registry.items()
        ],
    }
