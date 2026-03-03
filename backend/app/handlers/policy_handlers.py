from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.control_models import (
    ControlPolicyApprovalsAllowRequest,
    ControlPolicyApprovalsDecideRequest,
    ControlPolicyApprovalsPendingRequest,
)


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
