from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Body

JsonDict = dict


def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_control_policy_approvals_router(
    *,
    policy_approvals_pending_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    policy_approvals_allow_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
    policy_approvals_decide_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/policy-approvals.pending")
    async def control_policy_approvals_pending(request: JsonDict = Body(...)):
        result = policy_approvals_pending_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/policy-approvals.allow")
    async def control_policy_approvals_allow(request: JsonDict = Body(...)):
        result = policy_approvals_allow_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/policy-approvals.decide")
    async def control_policy_approvals_decide(request: JsonDict = Body(...)):
        result = policy_approvals_decide_handler(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
