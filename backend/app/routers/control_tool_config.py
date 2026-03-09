"""RPC router for tools.config.* and tools.security.* control endpoints."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Body

JsonDict = dict[str, Any]


def _maybe_await(result: Any) -> Awaitable[Any] | None:
    if inspect.isawaitable(result):
        return result
    return None


def build_control_tool_config_router(
    *,
    tools_config_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_config_reset_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_security_patterns_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_security_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/tools.config.list")
    async def control_tools_config_list(request: JsonDict = Body(...)) -> JsonDict:
        result = tools_config_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.config.get")
    async def control_tools_config_get(request: JsonDict = Body(...)) -> JsonDict:
        result = tools_config_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.config.update")
    async def control_tools_config_update(request: JsonDict = Body(...)) -> JsonDict:
        result = tools_config_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.config.reset")
    async def control_tools_config_reset(request: JsonDict = Body(...)) -> JsonDict:
        result = tools_config_reset_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.security.patterns")
    async def control_tools_security_patterns(request: JsonDict = Body(...)) -> JsonDict:
        result = tools_security_patterns_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.security.update")
    async def control_tools_security_update(request: JsonDict = Body(...)) -> JsonDict:
        result = tools_security_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
