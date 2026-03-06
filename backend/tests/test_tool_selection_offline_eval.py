from __future__ import annotations

import asyncio

import pytest

from app.agent import CoderAgent, HeadAgent
from app.config import settings
from app.errors import ToolExecutionError
from app.orchestrator.step_executors import PlannerStepExecutor, SynthesizeStepExecutor, ToolStepExecutor

FULL_TOOLS = {
    "list_dir",
    "read_file",
    "write_file",
    "run_command",
    "apply_patch",
    "file_search",
    "grep_search",
    "list_code_usages",
    "get_changed_files",
    "start_background_command",
    "get_background_output",
    "kill_background_process",
    "web_fetch",
    "spawn_subrun",
}


def test_extract_actions_requires_strict_json_object() -> None:
    candidate = "[TOOL_CALL] tool => \"CreateFile\""
    agent = HeadAgent()

    actions, parse_error = agent._extract_actions(candidate)

    assert actions == []
    assert parse_error is not None


def test_extract_actions_empty_list_is_valid_no_action_signal() -> None:
    """CB-1: Das Modell darf explizit {"actions":[]} zurückgeben.
    Dies ist ein valides "keine Aktion"-Signal und darf NICHT als Parse-Fehler
    behandelt werden, der einen Repair-Call auslöst."""
    for raw in (
        '{"actions":[]}',
        '{"actions":[], "reasoning": "nothing to do"}',
        '  { "actions" : [] }  ',
    ):
        agent = HeadAgent()
        actions, parse_error = agent._extract_actions(raw)
        assert actions == [], f"Expected empty list for input: {raw!r}"
        assert parse_error is None, f"Expected no parse error for valid empty-actions JSON: {raw!r}"


def test_structured_alias_is_normalized_to_registry_tool() -> None:
    agent = HeadAgent()

    actions, parse_error = agent._extract_actions('{"actions":[{"tool":"CreateFile","args":{"path":"a.txt","content":"x"}}]}')

    assert parse_error is None
    normalized, rejected = agent._validate_actions(actions, FULL_TOOLS)
    assert rejected == 0
    assert normalized[0]["tool"] == "write_file"


def test_evaluator_blocks_dangerous_run_command() -> None:
    agent = HeadAgent()

    evaluated_args, error = agent._evaluate_action("run_command", {"command": "rm -rf /"}, FULL_TOOLS)

    assert evaluated_args == {}
    assert error == "command blocked by policy"


def test_evaluator_validates_spawn_subrun_payload() -> None:
    agent = HeadAgent()

    evaluated_args, error = agent._evaluate_action(
        "spawn_subrun",
        {
            "message": "scan repo for migration risks",
            "mode": "session",
            "agent_id": "coder-agent",
            "model": "minimax-m2:cloud",
            "timeout_seconds": 45,
            "tool_policy": {"allow": ["read_file"], "deny": ["write_file"]},
        },
        FULL_TOOLS,
    )

    assert error is None
    assert evaluated_args["message"] == "scan repo for migration risks"
    assert evaluated_args["mode"] == "session"
    assert evaluated_args["agent_id"] == "coder-agent"
    assert evaluated_args["timeout_seconds"] == 45


def test_execute_tools_supports_spawn_subrun_tool(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":[{"tool":"spawn_subrun","args":'
            '{"message":"analyze architecture","mode":"run","agent_id":"head-agent"}}]}'
        )

    async def fake_spawn_subrun_handler(**kwargs) -> str:
        assert kwargs["parent_session_id"] == "s-subrun"
        assert kwargs["parent_request_id"] == "r-subrun"
        assert kwargs["user_message"] == "analyze architecture"
        assert kwargs["mode"] == "run"
        assert kwargs["agent_id"] == "head-agent"
        return "subrun-123"

    original_complete_chat = agent.client.complete_chat
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent.set_spawn_subrun_handler(fake_spawn_subrun_handler)
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="delegate a background architecture check",
                plan_text="spawn helper",
                memory_context="user: delegate",
                session_id="s-subrun",
                request_id="r-subrun",
                send_event=send_event,
                model=None,
                allowed_tools={"spawn_subrun"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]

    assert "[spawn_subrun]" in result
    assert "spawned_subrun_id=subrun-123" in result
    assert "handover_contract=" in result
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "tool_completed" for evt in events)


def test_execute_tools_supports_structured_spawn_subrun_response(monkeypatch) -> None:
    agent = HeadAgent()

    async def send_event(_: dict) -> None:
        return

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":[{"tool":"spawn_subrun","args":'
            '{"message":"analyze architecture","mode":"run","agent_id":"head-agent"}}]}'
        )

    async def fake_spawn_subrun_handler(**kwargs) -> dict:
        return {
            "run_id": "subrun-structured",
            "mode": kwargs.get("mode", "run"),
            "agent_id": kwargs.get("agent_id", "head-agent"),
            "handover": {
                "terminal_reason": "subrun-running",
                "confidence": 0.0,
                "result": None,
            },
        }

    original_complete_chat = agent.client.complete_chat
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent.set_spawn_subrun_handler(fake_spawn_subrun_handler)
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="delegate a background architecture check",
                plan_text="spawn helper",
                memory_context="user: delegate",
                session_id="s-subrun-structured",
                request_id="r-subrun-structured",
                send_event=send_event,
                model=None,
                allowed_tools={"spawn_subrun"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]

    assert "[spawn_subrun]" in result
    assert "spawned_subrun_id=subrun-structured" in result
    assert '"terminal_reason": "subrun-running"' in result


