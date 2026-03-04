from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_runtime_debug_router(
    *,
    runtime_status_handler: Callable[[], JsonDict | Awaitable[JsonDict]],
    runtime_features_handler: Callable[[], JsonDict | Awaitable[JsonDict]],
    runtime_update_features_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    resolved_prompts_handler: Callable[[], JsonDict | Awaitable[JsonDict]],
    ping_handler: Callable[[], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/runtime/status")
    async def get_runtime_status():
        result = runtime_status_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/runtime/features")
    async def get_runtime_features():
        result = runtime_features_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/runtime/features")
    async def post_runtime_features(request: JsonDict = Body(...)):
        result = runtime_update_features_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/debug/prompts/resolved")
    async def get_resolved_prompt_settings():
        result = resolved_prompts_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/test/ping")
    async def test_ping():
        result = ping_handler()
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
