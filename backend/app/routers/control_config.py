"""RPC router for config.* control endpoints."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_config_router(
    *,
    config_sections_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    config_diff_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    config_reset_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/config.sections")
    async def control_config_sections(request: JsonDict = Body(...)):
        result = config_sections_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.get")
    async def control_config_get(request: JsonDict = Body(...)):
        result = config_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.update")
    async def control_config_update(request: JsonDict = Body(...)):
        result = config_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.diff")
    async def control_config_diff(request: JsonDict = Body(...)):
        result = config_diff_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.reset")
    async def control_config_reset(request: JsonDict = Body(...)):
        result = config_reset_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
