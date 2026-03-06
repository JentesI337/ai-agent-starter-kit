"""Unit tests for ToolTelemetry + ToolSpan."""

from __future__ import annotations

import time

import pytest

from app.services.tool_telemetry import ToolSpan, ToolTelemetry

# ── ToolSpan unit tests ──────────────────────────────────────────────

class TestToolSpan:
    def test_initial_state(self):
        span = ToolSpan(tool="read_file", call_id="c-1")
        assert span.is_open
        assert span.status == "pending"
        assert span.duration_ms == 0.0

    def test_close_sets_end(self):
        span = ToolSpan(tool="read_file", call_id="c-2")
        span.close(status="ok", result_chars=123)
        assert not span.is_open
        assert span.status == "ok"
        assert span.result_chars == 123
        assert span.duration_ms >= 0.0

    def test_to_dict(self):
        span = ToolSpan(tool="run_command", call_id="c-3")
        span.close(status="error", error_category="transient")
        d = span.to_dict()
        assert d["tool"] == "run_command"
        assert d["call_id"] == "c-3"
        assert d["status"] == "error"
        assert d["error_category"] == "transient"
        assert isinstance(d["duration_ms"], float)

    def test_close_with_retry(self):
        span = ToolSpan(tool="web_fetch", call_id="c-4")
        span.close(status="ok", retried=True, outcome_status="verified")
        assert span.retried is True
        assert span.outcome_status == "verified"


# ── ToolTelemetry integration tests ──────────────────────────────────

class TestToolTelemetry:
    @pytest.fixture
    def tel(self):
        return ToolTelemetry()

    def test_start_end_span(self, tel: ToolTelemetry):
        span = tel.start_span(tool="read_file", call_id="c-10")
        tel.end_span(span, status="ok", result_chars=500)
        stats = tel.get_tool_stats()
        assert "read_file" in stats
        assert stats["read_file"]["calls"] == 1
        assert stats["read_file"]["ok"] == 1

    def test_error_tracking(self, tel: ToolTelemetry):
        span = tel.start_span(tool="run_command", call_id="c-11")
        tel.end_span(span, status="error", error_category="permission")
        stats = tel.get_tool_stats()
        assert stats["run_command"]["errors"] == 1
        assert stats["run_command"]["error_rate"] == 1.0

    def test_retry_tracking(self, tel: ToolTelemetry):
        span = tel.start_span(tool="web_fetch", call_id="c-12")
        tel.end_span(span, status="ok", retried=True)
        stats = tel.get_tool_stats()
        assert stats["web_fetch"]["retries"] == 1

    def test_suspicious_tracking(self, tel: ToolTelemetry):
        span = tel.start_span(tool="write_file", call_id="c-13")
        tel.end_span(span, status="ok", outcome_status="suspicious")
        stats = tel.get_tool_stats()
        assert stats["write_file"]["suspicious"] == 1

    def test_session_trace(self, tel: ToolTelemetry):
        for i in range(5):
            s = tel.start_span(tool="read_file", call_id=f"c-{i}")
            tel.end_span(s, status="ok")
        trace = tel.get_session_trace()
        assert len(trace) == 5
        assert trace[0]["call_id"] == "c-0"

    def test_session_trace_last_n(self, tel: ToolTelemetry):
        for i in range(5):
            s = tel.start_span(tool="read_file", call_id=f"c-{i}")
            tel.end_span(s, status="ok")
        trace = tel.get_session_trace(last_n=2)
        assert len(trace) == 2
        assert trace[0]["call_id"] == "c-3"

    def test_summary(self, tel: ToolTelemetry):
        s1 = tel.start_span(tool="read_file", call_id="c-a")
        tel.end_span(s1, status="ok")
        s2 = tel.start_span(tool="run_command", call_id="c-b")
        tel.end_span(s2, status="error", error_category="crash")
        summary = tel.get_summary()
        assert summary["total_calls"] == 2
        assert summary["total_errors"] == 1
        assert summary["tools_seen"] == 2
        assert summary["error_rate"] == 0.5

    def test_reset(self, tel: ToolTelemetry):
        s = tel.start_span(tool="read_file", call_id="c-x")
        tel.end_span(s, status="ok")
        tel.reset()
        assert tel.get_tool_stats() == {}
        assert tel.get_session_trace() == []

    def test_max_trace_eviction(self):
        tel = ToolTelemetry(max_trace_size=3)
        for i in range(5):
            s = tel.start_span(tool="read_file", call_id=f"c-{i}")
            tel.end_span(s, status="ok")
        trace = tel.get_session_trace()
        assert len(trace) == 3
        assert trace[0]["call_id"] == "c-2"  # oldest 2 evicted

    def test_args_keys_captured(self, tel: ToolTelemetry):
        span = tel.start_span(tool="write_file", call_id="c-k", args={"path": "/tmp/x", "content": "hi"})
        assert span.args_keys == ["content", "path"]

    def test_multiple_tools_stats(self, tel: ToolTelemetry):
        for tool in ("read_file", "read_file", "write_file"):
            s = tel.start_span(tool=tool, call_id=f"c-{tool}")
            tel.end_span(s, status="ok")
        stats = tel.get_tool_stats()
        assert stats["read_file"]["calls"] == 2
        assert stats["write_file"]["calls"] == 1

    def test_avg_ms_calculation(self, tel: ToolTelemetry):
        s = tel.start_span(tool="read_file", call_id="c-avg")
        time.sleep(0.05)  # ≥50ms — generous for CI / Windows
        tel.end_span(s, status="ok")
        stats = tel.get_tool_stats()
        assert stats["read_file"]["avg_ms"] >= 1.0  # very generous tolerance
