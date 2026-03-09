"""Extracted result processing logic from ToolExecutionManager."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResultProcessingConfig:
    max_chars: int = 6000
    smart_truncate_enabled: bool = True
    context_guard_enabled: bool = True
    context_headroom_ratio: float = 0.75
    single_share: float = 0.50

    @classmethod
    def from_settings(cls, settings: Any) -> ResultProcessingConfig:
        return cls(
            max_chars=getattr(settings, "tool_result_max_chars", 6000),
            smart_truncate_enabled=getattr(settings, "tool_result_smart_truncate_enabled", True),
            context_guard_enabled=getattr(settings, "tool_result_context_guard_enabled", True),
            context_headroom_ratio=getattr(settings, "tool_result_context_headroom_ratio", 0.75),
            single_share=getattr(settings, "tool_result_single_share", 0.50),
        )


class ToolResultProcessor:
    """Processes and truncates tool results to fit context budgets."""

    def __init__(self, config: ResultProcessingConfig) -> None:
        self.config = config

    def truncate(self, text: str, *, max_chars: int | None = None) -> str:
        limit = max_chars or self.config.max_chars
        if len(text) <= limit:
            return text
        if self.config.smart_truncate_enabled:
            return self._smart_truncate(text, limit)
        return text[:limit] + f"\n... [truncated, {len(text) - limit} chars omitted]"

    def _smart_truncate(self, text: str, limit: int) -> str:
        """Keep beginning and end, cut middle."""
        if limit < 100:
            return text[:limit]
        head_size = int(limit * 0.6)
        tail_size = limit - head_size - 50  # reserve for marker
        if tail_size < 20:
            return text[:limit] + "\n... [truncated]"
        head = text[:head_size]
        tail = text[-tail_size:]
        omitted = len(text) - head_size - tail_size
        return f"{head}\n\n... [{omitted} chars omitted] ...\n\n{tail}"

    def compute_budget(self, num_results: int, context_budget: int | None = None) -> int:
        """Compute per-result char budget based on context constraints."""
        base = self.config.max_chars
        if context_budget and self.config.context_guard_enabled:
            total_available = int(context_budget * self.config.context_headroom_ratio)
            if num_results > 0:
                per_result = int(total_available / num_results * self.config.single_share)
                base = min(base, per_result)
        return max(200, base)
