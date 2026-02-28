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
