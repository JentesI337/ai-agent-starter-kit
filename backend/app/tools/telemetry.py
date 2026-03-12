"""L2.1  Lightweight tool-call telemetry — no external dependencies.

Provides structured tracing of tool calls (spans) with latency,
outcome, retry info, and error categorisation.  All data stays
in-process; the REST endpoint (L2.6) exposes aggregated stats.

Thread-safety: guarded by a ``threading.Lock`` so hook callbacks
from different event-loop tasks cannot corrupt state.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpan:
    """One tool invocation — created at call start, closed on finish."""

    tool: str
    call_id: str
    start_ns: int = field(default_factory=time.monotonic_ns)
    end_ns: int | None = None
    status: str = "pending"  # pending → ok | error
    error_category: str | None = None
    retried: bool = False
    outcome_status: str | None = None  # verified | suspicious | failed
    args_keys: list[str] = field(default_factory=list)
    result_chars: int = 0

    # -- derived -----------------------------------------------------------

    @property
    def duration_ms(self) -> float:
        if self.end_ns is None:
            return 0.0
        return (self.end_ns - self.start_ns) / 1_000_000

    @property
    def is_open(self) -> bool:
        return self.end_ns is None

    def close(
        self,
        *,
        status: str = "ok",
        error_category: str | None = None,
        retried: bool = False,
        outcome_status: str | None = None,
        result_chars: int = 0,
    ) -> None:
        self.end_ns = time.monotonic_ns()
        self.status = status
        self.error_category = error_category
        self.retried = retried
        self.outcome_status = outcome_status
        self.result_chars = result_chars

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "call_id": self.call_id,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "error_category": self.error_category,
            "retried": self.retried,
            "outcome_status": self.outcome_status,
            "result_chars": self.result_chars,
        }


@dataclass
class _ToolStats:
    """Aggregated stats for one tool."""

    calls: int = 0
    ok: int = 0
    errors: int = 0
    retries: int = 0
    total_ms: float = 0.0
    suspicious: int = 0

    @property
    def avg_ms(self) -> float:
        return round(self.total_ms / self.calls, 2) if self.calls else 0.0

    @property
    def error_rate(self) -> float:
        return round(self.errors / self.calls, 4) if self.calls else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "ok": self.ok,
            "errors": self.errors,
            "retries": self.retries,
            "avg_ms": self.avg_ms,
            "error_rate": self.error_rate,
            "suspicious": self.suspicious,
        }


class ToolTelemetry:
    """In-process telemetry collector for tool calls.

    Usage::

        telemetry = ToolTelemetry()

        span = telemetry.start_span(tool="run_command", call_id="c-1")
        # … execute tool …
        telemetry.end_span(span, status="ok", outcome_status="verified")

        stats = telemetry.get_tool_stats()   # per-tool aggregates
        trace = telemetry.get_session_trace() # ordered span list
    """

    def __init__(self, *, max_trace_size: int = 2000) -> None:
        self._lock = threading.Lock()
        self._spans: list[ToolSpan] = []
        self._stats: dict[str, _ToolStats] = defaultdict(_ToolStats)
        self._max_trace_size = max_trace_size

    # ── span lifecycle ────────────────────────────────────────────────

    def start_span(self, *, tool: str, call_id: str, args: dict | None = None) -> ToolSpan:
        """Create and register a new span.  Returns it for later ``end_span``."""
        span = ToolSpan(
            tool=tool,
            call_id=call_id,
            args_keys=sorted(args.keys()) if args else [],
        )
        with self._lock:
            self._spans.append(span)
            # Evict oldest spans when trace exceeds limit
            if len(self._spans) > self._max_trace_size:
                self._spans = self._spans[-self._max_trace_size:]
        return span

    def end_span(
        self,
        span: ToolSpan,
        *,
        status: str = "ok",
        error_category: str | None = None,
        retried: bool = False,
        outcome_status: str | None = None,
        result_chars: int = 0,
    ) -> None:
        """Close *span* and update aggregated stats."""
        with self._lock:
            span.close(
                status=status,
                error_category=error_category,
                retried=retried,
                outcome_status=outcome_status,
                result_chars=result_chars,
            )
            st = self._stats[span.tool]
            st.calls += 1
            st.total_ms += span.duration_ms
            if status == "ok":
                st.ok += 1
            else:
                st.errors += 1
            if retried:
                st.retries += 1
            if outcome_status == "suspicious":
                st.suspicious += 1

    # ── queries ───────────────────────────────────────────────────────

    def get_tool_stats(self) -> dict[str, dict[str, Any]]:
        """Return per-tool aggregate stats."""
        with self._lock:
            return {name: s.to_dict() for name, s in sorted(self._stats.items())}

    def get_session_trace(self, *, last_n: int | None = None) -> list[dict[str, Any]]:
        """Return the most recent *last_n* spans (all if ``None``)."""
        with self._lock:
            spans = self._spans if last_n is None else self._spans[-last_n:]
            return [s.to_dict() for s in spans]

    def get_summary(self) -> dict[str, Any]:
        """Top-level summary numbers."""
        with self._lock:
            total = sum(s.calls for s in self._stats.values())
            errors = sum(s.errors for s in self._stats.values())
            retries = sum(s.retries for s in self._stats.values())
            return {
                "total_calls": total,
                "total_errors": errors,
                "total_retries": retries,
                "error_rate": round(errors / total, 4) if total else 0.0,
                "tools_seen": len(self._stats),
            }

    def reset(self) -> None:
        """Clear all telemetry data (useful for tests)."""
        with self._lock:
            self._spans.clear()
            self._stats.clear()
