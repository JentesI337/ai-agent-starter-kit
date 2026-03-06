"""Regression tests for bugs found in the 2026-03-04 Reasoning Lifecycle Bug Audit.

Bug 1: Retrieval context silently overwritten by skills injection
Bug 2: Parallel read-only mode bypasses budget and loop gates
Bug 3: Steer-interrupt not checked in parallel read-only path
Bug 6: Unsupported-type path leaves runs without terminal status (ws_handler integration)
Bug 7: request_cancelled sets no terminal state (ws_handler integration)
"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.services.tool_execution_manager import ToolExecutionConfig, ToolExecutionManager

# ---------------------------------------------------------------------------
# Helpers – standard fakes reused across tests
# ---------------------------------------------------------------------------

def _make_config(
    *,
    call_cap: int = 5,
    time_cap_seconds: float = 30.0,
    parallel_read_only_enabled: bool = False,
) -> ToolExecutionConfig:
    return ToolExecutionConfig(
        call_cap=call_cap,
        time_cap_seconds=time_cap_seconds,
        loop_warn_threshold=2,
        loop_critical_threshold=4,
        loop_circuit_breaker_threshold=8,
        generic_repeat_enabled=True,
        ping_pong_enabled=True,
        poll_no_progress_enabled=True,
        poll_no_progress_threshold=3,
        warning_bucket_size=10,
        parallel_read_only_enabled=parallel_read_only_enabled,
    )


def _noop_sync(*_a, **_kw):
    return None


async def _noop_async(*_a, **_kw):
    return None


# ===========================================================================
# Bug 2 – Parallel read-only mode must respect call-cap budget
# ===========================================================================

def test_parallel_read_only_respects_call_cap() -> None:
    """Read-only actions dispatched in parallel must be capped by the call budget."""
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_run_tool(*, tool: str, args: dict, policy: object) -> str:
        return f"result-{tool}"

    # 4 read-only actions but only 2 calls allowed
    actions = [{"tool": "read_file", "args": {"path": f"file{i}.md"}} for i in range(4)]

    result = asyncio.run(
        manager.run_tool_loop(
            actions=actions,
            effective_allowed_tools={"read_file"},
            config=_make_config(call_cap=2, parallel_read_only_enabled=True),
            app_settings=settings,
            user_message="read files",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool,
            invoke_spawn_subrun_tool=lambda **kw: asyncio.sleep(0),
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda msg: False,
            is_weather_lookup_task=lambda msg: False,
            build_web_research_url=lambda msg: "",
            memory_add=_noop_sync,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=_noop_async,
            invoke_hooks=lambda hook_name, payload: asyncio.sleep(0),
        )
    )

    # At most 2 results should have been executed (not all 4)
    executed_count = result.count("result-read_file")
    assert executed_count <= 2, f"Expected at most 2 executions, got {executed_count}"

    # Budget-exceeded lifecycle event must have been emitted for the skipped actions
    assert any(
        stage == "tool_budget_exceeded"
        and isinstance(details, dict)
        and details.get("tool") == "read_only_parallel"
        for stage, details in lifecycle_events
    ), "Expected tool_budget_exceeded lifecycle event for parallel read-only cap"


# ===========================================================================
# Bug 2 – Parallel read-only mode must respect time budget
# ===========================================================================

def test_parallel_read_only_respects_time_budget() -> None:
    """If time budget is already exceeded, parallel read-only batch must not execute."""
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_run_tool(*, tool: str, args: dict, policy: object) -> str:
        return f"result-{tool}"

    actions = [{"tool": "read_file", "args": {"path": "a.md"}}]

    result = asyncio.run(
        manager.run_tool_loop(
            actions=actions,
            effective_allowed_tools={"read_file"},
            config=_make_config(time_cap_seconds=0.0, parallel_read_only_enabled=True),
            app_settings=settings,
            user_message="read files",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool,
            invoke_spawn_subrun_tool=lambda **kw: asyncio.sleep(0),
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda msg: False,
            is_weather_lookup_task=lambda msg: False,
            build_web_research_url=lambda msg: "",
            memory_add=_noop_sync,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=_noop_async,
            invoke_hooks=lambda hook_name, payload: asyncio.sleep(0),
        )
    )

    # No tool should have actually executed
    assert "result-read_file" not in result

    assert any(
        stage == "tool_budget_exceeded"
        and isinstance(details, dict)
        and details.get("budget_type") == "time"
        for stage, details in lifecycle_events
    ), "Expected time budget exceeded lifecycle for parallel read-only"


# ===========================================================================
# Bug 3 – Steer interrupt must cancel parallel read-only batch
# ===========================================================================

def test_parallel_read_only_checks_steer_interrupt() -> None:
    """Steer-interrupt must prevent parallel read-only actions from executing."""
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_run_tool(*, tool: str, args: dict, policy: object) -> str:
        return f"result-{tool}"

    actions = [{"tool": "read_file", "args": {"path": "a.md"}}]

    result = asyncio.run(
        manager.run_tool_loop(
            actions=actions,
            effective_allowed_tools={"read_file"},
            config=_make_config(parallel_read_only_enabled=True),
            app_settings=settings,
            user_message="read file",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool,
            invoke_spawn_subrun_tool=lambda **kw: asyncio.sleep(0),
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda msg: False,
            is_weather_lookup_task=lambda msg: False,
            build_web_research_url=lambda msg: "",
            memory_add=_noop_sync,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=_noop_async,
            invoke_hooks=lambda hook_name, payload: asyncio.sleep(0),
            should_steer_interrupt=lambda: True,
        )
    )

    assert any(
        stage == "tool_parallel_read_only_steer_interrupted" for stage, _ in lifecycle_events
    ), "Expected steer-interrupted lifecycle event for parallel read-only"

    # The read-only action should not have produced a result
    assert "result-read_file" not in result
