from __future__ import annotations

import asyncio
import tempfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.transport.routers import runs as run_handlers, sessions as session_handlers
from app.workflows import handlers as workflow_handlers
from app.workflows.store import SqliteWorkflowStore, SqliteWorkflowAuditStore
from app.shared.idempotency.manager import IdempotencyManager


class _RuntimeManager:
    def get_state(self):
        return SimpleNamespace(runtime="api", model="gpt-test", base_url="http://localhost")

    async def resolve_api_request_model(self, model: str) -> str:
        return model

    async def ensure_model_ready(self, send_event, session_id: str, selected_model: str) -> str:
        _ = (send_event, session_id)
        return selected_model


class _RunStateStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}

    def init_run(self, **kwargs) -> None:
        run_id = str(kwargs["run_id"])
        self.runs[run_id] = {**kwargs, "events": []}

    def set_task_status(self, **kwargs) -> None:
        _ = kwargs

    def append_event(self, *, run_id: str, event: dict) -> None:
        self.runs.setdefault(run_id, {"events": []}).setdefault("events", []).append(event)


def _make_workflow_deps(tmp_path, **overrides):
    """Create WorkflowDependencies with sensible defaults for tests."""
    db_path = tmp_path / "workflow_store.db"
    wf_store = SqliteWorkflowStore(db_path=db_path)
    defaults = dict(
        settings=SimpleNamespace(),
        workflow_store=wf_store,
        audit_store=None,
        idempotency_mgr=IdempotencyManager(ttl_seconds=60, max_entries=100),
        run_agent=_noop_run_agent,
        build_workflow_create_fingerprint=lambda **kw: f"wf-create:{kw.get('name')}:{kw.get('base_agent_id')}:{kw.get('operation')}",
        build_workflow_execute_fingerprint=lambda **kw: f"wf-exec:{kw.get('workflow_id')}",
        build_workflow_delete_fingerprint=lambda **kw: f"wf-del:{kw.get('workflow_id')}",
    )
    defaults.update(overrides)
    return workflow_handlers.WorkflowDependencies(**defaults)


async def _noop_run_agent(agent_id: str, message: str, session_id: str) -> str:
    return "ok"


def test_run_handler_contract_and_idempotency_replay(monkeypatch) -> None:
    async def _noop_background(**kwargs) -> None:
        _ = kwargs

    monkeypatch.setattr(run_handlers, "_run_background_message", _noop_background)

    run_handlers.configure(
        run_handlers.RunHandlerDependencies(
            logger=SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None),
            settings=SimpleNamespace(run_wait_default_timeout_ms=100, run_wait_poll_interval_ms=10),
            runtime_manager=_RuntimeManager(),
            state_store=_RunStateStore(),
            agent=SimpleNamespace(name="head-agent"),
            active_run_tasks={},
            idempotency_mgr=IdempotencyManager(ttl_seconds=60, max_entries=100),
            resolve_agent=lambda agent_id: (agent_id or "head-agent", SimpleNamespace(name="head-agent"), object()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            build_run_start_fingerprint=lambda **kw: f"fp:{kw.get('message')}:{kw.get('session_id')}:{kw.get('runtime')}",
            extract_also_allow=lambda policy: None,
        )
    )

    first = asyncio.run(
        run_handlers.api_control_run_start(
            request_data={"message": "hello", "idempotency_key": "idem-run-1"},
            idempotency_key_header=None,
        )
    )
    second = asyncio.run(
        run_handlers.api_control_run_start(
            request_data={"message": "hello", "idempotency_key": "idem-run-1"},
            idempotency_key_header=None,
        )
    )

    assert first["schema"] == "run.start.v1"
    assert first["status"] == "accepted"
    assert first["idempotency"]["reused"] is False
    assert second["idempotency"]["reused"] is True
    assert second["runId"] == first["runId"]


