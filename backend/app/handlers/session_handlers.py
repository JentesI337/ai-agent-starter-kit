from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.control_models import (
    ControlSessionsGetRequest,
    ControlSessionsHistoryRequest,
    ControlSessionsListRequest,
    ControlSessionsPatchRequest,
    ControlSessionsResetRequest,
    ControlSessionsResolveRequest,
    ControlSessionsSendRequest,
    ControlSessionsSpawnRequest,
    ControlSessionsStatusRequest,
)
from app.services.request_normalization import normalize_idempotency_key
from app.handlers.run_handlers import extract_final_message, normalize_contract_run_status
from app.handlers.tools_handlers import normalize_tool_policy_payload


@dataclass
class SessionHandlerDependencies:
    runtime_manager: Any
    state_store: Any
    session_query_service: Any
    idempotency_mgr: Any
    build_run_start_fingerprint: Callable[..., str]
    build_session_patch_fingerprint: Callable[..., str]
    build_session_reset_fingerprint: Callable[..., str]
    start_run_background: Callable[..., str]


_deps: SessionHandlerDependencies | None = None


def configure(deps: SessionHandlerDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> SessionHandlerDependencies:
    if _deps is None:
        raise RuntimeError("session_handlers is not configured")
    return _deps


def _list_sessions_minimal(*, limit: int, active_only: bool) -> dict:
    deps = _require_deps()
    runs = deps.state_store.list_runs(limit=max(limit * 5, 200))
    by_session: dict[str, dict] = {}
    for run in runs:
        session_id = str(run.get("session_id", "")).strip()
        if not session_id:
            continue
        if active_only and run.get("status") != "active":
            continue
        if session_id in by_session:
            continue
        by_session[session_id] = {
            "session_id": session_id,
            "latest_run_id": run.get("run_id"),
            "status": normalize_contract_run_status(run.get("status")),
            "runtime": run.get("runtime"),
            "model": run.get("model"),
            "updated_at": run.get("updated_at"),
            "created_at": run.get("created_at"),
        }
        if len(by_session) >= max(1, limit):
            break

    items = list(by_session.values())
    return {
        "schema": "sessions.list.v1",
        "count": len(items),
        "items": items,
    }


def _resolve_latest_session_run(*, session_id: str, limit: int = 2000) -> tuple[dict | None, int, int]:
    deps = _require_deps()
    return deps.session_query_service.resolve_latest_session_run(session_id=session_id, limit=limit)


def _resolve_session_minimal(*, session_id: str, active_only: bool) -> dict | None:
    target = (session_id or "").strip()
    if not target:
        return None

    latest, runs_count, active_runs_count = _resolve_latest_session_run(session_id=target)

    if latest is None:
        return None

    if active_only and latest.get("status") != "active":
        return None

    return {
        "schema": "sessions.resolve.v1",
        "session": {
            "session_id": target,
            "latest_run_id": latest.get("run_id"),
            "status": normalize_contract_run_status(latest.get("status")),
            "runtime": latest.get("runtime"),
            "model": latest.get("model"),
            "updated_at": latest.get("updated_at"),
            "created_at": latest.get("created_at"),
            "runs_count": runs_count,
            "active_runs_count": active_runs_count,
        },
    }


def _session_history_minimal(*, session_id: str, limit: int) -> dict:
    deps = _require_deps()
    target = (session_id or "").strip()
    runs = deps.state_store.list_runs(limit=max(limit * 5, 250))
    items: list[dict] = []

    for run in runs:
        if str(run.get("session_id", "")).strip() != target:
            continue

        items.append(
            {
                "run_id": run.get("run_id"),
                "status": normalize_contract_run_status(run.get("status")),
                "runtime": run.get("runtime"),
                "model": run.get("model"),
                "updated_at": run.get("updated_at"),
                "created_at": run.get("created_at"),
                "error": run.get("error"),
                "final": extract_final_message(run),
            }
        )

        if len(items) >= max(1, limit):
            break

    return {
        "schema": "sessions.history.v1",
        "session_id": target,
        "count": len(items),
        "items": items,
    }


def _find_idempotent_run_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="run",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different request payload.",
        replay_builder=lambda key, existing: {
            "status": "accepted",
            "runId": existing.get("run_id"),
            "sessionId": existing.get("session_id"),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_run(*, idempotency_key: str | None, fingerprint: str, run_id: str, session_id: str) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="run",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"run_id": run_id, "session_id": session_id},
    )


