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
    def verify_plan(self, *, user_message: str, plan_text: str) -> VerificationResult:
        normalized_plan = (plan_text or "").strip()
        if not normalized_plan:
            return VerificationResult(
                status="failed",
                reason="empty_plan",
                details={"plan_chars": 0, "user_chars": len(user_message or "")},
            )
        if len(normalized_plan) < 20:
            return VerificationResult(
                status="warning",
                reason="plan_too_short",
                details={"plan_chars": len(normalized_plan), "user_chars": len(user_message or "")},
            )
        return VerificationResult(
            status="ok",
            reason="plan_acceptable",
            details={"plan_chars": len(normalized_plan), "user_chars": len(user_message or "")},
        )

    def verify_tool_result(self, *, plan_text: str, tool_results: str) -> VerificationResult:
        normalized_plan = (plan_text or "").strip()
        normalized_results = (tool_results or "").strip()
        if not normalized_results:
            return VerificationResult(
                status="warning",
                reason="empty_tool_results",
                details={"plan_chars": len(normalized_plan), "tool_result_chars": 0},
            )

        lowered = normalized_results.lower()
        has_error = " error" in lowered or "[error]" in lowered
        has_ok = "[ok]" in lowered or " ok" in lowered
        if has_error and not has_ok:
            return VerificationResult(
                status="warning",
                reason="tool_results_error_only",
                details={"plan_chars": len(normalized_plan), "tool_result_chars": len(normalized_results)},
            )

        return VerificationResult(
            status="ok",
            reason="tool_results_usable",
            details={"plan_chars": len(normalized_plan), "tool_result_chars": len(normalized_results)},
        )

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
