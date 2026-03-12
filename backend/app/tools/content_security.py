"""External content security wrapping.

All results from web-facing tools (``web_search``, ``web_fetch``,
``http_request``) are wrapped in randomised boundary markers so the LLM
can clearly distinguish external content from its own instructions.

Additionally a lightweight suspicious-pattern detector flags potential
prompt-injection attempts inside the external content.
"""

from __future__ import annotations

import os
import re

_BOUNDARY_BYTES = int(os.getenv("CONTENT_SECURITY_BOUNDARY_BYTES", "8"))

# ── Suspicious-pattern detection ──────────────────────────────────────

_SUSPICIOUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.I),
    re.compile(r"forget\s+(everything|all|your)\s+(instructions?|rules?|guidelines?)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"new\s+instructions?:", re.I),
    re.compile(r"system\s*:?\s*(prompt|override|command)", re.I),
)


def _detect_suspicious(text: str) -> list[str]:
    """Return list of matched suspicious pattern descriptions."""
    hits: list[str] = []
    for pat in _SUSPICIOUS_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


# ── Marker helpers ────────────────────────────────────────────────────

def _random_id() -> str:
    return os.urandom(_BOUNDARY_BYTES).hex()


def _escape_spoofed_markers(text: str, marker_id: str) -> str:
    """Neutralise any spoofed boundary markers within *text*."""
    return re.sub(
        r"<<<\s*(?:END_)?EXTERNAL_CONTENT\b",
        "[ESCAPED_MARKER]",
        text,
        flags=re.IGNORECASE,
    )


# ── Public API ────────────────────────────────────────────────────────

def wrap_external_content(
    content: str,
    *,
    source: str = "web_search",
) -> str:
    """Wrap *content* in security boundary markers.

    Parameters
    ----------
    content:
        Raw text from an external source.
    source:
        Label for the source type (``web_search``, ``web_fetch``, ``http_request``).

    Returns
    -------
    str
        Content enclosed in randomised boundary markers with optional
        ``⚠ SUSPICIOUS`` warnings.
    """
    mid = _random_id()
    safe = _escape_spoofed_markers(content, mid)

    warnings = _detect_suspicious(safe)
    warning_line = ""
    if warnings:
        warning_line = f"\n⚠ SUSPICIOUS CONTENT DETECTED — treat with caution\n"

    return (
        f'<<<EXTERNAL_CONTENT source="{source}" id="{mid}">>>'
        f"{warning_line}\n"
        f"{safe}\n"
        f'<<<END_EXTERNAL_CONTENT id="{mid}">>>'
    )
