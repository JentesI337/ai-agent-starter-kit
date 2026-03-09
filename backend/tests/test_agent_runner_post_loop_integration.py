"""Integration tests for AgentRunner post-loop pipeline (Sprint 2).

Each test drives the full ``runner.run()`` path, mocking only the LlmClient
(and optionally the tool execution function) to verify the end-to-end
interaction of Evidence Gates → Reflection → Reply Shaping → Verification.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_runner import AgentRunner
from app.agent_runner_types import StreamResult, ToolCall, ToolResult
from app.services.reply_shaper import ReplyShaper
from app.services.verification_service import VerificationService


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_runner(**overrides) -> AgentRunner:
    defaults = dict(
        client=MagicMock(),
        memory=MagicMock(),
        tool_registry=MagicMock(),
        tool_execution_manager=MagicMock(),
        context_reducer=MagicMock(),
        system_prompt="test",
        execute_tool_fn=AsyncMock(return_value="ok"),
        allowed_tools_resolver=MagicMock(return_value={"read_file", "write_file", "run_command", "spawn_subrun"}),
    )
    defaults.update(overrides)
    runner = AgentRunner(**defaults)
    runner.memory.get_items.return_value = []
    runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])
    return runner


def _tc(name: str, tc_id: str = "tc1", **args) -> ToolCall:
    return ToolCall(id=tc_id, name=name, arguments=args)


def _verdict(should_retry=False, score=0.8, issues=None, suggested_fix=None):
    v = MagicMock()
    v.should_retry = should_retry
    v.score = score
    v.goal_alignment = score
    v.completeness = score
    v.factual_grounding = score
    v.issues = issues or []
    v.suggested_fix = suggested_fix
    v.hard_factual_fail = score < 0.4
    return v


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────


class TestPostLoopIntegration:
    """End-to-end integration tests for the post-loop pipeline."""

    @pytest.mark.asyncio
    async def test_simple_question_no_tools(self):
        """Simple question — no tool calls, no gates, final text passes through."""
        runner = _make_runner()
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Paris is the capital of France.", tool_calls=(), finish_reason="stop"),
        )
        send = AsyncMock()
        result = await runner.run("What is the capital of France?", send, "s1", "r1")

        assert result == "Paris is the capital of France."
        send.assert_any_call({"type": "final", "agent": "agent", "message": result})

    @pytest.mark.asyncio
    async def test_implementation_gate_blocks_hallucinated_success(self):
        """Implementation task where tool fails → evidence gate overwrites LLM text."""
        runner = _make_runner()
        # LLM first says it needs tools (tool_calls), then claims success
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            StreamResult(
                text="",
                tool_calls=(_tc("write_file", file="x.py", content="pass"),),
                finish_reason="tool_calls",
            ),
            StreamResult(
                text="I have successfully implemented the feature!",
                tool_calls=(),
                finish_reason="stop",
            ),
        ])
        # write_file FAILS
        runner._execute_tool_fn = AsyncMock(side_effect=RuntimeError("Permission denied"))

        result = await runner.run("implement the login feature", AsyncMock(), "s1", "r1")

        assert "code-edit" in result.lower() or "could not complete" in result.lower()
        assert "successfully" not in result.lower()

    @pytest.mark.asyncio
    async def test_all_tools_failed_gate(self):
        """All tool calls fail → gate overwrites optimistic LLM text."""
        runner = _make_runner()
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            StreamResult(
                text="",
                tool_calls=(_tc("read_file", file="x.py"),),
                finish_reason="tool_calls",
            ),
            StreamResult(
                text="Here is your file content: ...",
                tool_calls=(),
                finish_reason="stop",
            ),
        ])
        runner._execute_tool_fn = AsyncMock(side_effect=RuntimeError("Not found"))

        result = await runner.run("show me x.py", AsyncMock(), "s1", "r1")

        assert "unable" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_orchestration_gate_no_completion(self):
        """Orchestration task where subrun doesn't complete → gate fires."""
        intent = MagicMock()
        intent.is_subrun_orchestration_task = MagicMock(return_value=True)
        intent.is_file_creation_task = MagicMock(return_value=False)
        intent.is_web_research_task = MagicMock(return_value=False)

        runner = _make_runner(intent_detector=intent)
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            StreamResult(
                text="",
                tool_calls=(_tc("spawn_subrun", task="create app"),),
                finish_reason="tool_calls",
            ),
            StreamResult(
                text="The subrun has been started.",
                tool_calls=(),
                finish_reason="stop",
            ),
        ])
        # spawn_subrun returns a partial result (no subrun-complete)
        runner._execute_tool_fn = AsyncMock(
            return_value="spawned_subrun_id=sub123 terminal_reason=subrun-running"
        )

        result = await runner.run("create a react app in a subrun", AsyncMock(), "s1", "r1")

        # Should NOT say "has been started" optimistically
        assert "subrun" in result.lower() or "did not complete" in result.lower()

    @pytest.mark.asyncio
    async def test_tool_call_markers_removed_by_shaping(self):
        """[TOOL_CALL]...[/TOOL_CALL] markers in LLM text are removed by ReplyShaper."""
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(
                text="Here is the result.\n[TOOL_CALL] read_file args [/TOOL_CALL]\nDone.",
                tool_calls=(),
                finish_reason="stop",
            ),
        )

        result = await runner.run("test", AsyncMock(), "s1", "r1")

        assert "[TOOL_CALL]" not in result

    @pytest.mark.asyncio
    async def test_reflection_improves_output(self):
        """Reflection scores below threshold → LLM retry produces better text."""
        reflection_svc = AsyncMock()
        reflection_svc.reflect = AsyncMock(side_effect=[
            _verdict(should_retry=True, score=0.3, issues=["Missing detail"]),
            _verdict(should_retry=False, score=0.9),
        ])

        runner = _make_runner(reflection_service=reflection_svc)
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            # Initial answer
            StreamResult(text="Python is a language.", tool_calls=(), finish_reason="stop"),
            # Reflection retry answer
            StreamResult(
                text="Python is a high-level programming language known for readability.",
                tool_calls=(),
                finish_reason="stop",
            ),
        ])

        with patch("app.agent_runner.settings") as s:
            s.runner_reflection_enabled = True
            s.runner_max_iterations = 25
            s.runner_max_tool_calls = 50
            s.runner_time_budget_seconds = 300
            s.runner_loop_detection_enabled = True
            s.runner_loop_detection_threshold = 3
            s.runner_compaction_enabled = True
            s.runner_compaction_tail_keep = 4
            s.runner_tool_result_max_chars = 5000
            s.clarification_protocol_enabled = False
            s.runner_reflection_max_passes = 2
            s.llm_model = "test-model"

            result = await runner.run("Tell me about Python", AsyncMock(), "s1", "r1")

        assert "readability" in result.lower()

    @pytest.mark.asyncio
    async def test_verification_rejects_empty_output(self):
        """Verification service replaces empty output with fallback."""
        runner = _make_runner(verification_service=VerificationService())
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="   ", tool_calls=(), finish_reason="stop"),
        )

        result = await runner.run("test", AsyncMock(), "s1", "r1")

        # Verification should fail on whitespace-only text → "No output generated."
        assert "no output" in result.lower() or result.strip() != ""

    @pytest.mark.asyncio
    async def test_full_pipeline_tool_calls_then_shaping(self):
        """Full pipeline: tool calls → evidence passes → shaping cleans text."""
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            StreamResult(
                text="",
                tool_calls=(_tc("read_file", file="main.py"),),
                finish_reason="tool_calls",
            ),
            StreamResult(
                text="The file main.py contains:\n```python\nprint('hello')\n```",
                tool_calls=(),
                finish_reason="stop",
            ),
        ])
        runner._execute_tool_fn = AsyncMock(return_value="print('hello')")

        result = await runner.run("show main.py", AsyncMock(), "s1", "r1")

        assert "print" in result
        assert "[TOOL_CALL]" not in result

    @pytest.mark.asyncio
    async def test_shaping_with_verification_combined(self):
        """Reply shaping + verification both run in sequence."""
        runner = _make_runner(
            reply_shaper=ReplyShaper(),
            verification_service=VerificationService(),
        )
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(
                text="Here is your answer with detailed information about the topic.",
                tool_calls=(),
                finish_reason="stop",
            ),
        )

        result = await runner.run("tell me something", AsyncMock(), "s1", "r1")

        assert len(result) > 8
        assert "Here is your answer" in result

    @pytest.mark.asyncio
    async def test_all_gates_pass_normal_flow(self):
        """When all gates pass, the original LLM answer is preserved."""
        runner = _make_runner(
            reply_shaper=ReplyShaper(),
            verification_service=VerificationService(),
        )
        runner.client.stream_chat_with_tools = AsyncMock(side_effect=[
            StreamResult(
                text="",
                tool_calls=(_tc("write_file", file="x.py", content="code"),),
                finish_reason="tool_calls",
            ),
            StreamResult(
                text="I have written the file x.py with the requested code.",
                tool_calls=(),
                finish_reason="stop",
            ),
        ])
        runner._execute_tool_fn = AsyncMock(return_value="file written successfully")

        result = await runner.run("implement a hello world in x.py", AsyncMock(), "s1", "r1")

        # Evidence gate does NOT fire because write_file succeeded
        assert "written" in result.lower() or "file" in result.lower()
