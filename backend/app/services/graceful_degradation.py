"""L6.5  GracefulDegradation — partial results + explanation instead of "Failed".

When all recovery attempts have been exhausted, this module builds a
structured degradation response that includes:
  - What was attempted and why it failed
  - Any partial results that were produced
  - Suggested manual steps for the user
  - Confidence level for each partial result

Usage::

    degradation = GracefulDegradation()
    response = degradation.build_response(
        task="Convert markdown to PDF",
        attempts=[attempt1, attempt2],
        partial_results=["HTML version generated successfully"],
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FailedAttempt:
    """Record of one failed attempt."""

    tool: str
    command: str = ""
    error: str = ""
    error_category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "command": self.command,
            "error": self.error,
            "error_category": self.error_category,
        }


@dataclass(frozen=True)
class DegradationResponse:
    """Structured response when a task cannot be fully completed."""

    task: str
    fully_resolved: bool = False
    partial_results: list[str] = field(default_factory=list)
    failed_attempts: list[FailedAttempt] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    explanation: str = ""
    confidence: float = 0.0     # 0.0 = nothing useful, 1.0 = fully done

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "fully_resolved": self.fully_resolved,
            "partial_results": self.partial_results,
            "failed_attempts": [a.to_dict() for a in self.failed_attempts],
            "suggestions": self.suggestions,
            "explanation": self.explanation,
            "confidence": round(self.confidence, 2),
        }

    def format_for_user(self) -> str:
        """Render a human-readable summary for the end user."""
        parts: list[str] = []

        if self.fully_resolved:
            parts.append(f"Task completed: {self.task}")
            return "\n".join(parts)

        parts.append(f"Task partially completed: {self.task}")
        parts.append("")

        if self.partial_results:
            parts.append("Partial results:")
            parts.extend(f"  - {pr}" for pr in self.partial_results)
            parts.append("")

        if self.failed_attempts:
            parts.append(f"Attempted {len(self.failed_attempts)} approach(es):")
            parts.extend(f"  - {fa.tool}: {fa.error[:120]}" for fa in self.failed_attempts)
            parts.append("")

        if self.suggestions:
            parts.append("Suggested next steps:")
            parts.extend(f"  - {s}" for s in self.suggestions)
            parts.append("")

        if self.explanation:
            parts.append(self.explanation)

        return "\n".join(parts)


# ── Suggestion generators ────────────────────────────────────────────

_CATEGORY_SUGGESTIONS: dict[str, str] = {
    "missing_dependency": "Install the required tool manually: check the error message for the package name.",
    "permission": "Run the command with appropriate permissions or check file ownership.",
    "transient": "Try again in a few moments — the issue may be temporary.",
    "invalid_args": "Check the command arguments for typos or missing values.",
    "resource_exhaustion": "Free up disk space or memory and retry.",
    "crash": "Check the tool's documentation or update it to the latest version.",
    "environment": "Verify that the working directory and environment variables are correct.",
}


def _generate_suggestions(attempts: list[FailedAttempt]) -> list[str]:
    """Generate unique suggestions based on error categories."""
    seen: set[str] = set()
    suggestions: list[str] = []
    for attempt in attempts:
        cat = attempt.error_category or "unknown"
        if cat in seen:
            continue
        seen.add(cat)
        suggestion = _CATEGORY_SUGGESTIONS.get(cat)
        if suggestion:
            suggestions.append(suggestion)
    if not suggestions:
        suggestions.append("Review the error messages above and try a different approach.")
    return suggestions


# ── Main class ────────────────────────────────────────────────────────


class GracefulDegradation:
    """Build structured degradation responses.

    Usage::

        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Convert to PDF",
            attempts=[FailedAttempt(tool="pandoc", error="not found")],
            partial_results=["HTML generated"],
        )
        print(resp.format_for_user())
    """

    def build_response(
        self,
        *,
        task: str,
        attempts: list[FailedAttempt] | None = None,
        partial_results: list[str] | None = None,
        explanation: str = "",
    ) -> DegradationResponse:
        """Assemble a ``DegradationResponse``."""
        attempts = attempts or []
        partial_results = partial_results or []

        suggestions = _generate_suggestions(attempts)

        # Confidence: based on partial results vs total attempts
        if not attempts and partial_results:
            confidence = 1.0
        elif partial_results:
            confidence = len(partial_results) / (len(partial_results) + len(attempts))
        else:
            confidence = 0.0

        if not explanation:
            if not attempts:
                explanation = "No approaches were attempted."
            elif partial_results:
                explanation = (
                    f"The task could not be fully completed. "
                    f"{len(partial_results)} partial result(s) were produced, "
                    f"but {len(attempts)} approach(es) failed."
                )
            else:
                explanation = (
                    f"All {len(attempts)} approach(es) failed. "
                    f"See suggestions below for manual resolution."
                )

        fully_resolved = len(attempts) == 0 and len(partial_results) > 0

        logger.info(
            "degradation: task='%s' resolved=%s confidence=%.2f partials=%d failures=%d",
            task, fully_resolved, confidence, len(partial_results), len(attempts),
        )

        return DegradationResponse(
            task=task,
            fully_resolved=fully_resolved,
            partial_results=partial_results,
            failed_attempts=attempts,
            suggestions=suggestions,
            explanation=explanation,
            confidence=confidence,
        )
