from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextWindowGuardResult:
    tokens: int
    should_warn: bool
    should_block: bool


def evaluate_context_window_guard(*, tokens: int, warn_below_tokens: int, hard_min_tokens: int) -> ContextWindowGuardResult:
    safe_tokens = max(0, int(tokens))
    warn_below = max(1, int(warn_below_tokens))
    hard_min = max(1, int(hard_min_tokens))

    if hard_min > warn_below:
        warn_below = hard_min

    return ContextWindowGuardResult(
        tokens=safe_tokens,
        should_warn=safe_tokens > 0 and safe_tokens < warn_below,
        should_block=safe_tokens > 0 and safe_tokens < hard_min,
    )
