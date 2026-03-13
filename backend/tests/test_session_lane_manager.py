from __future__ import annotations

import asyncio

import pytest

from app.orchestration.session_lane_manager import SessionLaneManager


def test_on_released_error_does_not_mask_run_error() -> None:
    manager = SessionLaneManager(global_max_concurrent=2)

    async def _run() -> str:
        raise ValueError("run failed")

    async def _on_released(_details: dict) -> None:
        raise RuntimeError("release failed")

    async def _execute() -> None:
        await manager.run_in_lane(
            session_id="sess-a",
            on_acquired=None,
            run=_run,
            on_released=_on_released,
        )

    with pytest.raises(ValueError, match="run failed"):
        asyncio.run(_execute())


def test_on_released_error_propagates_when_run_succeeds() -> None:
    manager = SessionLaneManager(global_max_concurrent=2)

    async def _run() -> str:
        return "ok"

    async def _on_released(_details: dict) -> None:
        raise RuntimeError("release failed")

    async def _execute() -> None:
        await manager.run_in_lane(
            session_id="sess-b",
            on_acquired=None,
            run=_run,
            on_released=_on_released,
        )

    with pytest.raises(RuntimeError, match="release failed"):
        asyncio.run(_execute())


def test_session_lock_cache_evicts_idle_entries() -> None:
    manager = SessionLaneManager(
        global_max_concurrent=2,
        max_cached_session_locks=32,
        session_lock_idle_ttl_seconds=0.01,
    )

    async def _run_once(session_id: str) -> str:
        async def _run() -> str:
            return "ok"

        return await manager.run_in_lane(
            session_id=session_id,
            on_acquired=None,
            run=_run,
            on_released=None,
        )

    async def _execute() -> None:
        for idx in range(120):
            await _run_once(f"sess-{idx}")
        await asyncio.sleep(0.02)
        await _run_once("sess-trigger")

    asyncio.run(_execute())

    assert len(manager._session_locks) <= 32


def test_on_released_fires_exactly_once_on_run_failure() -> None:
    manager = SessionLaneManager(global_max_concurrent=2)
    released_calls: list[dict] = []

    async def _run() -> str:
        raise RuntimeError("non-retryable model failure")

    async def _on_released(details: dict) -> None:
        released_calls.append(details)

    async def _execute() -> None:
        await manager.run_in_lane(
            session_id="sess-c",
            on_acquired=None,
            run=_run,
            on_released=_on_released,
        )

    with pytest.raises(RuntimeError, match="non-retryable model failure"):
        asyncio.run(_execute())

    assert len(released_calls) == 1
