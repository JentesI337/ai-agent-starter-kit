from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_tools_router(
    *,
    tools_catalog_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_profile_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_policy_matrix_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    tools_policy_preview_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/tools.catalog")
    async def control_tools_catalog(request: JsonDict = Body(...)):
        result = tools_catalog_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.profile")
    async def control_tools_profile(request: JsonDict = Body(...)):
        result = tools_profile_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.policy.matrix")
    async def control_tools_policy_matrix(request: JsonDict = Body(...)):
        result = tools_policy_matrix_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/tools.policy.preview")
    async def control_tools_policy_preview(request: JsonDict = Body(...)):
        result = tools_policy_preview_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