def test_execute_tools_sanitizes_spawn_subrun_handover_and_scope_metadata(monkeypatch) -> None:
    agent = HeadAgent()

    async def send_event(_: dict) -> None:
        return

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":[{"tool":"spawn_subrun","args":'
            '{"message":"delegate","mode":"run","agent_id":"coder-agent"}}]}'
        )

    async def fake_spawn_subrun_handler(**kwargs) -> dict:
        return {
            "run_id": "subrun-sanitized",
            "mode": kwargs.get("mode", "run"),
            "agent_id": kwargs.get("agent_id", "head-agent"),
            "handover": {
                "terminal_reason": "subrun-running",
                "confidence": 1.7,
                "result": "ok",
                "secret": "must-not-leak",
            },
            "delegation_scope": {
                "source_agent_id": "head-agent",
                "target_agent_id": "coder-agent",
                "allowed": True,
                "reason": "cross_scope_allowlisted",
                "credentials": "must-not-leak",
            },
        }

    original_complete_chat = agent.client.complete_chat
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent.set_spawn_subrun_handler(fake_spawn_subrun_handler)
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="delegate",
                plan_text="spawn",
                memory_context="",
                session_id="s-subrun-sanitized",
                request_id="r-subrun-sanitized",
                send_event=send_event,
                model=None,
                allowed_tools={"spawn_subrun"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]

    assert "spawned_subrun_id=subrun-sanitized" in result
    assert '"confidence": 1.0' in result
    assert '"secret"' not in result
    assert "delegation_scope=" in result
    assert '"reason": "cross_scope_allowlisted"' in result
    assert '"credentials"' not in result


def test_run_command_retries_on_transient_errors(monkeypatch) -> None:
    """run_command is NOT in _TRANSIENT_RETRY_TOOLS (side-effects!),
    so a transient error must NOT trigger automatic retry."""
    agent = HeadAgent()
    attempts = {"count": 0}

    def fake_invoke(tool: str, args: dict) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ToolExecutionError("tool busy, try again")
        return "ok"

    monkeypatch.setattr(agent, "_invoke_tool", fake_invoke)

    with pytest.raises(ToolExecutionError):
        asyncio.run(
            agent._run_tool_with_policy(
                tool="run_command",
                args={"command": "echo hi"},
                policy=agent._build_execution_policy("run_command"),
            )
        )

    assert attempts["count"] == 1  # no retry for side-effectful tool


def test_run_tool_with_policy_accepts_sync_invoke_returning_awaitable(monkeypatch) -> None:
    agent = HeadAgent()

    async def _awaitable_result() -> str:
        return "ok-awaitable"

    def fake_invoke(tool: str, args: dict):
        _ = (tool, args)
        return _awaitable_result()

    monkeypatch.setattr(agent, "_invoke_tool", fake_invoke)

    result = asyncio.run(
        agent._run_tool_with_policy(
            tool="run_command",
            args={"command": "echo hi"},
            policy=agent._build_execution_policy("run_command"),
        )
    )

    assert result == "ok-awaitable"


def test_run_command_policy_unsupported_can_be_approved_and_retried(monkeypatch) -> None:
    agent = HeadAgent()
    attempts = {"count": 0}
    approval_calls = {"count": 0}
    events: list[dict] = []

    def fake_invoke(tool: str, args: dict) -> str:
        _ = (tool, args)
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ToolExecutionError(
                "Command 'ng' is not allowed by command allowlist.",
                error_code="command_policy_unsupported",
                details={"category": "unsupported", "leader": "ng"},
            )
        return "ok-ng"

    async def fake_policy_handler(*, send_event, session_id, request_id, agent_name, tool, resource, display_text):
        _ = (send_event, session_id, request_id, agent_name, tool, resource, display_text)
        approval_calls["count"] += 1
        return True

    async def fake_send_event(payload: dict) -> None:
        events.append(payload)

    monkeypatch.setattr(agent, "_invoke_tool", fake_invoke)
    agent.set_policy_approval_handler(fake_policy_handler)

    send_event_token = agent._active_send_event_context.set(fake_send_event)
    session_token = agent._active_session_id_context.set("sess-1")
    request_token = agent._active_request_id_context.set("req-1")
    try:
        result = asyncio.run(
            agent._run_tool_with_policy(
                tool="run_command",
                args={"command": "ng version"},
                policy=agent._build_execution_policy("run_command"),
            )
        )
    finally:
        agent._active_request_id_context.reset(request_token)
        agent._active_session_id_context.reset(session_token)
        agent._active_send_event_context.reset(send_event_token)

    assert result == "ok-ng"
    assert attempts["count"] == 2
    assert approval_calls["count"] == 1
    assert any(
        event.get("type") == "lifecycle"
        and event.get("stage") == "policy_override_decision"
        and event.get("details", {}).get("approved") is True
        for event in events
    )


