from __future__ import annotations

import asyncio

from app.services.policy_approval_service import PolicyApprovalService


def test_policy_approval_service_allow_and_wait() -> None:
    service = PolicyApprovalService()

    async def run_case() -> bool:
        created = await service.create(
            run_id="run-1",
            session_id="sess-1",
            agent_name="head-agent",
            tool="run_command",
            resource="pytest -q",
            display_text="allow?",
        )
        await service.allow(created["approval_id"])
        return await service.wait_for_allow(created["approval_id"], timeout_seconds=1.0)

    assert asyncio.run(run_case()) is True


def test_policy_approval_service_timeout_marks_expired() -> None:
    service = PolicyApprovalService()

    async def run_case() -> tuple[bool, list[dict]]:
        created = await service.create(
            run_id="run-2",
            session_id="sess-2",
            agent_name="head-agent",
            tool="spawn_subrun",
            resource="deep research",
            display_text="allow spawn?",
        )
        allowed = await service.wait_for_allow(created["approval_id"], timeout_seconds=0.1)
        pending = await service.list_pending(run_id="run-2", limit=10)
        return allowed, pending

    allowed, pending = asyncio.run(run_case())
    assert allowed is False
    assert pending == []