def test_session_handler_contract_and_idempotency_replay() -> None:
    session_handlers.configure(
        session_handlers.SessionHandlerDependencies(
            runtime_manager=_RuntimeManager(),
            state_store=SimpleNamespace(),
            session_query_service=SimpleNamespace(resolve_latest_session_run=lambda **_: (None, 0, 0)),
            idempotency_mgr=IdempotencyManager(ttl_seconds=60, max_entries=100),
            build_run_start_fingerprint=lambda **kw: f"fp:{kw.get('message')}:{kw.get('session_id')}:{kw.get('runtime')}",
            build_session_patch_fingerprint=lambda **kw: f"patch:{kw}",
            build_session_reset_fingerprint=lambda **kw: f"reset:{kw}",
            start_run_background=lambda **kwargs: "run-session-1",
        )
    )

    first = session_handlers.api_control_sessions_send(
        request_data={"session_id": "sess-1", "message": "hello", "idempotency_key": "idem-sess-1"},
        idempotency_key_header=None,
    )
    second = session_handlers.api_control_sessions_send(
        request_data={"session_id": "sess-1", "message": "hello", "idempotency_key": "idem-sess-1"},
        idempotency_key_header=None,
    )

    assert first["schema"] == "sessions.send.v1"
    assert first["status"] == "accepted"
    assert first["idempotency"]["reused"] is False
    assert second["idempotency"]["reused"] is True
    assert second["runId"] == first["runId"]


def test_workflow_handler_contract_and_idempotency_replay(tmp_path) -> None:
    workflow_handlers.configure(_make_workflow_deps(tmp_path))

    first = workflow_handlers.api_control_workflows_create(
        request_data={
            "name": "Demo Workflow",
            "description": "desc",
            "base_agent_id": "head-agent",
            "steps": ["step one"],
            "idempotency_key": "idem-wf-1",
        },
        idempotency_key_header=None,
    )
    second = workflow_handlers.api_control_workflows_create(
        request_data={
            "name": "Demo Workflow",
            "description": "desc",
            "base_agent_id": "head-agent",
            "steps": ["step one"],
            "idempotency_key": "idem-wf-1",
        },
        idempotency_key_header=None,
    )

    assert first["schema"] == "workflows.create.v1"
    assert first["status"] == "created"
    assert first["idempotency"]["reused"] is False
    assert second["idempotency"]["reused"] is True
    assert second["workflow"]["id"] == first["workflow"]["id"]


def test_workflow_create_and_get_roundtrip(tmp_path) -> None:
    workflow_handlers.configure(_make_workflow_deps(tmp_path))

    created = workflow_handlers.api_control_workflows_create(
        request_data={
            "name": "Vision Workflow",
            "description": "Use vision in workflow run",
            "base_agent_id": "head-agent",
            "steps": ["analyze the image"],
            "idempotency_key": "idem-wf-vision-1",
        },
        idempotency_key_header=None,
    )
    assert created["schema"] == "workflows.create.v1"
    workflow_id = created["workflow"]["id"]

    got = workflow_handlers.api_control_workflows_get(
        request_data={
            "workflow_id": workflow_id,
        }
    )
    assert got["schema"] == "workflows.get.v1"
    assert got["workflow"]["name"] == "Vision Workflow"
    assert got["workflow"]["description"] == "Use vision in workflow run"


def test_workflow_execute_returns_accepted(tmp_path) -> None:
    workflow_handlers.configure(_make_workflow_deps(tmp_path))

    created = workflow_handlers.api_control_workflows_create(
        request_data={
            "name": "Exec Workflow",
            "description": "desc",
            "base_agent_id": "head-agent",
            "steps": ["do something"],
            "idempotency_key": "idem-wf-exec-create-1",
        },
        idempotency_key_header=None,
    )
    workflow_id = created["workflow"]["id"]

    executed = asyncio.run(
        workflow_handlers.api_control_workflows_execute(
            request_data={
                "workflow_id": workflow_id,
                "message": "analyze screenshot",
                "idempotency_key": "idem-wf-exec-1",
            },
            idempotency_key_header=None,
        )
    )

    assert executed["status"] == "accepted"
    assert "runId" in executed


def test_run_handler_idempotency_conflict_when_queue_mode_differs() -> None:
    captured_queue_modes: list[str | None] = []

    def _build_run_start_fingerprint(**kw) -> str:
        captured_queue_modes.append(kw.get("queue_mode"))
        return f"fp:{kw.get('message')}:{kw.get('session_id')}:{kw.get('runtime')}:{kw.get('queue_mode')}"

    run_handlers.configure(
        run_handlers.RunHandlerDependencies(
            logger=SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None),
            settings=SimpleNamespace(run_wait_default_timeout_ms=100, run_wait_poll_interval_ms=10),
            runtime_manager=_RuntimeManager(),
            state_store=_RunStateStore(),
            agent=SimpleNamespace(name="head-agent"),
            active_run_tasks={},
            idempotency_mgr=IdempotencyManager(ttl_seconds=60, max_entries=100),
            resolve_agent=lambda agent_id: (agent_id or "head-agent", SimpleNamespace(name="head-agent"), object()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            build_run_start_fingerprint=_build_run_start_fingerprint,
            extract_also_allow=lambda policy: None,
        )
    )

    first = asyncio.run(
        run_handlers.api_control_run_start(
            request_data={
                "message": "hello",
                "queue_mode": "wait",
                "idempotency_key": "idem-run-queue-mode",
            },
            idempotency_key_header=None,
        )
    )

    assert first["status"] == "accepted"
    assert captured_queue_modes == ["wait"]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            run_handlers.api_control_run_start(
                request_data={
                    "message": "hello",
                    "queue_mode": "steer",
                    "idempotency_key": "idem-run-queue-mode",
                },
                idempotency_key_header=None,
            )
        )

    assert exc.value.status_code == 409
    assert captured_queue_modes == ["wait", "steer"]


