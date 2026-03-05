from __future__ import annotations

from dataclasses import dataclass
import re

from app.config import settings


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str
    details: dict[str, object]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class VerificationService:
    def __init__(
        self,
        *,
        plan_coverage_warn_threshold: float | None = None,
        plan_coverage_fail_threshold: float | None = None,
    ) -> None:
        # T1.3: Schwellen konfigurierbar — Defaults aus settings, überschreibbar per Konstruktor (für Tests)
        self._plan_coverage_warn_threshold = float(
            plan_coverage_warn_threshold
            if plan_coverage_warn_threshold is not None
            else settings.plan_coverage_warn_threshold
        )
        self._plan_coverage_fail_threshold = float(
            plan_coverage_fail_threshold
            if plan_coverage_fail_threshold is not None
            else settings.plan_coverage_fail_threshold
        )

    @staticmethod
    def _tokenize_words(text: str) -> set[str]:
        normalized = (text or "").lower()
        return set(re.findall(r"[\wäöüß]+", normalized, flags=re.UNICODE))

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

    def verify_plan_semantically(self, *, user_message: str, plan_text: str) -> VerificationResult:
        user_words = self._tokenize_words(user_message)
        plan_words = self._tokenize_words(plan_text)
        stopwords = {
            "the",
            "a",
            "is",
            "in",
            "to",
            "and",
            "or",
            "of",
            "for",
            "it",
            "my",
            "me",
            "ich",
            "ein",
            "der",
            "die",
            "das",
            "und",
            "oder",
            "für",
            "ist",
            "mir",
        }
        significant_user_words = {word for word in user_words if word not in stopwords and len(word) > 2}
        if not significant_user_words:
            return VerificationResult(status="ok", reason="no_significant_words", details={})

        overlap = significant_user_words & plan_words
        coverage = len(overlap) / len(significant_user_words)
        rounded_coverage = round(coverage, 2)
        # T1.3: Hard-Fail Schwelle (default 0.0 = deaktiviert; via PLAN_COVERAGE_FAIL_THRESHOLD aktivierbar)
        if self._plan_coverage_fail_threshold > 0.0 and coverage < self._plan_coverage_fail_threshold:
            missing_words = sorted(significant_user_words - plan_words)[:5]
            return VerificationResult(
                status="failed",
                reason="plan_semantic_fail",
                details={"coverage": rounded_coverage, "missing": missing_words},
            )
        # Warn-Schwelle (default 0.15 — identisch mit bisherigem Verhalten)
        if coverage < self._plan_coverage_warn_threshold:
            missing_words = sorted(significant_user_words - plan_words)[:5]
            return VerificationResult(
                status="warning",
                reason="plan_may_miss_user_intent",
                details={"coverage": rounded_coverage, "missing": missing_words},
            )
        return VerificationResult(
            status="ok",
            reason="plan_covers_intent",
            details={"coverage": rounded_coverage},
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
        has_error = "] error" in lowered or "[error]" in lowered
        has_ok = "[ok]" in lowered or "] ok" in lowered
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
