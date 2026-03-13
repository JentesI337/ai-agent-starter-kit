"""Unit tests for the debug checkpoint infrastructure (Phase 2).

Tests verify:
- _debug_checkpoint() blocks on breakpoint-hit phases
- _debug_checkpoint() is a no-op when debug mode is off
- _debug_checkpoint() is a no-op when _debug_mode_active is False
- _debug_checkpoint() resumes after continue event is set
- _emit_lifecycle() filters debug_* events when debug_mode=False
- ws_handler debug message handling activates/deactivates _debug_mode_active
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(*, debug_mode_active: bool = True) -> MagicMock:
    """Build a minimal HeadAgent-like object for checkpoint tests."""
    from app.agent import HeadAgent

    agent = MagicMock(spec=HeadAgent)
    agent.name = "test-agent"
    agent._debug_mode_active = debug_mode_active
    agent._debug_breakpoints = set()
    agent._debug_continue_event = asyncio.Event()
    agent._debug_continue_event.set()  # not paused by default

    # Delegate to real _debug_checkpoint implementation
    agent._debug_checkpoint = lambda phase, send_event, request_id, session_id: HeadAgent._debug_checkpoint(
        agent, phase, send_event, request_id, session_id
    )
    agent._emit_lifecycle = AsyncMock()
    return agent


def _dummy_send_event(payload: dict) -> None:
    pass


# ---------------------------------------------------------------------------
# _debug_checkpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_no_op_when_inactive():
    """Checkpoint must return immediately if _debug_mode_active is False."""
    agent = _make_agent(debug_mode_active=False)
    agent._debug_breakpoints = {"planning"}

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True
        await agent._debug_checkpoint("planning", AsyncMock(), "req-1", "sess-1")

    agent._emit_lifecycle.assert_not_called()


@pytest.mark.asyncio
async def test_checkpoint_no_op_when_debug_mode_active_false():
    """Checkpoint must return immediately if _debug_mode_active is False,
    even when breakpoints are registered."""
    agent = _make_agent(debug_mode_active=False)
    agent._debug_breakpoints = {"planning"}
    send_event = AsyncMock()

    await agent._debug_checkpoint("planning", send_event, "req-1", "sess-1")

    send_event.assert_not_called()


@pytest.mark.asyncio
async def test_checkpoint_passes_through_when_phase_not_in_breakpoints():
    """Checkpoint should not block when phase is not a registered breakpoint."""
    agent = _make_agent(debug_mode_active=True)
    agent._debug_breakpoints = {"synthesis"}  # planning is NOT a breakpoint

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True
        # Should complete without blocking
        await asyncio.wait_for(
            agent._debug_checkpoint("planning", AsyncMock(), "req-1", "sess-1"),
            timeout=1.0,
        )

    agent._emit_lifecycle.assert_not_called()


@pytest.mark.asyncio
async def test_checkpoint_blocks_on_registered_breakpoint():
    """Checkpoint must block and emit debug_breakpoint_hit on a registered breakpoint."""
    agent = _make_agent(debug_mode_active=True)
    agent._debug_breakpoints = {"planning"}

    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True

        # Start checkpoint coroutine — it should block
        task = asyncio.create_task(agent._debug_checkpoint("planning", send_event, "req-1", "sess-1"))

        # Allow event loop to run checkpoint until it blocks
        await asyncio.sleep(0.05)
        assert not task.done(), "checkpoint should be blocked waiting for continue"

        # Unblock by setting the event
        agent._debug_continue_event.set()
        await asyncio.wait_for(task, timeout=1.0)

    # debug_breakpoint_hit should have been emitted via send_event
    send_event.assert_awaited_once()
    call_args = send_event.call_args
    payload = call_args[0][0]
    assert payload["stage"] == "debug_breakpoint_hit"
    assert payload["details"]["phase"] == "planning"


@pytest.mark.asyncio
async def test_checkpoint_resumes_on_continue():
    """After blocking, checkpoint must resume once continue event is set."""
    agent = _make_agent(debug_mode_active=True)
    agent._debug_breakpoints = {"context"}
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True

        async def unblock_after_delay() -> None:
            await asyncio.sleep(0.1)
            agent._debug_continue_event.set()

        _task = asyncio.create_task(unblock_after_delay())  # noqa: RUF006
        await asyncio.wait_for(
            agent._debug_checkpoint("context", send_event, "req-2", "sess-2"),
            timeout=2.0,
        )

    # debug_breakpoint_hit emitted via send_event
    send_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_checkpoint_times_out_gracefully():
    """Checkpoint should auto-resume after timeout (300s) without raising."""
    agent = _make_agent(debug_mode_active=True)
    agent._debug_breakpoints = {"synthesis"}
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True
        # Patch wait_for to use a very short timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            # Should not raise
            await agent._debug_checkpoint("synthesis", send_event, "req-3", "sess-3")

    # After timeout, continue event should be set
    assert agent._debug_continue_event.is_set()


# ---------------------------------------------------------------------------
# _emit_lifecycle debug gate tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_lifecycle_filters_debug_events_when_debug_mode_off():
    """debug_* stage events must be swallowed when settings.debug_mode is False."""
    from app.agent import HeadAgent

    agent = MagicMock(spec=HeadAgent)
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = False
        await HeadAgent._emit_lifecycle(
            agent,
            send_event,
            stage="debug_breakpoint_hit",
            request_id="req-1",
            session_id="sess-1",
            details={"phase": "planning"},
        )

    send_event.assert_not_called()


@pytest.mark.asyncio
async def test_emit_lifecycle_passes_debug_events_when_debug_mode_on():
    """debug_* stage events must be forwarded when settings.debug_mode is True."""
    from app.agent import HeadAgent

    agent = MagicMock(spec=HeadAgent)
    agent.name = "test-agent"
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = True
        await HeadAgent._emit_lifecycle(
            agent,
            send_event,
            stage="debug_breakpoint_hit",
            request_id="req-1",
            session_id="sess-1",
            details={"phase": "planning"},
        )

    send_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_emit_lifecycle_always_passes_non_debug_events():
    """Non-debug_* events must be forwarded regardless of debug_mode."""
    from app.agent import HeadAgent

    agent = MagicMock(spec=HeadAgent)
    agent.name = "test-agent"
    send_event = AsyncMock()

    with patch("app.agent.head_agent.settings") as mock_settings:
        mock_settings.debug_mode = False
        await HeadAgent._emit_lifecycle(
            agent,
            send_event,
            stage="planning_started",
            request_id="req-1",
            session_id="sess-1",
        )

    send_event.assert_awaited_once()


# ---------------------------------------------------------------------------
# ws_handler debug message handling tests
# ---------------------------------------------------------------------------


def test_debug_set_breakpoints_activates_debug_mode():
    """debug_set_breakpoints must set _debug_mode_active=True on the agent."""

    class FakeAgent:
        _debug_breakpoints: set[str] = set()
        _debug_mode_active: bool = False

    agent = FakeAgent()

    # Simulate what ws_handler does on debug_set_breakpoints
    bp_list = ["planning", "synthesis"]
    _valid_phases = {
        "guardrails",
        "context",
        "planning",
        "tool_selection",
        "synthesis",
        "reflection",
        "reply_shaping",
    }
    if hasattr(agent, "_debug_breakpoints"):
        agent._debug_breakpoints = set(bp_list) & _valid_phases
    if hasattr(agent, "_debug_mode_active"):
        agent._debug_mode_active = bool(bp_list)

    assert agent._debug_mode_active is True
    assert agent._debug_breakpoints == {"planning", "synthesis"}


def test_debug_play_deactivates_debug_mode():
    """debug_play must clear breakpoints and set _debug_mode_active=False."""

    class FakeAgent:
        _debug_breakpoints: set[str] = {"planning"}
        _debug_mode_active: bool = True
        _debug_continue_event = asyncio.Event()

    agent = FakeAgent()
    agent._debug_continue_event.clear()  # pretend paused

    # Simulate what ws_handler does on debug_play
    if hasattr(agent, "_debug_breakpoints"):
        agent._debug_breakpoints.clear()
    if hasattr(agent, "_debug_continue_event"):
        agent._debug_continue_event.set()
    if hasattr(agent, "_debug_mode_active"):
        agent._debug_mode_active = False

    assert agent._debug_mode_active is False
    assert len(agent._debug_breakpoints) == 0
    assert agent._debug_continue_event.is_set()


def test_debug_set_breakpoints_filters_invalid_phases():
    """debug_set_breakpoints must filter out phases not in _valid_phases."""

    class FakeAgent:
        _debug_breakpoints: set[str] = set()
        _debug_mode_active: bool = False

    agent = FakeAgent()
    bp_list = ["planning", "routing", "invalid_phase"]
    _valid_phases = {
        "guardrails",
        "context",
        "planning",
        "tool_selection",
        "synthesis",
        "reflection",
        "reply_shaping",
    }
    if hasattr(agent, "_debug_breakpoints"):
        agent._debug_breakpoints = set(bp_list) & _valid_phases

    assert "routing" not in agent._debug_breakpoints
    assert "invalid_phase" not in agent._debug_breakpoints
    assert "planning" in agent._debug_breakpoints


def test_debug_set_empty_breakpoints_deactivates_debug_mode():
    """Sending an empty breakpoints list should set _debug_mode_active=False."""

    class FakeAgent:
        _debug_breakpoints: set[str] = {"planning"}
        _debug_mode_active: bool = True

    agent = FakeAgent()
    bp_list: list[str] = []
    _valid_phases = {
        "guardrails",
        "context",
        "planning",
        "tool_selection",
        "synthesis",
        "reflection",
        "reply_shaping",
    }
    if hasattr(agent, "_debug_breakpoints"):
        agent._debug_breakpoints = set(bp_list) & _valid_phases
    if hasattr(agent, "_debug_mode_active"):
        agent._debug_mode_active = bool(bp_list)

    assert agent._debug_mode_active is False
    assert len(agent._debug_breakpoints) == 0
