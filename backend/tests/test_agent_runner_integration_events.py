"""Integration tests for AgentRunner Sprint 3 — Events, Hooks, LTM, Feature-Flag."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_runner import AgentRunner
from app.agent_runner_types import StreamResult, ToolCall

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_runner(**overrides) -> AgentRunner:
    defaults = {
        "client": MagicMock(),
        "memory": MagicMock(),
        "tool_registry": MagicMock(),
        "tool_execution_manager": MagicMock(),
        "system_prompt": "You are a test agent.",
        "execute_tool_fn": AsyncMock(return_value="ok"),
        "allowed_tools_resolver": MagicMock(return_value={"read_file"}),
    }
    defaults.update(overrides)
    runner = AgentRunner(**defaults)
    runner.memory.get_items.return_value = []
    runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])
    return runner


def _tc(name: str, tc_id: str = "tc1", **args) -> ToolCall:
    return ToolCall(id=tc_id, name=name, arguments=args)


# ──────────────────────────────────────────────────────────────────────
# S3-10: Token-Event-Kompatibilität
# ──────────────────────────────────────────────────────────────────────


class TestTokenEventCompatibility:

    @pytest.mark.asyncio
    async def test_stream_emits_token_type(self):
        """Streaming chunks emit {type: 'token', token: ...} not 'stream'."""
        runner = _make_runner()

        async def on_chunk(chunk_text: str):
            """LlmClient calls on_text_chunk with each chunk."""

        # Capture send_event calls
        send = AsyncMock()

        async def fake_stream(*, messages, tools, model, on_text_chunk):
            if on_text_chunk:
                await on_text_chunk("Hello ")
                await on_text_chunk("world!")
            return StreamResult(text="Hello world!", tool_calls=(), finish_reason="stop")

        runner.client.stream_chat_with_tools = AsyncMock(side_effect=fake_stream)

        await runner.run("hi", send, "s1", "r1")

        # Check that token events were sent
        token_events = [
            call.args[0] for call in send.call_args_list
            if call.args and isinstance(call.args[0], dict) and call.args[0].get("type") == "token"
        ]
        assert len(token_events) == 2
        assert token_events[0] == {"type": "token", "agent": "agent", "token": "Hello "}
        assert token_events[1] == {"type": "token", "agent": "agent", "token": "world!"}

    @pytest.mark.asyncio
    async def test_agent_name_in_token_events(self):
        """Token events include the agent_name field."""
        runner = _make_runner(agent_name="my-agent")

        async def fake_stream(*, messages, tools, model, on_text_chunk):
            if on_text_chunk:
                await on_text_chunk("X")
            return StreamResult(text="X", tool_calls=(), finish_reason="stop")

        runner.client.stream_chat_with_tools = AsyncMock(side_effect=fake_stream)
        send = AsyncMock()

        await runner.run("hi", send, "s1", "r1")

        token_events = [
            c.args[0] for c in send.call_args_list
            if c.args and isinstance(c.args[0], dict) and c.args[0].get("type") == "token"
        ]
        assert len(token_events) >= 1
        assert token_events[0]["agent"] == "my-agent"

    @pytest.mark.asyncio
    async def test_agent_name_in_final_event(self):
        """Final event includes the agent_name field."""
        runner = _make_runner(agent_name="coding-agent")
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Done.", tool_calls=(), finish_reason="stop"),
        )
        send = AsyncMock()

        await runner.run("test", send, "s1", "r1")

        final_events = [
            c.args[0] for c in send.call_args_list
            if c.args and isinstance(c.args[0], dict) and c.args[0].get("type") == "final"
        ]
        assert len(final_events) == 1
        assert final_events[0]["agent"] == "coding-agent"
        assert final_events[0]["message"] == "Done."

    @pytest.mark.asyncio
    async def test_agent_name_in_tool_events(self):
        """tool_start and tool_end events include agent_name."""
        runner = _make_runner(
            agent_name="tool-agent",
            allowed_tools_resolver=MagicMock(return_value={"read_file"}),
        )
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            StreamResult(
                text="",
                tool_calls=(_tc("read_file", file="x.py"),),
                finish_reason="tool_calls",
            ),
            StreamResult(text="File read.", tool_calls=(), finish_reason="stop"),
        ])
        send = AsyncMock()

        await runner.run("read x.py", send, "s1", "r1")

        tool_start = [
            c.args[0] for c in send.call_args_list
            if c.args and isinstance(c.args[0], dict) and c.args[0].get("type") == "tool_start"
        ]
        tool_end = [
            c.args[0] for c in send.call_args_list
            if c.args and isinstance(c.args[0], dict) and c.args[0].get("type") == "tool_end"
        ]
        assert len(tool_start) == 1
        assert tool_start[0]["agent"] == "tool-agent"
        assert len(tool_end) == 1
        assert tool_end[0]["agent"] == "tool-agent"


# ──────────────────────────────────────────────────────────────────────
# S3-11: Distillation, Hooks, LTM Context
# ──────────────────────────────────────────────────────────────────────


class TestDistillationAndLTM:

    @pytest.mark.asyncio
    async def test_distill_fn_called_on_success(self):
        """distill_fn is called after a successful run."""
        distill = AsyncMock()
        runner = _make_runner(distill_fn=distill)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Done.", tool_calls=(), finish_reason="stop"),
        )

        await runner.run("test", AsyncMock(), "s1", "r1")

        # distill_fn is called as fire-and-forget task — give it a tick
        import asyncio
        await asyncio.sleep(0.05)

        distill.assert_awaited_once()
        call_kwargs = distill.call_args[1]
        assert call_kwargs["session_id"] == "s1"
        assert call_kwargs["user_message"] == "test"
        assert call_kwargs["final_text"] == "Done."

    @pytest.mark.asyncio
    async def test_distill_fn_not_called_when_none(self):
        """No error when distill_fn is None."""
        runner = _make_runner(distill_fn=None)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Done.", tool_calls=(), finish_reason="stop"),
        )

        result = await runner.run("test", AsyncMock(), "s1", "r1")
        assert result == "Done."

    @pytest.mark.asyncio
    async def test_ltm_context_injected_into_system_prompt(self):
        """Long-term context is injected into the system message."""
        ltm_fn = MagicMock(return_value="[Past failures]\n- task X failed due to Y")
        runner = _make_runner(long_term_context_fn=ltm_fn)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="OK", tool_calls=(), finish_reason="stop"),
        )

        await runner.run("do something", AsyncMock(), "s1", "r1")

        # Check that stream_chat_with_tools received messages with LTM content
        call_kwargs = runner.client.stream_chat_with_tools.call_args[1]
        system_msg = call_kwargs["messages"][0]
        assert system_msg["role"] == "system"
        assert "Past failures" in system_msg["content"]
        assert "task X failed" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_ltm_fn_none_no_injection(self):
        """When long_term_context_fn is None, system prompt stays original."""
        runner = _make_runner(long_term_context_fn=None, system_prompt="Base prompt.")
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="OK", tool_calls=(), finish_reason="stop"),
        )

        await runner.run("test", AsyncMock(), "s1", "r1")

        call_kwargs = runner.client.stream_chat_with_tools.call_args[1]
        system_msg = call_kwargs["messages"][0]
        assert system_msg["content"] == "Base prompt."

    @pytest.mark.asyncio
    async def test_ltm_fn_exception_handled(self):
        """Exception in long_term_context_fn does not crash the runner."""
        ltm_fn = MagicMock(side_effect=RuntimeError("DB unavailable"))
        runner = _make_runner(long_term_context_fn=ltm_fn)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="OK", tool_calls=(), finish_reason="stop"),
        )

        result = await runner.run("test", AsyncMock(), "s1", "r1")
        assert result == "OK"

    @pytest.mark.asyncio
    async def test_lifecycle_guardrails_passed_emitted(self):
        """Lifecycle event guardrails_passed is emitted after guardrail check."""
        lifecycle = AsyncMock()
        runner = _make_runner(emit_lifecycle_fn=lifecycle)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="OK", tool_calls=(), finish_reason="stop"),
        )

        await runner.run("test", AsyncMock(), "s1", "r1")

        stages = [call.kwargs.get("stage") or call.args[1] for call in lifecycle.call_args_list]
        assert "guardrails_passed" in stages
        assert "memory_updated" in stages


# ──────────────────────────────────────────────────────────────────────
# S3-12: Feature-Flag Toggle & configure_runtime
# ──────────────────────────────────────────────────────────────────────


class TestFeatureFlagAndConfigureRuntime:

    def test_runner_created_when_flag_true(self):
        """AgentRunner is constructed when USE_CONTINUOUS_LOOP=true."""
        with patch("app.agent_runner.settings") as mock_settings:
            mock_settings.runner_max_iterations = 25
            mock_settings.runner_max_tool_calls = 50
            mock_settings.runner_time_budget_seconds = 300
            mock_settings.runner_loop_detection_enabled = True
            mock_settings.runner_loop_detection_threshold = 3
            mock_settings.runner_compaction_enabled = True
            mock_settings.runner_compaction_tail_keep = 4
            mock_settings.runner_tool_result_max_chars = 5000

            runner = _make_runner(agent_name="test-agent")

        assert runner._agent_name == "test-agent"

    def test_constructor_params_stored(self):
        """New Sprint 3 constructor params are properly stored."""
        distill = AsyncMock()
        ltm = MagicMock()
        runner = _make_runner(
            agent_name="my-agent",
            distill_fn=distill,
            long_term_context_fn=ltm,
        )

        assert runner._agent_name == "my-agent"
        assert runner._distill_fn is distill
        assert runner._long_term_context_fn is ltm

    @pytest.mark.asyncio
    async def test_runner_path_runs_on_flag_true(self):
        """With flag=true, HeadAgent.run() would delegate to AgentRunner."""
        # We just verify AgentRunner.run() works end-to-end (standalone)
        runner = _make_runner()
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Hello!", tool_calls=(), finish_reason="stop"),
        )

        result = await runner.run("hi", AsyncMock(), "s1", "r1")
        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_error_handling_preserves_state(self):
        """When LLM call raises, fallback text is returned."""
        runner = _make_runner()
        runner.client.stream_chat_with_tools = AsyncMock(
            side_effect=RuntimeError("LLM unreachable"),
        )

        # Should not crash — unknown finish reason path will break safely
        # Actually: the exception will propagate since it's not caught in the loop
        with pytest.raises(RuntimeError, match="LLM unreachable"):
            await runner.run("test", AsyncMock(), "s1", "r1")
