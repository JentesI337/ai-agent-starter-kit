from __future__ import annotations

import asyncio
import pytest

from app.errors import GuardrailViolation
from app.interfaces.request_context import RequestContext
from app.orchestrator.subrun_lane import SubrunLane
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
    assert any(event.get("type") == "subrun_announce" and event.get("status") == "completed" for event in events)


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
    assert any(event.get("type") == "subrun_announce" and event.get("status") == "timed_out" for event in events)


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
