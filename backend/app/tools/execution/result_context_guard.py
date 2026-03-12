from __future__ import annotations

import re
from dataclasses import dataclass

_TOOL_BLOCK_PATTERN = re.compile(r"(?ms)^\[[^\]\n]+\]\n?")

# ---------------------------------------------------------------------------
# L1.5  PII-Redaction patterns
# ---------------------------------------------------------------------------
# Each tuple: (compiled regex, replacement label).
# Order matters — more specific patterns first to avoid partial matches.

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API keys / bearer tokens  (generic hex/base64 ≥ 20 chars after marker)
    (
        re.compile(
            r"(?i)(api[_-]?key|token|bearer|secret|password|passwd|authorization)"
            r"[\s:=]+['\"]?([A-Za-z0-9_\-/.+]{20,})['\"]?",
        ),
        r"\1=<REDACTED>",
    ),
    # AWS-style keys  (AKIA…, ASIA…)
    (
        re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"),
        "<REDACTED_AWS_KEY>",
    ),
    # E-Mail
    (
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "<REDACTED_EMAIL>",
    ),
    # US phone numbers  (###-###-####, (###) ###-####, +1…)
    # Requires at least one separator to avoid matching plain 10-digit
    # numbers (file sizes, timestamps, memory addresses).
    (
        re.compile(
            r"(?<!\d)(?:\+1[\s.-])?\(?\d{3}\)[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)"
            r"|(?<!\d)\d{3}[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)",
        ),
        "<REDACTED_PHONE>",
    ),
    # SSN-like  (###-##-####)
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "<REDACTED_SSN>",
    ),
    # IPv4 addresses (except 127.0.0.1 and 0.0.0.0)
    (
        re.compile(
            r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)"
            r"(?:25[0-5]|2[0-4]\d|1?\d{1,2})(?:\.(?:25[0-5]|2[0-4]\d|1?\d{1,2})){3}\b",
        ),
        "<REDACTED_IP>",
    ),
]


def redact_pii(text: str) -> tuple[str, int]:
    """Remove PII from *text*.  Returns ``(cleaned, redaction_count)``."""
    count = 0
    for pattern, replacement in _PII_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


# ---------------------------------------------------------------------------
# SEC (OE-06): Prompt-injection anomaly detection in tool results
# ---------------------------------------------------------------------------

_INJECTION_ANOMALY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions?"),
        "<PI_NEUTRALIZED>",
    ),
    (
        re.compile(r"(?i)you\s+are\s+now\s+"),
        "<PI_NEUTRALIZED>",
    ),
    (
        re.compile(r"(?i)new\s+system\s+prompt"),
        "<PI_NEUTRALIZED>",
    ),
    (
        re.compile(r"(?i)(?:^|\n)\s*(?:system|assistant|user)\s*:"),
        "\n<PI_NEUTRALIZED>:",
    ),
    (
        re.compile(r"\[INST\]|\[/INST\]"),
        "<PI_NEUTRALIZED>",
    ),
    (
        re.compile(r"<\|(?:im_start|im_end|system|user|assistant)\|>"),
        "<PI_NEUTRALIZED>",
    ),
    (
        re.compile(r"<!--\s*(?:ignore|system|override|inject|prompt)", re.IGNORECASE),
        "<!-- PI_NEUTRALIZED",
    ),
]


def neutralize_prompt_injections(text: str) -> tuple[str, int]:
    """SEC (OE-06): Detect and neutralize common prompt injection patterns.

    Returns ``(cleaned_text, injection_count)``.
    """
    count = 0
    for pattern, replacement in _INJECTION_ANOMALY_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


@dataclass(frozen=True)
class ToolResultContextGuardResult:
    modified: bool
    original_chars: int
    reduced_chars: int
    reason: str


def _split_tool_result_blocks(text: str) -> list[str]:
    source = str(text or "")
    if not source:
        return []

    matches = list(_TOOL_BLOCK_PATTERN.finditer(source))
    if not matches:
        return [source]

    blocks: list[str] = []
    # Bug 7: preserve any preamble text that appears before the first [header] block
    if matches[0].start() > 0:
        blocks.append(source[: matches[0].start()])
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        blocks.append(source[start:end])
    return blocks


def _truncate_single_block(block: str, *, max_chars: int) -> str:
    if len(block) <= max_chars:
        return block
    suffix = "\n[compacted: tool output removed to free context]"
    safe_limit = max(0, max_chars - len(suffix))
    return f"{block[:safe_limit]}{suffix}" if safe_limit > 0 else suffix


def enforce_tool_result_context_budget(
    *,
    tool_results: str,
    context_window_tokens: int,
    chars_per_token_estimate: float = 4.0,
    context_input_headroom_ratio: float = 0.75,
    single_tool_result_share: float = 0.50,
) -> tuple[str, ToolResultContextGuardResult]:
    source = str(tool_results or "")
    if not source:
        return (
            source,
            ToolResultContextGuardResult(
                modified=False,
                original_chars=0,
                reduced_chars=0,
                reason="none",
            ),
        )

    # L1.5  PII redaction — runs before any truncation so we never
    # accidentally preserve PII that would have been kept inside the
    # context budget.
    pre_redaction_chars = len(source)
    source, pii_redactions = redact_pii(source)

    # SEC (OE-06): Neutralize prompt injection patterns in tool results
    source, injection_count = neutralize_prompt_injections(source)

    normalized_context_tokens = max(1, int(context_window_tokens))
    normalized_chars_per_token = max(1.0, float(chars_per_token_estimate))
    normalized_headroom = max(0.1, min(1.0, float(context_input_headroom_ratio)))
    normalized_single_share = max(0.05, min(1.0, float(single_tool_result_share)))

    max_input_chars = int(normalized_context_tokens * normalized_chars_per_token * normalized_headroom)
    max_single_chars = int(normalized_context_tokens * normalized_chars_per_token * normalized_single_share)
    max_input_chars = max(1, max_input_chars)
    max_single_chars = max(1, min(max_single_chars, max_input_chars))

    blocks = _split_tool_result_blocks(source)
    single_share_modified = False
    if blocks:
        clipped_blocks: list[str] = []
        for block in blocks:
            clipped = _truncate_single_block(block, max_chars=max_single_chars)
            if clipped != block:
                single_share_modified = True
            clipped_blocks.append(clipped)
        reduced = "".join(clipped_blocks)
    else:
        reduced = _truncate_single_block(source, max_chars=max_single_chars)
        single_share_modified = reduced != source

    reason = "single_result_share" if single_share_modified else "none"
    if len(reduced) > max_input_chars:
        suffix = f"\n\n[truncated: tool output exceeded context budget ({len(source)} chars)]"
        safe_limit = max(0, max_input_chars - len(suffix))
        reduced = f"{reduced[:safe_limit]}{suffix}" if safe_limit > 0 else suffix[:max_input_chars]
        reason = "context_budget"

    modified = reduced != source
    if not modified and pii_redactions > 0:
        modified = True
    if not modified and injection_count > 0:
        modified = True
    final_reason = reason if reason != "none" else ("pii_redacted" if pii_redactions > 0 else ("injection_neutralized" if injection_count > 0 else "none"))
    return (
        reduced,
        ToolResultContextGuardResult(
            modified=modified,
            original_chars=pre_redaction_chars,
            reduced_chars=len(reduced),
            reason=final_reason if modified else "none",
        ),
    )
