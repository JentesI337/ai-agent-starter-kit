from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body, Header

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_sessions_router(
    *,
    sessions_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    sessions_resolve_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    sessions_history_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    sessions_send_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    sessions_spawn_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    sessions_status_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    sessions_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    sessions_patch_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    sessions_reset_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/sessions.list")
    async def control_sessions_list(request: JsonDict = Body(...)):
        result = sessions_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.resolve")
    async def control_sessions_resolve(request: JsonDict = Body(...)):
        result = sessions_resolve_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.history")
    async def control_sessions_history(request: JsonDict = Body(...)):
        result = sessions_history_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.send")
    async def control_sessions_send(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = sessions_send_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.spawn")
    async def control_sessions_spawn(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = sessions_spawn_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.status")
    async def control_sessions_status(request: JsonDict = Body(...)):
        result = sessions_status_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.get")
    async def control_sessions_get(request: JsonDict = Body(...)):
        result = sessions_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.patch")
    async def control_sessions_patch(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = sessions_patch_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/sessions.reset")
    async def control_sessions_reset(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = sessions_reset_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
