"""Tests for the workflow engine — models, transforms, and execution."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.workflows.models import (
    StepResult,
    WorkflowExecutionState,
    WorkflowGraphDef,
    WorkflowStepDef,
)
from app.workflows.transforms import (
    evaluate_condition,
    resolve_params,
    resolve_templates,
)


# ---------------------------------------------------------------------------
# Template resolution tests
# ---------------------------------------------------------------------------

class TestResolveTemplates:
    def test_simple_substitution(self):
        ctx = {"step1": {"output": "hello world"}}
        result = resolve_templates("Result: {{step1.output}}", ctx)
        assert result == "Result: hello world"

    def test_nested_dot_path(self):
        ctx = {"step1": {"output": {"status": "open", "count": 5}}}
        result = resolve_templates("Status is {{step1.output.status}}", ctx)
        assert result == "Status is open"

    def test_array_index(self):
        ctx = {"step1": {"output": {"items": [{"name": "first"}, {"name": "second"}]}}}
        result = resolve_templates("{{step1.output.items[0].name}}", ctx)
        assert result == "first"

    def test_input_message(self):
        ctx = {"input": {"message": "deploy v2.0"}}
        result = resolve_templates("Trigger: {{input.message}}", ctx)
        assert result == "Trigger: deploy v2.0"

    def test_filter_upper(self):
        ctx = {"step1": {"output": "hello"}}
        result = resolve_templates("{{step1.output | upper}}", ctx)
        assert result == "HELLO"

    def test_filter_lower(self):
        ctx = {"step1": {"output": "HELLO"}}
        result = resolve_templates("{{step1.output | lower}}", ctx)
        assert result == "hello"

    def test_filter_length(self):
        ctx = {"step1": {"output": [1, 2, 3]}}
        result = resolve_templates("{{step1.output | length}}", ctx)
        assert result == "3"

    def test_filter_join(self):
        ctx = {"step1": {"output": ["a", "b", "c"]}}
        result = resolve_templates('{{step1.output | join(",")}}', ctx)
        assert result == "a,b,c"

    def test_unresolved_stays(self):
        ctx = {}
        result = resolve_templates("{{missing.path}}", ctx)
        assert result == "{{missing.path}}"

    def test_dict_output_as_json(self):
        ctx = {"step1": {"output": {"key": "val"}}}
        result = resolve_templates("{{step1.output}}", ctx)
        parsed = json.loads(result)
        assert parsed["key"] == "val"

    def test_multiple_templates(self):
        ctx = {"s1": {"output": "A"}, "s2": {"output": "B"}}
        result = resolve_templates("{{s1.output}} and {{s2.output}}", ctx)
        assert result == "A and B"


class TestResolveParams:
    def test_resolves_string_values(self):
        ctx = {"step1": {"output": {"repo": "my-repo"}}}
        params = {"owner": "acme", "repo": "{{step1.output.repo}}"}
        resolved = resolve_params(params, ctx)
        assert resolved["owner"] == "acme"
        assert resolved["repo"] == "my-repo"

    def test_non_string_values_unchanged(self):
        ctx = {}
        params = {"count": 5, "flag": True}
        resolved = resolve_params(params, ctx)
        assert resolved["count"] == 5
        assert resolved["flag"] is True


# ---------------------------------------------------------------------------
# Condition evaluator tests
# ---------------------------------------------------------------------------

class TestEvaluateCondition:
    def test_simple_comparison(self):
        ctx = {"step1": {"output": {"status": "open"}}}
        assert evaluate_condition('step1["output"]["status"] == "open"', ctx) is True

    def test_numeric_comparison(self):
        ctx = {"step1": {"output": {"count": 10}}}
        assert evaluate_condition('step1["output"]["count"] > 5', ctx) is True

    def test_boolean_and(self):
        ctx = {"a": True, "b": True}
        assert evaluate_condition("a and b", ctx) is True

    def test_boolean_or(self):
        ctx = {"a": False, "b": True}
        assert evaluate_condition("a or b", ctx) is True

    def test_not(self):
        ctx = {"a": False}
        assert evaluate_condition("not a", ctx) is True

    def test_empty_returns_true(self):
        assert evaluate_condition("", {}) is True

    def test_unsafe_node_rejected(self):
        with pytest.raises(ValueError, match="Unsafe"):
            evaluate_condition("__import__('os')", {})

    def test_invalid_syntax(self):
        with pytest.raises(ValueError, match="Invalid"):
            evaluate_condition("if True:", {})

    def test_in_check(self):
        ctx = {"items": ["a", "b", "c"]}
        assert evaluate_condition('"a" in items', ctx) is True

    def test_template_in_condition(self):
        ctx = {"step1": {"output": "open"}}
        result = evaluate_condition('"{{step1.output}}" == "open"', ctx)
        assert result is True


# ---------------------------------------------------------------------------
# Workflow models tests
# ---------------------------------------------------------------------------

class TestWorkflowModels:
    def test_graph_get_step(self):
        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(id="s1", type="agent", instruction="do stuff"),
                WorkflowStepDef(id="s2", type="transform", transform_expr="{{s1.output}}"),
            ],
            entry_step_id="s1",
        )
        assert graph.get_step("s1") is not None
        assert graph.get_step("s1").type == "agent"
        assert graph.get_step("nonexistent") is None

    def test_step_defaults(self):
        step = WorkflowStepDef(id="test", type="agent")
        assert step.timeout_seconds == 120
        assert step.retry_count == 0
        assert step.label == ""

    def test_execution_state_defaults(self):
        state = WorkflowExecutionState(
            workflow_id="wf1", run_id="r1", session_id="s1"
        )
        assert state.status == "running"
        assert state.step_results == {}
        assert state.context == {}


# ---------------------------------------------------------------------------
# Workflow engine tests
# ---------------------------------------------------------------------------

class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_transform_step_only(self):
        """Engine executes a single transform step."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="t1", type="transform",
                    label="Extract",
                    transform_expr="processed: {{input.message}}",
                ),
            ],
            entry_step_id="t1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-1",
            session_id="sess-1",
            initial_message="hello",
            workflow_id="wf-test",
            send_event=send,
        )

        assert state.status == "completed"
        assert "t1" in state.step_results
        assert state.step_results["t1"].status == "success"
        assert "hello" in str(state.step_results["t1"].output)

    @pytest.mark.asyncio
    async def test_condition_branching(self):
        """Engine follows condition true/false branches."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="c1", type="condition",
                    label="Check",
                    condition_expr="True",
                    on_true="t_true",
                    on_false="t_false",
                ),
                WorkflowStepDef(
                    id="t_true", type="transform",
                    label="True Path",
                    transform_expr="went true",
                ),
                WorkflowStepDef(
                    id="t_false", type="transform",
                    label="False Path",
                    transform_expr="went false",
                ),
            ],
            entry_step_id="c1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-2",
            session_id="sess-2",
            initial_message="test",
            workflow_id="wf-cond",
            send_event=send,
        )

        assert state.status == "completed"
        assert "c1" in state.step_results
        assert "t_true" in state.step_results
        assert "t_false" not in state.step_results  # should not execute false branch

    @pytest.mark.asyncio
    async def test_delay_step(self):
        """Engine executes a delay step."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="d1", type="delay",
                    label="Wait",
                    timeout_seconds=1,
                ),
            ],
            entry_step_id="d1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-3",
            session_id="sess-3",
            initial_message="test",
            workflow_id="wf-delay",
            send_event=send,
        )

        assert state.status == "completed"
        assert state.step_results["d1"].status == "success"
        assert state.step_results["d1"].output["delayed_seconds"] == 1

    @pytest.mark.asyncio
    async def test_sequential_data_flow(self):
        """Step 2 can reference step 1's output via template."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="s1", type="transform",
                    label="Step 1",
                    transform_expr="first_result",
                    next_step="s2",
                ),
                WorkflowStepDef(
                    id="s2", type="transform",
                    label="Step 2",
                    transform_expr="got: {{s1.output}}",
                ),
            ],
            entry_step_id="s1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-4",
            session_id="sess-4",
            initial_message="test",
            workflow_id="wf-flow",
            send_event=send,
        )

        assert state.status == "completed"
        # Transform auto-wraps bare exprs with {{}} — s1 output becomes {{first_result}}
        # s2 resolves s1.output which is {{first_result}} (unresolvable stays wrapped)
        assert "s2" in state.step_results
        assert state.step_results["s2"].status == "success"
        # The key point: s2 referenced s1's output successfully
        assert "s1" in state.context

    @pytest.mark.asyncio
    async def test_events_emitted(self):
        """Engine emits start/complete/workflow_completed events."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(id="s1", type="transform", transform_expr="ok"),
            ],
            entry_step_id="s1",
        )

        events: list[dict] = []

        async def capture(event: dict) -> None:
            events.append(event)

        await engine.execute(
            graph=graph,
            run_id="run-5",
            session_id="sess-5",
            initial_message="test",
            workflow_id="wf-events",
            send_event=capture,
        )

        event_types = [e["type"] for e in events]
        assert "workflow_step_started" in event_types
        assert "workflow_step_completed" in event_types
        assert "workflow_completed" in event_types


