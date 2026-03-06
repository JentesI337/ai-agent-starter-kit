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


def test_policy_approval_service_allow_session_applies_only_to_current_session() -> None:
    service = PolicyApprovalService()

    async def run_case() -> tuple[str | None, bool, bool, bool]:
        created = await service.create(
            run_id="run-5",
            session_id="sess-5",
            agent_name="head-agent",
            tool="run_command",
            resource="echo hi",
            display_text="allow in session?",
        )
        await service.decide(created["approval_id"], "allow_session", scope="session_tool")
        decision = await service.wait_for_decision(created["approval_id"], timeout_seconds=1.0)
        preapproved_same_session = await service.is_preapproved(
            tool="run_command",
            resource="another command",
            session_id="sess-5",
        )
        preapproved_other_session = await service.is_preapproved(
            tool="run_command",
            resource="another command",
            session_id="sess-other",
        )
        await service.clear_session_overrides("sess-5")
        preapproved_after_clear = await service.is_preapproved(
            tool="run_command",
            resource="another command",
            session_id="sess-5",
        )
        return decision, preapproved_same_session, preapproved_other_session, preapproved_after_clear

    decision, preapproved_same_session, preapproved_other_session, preapproved_after_clear = asyncio.run(run_case())
    assert decision == "allow_session"
    assert preapproved_same_session is True
    assert preapproved_other_session is False
    assert preapproved_after_clear is False


def test_policy_approval_service_duplicate_decision_is_ignored() -> None:
    service = PolicyApprovalService()

    async def run_case() -> tuple[dict, dict]:
        created = await service.create(
            run_id="run-6",
            session_id="sess-6",
            agent_name="head-agent",
            tool="run_command",
            resource="echo hi",
            display_text="allow once?",
        )
        first = await service.decide(created["approval_id"], "allow_once")
        second = await service.decide(created["approval_id"], "cancel")
        return first or {}, second or {}

    first, second = asyncio.run(run_case())
    assert first.get("decision") == "allow_once"
    assert second.get("decision") == "allow_once"
    assert second.get("duplicate_decision") is True
    assert second.get("duplicate_matches_existing") is False


def test_policy_approval_service_create_is_idempotent_for_same_run_and_resource() -> None:
    service = PolicyApprovalService()

    async def run_case() -> tuple[dict, dict]:
        first = await service.create(
            run_id="run-7",
            session_id="sess-7",
            agent_name="head-agent",
            tool="run_command",
            resource="ng new calculator-app",
            display_text="allow?",
        )
        second = await service.create(
            run_id="run-7",
            session_id="sess-7",
            agent_name="head-agent",
            tool="run_command",
            resource="ng new calculator-app",
            display_text="allow?",
        )
        return first, second

    first, second = asyncio.run(run_case())
    assert first.get("approval_id") == second.get("approval_id")
    assert first.get("status") == "pending"
    assert second.get("status") == "pending"
    assert first.get("idempotent_reuse") is False
    assert second.get("idempotent_reuse") is True


# ---------------------------------------------------------------------------
# Regression tests for Bug 1/2/3 fixes
# ---------------------------------------------------------------------------


def test_create_does_not_reuse_expired_record() -> None:
    """create() must NOT return a timed-out record as idempotent_reuse=True.

    Bug 1: the old idempotency check had no status filter, so after a 30-second
    timeout an expired record was handed back to the caller. The caller then skipped
    wait_for_decision (because decision was already "timeout") and the agent never
    got another approval prompt.
    """
    service = PolicyApprovalService()

    async def run_case() -> tuple[str, str, bool]:
        first = await service.create(
            run_id="run-r1",
            session_id="sess-r1",
            agent_name="head-agent",
            tool="run_command",
            resource="get-content foo.txt",
            display_text="allow?",
        )
        # Simulate timeout: mark the record "expired" as the timeout coroutine does.
        first_id = first["approval_id"]
        service._records[first_id]["status"] = "expired"
        service._records[first_id]["decision"] = "timeout"

        second = await service.create(
            run_id="run-r1",
            session_id="sess-r1",
            agent_name="head-agent",
            tool="run_command",
            resource="get-content foo.txt",
            display_text="allow?",
        )
        return first_id, second["approval_id"], bool(second.get("idempotent_reuse"))

    first_id, second_id, reused = asyncio.run(run_case())
    assert second_id != first_id, "A fresh approval must be created, not the expired one"
    assert reused is False


def test_allow_session_on_expired_record_still_applies_session_override() -> None:
    """decide(allow_session) on an already-expired record must still update
    _session_allow_all so subsequent is_preapproved() calls return True.

    Bug 2 (partial): the old code returned early for non-pending records without
    touching _session_allow_all, silently dropping the user's intent.
    """
    service = PolicyApprovalService()

    async def run_case() -> tuple[bool, bool]:
        created = await service.create(
            run_id="run-r2",
            session_id="sess-r2",
            agent_name="head-agent",
            tool="run_command",
            resource="get-content foo.txt",
            display_text="allow?",
        )
        # Simulate the approval having timed out before the user clicked.
        service._records[created["approval_id"]]["status"] = "expired"
        service._records[created["approval_id"]]["decision"] = "timeout"

        # User clicks "Allow all in this session" on the now-expired prompt.
        await service.decide(created["approval_id"], "allow_session", scope="session_tool")

        preapproved_same_session = await service.is_preapproved(
            tool="run_command",
            resource="any-other-resource",
            session_id="sess-r2",
        )
        preapproved_other_session = await service.is_preapproved(
            tool="run_command",
            resource="any-other-resource",
            session_id="sess-other",
        )
        return preapproved_same_session, preapproved_other_session

    same, other = asyncio.run(run_case())
    assert same is True, "Session override must be set even when record was already expired"
    assert other is False, "Override must not bleed into other sessions"


def test_allow_session_cascades_to_pending_sibling_approvals() -> None:
    """decide(allow_session) on one approval must immediately unblock every other
    pending approval for the same (session_id, tool) pair.

    Bug 2 (cascade): without the fix, sibling approvals time out even after the
    user clicks "Allow all in this session" because their asyncio.Event is never set.
    """
    service = PolicyApprovalService()

    async def run_case() -> tuple[str | None, str | None]:
        # approval_A: first prompt (will be the one the user clicks on)
        approval_a = await service.create(
            run_id="run-r3a",
            session_id="sess-r3",
            agent_name="head-agent",
            tool="run_command",
            resource="get-content a.txt",
            display_text="allow a?",
        )
        # approval_B: second prompt for the same session+tool, different resource
        approval_b = await service.create(
            run_id="run-r3b",
            session_id="sess-r3",
            agent_name="head-agent",
            tool="run_command",
            resource="get-content b.txt",
            display_text="allow b?",
        )

        # Start waiting on B with a generous timeout so it resolves via cascade,
        # not via its own timeout.
        wait_b = asyncio.ensure_future(
            service.wait_for_decision(approval_b["approval_id"], timeout_seconds=5.0)
        )

        # User clicks "Allow all in this session" on A.
        await service.decide(approval_a["approval_id"], "allow_session", scope="session_tool")

        decision_b = await asyncio.wait_for(wait_b, timeout=2.0)
        decision_a = await service.wait_for_decision(approval_a["approval_id"], timeout_seconds=1.0)
        return decision_a, decision_b

    decision_a, decision_b = asyncio.run(run_case())
    assert decision_a == "allow_session"
    assert decision_b == "allow_session", "Sibling approval must be cascaded to 'allow_session'"
