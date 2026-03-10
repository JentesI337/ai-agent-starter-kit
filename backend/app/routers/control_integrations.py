"""Router for integration/connector management endpoints."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import HTMLResponse

JsonDict = dict[str, Any]


def _maybe_await(result: Any) -> Awaitable[Any] | None:
    if inspect.isawaitable(result):
        return result
    return None


def build_control_integrations_router(
    *,
    connectors_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    connectors_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    connectors_create_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    connectors_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    connectors_delete_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    connectors_test_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    oauth_start_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    oauth_callback_handler: Callable[[str, str], Awaitable[str]],
    oauth_status_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/integrations.connectors.list")
    async def control_connectors_list(request: JsonDict = Body(default={})):
        result = connectors_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/integrations.connectors.get")
    async def control_connectors_get(request: JsonDict = Body(...)):
        result = connectors_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/integrations.connectors.create")
    async def control_connectors_create(request: JsonDict = Body(...)):
        result = connectors_create_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/integrations.connectors.update")
    async def control_connectors_update(request: JsonDict = Body(...)):
        result = connectors_update_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/integrations.connectors.delete")
    async def control_connectors_delete(request: JsonDict = Body(...)):
        result = connectors_delete_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/integrations.connectors.test")
    async def control_connectors_test(request: JsonDict = Body(...)):
        result = connectors_test_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/integrations.oauth.start")
    async def control_oauth_start(request: JsonDict = Body(...)):
        result = oauth_start_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/integrations/oauth/callback")
    async def oauth_callback(code: str = Query(...), state: str = Query(...)):
        html = await oauth_callback_handler(code, state)
        return HTMLResponse(content=html)

    @router.post("/api/control/integrations.oauth.status")
    async def control_oauth_status(request: JsonDict = Body(...)):
        result = oauth_status_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
