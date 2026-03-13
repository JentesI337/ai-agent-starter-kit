from __future__ import annotations

import asyncio
import json

import pytest

from app.errors import GuardrailViolation
from app.contracts.request_context import RequestContext
from app.orchestration.subrun_lane import SubrunLane
from app.state import StateStore


class _FakeOrchestratorApi:
    def __init__(self, *, delay_seconds: float = 0.0):
        self.delay_seconds = delay_seconds

    async def run_user_message(self, *, user_message: str, send_event, request_context: RequestContext) -> str:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        await send_event(
            {
                "type": "lifecycle",
                "stage": "run_started",
                "request_id": request_context.request_id,
                "session_id": request_context.session_id,
                "details": {},
            }
        )
        await send_event(
            {
                "type": "final",
                "message": f"done:{user_message}",
                "request_id": request_context.request_id,
                "session_id": request_context.session_id,
            }
        )
        return f"done:{user_message}"


def test_subrun_lane_completes_and_announces(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=500,
        announce_retry_max_delay_ms=10_000,
        announce_retry_jitter=True,
    )

    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def run_case() -> dict | None:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="build feature",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy={"allow": ["read_file"]},
            send_event=send_event,
        )
        return await lane.wait_for_completion(run_id, timeout=5)

    status = asyncio.run(run_case())

    assert status is not None
    assert status["status"] == "completed"
    assert any(event.get("type") == "subrun_status" and event.get("status") == "accepted" for event in events)
    assert any(event.get("type") == "subrun_status" and event.get("status") == "running" for event in events)
    assert any(event.get("type") == "subrun_status" and event.get("status") == "completed" for event in events)
    completed_announce = next(
        event for event in events if event.get("type") == "subrun_announce" and event.get("status") == "completed"
    )
    assert completed_announce["handover"]["terminal_reason"] == "subrun-complete"
    assert completed_announce["handover"]["confidence"] > 0.5
    assert completed_announce["handover"]["result"] == "done:build feature"


def test_subrun_lane_times_out_and_announces(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(delay_seconds=1.2),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=500,
        announce_retry_max_delay_ms=10_000,
        announce_retry_jitter=True,
    )

    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def run_case() -> dict | None:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="slow task",
            runtime="local",
            model="llama",
            timeout_seconds=1,
            tool_policy=None,
            send_event=send_event,
        )
        return await lane.wait_for_completion(run_id, timeout=5)

    status = asyncio.run(run_case())

    assert status is not None
    assert status["status"] == "timed_out"
    timed_out_announce = next(
        event for event in events if event.get("type") == "subrun_announce" and event.get("status") == "timed_out"
    )
    assert timed_out_announce["handover"]["terminal_reason"] == "subrun-timeout"
    assert timed_out_announce["handover"]["result"] is None


def test_subrun_lane_get_handover_contract_pending_and_terminal(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(delay_seconds=0.05),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> tuple[dict, dict | None]:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="contract",
            runtime="local",
            model="llama",
            timeout_seconds=2,
            tool_policy=None,
            send_event=send_event,
        )
        pending = lane.get_handover_contract(run_id)
        await lane.wait_for_completion(run_id, timeout=5)
        terminal = lane.get_handover_contract(run_id)
        return pending or {}, terminal

    pending_contract, terminal_contract = asyncio.run(run_case())

    assert pending_contract["terminal_reason"] in {"subrun-accepted", "subrun-running"}
    assert pending_contract["result"] is None
    assert terminal_contract is not None
    assert terminal_contract["terminal_reason"] == "subrun-complete"
    assert terminal_contract["result"] == "done:contract"


def test_subrun_lane_invokes_completion_callback(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=3,
        announce_retry_base_delay_ms=50,
        announce_retry_max_delay_ms=200,
        announce_retry_jitter=False,
    )

    callback_payloads: list[dict] = []

    async def completion_callback(**payload) -> None:
        callback_payloads.append(payload)

    lane.set_completion_callback(completion_callback)

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> None:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="callback-check",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=send_event,
        )
        await lane.wait_for_completion(run_id, timeout=5)

    asyncio.run(run_case())

    assert len(callback_payloads) == 1
    payload = callback_payloads[0]
    assert payload["parent_session_id"] == "sess-parent"
    assert payload["terminal_reason"] == "subrun-complete"
    assert payload["child_agent_id"] == "head-agent"


