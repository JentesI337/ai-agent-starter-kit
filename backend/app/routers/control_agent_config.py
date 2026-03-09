"""RPC router for agents.config.* control endpoints."""
from __future__ import annotations
import inspect
from collections.abc import Awaitable, Callable
from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_agent_config_router(
    *,
    agents_config_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    agents_config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    agents_config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    agents_config_reset_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/agents.config.list")
    async def control_agents_config_list(request: JsonDict = Body(...)):
        result = agents_config_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agents.config.get")
    async def control_agents_config_get(request: JsonDict = Body(...)):
        result = agents_config_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agents.config.update")
    async def control_agents_config_update(request: JsonDict = Body(...)):
        result = agents_config_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agents.config.reset")
    async def control_agents_config_reset(request: JsonDict = Body(...)):
        result = agents_config_reset_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
