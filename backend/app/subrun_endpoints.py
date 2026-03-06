from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


class KillAllSubrunsRequest(BaseModel):
    parent_session_id: str | None = None
    parent_request_id: str | None = None
    cascade: bool = True
    requester_session_id: str | None = None
    visibility_scope: str | None = None


@dataclass(frozen=True)
class SubrunEndpointsDependencies:
    subrun_lane: Any
    session_visibility_default: str
    state_append_event_safe: Callable[..., None]


def _normalize_visibility_scope(value: str | None, deps: SubrunEndpointsDependencies) -> str:
    scope = (value or deps.session_visibility_default or "tree").strip().lower()
    if scope not in {"self", "tree", "agent", "all"}:
        return "tree"
    return scope


def _enforce_subrun_visibility_or_403(
    run_id: str,
    requester_session_id: str | None,
    visibility_scope: str | None,
    deps: SubrunEndpointsDependencies,
) -> dict:
    scope = _normalize_visibility_scope(visibility_scope, deps)
    allowed, decision = deps.subrun_lane.evaluate_visibility(
        run_id,
        requester_session_id=(requester_session_id or ""),
        visibility_scope=scope,
    )

    deps.state_append_event_safe(
        run_id=run_id,
        event={
            "type": "visibility_decision",
            "decision": decision,
        },
    )

    if not allowed:
        raise HTTPException(status_code=403, detail={"message": "Subrun visibility denied", "decision": decision})
    return decision


def api_subruns_list(
    *,
    parent_session_id: str | None,
    parent_request_id: str | None,
    requester_session_id: str | None,
    visibility_scope: str | None,
    limit: int,
    deps: SubrunEndpointsDependencies,
) -> dict:
    scope = _normalize_visibility_scope(visibility_scope, deps)
    return {
        "items": deps.subrun_lane.list_runs(
            parent_session_id=parent_session_id,
            parent_request_id=parent_request_id,
            requester_session_id=requester_session_id,
            visibility_scope=scope,
            limit=limit,
        ),
        "visibility_scope": scope,
        "requester_session_id": requester_session_id,
    }


def api_subruns_get(
    *,
    run_id: str,
    requester_session_id: str,
    visibility_scope: str | None,
    deps: SubrunEndpointsDependencies,
) -> dict:
    # BUG-11: check existence first to avoid leaking information via 403-vs-404 side channel
    info = deps.subrun_lane.get_info(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Subrun not found")
    decision = _enforce_subrun_visibility_or_403(run_id, requester_session_id, visibility_scope, deps)
    info["visibility_decision"] = decision
    return info


def api_subruns_log(
    *,
    run_id: str,
    requester_session_id: str,
    visibility_scope: str | None,
    deps: SubrunEndpointsDependencies,
) -> dict:
    # BUG-11: check existence first to avoid leaking information via 403-vs-404 side channel
    log = deps.subrun_lane.get_log(run_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Subrun not found")
    decision = _enforce_subrun_visibility_or_403(run_id, requester_session_id, visibility_scope, deps)
    return {"runId": run_id, "events": log, "visibility_decision": decision}


async def api_subruns_kill(
    *,
    run_id: str,
    requester_session_id: str,
    visibility_scope: str | None,
    cascade: bool,
    deps: SubrunEndpointsDependencies,
) -> dict:
    # BUG-11: check existence first to avoid leaking information via 403-vs-404 side channel
    exists = deps.subrun_lane.get_info(run_id) is not None
    if not exists:
        raise HTTPException(status_code=404, detail="Subrun not running or not found")
    decision = _enforce_subrun_visibility_or_403(run_id, requester_session_id, visibility_scope, deps)
    killed = await deps.subrun_lane.kill(run_id, cascade=cascade)
    if not killed:
        raise HTTPException(status_code=404, detail="Subrun not running or not found")
    return {"runId": run_id, "killed": True, "cascade": cascade, "visibility_decision": decision}


async def api_subruns_kill_all_async(request_data: dict, deps: SubrunEndpointsDependencies) -> dict:
    request = KillAllSubrunsRequest.model_validate(request_data)
    scope = _normalize_visibility_scope(request.visibility_scope, deps)
    # BUG-12: enforce requester identity and session ownership before bulk kill
    requester = (request.requester_session_id or "").strip()
    if not requester:
        raise HTTPException(status_code=403, detail="requester_session_id is required for kill_all")
    if request.parent_session_id and request.parent_session_id != requester and scope != "all":
        raise HTTPException(
            status_code=403,
            detail="Not authorized to kill subruns from a different session; use visibility_scope='all' only if permitted",
        )
    killed_count = await deps.subrun_lane.kill_all(
        parent_session_id=request.parent_session_id,
        parent_request_id=request.parent_request_id,
        cascade=request.cascade,
    )
    return {
        "killed": killed_count,
        "parent_session_id": request.parent_session_id,
        "parent_request_id": request.parent_request_id,
        "cascade": request.cascade,
        "requester_session_id": request.requester_session_id,
        "visibility_scope": scope,
    }
