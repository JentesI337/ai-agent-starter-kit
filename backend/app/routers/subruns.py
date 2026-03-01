from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_subruns_router(
    *,
    subruns_list_handler: Callable[[str | None, str | None, str | None, str | None, int], JsonDict | Awaitable[JsonDict]],
    subrun_get_handler: Callable[[str, str, str | None], JsonDict | Awaitable[JsonDict]],
    subrun_log_handler: Callable[[str, str, str | None], JsonDict | Awaitable[JsonDict]],
    subrun_kill_handler: Callable[[str, str, str | None, bool], JsonDict | Awaitable[JsonDict]],
    subrun_kill_all_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/subruns")
    async def list_subruns(
        parent_session_id: str | None = None,
        parent_request_id: str | None = None,
        requester_session_id: str | None = None,
        visibility_scope: str | None = None,
        limit: int = 100,
    ):
        result = subruns_list_handler(
            parent_session_id,
            parent_request_id,
            requester_session_id,
            visibility_scope,
            limit,
        )
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/subruns/{run_id}")
    async def get_subrun_info(run_id: str, requester_session_id: str, visibility_scope: str | None = None):
        result = subrun_get_handler(run_id, requester_session_id, visibility_scope)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.get("/api/subruns/{run_id}/log")
    async def get_subrun_log(run_id: str, requester_session_id: str, visibility_scope: str | None = None):
        result = subrun_log_handler(run_id, requester_session_id, visibility_scope)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/subruns/{run_id}/kill")
    async def kill_subrun(
        run_id: str,
        requester_session_id: str,
        visibility_scope: str | None = None,
        cascade: bool = True,
    ):
        result = subrun_kill_handler(run_id, requester_session_id, visibility_scope, cascade)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/subruns/kill-all")
    async def kill_all_subruns(request: JsonDict):
        result = subrun_kill_all_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