def _send_session_minimal(*, request: ControlSessionsSendRequest, idempotency_key_header: str | None) -> dict:
    deps = _require_deps()
    runtime_state = deps.runtime_manager.get_state()
    session_id = (request.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    normalized_tool_policy = normalize_tool_policy_payload(request.tool_policy)
    idempotency_key = normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = deps.build_run_start_fingerprint(
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_run_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return {
            "schema": "sessions.send.v1",
            **existing,
        }

    run_id = deps.start_run_background(
        agent_id=None,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
    )
    _register_idempotent_run(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        run_id=run_id,
        session_id=session_id,
    )

    return {
        "schema": "sessions.send.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }


def _spawn_session_minimal(*, request: ControlSessionsSpawnRequest, idempotency_key_header: str | None) -> dict:
    deps = _require_deps()
    runtime_state = deps.runtime_manager.get_state()
    parent_session_id = (request.parent_session_id or "").strip()
    if not parent_session_id:
        raise HTTPException(status_code=400, detail="Parent session id must not be empty")

    normalized_tool_policy = normalize_tool_policy_payload(request.tool_policy)
    idempotency_key = normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = deps.build_run_start_fingerprint(
        message=request.message,
        session_id=parent_session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_run_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return {
            "schema": "sessions.spawn.v1",
            "status": existing.get("status"),
            "runId": existing.get("runId"),
            "sessionId": existing.get("sessionId"),
            "parentSessionId": parent_session_id,
            "idempotency": existing.get("idempotency"),
        }

    child_session_id = str(uuid.uuid4())
    run_id = deps.start_run_background(
        agent_id=None,
        message=request.message,
        session_id=child_session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        meta={
            "source": "control.sessions.spawn",
            "parent_session_id": parent_session_id,
        },
    )
    _register_idempotent_run(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        run_id=run_id,
        session_id=child_session_id,
    )

    return {
        "schema": "sessions.spawn.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": child_session_id,
        "parentSessionId": parent_session_id,
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }


def _session_status_minimal(*, session_id: str) -> dict:
    target = (session_id or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    latest, runs_count, active_runs_count = _resolve_latest_session_run(session_id=target)

    if latest is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "schema": "sessions.status.v1",
        "session": {
            "session_id": target,
            "latest_run_id": latest.get("run_id"),
            "status": normalize_contract_run_status(latest.get("status")),
            "runtime": latest.get("runtime"),
            "model": latest.get("model"),
            "updated_at": latest.get("updated_at"),
            "created_at": latest.get("created_at"),
            "runs_count": runs_count,
            "active_runs_count": active_runs_count,
            "latest_final": extract_final_message(latest),
            "latest_error": latest.get("error"),
        },
    }


def _get_session_minimal(*, session_id: str) -> dict:
    payload = _session_status_minimal(session_id=session_id)
    return {
        "schema": "sessions.get.v1",
        "session": payload.get("session"),
    }


def _find_idempotent_session_patch_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="session_patch",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different session patch payload.",
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_session_patch(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="session_patch",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
    )


def _patch_session_minimal(*, request: ControlSessionsPatchRequest, idempotency_key_header: str | None) -> dict:
    deps = _require_deps()
    session_id = (request.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    patch_meta = request.meta if isinstance(request.meta, dict) else {}
    idempotency_key = normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = deps.build_session_patch_fingerprint(session_id=session_id, meta=patch_meta)
    existing = _find_idempotent_session_patch_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    latest, _, _ = _resolve_latest_session_run(session_id=session_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="Session not found")

    run_id = str(latest.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=500, detail="Session latest run is missing run_id")

    updated = deps.state_store.patch_run_meta(run_id, patch_meta)
    response = {
        "schema": "sessions.patch.v1",
        "session": {
            "session_id": session_id,
            "latest_run_id": run_id,
            "meta": updated.get("meta") or {},
            "updated_at": updated.get("updated_at"),
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_session_patch(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def _find_idempotent_session_reset_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="session_reset",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different session reset payload.",
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_session_reset(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="session_reset",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
    )


def _reset_session_minimal(*, request: ControlSessionsResetRequest, idempotency_key_header: str | None) -> dict:
    deps = _require_deps()
    session_id = (request.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    idempotency_key = normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = deps.build_session_reset_fingerprint(session_id=session_id)
    existing = _find_idempotent_session_reset_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    latest, _, _ = _resolve_latest_session_run(session_id=session_id)

    if latest is None:
        raise HTTPException(status_code=404, detail="Session not found")

    run_id = str(latest.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=500, detail="Session latest run is missing run_id")

    updated = deps.state_store.set_run_meta(run_id, {})
    response = {
        "schema": "sessions.reset.v1",
        "session": {
            "session_id": session_id,
            "latest_run_id": run_id,
            "meta": updated.get("meta") or {},
            "updated_at": updated.get("updated_at"),
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_session_reset(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def api_control_sessions_list(request_data: dict) -> dict:
    request = ControlSessionsListRequest.model_validate(request_data)
    limit = max(1, min(int(request.limit), 500))
    return _list_sessions_minimal(limit=limit, active_only=bool(request.active_only))


def api_control_sessions_resolve(request_data: dict) -> dict:
    request = ControlSessionsResolveRequest.model_validate(request_data)
    payload = _resolve_session_minimal(session_id=request.session_id, active_only=bool(request.active_only))
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return payload


def api_control_sessions_history(request_data: dict) -> dict:
    request = ControlSessionsHistoryRequest.model_validate(request_data)
    limit = max(1, min(int(request.limit), 500))
    return _session_history_minimal(session_id=request.session_id, limit=limit)


def api_control_sessions_send(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsSendRequest.model_validate(request_data)
    return _send_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def api_control_sessions_spawn(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsSpawnRequest.model_validate(request_data)
    return _spawn_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def api_control_sessions_status(request_data: dict) -> dict:
    request = ControlSessionsStatusRequest.model_validate(request_data)
    return _session_status_minimal(session_id=request.session_id)


def api_control_sessions_get(request_data: dict) -> dict:
    request = ControlSessionsGetRequest.model_validate(request_data)
    return _get_session_minimal(session_id=request.session_id)


def api_control_sessions_patch(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsPatchRequest.model_validate(request_data)
    return _patch_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def api_control_sessions_reset(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsResetRequest.model_validate(request_data)
    return _reset_session_minimal(request=request, idempotency_key_header=idempotency_key_header)
