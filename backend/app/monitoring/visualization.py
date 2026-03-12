"""Visualization helpers — build events, validate Mermaid, convert plans to diagrams."""

from __future__ import annotations

import re
from typing import Any

from app.agent.runner_types import PlanTracker
from app.services.plan_graph import PlanGraph


def build_plan_progress_event(
    tracker: PlanTracker,
    request_id: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
) -> dict[str, Any]:
    """Return a lightweight plan-progress WebSocket event (no Mermaid generation)."""
    return {
        "type": "plan_progress",
        "request_id": request_id,
        "session_id": session_id,
        "agent": agent,
        "steps": [
            {"index": s.index, "description": s.description, "status": s.status}
            for s in tracker.steps
        ],
    }


def build_visualization_event(
    viz_type: str,
    data: str,
    request_id: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
) -> dict[str, Any]:
    """Return a visualization WebSocket event dict."""
    return {
        "type": "visualization",
        "viz_type": viz_type,
        "data": data,
        "request_id": request_id,
        "session_id": session_id,
        "agent": agent,
    }


# ── Mermaid validation ────────────────────────────────────

_NODE_PATTERNS = re.compile(
    r"""
      ^\s*\w[\w.-]*\s*[\[\(\{<]        # flowchart node id followed by shape opener
    | ^\s*(?:participant|actor)\s+       # sequence diagram
    | ^\s*class\s+\w                     # class diagram
    | ^\s*\w+\s*\{                       # entity/class block opener
    """,
    re.MULTILINE | re.VERBOSE,
)


# Patterns to detect unquoted node labels in common Mermaid shapes.
# Negative lookahead (?!") skips labels already wrapped in double quotes.
_UNQUOTED_RECT_LABEL = re.compile(r'(\b\w[\w.-]*)\[(?!")([^\]"]+)\]')
_UNQUOTED_DIAMOND_LABEL = re.compile(r'(\b\w[\w.-]*)\{(?!")([^\}"]+)\}')


def sanitize_mermaid_labels(code: str) -> str:
    """Wrap unquoted Mermaid node labels in double-quotes to prevent parse errors.

    LLMs frequently emit labels like ``B[func()]`` where the parentheses are
    interpreted as Mermaid shape delimiters.  Quoting to ``B["func()"]`` fixes
    this.  Already-quoted labels are left unchanged.
    """
    code = _UNQUOTED_RECT_LABEL.sub(r'\1["\2"]', code)
    code = _UNQUOTED_DIAMOND_LABEL.sub(r'\1{"\2"}', code)
    return code


def validate_mermaid_node_count(mermaid_code: str, max_nodes: int = 500) -> None:
    """Raise ``ValueError`` if the heuristic node count exceeds *max_nodes*."""
    count = len(_NODE_PATTERNS.findall(mermaid_code))
    if count > max_nodes:
        raise ValueError(f"Mermaid diagram has ~{count} nodes (limit {max_nodes})")


# ── PlanTracker → Mermaid ─────────────────────────────────

_STATUS_CLASS = {
    "completed": "done",
    "in_progress": "active",
    "failed": "error",
}

_CLASS_DEFS = (
    "classDef done fill:#0a3d23,stroke:#00cc7a,color:#d4d4d4\n"
    "classDef active fill:#0e2a4a,stroke:#3794ff,color:#d4d4d4\n"
    "classDef error fill:#3d0a0a,stroke:#ff5555,color:#d4d4d4"
)


def _escape_mermaid(text: str) -> str:
    return text.replace('"', '#quot;')


def plan_tracker_to_mermaid(tracker: PlanTracker) -> str:
    """Convert a ``PlanTracker`` to a Mermaid flowchart string."""
    lines = ["flowchart TD"]
    for step in tracker.steps:
        label = _escape_mermaid(step.description)
        cls = _STATUS_CLASS.get(step.status, "")
        cls_suffix = f":::{cls}" if cls else ""
        lines.append(f'  s{step.index}["{step.index + 1}. {label}"]{cls_suffix}')

    # Sequential edges
    for i in range(len(tracker.steps) - 1):
        lines.append(f"  s{tracker.steps[i].index} --> s{tracker.steps[i + 1].index}")

    lines.append(f"  {_CLASS_DEFS}")
    return "\n".join(lines)


# ── PlanGraph → Mermaid ───────────────────────────────────

_GRAPH_STATUS_CLASS = {
    "completed": "done",
    "running": "active",
    "failed": "error",
}


def plan_graph_to_mermaid(graph: PlanGraph) -> str:
    """Convert a ``PlanGraph`` to a Mermaid flowchart with DAG edges."""
    lines = ["flowchart TD"]
    for step in graph.steps:
        label = _escape_mermaid(step.action)
        cls = _GRAPH_STATUS_CLASS.get(step.status, "")
        cls_suffix = f":::{cls}" if cls else ""
        lines.append(f'  {step.step_id}["{label}"]{cls_suffix}')

    # Dependency edges (true DAG)
    for step in graph.steps:
        for dep in step.depends_on:
            lines.append(f"  {dep} --> {step.step_id}")

    # Fallback: sequential edges for steps with no dependencies (except the first)
    step_ids_with_deps = {s.step_id for s in graph.steps if s.depends_on}
    prev_id: str | None = None
    for step in graph.steps:
        if step.step_id not in step_ids_with_deps and prev_id is not None:
            lines.append(f"  {prev_id} --> {step.step_id}")
        prev_id = step.step_id

    lines.append(f"  {_CLASS_DEFS}")
    return "\n".join(lines)
