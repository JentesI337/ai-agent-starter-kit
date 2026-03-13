"""Extracted budget management logic from ToolExecutionManager."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BudgetConfig:
    call_cap: int = 8
    time_cap_seconds: float = 90.0

    @classmethod
    def from_settings(cls, settings: Any) -> BudgetConfig:
        return cls(
            call_cap=getattr(settings, "run_tool_call_cap", 8),
            time_cap_seconds=getattr(settings, "run_tool_time_cap_seconds", 90.0),
        )


class ToolBudgetManager:
    """Tracks call count and time budget for a tool execution phase."""

    def __init__(self, config: BudgetConfig) -> None:
        self.config = config
        self._call_count = 0
        self._start_time: float | None = None

    def start(self) -> None:
        self._start_time = time.monotonic()
        self._call_count = 0

    def record_call(self) -> None:
        self._call_count += 1

    @property
    def calls_remaining(self) -> int:
        return max(0, self.config.call_cap - self._call_count)

    @property
    def total_calls(self) -> int:
        return self._call_count

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def time_remaining(self) -> float:
        return max(0.0, self.config.time_cap_seconds - self.elapsed_seconds)

    @property
    def is_exhausted(self) -> bool:
        if self._call_count >= self.config.call_cap:
            return True
        return bool(self._start_time is not None and self.elapsed_seconds >= self.config.time_cap_seconds)

    def exhaustion_reason(self) -> str | None:
        if self._call_count >= self.config.call_cap:
            return f"call_cap_reached ({self._call_count}/{self.config.call_cap})"
        if self._start_time is not None and self.elapsed_seconds >= self.config.time_cap_seconds:
            return f"time_cap_reached ({self.elapsed_seconds:.1f}s/{self.config.time_cap_seconds}s)"
        return None
