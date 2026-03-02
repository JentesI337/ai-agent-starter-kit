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


def test_policy_approval_service_deny_decision() -> None:
    service = PolicyApprovalService()

    async def run_case() -> tuple[str | None, bool]:
        created = await service.create(
            run_id="run-3",
            session_id="sess-3",
            agent_name="head-agent",
            tool="run_command",
            resource="rm -rf /tmp/foo",
            display_text="deny?",
        )
        await service.deny(created["approval_id"])
        decision = await service.wait_for_decision(created["approval_id"], timeout_seconds=1.0)
        allowed = await service.wait_for_allow(created["approval_id"], timeout_seconds=1.0)
        return decision, allowed

    decision, allowed = asyncio.run(run_case())
    assert decision == "deny"
    assert allowed is False


def test_policy_approval_service_allow_always_marks_preapproved() -> None:
    service = PolicyApprovalService()

    async def run_case() -> tuple[str | None, bool]:
        created = await service.create(
            run_id="run-4",
            session_id="sess-4",
            agent_name="head-agent",
            tool="run_command",
            resource="echo hi",
            display_text="allow always?",
        )
        await service.allow_always(created["approval_id"])
        decision = await service.wait_for_decision(created["approval_id"], timeout_seconds=1.0)
        preapproved = await service.is_preapproved(tool="run_command", resource="echo hi")
        return decision, preapproved

    decision, preapproved = asyncio.run(run_case())
    assert decision == "allow_always"
    assert preapproved is True
