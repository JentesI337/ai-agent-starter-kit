from __future__ import annotations

import asyncio

from app.errors import ToolExecutionError
from app.services.tool_execution_manager import ToolExecutionConfig, ToolExecutionManager


def test_build_tool_selector_prompt_contains_allowed_tools_and_context() -> None:
    manager = ToolExecutionManager()

    prompt = manager.build_tool_selector_prompt(
        allowed_tools={"read_file", "web_fetch"},
        memory_context="context-line",
        user_message="please research this",
        plan_text="1) inspect",
    )

    assert '"tool":"read_file|web_fetch"' in prompt or '"tool":"web_fetch|read_file"' in prompt
    assert "Allowed tool names are exactly: read_file, web_fetch." in prompt or "Allowed tool names are exactly: web_fetch, read_file." in prompt
    assert "[kernel_version=prompt-kernel.v1]" in prompt
    assert "[prompt_type=tool_selection]" in prompt
    assert "## memory\ncontext-line" in prompt
    assert "## task\nplease research this" in prompt
    assert "## plan\n1) inspect" in prompt


def test_build_loop_gatekeeper_uses_config_values() -> None:
    manager = ToolExecutionManager()
    config = ToolExecutionConfig(
        call_cap=8,
        time_cap_seconds=90.0,
        loop_warn_threshold=2,
        loop_critical_threshold=5,
        loop_circuit_breaker_threshold=9,
        generic_repeat_enabled=False,
        ping_pong_enabled=True,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=4,
        warning_bucket_size=7,
    )

    gatekeeper = manager.build_loop_gatekeeper(config)

    assert gatekeeper.warn_threshold == 2
    assert gatekeeper.critical_threshold == 5
    assert gatekeeper.circuit_breaker_threshold == 9
    assert gatekeeper.warning_bucket_size == 7
    assert gatekeeper.generic_repeat_enabled is False
    assert gatekeeper.ping_pong_enabled is True
    assert gatekeeper.poll_no_progress_enabled is False
    assert gatekeeper.poll_no_progress_threshold == 4


def test_select_actions_with_repair_recovers_and_emits_status() -> None:
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []
    sent_events: list[dict] = []
    first_call = {"done": False}

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        if first_call["done"]:
            return '{"actions":[]}'
        first_call["done"] = True
        return "broken-json"

    def fake_extract_actions(raw: str) -> tuple[list[dict], str | None]:
        if raw == "broken-json":
            return [], "LLM JSON could not be decoded."
        return [{"tool": "read_file", "args": {"path": "README.md"}}], None

    async def fake_repair_tool_selection_json(*, raw: str, model: str | None) -> str:
        return '{"actions":[{"tool":"read_file","args":{"path":"README.md"}}]}'

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_send_event(payload: dict) -> None:
        sent_events.append(payload)

    actions = asyncio.run(
        manager.select_actions_with_repair(
            complete_chat=fake_complete_chat,
            tool_selector_system_prompt="system",
            tool_selector_prompt="prompt",
            model=None,
            extract_actions=fake_extract_actions,
            repair_tool_selection_json=fake_repair_tool_selection_json,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=fake_send_event,
            request_id="r1",
            session_id="s1",
            agent_name="head-agent",
        )
    )

    assert actions and actions[0]["tool"] == "read_file"
    assert any(stage == "tool_selection_repair_started" for stage, _ in lifecycle_events)
    assert any(stage == "tool_selection_repair_completed" for stage, _ in lifecycle_events)
    assert any(event.get("type") == "status" for event in sent_events)


