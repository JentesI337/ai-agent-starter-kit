"""Workflow domain models — merged from workflow_models, workflow_record, and WorkflowTrigger.

Single source of truth for all workflow data structures:
- Step definitions, graph, execution state (ex workflow_models.py)
- Workflow record, tool policy (ex workflow_record.py)
- Workflow trigger (ex unified_agent_record.py)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Graph / step / execution models (ex orchestrator/workflow_models.py)
# ---------------------------------------------------------------------------


class WorkflowStepDef(BaseModel):
    """Single step in a workflow graph."""

    id: str
    type: Literal["agent", "connector", "transform", "condition", "delay",
                  "fork", "join", "loop", "trigger", "end"]
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
    output_type: Literal["text", "file"] = "text"
    output_path: str = ""
    timeout_seconds: int = 120
    retry_count: int = 0

    # Fork fan-out (mutually exclusive with next_step)
    next_steps: list[str] | None = None

    # Join barrier
    wait_for: str | None = None       # "all" | "1" | "2" ...
    join_from: list[str] | None = None  # explicit source step IDs

    # Loop control
    loop_condition: str | None = None
    loop_body_entry: str | None = None
    loop_max_iterations: int = 100


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
    output_dir: str | None = None


# ---------------------------------------------------------------------------
# Trigger (ex agents/unified_agent_record.py)
# ---------------------------------------------------------------------------


class WorkflowTrigger(BaseModel):
    """Trigger configuration for a workflow."""

    type: Literal["manual", "schedule", "webhook", "chat_command"] = "manual"
    cron_expression: str | None = None
    webhook_secret: str | None = None
    command_name: str | None = None
    last_run_at: str | None = None
    next_run_at: str | None = None


# ---------------------------------------------------------------------------
# Tool policy + record (ex services/workflow_record.py)
# ---------------------------------------------------------------------------


class WorkflowToolPolicy(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)


class WorkflowRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    base_agent_id: str = "head-agent"
    execution_mode: Literal["parallel", "sequential"] = "parallel"
    workflow_graph: WorkflowGraphDef | None = None
    tool_policy: WorkflowToolPolicy | None = None
    triggers: list[WorkflowTrigger] = Field(default_factory=list)
    allow_subrun_delegation: bool = False
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


def _extract_flat_steps(record: WorkflowRecord) -> list[str]:
    """Derive flat step list from workflow_graph for backward compat."""
    if record.workflow_graph is None:
        return []
    return [
        s.instruction
        for s in record.workflow_graph.steps
        if s.type == "agent" and s.instruction.strip()
    ]
