from __future__ import annotations

from dataclasses import dataclass
import re


_TOOL_BLOCK_PATTERN = re.compile(r"(?ms)^\[[^\]\n]+\]\n?")


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
        if safe_limit > 0:
            reduced = f"{reduced[:safe_limit]}{suffix}"
        else:
            reduced = suffix[:max_input_chars]
        reason = "context_budget"

    modified = reduced != source
    return (
        reduced,
        ToolResultContextGuardResult(
            modified=modified,
            original_chars=len(source),
            reduced_chars=len(reduced),
            reason=reason if modified else "none",
        ),
    )
