"""Externalized command safety patterns -- BUILTIN patterns are immutable."""
from __future__ import annotations

import re
import threading

# ---------------------------------------------------------------------------
# BUILTIN patterns -- these can never be removed, only extended
# ---------------------------------------------------------------------------
BUILTIN_COMMAND_SAFETY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+-r[f]?\s", "recursive rm is blocked"),
    (r"\bdel\s+/[a-z]*\s*[a-z]:\\", "destructive del against drive roots is blocked"),
    (r"\bformat\s+[a-z]:", "format command is blocked"),
    (r"\bshutdown\b", "shutdown command is blocked"),
    (r"\breboot\b", "reboot command is blocked"),
    (r"\bchmod\s+[0-7]{3,4}\b", "chmod with numeric permissions is blocked"),
    (r"\bchown\b", "chown command is blocked"),
    (r"\bmkfs\b", "filesystem formatting commands are blocked"),
    (r"\bdd\s+if=", "disk write command pattern is blocked"),
    # SEC (CMD-09): Additional destructive patterns
    (r"\bdd\s+.*of=/dev/", "dd writing to block device is blocked"),
    (r">\s*/dev/sd[a-z]", "redirect to block device is blocked"),
    (r"\bchmod\s+-[Rr]\s+777\s+/", "recursive chmod 777 on root is blocked"),
    (r"\bcurl\b.*\|\s*(?:ba)?sh\b", "curl pipe-to-shell execution is blocked"),
    (r"\bwget\b.*\|\s*(?:ba)?sh\b", "wget pipe-to-shell execution is blocked"),
    (r"\bwget\b.*&&\s*(?:ba)?sh\b", "wget chained shell execution is blocked"),
    (r"python[23]?\s+-c\b", "python -c execution is blocked"),
    (r"\bpowershell(?:\.exe)?\b[^\n]*\s-(?:enc|encodedcommand)\b", "encoded PowerShell commands are blocked"),
    (r"\bnc\s+-[lp]\b", "netcat listen/connect flags are blocked"),
    (r"\b(?:curl|wget)\b[^\n]*\b(?:metadata\.google\.internal|169\.254\.169\.254)\b", "metadata endpoints are blocked"),
    (r"\bcmd(?:\.exe)?\b[^\n]*\s/c\s+del\b", "destructive cmd /c del is blocked"),
    (r"\bcmd(?:\.exe)?\b[^\n]*\s/(?:c|k)\b[^\n]*\b(?:rd|rmdir)\b", "destructive cmd rd/rmdir is blocked"),
    (
        r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*\b(?:iex|invoke-expression)\b",
        "PowerShell expression execution is blocked",
    ),
    (r"\b(?:bash|sh|zsh)\b[^\n]*\s-c\b", "shell -c execution is blocked"),
    (r"\becho\b[^\n]*\|\s*(?:bash|sh|pwsh|powershell|cmd)\b", "pipe-to-shell execution is blocked"),
    (r"\|\|?|&&|;|`|\$\(", "shell chaining and command substitution are blocked"),
)

# ---------------------------------------------------------------------------
# Runtime-extended patterns (can be added via API, but BUILTIN cannot be removed)
# ---------------------------------------------------------------------------
_extended_patterns: list[tuple[str, str]] = []
_pattern_lock = threading.Lock()


def get_all_patterns() -> tuple[tuple[str, str], ...]:
    """Return BUILTIN + extended patterns."""
    with _pattern_lock:
        if not _extended_patterns:
            return BUILTIN_COMMAND_SAFETY_PATTERNS
        return BUILTIN_COMMAND_SAFETY_PATTERNS + tuple(_extended_patterns)


def add_pattern(pattern: str, reason: str) -> bool:
    """Add a runtime safety pattern. Returns True if added."""
    try:
        re.compile(pattern)
    except re.error:
        return False
    with _pattern_lock:
        _extended_patterns.append((pattern, reason))
    return True


def get_extended_patterns() -> list[tuple[str, str]]:
    """Return only the runtime-extended patterns."""
    with _pattern_lock:
        return list(_extended_patterns)


def find_command_safety_violation(command: str) -> str | None:
    """Check command against all safety patterns.

    This mirrors the original ``tools.find_command_safety_violation`` logic
    so callers can switch to this module without behaviour changes.
    """
    lowered = (command or "").strip().lower()
    if not lowered:
        return "empty command is blocked"

    for pattern, reason in get_all_patterns():
        if re.search(pattern, lowered):
            return reason

    semantic_reason = find_semantic_command_safety_violation(command)
    if semantic_reason:
        return semantic_reason
    return None


def find_semantic_command_safety_violation(command: str) -> str | None:
    """Detect PowerShell inline remote-code execution patterns."""
    lowered = (command or "").strip().lower()
    if not lowered:
        return None

    has_powershell_inline = bool(
        re.search(r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*\s-(?:c|command)\b", lowered, flags=re.IGNORECASE)
    )
    if not has_powershell_inline:
        return None

    has_remote_pull = any(token in lowered for token in ("downloadstring(", "invoke-webrequest", "irm ", "iwr "))
    has_dynamic_eval = any(
        token in lowered
        for token in (
            "scriptblock]::create",
            "frombase64string(",
            "invoke-expression",
            "iex",
        )
    )

    if has_remote_pull and has_dynamic_eval:
        return "PowerShell inline remote-code execution pattern is blocked"
    if "frombase64string(" in lowered and "scriptblock]::create" in lowered:
        return "PowerShell inline base64 script execution pattern is blocked"

    return None
