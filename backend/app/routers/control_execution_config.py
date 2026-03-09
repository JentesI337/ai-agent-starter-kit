"""RPC router for execution.config.* and execution.loop-detection.* control endpoints."""
from __future__ import annotations
import inspect
from collections.abc import Awaitable, Callable
from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_execution_config_router(
    *,
    execution_config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    execution_config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    execution_loop_detection_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    execution_loop_detection_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/execution.config.get")
    async def control_execution_config_get(request: JsonDict = Body(...)):
        result = execution_config_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/execution.config.update")
    async def control_execution_config_update(request: JsonDict = Body(...)):
        result = execution_config_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/execution.loop-detection.get")
    async def control_execution_loop_detection_get(request: JsonDict = Body(...)):
        result = execution_loop_detection_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/execution.loop-detection.update")
    async def control_execution_loop_detection_update(request: JsonDict = Body(...)):
        result = execution_loop_detection_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