def test_apply_action_pipeline_forces_run_command_for_intent() -> None:
    manager = ToolExecutionManager()

    async def fake_approve(*, actions: list[dict], allowed_tools: set[str]) -> set[str]:
        return set(allowed_tools)

    def fake_validate(actions: list[dict], allowed_tools: set[str]) -> tuple[list[dict], int]:
        return actions, 0

    async def fake_augment(**kwargs) -> list[dict]:
        return []

    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_emit_empty(reason: str, details: dict | None) -> None:
        raise AssertionError(f"unexpected empty emit: {reason} {details}")

    def fake_encode_blocked_tool_result(*, blocked_with_reason: str, message: str) -> str:
        return f"{blocked_with_reason}:{message}"

    actions, _, rejected_count, blocked_result = asyncio.run(
        manager.apply_action_pipeline(
            actions=[],
            effective_allowed_tools={"run_command"},
            user_message="run pytest",
            plan_text="",
            memory_context="",
            model=None,
            intent="execute_command",
            confidence="high",
            extracted_command="pytest -q",
            approve_blocked_process_tools_if_needed=fake_approve,
            validate_actions=fake_validate,
            augment_actions_if_needed=fake_augment,
            emit_lifecycle=fake_emit_lifecycle,
            emit_tool_selection_empty=fake_emit_empty,
            encode_blocked_tool_result=fake_encode_blocked_tool_result,
        )
    )

    assert rejected_count == 0
    assert blocked_result is None
    assert actions == [{"tool": "run_command", "args": {"command": "pytest -q"}}]
    assert any(stage == "tool_selection_followup_completed" for stage, _ in lifecycle_events)


def test_apply_action_pipeline_returns_missing_command_blocked_result() -> None:
    manager = ToolExecutionManager()

    async def fake_approve(*, actions: list[dict], allowed_tools: set[str]) -> set[str]:
        return set(allowed_tools)

    def fake_validate(actions: list[dict], allowed_tools: set[str]) -> tuple[list[dict], int]:
        return actions, 0

    async def fake_augment(**kwargs) -> list[dict]:
        return []

    empty_events: list[tuple[str, dict | None]] = []
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_empty(reason: str, details: dict | None) -> None:
        empty_events.append((reason, details))

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    def fake_encode_blocked_tool_result(*, blocked_with_reason: str, message: str) -> str:
        return f"{blocked_with_reason}:{message}"

    actions, _, rejected_count, blocked_result = asyncio.run(
        manager.apply_action_pipeline(
            actions=[],
            effective_allowed_tools={"run_command"},
            user_message="run command",
            plan_text="",
            memory_context="",
            model=None,
            intent="execute_command",
            confidence="high",
            extracted_command=None,
            approve_blocked_process_tools_if_needed=fake_approve,
            validate_actions=fake_validate,
            augment_actions_if_needed=fake_augment,
            emit_lifecycle=fake_emit_lifecycle,
            emit_tool_selection_empty=fake_emit_empty,
            encode_blocked_tool_result=fake_encode_blocked_tool_result,
        )
    )

    assert rejected_count == 0
    assert actions == []
    assert blocked_result is not None and blocked_result.startswith("missing_command:")
    assert any(reason == "missing_slots" for reason, _ in empty_events)
    assert any(stage == "tool_selection_completed" for stage, _ in lifecycle_events)


