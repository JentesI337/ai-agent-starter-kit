"""
Agent contract schemas — every agent in the system must define:
  role, input_schema, output_schema, constraints.

No cross-agent implicit knowledge. No shared memory between agents.
All outputs are JSON-only.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class AgentRole(str, Enum):
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ModelTier(str, Enum):
    SMALL = "small"      # 7B–14B
    MID = "mid"          # 32B–70B
    HIGH = "high"        # 70B+ / GPT-4


# ---------------------------------------------------------------------------
# Agent Constraints
# ---------------------------------------------------------------------------

class AgentConstraints(BaseModel):
    """Runtime constraints for an agent invocation."""
    max_context_tokens: int = Field(default=4000, ge=256, description="Token budget for the context window")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_reflection_passes: int = Field(default=0, ge=0, description="0 = linear / no reflection")
    max_output_tokens: int = Field(default=2048, ge=64)
    timeout_seconds: float = Field(default=120.0, ge=1.0)


# ---------------------------------------------------------------------------
# Agent Contract
# ---------------------------------------------------------------------------

class AgentContract(BaseModel):
    """
    Strict, explicit contract that every orchestrated agent must satisfy.

    - role: single clear responsibility
    - input_schema: typed, validated input definition (JSON Schema dict)
    - output_schema: typed, structured output definition (JSON Schema dict)
    - constraints: context limit, temperature, reflection cap
    """
    role: AgentRole
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for agent input")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for agent output")
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)


# ---------------------------------------------------------------------------
# Planner schemas
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    step_id: int
    description: str
    tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)


class PlannerInput(BaseModel):
    user_message: str
    context_summary: str = ""
    evidence: str = ""
    task_complexity: TaskComplexity = TaskComplexity.SIMPLE


class PlannerOutput(BaseModel):
    steps: list[PlanStep]
    estimated_complexity: TaskComplexity = TaskComplexity.SIMPLE
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Coder schemas
# ---------------------------------------------------------------------------

class CoderInput(BaseModel):
    plan_step: PlanStep
    context_summary: str = ""
    file_contents: dict[str, str] = Field(default_factory=dict, description="path -> content snippets")
    evidence: str = ""


class FileChange(BaseModel):
    path: str
    action: str = "write"  # write | delete
    content: str = ""


class CoderOutput(BaseModel):
    changes: list[FileChange] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    reasoning: str = ""
    success: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# Reviewer schemas
# ---------------------------------------------------------------------------

class ReviewerInput(BaseModel):
    plan: PlannerOutput
    coder_output: CoderOutput
    context_summary: str = ""
    original_request: str = ""


class ReviewIssue(BaseModel):
    severity: str = "info"  # info | warning | error
    file: str | None = None
    message: str = ""


class ReviewerOutput(BaseModel):
    approved: bool = True
    issues: list[ReviewIssue] = Field(default_factory=list)
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Model Capability Profile
# ---------------------------------------------------------------------------

class ModelCapabilityProfile(BaseModel):
    """
    Each model is registered with a capability profile used by the
    capability router to select the right model for a task.
    """
    model_id: str
    tier: ModelTier = ModelTier.SMALL
    max_context: int = Field(default=8000, ge=256)
    reasoning_depth: int = Field(default=2, ge=0)
    reflection_passes: int = Field(default=0, ge=0)
    combine_steps: bool = False
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    cost_per_1k_tokens: float = Field(default=0.0, ge=0.0, description="Approximate cost per 1K tokens")


# ---------------------------------------------------------------------------
# Routing request / result
# ---------------------------------------------------------------------------

class RoutingRequest(BaseModel):
    """Input to the capability router."""
    task_complexity: TaskComplexity
    context_size: int = Field(ge=0, description="Token count of required input")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Output from previous agent pass")
    budget_threshold: float = Field(default=float("inf"), ge=0.0, description="Cost ceiling per task")
    required_reflection: bool = False


class RoutingResult(BaseModel):
    """Output from the capability router."""
    selected_model: ModelCapabilityProfile
    reason: str = ""
    fallback_model: ModelCapabilityProfile | None = None


# ---------------------------------------------------------------------------
# Orchestrator task envelope
# ---------------------------------------------------------------------------

class TaskEnvelope(BaseModel):
    """
    The unit of work flowing through the orchestrator.
    Models receive *slices* of state only — never the full store.
    """
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    agent_role: AgentRole = AgentRole.PLANNER
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] | None = None
    error: str | None = None
    retries: int = 0
    max_retries: int = 2
    parent_task_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
