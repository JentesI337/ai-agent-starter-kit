from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body, Header

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_runs_router(
    *,
    run_start_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    run_wait_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    agent_run_handler: Callable[[JsonDict, str | None], JsonDict | Awaitable[JsonDict]],
    agent_wait_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    runs_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    runs_list_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    runs_events_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    runs_audit_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/run.start")
    async def control_run_start(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = run_start_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/run.wait")
    async def control_run_wait(request: JsonDict = Body(...)):
        result = run_wait_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agent.run")
    async def control_agent_run(
        request: JsonDict = Body(...),
        idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        result = agent_run_handler(request, idempotency_key_header)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/agent.wait")
    async def control_agent_wait(request: JsonDict = Body(...)):
        result = agent_wait_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.get")
    async def control_runs_get(request: JsonDict = Body(...)):
        result = runs_get_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.list")
    async def control_runs_list(request: JsonDict = Body(...)):
        result = runs_list_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.events")
    async def control_runs_events(request: JsonDict = Body(...)):
        result = runs_events_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/runs.audit")
    async def control_runs_audit(request: JsonDict = Body(...)):
        result = runs_audit_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
