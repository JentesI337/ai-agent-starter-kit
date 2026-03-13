from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str
    details: dict[str, object]

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# Patterns that indicate the LLM is referencing tool output it
# never actually received (hallucinated tool references).
_HALLUCINATION_PATTERNS = (
    re.compile(r"\b(?:as shown|as seen) (?:in|by) the (?:output|result|tool|command)", re.IGNORECASE),
    re.compile(r"(?:the tool|the command) (?:returned|showed|output|produced)\s*:", re.IGNORECASE),
    re.compile(r"according to the (?:tool|command) (?:output|result)", re.IGNORECASE),
)


class VerificationService:
    def verify_final(
        self,
        *,
        user_message: str,
        final_text: str,
        tool_results: list[object] | None = None,
    ) -> VerificationResult:
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

        # Detect hallucinated tool references when no tools were actually used
        if not tool_results:
            for pattern in _HALLUCINATION_PATTERNS:
                if pattern.search(normalized_final):
                    return VerificationResult(
                        status="warning",
                        reason="hallucinated_tool_reference",
                        details={
                            "final_chars": len(normalized_final),
                            "user_chars": len(user_message or ""),
                            "pattern": pattern.pattern,
                        },
                    )

        return VerificationResult(
            status="ok",
            reason="final_acceptable",
            details={"final_chars": len(normalized_final), "user_chars": len(user_message or "")},
        )
