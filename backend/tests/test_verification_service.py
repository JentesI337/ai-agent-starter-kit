from __future__ import annotations

from app.quality.verification_service import VerificationService


def test_verify_final_ok() -> None:
    service = VerificationService()
    result = service.verify_final(
        user_message="Implement and verify",
        final_text="Implemented fairness and verified with tests.",
    )
    assert result.status == "ok"


def test_verify_final_flags_empty() -> None:
    service = VerificationService()
    result = service.verify_final(user_message="test", final_text="")
    assert result.status == "failed"
    assert result.reason == "empty_final"
