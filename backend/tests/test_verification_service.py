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


def test_verify_plan_semantically_warns_on_low_coverage() -> None:
    service = VerificationService()

    result = service.verify_plan_semantically(
        user_message="Please add websocket authentication and token refresh handling",
        plan_text="1. Improve UI labels\n2. Tidy docs\n3. Reformat code",
    )

    assert result.status == "warning"
    assert result.reason == "plan_may_miss_user_intent"
    assert result.details.get("coverage", 1.0) < 0.15
    assert isinstance(result.details.get("missing"), list)


def test_verify_plan_semantically_ok_on_sufficient_overlap() -> None:
    service = VerificationService()

    result = service.verify_plan_semantically(
        user_message="Implement websocket authentication and token refresh for sessions",
        plan_text="1. Implement websocket authentication\n2. Add token refresh handling\n3. Validate session flow",
    )

    assert result.status == "ok"
    assert result.reason == "plan_covers_intent"
    assert result.details.get("coverage", 0.0) >= 0.15