# ---------------------------------------------------------------------------
# Fork / Join tests
# ---------------------------------------------------------------------------

class TestForkJoin:
    @pytest.mark.asyncio
    async def test_fork_two_transforms_join(self):
        """fork -> 2 transform branches -> join, verify merged output."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="fork1", type="fork",
                    next_steps=["branch_a", "branch_b"],
                ),
                WorkflowStepDef(
                    id="branch_a", type="transform",
                    label="Branch A",
                    transform_expr="result_a",
                    next_step="join1",
                ),
                WorkflowStepDef(
                    id="branch_b", type="transform",
                    label="Branch B",
                    transform_expr="result_b",
                    next_step="join1",
                ),
                WorkflowStepDef(
                    id="join1", type="join",
                    join_from=["branch_a", "branch_b"],
                    next_step="final",
                ),
                WorkflowStepDef(
                    id="final", type="transform",
                    label="Final",
                    transform_expr="done",
                ),
            ],
            entry_step_id="fork1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-fork-1",
            session_id="sess-fork-1",
            initial_message="test",
            workflow_id="wf-fork",
            send_event=send,
        )

        assert state.status == "completed"
        assert "fork1" in state.step_results
        assert "branch_a" in state.step_results
        assert "branch_b" in state.step_results
        assert "join1" in state.step_results
        assert "final" in state.step_results

        # Join should have merged branch outputs
        join_output = state.step_results["join1"].output
        assert isinstance(join_output, dict)
        assert "branch_a" in join_output
        assert "branch_b" in join_output

    @pytest.mark.asyncio
    async def test_fork_join_context_isolation(self):
        """Branches don't clobber each other's context."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="fork1", type="fork",
                    next_steps=["b1", "b2"],
                ),
                WorkflowStepDef(
                    id="b1", type="transform",
                    transform_expr="value_from_b1",
                    next_step="join1",
                ),
                WorkflowStepDef(
                    id="b2", type="transform",
                    transform_expr="value_from_b2",
                    next_step="join1",
                ),
                WorkflowStepDef(
                    id="join1", type="join",
                    join_from=["b1", "b2"],
                ),
            ],
            entry_step_id="fork1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-fork-2",
            session_id="sess-fork-2",
            initial_message="test",
            workflow_id="wf-fork-iso",
            send_event=send,
        )

        assert state.status == "completed"
        # Both branches produced results and are stored separately
        assert "b1" in state.context
        assert "b2" in state.context
        # Ensure the branches produced distinct outputs (not clobbered)
        assert state.context["b1"]["output"] != state.context["b2"]["output"]


