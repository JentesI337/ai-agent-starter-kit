"""Tests for reasoning quality improvements: planning, smart summarization, reflection retry."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import AgentRunner
from app.agent.runner_types import PlanStep, PlanTracker, StreamResult, ToolCall, ToolResult

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
        "execute_tool_fn": AsyncMock(return_value="tool result"),
        "allowed_tools_resolver": MagicMock(return_value={"read_file", "run_command"}),
    }
    defaults.update(overrides)
    return AgentRunner(**defaults)


def _stop_result(text: str = "Final answer") -> StreamResult:
    return StreamResult(text=text, tool_calls=(), finish_reason="stop")


def _tool_calls_result(*calls: tuple[str, str, dict]) -> StreamResult:
    tcs = tuple(ToolCall(id=c[0], name=c[1], arguments=c[2]) for c in calls)
    return StreamResult(text="", tool_calls=tcs, finish_reason="tool_calls")


# ──────────────────────────────────────────────────────────────────────
# _needs_planning
# ──────────────────────────────────────────────────────────────────────


class TestNeedsPlanning:
    def test_short_message_false(self):
        runner = _make_runner()
        assert runner._needs_planning("Hello") is False

    def test_simple_question_false(self):
        runner = _make_runner()
        assert runner._needs_planning("What is 2+2?") is False

    def test_complex_message_true(self):
        runner = _make_runner()
        msg = (
            "Please implement a new authentication module. "
            "First, refactor the existing user model to support OAuth. "
            "Then configure the middleware to validate tokens. "
            "Finally, migrate the database schema."
        )
        assert runner._needs_planning(msg) is True

    def test_bulleted_list_with_keywords(self):
        runner = _make_runner()
        msg = (
            "I need you to:\n"
            "- implement user registration\n"
            "- configure email verification\n"
            "- deploy to staging"
        )
        assert runner._needs_planning(msg) is True

    def test_empty_message_false(self):
        runner = _make_runner()
        assert runner._needs_planning("") is False


# ──────────────────────────────────────────────────────────────────────
# _extract_plan / _strip_plan_from_text
# ──────────────────────────────────────────────────────────────────────


class TestExtractPlan:
    def test_valid_plan_block(self):
        text = (
            "Let me work on this.\n"
            "<plan>\n"
            "1. Read the config file -> read_file\n"
            "2. Update the settings -> write_file\n"
            "3. Run tests -> run_command\n"
            "</plan>\n"
            "Starting now."
        )
        plan = AgentRunner._extract_plan(text)
        assert plan.planning_active is True
        assert len(plan.steps) == 3
        assert plan.steps[0].description == "Read the config file"
        assert plan.steps[0].expected_tools == ["read_file"]
        assert plan.steps[0].status == "in_progress"
        assert plan.steps[1].status == "pending"

    def test_no_plan_block_returns_inactive(self):
        plan = AgentRunner._extract_plan("Just a normal response with no plan.")
        assert plan.planning_active is False
        assert plan.steps == []

    def test_step_without_tools(self):
        text = "<plan>\n1. Think about the problem\n2. Write code -> write_file\n</plan>"
        plan = AgentRunner._extract_plan(text)
        assert len(plan.steps) == 2
        assert plan.steps[0].expected_tools == []
        assert plan.steps[1].expected_tools == ["write_file"]

    def test_strip_plan_from_text(self):
        text = "Before\n<plan>\n1. Step one\n</plan>\nAfter"
        result = AgentRunner._strip_plan_from_text(text)
        assert "<plan>" not in result
        assert "Before" in result
        assert "After" in result

    def test_multiple_tools_in_step(self):
        text = "<plan>\n1. Read and analyze -> read_file, web_search\n</plan>"
        plan = AgentRunner._extract_plan(text)
        assert plan.steps[0].expected_tools == ["read_file", "web_search"]


# ──────────────────────────────────────────────────────────────────────
# PlanTracker operations
# ──────────────────────────────────────────────────────────────────────


class TestPlanTracker:
    def test_advance_on_success(self):
        plan = PlanTracker(
            planning_active=True,
            steps=[
                PlanStep(index=1, description="Step 1", status="in_progress"),
                PlanStep(index=2, description="Step 2"),
            ],
        )
        results = [ToolResult(tool_call_id="c1", tool_name="read_file", content="ok", is_error=False)]
        AgentRunner._update_plan_progress(plan, results)
        assert plan.steps[0].status == "completed"
        assert plan.steps[1].status == "in_progress"
        assert plan.current_step_index == 1

    def test_fail_current(self):
        plan = PlanTracker(
            planning_active=True,
            steps=[
                PlanStep(index=1, description="Step 1", status="in_progress"),
                PlanStep(index=2, description="Step 2"),
            ],
        )
        plan.fail_current()
        assert plan.steps[0].status == "failed"

    def test_all_completed(self):
        plan = PlanTracker(
            planning_active=True,
            steps=[
                PlanStep(index=1, description="Step 1", status="completed"),
                PlanStep(index=2, description="Step 2", status="completed"),
            ],
        )
        assert plan.all_completed is True

    def test_not_all_completed(self):
        plan = PlanTracker(
            planning_active=True,
            steps=[
                PlanStep(index=1, description="Step 1", status="completed"),
                PlanStep(index=2, description="Step 2", status="pending"),
            ],
        )
        assert plan.all_completed is False

    def test_replan_on_failure(self):
        plan = PlanTracker(
            planning_active=True,
            steps=[
                PlanStep(index=1, description="Step 1", expected_tools=["run_command"], status="in_progress"),
                PlanStep(index=2, description="Step 2"),
            ],
        )
        failed = [ToolResult(tool_call_id="c1", tool_name="run_command", content="error", is_error=True)]
        plan.fail_current()
        plan.replan_count += 1
        msg = AgentRunner._build_replan_message(plan, failed)
        assert "Step 1" in msg
        assert "Reassess" in msg


# ──────────────────────────────────────────────────────────────────────
# Smart summarization
# ──────────────────────────────────────────────────────────────────────


class TestSmartSummarization:
    def test_file_read_summarization(self):
        runner = _make_runner()
        # Create a large file content (100 lines)
        lines = [f"line {i}: content here" for i in range(100)]
        content = "\n".join(lines)
        result = runner._smart_summarize_tool_result("read_file", content)
        assert "100 total lines" in result
        assert "line 0:" in result  # head preserved
        assert "line 99:" in result  # tail preserved

    def test_command_output_summarization(self):
        runner = _make_runner()
        lines = [f"output line {i}" for i in range(100)]
        content = "\n".join(lines)
        result = runner._smart_summarize_tool_result("run_command", content)
        assert "100 total lines" in result
        # Tail-heavy: last 40 lines should be present
        assert "output line 99" in result

    def test_default_fallback_summarization(self):
        runner = _make_runner()
        lines = [f"data {i}" for i in range(100)]
        content = "\n".join(lines)
        result = runner._smart_summarize_tool_result("some_unknown_tool", content)
        assert "100 total lines" in result

    def test_web_search_extracts_urls(self):
        runner = _make_runner()
        lines = ["Some text"] * 30 + [
            "https://example.com/result1",
            "## Key Finding",
            "1. First result",
            "2. Second result",
        ] + ["Some text"] * 30
        content = "\n".join(lines)
        result = runner._smart_summarize_tool_result("web_search", content)
        assert "https://example.com/result1" in result
        assert "Key Finding" in result

    def test_budget_enforcement(self):
        runner = _make_runner()
        runner._tool_result_max_chars = 200
        content = "x" * 1000
        result = runner._smart_summarize_tool_result("read_file", content)
        assert len(result) <= 200 + 50  # allow small overhead from markers


# ──────────────────────────────────────────────────────────────────────
# Reflection tool retry
# ──────────────────────────────────────────────────────────────────────


class TestReflectionToolRetry:
    @pytest.mark.asyncio
    async def test_text_only_retry_unchanged(self):
        """When tool retry is disabled, behavior is unchanged (text-only)."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(memory=memory)
        runner._reflection_service = MagicMock()

        # Reflection says retry
        verdict = MagicMock()
        verdict.score = 0.4
        verdict.goal_alignment = 0.5
        verdict.completeness = 0.3
        verdict.factual_grounding = 0.5
        verdict.issues = ["Missing details"]
        verdict.should_retry = True
        verdict.hard_factual_fail = False
        verdict.suggested_fix = "Add more details"

        # First call: should_retry=True, second call: should_retry=False
        verdict2 = MagicMock()
        verdict2.score = 0.8
        verdict2.goal_alignment = 0.9
        verdict2.completeness = 0.8
        verdict2.factual_grounding = 0.7
        verdict2.issues = []
        verdict2.should_retry = False
        verdict2.hard_factual_fail = False
        verdict2.suggested_fix = ""

        runner._reflection_service.reflect = AsyncMock(side_effect=[verdict, verdict2])

        # LLM retry returns revised text
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=_stop_result("Revised answer with more details")
        )

        result = await runner._run_reflection(
            final_text="Short answer",
            user_message="Tell me about X",
            tool_results=[],
            task_type="research",
            model=None,
            send_event=send_event,
            request_id="r1",
            session_id="s1",
            messages=[{"role": "system", "content": "sys"}],
        )

        assert result == "Revised answer with more details"
        # tools=None means text-only retry
        call_args = runner.client.stream_chat_with_tools.call_args
        assert call_args.kwargs.get("tools") is None or call_args[1].get("tools") is None

    @pytest.mark.asyncio
    async def test_tool_retry_when_enabled(self):
        """When tool retry is enabled and completeness < 0.5, tools are passed."""
        send_event = AsyncMock()
        memory = MagicMock()
        memory.get_items.return_value = []

        runner = _make_runner(memory=memory)
        runner._reflection_service = MagicMock()

        verdict = MagicMock()
        verdict.score = 0.3
        verdict.goal_alignment = 0.4
        verdict.completeness = 0.2  # < 0.5 threshold
        verdict.factual_grounding = 0.3
        verdict.issues = ["Very incomplete"]
        verdict.should_retry = True
        verdict.hard_factual_fail = False
        verdict.suggested_fix = "Gather more data"

        verdict2 = MagicMock()
        verdict2.score = 0.9
        verdict2.should_retry = False
        verdict2.goal_alignment = 0.9
        verdict2.completeness = 0.9
        verdict2.factual_grounding = 0.9
        verdict2.issues = []
        verdict2.hard_factual_fail = False
        verdict2.suggested_fix = ""

        runner._reflection_service.reflect = AsyncMock(side_effect=[verdict, verdict2])

        # LLM returns final answer directly (tool retry path, but LLM decides it has enough)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=_stop_result("Complete answer with tool data")
        )

        tool_defs = [{"type": "function", "function": {"name": "read_file"}}]

        with patch("app.agent.runner.settings") as mock_settings:
            mock_settings.runner_reflection_tool_retry_enabled = True
            mock_settings.runner_reflection_enabled = True
            mock_settings.runner_reflection_max_passes = 1
            mock_settings.llm_model = "test"

            result = await runner._run_reflection(
                final_text="Incomplete",
                user_message="Research X",
                tool_results=[],
                task_type="research",
                model=None,
                send_event=send_event,
                request_id="r1",
                session_id="s1",
                messages=[{"role": "system", "content": "sys"}],
                tool_definitions=tool_defs,
                effective_allowed_tools={"read_file"},
            )

        assert result == "Complete answer with tool data"
        # Verify tools were passed (not None)
        call_args = runner.client.stream_chat_with_tools.call_args
        assert call_args.kwargs.get("tools") is not None


# ──────────────────────────────────────────────────────────────────────
# Progress context building
# ──────────────────────────────────────────────────────────────────────


class TestBuildProgressContext:
    def test_progress_format(self):
        plan = PlanTracker(
            planning_active=True,
            steps=[
                PlanStep(index=1, description="Read config", status="completed"),
                PlanStep(index=2, description="Update code", status="in_progress"),
                PlanStep(index=3, description="Run tests", status="pending"),
            ],
            current_step_index=1,
        )
        ctx = AgentRunner._build_progress_context(plan)
        assert "[x] 1. Read config" in ctx
        assert "[>] 2. Update code" in ctx
        assert "[ ] 3. Run tests" in ctx
        assert "(1/3 completed)" in ctx