def test_workflow_execute_idempotency_conflict_when_queue_mode_differs(tmp_path) -> None:
    captured_queue_modes: list[str | None] = []

    def _build_workflow_execute_fingerprint(**kw) -> str:
        captured_queue_modes.append(kw.get("queue_mode"))
        return f"wf-exec:{kw.get('workflow_id')}:{kw.get('queue_mode')}"

    workflow_handlers.configure(_make_workflow_deps(
        tmp_path,
        build_workflow_execute_fingerprint=_build_workflow_execute_fingerprint,
    ))

    created = workflow_handlers.api_control_workflows_create(
        request_data={
            "name": "QueueMode Workflow",
            "description": "desc",
            "base_agent_id": "head-agent",
            "steps": ["step one"],
            "idempotency_key": "idem-wf-create-queue-mode",
        },
        idempotency_key_header=None,
    )
    workflow_id = created["workflow"]["id"]

    first = asyncio.run(
        workflow_handlers.api_control_workflows_execute(
            request_data={
                "workflow_id": workflow_id,
                "message": "run workflow",
                "queue_mode": "wait",
                "idempotency_key": "idem-wf-exec-queue-mode",
            },
            idempotency_key_header=None,
        )
    )

    assert first["status"] == "accepted"
    assert captured_queue_modes == ["wait"]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            workflow_handlers.api_control_workflows_execute(
                request_data={
                    "workflow_id": workflow_id,
                    "message": "run workflow",
                    "queue_mode": "follow_up",
                    "idempotency_key": "idem-wf-exec-queue-mode",
                },
                idempotency_key_header=None,
            )
        )

    assert exc.value.status_code == 409
    assert captured_queue_modes == ["wait", "follow_up"]


def test_run_start_wait_reports_error_for_directive_only_background_message() -> None:
    class _StateStoreWithStatus(_RunStateStore):
        def mark_failed(self, *, run_id: str, error: str) -> None:
            run = self.runs.setdefault(run_id, {"events": []})
            run["status"] = "failed"
            run["error"] = error

        def mark_completed(self, *, run_id: str) -> None:
            run = self.runs.setdefault(run_id, {"events": []})
            run["status"] = "completed"

        def get_run(self, run_id: str):
            return self.runs.get(run_id)

    store = _StateStoreWithStatus()

    run_handlers.configure(
        run_handlers.RunHandlerDependencies(
            logger=SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None),
            settings=SimpleNamespace(run_wait_default_timeout_ms=200, run_wait_poll_interval_ms=10),
            runtime_manager=_RuntimeManager(),
            state_store=store,
            agent=SimpleNamespace(name="head-agent"),
            active_run_tasks={},
            idempotency_mgr=IdempotencyManager(ttl_seconds=60, max_entries=100),
            resolve_agent=lambda agent_id: (agent_id or "head-agent", SimpleNamespace(name="head-agent"), object()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            build_run_start_fingerprint=lambda **kw: f"fp:{kw.get('message')}:{kw.get('session_id')}:{kw.get('runtime')}",
            extract_also_allow=lambda policy: None,
        )
    )

    async def _run_flow() -> tuple[dict, dict]:
        start_payload = await run_handlers.api_control_run_start(
            request_data={"message": "/model gpt-oss"},
            idempotency_key_header=None,
        )
        wait_payload = await run_handlers.api_control_run_wait(
            request_data={
                "run_id": start_payload["runId"],
                "timeout_ms": 200,
                "poll_interval_ms": 10,
            }
        )
        return start_payload, wait_payload

    start_payload, wait_payload = asyncio.run(_run_flow())

    assert start_payload["status"] == "accepted"
    assert wait_payload["status"] == "error"
    assert wait_payload["runStatus"] == "error"
    assert "Directive-only message" in str(wait_payload.get("error") or "")