def test_offline_tool_call_accuracy_curated_set() -> None:
    agent = HeadAgent()
    cases = [
        ({"tool": "list_dir", "args": {}}, "list_dir"),
        ({"tool": "CreateFile", "args": {"path": "x.txt", "content": "y"}}, "write_file"),
        ({"tool": "read_file", "args": {"path": "README.md"}}, "read_file"),
        ({"tool": "run_command", "args": {"command": "echo hi"}}, "run_command"),
        ({"tool": "unknown", "args": {}}, None),
    ]

    correct = 0
    for action, expected_tool in cases:
        normalized_actions, rejected = agent._validate_actions([action], FULL_TOOLS)
        if expected_tool is None:
            if rejected == 1:
                correct += 1
            continue
        if rejected != 0:
            continue
        normalized = normalized_actions[0]
        evaluated_args, eval_error = agent._evaluate_action(normalized["tool"], normalized["args"], FULL_TOOLS)
        if eval_error is None and normalized["tool"] == expected_tool and isinstance(evaluated_args, dict):
            correct += 1

    accuracy = correct / len(cases)
    assert accuracy >= 0.8


def test_final_response_sanitizer_removes_tool_call_artifacts() -> None:
    agent = HeadAgent()
    raw = (
        "Done.\n"
        "[TOOL_CALL] {tool => \"list_dir\", args => { --path \".\" }} [/TOOL_CALL]\n"
        "Next steps."
    )

    sanitized = agent._sanitize_final_response(raw)

    assert "[TOOL_CALL]" not in sanitized
    assert "tool =>" not in sanitized
    assert "Done." in sanitized
    assert "Next steps." in sanitized


def test_augment_actions_adds_followup_for_file_task() -> None:
    agent = HeadAgent()

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> list[dict]:
        original = agent.client.complete_chat

        async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
            if "include write_file" in user_prompt.lower():
                return '{"actions":[{"tool":"write_file","args":{"path":"calculator.html","content":"<html></html>"}}]}'
            return await original(system_prompt, user_prompt, model)

        agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
        try:
            return await agent._augment_actions_if_needed(
                actions=[],
                user_message="create a file for a calculator with html css and javascript",
                plan_text="create files",
                memory_context="- user: create a file for calculator",
                send_event=send_event,
                request_id="r1",
                session_id="s1",
                model=None,
                allowed_tools=FULL_TOOLS,
            )
        finally:
            agent.client.complete_chat = original  # type: ignore[method-assign]

    result_actions = asyncio.run(run_case())

    assert any(action.get("tool") == "write_file" for action in result_actions)


def test_is_file_creation_task_requires_explicit_file_phrase() -> None:
    agent = HeadAgent()

    assert agent._is_file_creation_task("Please explain JavaScript closures") is False
    assert agent._is_file_creation_task("create a file with hello world") is True


def test_augment_actions_followup_uses_prompt_profile_tool_selector_prompt(monkeypatch) -> None:
    agent = CoderAgent()
    monkeypatch.setattr(settings, "agent_tool_selector_prompt", "GLOBAL_SENTINEL_PROMPT_SHOULD_NOT_BE_USED")
    captured_system_prompts: list[str] = []

    async def send_event(_: dict) -> None:
        return

    async def run_case() -> list[dict]:
        original = agent.client.complete_chat

        async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
            captured_system_prompts.append(system_prompt)
            return '{"actions":[{"tool":"write_file","args":{"path":"x.txt","content":"ok"}}]}'

        agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
        try:
            return await agent._augment_actions_if_needed(
                actions=[],
                user_message="create a file with content",
                plan_text="create file",
                memory_context="- user: create a file",
                send_event=send_event,
                request_id="r-prompt",
                session_id="s-prompt",
                model=None,
                allowed_tools=FULL_TOOLS,
            )
        finally:
            agent.client.complete_chat = original  # type: ignore[method-assign]

    result_actions = asyncio.run(run_case())

    assert any(action.get("tool") == "write_file" for action in result_actions)
    assert captured_system_prompts == [agent.prompt_profile.tool_selector_prompt]
    assert captured_system_prompts[0] != "GLOBAL_SENTINEL_PROMPT_SHOULD_NOT_BE_USED"


def test_effective_tool_policy_combines_global_and_per_run(monkeypatch) -> None:
    agent = HeadAgent()
    monkeypatch.setattr(settings, "agent_tools_allow", ["read_file", "run_command", "write_file"])
    monkeypatch.setattr(settings, "agent_tools_deny", ["run_command"])

    allowed = agent._resolve_effective_allowed_tools(
        {
            "allow": ["read_file", "run_command"],
            "deny": ["read_file"],
        }
    )

    assert allowed == set()


