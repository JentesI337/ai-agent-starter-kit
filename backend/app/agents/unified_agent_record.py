"""Unified agent record — single model for both built-in and custom agents.

Replaces the split between ``AgentDefinition``, ``CustomAgentDefinition``,
and ``AgentRuntimeConfig`` with one serializable Pydantic model.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ConstraintSpec(BaseModel):
    """Runtime constraint values for an agent."""

    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    reflection_passes: int = Field(default=0, ge=0, le=10)
    reasoning_depth: int = Field(default=2, ge=0, le=10)
    max_context: int | None = Field(default=None, ge=256)
    combine_steps: bool = False


class ToolPolicySpec(BaseModel):
    """Declarative tool access rules for an agent."""

    read_only: bool = False
    mandatory_deny: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    additional_deny: list[str] = Field(default_factory=list)
    additional_allow: list[str] = Field(default_factory=list)


class PromptSpec(BaseModel):
    """Inline prompt text with fallback keys for backward compatibility.

    If a prompt field is empty, the system falls back to resolving the
    corresponding ``fallback_*_key`` from application settings / env vars.
    """

    system: str = ""
    plan: str = ""
    tool_selector: str = ""
    tool_repair: str = ""
    final: str = ""
    # Fallback keys — used when inline text is empty
    fallback_system_key: str = ""
    fallback_plan_key: str = ""
    fallback_tool_selector_key: str = ""
    fallback_tool_repair_key: str = ""
    fallback_final_key: str = ""


class DelegationSpec(BaseModel):
    """Delegation and autonomy settings."""

    autonomy_level: int = Field(default=5, ge=1, le=10)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    delegation_preference: Literal["eager", "selective", "reluctant"] = "selective"
    supports_delegation: bool = False
    supports_parallel: bool = False
    max_concurrent_tasks: int = Field(default=1, ge=1)


class BehaviorFlags(BaseModel):
    """Encodes adapter-class behavioral variations as data.

    Instead of 15 separate adapter subclasses, behavioral differences
    (review evidence check, command allowlists, relaxed deny lists)
    are expressed as flags on the record.
    """

    require_review_evidence: bool = False
    command_allowlist_regex: str | None = None
    relaxed_deny: list[str] = Field(default_factory=list)
    custom_deny_override: list[str] | None = None


class CustomWorkflow(BaseModel):
    """Workflow definition for custom (user-created) agents."""

    base_agent_id: str = Field(default="head-agent", min_length=1, max_length=80)
    workflow_steps: list[str] = Field(default_factory=list)
    allow_subrun_delegation: bool = False
    workspace_scope: str | None = Field(default=None, max_length=120)
    skills_scope: str | None = Field(default=None, max_length=120)
    credential_scope: str | None = Field(default=None, max_length=120)


# ---------------------------------------------------------------------------
# Unified record
# ---------------------------------------------------------------------------


class UnifiedAgentRecord(BaseModel):
    """Complete, serializable description of any agent (built-in or custom).

    This is the single source of truth.  Both built-in and custom agents
    share the same schema.  The ``origin`` field distinguishes them.
    """

    agent_id: str = Field(min_length=1, max_length=80)
    origin: Literal["builtin", "custom"] = "custom"
    enabled: bool = True
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    category: Literal["core", "specialist", "industry", "custom"] = "custom"
    role: str = "specialist"
    reasoning_strategy: str = "plan_execute"
    specialization: str = ""
    capabilities: list[str] = Field(default_factory=list)
    constraints: ConstraintSpec = Field(default_factory=ConstraintSpec)
    tool_policy: ToolPolicySpec = Field(default_factory=ToolPolicySpec)
    prompts: PromptSpec = Field(default_factory=PromptSpec)
    delegation: DelegationSpec = Field(default_factory=DelegationSpec)
    behavior: BehaviorFlags = Field(default_factory=BehaviorFlags)
    custom_workflow: CustomWorkflow | None = None
    cost_tier: str = "standard"
    latency_tier: str = "standard"
    quality_tier: str = "high"
    version: int = 1
