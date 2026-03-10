"""Unit tests for AgentRunner evidence gates and task-type resolution (Sprint 2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_runner import AgentRunner
from app.agent_runner_types import ToolResult


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


def _err(name: str, content: str = "Error: failed") -> ToolResult:
    return ToolResult(tool_call_id="c1", tool_name=name, content=content, is_error=True)


# ──────────────────────────────────────────────────────────────────────
# _tool_results_to_string
# ──────────────────────────────────────────────────────────────────────


class TestToolResultsToString:
    def test_empty_list(self):
        assert AgentRunner._tool_results_to_string([]) == ""

    def test_single_ok(self):
        result = AgentRunner._tool_results_to_string([_ok("read_file", "contents")])
        assert result == "[read_file] contents"

    def test_single_error(self):
        result = AgentRunner._tool_results_to_string([_err("write_file", "denied")])
        assert result == "[write_file] [ERROR] denied"

    def test_mixed(self):
        result = AgentRunner._tool_results_to_string([
            _ok("read_file", "data"),
            _err("run_command", "blocked"),
        ])
        assert "[read_file] data" in result
        assert "[run_command] [ERROR] blocked" in result


# ──────────────────────────────────────────────────────────────────────
# _resolve_task_type
# ──────────────────────────────────────────────────────────────────────


class TestResolveTaskType:
    def test_implementation_keyword(self):
        runner = _make_runner()
        assert runner._resolve_task_type("implement the new feature", []) == "implementation"

    def test_implementation_regex_fix(self):
        runner = _make_runner()
        assert runner._resolve_task_type("fix the broken test", []) == "implementation"

    def test_orchestration_via_subrun_complete(self):
        runner = _make_runner()
        results = [_ok("spawn_subrun", "spawned_subrun_id=abc terminal_reason=subrun-complete")]
        assert runner._resolve_task_type("do something", results) == "orchestration"

    def test_orchestration_via_subrun_error(self):
        runner = _make_runner()
        results = [_ok("spawn_subrun", "spawned_subrun_id=abc terminal_reason=subrun-error")]
        assert runner._resolve_task_type("do something", results) == "orchestration_failed"

    def test_orchestration_pending(self):
        runner = _make_runner()
        results = [_ok("spawn_subrun", "spawned_subrun_id=abc terminal_reason=subrun-accepted")]
        assert runner._resolve_task_type("do something", results) == "orchestration_pending"

    def test_research_via_intent_detector(self):
        intent = MagicMock()
        intent.is_subrun_orchestration_task.return_value = False
        intent.is_file_creation_task.return_value = False
        intent.is_web_research_task.return_value = True
        runner = _make_runner(intent_detector=intent)
        assert runner._resolve_task_type("search the web for latest Python news", []) == "research"

    def test_default_general(self):
        runner = _make_runner()
        assert runner._resolve_task_type("hello world", []) == "general"

    def test_orchestration_via_intent_detector(self):
        intent = MagicMock()
        intent.is_subrun_orchestration_task.return_value = True
        runner = _make_runner(intent_detector=intent)
        assert runner._resolve_task_type("orchestrate multi-agent workflow", []) == "orchestration"


# ──────────────────────────────────────────────────────────────────────
# Evidence Gate 1: Implementation
# ──────────────────────────────────────────────────────────────────────


class TestImplementationEvidenceGate:
    def test_fires_when_implementation_without_evidence(self):
        runner = _make_runner()
        result = runner._apply_evidence_gates(
            "I successfully created the file!",
            [_err("write_file", "permission denied")],
            "implement the feature",
        )
        assert "could not complete the implementation" in result.lower()

    def test_does_not_fire_with_write_file_success(self):
        runner = _make_runner()
        original = "I created the file."
        result = runner._apply_evidence_gates(
            original,
            [_ok("write_file", "file written")],
            "implement the feature",
        )
        assert result == original

    def test_does_not_fire_with_run_command_success(self):
        runner = _make_runner()
        original = "Done."
        result = runner._apply_evidence_gates(
            original,
            [_ok("run_command", "exit code 0")],
            "fix the bug",
        )
        assert result == original

    def test_does_not_fire_for_general_task(self):
        runner = _make_runner()
        original = "Hello there."
        result = runner._apply_evidence_gates(original, [], "hello")
        assert result == original


# ──────────────────────────────────────────────────────────────────────
# Evidence Gate 2: All-Tools-Failed
# ──────────────────────────────────────────────────────────────────────


class TestAllToolsFailedGate:
    def test_fires_when_all_tools_failed_and_hallucinated_success(self):
        runner = _make_runner()
        result = runner._apply_evidence_gates(
            "A comprehensive review has been completed. Files were analyzed.",
            [_err("read_file", "Error"), _err("run_command", "Error")],
            "analyze the code",
        )
        assert "unable to complete" in result.lower()

    def test_does_not_fire_when_at_least_one_ok(self):
        runner = _make_runner()
        original = "Analysis complete."
        result = runner._apply_evidence_gates(
            original,
            [_ok("read_file", "content"), _err("run_command", "Error")],
            "analyze the code",
        )
        assert result == original

    def test_does_not_fire_when_response_acknowledges_failure(self):
        runner = _make_runner()
        text = "I encountered errors while trying to read the files."
        result = runner._apply_evidence_gates(
            text,
            [_err("read_file", "Error")],
            "read files",
        )
        assert result == text

    def test_does_not_fire_with_empty_results(self):
        runner = _make_runner()
        original = "Hello"
        result = runner._apply_evidence_gates(original, [], "hello")
        assert result == original


# ──────────────────────────────────────────────────────────────────────
# Evidence Gate 3: Orchestration
# ──────────────────────────────────────────────────────────────────────


class TestOrchestrationEvidenceGate:
    def test_fires_when_subrun_attempted_not_completed(self):
        runner = _make_runner()
        results = [_ok("spawn_subrun", "spawned_subrun_id=abc terminal_reason=subrun-error")]
        result = runner._apply_evidence_gates("Success!", results, "orchestrate")
        assert "did not complete successfully" in result.lower()

    def test_fires_when_no_subrun_executed(self):
        intent = MagicMock()
        intent.is_subrun_orchestration_task.return_value = True
        intent.is_file_creation_task.return_value = False
        intent.is_web_research_task.return_value = False
        runner = _make_runner(intent_detector=intent)
        result = runner._apply_evidence_gates("Done!", [], "orchestrate this")
        assert "no subrun was executed" in result.lower()

    def test_does_not_fire_when_subrun_complete(self):
        runner = _make_runner()
        results = [_ok("spawn_subrun", "spawned_subrun_id=abc subrun-complete")]
        original = "Orchestration done."
        result = runner._apply_evidence_gates(original, results, "orchestrate")
        assert result == original

    def test_does_not_fire_for_non_orchestration_task(self):
        runner = _make_runner()
        original = "Hello"
        result = runner._apply_evidence_gates(original, [], "what is 2+2")
        assert result == original


# ──────────────────────────────────────────────────────────────────────
# Helper method tests
# ──────────────────────────────────────────────────────────────────────


class TestEvidenceGateHelpers:
    def test_all_tools_failed_true(self):
        assert AgentRunner._all_tools_failed([_err("a"), _err("b")]) is True

    def test_all_tools_failed_false_with_ok(self):
        assert AgentRunner._all_tools_failed([_ok("a"), _err("b")]) is False

    def test_all_tools_failed_false_empty(self):
        assert AgentRunner._all_tools_failed([]) is False

    def test_response_acknowledges_failures_true(self):
        assert AgentRunner._response_acknowledges_failures("I was unable to complete") is True

    def test_response_acknowledges_failures_false(self):
        assert AgentRunner._response_acknowledges_failures("Everything is great!") is False

    def test_has_implementation_evidence_with_write_file(self):
        runner = _make_runner()
        assert runner._has_implementation_evidence([_ok("write_file")]) is True

    def test_has_implementation_evidence_without(self):
        runner = _make_runner()
        assert runner._has_implementation_evidence([_ok("read_file")]) is False

    def test_has_implementation_evidence_error_write_file(self):
        runner = _make_runner()
        assert runner._has_implementation_evidence([_err("write_file")]) is False


# ──────────────────────────────────────────────────────────────────────
# Combined gates test
# ──────────────────────────────────────────────────────────────────────


class TestCombinedGates:
    def test_all_three_gates_in_one_run(self):
        """Implementation gate fires first, even if all-tools-failed also applies."""
        runner = _make_runner()
        result = runner._apply_evidence_gates(
            "Everything worked perfectly!",
            [_err("write_file", "Error: denied")],
            "implement the feature",
        )
        # Implementation gate fires — its text contains "could not complete"
        assert "could not complete" in result.lower()
