from __future__ import annotations

from types import SimpleNamespace

from app.orchestration.run_state_machine import is_allowed_run_state_transition, resolve_run_state_from_stage
from app.transport.routers import runs as run_handlers


class _StateStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}

    def init_run(self, **kwargs) -> None:
        run_id = str(kwargs["run_id"])
        self.runs[run_id] = {
            **kwargs,
            "events": [],
            "meta": dict(kwargs.get("meta") or {}),
        }

    def append_event(self, *, run_id: str, event: dict) -> None:
        self.runs.setdefault(run_id, {"events": [], "meta": {}}).setdefault("events", []).append(event)

    def get_run(self, run_id: str):
        return self.runs.get(run_id)

    def patch_run_meta(self, run_id: str, patch: dict | None) -> None:
        run_state = self.runs.setdefault(run_id, {"events": [], "meta": {}})
        run_state.setdefault("meta", {}).update(dict(patch or {}))

    def set_task_status(self, run_id: str, task_id: str, label: str, status: str) -> None:
        run_state = self.runs.setdefault(run_id, {"events": [], "meta": {}})
        tasks = run_state.setdefault("tasks", {})
        tasks[str(task_id)] = {"label": label, "status": status}

    def mark_failed(self, run_id: str, error: str) -> None:
        run_state = self.runs.setdefault(run_id, {"events": [], "meta": {}})
        run_state["status"] = "failed"
        run_state["error"] = error


def _configure_with_store(store: _StateStore) -> None:
    run_handlers.configure(
        run_handlers.RunHandlerDependencies(
            logger=SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None),
            settings=SimpleNamespace(run_wait_default_timeout_ms=100, run_wait_poll_interval_ms=10),
            runtime_manager=SimpleNamespace(get_state=lambda: SimpleNamespace(runtime="api", model="m", base_url="u")),
            state_store=store,
            agent=SimpleNamespace(name="head-agent"),
            active_run_tasks={},
            idempotency_mgr=SimpleNamespace(),
            resolve_agent=lambda agent_id: (agent_id or "head-agent", SimpleNamespace(name="head-agent"), object()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            build_run_start_fingerprint=lambda **kw: "fp",
            extract_also_allow=lambda policy: None,
        )
    )


def _set_hard_fail(enabled: bool) -> None:
    run_handlers.settings.run_state_violation_hard_fail_enabled = enabled


def test_run_state_machine_stage_resolution_and_transition_rules() -> None:
    assert resolve_run_state_from_stage("request_received") == "received"
    assert resolve_run_state_from_stage("queued") == "queued"
    assert resolve_run_state_from_stage("planning_started") == "planning"
    assert resolve_run_state_from_stage("tool_completed") == "tool_loop"
    assert resolve_run_state_from_stage("streaming_started") == "synthesis"
    assert resolve_run_state_from_stage("request_completed") == "completed"

    assert is_allowed_run_state_transition(None, "received")
    assert is_allowed_run_state_transition("planning", "tool_loop")
    assert not is_allowed_run_state_transition("tool_loop", "received")


def test_state_append_event_safe_emits_stage_and_run_state_events() -> None:
    store = _StateStore()
    _configure_with_store(store)
    _set_hard_fail(False)
    run_id = "run-1"
    store.init_run(
        run_id=run_id,
        session_id="s1",
        request_id=run_id,
        user_message="hi",
        runtime="api",
        model="m",
        meta={},
    )

    run_handlers.state_append_event_safe(
        run_id=run_id,
        event={"type": "lifecycle", "stage": "request_received", "session_id": "s1", "ts": "2026-01-01T00:00:00Z"},
    )
    run_handlers.state_append_event_safe(
        run_id=run_id,
        event={"type": "lifecycle", "stage": "planning_started", "session_id": "s1", "ts": "2026-01-01T00:00:01Z"},
    )

    events = store.runs[run_id]["events"]
    assert any(evt.get("type") == "stage_event" and evt.get("stage") == "request_received" for evt in events)
    assert any(evt.get("type") == "run_state_event" and evt.get("to") == "received" for evt in events)
    assert any(evt.get("type") == "run_state_event" and evt.get("to") == "planning" for evt in events)
    assert store.runs[run_id]["meta"].get("run_state") == "planning"


def test_state_append_event_safe_emits_run_state_violation_on_backward_transition() -> None:
    store = _StateStore()
    _configure_with_store(store)
    _set_hard_fail(False)
    run_id = "run-2"
    store.init_run(
        run_id=run_id,
        session_id="s1",
        request_id=run_id,
        user_message="hi",
        runtime="api",
        model="m",
        meta={"run_state": "tool_loop"},
    )

    run_handlers.state_append_event_safe(
        run_id=run_id,
        event={"type": "lifecycle", "stage": "request_received", "session_id": "s1", "ts": "2026-01-01T00:00:00Z"},
    )

    events = store.runs[run_id]["events"]
    assert any(evt.get("type") == "run_state_violation" for evt in events)


