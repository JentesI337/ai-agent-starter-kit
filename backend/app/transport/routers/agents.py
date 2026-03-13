"""Agent management endpoints."""
from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agent.record import UnifiedAgentRecord
from app.orchestration.events import LifecycleStage
from app.tools.provisioning.policy_service import PRESET_TOOL_POLICIES

JsonDict = dict


# === Handler dependencies ===

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


# === Handler functions ===

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


def api_custom_agents_list() -> list:
    deps = _require_deps()
    return deps.custom_agent_store.list()


def api_custom_agents_create(request_data: dict) -> Any:
    deps = _require_deps()
    request = SimpleNamespace(**request_data)
    base_agent_id = deps.normalize_agent_id(getattr(request, "base_agent_id", "head-agent"))
    if base_agent_id not in deps.agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {base_agent_id}")

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


def api_custom_agents_update(agent_id: str, patch_data: dict) -> Any:
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

    request = SimpleNamespace(**merged)
    base_agent_id = getattr(request, "base_agent_id", "")
    if base_agent_id and deps.normalize_agent_id(base_agent_id) not in deps.agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {base_agent_id}")

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


# === Agent config handlers (from agent_config_handlers.py) ===

def _get_store():
    from app.agent.store import UnifiedAgentStore
    from app.transport.runtime_wiring import agent_store
    return agent_store


def handle_agents_config_list(request: dict[str, Any]) -> dict[str, Any]:
    store = _get_store()
    records = store.list_all()
    agents: list[dict] = []
    for record in records:
        agents.append({
            "agent_id": record.agent_id,
            **record.constraints.model_dump(),
            "read_only": record.tool_policy.read_only,
            "mandatory_deny_tools": record.tool_policy.mandatory_deny,
            "additional_deny_tools": record.tool_policy.additional_deny,
            "additional_allow_tools": record.tool_policy.additional_allow,
        })
    return {"agents": agents}


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

    patch: dict[str, Any] = {}
    constraint_keys = {"temperature", "reflection_passes", "reasoning_depth", "max_context", "combine_steps"}
    constraint_patch = {k: v for k, v in updates.items() if k in constraint_keys}
    if constraint_patch:
        patch["constraints"] = constraint_patch

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


# === Backward-compat builders ===

def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_agents_router(
    *,
    agents_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]] | None = None,
    agents_list_enriched_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]] | None = None,
    agent_detail_handler: Callable[[str], JsonDict | Awaitable[JsonDict]] | None = None,
    presets_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]] | None = None,
    custom_agents_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]] | None = None,
    custom_agents_create_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    custom_agents_update_handler: Callable[[str, JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    custom_agents_delete_handler: Callable[[str], JsonDict | Awaitable[JsonDict]] | None = None,
    monitoring_schema_handler: Callable[[], JsonDict | Awaitable[JsonDict]] | None = None,
    # Unified store handlers (Phase 4)
    agent_patch_handler: Callable[[str, JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agent_create_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agent_delete_handler: Callable[[str], JsonDict | Awaitable[JsonDict]] | None = None,
    agent_reset_handler: Callable[[str], JsonDict | Awaitable[JsonDict]] | None = None,
    manifest_get_handler: Callable[[], JsonDict | Awaitable[JsonDict]] | None = None,
    manifest_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agents_list_unified_handler: Callable[[], list[JsonDict] | Awaitable[list[JsonDict]]] | None = None,
) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------
    # Static /api/agents/* routes MUST be registered before {agent_id}
    # ------------------------------------------------------------------

    @router.get("/api/agents")
    async def get_agents(detail: bool = False):
        if detail and agents_list_enriched_handler is not None:
            result = agents_list_enriched_handler()
        else:
            h = agents_list_handler or api_agents_list
            result = h()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    if agents_list_unified_handler is not None:
        @router.get("/api/agents/store")
        async def get_agents_store():
            """List ALL agents (builtin + custom, enabled + disabled) from the unified store."""
            result = agents_list_unified_handler()
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if manifest_get_handler is not None:
        @router.get("/api/agents/manifest")
        async def get_manifest():
            result = manifest_get_handler()
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if manifest_update_handler is not None:
        @router.put("/api/agents/manifest")
        async def update_manifest(data: JsonDict = Body(...)):
            result = manifest_update_handler(data)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if agent_create_handler is not None:
        @router.post("/api/agents")
        async def create_agent(data: JsonDict = Body(...)):
            result = agent_create_handler(data)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    # ------------------------------------------------------------------
    # Parameterized /api/agents/{agent_id} routes
    # ------------------------------------------------------------------

    if agent_detail_handler is not None:
        @router.get("/api/agents/{agent_id}")
        async def get_agent_detail(agent_id: str):
            result = agent_detail_handler(agent_id)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if agent_patch_handler is not None:
        @router.patch("/api/agents/{agent_id}")
        async def patch_agent(agent_id: str, patch: JsonDict = Body(...)):
            result = agent_patch_handler(agent_id, patch)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if agent_delete_handler is not None:
        @router.delete("/api/agents/{agent_id}")
        async def delete_agent(agent_id: str):
            result = agent_delete_handler(agent_id)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if agent_reset_handler is not None:
        @router.post("/api/agents/{agent_id}/reset")
        async def reset_agent(agent_id: str):
            result = agent_reset_handler(agent_id)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    # ------------------------------------------------------------------
    # Other endpoints
    # ------------------------------------------------------------------

    @router.get("/api/presets")
    async def get_presets():
        h = presets_list_handler or api_presets_list
        result = h()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/custom-agents")
    async def get_custom_agents():
        h = custom_agents_list_handler or api_custom_agents_list
        result = h()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/custom-agents")
    async def create_custom_agent(request: JsonDict = Body(...)):
        h = custom_agents_create_handler or api_custom_agents_create
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.delete("/api/custom-agents/{agent_id}")
    async def delete_custom_agent(agent_id: str):
        h = custom_agents_delete_handler or api_custom_agents_delete
        result = h(agent_id)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.patch("/api/custom-agents/{agent_id}")
    async def update_custom_agent(agent_id: str, patch: JsonDict = Body(...)):
        h = custom_agents_update_handler or api_custom_agents_update
        result = h(agent_id, patch)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/monitoring/schema")
    async def get_monitoring_schema():
        h = monitoring_schema_handler or api_monitoring_schema
        result = h()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router


def build_control_agent_config_router(
    *,
    agents_config_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agents_config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agents_config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    agents_config_reset_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/agents.config.list")
    async def control_agents_config_list(request: JsonDict = Body(...)):
        h = agents_config_list_handler or handle_agents_config_list
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agents.config.get")
    async def control_agents_config_get(request: JsonDict = Body(...)):
        h = agents_config_get_handler or handle_agents_config_get
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agents.config.update")
    async def control_agents_config_update(request: JsonDict = Body(...)):
        h = agents_config_update_handler or handle_agents_config_update
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agents.config.reset")
    async def control_agents_config_reset(request: JsonDict = Body(...)):
        h = agents_config_reset_handler or handle_agents_config_reset
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
