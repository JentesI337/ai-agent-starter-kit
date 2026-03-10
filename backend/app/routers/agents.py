from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_agents_router(
    *,
    agents_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]],
    agents_list_enriched_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]] | None = None,
    agent_detail_handler: Callable[[str], JsonDict | Awaitable[JsonDict]] | None = None,
    presets_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]],
    custom_agents_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]],
    custom_agents_create_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    custom_agents_update_handler: Callable[[str, JsonDict], JsonDict | Awaitable[JsonDict]],
    custom_agents_delete_handler: Callable[[str], JsonDict | Awaitable[JsonDict]],
    monitoring_schema_handler: Callable[[], JsonDict | Awaitable[JsonDict]],
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
            result = agents_list_handler()
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
        result = presets_list_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/custom-agents")
    async def get_custom_agents():
        result = custom_agents_list_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/custom-agents")
    async def create_custom_agent(request: JsonDict = Body(...)):
        result = custom_agents_create_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.delete("/api/custom-agents/{agent_id}")
    async def delete_custom_agent(agent_id: str):
        result = custom_agents_delete_handler(agent_id)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.patch("/api/custom-agents/{agent_id}")
    async def update_custom_agent(agent_id: str, patch: JsonDict = Body(...)):
        result = custom_agents_update_handler(agent_id, patch)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/monitoring/schema")
    async def get_monitoring_schema():
        result = monitoring_schema_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