def test_subrun_lane_rejects_depth_overflow(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=2,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=500,
        announce_retry_max_delay_ms=10_000,
        announce_retry_jitter=True,
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> None:
        level1 = await lane.spawn(
            parent_request_id="root-request",
            parent_session_id="sess-parent",
            user_message="l1",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=send_event,
        )
        level2 = await lane.spawn(
            parent_request_id=level1,
            parent_session_id="sess-parent",
            user_message="l2",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=send_event,
        )
        with pytest.raises(GuardrailViolation):
            await lane.spawn(
                parent_request_id=level2,
                parent_session_id="sess-parent",
                user_message="l3",
                runtime="local",
                model="llama",
                timeout_seconds=5,
                tool_policy=None,
                send_event=send_event,
            )

    asyncio.run(run_case())


def test_subrun_lane_rejects_child_limit(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=2,
        max_spawn_depth=3,
        max_children_per_parent=1,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=500,
        announce_retry_max_delay_ms=10_000,
        announce_retry_jitter=True,
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> None:
        await lane.spawn(
            parent_request_id="root-request",
            parent_session_id="sess-parent",
            user_message="first",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=send_event,
        )
        with pytest.raises(GuardrailViolation):
            await lane.spawn(
                parent_request_id="root-request",
                parent_session_id="sess-parent",
                user_message="second",
                runtime="local",
                model="llama",
                timeout_seconds=5,
                tool_policy=None,
                send_event=send_event,
            )

    asyncio.run(run_case())


def test_subrun_lane_rejects_leaf_spawn_when_guard_enabled(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=2,
        max_spawn_depth=3,
        max_children_per_parent=5,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=500,
        announce_retry_max_delay_ms=10_000,
        announce_retry_jitter=True,
        leaf_spawn_depth_guard_enabled=True,
        orchestrator_agent_ids=["head-agent"],
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> None:
        with pytest.raises(GuardrailViolation, match="Subrun depth policy blocked request"):
            await lane.spawn(
                parent_request_id="root-request",
                parent_session_id="sess-parent",
                user_message="leaf spawn",
                runtime="local",
                model="llama",
                timeout_seconds=5,
                tool_policy=None,
                send_event=send_event,
                agent_id="coder-agent",
            )

    asyncio.run(run_case())


def test_subrun_lane_kill_cascade_cancels_descendants(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(delay_seconds=2.0),
        state_store=store,
        max_concurrent=2,
        max_spawn_depth=3,
        max_children_per_parent=5,
        announce_retry_max_attempts=5,
        announce_retry_base_delay_ms=500,
        announce_retry_max_delay_ms=10_000,
        announce_retry_jitter=True,
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> tuple[str, str]:
        parent_run_id = await lane.spawn(
            parent_request_id="root-request",
            parent_session_id="sess-parent",
            user_message="parent",
            runtime="local",
            model="llama",
            timeout_seconds=10,
            tool_policy=None,
            send_event=send_event,
        )
        child_run_id = await lane.spawn(
            parent_request_id=parent_run_id,
            parent_session_id="sess-parent",
            user_message="child",
            runtime="local",
            model="llama",
            timeout_seconds=10,
            tool_policy=None,
            send_event=send_event,
        )
        await asyncio.sleep(0.1)
        killed = await lane.kill(parent_run_id, cascade=True)
        assert killed is True
        await asyncio.sleep(0.1)
        return parent_run_id, child_run_id

    parent_run_id, child_run_id = asyncio.run(run_case())

    assert lane.get_status(parent_run_id) is not None
    assert lane.get_status(child_run_id) is not None
    assert lane.get_status(parent_run_id)["status"] == "cancelled"
    assert lane.get_status(child_run_id)["status"] == "cancelled"


def test_subrun_lane_announce_retries_and_marks_sent(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=3,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )

    calls = {"announce": 0}

    async def flaky_send_event(payload: dict) -> None:
        if payload.get("type") == "subrun_announce":
            calls["announce"] += 1
            if calls["announce"] == 1:
                raise RuntimeError("transient announce send failure")

    async def run_case() -> str:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="retry announce",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=flaky_send_event,
        )
        await lane.wait_for_completion(run_id, timeout=5)
        return run_id

    run_id = asyncio.run(run_case())

    info = lane.get_info(run_id)
    assert info is not None
    delivery = info.get("announce_delivery") or {}
    assert delivery.get("status") == "announced"
    assert delivery.get("legacy_status") == "sent"
    assert delivery.get("attempt") == 2
    assert calls["announce"] == 2

    log = lane.get_log(run_id) or []
    announce_delivery_events = [event for event in log if event.get("type") == "announce_delivery"]
    assert any(
        event.get("status") == "announce_retrying" and event.get("legacy_status") == "retrying"
        for event in announce_delivery_events
    )
    assert any(
        event.get("status") == "announced" and event.get("legacy_status") == "sent"
        for event in announce_delivery_events
    )


def test_subrun_lane_restores_registry_from_disk(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=2,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> str:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="persist me",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=send_event,
        )
        await lane.wait_for_completion(run_id, timeout=5)
        return run_id

    run_id = asyncio.run(run_case())

    restored_lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=StateStore(persist_dir=str(tmp_path / "state")),
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=2,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )

    restored_info = restored_lane.get_info(run_id)
    assert restored_info is not None
    assert restored_info.get("status") == "completed"
    assert restored_info.get("parent_session_id") == "sess-parent"


def test_subrun_lane_restore_reconciles_orphaned_running_run(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    run_id = "orphan-run"
    store.init_run(
        run_id=run_id,
        session_id="sess-parent-subrun-orphan",
        request_id=run_id,
        user_message="recover me",
        runtime="local",
        model="llama",
        meta={"subrun": True},
    )

    registry_file = store.persist_dir / "subrun_registry.json"
    registry_payload = {
        "version": 1,
        "updated_at": "2026-03-02T00:00:00+00:00",
        "run_specs": {
            run_id: {
                "run_id": run_id,
                "parent_request_id": "req-parent",
                "parent_session_id": "sess-parent",
                "child_session_id": "sess-parent-subrun-orphan",
                "user_message": "recover me",
                "runtime": "local",
                "model": "llama",
                "tool_policy": None,
                "preset": None,
                "timeout_seconds": 5,
                "depth": 1,
                "parent_run_id": None,
                "root_run_id": "req-parent",
                "agent_id": "head-agent",
                "mode": "run",
                "orchestrator_agent_ids": None,
            }
        },
        "run_status": {
            run_id: {
                "run_id": run_id,
                "status": "running",
                "details": {"started_at": "2026-03-02T00:00:00+00:00"},
                "updated_at": "2026-03-02T00:00:00+00:00",
            }
        },
        "announce_status": {},
    }
    registry_file.write_text(json.dumps(registry_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    restored_lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=StateStore(persist_dir=str(tmp_path / "state")),
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=2,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )

    restored_info = restored_lane.get_info(run_id)
    assert restored_info is not None
    assert restored_info.get("status") == "failed"
    details = restored_info.get("details") or {}
    assert details.get("reconciled") is True
    assert details.get("reconcile_reason") == "orphaned_after_restore"

    run_state = StateStore(persist_dir=str(tmp_path / "state")).get_run(run_id)
    assert run_state is not None
    assert run_state.get("status") == "failed"
    assert any(
        event.get("type") == "subrun_orphan_reconciled"
        and event.get("reason") == "orphaned_after_restore"
        for event in (run_state.get("events") or [])
    )


def test_subrun_lane_lifecycle_delivery_error_is_deferred(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=3,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )

    events: list[dict] = []

    async def flaky_send_event(payload: dict) -> None:
        if payload.get("type") == "lifecycle" and payload.get("subrun") is True:
            raise RuntimeError("transient lifecycle sink failure")
        events.append(payload)

    async def run_case() -> str:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="grace lifecycle errors",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=flaky_send_event,
        )
        await lane.wait_for_completion(run_id, timeout=5)
        return run_id

    run_id = asyncio.run(run_case())

    status = lane.get_status(run_id)
    assert status is not None
    assert status.get("status") == "completed"
    assert any(evt.get("type") == "subrun_announce" and evt.get("status") == "completed" for evt in events)

    run_log = lane.get_log(run_id) or []
    assert any(
        event.get("type") == "lifecycle_delivery_deferred"
        and event.get("stage") == "run_started"
        for event in run_log
    )


def test_subrun_lane_restore_respects_orphan_grace_window(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    run_id = "orphan-grace-run"
    store.init_run(
        run_id=run_id,
        session_id="sess-parent-subrun-grace",
        request_id=run_id,
        user_message="recover me later",
        runtime="local",
        model="llama",
        meta={"subrun": True},
    )

    registry_file = store.persist_dir / "subrun_registry.json"
    registry_payload = {
        "version": 1,
        "updated_at": "2026-03-02T00:00:00+00:00",
        "run_specs": {
            run_id: {
                "run_id": run_id,
                "parent_request_id": "req-parent",
                "parent_session_id": "sess-parent",
                "child_session_id": "sess-parent-subrun-grace",
                "user_message": "recover me later",
                "runtime": "local",
                "model": "llama",
                "tool_policy": None,
                "preset": None,
                "timeout_seconds": 5,
                "depth": 1,
                "parent_run_id": None,
                "root_run_id": "req-parent",
                "agent_id": "head-agent",
                "mode": "run",
                "orchestrator_agent_ids": None,
            }
        },
        "run_status": {
            run_id: {
                "run_id": run_id,
                "status": "running",
                "details": {"started_at": "2026-03-02T00:00:00+00:00"},
                "updated_at": "2999-01-01T00:00:00+00:00",
            }
        },
        "announce_status": {},
    }
    registry_file.write_text(json.dumps(registry_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    restored_lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=StateStore(persist_dir=str(tmp_path / "state")),
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=2,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
        restore_orphan_reconcile_enabled=True,
        restore_orphan_grace_seconds=3600,
    )

    restored_info = restored_lane.get_info(run_id)
    assert restored_info is not None
    assert restored_info.get("status") == "running"


def test_subrun_lane_lifecycle_delivery_error_grace_can_be_disabled(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=5,
        announce_retry_max_attempts=3,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
        lifecycle_delivery_error_grace_enabled=False,
    )

    events: list[dict] = []

    async def flaky_send_event(payload: dict) -> None:
        if payload.get("type") == "lifecycle" and payload.get("subrun") is True:
            raise RuntimeError("hard lifecycle sink failure")
        events.append(payload)

    async def run_case() -> str:
        run_id = await lane.spawn(
            parent_request_id="req-parent",
            parent_session_id="sess-parent",
            user_message="disable lifecycle grace",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=flaky_send_event,
        )
        await lane.wait_for_completion(run_id, timeout=5)
        return run_id

    run_id = asyncio.run(run_case())

    status = lane.get_status(run_id)
    assert status is not None
    assert status.get("status") == "failed"
    failed_announce = next(evt for evt in events if evt.get("type") == "subrun_announce" and evt.get("status") == "failed")
    assert failed_announce["handover"]["terminal_reason"] == "subrun-error"


def test_subrun_lane_retention_prunes_terminal_status_maps(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    lane = SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=store,
        max_concurrent=1,
        max_spawn_depth=2,
        max_children_per_parent=20,
        announce_retry_max_attempts=2,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
        max_retained_terminal_runs=3,
        max_retained_run_entries=3,
    )

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> list[str]:
        run_ids: list[str] = []
        for idx in range(8):
            run_id = await lane.spawn(
                parent_request_id=f"req-{idx}",
                parent_session_id="sess-parent",
                user_message=f"task-{idx}",
                runtime="local",
                model="llama",
                timeout_seconds=5,
                tool_policy=None,
                send_event=send_event,
            )
            await lane.wait_for_completion(run_id, timeout=5)
            run_ids.append(run_id)
            await asyncio.sleep(0.002)
        return run_ids

    run_ids = asyncio.run(run_case())

    assert len(lane._run_status) <= 3
    assert len(lane._announce_status) <= 3
    assert run_ids[-1] in lane._run_status
    assert run_ids[0] not in lane._run_status
