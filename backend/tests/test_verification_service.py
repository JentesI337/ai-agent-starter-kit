from __future__ import annotations

from app.services.verification_service import VerificationService


def test_verification_service_plan_and_tool_and_final() -> None:
    service = VerificationService()

    plan_result = service.verify_plan(
        user_message="Please inspect and fix the queue behavior.",
        plan_text="1. Inspect queue implementation\n2. Add fairness\n3. Validate with tests",
    )
    assert plan_result.status == "ok"

    tool_result = service.verify_tool_result(
        plan_text="Inspect queue and implement fairness",
        tool_results="[read_file]\n[OK] loaded queue code",
    )
    assert tool_result.status == "ok"

    final_result = service.verify_final(
        user_message="Implement and verify",
        final_text="Implemented fairness and verified with tests.",
    )
    assert final_result.status == "ok"


def test_verification_service_flags_empty_outputs() -> None:
    service = VerificationService()

    plan_result = service.verify_plan(user_message="test", plan_text="")
    assert plan_result.status == "failed"
    assert plan_result.reason == "empty_plan"

    tool_result = service.verify_tool_result(plan_text="plan", tool_results="")
    assert tool_result.status == "warning"
    assert tool_result.reason == "empty_tool_results"

    final_result = service.verify_final(user_message="test", final_text="")
    assert final_result.status == "failed"
    assert final_result.reason == "empty_final"
