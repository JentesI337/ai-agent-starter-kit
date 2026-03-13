"""Policy management endpoints."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.control_models import (
    ControlPolicyApprovalsAllowRequest,
    ControlPolicyApprovalsDecideRequest,
    ControlPolicyApprovalsPendingRequest,
)
from app.policy.store import PolicyCreateRequest, PolicyStore

JsonDict = dict


# === Handler dependencies ===

@dataclass
class PolicyHandlerDependencies:
    policy_approval_service: Any


_deps: PolicyHandlerDependencies | None = None


def configure(deps: PolicyHandlerDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> PolicyHandlerDependencies:
    if _deps is None:
        raise RuntimeError("policy_handlers is not configured")
    return _deps


# === Handler functions ===

async def api_control_policy_approvals_pending(request_data: dict) -> dict:
    deps = _require_deps()
    request = ControlPolicyApprovalsPendingRequest.model_validate(request_data)
    items = await deps.policy_approval_service.list_pending(
        run_id=request.run_id,
        session_id=request.session_id,
        limit=request.limit,
    )
    return {
        "schema": "policy.approvals.pending.v1",
        "items": items,
        "count": len(items),
    }


async def api_control_policy_approvals_allow(request_data: dict) -> dict:
    deps = _require_deps()
    request = ControlPolicyApprovalsAllowRequest.model_validate(request_data)
    updated = await deps.policy_approval_service.allow(request.approval_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "schema": "policy.approvals.allow.v1",
        "approval": updated,
    }


async def api_control_policy_approvals_decide(request_data: dict) -> dict:
    deps = _require_deps()
    request = ControlPolicyApprovalsDecideRequest.model_validate(request_data)
    normalized_decision = (request.decision or "").strip().lower()
    if normalized_decision not in {"allow_once", "allow_always", "deny"}:
        raise HTTPException(status_code=400, detail="Unsupported policy approval decision")

    try:
        updated = await deps.policy_approval_service.decide(
            request.approval_id,
            normalized_decision,
            scope=request.scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "schema": "policy.approvals.decide.v1",
        "approval": updated,
    }


# === Backward-compat builders ===

def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


def build_policies_router(*, policy_store: PolicyStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/policies")
    def list_policies():
        items = policy_store.list()
        return {
            "schema": "policy-list-v1",
            "items": [item.model_dump() for item in items],
            "count": len(items),
        }

    @router.get("/api/policies/{policy_id}")
    def get_policy(policy_id: str):
        item = policy_store.get(policy_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        return item.model_dump()

    @router.post("/api/policies")
    def create_policy(payload: JsonDict = Body(...)):
        request = PolicyCreateRequest.model_validate(payload)
        created = policy_store.create(request)
        return created.model_dump()

    @router.patch("/api/policies/{policy_id}")
    def update_policy(policy_id: str, patch: JsonDict = Body(...)):
        updated = policy_store.update(policy_id, patch)
        if updated is None:
            raise HTTPException(status_code=404, detail="Policy not found")
        return updated.model_dump()

    @router.delete("/api/policies/{policy_id}")
    def delete_policy(policy_id: str):
        deleted = policy_store.delete(policy_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Policy not found")
        return {"ok": True}

    return router


def build_control_policy_approvals_router(
    *,
    policy_approvals_pending_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    policy_approvals_allow_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    policy_approvals_decide_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/policy-approvals.pending")
    async def control_policy_approvals_pending(request: JsonDict = Body(...)):
        h = policy_approvals_pending_handler or api_control_policy_approvals_pending
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/policy-approvals.allow")
    async def control_policy_approvals_allow(request: JsonDict = Body(...)):
        h = policy_approvals_allow_handler or api_control_policy_approvals_allow
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/policy-approvals.decide")
    async def control_policy_approvals_decide(request: JsonDict = Body(...)):
        h = policy_approvals_decide_handler or api_control_policy_approvals_decide
        result = h(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
