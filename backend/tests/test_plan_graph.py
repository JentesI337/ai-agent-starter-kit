from __future__ import annotations

from app.services.plan_graph import PlanGraph, PlanStep


def test_plan_graph_ready_steps_is_complete_and_failed_steps() -> None:
    graph = PlanGraph(
        goal="g",
        complexity="moderate",
        steps=[
            PlanStep(step_id="s1", action="first", tool=None, depends_on=[], fallback=None, status="completed"),
            PlanStep(step_id="s2", action="second", tool="read_file", depends_on=["s1"], fallback="retry"),
            PlanStep(step_id="s3", action="third", tool="run_command", depends_on=["s2"], fallback="skip", status="failed"),
        ],
    )

    ready = graph.ready_steps()

    assert [step.step_id for step in ready] == ["s2"]
    assert graph.is_complete() is False
    assert [step.step_id for step in graph.failed_steps()] == ["s3"]


def test_plan_graph_from_dict_sanitizes_and_limits_steps() -> None:
    payload = {
        "goal": "Ship feature",
        "complexity": "complex",
        "steps": [
            {"step_id": "s1", "action": "Analyze", "tool": "read_file", "depends_on": ["unknown"], "fallback": None},
            {"step_id": "s2", "action": "Implement", "tool": "apply_patch", "depends_on": ["s1"], "fallback": "try again"},
        ],
    }

    graph = PlanGraph.from_dict(payload, max_steps=1)

    assert graph.goal == "Ship feature"
    assert graph.complexity == "complex"
    assert len(graph.steps) == 1
    assert graph.steps[0].depends_on == []
