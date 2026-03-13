"""Unit tests for AgentRunner reflection loop (Sprint 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.runner import AgentRunner
from app.agent.runner_types import StreamResult, ToolResult

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_runner(**overrides) -> AgentRunner:
    defaults = {
        "client": MagicMock(),
        "memory": MagicMock(),
        "tool_registry": MagicMock(),
        "tool_execution_manager": MagicMock(),
        "system_prompt": "test",
        "execute_tool_fn": AsyncMock(return_value="ok"),
        "allowed_tools_resolver": MagicMock(return_value={"read_file"}),
    }
    defaults.update(overrides)
    return AgentRunner(**defaults)


def _ok(name: str, content: str = "success") -> ToolResult:
    return ToolResult(tool_call_id="c1", tool_name=name, content=content, is_error=False)


def _verdict(should_retry=False, score=0.8, issues=None, suggested_fix=None):
    """Create a mock ReflectionVerdict."""
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
# Reflection tests
# ──────────────────────────────────────────────────────────────────────


class TestReflectionLoop:
    @pytest.mark.asyncio
    async def test_skipped_when_disabled(self):
        """Reflection is skipped when runner_reflection_enabled=False."""
        reflection_svc = AsyncMock()
        runner = _make_runner(reflection_service=reflection_svc)
        runner.memory.get_items.return_value = []
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Hello!", tool_calls=(), finish_reason="stop"),
        )

        with patch("app.agent.runner.settings") as mock_settings:
            mock_settings.runner_reflection_enabled = False
            mock_settings.runner_max_iterations = 25
            mock_settings.runner_max_tool_calls = 50
            mock_settings.runner_time_budget_seconds = 300
            mock_settings.runner_loop_detection_enabled = True
            mock_settings.runner_loop_detection_threshold = 3
            mock_settings.runner_compaction_enabled = True
            mock_settings.runner_compaction_tail_keep = 4
            mock_settings.runner_tool_result_max_chars = 5000
            mock_settings.runner_reflection_max_passes = 1

            await runner.run(
                user_message="Hello",
                send_event=AsyncMock(),
                session_id="s1",
                request_id="r1",
            )

        reflection_svc.reflect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_when_service_none(self):
        """Reflection is skipped when no ReflectionService provided."""
        runner = _make_runner(reflection_service=None)
        runner.memory.get_items.return_value = []
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Hello!", tool_calls=(), finish_reason="stop"),
        )
        result = await runner.run(
            user_message="Hello",
            send_event=AsyncMock(),
            session_id="s1",
            request_id="r1",
        )
        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_skipped_when_final_too_short(self):
        """Reflection is skipped when final_text < 8 chars."""
        reflection_svc = AsyncMock()
        runner = _make_runner(reflection_service=reflection_svc)
        runner.memory.get_items.return_value = []
        runner.tool_registry.build_function_calling_tools = MagicMock(return_value=[])
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="OK", tool_calls=(), finish_reason="stop"),
        )
        await runner.run(
            user_message="ping",
            send_event=AsyncMock(),
            session_id="s1",
            request_id="r1",
        )
        reflection_svc.reflect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_retry_keeps_original(self):
        """Reflection with should_retry=False keeps original text."""
        reflection_svc = AsyncMock()
        reflection_svc.reflect = AsyncMock(return_value=_verdict(should_retry=False))
        runner = _make_runner(reflection_service=reflection_svc)
        messages = [{"role": "system", "content": "sys"}]

        result = await runner._run_reflection(
            final_text="A detailed answer about Python.",
            user_message="tell me about python",
            tool_results=[],
            task_type="general",
            model=None,
            send_event=AsyncMock(),
            request_id="r1",
            session_id="s1",
            messages=messages,
        )
        assert result == "A detailed answer about Python."
        reflection_svc.reflect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_calls_llm_with_feedback(self):
        """Reflection with should_retry=True triggers an LLM retry call."""
        reflection_svc = AsyncMock()
        # First call: retry, second call: no retry
        reflection_svc.reflect = AsyncMock(side_effect=[
            _verdict(should_retry=True, score=0.3, issues=["Missing detail"]),
            _verdict(should_retry=False, score=0.9),
        ])
        runner = _make_runner(reflection_service=reflection_svc)
        runner.client.stream_chat_with_tools = AsyncMock(
            return_value=StreamResult(text="Revised detailed answer.", tool_calls=(), finish_reason="stop"),
        )
        messages = [{"role": "system", "content": "sys"}]

        with patch("app.agent.runner.settings") as mock_settings:
            mock_settings.runner_reflection_max_passes = 2
            mock_settings.llm_model = "test-model"

            result = await runner._run_reflection(
                final_text="Short answer.",
                user_message="tell me about python",
                tool_results=[],
                task_type="general",
                model=None,
                send_event=AsyncMock(),
                request_id="r1",
                session_id="s1",
                messages=messages,
            )

        assert result == "Revised detailed answer."
        assert reflection_svc.reflect.await_count == 2
        runner.client.stream_chat_with_tools.assert_awaited_once()
        # Check that feedback message was appended
        assert any("[REFLECTION FEEDBACK]" in m.get("content", "") for m in messages)

    @pytest.mark.asyncio
    async def test_exception_keeps_original(self):
        """Reflection exception doesn't crash — keeps original text."""
        reflection_svc = AsyncMock()
        reflection_svc.reflect = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        runner = _make_runner(reflection_service=reflection_svc)

        result = await runner._run_reflection(
            final_text="Original answer.",
            user_message="test",
            tool_results=[],
            task_type="general",
            model=None,
            send_event=AsyncMock(),
            request_id="r1",
            session_id="s1",
            messages=[],
        )
        assert result == "Original answer."

    @pytest.mark.asyncio
    async def test_feedback_store_called(self):
        """ReflectionFeedbackStore.store() is called when available."""
        reflection_svc = AsyncMock()
        reflection_svc.reflect = AsyncMock(return_value=_verdict(should_retry=False))
        store = MagicMock()
        runner = _make_runner(
            reflection_service=reflection_svc,
            reflection_feedback_store=store,
        )

        with patch("app.agent.runner.settings") as mock_settings:
            mock_settings.runner_reflection_max_passes = 1
            mock_settings.llm_model = "test-model"

            await runner._run_reflection(
                final_text="A detailed answer.",
                user_message="test",
                tool_results=[],
                task_type="general",
                model=None,
                send_event=AsyncMock(),
                request_id="r1",
                session_id="s1",
                messages=[],
            )

        store.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_store_none_no_error(self):
        """No error when ReflectionFeedbackStore is None."""
        reflection_svc = AsyncMock()
        reflection_svc.reflect = AsyncMock(return_value=_verdict(should_retry=False))
        runner = _make_runner(
            reflection_service=reflection_svc,
            reflection_feedback_store=None,
        )

        with patch("app.agent.runner.settings") as mock_settings:
            mock_settings.runner_reflection_max_passes = 1
            mock_settings.llm_model = "test-model"

            result = await runner._run_reflection(
                final_text="A detailed answer.",
                user_message="test",
                tool_results=[],
                task_type="general",
                model=None,
                send_event=AsyncMock(),
                request_id="r1",
                session_id="s1",
                messages=[],
            )

        assert result == "A detailed answer."

    @pytest.mark.asyncio
    async def test_type_error_fallback(self):
        """Older ReflectionService without task_type param triggers fallback."""
        reflection_svc = AsyncMock()
        # First call with task_type raises TypeError, second without succeeds
        reflection_svc.reflect = AsyncMock(side_effect=[
            TypeError("unexpected keyword argument 'task_type'"),
            _verdict(should_retry=False),
        ])
        runner = _make_runner(reflection_service=reflection_svc)

        with patch("app.agent.runner.settings") as mock_settings:
            mock_settings.runner_reflection_max_passes = 1
            mock_settings.llm_model = "test-model"

            result = await runner._run_reflection(
                final_text="A good answer here.",
                user_message="test",
                tool_results=[],
                task_type="general",
                model=None,
                send_event=AsyncMock(),
                request_id="r1",
                session_id="s1",
                messages=[],
            )

        assert result == "A good answer here."
        assert reflection_svc.reflect.await_count == 2
