"""Unit tests for AgentRunner — continuous streaming tool loop."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.runner import AgentRunner, build_unified_system_prompt
from app.agent.runner_types import LoopState, StreamResult, ToolCall

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_runner(**overrides) -> AgentRunner:
    """Create an AgentRunner with all required dependencies mocked."""
    defaults = {
        "client": MagicMock(),
        "memory": MagicMock(),
        "tool_registry": MagicMock(),
        "tool_execution_manager": MagicMock(),
        "system_prompt": "You are a test agent.",
        "execute_tool_fn": AsyncMock(return_value="tool result"),
        "allowed_tools_resolver": MagicMock(return_value={"read_file", "run_command"}),
    }
    defaults.update(overrides)
    return AgentRunner(**defaults)


def _stop_result(text: str = "Final answer") -> StreamResult:
    return StreamResult(text=text, tool_calls=(), finish_reason="stop")


def _tool_calls_result(*calls: tuple[str, str, dict]) -> StreamResult:
    """Build a StreamResult with tool_calls from (id, name, args) tuples."""
    tcs = tuple(ToolCall(id=c[0], name=c[1], arguments=c[2]) for c in calls)
    return StreamResult(text="", tool_calls=tcs, finish_reason="tool_calls")


# ──────────────────────────────────────────────────────────────────────
# build_unified_system_prompt
# ──────────────────────────────────────────────────────────────────────


class TestBuildUnifiedSystemPrompt:
    def test_minimal(self):
        prompt = build_unified_system_prompt(
            role="test-agent",
            tool_hints="hints",
            final_instructions="answer rules",
        )
        assert "test-agent" in prompt
        assert "hints" in prompt
        assert "answer rules" in prompt

    def test_empty_optional_sections(self):
        prompt = build_unified_system_prompt(
            role="test",
            tool_hints="",
            final_instructions="",
        )
        assert "test" in prompt
        assert "Tool guidelines" not in prompt
        assert "Answer guidelines" not in prompt

    def test_includes_platform_and_skills(self):
        prompt = build_unified_system_prompt(
            role="r",
            tool_hints="t",
            final_instructions="f",
            platform_summary="Linux x86_64",
        )
        assert "Linux x86_64" in prompt

    def test_includes_guardrails(self):
        prompt = build_unified_system_prompt(
            role="r",
            tool_hints="t",
            final_instructions="f",
            guardrails="Never access /etc/shadow",
        )
        assert "Never access /etc/shadow" in prompt
        assert "Safety rules" in prompt


# ──────────────────────────────────────────────────────────────────────
# AgentRunner._build_initial_messages
# ──────────────────────────────────────────────────────────────────────


class TestBuildInitialMessages:
    def test_system_plus_user(self):
        runner = _make_runner()
        runner.memory.get_items.return_value = []
        msgs = runner._build_initial_messages(memory_items=[], user_message="Hello")
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "Hello"

    def test_includes_history(self):
        runner = _make_runner()
        item1 = MagicMock(role="user", content="first")
        item2 = MagicMock(role="assistant", content="reply")
        msgs = runner._build_initial_messages(
            memory_items=[item1, item2], user_message="second"
        )
        # system + 2 history + user
        assert len(msgs) == 4
        assert msgs[1]["content"] == "first"
        assert msgs[2]["content"] == "reply"
        assert msgs[3]["content"] == "second"

    def test_dedupes_trailing_user_message(self):
        runner = _make_runner()
        item = MagicMock(role="user", content="Hello")
        msgs = runner._build_initial_messages(
            memory_items=[item], user_message="Hello"
        )
        # Should not duplicate: system + user(Hello) only
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 1


# ──────────────────────────────────────────────────────────────────────
# AgentRunner._detect_tool_loop
# ──────────────────────────────────────────────────────────────────────


class TestDetectToolLoop:
    def test_no_loop_below_threshold(self):
        runner = _make_runner()
        state = LoopState()
        tc = (ToolCall(id="c1", name="read_file", arguments={"path": "a"}),)
        # Call twice (threshold=3 by default)
        assert runner._detect_tool_loop(state, tc) is False
        assert runner._detect_tool_loop(state, tc) is False

    def test_detects_identical_repeat(self):
        runner = _make_runner()
        state = LoopState()
        tc = (ToolCall(id="c1", name="read_file", arguments={"path": "a"}),)
        runner._detect_tool_loop(state, tc)
        runner._detect_tool_loop(state, tc)
        assert runner._detect_tool_loop(state, tc) is True

    def test_detects_ping_pong(self):
        runner = _make_runner()
        state = LoopState()
        tc_a = (ToolCall(id="c1", name="read_file", arguments={"path": "a"}),)
        tc_b = (ToolCall(id="c2", name="read_file", arguments={"path": "b"}),)
        runner._detect_tool_loop(state, tc_a)
        runner._detect_tool_loop(state, tc_b)
        runner._detect_tool_loop(state, tc_a)
        assert runner._detect_tool_loop(state, tc_b) is True

    def test_no_false_positive_different_calls(self):
        runner = _make_runner()
        state = LoopState()
        for i in range(5):
            tc = (ToolCall(id=f"c{i}", name="read_file", arguments={"path": f"file{i}"}),)
            assert runner._detect_tool_loop(state, tc) is False


# ──────────────────────────────────────────────────────────────────────
# AgentRunner._compact_messages
# ──────────────────────────────────────────────────────────────────────


class TestCompactMessages:
    def test_short_messages_unchanged(self):
        runner = _make_runner()
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = runner._compact_messages(msgs)
        assert result == msgs

    def test_truncates_old_tool_results(self):
        runner = _make_runner()
        long_content = "x" * 1000
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "tool_call_id": "c1", "content": long_content},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
        ]
        result = runner._compact_messages(msgs)
        # Tool result in the old section should be truncated
        tool_msg = next(m for m in result if m["role"] == "tool")
        assert len(tool_msg["content"]) < len(long_content)
        assert "(truncated)" in tool_msg["content"]


# ──────────────────────────────────────────────────────────────────────
# AgentRunner.run — full loop
# ──────────────────────────────────────────────────────────────────────


class TestAgentRunnerRun:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """LLM returns text immediately (no tools) → single iteration."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(memory=memory)
        runner.client.stream_chat_with_tools = AsyncMock(return_value=_stop_result("Hello!"))
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])

        result = await runner.run(
            user_message="Hi",
            send_event=send_event,
            session_id="s1",
            request_id="r1",
        )

        assert result == "Hello!"
        send_event.assert_any_call({"type": "final", "agent": "agent", "message": "Hello!"})
        memory.add.assert_any_call("s1", "user", "Hi")
        memory.add.assert_any_call("s1", "assistant", "Hello!")

    @pytest.mark.asyncio
    async def test_single_tool_call_then_answer(self):
        """LLM uses one tool, then answers."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(memory=memory)
        runner.tool_registry.build_function_calling_tools = MagicMock(
            return_value=[{"type": "function", "function": {"name": "read_file"}}]
        )

        # Call 1: tool_calls, Call 2: stop
        runner.client.stream_chat_with_tools = AsyncMock(
            side_effect=[
                _tool_calls_result(("call_1", "read_file", {"path": "x.py"})),
                _stop_result("File content is ...")
            ]
        )

        result = await runner.run(
            user_message="Read x.py",
            send_event=send_event,
            session_id="s1",
            request_id="r1",
        )

        assert result == "File content is ..."
        assert runner._execute_tool_fn.await_count == 1

    @pytest.mark.asyncio
    async def test_blocked_tool_returns_error_message(self):
        """Tool not in allowed list → error result, loop continues."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(
            memory=memory,
            allowed_tools_resolver=MagicMock(return_value={"read_file"}),
        )
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])

        runner.client.stream_chat_with_tools = AsyncMock(
            side_effect=[
                _tool_calls_result(("c1", "delete_file", {"path": "important.py"})),
                _stop_result("I could not delete the file because the tool is not allowed."),
            ]
        )

        result = await runner.run(
            user_message="delete important.py",
            send_event=send_event,
            session_id="s1",
            request_id="r1",
        )

        assert "could not" in result.lower()
        # execute_tool_fn should NOT have been called for blocked tool
        runner._execute_tool_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_steer_interrupt_stops_loop(self):
        """Steer interrupt stops the loop mid-iteration."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(memory=memory)
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])

        # interrupt is immediately true
        result = await runner.run(
            user_message="do something",
            send_event=send_event,
            session_id="s1",
            request_id="r1",
            should_steer_interrupt=lambda: True,
        )

        assert "interrupted" in result.lower()

    @pytest.mark.asyncio
    async def test_max_iterations_triggers_fallback(self):
        """Exceeding max iterations triggers budget exhaustion fallback."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(memory=memory)
        runner._max_iterations = 2
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])

        # Always return tool_calls → triggers max iterations
        runner.client.stream_chat_with_tools = AsyncMock(
            side_effect=[
                _tool_calls_result(("c1", "read_file", {"path": "a"})),
                _tool_calls_result(("c2", "read_file", {"path": "b"})),
                # This is the budget exhaustion fallback call
                _stop_result("Partial result"),
            ]
        )

        result = await runner.run(
            user_message="lots of work",
            send_event=send_event,
            session_id="s1",
            request_id="r1",
        )

        assert result == "Partial result"
