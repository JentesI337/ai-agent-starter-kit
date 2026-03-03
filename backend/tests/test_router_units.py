from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import (
    build_agents_router,
    build_control_runs_router,
    build_runtime_debug_router,
    build_subruns_router,
)


def test_agents_router_wires_basic_routes() -> None:
    app = FastAPI()
    app.include_router(
        build_agents_router(
            agents_list_handler=lambda: [{"id": "head-agent"}],
            presets_list_handler=lambda: [{"id": "default"}],
            custom_agents_list_handler=lambda: [{"id": "custom-a"}],
            custom_agents_create_handler=lambda payload: {"created": payload.get("name")},
            custom_agents_delete_handler=lambda agent_id: {"deleted": agent_id},
            monitoring_schema_handler=lambda: {"eventTypes": ["status"]},
        )
    )

    client = TestClient(app)

    assert client.get("/api/agents").json() == [{"id": "head-agent"}]
    assert client.get("/api/presets").json() == [{"id": "default"}]
    assert client.get("/api/custom-agents").json() == [{"id": "custom-a"}]
    assert client.post("/api/custom-agents", json={"name": "x"}).json() == {"created": "x"}
    assert client.delete("/api/custom-agents/custom-a").json() == {"deleted": "custom-a"}
    assert client.get("/api/monitoring/schema").json() == {"eventTypes": ["status"]}


def test_runtime_debug_router_supports_async_and_sync_handlers() -> None:
    app = FastAPI()

    async def runtime_status():
        return {"runtime": "local"}

    app.include_router(
        build_runtime_debug_router(
            runtime_status_handler=runtime_status,
            resolved_prompts_handler=lambda: {"prompts": {"head": "x"}},
            ping_handler=lambda: {"ok": True},
        )
    )

    client = TestClient(app)

    assert client.get("/api/runtime/status").json() == {"runtime": "local"}
    assert client.get("/api/debug/prompts/resolved").json() == {"prompts": {"head": "x"}}
    assert client.get("/api/test/ping").json() == {"ok": True}


def test_subruns_router_forwards_query_path_and_body() -> None:
    app = FastAPI()

    async def kill_handler(run_id: str, requester_session_id: str, visibility_scope: str | None, cascade: bool):
        return {
            "run_id": run_id,
            "requester_session_id": requester_session_id,
            "visibility_scope": visibility_scope,
            "cascade": cascade,
        }

    app.include_router(
        build_subruns_router(
            subruns_list_handler=lambda p_sid, p_rid, r_sid, scope, limit: {
                "parent_session_id": p_sid,
                "parent_request_id": p_rid,
                "requester_session_id": r_sid,
                "scope": scope,
                "limit": limit,
            },
            subrun_get_handler=lambda run_id, requester_session_id, visibility_scope: {
                "run_id": run_id,
                "requester_session_id": requester_session_id,
                "visibility_scope": visibility_scope,
            },
            subrun_log_handler=lambda run_id, requester_session_id, visibility_scope: {
                "run_id": run_id,
                "requester_session_id": requester_session_id,
                "visibility_scope": visibility_scope,
                "events": [],
            },
            subrun_kill_handler=kill_handler,
            subrun_kill_all_handler=lambda payload: {"killed": payload.get("cascade", False)},
        )
    )

    client = TestClient(app)

    list_payload = client.get(
        "/api/subruns",
        params={
            "parent_session_id": "s1",
            "parent_request_id": "r1",
            "requester_session_id": "u1",
            "visibility_scope": "tree",
            "limit": 7,
        },
    ).json()
    assert list_payload["parent_session_id"] == "s1"
    assert list_payload["parent_request_id"] == "r1"
    assert list_payload["requester_session_id"] == "u1"
    assert list_payload["scope"] == "tree"
    assert list_payload["limit"] == 7

    get_payload = client.get("/api/subruns/run-1", params={"requester_session_id": "u1", "visibility_scope": "all"}).json()
    assert get_payload["run_id"] == "run-1"

    log_payload = client.get("/api/subruns/run-1/log", params={"requester_session_id": "u1"}).json()
    assert log_payload["events"] == []

    kill_payload = client.post(
        "/api/subruns/run-1/kill",
        params={"requester_session_id": "u1", "visibility_scope": "self", "cascade": False},
    ).json()
    assert kill_payload["cascade"] is False

    kill_all_payload = client.post("/api/subruns/kill-all", json={"cascade": True}).json()
    assert kill_all_payload == {"killed": True}


def test_control_runs_router_forwards_idempotency_key_header() -> None:
    captured: dict[str, str | None] = {}

    def run_start_handler(payload: dict, idempotency_key: str | None) -> dict:
        captured["key"] = idempotency_key
        captured["message"] = str(payload.get("message"))
        return {"ok": True}

    app = FastAPI()
    app.include_router(
        build_control_runs_router(
            run_start_handler=run_start_handler,
            run_wait_handler=lambda payload: {"wait": payload.get("runId")},
            agent_run_handler=lambda payload, key: {"run": True, "key": key},
            agent_wait_handler=lambda payload: {"wait": True},
            runs_get_handler=lambda payload: {"run": payload.get("runId")},
            runs_list_handler=lambda payload: {"limit": payload.get("limit")},
            runs_events_handler=lambda payload: {"events": []},
            runs_audit_handler=lambda payload: {"audit": []},
        )
    )

    client = TestClient(app)
    response = client.post(
        "/api/control/run.start",
        json={"message": "hello"},
        headers={"Idempotency-Key": "abc-123"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["key"] == "abc-123"
    assert captured["message"] == "hello"
