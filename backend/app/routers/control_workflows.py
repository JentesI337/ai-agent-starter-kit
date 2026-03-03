from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body, Header

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_workflows_router(
    *,
    workflows_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    workflows_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    workflows_create_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    workflows_update_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    workflows_execute_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    workflows_delete_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/workflows.list")
    async def control_workflows_list(request: JsonDict = Body(...)):
        result = workflows_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.get")
    async def control_workflows_get(request: JsonDict = Body(...)):
        result = workflows_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.create")
    async def control_workflows_create(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_create_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.update")
    async def control_workflows_update(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_update_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.execute")
    async def control_workflows_execute(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_execute_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/workflows.delete")
    async def control_workflows_delete(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = workflows_delete_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
