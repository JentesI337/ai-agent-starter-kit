from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.shared.idempotency.manager import IdempotencyManager
from app.transport.routers import runs as run_handlers, sessions as session_handlers


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
