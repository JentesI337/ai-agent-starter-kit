from __future__ import annotations

from app.orchestrator.subrun_lane import SubrunLane
from app.state import StateStore


class _FakeOrchestratorApi:
    async def run_user_message(self, *, user_message: str, send_event, request_context):
        await send_event({"type": "final", "message": f"done:{user_message}"})
        return f"done:{user_message}"


def _new_lane(tmp_path) -> SubrunLane:
    return SubrunLane(
        orchestrator_api=_FakeOrchestratorApi(),
        state_store=StateStore(persist_dir=str(tmp_path / "state")),
        max_concurrent=2,
        max_spawn_depth=3,
        max_children_per_parent=5,
        announce_retry_max_attempts=2,
        announce_retry_base_delay_ms=10,
        announce_retry_max_delay_ms=50,
        announce_retry_jitter=False,
    )


def test_visibility_scope_self_and_tree(tmp_path) -> None:
    import asyncio

    lane = _new_lane(tmp_path)

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> tuple[str, str]:
        run_id = await lane.spawn(
            parent_request_id="root-request",
            parent_session_id="sess-root",
            user_message="x",
            runtime="local",
            model="llama",
            timeout_seconds=5,
            tool_policy=None,
            send_event=send_event,
        )
        await lane.wait_for_completion(run_id, timeout=5)
        return run_id, "sess-root"

    run_id, root_session = asyncio.run(run_case())

    allowed_self, _ = lane.evaluate_visibility(
        run_id,
        requester_session_id=root_session,
        visibility_scope="self",
    )
    denied_self, _ = lane.evaluate_visibility(
        run_id,
        requester_session_id="another-session",
        visibility_scope="self",
    )
    allowed_tree, _ = lane.evaluate_visibility(
        run_id,
        requester_session_id=root_session,
        visibility_scope="tree",
    )

    assert allowed_self is True
    assert denied_self is False
    assert allowed_tree is True
