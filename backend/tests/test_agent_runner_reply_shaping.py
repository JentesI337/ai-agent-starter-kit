"""Unit tests for AgentRunner reply shaping and verification (Sprint 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_runner import AgentRunner
from app.agent_runner_types import ToolResult
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
        system_prompt="test",
        execute_tool_fn=AsyncMock(return_value="ok"),
        allowed_tools_resolver=MagicMock(return_value={"read_file"}),
    )
    defaults.update(overrides)
    return AgentRunner(**defaults)


def _ok(name: str, content: str = "success") -> ToolResult:
    return ToolResult(tool_call_id="c1", tool_name=name, content=content, is_error=False)


# ──────────────────────────────────────────────────────────────────────
# Reply Shaping
# ──────────────────────────────────────────────────────────────────────


class TestReplyShaping:
    @pytest.mark.asyncio
    async def test_tool_call_markers_removed(self):
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.tool_registry.keys = MagicMock(return_value=["read_file"])
        text = "Here is the result [TOOL_CALL]read_file[/TOOL_CALL] of the operation."
        result = await runner._shape_final_response(text, [])
        assert "[TOOL_CALL]" not in result
        assert "[/TOOL_CALL]" not in result

    @pytest.mark.asyncio
    async def test_empty_text_suppressed(self):
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.tool_registry.keys = MagicMock(return_value=[])
        result = await runner._shape_final_response("", [])
        assert "suppressed" in result.lower() or result == ""

    @pytest.mark.asyncio
    async def test_duplicate_tool_confirmations_deduped(self):
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.tool_registry.keys = MagicMock(return_value=["read_file"])
        text = "read_file done\nread_file done\nAll good."
        result = await runner._shape_final_response(text, [_ok("read_file")])
        # Should only have one "read_file done" line
        assert result.count("read_file done") == 1

    @pytest.mark.asyncio
    async def test_suppressed_response_returns_fallback(self):
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.tool_registry.keys = MagicMock(return_value=["read_file"])
        result = await runner._shape_final_response("done.", [_ok("read_file")])
        assert "suppressed" in result.lower() or result == ""

    @pytest.mark.asyncio
    async def test_without_reply_shaper_returns_original(self):
        runner = _make_runner(reply_shaper=None)
        original = "Hello world!"
        result = await runner._shape_final_response(original, [])
        assert result == original

    @pytest.mark.asyncio
    async def test_normal_text_passes_through(self):
        runner = _make_runner(reply_shaper=ReplyShaper())
        runner.tool_registry.keys = MagicMock(return_value=[])
        original = "Here is a detailed analysis of the code."
        result = await runner._shape_final_response(original, [])
        assert result == original


# ──────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────


class TestVerification:
    def test_empty_text_replaced(self):
        vs = VerificationService()
        runner = _make_runner(verification_service=vs)
        check = vs.verify_final(user_message="test", final_text="")
        assert not check.ok

    def test_short_text_replaced(self):
        vs = VerificationService()
        check = vs.verify_final(user_message="test", final_text="Hi")
        # VerificationService considers < 8 chars as too short
        assert not check.ok

    def test_normal_text_passes(self):
        vs = VerificationService()
        check = vs.verify_final(user_message="test", final_text="Here is a well-formed answer.")
        assert check.ok

    def test_without_verification_service_no_check(self):
        """When no verification service is configured, text passes through unchanged."""
        runner = _make_runner(verification_service=None)
        # Just verify the runner has None for verification
        assert runner._verification_service is None
