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
    skills_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    skills_preview_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    skills_check_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    skills_sync_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    context_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    context_detail_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    config_health_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    memory_overview_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
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

    @router.post("/api/control/skills.list")
    async def control_skills_list(request: JsonDict = Body(...)):
        result = skills_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/skills.preview")
    async def control_skills_preview(request: JsonDict = Body(...)):
        result = skills_preview_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/skills.check")
    async def control_skills_check(request: JsonDict = Body(...)):
        result = skills_check_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/skills.sync")
    async def control_skills_sync(request: JsonDict = Body(...)):
        result = skills_sync_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/context.list")
    async def control_context_list(request: JsonDict = Body(...)):
        result = context_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/context.detail")
    async def control_context_detail(request: JsonDict = Body(...)):
        result = context_detail_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.health")
    async def control_config_health(request: JsonDict = Body(...)):
        result = config_health_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/memory.overview")
    async def control_memory_overview(request: JsonDict = Body(...)):
        result = memory_overview_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