def test_effective_tool_policy_ignores_unknown_only_request_allow(monkeypatch) -> None:
    agent = HeadAgent()
    monkeypatch.setattr(settings, "agent_tools_allow", ["read_file", "list_dir"])
    monkeypatch.setattr(settings, "agent_tools_deny", [])

    allowed = agent._resolve_effective_allowed_tools(
        {
            "allow": ["totally_unknown_tool"],
        }
    )

    assert allowed == {"read_file", "list_dir"}


def test_effective_tool_policy_blocks_vision_tool_when_disabled(monkeypatch) -> None:
    agent = HeadAgent()
    monkeypatch.setattr(settings, "vision_enabled", False)
    monkeypatch.setattr(settings, "agent_tools_allow", ["read_file", "analyze_image"])
    monkeypatch.setattr(settings, "agent_tools_deny", [])

    allowed = agent._resolve_effective_allowed_tools(
        {
            "allow": ["analyze_image", "read_file"],
        }
    )

    assert "analyze_image" not in allowed
    assert allowed == {"read_file"}


def test_validate_actions_respects_active_tool_policy() -> None:
    agent = HeadAgent()
    actions, parse_error = agent._extract_actions('{"actions":[{"tool":"write_file","args":{"path":"a.txt","content":"x"}}]}')
    assert parse_error is None

    validated, rejected = agent._validate_actions(actions, {"read_file"})

    assert validated == []
    assert rejected == 1


def test_hooks_are_called_for_tool_execution() -> None:
    agent = HeadAgent()
    captured: list[tuple[str, dict]] = []

    class _Hook:
        async def before_prompt_build(self, payload: dict) -> None:
            captured.append(("before_prompt_build", payload))

        async def before_tool_call(self, payload: dict) -> None:
            captured.append(("before_tool_call", payload))

        async def after_tool_call(self, payload: dict) -> None:
            captured.append(("after_tool_call", payload))

    agent.register_hook(_Hook())

    async def send_event(_: dict) -> None:
        return

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return '{"actions":[{"tool":"read_file","args":{"path":"README.md"}}]}'

    def fake_invoke_tool(tool: str, args: dict) -> str:
        return "content"

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="read project readme",
                plan_text="inspect docs",
                memory_context="user: readme",
                session_id="s1",
                request_id="r1",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "[read_file]" in result
    assert any(name == "before_prompt_build" and payload.get("prompt_type") == "tool_selection" for name, payload in captured)
    assert any(name == "before_tool_call" and payload.get("tool") == "read_file" for name, payload in captured)
    assert any(name == "after_tool_call" and payload.get("tool") == "read_file" and payload.get("status") == "ok" for name, payload in captured)


def test_hook_agent_end_is_called_on_run_completion() -> None:
    agent = HeadAgent()
    captured: list[tuple[str, dict]] = []

    class _Hook:
        async def agent_end(self, payload: dict) -> None:
            captured.append(("agent_end", payload))

    agent.register_hook(_Hook())

    async def send_event(_: dict) -> None:
        return

    async def fake_plan_execute(payload, model=None):
        return "plan"

    async def fake_tool_execute(
        payload,
        session_id,
        request_id,
        send_event,
        model,
        allowed_tools,
        should_steer_interrupt=None,
    ):
        return "[run_command]\necho done"

    async def fake_synth_execute(payload, session_id, request_id, send_event, model):
        return "final response"

    original_plan_executor = agent.plan_step_executor
    original_tool_executor = agent.tool_step_executor
    original_synth_executor = agent.synthesize_step_executor
    agent.plan_step_executor = PlannerStepExecutor(execute_fn=fake_plan_execute)
    agent.tool_step_executor = ToolStepExecutor(execute_fn=fake_tool_execute)
    agent.synthesize_step_executor = SynthesizeStepExecutor(execute_fn=fake_synth_execute)
    try:
        result = asyncio.run(
            agent.run(
                user_message="build feature",
                send_event=send_event,
                session_id="sess1",
                request_id="req1",
                model="llama",
                tool_policy=None,
            )
        )
    finally:
        agent.plan_step_executor = original_plan_executor
        agent.tool_step_executor = original_tool_executor
        agent.synthesize_step_executor = original_synth_executor

    assert result == "final response"
    assert any(name == "agent_end" and payload.get("status") == "completed" for name, payload in captured)


def test_reply_shaping_suppresses_no_reply_token() -> None:
    agent = HeadAgent()

    shaped = agent._shape_final_response("NO_REPLY", tool_results="[read_file]\ncontent")

    assert shaped.suppressed is True
    assert shaped.reason == "no_reply_token"
    assert shaped.text == ""


def test_reply_shaping_deduplicates_tool_confirmations() -> None:
    agent = HeadAgent()
    text = (
        "read_file completed successfully\n"
        "read_file completed successfully\n"
        "Next step: implement change"
    )

    shaped = agent._shape_final_response(text, tool_results="[read_file]\nfoo")

    assert shaped.suppressed is False
    assert shaped.deduped_lines == 1
    assert shaped.text.count("read_file completed successfully") == 1