def test_run_tool_loop_executes_action_and_emits_audit_summary() -> None:
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []
    hook_calls: list[tuple[str, dict]] = []
    memory_entries: list[tuple[str, str]] = []

    async def fake_run_tool_with_policy(*, tool: str, args: dict, policy: object) -> str:
        return f"result for {tool}"

    async def fake_invoke_spawn_subrun_tool(*, args: dict, model: str | None) -> str:
        return "spawned"

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_send_event(payload: dict) -> None:
        return None

    async def fake_invoke_hooks(hook_name: str, payload: dict) -> None:
        hook_calls.append((hook_name, payload))

    def fake_memory_add(tool: str, clipped: str) -> None:
        memory_entries.append((tool, clipped))

    result = asyncio.run(
        manager.run_tool_loop(
            actions=[{"tool": "read_file", "args": {"path": "README.md"}}],
            effective_allowed_tools={"read_file"},
            config=ToolExecutionConfig(
                call_cap=5,
                time_cap_seconds=30.0,
                loop_warn_threshold=2,
                loop_critical_threshold=4,
                loop_circuit_breaker_threshold=8,
                generic_repeat_enabled=True,
                ping_pong_enabled=True,
                poll_no_progress_enabled=True,
                poll_no_progress_threshold=3,
                warning_bucket_size=10,
            ),
            user_message="read file",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool_with_policy,
            invoke_spawn_subrun_tool=fake_invoke_spawn_subrun_tool,
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda message: False,
            is_weather_lookup_task=lambda message: False,
            build_web_research_url=lambda message: "",
            memory_add=fake_memory_add,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=fake_send_event,
            invoke_hooks=fake_invoke_hooks,
        )
    )

    assert "[read_file]" in result
    assert "result for read_file" in result
    assert any(stage == "tool_loop_started" for stage, _ in lifecycle_events)
    assert any(stage == "tool_started" for stage, _ in lifecycle_events)
    assert any(stage == "tool_completed" for stage, _ in lifecycle_events)
    assert any(stage == "tool_audit_summary" for stage, _ in lifecycle_events)
    assert any(name == "before_tool_call" for name, _ in hook_calls)
    assert any(name == "after_tool_call" for name, _ in hook_calls)
    assert memory_entries == [("read_file", "result for read_file")]

    started_details = next(
        details
        for stage, details in lifecycle_events
        if stage == "tool_started" and isinstance(details, dict)
    )
    before_hook_payload = next(payload for name, payload in hook_calls if name == "before_tool_call")
    completed_details = next(
        details
        for stage, details in lifecycle_events
        if stage == "tool_completed" and isinstance(details, dict)
    )
    after_hook_payload = next(payload for name, payload in hook_calls if name == "after_tool_call")

    assert isinstance(started_details.get("call_id"), str) and started_details["call_id"]
    assert started_details.get("status") == "started"
    assert started_details.get("duration_ms") == 0
    assert before_hook_payload.get("call_id") == started_details.get("call_id")
    assert completed_details.get("call_id") == started_details.get("call_id")
    assert completed_details.get("status") == "ok"
    assert isinstance(completed_details.get("duration_ms"), int)
    assert after_hook_payload.get("status") == "ok"
    assert isinstance(after_hook_payload.get("duration_ms"), int)


def test_run_tool_loop_respects_call_budget() -> None:
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_send_event(payload: dict) -> None:
        return None

    async def fake_run_tool_with_policy(*, tool: str, args: dict, policy: object) -> str:
        return "should-not-run"

    result = asyncio.run(
        manager.run_tool_loop(
            actions=[{"tool": "read_file", "args": {"path": "README.md"}}],
            effective_allowed_tools={"read_file"},
            config=ToolExecutionConfig(
                call_cap=0,
                time_cap_seconds=30.0,
                loop_warn_threshold=2,
                loop_critical_threshold=4,
                loop_circuit_breaker_threshold=8,
                generic_repeat_enabled=True,
                ping_pong_enabled=True,
                poll_no_progress_enabled=True,
                poll_no_progress_threshold=3,
                warning_bucket_size=10,
            ),
            user_message="read file",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool_with_policy,
            invoke_spawn_subrun_tool=lambda **kwargs: asyncio.sleep(0),
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda message: False,
            is_weather_lookup_task=lambda message: False,
            build_web_research_url=lambda message: "",
            memory_add=lambda tool, clipped: None,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=fake_send_event,
            invoke_hooks=lambda hook_name, payload: asyncio.sleep(0),
        )
    )

    assert "tool call budget exceeded (0)" in result
    assert any(stage == "tool_budget_exceeded" for stage, _ in lifecycle_events)


