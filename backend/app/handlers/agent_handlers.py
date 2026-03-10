from __future__ import annotations

import uuid
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.agents.unified_agent_record import UnifiedAgentRecord
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
    agent_store: Any = None  # UnifiedAgentStore — new unified store


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


def _enrich_agent_entry(agent_id: str, agent_instance: Any, default_model: str) -> dict:
    """Build an enriched agent descriptor with full metadata."""
    record: UnifiedAgentRecord | None = getattr(agent_instance, "record", None)

    entry: dict[str, Any] = {
        "id": agent_id,
        "name": agent_instance.name,
        "role": getattr(agent_instance, "role", "agent"),
        "status": "ready",
        "defaultModel": default_model,
        "isBuiltin": record is not None and record.origin == "builtin",
    }

    if record is not None:
        entry.update({
            "displayName": record.display_name,
            "description": record.description,
            "category": record.category,
            "enabled": record.enabled,
            "reasoningStrategy": record.reasoning_strategy,
            "specialization": record.specialization,
            "capabilities": record.capabilities,
            "toolPolicy": {
                "readOnly": record.tool_policy.read_only,
                "mandatoryDeny": record.tool_policy.mandatory_deny,
                "preferredTools": record.tool_policy.preferred_tools,
                "forbiddenTools": record.tool_policy.forbidden_tools,
            },
            "promptKeys": {
                "system": record.prompts.fallback_system_key,
                "plan": record.prompts.fallback_plan_key,
                "toolSelector": record.prompts.fallback_tool_selector_key,
                "toolRepair": record.prompts.fallback_tool_repair_key,
                "final": record.prompts.fallback_final_key,
            },
            "autonomyLevel": record.delegation.autonomy_level,
            "confidenceThreshold": record.delegation.confidence_threshold,
            "delegationPreference": record.delegation.delegation_preference,
            "constraints": record.constraints.model_dump(),
        })
    else:
        entry.update({
            "displayName": agent_instance.name,
            "description": "",
            "category": "custom",
            "capabilities": [],
        })

    return entry


def api_agents_list_enriched() -> list[dict]:
    """Enriched agent listing with full metadata from canonical definitions."""
    deps = _require_deps()
    deps.sync_custom_agents()
    active = deps.runtime_manager.get_state()
    items = [
        _enrich_agent_entry(agent_id, agent_instance, active.model)
        for agent_id, agent_instance in deps.agent_registry.items()
    ]
    items.sort(key=lambda item: item["id"])
    return items


def api_agent_detail(agent_id: str) -> dict:
    """Full metadata for a single agent."""
    deps = _require_deps()
    deps.sync_custom_agents()
    normalized = deps.normalize_agent_id(agent_id)
    agent_instance = deps.agent_registry.get(normalized)
    if agent_instance is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    active = deps.runtime_manager.get_state()
    return _enrich_agent_entry(normalized, agent_instance, active.model)


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


def api_custom_agents_update(agent_id: str, patch_data: dict) -> CustomAgentDefinition:
    deps = _require_deps()
    normalized = deps.normalize_agent_id(agent_id)
    existing = deps.custom_agent_store.get(normalized)
    if existing is None:
        raise HTTPException(status_code=404, detail="Custom agent not found")

    merged = existing.model_dump()
    for key, value in patch_data.items():
        if key in merged:
            merged[key] = value
    merged["id"] = normalized  # keep original id

    request = CustomAgentCreateRequest.model_validate(merged)
    if request.base_agent_id and deps.normalize_agent_id(request.base_agent_id) not in deps.agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    updated = deps.custom_agent_store.upsert(request)
    deps.sync_custom_agents()
    return updated


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


# ---------------------------------------------------------------------------
# Unified Agent Store API handlers (Phase 4)
# ---------------------------------------------------------------------------


def _require_agent_store():
    deps = _require_deps()
    if deps.agent_store is None:
        raise RuntimeError("agent_store not configured in handler dependencies")
    return deps.agent_store


def _record_to_api(record: UnifiedAgentRecord) -> dict:
    """Convert a UnifiedAgentRecord to an API-friendly dict."""
    return {
        "agentId": record.agent_id,
        "origin": record.origin,
        "enabled": record.enabled,
        "displayName": record.display_name,
        "description": record.description,
        "category": record.category,
        "role": record.role,
        "reasoningStrategy": record.reasoning_strategy,
        "specialization": record.specialization,
        "capabilities": record.capabilities,
        "constraints": record.constraints.model_dump(),
        "toolPolicy": record.tool_policy.model_dump(),
        "prompts": record.prompts.model_dump(),
        "delegation": record.delegation.model_dump(),
        "behavior": record.behavior.model_dump(),
        "customWorkflow": record.custom_workflow.model_dump() if record.custom_workflow else None,
        "costTier": record.cost_tier,
        "latencyTier": record.latency_tier,
        "qualityTier": record.quality_tier,
        "version": record.version,
    }


def api_agent_patch(agent_id: str, patch: dict) -> dict:
    """Partial update of any agent via UnifiedAgentStore."""
    deps = _require_deps()
    store = _require_agent_store()
    normalized = deps.normalize_agent_id(agent_id)

    try:
        record = store.update(normalized, patch)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    deps.sync_custom_agents()
    return _record_to_api(record)


def api_agent_create(data: dict) -> dict:
    """Create a new custom agent via UnifiedAgentStore."""
    store = _require_agent_store()
    deps = _require_deps()

    try:
        record = store.create(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    deps.sync_custom_agents()
    return _record_to_api(record)


def api_agent_delete(agent_id: str) -> dict:
    """Delete a custom agent via UnifiedAgentStore."""
    deps = _require_deps()
    store = _require_agent_store()
    normalized = deps.normalize_agent_id(agent_id)

    try:
        deleted = store.delete(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    deps.sync_custom_agents()
    return {"ok": True, "deletedId": normalized}


def api_agent_reset(agent_id: str) -> dict:
    """Restore a built-in agent to factory defaults."""
    deps = _require_deps()
    store = _require_agent_store()
    normalized = deps.normalize_agent_id(agent_id)

    try:
        record = store.reset(normalized)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No factory default for agent: {agent_id}")

    deps.sync_custom_agents()
    return _record_to_api(record)


def api_manifest_get() -> dict:
    """Get the current agent manifest."""
    store = _require_agent_store()
    return store.get_manifest()


def api_manifest_update(data: dict) -> dict:
    """Update the agent manifest."""
    store = _require_agent_store()
    return store.update_manifest(data)


def api_agents_list_unified() -> list[dict]:
    """List ALL agents (builtin + custom, enabled + disabled) from the store."""
    store = _require_agent_store()
    records = store.list_all()
    return [_record_to_api(r) for r in records]