def test_web_research_task_detection_positive() -> None:
    agent = HeadAgent()

    assert agent._is_web_research_task("can you search on the web for the best ai models?") is True


def test_web_research_task_detection_does_not_trigger_on_latest_framework_request() -> None:
    agent = HeadAgent()

    assert agent._is_web_research_task("make a to do app with the latest angular version") is False


def test_synthesis_task_type_prefers_implementation_over_generic_latest_signal() -> None:
    agent = HeadAgent()

    resolved = agent._resolve_synthesis_task_type(
        user_message="implement a todo app with the latest angular version",
        tool_results="",
    )

    assert resolved == "implementation"


def test_implementation_evidence_requires_successful_write_or_command() -> None:
    agent = HeadAgent()

    assert agent._has_implementation_evidence("[write_file]\ncreated app component") is True
    assert agent._has_implementation_evidence("[run_command] ERROR: command not allowed") is False
    assert agent._has_implementation_evidence("[read_file]\ncontent") is False


def test_orchestration_evidence_accepts_subrun_announce_complete() -> None:
    agent = HeadAgent()

    tool_results = "[spawn_subrun_announce]\n[subrun_announce] spawned_subrun_id=run-1 terminal_reason=subrun-complete"

    assert agent._has_orchestration_evidence(tool_results) is True


def test_synthesis_task_type_uses_last_terminal_reason_complete_wins() -> None:
    agent = HeadAgent()

    tool_results = (
        "[spawn_subrun]\nspawned_subrun_id=run-1 terminal_reason=subrun-error\n"
        "[spawn_subrun_announce]\nspawned_subrun_id=run-1 terminal_reason=subrun-complete"
    )

    resolved = agent._resolve_synthesis_task_type(
        user_message="delegate task",
        tool_results=tool_results,
    )

    assert resolved == "orchestration"


def test_synthesis_task_type_uses_last_terminal_reason_failure_wins() -> None:
    agent = HeadAgent()

    tool_results = (
        "[spawn_subrun]\nspawned_subrun_id=run-1 terminal_reason=subrun-complete\n"
        "[spawn_subrun_announce]\nspawned_subrun_id=run-1 terminal_reason=subrun-timeout"
    )

    resolved = agent._resolve_synthesis_task_type(
        user_message="delegate task",
        tool_results=tool_results,
    )

    assert resolved == "orchestration_failed"


def test_intent_gate_does_not_treat_build_research_as_shell_command() -> None:
    agent = HeadAgent()

    decision = agent._detect_intent_gate("build a big research report about llms and write it to markdown")

    assert decision.intent is None
    assert decision.extracted_command is None


def test_augment_actions_adds_spawn_subrun_for_orchestration_request() -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    result_actions = asyncio.run(
        agent._augment_actions_if_needed(
            actions=[],
            user_message="orchestrate a big parallel research about llms with authoritative sources",
            plan_text="delegate deep research",
            memory_context="- user: orchestrate deep research",
            send_event=send_event,
            request_id="r-subrun-followup",
            session_id="s-subrun-followup",
            model=None,
            allowed_tools=FULL_TOOLS,
        )
    )

    assert any(action.get("tool") == "spawn_subrun" for action in result_actions)
    spawn_action = next(action for action in result_actions if action.get("tool") == "spawn_subrun")
    assert str(spawn_action.get("args", {}).get("message", "")).startswith("orchestrate a big parallel research")
    assert any(
        payload.get("type") == "lifecycle"
        and payload.get("stage") == "tool_selection_followup_completed"
        and payload.get("details", {}).get("reason") == "orchestration_without_spawn_subrun"
        for payload in events
    )


def test_augment_actions_adds_web_fetch_for_web_research() -> None:
    agent = HeadAgent()

    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    result_actions = asyncio.run(
        agent._augment_actions_if_needed(
            actions=[],
            user_message="can you search on the web for the best ai models?",
            plan_text="find best ai models",
            memory_context="- user: search web",
            send_event=send_event,
            request_id="r-web",
            session_id="s-web",
            model=None,
            allowed_tools=FULL_TOOLS,
        )
    )

    assert any(action.get("tool") == "web_fetch" for action in result_actions)
    web_action = next(action for action in result_actions if action.get("tool") == "web_fetch")
    assert "url" in web_action.get("args", {})
    assert str(web_action["args"]["url"]).startswith("https://duckduckgo.com/html/?q=")
    assert any(
        payload.get("type") == "lifecycle"
        and payload.get("stage") == "tool_selection_followup_completed"
        and payload.get("details", {}).get("reason") in {"web_research_without_web_fetch", "web_research_without_search_tool"}
        for payload in events
    )


