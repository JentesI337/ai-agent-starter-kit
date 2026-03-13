"""Unit tests for agent_runner_types dataclasses."""
from __future__ import annotations

import pytest

from app.agent.runner_types import LoopState, StreamResult, ToolCall, ToolResult


class TestToolCall:
    def test_frozen(self):
        tc = ToolCall(id="call_1", name="read_file", arguments={"path": "x"})
        with pytest.raises(AttributeError):
            tc.name = "other"  # type: ignore[misc]

    def test_fields(self):
        tc = ToolCall(id="call_1", name="read_file", arguments={"path": "x"})
        assert tc.id == "call_1"
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "x"}


class TestStreamResult:
    def test_frozen(self):
        sr = StreamResult(text="hello", tool_calls=(), finish_reason="stop")
        with pytest.raises(AttributeError):
            sr.text = "other"  # type: ignore[misc]

    def test_defaults(self):
        sr = StreamResult(text="", tool_calls=(), finish_reason="stop")
        assert sr.usage == {}

    def test_with_tool_calls(self):
        tc = ToolCall(id="c1", name="run_command", arguments={"command": "ls"})
        sr = StreamResult(text="", tool_calls=(tc,), finish_reason="tool_calls")
        assert len(sr.tool_calls) == 1
        assert sr.tool_calls[0].name == "run_command"


class TestToolResult:
    def test_mutable_and_defaults(self):
        tr = ToolResult(tool_call_id="c1", tool_name="read_file", content="ok", is_error=False)
        assert tr.duration_ms == 0
        tr.duration_ms = 42
        assert tr.duration_ms == 42

    def test_error_flag(self):
        tr = ToolResult(tool_call_id="c1", tool_name="bad", content="boom", is_error=True)
        assert tr.is_error is True


class TestLoopState:
    def test_defaults(self):
        ls = LoopState()
        assert ls.iteration == 0
        assert ls.total_tool_calls == 0
        assert ls.total_tokens_used == 0
        assert ls.elapsed_seconds == 0.0
        assert ls.tool_call_history == []
        assert ls.loop_detected is False
        assert ls.budget_exhausted is False
        assert ls.steer_interrupted is False

    def test_mutable_tracking(self):
        ls = LoopState()
        ls.iteration = 5
        ls.total_tool_calls = 12
        ls.loop_detected = True
        assert ls.iteration == 5
        assert ls.total_tool_calls == 12
        assert ls.loop_detected is True

    def test_tool_call_history_independence(self):
        ls1 = LoopState()
        ls2 = LoopState()
        ls1.tool_call_history.append({"name": "foo"})
        assert ls2.tool_call_history == []