def test_state_append_event_safe_hard_fail_marks_run_failed() -> None:
    store = _StateStore()
    _configure_with_store(store)
    _set_hard_fail(True)
    run_id = "run-3"
    store.init_run(
        run_id=run_id,
        session_id="s1",
        request_id=run_id,
        user_message="hi",
        runtime="api",
        model="m",
        meta={"run_state": "tool_loop"},
    )

    run_handlers.state_append_event_safe(
        run_id=run_id,
        event={"type": "lifecycle", "stage": "request_received", "session_id": "s1", "ts": "2026-01-01T00:00:00Z"},
    )

    assert store.runs[run_id].get("status") == "failed"
    assert "run_state_violation" in str(store.runs[run_id].get("error") or "")
    assert store.runs[run_id].get("meta", {}).get("run_state_hard_failed") is True


def test_background_collector_stops_after_hard_fail_violation() -> None:
    store = _StateStore()

    async def _resolve_api_request_model(model: str) -> str:
        return model

    class _Agent:
        name = "head-agent"

        def configure_runtime(self, base_url: str, model: str) -> None:
            _ = (base_url, model)

    class _Orchestrator:
        async def run_user_message(self, *, user_message: str, send_event, request_context) -> str:
            _ = (user_message, request_context)
            await send_event(
                {
                    "type": "lifecycle",
                    "stage": "request_received",
                    "session_id": "s1",
                    "request_id": "run-hard-fail",
                }
            )
            await send_event(
                {
                    "type": "lifecycle",
                    "stage": "planning_started",
                    "session_id": "s1",
                    "request_id": "run-hard-fail",
                }
            )
            return "done"

    run_handlers.configure(
        run_handlers.RunHandlerDependencies(
            logger=SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None),
            settings=SimpleNamespace(run_wait_default_timeout_ms=100, run_wait_poll_interval_ms=10),
            runtime_manager=SimpleNamespace(
                get_state=lambda: SimpleNamespace(runtime="api", model="m", base_url="u"),
                resolve_api_request_model=_resolve_api_request_model,
            ),
            state_store=store,
            agent=SimpleNamespace(name="head-agent"),
            active_run_tasks={},
            idempotency_mgr=SimpleNamespace(),
            resolve_agent=lambda agent_id: (agent_id or "head-agent", _Agent(), _Orchestrator()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            build_run_start_fingerprint=lambda **kw: "fp",
            extract_also_allow=lambda policy: None,
        )
    )

    run_handlers.settings.run_state_violation_hard_fail_enabled = True
    run_id = "run-hard-fail"
    store.init_run(
        run_id=run_id,
        session_id="s1",
        request_id=run_id,
        user_message="hi",
        runtime="api",
        model="m",
        meta={"run_state": "tool_loop"},
    )

    import asyncio

    asyncio.run(
        run_handlers._run_background_message(
            agent_id="head-agent",
            run_id=run_id,
            session_id="s1",
            message="hello",
            model=None,
            preset=None,
            queue_mode="wait",
            prompt_mode="full",
            tool_policy=None,
        )
    )

    lifecycle_stages = [
        evt.get("stage")
        for evt in store.runs[run_id].get("events", [])
        if isinstance(evt, dict) and evt.get("type") == "lifecycle"
    ]
    assert "request_received" in lifecycle_stages
    assert "planning_started" not in lifecycle_stages
    assert store.runs[run_id].get("status") == "failed"


def test_background_run_directive_parse_failure_marks_failed_and_cleans_active_task() -> None:
    store = _StateStore()
    active_tasks: dict[str, object] = {}
    run_id = "run-directive-failure"

    run_handlers.configure(
        run_handlers.RunHandlerDependencies(
            logger=SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None),
            settings=SimpleNamespace(run_wait_default_timeout_ms=100, run_wait_poll_interval_ms=10),
            runtime_manager=SimpleNamespace(get_state=lambda: SimpleNamespace(runtime="api", model="m", base_url="u")),
            state_store=store,
            agent=SimpleNamespace(name="head-agent"),
            active_run_tasks=active_tasks,
            idempotency_mgr=SimpleNamespace(),
            resolve_agent=lambda agent_id: (agent_id or "head-agent", SimpleNamespace(name="head-agent"), object()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            build_run_start_fingerprint=lambda **kw: "fp",
            extract_also_allow=lambda policy: None,
        )
    )

    store.init_run(
        run_id=run_id,
        session_id="s1",
        request_id=run_id,
        user_message="/model gpt-oss",
        runtime="api",
        model="m",
        meta={},
    )
    active_tasks[run_id] = object()

    import asyncio

    asyncio.run(
        run_handlers._run_background_message(
            agent_id="head-agent",
            run_id=run_id,
            session_id="s1",
            message="/model gpt-oss",
            model=None,
            preset=None,
            queue_mode="wait",
            prompt_mode="full",
            tool_policy=None,
        )
    )

    assert store.runs[run_id].get("status") == "failed"
    assert "Directive-only message" in str(store.runs[run_id].get("error") or "")
    assert run_id not in active_tasks

    lifecycle_stages = [
        evt.get("stage")
        for evt in store.runs[run_id].get("events", [])
        if isinstance(evt, dict) and evt.get("type") == "lifecycle"
    ]
    assert "processing_failed" in lifecycle_stages