def test_execute_tools_loop_detector_warns_and_blocks(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        return "content"

    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 2)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 3)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="read readme repeatedly",
                plan_text="read file",
                memory_context="user: read readme",
                session_id="s-loop",
                request_id="r-loop",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert result.count("[read_file]") >= 2
    assert "REJECTED: tool loop blocked" in result
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "tool_loop_warn" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "tool_loop_blocked" for evt in events)
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_blocked"
        and evt.get("details", {}).get("reason_type") == "generic_repeat"
        for evt in events
    )
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "tool_audit_summary" for evt in events)


def test_execute_tools_loop_detector_poll_no_progress_ignores_different_tool_signatures(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        return "no-progress"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_poll_no_progress_threshold", 2)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="do two checks",
                plan_text="check repository",
                memory_context="user: check repository",
                session_id="s-loop-poll",
                request_id="r-loop-poll",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "poll_no_progress streak" not in result
    assert not any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_poll_no_progress_blocked"
        for evt in events
    )


def test_execute_tools_loop_detector_poll_no_progress_blocks_same_signature(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        return "no-progress"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_poll_no_progress_threshold", 2)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="do two checks",
                plan_text="check repository",
                memory_context="user: check repository",
                session_id="s-loop-poll-same",
                request_id="r-loop-poll-same",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "poll_no_progress streak" in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_poll_no_progress_blocked"
        and evt.get("details", {}).get("reason_type") == "poll_no_progress"
        for evt in events
    )


def test_execute_tools_ping_pong_requires_no_progress_evidence(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    read_count = {"count": 0}

    def fake_invoke_tool(tool: str, args: dict) -> str:
        if tool == "read_file":
            read_count["count"] += 1
            return f"read-content-{read_count['count']}"
        return "dir-content"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="alternate checks",
                plan_text="alternate read/list checks",
                memory_context="user: alternate checks",
                session_id="s-ping-pong-no-evidence",
                request_id="r-ping-pong-no-evidence",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "ping-pong pattern detected" not in result
    assert not any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_ping_pong_blocked"
        for evt in events
    )


def test_execute_tools_ping_pong_blocks_with_no_progress_evidence(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        if tool == "read_file":
            return "same-read"
        return "same-dir"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="alternate checks",
                plan_text="alternate read/list checks",
                memory_context="user: alternate checks",
                session_id="s-ping-pong-evidence",
                request_id="r-ping-pong-evidence",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "ping-pong pattern detected" in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_ping_pong_blocked"
        and evt.get("details", {}).get("reason_type") == "ping_pong"
        and evt.get("details", {}).get("no_progress_evidence") is True
        for evt in events
    )


def test_execute_tools_ping_pong_warns_before_critical(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        if tool == "read_file":
            return "same-read"
        return "same-dir"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 4)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 6)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="alternate checks",
                plan_text="alternate read/list checks",
                memory_context="user: alternate checks",
                session_id="s-ping-pong-warn",
                request_id="r-ping-pong-warn",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "ping-pong pattern detected" not in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_ping_pong_warn"
        and evt.get("details", {}).get("reason_type") == "ping_pong"
        and evt.get("details", {}).get("alternating_count") == 4
        for evt in events
    )
    assert not any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_ping_pong_blocked"
        for evt in events
    )


def test_execute_tools_ping_pong_blocks_at_critical_threshold(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        if tool == "read_file":
            return "same-read"
        return "same-dir"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 4)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 6)
    monkeypatch.setattr(settings, "run_tool_call_cap", 12)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="alternate checks",
                plan_text="alternate read/list checks",
                memory_context="user: alternate checks",
                session_id="s-ping-pong-critical",
                request_id="r-ping-pong-critical",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "ping-pong pattern detected" in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_ping_pong_warn"
        and evt.get("details", {}).get("alternating_count") == 4
        for evt in events
    )
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_loop_ping_pong_blocked"
        and evt.get("details", {}).get("critical_threshold") == 6
        and evt.get("details", {}).get("alternating_count") == 6
        for evt in events
    )


