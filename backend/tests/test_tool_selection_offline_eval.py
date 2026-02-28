from __future__ import annotations

import asyncio

from app.agent import HeadCodingAgent
from app.errors import ToolExecutionError


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
    normalized, rejected = agent._validate_actions(actions)
    assert rejected == 0
    assert normalized[0]["tool"] == "write_file"


def test_evaluator_blocks_dangerous_run_command() -> None:
    agent = HeadCodingAgent()

    evaluated_args, error = agent._evaluate_action("run_command", {"command": "rm -rf /"})

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
        normalized_actions, rejected = agent._validate_actions([action])
        if expected_tool is None:
            if rejected == 1:
                correct += 1
            continue
        if rejected != 0:
            continue
        normalized = normalized_actions[0]
        evaluated_args, eval_error = agent._evaluate_action(normalized["tool"], normalized["args"])
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
            )
        finally:
            agent.client.complete_chat = original  # type: ignore[method-assign]

    result_actions = asyncio.run(run_case())

    assert any(action.get("tool") == "write_file" for action in result_actions)
