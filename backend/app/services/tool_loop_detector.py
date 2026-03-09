"""Extracted loop-detection logic from ToolExecutionManager."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LoopDetectionConfig:
    warn_threshold: int = 2
    critical_threshold: int = 3
    circuit_breaker_threshold: int = 6
    generic_repeat_enabled: bool = True
    ping_pong_enabled: bool = True
    poll_no_progress_enabled: bool = True
    poll_no_progress_threshold: int = 3
    warning_bucket_size: int = 10

    @classmethod
    def from_settings(cls, settings: Any) -> LoopDetectionConfig:
        return cls(
            warn_threshold=getattr(settings, "tool_loop_warn_threshold", 2),
            critical_threshold=getattr(settings, "tool_loop_critical_threshold", 3),
            circuit_breaker_threshold=getattr(settings, "tool_loop_circuit_breaker_threshold", 6),
            generic_repeat_enabled=getattr(settings, "tool_loop_detector_generic_repeat_enabled", True),
            ping_pong_enabled=getattr(settings, "tool_loop_detector_ping_pong_enabled", True),
            poll_no_progress_enabled=getattr(settings, "tool_loop_detector_poll_no_progress_enabled", True),
            poll_no_progress_threshold=getattr(settings, "tool_loop_poll_no_progress_threshold", 3),
            warning_bucket_size=getattr(settings, "tool_loop_warning_bucket_size", 10),
        )


@dataclass
class LoopDetectionState:
    """Mutable state tracked during a tool execution phase."""
    call_history: list[tuple[str, str]] = field(default_factory=list)  # (tool_name, args_fingerprint)
    consecutive_same: int = 0
    warnings_issued: int = 0
    loop_detected: bool = False
    circuit_broken: bool = False


class ToolLoopDetector:
    """Detects repetitive tool call patterns (generic-repeat, ping-pong, poll-no-progress)."""

    def __init__(self, config: LoopDetectionConfig) -> None:
        self.config = config

    def check(self, state: LoopDetectionState, tool_name: str, args_fingerprint: str) -> str | None:
        """Check for loop patterns. Returns warning message or None."""
        state.call_history.append((tool_name, args_fingerprint))

        severity = None

        # Generic repeat detection
        if self.config.generic_repeat_enabled:
            severity = self._check_generic_repeat(state, tool_name, args_fingerprint)

        # Ping-pong detection
        if severity is None and self.config.ping_pong_enabled:
            severity = self._check_ping_pong(state)

        # Poll-no-progress detection
        if severity is None and self.config.poll_no_progress_enabled:
            severity = self._check_poll_no_progress(state)

        if severity:
            state.warnings_issued += 1
            if state.warnings_issued >= self.config.circuit_breaker_threshold:
                state.circuit_broken = True
                state.loop_detected = True
            elif state.warnings_issued >= self.config.critical_threshold:
                state.loop_detected = True

        return severity

    def _check_generic_repeat(self, state: LoopDetectionState, tool_name: str, args_fp: str) -> str | None:
        if len(state.call_history) < 2:
            return None
        prev_name, prev_fp = state.call_history[-2]
        if tool_name == prev_name and args_fp == prev_fp:
            state.consecutive_same += 1
            if state.consecutive_same >= self.config.warn_threshold:
                return f"generic_repeat: {tool_name} called {state.consecutive_same + 1} times with same args"
        else:
            state.consecutive_same = 0
        return None

    def _check_ping_pong(self, state: LoopDetectionState) -> str | None:
        h = state.call_history
        if len(h) < 4:
            return None
        if h[-1][0] == h[-3][0] and h[-2][0] == h[-4][0] and h[-1][0] != h[-2][0]:
            return f"ping_pong: alternating between {h[-1][0]} and {h[-2][0]}"
        return None

    def _check_poll_no_progress(self, state: LoopDetectionState) -> str | None:
        h = state.call_history
        threshold = self.config.poll_no_progress_threshold
        if len(h) < threshold:
            return None
        recent = h[-threshold:]
        names = {name for name, _ in recent}
        fingerprints = {fp for _, fp in recent}
        if len(names) == 1 and len(fingerprints) <= 2:
            return f"poll_no_progress: {next(iter(names))} repeated {threshold} times with no progress"
        return None