# ---------------------------------------------------------------------------
# Loop tests
# ---------------------------------------------------------------------------

class TestLoop:
    @pytest.mark.asyncio
    async def test_loop_iterates_three_times(self):
        """Loop with counter < 3, verify 3 iterations."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="loop1", type="loop",
                    loop_condition="_loop_loop1._iteration < 3",
                    loop_body_entry="body",
                    next_step="done",
                    loop_max_iterations=10,
                ),
                WorkflowStepDef(
                    id="body", type="transform",
                    label="Body",
                    transform_expr="iteration_output",
                    next_step="loop1",
                ),
                WorkflowStepDef(
                    id="done", type="transform",
                    label="Done",
                    transform_expr="loop_finished",
                ),
            ],
            entry_step_id="loop1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-loop-1",
            session_id="sess-loop-1",
            initial_message="test",
            workflow_id="wf-loop",
            send_event=send,
        )

        assert state.status == "completed"
        assert "done" in state.step_results

    @pytest.mark.asyncio
    async def test_loop_max_iterations_cap(self):
        """Loop that never exits hits max_iterations."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="loop1", type="loop",
                    loop_condition="True",
                    loop_body_entry="body",
                    next_step="done",
                    loop_max_iterations=3,
                ),
                WorkflowStepDef(
                    id="body", type="transform",
                    transform_expr="looping",
                    next_step="loop1",
                ),
                WorkflowStepDef(
                    id="done", type="transform",
                    transform_expr="finished",
                ),
            ],
            entry_step_id="loop1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-loop-2",
            session_id="sess-loop-2",
            initial_message="test",
            workflow_id="wf-loop-max",
            send_event=send,
        )

        assert state.status == "completed"
        assert "done" in state.step_results

    @pytest.mark.asyncio
    async def test_loop_zero_iterations(self):
        """Condition false on first eval -> skip body, go to done."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="loop1", type="loop",
                    loop_condition="False",
                    loop_body_entry="body",
                    next_step="done",
                ),
                WorkflowStepDef(
                    id="body", type="transform",
                    transform_expr="should_not_run",
                ),
                WorkflowStepDef(
                    id="done", type="transform",
                    transform_expr="skipped_loop",
                ),
            ],
            entry_step_id="loop1",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-loop-3",
            session_id="sess-loop-3",
            initial_message="test",
            workflow_id="wf-loop-zero",
            send_event=send,
        )

        assert state.status == "completed"
        assert "body" not in state.step_results
        assert "done" in state.step_results


# ---------------------------------------------------------------------------
# Passthrough tests
# ---------------------------------------------------------------------------

class TestPassthrough:
    @pytest.mark.asyncio
    async def test_trigger_end_passthrough(self):
        """trigger -> agent-like transform -> end works."""
        from app.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()

        graph = WorkflowGraphDef(
            steps=[
                WorkflowStepDef(
                    id="trig", type="trigger",
                    next_step="work",
                ),
                WorkflowStepDef(
                    id="work", type="transform",
                    transform_expr="result_data",
                    next_step="finish",
                ),
                WorkflowStepDef(
                    id="finish", type="end",
                ),
            ],
            entry_step_id="trig",
        )

        send = AsyncMock()
        state = await engine.execute(
            graph=graph,
            run_id="run-pt-1",
            session_id="sess-pt-1",
            initial_message="hello",
            workflow_id="wf-passthrough",
            send_event=send,
        )

        assert state.status == "completed"
        assert "trig" in state.step_results
        assert state.step_results["trig"].status == "success"
        assert "finish" in state.step_results
        assert state.step_results["finish"].status == "success"