def test_execute_tools_ping_pong_warn_is_deduplicated(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        if tool == "read_file":
            return "read-changing"
        return "dir-changing"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 4)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 99)
    monkeypatch.setattr(settings, "run_tool_call_cap", 20)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        _ = asyncio.run(
            agent._execute_tools(
                user_message="alternate checks",
                plan_text="alternate read/list checks",
                memory_context="user: alternate checks",
                session_id="s-ping-pong-warn-dedupe",
                request_id="r-ping-pong-warn-dedupe",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    warn_events = [
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "tool_loop_ping_pong_warn"
    ]
    assert len(warn_events) == 1
    assert isinstance(warn_events[0].get("details", {}).get("warning_key"), str)
    assert warn_events[0].get("details", {}).get("warning_key", "").startswith("pingpong:")


def test_execute_tools_generic_repeat_warning_bucket_progression(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"README.md"}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        return "content"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 2)
    monkeypatch.setattr(settings, "tool_loop_warning_bucket_size", 2)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 99)
    monkeypatch.setattr(settings, "run_tool_call_cap", 10)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        _ = asyncio.run(
            agent._execute_tools(
                user_message="repeat readme",
                plan_text="repeat read",
                memory_context="user: repeat readme",
                session_id="s-generic-bucket",
                request_id="r-generic-bucket",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    warn_events = [
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "tool_loop_warn"
    ]
    bucket_indices = [
        evt.get("details", {}).get("warning_bucket_index")
        for evt in warn_events
    ]

    assert len(warn_events) == 2
    assert bucket_indices == [1, 2]
    assert all(
        evt.get("details", {}).get("warning_bucket_size") == 2
        for evt in warn_events
    )


def test_execute_tools_ping_pong_warning_bucket_progression(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}},'
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"list_dir","args":{"path":"."}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        if tool == "read_file":
            return "read-stable"
        return "dir-stable"

    monkeypatch.setattr(settings, "tool_loop_detector_generic_repeat_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_detector_ping_pong_enabled", True)
    monkeypatch.setattr(settings, "tool_loop_detector_poll_no_progress_enabled", False)
    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 4)
    monkeypatch.setattr(settings, "tool_loop_warning_bucket_size", 2)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 99)
    monkeypatch.setattr(settings, "run_tool_call_cap", 20)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        _ = asyncio.run(
            agent._execute_tools(
                user_message="alternate checks",
                plan_text="alternate read/list checks",
                memory_context="user: alternate checks",
                session_id="s-ping-pong-bucket",
                request_id="r-ping-pong-bucket",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file", "list_dir"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    warn_events = [
        evt
        for evt in events
        if evt.get("type") == "lifecycle" and evt.get("stage") == "tool_loop_ping_pong_warn"
    ]
    bucket_indices = [
        evt.get("details", {}).get("warning_bucket_index")
        for evt in warn_events
    ]

    assert len(warn_events) >= 2
    assert bucket_indices == sorted(bucket_indices)
    assert warn_events[0].get("details", {}).get("warning_bucket_index") == 1
    assert all(
        evt.get("details", {}).get("warning_bucket_size") == 2
        for evt in warn_events
    )


def test_execute_tools_budget_blocks_excess_calls(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return (
            '{"actions":['
            '{"tool":"read_file","args":{"path":"README.md"}},'
            '{"tool":"read_file","args":{"path":"instructions.md"}}]}'
        )

    def fake_invoke_tool(tool: str, args: dict) -> str:
        return "content"

    monkeypatch.setattr(settings, "tool_loop_warn_threshold", 99)
    monkeypatch.setattr(settings, "tool_loop_critical_threshold", 100)
    monkeypatch.setattr(settings, "run_tool_call_cap", 1)
    monkeypatch.setattr(settings, "run_tool_time_cap_seconds", 60.0)

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="read two files",
                plan_text="read files",
                memory_context="user: read files",
                session_id="s-budget",
                request_id="r-budget",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "REJECTED: tool call budget exceeded" in result
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "tool_budget_exceeded" for evt in events)
    assert any(evt.get("type") == "lifecycle" and evt.get("stage") == "tool_audit_summary" for evt in events)


def test_execute_tools_blocks_when_command_slot_missing() -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    result = asyncio.run(
        agent._execute_tools(
            user_message="run",
            plan_text="execute requested command",
            memory_context="user: run",
            session_id="s-cmd-missing",
            request_id="r-cmd-missing",
            send_event=send_event,
            model=None,
            allowed_tools={"run_command"},
        )
    )

    parsed = agent._parse_blocked_tool_result(result)
    assert isinstance(parsed, dict)
    assert parsed.get("blocked_with_reason") == "missing_command"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_selection_empty"
        and evt.get("details", {}).get("reason") == "missing_slots"
        for evt in events
    )


def test_execute_tools_allows_run_command_with_policy_approval(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_policy_approval_handler(**kwargs) -> bool:
        return kwargs.get("tool") == "run_command"

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return '{"actions":[]}'

    def fake_invoke_tool(tool: str, args: dict) -> str:
        assert tool == "run_command"
        assert args.get("command") == "pytest -q"
        return "approved-ok"

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    agent.set_policy_approval_handler(fake_policy_approval_handler)
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="run `pytest -q`",
                plan_text="execute tests",
                memory_context="user: run tests",
                session_id="s-cmd-approval",
                request_id="r-cmd-approval",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "[run_command]" in result
    assert "approved-ok" in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "policy_override_decision"
        and evt.get("details", {}).get("tool") == "run_command"
        and evt.get("details", {}).get("approved") is True
        for evt in events
    )