def test_run_tool_loop_emits_error_code_and_category_on_tool_failed() -> None:
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []
    sent_events: list[dict] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_send_event(payload: dict) -> None:
        sent_events.append(payload)

    async def fake_run_tool_with_policy(*, tool: str, args: dict, policy: object) -> str:
        _ = (tool, args, policy)
        raise ToolExecutionError(
            "Command blocked by safety policy",
            error_code="command_policy_security",
            details={"category": "security", "leader": "bash"},
        )

    result = asyncio.run(
        manager.run_tool_loop(
            actions=[{"tool": "run_command", "args": {"command": "bash -c whoami"}}],
            effective_allowed_tools={"run_command"},
            config=ToolExecutionConfig(
                call_cap=5,
                time_cap_seconds=30.0,
                loop_warn_threshold=2,
                loop_critical_threshold=4,
                loop_circuit_breaker_threshold=8,
                generic_repeat_enabled=True,
                ping_pong_enabled=True,
                poll_no_progress_enabled=True,
                poll_no_progress_threshold=3,
                warning_bucket_size=10,
            ),
            user_message="run command",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool_with_policy,
            invoke_spawn_subrun_tool=lambda **kwargs: asyncio.sleep(0),
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda message: False,
            is_weather_lookup_task=lambda message: False,
            build_web_research_url=lambda message: "",
            memory_add=lambda tool, clipped: None,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=fake_send_event,
            invoke_hooks=lambda hook_name, payload: asyncio.sleep(0),
        )
    )

    assert "ERROR" in result
    failed_events = [
        details
        for stage, details in lifecycle_events
        if stage == "tool_failed" and isinstance(details, dict)
    ]
    assert failed_events
    assert failed_events[0].get("error_code") == "command_policy_security"
    assert failed_events[0].get("error_category") == "security"
    assert failed_events[0].get("status") == "error"
    assert isinstance(failed_events[0].get("duration_ms"), int)
    error_events = [evt for evt in sent_events if evt.get("type") == "error"]
    assert error_events
    assert error_events[0].get("error_code") == "command_policy_security"
    assert error_events[0].get("error_category") == "security"


def test_run_tool_loop_applies_steer_interrupt_checkpoint() -> None:
    manager = ToolExecutionManager()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def fake_emit_lifecycle(stage: str, details: dict | None) -> None:
        lifecycle_events.append((stage, details))

    async def fake_send_event(payload: dict) -> None:
        _ = payload

    async def fake_run_tool_with_policy(*, tool: str, args: dict, policy: object) -> str:
        _ = (tool, args, policy)
        return "ok"

    result = asyncio.run(
        manager.run_tool_loop(
            actions=[{"tool": "read_file", "args": {"path": "README.md"}}],
            effective_allowed_tools={"read_file"},
            config=ToolExecutionConfig(
                call_cap=5,
                time_cap_seconds=30.0,
                loop_warn_threshold=2,
                loop_critical_threshold=4,
                loop_circuit_breaker_threshold=8,
                generic_repeat_enabled=True,
                ping_pong_enabled=True,
                poll_no_progress_enabled=True,
                poll_no_progress_threshold=3,
                warning_bucket_size=10,
            ),
            user_message="read file",
            model=None,
            agent_name="head-agent",
            normalize_tool_name=lambda tool: tool,
            evaluate_action=lambda tool, args, allowed: (args, None),
            build_execution_policy=lambda tool: object(),
            run_tool_with_policy=fake_run_tool_with_policy,
            invoke_spawn_subrun_tool=lambda **kwargs: asyncio.sleep(0),
            should_retry_web_fetch_on_404=lambda error: False,
            is_web_research_task=lambda message: False,
            is_weather_lookup_task=lambda message: False,
            build_web_research_url=lambda message: "",
            memory_add=lambda tool, clipped: None,
            emit_lifecycle=fake_emit_lifecycle,
            send_event=fake_send_event,
            invoke_hooks=lambda hook_name, payload: asyncio.sleep(0),
            should_steer_interrupt=lambda: True,
        )
    )

    assert result == "__STEER_INTERRUPTED__"
    assert any(stage == "steer_detected" for stage, _ in lifecycle_events)
    assert any(stage == "steer_applied" for stage, _ in lifecycle_events)
