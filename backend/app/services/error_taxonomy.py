"""Canonical error-classification taxonomy for tool results.

Single source of truth for error patterns used by:
- ``ToolRetryStrategy``  (retry decisions)
- ``ToolOutcomeVerifier`` (outcome classification)
- ``HeadAgent``           (replan classification)

Each entry is a ``(compiled_regex, category, description)`` tuple.
Consumers that only need ``(pattern, category)`` can ignore the
third element.
"""

from __future__ import annotations

import re
from enum import StrEnum


# ── Error categories ──────────────────────────────────────────────────

class ErrorCategory(StrEnum):
    """Canonical error-category labels.

    Using a StrEnum ensures that typos are caught at import time
    and IDE / type-checker support is available everywhere.
    """

    TRANSIENT = "transient"
    MISSING_DEPENDENCY = "missing_dependency"
    INVALID_ARGS = "invalid_args"
    PERMISSION = "permission"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CRASH = "crash"
    UNKNOWN = "unknown"


# ── Shared error patterns ────────────────────────────────────────────

ERROR_PATTERNS: list[tuple[re.Pattern[str], ErrorCategory, str]] = [
    # Transient / network
    (
        re.compile(
            r"timeout|ECONNRESET|ECONNREFUSED|connection refused|connection reset"
            r"|503 service unavailable|502 bad gateway|429 too many"
            r"|temporary|temporarily|try again|busy|rate.?limit",
            re.IGNORECASE,
        ),
        ErrorCategory.TRANSIENT,
        "Transient network or service error",
    ),
    # Missing dependency
    (
        re.compile(
            r"command not found|not recognized as|is not recognized"
            r"|'(\w+)' is not installed|No such file or directory.*bin/"
            r"|ModuleNotFoundError|No module named|ImportError",
            re.IGNORECASE,
        ),
        ErrorCategory.MISSING_DEPENDENCY,
        "Command or dependency not available",
    ),
    # Invalid arguments / syntax
    (
        re.compile(
            r"invalid option|unknown flag|unrecognized argument"
            r"|no such option|unexpected argument"
            r"|SyntaxError|IndentationError|NameError|TypeError",
            re.IGNORECASE,
        ),
        ErrorCategory.INVALID_ARGS,
        "Syntax or argument error in command/code",
    ),
    # Permission
    (
        re.compile(
            r"permission denied|access denied|EACCES|Operation not permitted"
            r"|requires? (admin|root|sudo|elevated)",
            re.IGNORECASE,
        ),
        ErrorCategory.PERMISSION,
        "Insufficient permissions",
    ),
    # Resource exhaustion
    (
        re.compile(
            r"disk full|no space left|out of memory|ENOMEM"
            r"|port.+in use|address already in use|EADDRINUSE",
            re.IGNORECASE,
        ),
        ErrorCategory.RESOURCE_EXHAUSTION,
        "System resource exhaustion",
    ),
    # Crash / fatal
    (
        re.compile(
            r"Traceback \(most recent call last\)|panic:|fatal error"
            r"|SIGSEGV|Segmentation fault|core dumped|stack overflow",
            re.IGNORECASE,
        ),
        ErrorCategory.CRASH,
        "Process crashed or produced a stack trace",
    ),
]


def classify_error(text: str) -> ErrorCategory:
    """Classify *text* into a canonical :class:`ErrorCategory`.

    Returns :attr:`ErrorCategory.UNKNOWN` when no pattern matches.
    """
    for pattern, category, _description in ERROR_PATTERNS:
        if pattern.search(text):
            return category
    return ErrorCategory.UNKNOWN
