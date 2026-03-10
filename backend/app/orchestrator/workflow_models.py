"""Workflow graph model — step definitions, execution state, and results."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowStepDef(BaseModel):
    """Single step in a workflow graph."""

    id: str
    type: Literal["agent", "connector", "transform", "condition", "delay"]
    label: str = ""
    instruction: str = ""
    agent_id: str | None = None
    connector_id: str | None = None
    connector_method: str | None = None
    connector_params: dict[str, Any] = Field(default_factory=dict)
    transform_expr: str | None = None
    condition_expr: str | None = None
    on_true: str | None = None
    on_false: str | None = None
    next_step: str | None = None
    timeout_seconds: int = 120
    retry_count: int = 0


class WorkflowGraphDef(BaseModel):
    """Directed graph of workflow steps."""

    steps: list[WorkflowStepDef]
    entry_step_id: str

    def get_step(self, step_id: str) -> WorkflowStepDef | None:
        return next((s for s in self.steps if s.id == step_id), None)


class StepResult(BaseModel):
    """Result of executing a single workflow step."""

    step_id: str
    status: Literal["success", "error", "skipped", "timeout"]
    output: Any = None
    error: str | None = None
    duration_ms: int = 0


class WorkflowExecutionState(BaseModel):
    """Full execution state for a workflow run."""

    workflow_id: str
    run_id: str
    session_id: str
    current_step_id: str | None = None
    step_results: dict[str, StepResult] = Field(default_factory=dict)
    status: Literal["running", "completed", "failed", "cancelled"] = "running"
    context: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    completed_at: str | None = None
