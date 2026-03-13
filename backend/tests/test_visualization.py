"""Tests for backend/app/services/visualization.py"""

import pytest

from app.agent_runner_types import PlanStep, PlanTracker
from app.reasoning.plan_graph import PlanGraph
from app.reasoning.plan_graph import PlanStep as GraphStep
from app.monitoring.visualization import (
    build_visualization_event,
    plan_graph_to_mermaid,
    plan_tracker_to_mermaid,
    validate_mermaid_node_count,
)


# ── build_visualization_event ─────────────────────────────


class TestBuildVisualizationEvent:
    @pytest.mark.parametrize("viz_type", ["mermaid", "image", "svg"])
    def test_structure(self, viz_type: str):
        ev = build_visualization_event(viz_type, "<data>", "r1", "s1", "agent-x")
        assert ev["type"] == "visualization"
        assert ev["viz_type"] == viz_type
        assert ev["data"] == "<data>"
        assert ev["request_id"] == "r1"
        assert ev["session_id"] == "s1"
        assert ev["agent"] == "agent-x"


# ── validate_mermaid_node_count ───────────────────────────


class TestValidateMermaidNodeCount:
    def test_passes_small(self):
        code = "\n".join(f"  node{i}[label]" for i in range(10))
        validate_mermaid_node_count(code)  # should not raise

    def test_rejects_over_limit(self):
        code = "\n".join(f"  node{i}[label]" for i in range(501))
        with pytest.raises(ValueError, match="501"):
            validate_mermaid_node_count(code)

    def test_edge_500_passes(self):
        code = "\n".join(f"  node{i}[label]" for i in range(500))
        validate_mermaid_node_count(code)  # exactly 500 is OK


# ── plan_tracker_to_mermaid ───────────────────────────────


def _make_tracker(*statuses: str) -> PlanTracker:
    steps = [
        PlanStep(index=i, description=f"Step {i}", status=s)
        for i, s in enumerate(statuses)
    ]
    return PlanTracker(steps=steps, planning_active=True)


class TestPlanTrackerToMermaid:
    def test_three_steps(self):
        tracker = _make_tracker("pending", "pending", "pending")
        md = plan_tracker_to_mermaid(tracker)
        assert "flowchart TD" in md
        assert "s0 --> s1" in md
        assert "s1 --> s2" in md

    def test_statuses(self):
        tracker = _make_tracker("completed", "in_progress", "failed")
        md = plan_tracker_to_mermaid(tracker)
        assert ":::done" in md
        assert ":::active" in md
        assert ":::error" in md

    def test_escapes_quotes(self):
        t = PlanTracker(
            steps=[PlanStep(index=0, description='Read "config.json"', status="pending")],
            planning_active=True,
        )
        md = plan_tracker_to_mermaid(t)
        assert '#quot;' in md
        assert '"config.json"' not in md.split("\n", 1)[1]  # not in body after header


# ── plan_graph_to_mermaid ─────────────────────────────────


def _make_graph() -> PlanGraph:
    return PlanGraph(
        goal="Test",
        complexity="moderate",
        steps=[
            GraphStep(step_id="s1", action="Fetch data", tool="http_get", depends_on=[], fallback=None, status="completed"),
            GraphStep(step_id="s2", action="Parse data", tool=None, depends_on=["s1"], fallback=None, status="running"),
            GraphStep(step_id="s3", action="Store result", tool="write_file", depends_on=["s2"], fallback=None),
        ],
    )


class TestPlanGraphToMermaid:
    def test_dag_edges(self):
        md = plan_graph_to_mermaid(_make_graph())
        assert "s1 --> s2" in md
        assert "s2 --> s3" in md
        assert "flowchart TD" in md

    def test_status_classes(self):
        md = plan_graph_to_mermaid(_make_graph())
        assert ":::done" in md
        assert ":::active" in md
