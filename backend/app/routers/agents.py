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
    presets_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]],
    custom_agents_list_handler: Callable[[], JsonDict | list[JsonDict] | Awaitable[JsonDict | list[JsonDict]]],
    custom_agents_create_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    custom_agents_update_handler: Callable[[str, JsonDict], JsonDict | Awaitable[JsonDict]],
    custom_agents_delete_handler: Callable[[str], JsonDict | Awaitable[JsonDict]],
    monitoring_schema_handler: Callable[[], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/agents")
    async def get_agents():
        result = agents_list_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

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
