from __future__ import annotations

import asyncio

from app.agent import HeadCodingAgent
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
}


def test_extract_actions_requires_strict_json_object() -> None:
    candidate = "[TOOL_CALL] tool => \"CreateFile\""
    agent = HeadCodingAgent()

    actions, parse_error = agent._extract_actions(candidate)

    assert actions == []
    assert parse_error is not None


def test_structured_alias_is_normalized_to_registry_tool() -> None:
    agent = HeadCodingAgent()

    actions, parse_error = agent._extract_actions('{"actions":[{"tool":"CreateFile","args":{"path":"a.txt","content":"x"}}]}')

    assert parse_error is None
    normalized, rejected = agent._validate_actions(actions, FULL_TOOLS)
    assert rejected == 0
    assert normalized[0]["tool"] == "write_file"


def test_evaluator_blocks_dangerous_run_command() -> None:
    agent = HeadCodingAgent()

    evaluated_args, error = agent._evaluate_action("run_command", {"command": "rm -rf /"}, FULL_TOOLS)

    assert evaluated_args == {}
    assert error == "command blocked by policy"


def test_run_command_retries_on_transient_errors(monkeypatch) -> None:
    agent = HeadCodingAgent()
    attempts = {"count": 0}

    def fake_invoke(tool: str, args: dict) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ToolExecutionError("tool busy, try again")
        return "ok"

    monkeypatch.setattr(agent, "_invoke_tool", fake_invoke)

    result = asyncio.run(
        agent._run_tool_with_policy(
            tool="run_command",
            args={"command": "echo hi"},
            policy=agent._build_execution_policy("run_command"),
        )
    )

    assert result == "ok"
    assert attempts["count"] == 2


def test_offline_tool_call_accuracy_curated_set() -> None:
    agent = HeadCodingAgent()
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
    agent = HeadCodingAgent()
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
    agent = HeadCodingAgent()

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
                user_message="make a calculator with html css and javascript",
                plan_text="create files",
                memory_context="- user: make calculator",
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


def test_effective_tool_policy_combines_global_and_per_run(monkeypatch) -> None:
    agent = HeadCodingAgent()
    monkeypatch.setattr(settings, "agent_tools_allow", ["read_file", "run_command", "write_file"])
    monkeypatch.setattr(settings, "agent_tools_deny", ["run_command"])

    allowed = agent._resolve_effective_allowed_tools(
        {
            "allow": ["read_file", "run_command"],
            "deny": ["read_file"],
        }
    )

    assert allowed == set()


def test_validate_actions_respects_active_tool_policy() -> None:
    agent = HeadCodingAgent()
    actions, parse_error = agent._extract_actions('{"actions":[{"tool":"write_file","args":{"path":"a.txt","content":"x"}}]}')
    assert parse_error is None

    validated, rejected = agent._validate_actions(actions, {"read_file"})

    assert validated == []
    assert rejected == 1


def test_hooks_are_called_for_tool_execution() -> None:
    agent = HeadCodingAgent()
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
    agent = HeadCodingAgent()
    captured: list[tuple[str, dict]] = []

    class _Hook:
        async def agent_end(self, payload: dict) -> None:
            captured.append(("agent_end", payload))

    agent.register_hook(_Hook())

    async def send_event(_: dict) -> None:
        return

    async def fake_plan_execute(payload, model=None):
        return "plan"

    async def fake_tool_execute(payload, session_id, request_id, send_event, model, allowed_tools):
        return ""

    async def fake_synth_execute(payload, session_id, request_id, send_event, model):
        return "final"

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

    assert result == "final"
    assert any(name == "agent_end" and payload.get("status") == "completed" for name, payload in captured)


def test_reply_shaping_suppresses_no_reply_token() -> None:
    agent = HeadCodingAgent()

    shaped = agent._shape_final_response("NO_REPLY", tool_results="[read_file]\ncontent")

    assert shaped.suppressed is True
    assert shaped.reason == "no_reply_token"
    assert shaped.text == ""


def test_reply_shaping_deduplicates_tool_confirmations() -> None:
    agent = HeadCodingAgent()
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
    agent = HeadCodingAgent()

    assert agent._is_web_research_task("can you search on the web for the best ai models?") is True


def test_augment_actions_adds_web_fetch_for_web_research() -> None:
    agent = HeadCodingAgent()

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
        and payload.get("details", {}).get("reason") == "web_research_without_web_fetch"
        for payload in events
    )
