"""Dedicated workflow record model — owns all workflow-specific fields.

Replaces the shoehorned path through UnifiedAgentRecord + CustomWorkflow
with a purpose-built model that preserves all fields on round-trip.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.unified_agent_record import WorkflowTrigger
from app.orchestrator.workflow_models import WorkflowGraphDef


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


def workflow_record_to_agent_record(wf: WorkflowRecord) -> Any:
    """Build a lightweight UnifiedAgentRecord from a WorkflowRecord.

    Used only for execution context (agent registration), not stored.
    """
    from app.agents.unified_agent_record import (
        CustomWorkflow,
        ToolPolicySpec,
        UnifiedAgentRecord,
    )

    tp = ToolPolicySpec()
    if wf.tool_policy is not None:
        tp = ToolPolicySpec(
            additional_allow=list(wf.tool_policy.allow),
            additional_deny=list(wf.tool_policy.deny),
        )

    custom_workflow = CustomWorkflow(
        base_agent_id=wf.base_agent_id,
        workflow_steps=_extract_flat_steps(wf),
        execution_mode=wf.execution_mode,
        workflow_graph=wf.workflow_graph.model_dump() if wf.workflow_graph else None,
        triggers=list(wf.triggers),
        allow_subrun_delegation=wf.allow_subrun_delegation,
    )

    return UnifiedAgentRecord(
        agent_id=wf.id,
        origin="custom",
        enabled=True,
        display_name=wf.name,
        description=wf.description,
        category="custom",
        tool_policy=tp,
        custom_workflow=custom_workflow,
        version=wf.version,
    )


def _extract_flat_steps(record: WorkflowRecord) -> list[str]:
    """Derive flat step list from workflow_graph for backward compat."""
    if record.workflow_graph is None:
        return []
    return [
        s.instruction
        for s in record.workflow_graph.steps
        if s.type == "agent" and s.instruction.strip()
    ]