def test_execute_tools_allows_spawn_subrun_with_policy_approval(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []
    captured_modes: list[str] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return '{"actions":[{"tool":"spawn_subrun","args":{"message":"orchestrate deep research","mode":"run","agent_id":"head-agent"}}]}'

    async def fake_policy_approval_handler(**kwargs) -> bool:
        return kwargs.get("tool") == "spawn_subrun"

    async def fake_spawn_subrun_handler(**kwargs) -> str:
        captured_modes.append(str(kwargs.get("mode") or ""))
        return "subrun-approved"

    original_complete_chat = agent.client.complete_chat
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent.set_policy_approval_handler(fake_policy_approval_handler)
    agent.set_spawn_subrun_handler(fake_spawn_subrun_handler)
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="orchestrate deep research",
                plan_text="spawn helper",
                memory_context="user: orchestration",
                session_id="s-subrun-approval",
                request_id="r-subrun-approval",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]

    assert "[spawn_subrun]" in result
    assert "spawned_subrun_id=subrun-approved" in result
    assert "handover_contract=" in result
    assert captured_modes
    assert captured_modes[-1] == "wait"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "policy_override_decision"
        and evt.get("details", {}).get("tool") == "spawn_subrun"
        and evt.get("details", {}).get("approved") is True
        for evt in events
    )


def test_execute_tools_forces_single_run_command_when_intent_is_clear(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return '{"actions":[]}'

    def fake_invoke_tool(tool: str, args: dict) -> str:
        assert tool == "run_command"
        assert args.get("command") == "pytest -q"
        return "ok"

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="run `pytest -q`",
                plan_text="execute tests",
                memory_context="user: run tests",
                session_id="s-cmd-force",
                request_id="r-cmd-force",
                send_event=send_event,
                model=None,
                allowed_tools={"run_command"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert "[run_command]" in result
    assert "ok" in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_selection_followup_completed"
        and evt.get("details", {}).get("reason") == "intent_execute_command_forced_action"
        for evt in events
    )


def test_execute_tools_blocks_on_policy_for_execute_command_intent() -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    result = asyncio.run(
        agent._execute_tools(
            user_message="run `pytest -q`",
            plan_text="execute tests",
            memory_context="user: run tests",
            session_id="s-cmd-policy",
            request_id="r-cmd-policy",
            send_event=send_event,
            model=None,
            allowed_tools={"read_file"},
        )
    )

    parsed = agent._parse_blocked_tool_result(result)
    assert isinstance(parsed, dict)
    assert parsed.get("blocked_with_reason") == "run_command_not_allowed"
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_selection_empty"
        and evt.get("details", {}).get("reason") == "policy_block"
        for evt in events
    )


def test_execute_tools_emits_tool_selection_empty_for_ambiguous_input(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return '{"actions":[]}'

    original_complete_chat = agent.client.complete_chat
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="help",
                plan_text="provide support",
                memory_context="user: help",
                session_id="s-empty-amb",
                request_id="r-empty-amb",
                send_event=send_event,
                model=None,
                allowed_tools={"read_file"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]

    assert result == ""
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_selection_empty"
        and evt.get("details", {}).get("reason") == "ambiguous_input"
        for evt in events
    )


def test_head_and_coder_agents_use_distinct_prompt_profiles() -> None:
    head = HeadAgent()
    coder = CoderAgent()

    assert head.role == "head-agent"
    assert coder.role == "coding-agent"
    assert head.prompt_profile.plan_prompt == settings.head_agent_plan_prompt
    assert coder.prompt_profile.plan_prompt == settings.coder_agent_plan_prompt
    assert head.prompt_profile.final_prompt == settings.head_agent_final_prompt
    assert coder.prompt_profile.final_prompt == settings.coder_agent_final_prompt


def test_execute_tools_web_fetch_404_retries_with_fallback(monkeypatch) -> None:
    agent = HeadAgent()
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        return '{"actions":[{"tool":"web_fetch","args":{"url":"https://example.com/404","max_chars":12000}}]}'

    attempts = {"count": 0}

    def fake_invoke_tool(tool: str, args: dict) -> str:
        assert tool == "web_fetch"
        attempts["count"] += 1
        url = str(args.get("url") or "")
        if attempts["count"] == 1:
            raise ToolExecutionError("web_fetch failed for url=https://example.com/404: HTTP Error 404: Not Found")
        assert "duckduckgo.com/html/?q=" in url
        return f"source_url: {url}\ncontent_type: text/html\ncontent:\nweather ok"

    original_complete_chat = agent.client.complete_chat
    original_invoke = agent._invoke_tool
    agent.client.complete_chat = fake_complete_chat  # type: ignore[method-assign]
    agent._invoke_tool = fake_invoke_tool  # type: ignore[method-assign]
    try:
        result = asyncio.run(
            agent._execute_tools(
                user_message="what is the weather in berlin germany",
                plan_text="fetch weather",
                memory_context="user: weather in berlin",
                session_id="s-web-retry",
                request_id="r-web-retry",
                send_event=send_event,
                model=None,
                allowed_tools={"web_fetch"},
            )
        )
    finally:
        agent.client.complete_chat = original_complete_chat  # type: ignore[method-assign]
        agent._invoke_tool = original_invoke  # type: ignore[method-assign]

    assert attempts["count"] == 2
    assert "[web_fetch]" in result
    assert "weather ok" in result
    assert any(
        evt.get("type") == "lifecycle"
        and evt.get("stage") == "tool_retry_completed"
        and evt.get("details", {}).get("reason") == "http_404"
        for evt in events
    )
