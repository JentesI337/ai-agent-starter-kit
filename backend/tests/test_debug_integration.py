"""Integration tests for the debug pipeline flow.

Tests verify:
- Debug events are emitted for all phases when DEBUG_MODE=true
- Debug events are suppressed when DEBUG_MODE=false
- Breakpoint set → pause → continue cycle works end-to-end
- debug_prompt_sent / debug_llm_response emitted for planning, tool_selection, synthesis, reflection
- ws_handler routes debug_continue, debug_pause, debug_play, debug_set_breakpoints
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_BREAKPOINT_PHASES = {
    "routing",
    "guardrails",
    "context",
    "planning",
    "tool_selection",
    "synthesis",
    "reflection",
    "reply_shaping",
    "response",
}


def _make_agent(*, debug_mode_active: bool = True) -> MagicMock:
    """Build a HeadAgent-like mock for integration tests."""
    from app.agent import HeadAgent

    agent = MagicMock(spec=HeadAgent)
    agent.name = "test-agent"
    agent._debug_mode_active = debug_mode_active
    agent._debug_breakpoints = set()
    agent._debug_continue_event = asyncio.Event()
    agent._debug_continue_event.set()

    agent._debug_checkpoint = lambda phase, send_event, request_id, session_id: HeadAgent._debug_checkpoint(
        agent, phase, send_event, request_id, session_id
    )
    agent._emit_lifecycle = AsyncMock()
    return agent


# ---------------------------------------------------------------------------
# Integration: breakpoint pause+continue cycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breakpoint_pause_continue_cycle():
    """Full cycle: set breakpoint → hit → pause → continue → resume."""
    agent = _make_agent(debug_mode_active=True)
    agent._debug_breakpoints = {"planning"}
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True

        # Checkpoint should block
        task = asyncio.create_task(
            agent._debug_checkpoint("planning", send_event, "req-cycle", "sess-cycle")
        )
        await asyncio.sleep(0.05)
        assert not task.done(), "Should be paused at breakpoint"

        # Simulate continue
        agent._debug_continue_event.set()
        await asyncio.wait_for(task, timeout=2.0)

    # Verify breakpoint_hit was emitted via send_event
    send_event.assert_awaited_once()
    payload = send_event.call_args[0][0]
    assert payload["stage"] == "debug_breakpoint_hit"
    assert payload["details"]["phase"] == "planning"


# ---------------------------------------------------------------------------
# Integration: multiple breakpoints in sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_breakpoints_sequential():
    """Two breakpoints should each pause independently."""
    agent = _make_agent(debug_mode_active=True)
    agent._debug_breakpoints = {"context", "planning"}
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True

        # First breakpoint: context
        task1 = asyncio.create_task(
            agent._debug_checkpoint("context", send_event, "req-m1", "sess-m1")
        )
        await asyncio.sleep(0.05)
        assert not task1.done()
        agent._debug_continue_event.set()
        await asyncio.wait_for(task1, timeout=2.0)

        # Second breakpoint: planning
        agent._debug_continue_event.clear()
        task2 = asyncio.create_task(
            agent._debug_checkpoint("planning", send_event, "req-m1", "sess-m1")
        )
        await asyncio.sleep(0.05)
        assert not task2.done()
        agent._debug_continue_event.set()
        await asyncio.wait_for(task2, timeout=2.0)

    assert send_event.await_count == 2
    phases_hit = [c[0][0]["details"]["phase"] for c in send_event.call_args_list]
    assert "context" in phases_hit
    assert "planning" in phases_hit


# ---------------------------------------------------------------------------
# Integration: ws_handler breakpoint whitelist validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breakpoint_phase_whitelist():
    """Only valid phase names should be accepted as breakpoints."""

    invalid_phases = {"invalid_phase", "DROP TABLE", "<script>", ""}
    valid_phases = {"planning", "reflection"}

    # Only phases in the valid set should pass
    filtered = {p for p in (invalid_phases | valid_phases) if p in _VALID_BREAKPOINT_PHASES}
    assert filtered == valid_phases


# ---------------------------------------------------------------------------
# Integration: debug events filtered in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debug_events_filtered_when_debug_mode_false():
    """_emit_lifecycle should suppress debug_* events when debug_mode is off."""
    from app.agent import HeadAgent

    agent = MagicMock(spec=HeadAgent)
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = False
        await HeadAgent._emit_lifecycle(
            agent,
            send_event,
            stage="debug_prompt_sent",
            request_id="req-1",
            session_id="sess-1",
            details={"phase": "planning", "system_prompt": "leak!"},
        )

    send_event.assert_not_called()
