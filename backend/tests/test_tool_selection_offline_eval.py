from __future__ import annotations

import asyncio

from app.agent import HeadCodingAgent, IMPLEMENTATION_CREATE_TOOLS
from app.errors import ToolExecutionError


def test_extract_actions_requires_strict_json_object() -> None:
    candidate = "[TOOL_CALL] tool => \"CreateFile\""
    agent = HeadCodingAgent()

    selection = agent._extract_actions(candidate)

    assert selection.actions == []
    assert selection.parse_error is not None


def test_structured_alias_is_normalized_to_registry_tool() -> None:
    agent = HeadCodingAgent()

    selection = agent._extract_actions('{"actions":[{"tool":"CreateFile","args":{"path":"a.txt","content":"x"}}]}')

    assert selection.parse_error is None
    normalized, rejected, reasons = agent._validate_actions(selection.actions)
    assert rejected == 0
    assert reasons == []
    assert normalized[0]["tool"] == "write_file"


def test_extract_actions_accepts_optional_execution_mode() -> None:
    agent = HeadCodingAgent()

    selection = agent._extract_actions('{"mode":"sequential","actions":[{"tool":"read_file","args":{"path":"README.md"}}]}')

    assert selection.parse_error is None
    assert selection.mode == "sequential"
    assert len(selection.actions) == 1


def test_extract_actions_rejects_unsupported_action_fields() -> None:
    agent = HeadCodingAgent()

    selection = agent._extract_actions('{"actions":[{"tool":"read_file","args":{"path":"README.md"},"extra":1}]}')

    assert selection.actions == []
    assert selection.parse_error is not None


def test_validate_actions_honors_phase_allowed_tools() -> None:
    agent = HeadCodingAgent()

    normalized, rejected, reasons = agent._validate_actions(
        [{"tool": "write_file", "args": {"path": "x.txt", "content": "ok"}}],
        allowed_tools={"list_dir", "read_file"},
    )

    assert normalized == []
    assert rejected == 1
    assert reasons
    assert "not allowed in this phase" in reasons[0]


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
        normalized_actions, rejected, _ = agent._validate_actions([action])
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


def test_triage_marks_code_task_as_exploration_needed() -> None:
    agent = HeadCodingAgent()

    triage = agent._triage_task("please fix this bug in the code and update tests")

    assert triage.needs_exploration is True
    assert triage.needs_evidence_gate is True
    assert "code_context" in triage.required_evidence_types
    assert triage.confidence > 0


def test_triage_detects_greenfield_create_intent() -> None:
    agent = HeadCodingAgent()

    triage = agent._triage_task("make a calculator app with html css and javascript")

    assert triage.create_intent is True
    assert triage.needs_exploration is True
    assert "repo_map" in triage.required_evidence_types


def test_triage_skips_exploration_for_precise_single_file_change() -> None:
    agent = HeadCodingAgent()

    triage = agent._triage_task("update backend/app/agent.py change timeout from 8 to 10")

    assert triage.needs_exploration is False
    assert triage.confidence >= 0.85


def test_assess_evidence_coverage_reports_missing_types() -> None:
    agent = HeadCodingAgent()

    coverage = agent._assess_evidence_coverage(
        tool_results="[list_dir]\nbackend/\n\n[read_file]\n# app/agent.py",
        required_evidence_types=("repo_map", "code_context", "test_context"),
    )

    assert coverage["missing"] == ["test_context"]
    assert coverage["quality_score"] < 1.0


def test_evidence_helpers_detect_verified_reads() -> None:
    agent = HeadCodingAgent()

    assert agent._has_verified_evidence("") is False
    assert agent._has_verified_evidence("[read_file]\ncontent") is True
    assert agent._has_verified_evidence("[run_command] ERROR: timeout") is False
    assert agent._has_verified_evidence("[write_file]\nOK", allow_write_only=False) is False
    assert agent._has_verified_evidence("[write_file]\nOK", allow_write_only=True) is True


def test_bootstrap_action_created_for_calculator_prompt() -> None:
    agent = HeadCodingAgent()

    action = agent._build_bootstrap_action("make a calculator app with html css and javascript")

    assert action is not None
    assert action["tool"] == "write_file"
    assert action["args"]["path"] == "index.html"


def test_create_implementation_tools_reject_list_dir() -> None:
    agent = HeadCodingAgent()

    normalized, rejected, reasons = agent._validate_actions(
        [{"tool": "list_dir", "args": {}}],
        allowed_tools=IMPLEMENTATION_CREATE_TOOLS,
    )

    assert normalized == []
    assert rejected == 1
    assert "not allowed in this phase" in reasons[0]


def test_has_successful_tool_result_detects_write_success() -> None:
    agent = HeadCodingAgent()

    assert agent._has_successful_tool_result("[write_file]\nOK", "write_file") is True
    assert agent._has_successful_tool_result("[write_file] ERROR: failed", "write_file") is False
