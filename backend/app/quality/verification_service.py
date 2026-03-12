from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str
    details: dict[str, object]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class VerificationService:
    def verify_final(self, *, user_message: str, final_text: str) -> VerificationResult:
        normalized_final = (final_text or "").strip()
        if not normalized_final:
            return VerificationResult(
                status="failed",
                reason="empty_final",
                details={"final_chars": 0, "user_chars": len(user_message or "")},
            )
        if len(normalized_final) < 8:
            return VerificationResult(
                status="warning",
                reason="final_too_short",
                details={"final_chars": len(normalized_final), "user_chars": len(user_message or "")},
            )
        return VerificationResult(
            status="ok",
            reason="final_acceptable",
            details={"final_chars": len(normalized_final), "user_chars": len(user_message or "")},
        )
