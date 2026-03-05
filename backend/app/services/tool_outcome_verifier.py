"""Lightweight deterministic outcome verification for tool results.

Classifies tool results as verified / suspicious / failed based on
structural checks — no LLM calls, no network. Fast enough to run
inline after every tool call (<1ms).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.error_taxonomy import classify_error


@dataclass(frozen=True)
class OutcomeVerdict:
    """Result of a tool outcome verification."""

    status: str  # "verified" | "suspicious" | "failed"
    reason: str  # human-readable explanation
    error_category: str | None = None  # from error taxonomy if applicable
    checks_passed: int = 0
    checks_failed: int = 0

# Results that indicate emptiness (suspicious but not failed)
_EMPTY_RESULT_PATTERNS = re.compile(
    r"^\s*$|^None$|^null$|^\[\]$|^\{\}$|^undefined$",
    re.IGNORECASE,
)


class ToolOutcomeVerifier:
    """Classifies tool outcomes using fast deterministic checks.

    Usage:
        verifier = ToolOutcomeVerifier()
        verdict = verifier.verify(tool="run_command", result=result_text)
    """

    def verify(
        self,
        *,
        tool: str,
        result: str,
        args: dict | None = None,
    ) -> OutcomeVerdict:
        """Verify a tool result and return a verdict."""
        checks_passed = 0
        checks_failed = 0
        issues: list[str] = []
        error_category: str | None = None

        text = result or ""

        # ── Check 1: Explicit error markers ──────────────────────────
        if text.startswith("[error]") or text.startswith("ERROR:"):
            checks_failed += 1
            error_category = self._classify_error_text(text)
            return OutcomeVerdict(
                status="failed",
                reason=f"Explicit error marker in result",
                error_category=error_category,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
            )
        checks_passed += 1

        # ── Check 2: Empty or trivially empty result ─────────────────
        if _EMPTY_RESULT_PATTERNS.match(text.strip()):
            checks_failed += 1
            return OutcomeVerdict(
                status="suspicious",
                reason="Result is empty or trivially empty",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
            )
        checks_passed += 1

        # ── Check 3: Tool-specific checks ────────────────────────────
        if tool == "run_command":
            verdict = self._verify_run_command(text, args)
            if verdict is not None:
                return verdict

        elif tool in ("write_file", "apply_patch"):
            verdict = self._verify_write_tool(tool, text, args)
            if verdict is not None:
                return verdict

        elif tool == "read_file":
            verdict = self._verify_read_file(text, args)
            if verdict is not None:
                return verdict

        elif tool == "web_fetch":
            verdict = self._verify_web_fetch(text)
            if verdict is not None:
                return verdict

        elif tool == "code_execute":
            verdict = self._verify_code_execute(text)
            if verdict is not None:
                return verdict

        # ── Check 4: Generic error pattern scan ──────────────────────
        error_category = self._classify_error_text(text)
        if error_category is not None:
            # Only flag as suspicious, not failed — some tools legitimately
            # output error-like text (e.g. grep_search finding error messages)
            if tool not in ("grep_search", "read_file", "file_search", "list_dir"):
                checks_failed += 1
                return OutcomeVerdict(
                    status="suspicious",
                    reason=f"Error pattern detected: {error_category}",
                    error_category=error_category,
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                )
        checks_passed += 1

        return OutcomeVerdict(
            status="verified",
            reason="All checks passed",
            checks_passed=checks_passed,
            checks_failed=0,
        )

    def _verify_run_command(
        self, text: str, args: dict | None,
    ) -> OutcomeVerdict | None:
        """Check run_command specific patterns."""
        lower = text.lower()

        # Explicit non-zero exit code
        exit_match = re.search(r"exit code[:\s]+(\d+)", lower)
        if exit_match:
            code = int(exit_match.group(1))
            if code != 0:
                error_cat = self._classify_error_text(text)
                return OutcomeVerdict(
                    status="failed",
                    reason=f"Non-zero exit code: {code}",
                    error_category=error_cat or "command_failed",
                    checks_passed=1,
                    checks_failed=1,
                )

        # stderr indicators combined with error keywords
        if "stderr:" in lower and any(
            kw in lower for kw in ("error", "fatal", "failed", "exception", "panic")
        ):
            error_cat = self._classify_error_text(text)
            return OutcomeVerdict(
                status="suspicious",
                reason="stderr contains error keywords",
                error_category=error_cat,
                checks_passed=1,
                checks_failed=1,
            )

        return None

    def _verify_write_tool(self, tool: str, text: str, args: dict | None) -> OutcomeVerdict | None:
        """Check write_file / apply_patch results."""
        lower = text.lower()

        if "error" in lower and ("no such file" in lower or "not found" in lower):
            return OutcomeVerdict(
                status="failed",
                reason="File not found during write operation",
                error_category="file_not_found",
                checks_passed=0,
                checks_failed=1,
            )

        if tool == "apply_patch" and "no match found" in lower:
            return OutcomeVerdict(
                status="failed",
                reason="Patch search string not found in file",
                error_category="patch_no_match",
                checks_passed=0,
                checks_failed=1,
            )

        return None

    def _verify_read_file(self, text: str, args: dict | None) -> OutcomeVerdict | None:
        """Check read_file results — content-type plausibility."""
        lower = text.lower()

        # File not found
        if "no such file" in lower or "file not found" in lower or "does not exist" in lower:
            return OutcomeVerdict(
                status="failed",
                reason="Target file does not exist",
                error_category="file_not_found",
                checks_passed=0,
                checks_failed=1,
            )

        # L1.4  Binary-content detection — reading binary files usually
        # produces gibberish with many \x00 / replacement chars.
        nul_count = text.count("\x00")
        replacement_count = text.count("\ufffd")
        if len(text) > 100 and (nul_count > 20 or replacement_count > 20):
            return OutcomeVerdict(
                status="suspicious",
                reason="File appears to be binary (many NUL / replacement characters)",
                error_category="binary_content",
                checks_passed=1,
                checks_failed=1,
            )

        return None

    def _verify_web_fetch(self, text: str) -> OutcomeVerdict | None:
        """Check web_fetch results."""
        lower = text.lower()

        if any(code in lower for code in ("404 not found", "403 forbidden", "401 unauthorized")):
            return OutcomeVerdict(
                status="failed",
                reason="HTTP error response",
                error_category="http_error",
                checks_passed=0,
                checks_failed=1,
            )

        # Suspiciously short response for a web page
        if len(text.strip()) < 50:
            return OutcomeVerdict(
                status="suspicious",
                reason="Web fetch returned very little content",
                checks_passed=1,
                checks_failed=1,
            )

        return None

    def _verify_code_execute(self, text: str) -> OutcomeVerdict | None:
        """Check code_execute results."""
        lower = text.lower()

        # Explicit traceback = code crashed
        if "traceback (most recent call last)" in lower:
            error_cat = self._classify_error_text(text)
            return OutcomeVerdict(
                status="failed",
                reason="Code execution produced a traceback",
                error_category=error_cat or "code_crash",
                checks_passed=0,
                checks_failed=1,
            )

        return None

    @staticmethod
    def _classify_error_text(text: str) -> str | None:
        """Classify error text via the shared taxonomy."""
        category = classify_error(text)
        return None if category == "unknown" else str(category)
