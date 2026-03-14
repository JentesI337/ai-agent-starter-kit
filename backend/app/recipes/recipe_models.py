"""Recipe domain models — structured intent + constraints + checkpoints.

Recipes replace rigid graph-based workflows with a goal-driven system where
the agent IS the execution engine. Two modes:
- adaptive: agent reasons through goal, hits checkpoints
- strict: deterministic linear step sequence
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Checkpoint (adaptive mode milestones)
# ---------------------------------------------------------------------------

class RecipeCheckpoint(BaseModel):
    """A verifiable milestone the agent must reach during adaptive execution."""

    id: str
    label: str
    verification: str                                   # assertion expr or rubric
    verification_mode: Literal["assert", "agent"] = "assert"
    required: bool = True
    order: int = 0


class CheckpointResult(BaseModel):
    """Result of reaching and verifying a checkpoint."""

    checkpoint_id: str
    reached_at: str = ""
    verification_passed: bool = False
    verification_output: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

class RecipeConstraints(BaseModel):
    """Budget and access constraints for recipe execution."""

    max_duration_seconds: int | None = None
    max_tool_calls: int | None = None
    max_llm_tokens: int | None = None
    tools_allowed: list[str] | None = None              # whitelist (None = all)
    tools_denied: list[str] | None = None               # blacklist
    require_human_approval_before: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Strict mode steps
# ---------------------------------------------------------------------------

class StrictStep(BaseModel):
    """A single deterministic step in strict mode execution."""

    id: str
    label: str = ""
    instruction: str = ""
    tool: str | None = None                             # specific tool (None = agent decides)
    tool_params: dict[str, Any] | None = None           # supports {{prev.output}} templates
    timeout_seconds: int | None = None
    retry_count: int = 0


class StrictStepResult(BaseModel):
    """Result of executing a single strict-mode step."""

    step_id: str
    status: Literal["success", "failed", "timeout", "skipped"] = "success"
    tool_called: str | None = None
    tool_output: Any = None
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    retry_attempts: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Budget snapshot
# ---------------------------------------------------------------------------

class BudgetSnapshot(BaseModel):
    """Tracks resource consumption during a recipe run."""

    tokens_used: int = 0
    tool_calls_used: int = 0
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Recipe definition
# ---------------------------------------------------------------------------

class RecipeDef(BaseModel):
    """Top-level recipe definition — the thing users create and save."""

    id: str
    name: str
    description: str = ""
    goal: str = ""                                      # natural language intent
    mode: Literal["adaptive", "strict"] = "adaptive"
    constraints: RecipeConstraints = Field(default_factory=RecipeConstraints)
    checkpoints: list[RecipeCheckpoint] = Field(default_factory=list)
    strict_steps: list[StrictStep] | None = None
    agent_id: str | None = None                         # override agent
    triggers: list[dict[str, Any]] = Field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Recipe run state
# ---------------------------------------------------------------------------

class RecipeRunState(BaseModel):
    """Full execution state for a recipe run."""

    recipe_id: str
    run_id: str
    session_id: str = ""
    status: Literal["pending", "running", "paused", "completed", "failed", "cancelled"] = "pending"
    mode: Literal["adaptive", "strict"] = "adaptive"

    # Adaptive mode tracking
    checkpoints_reached: dict[str, CheckpointResult] = Field(default_factory=dict)

    # Strict mode tracking
    step_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    current_step_id: str | None = None

    # Shared
    context: dict[str, Any] = Field(default_factory=dict)
    pause_reason: str | None = None
    pause_data: dict[str, Any] | None = None
    paused_at: str | None = None
    resume_data: dict[str, Any] | None = None
    started_at: str = ""
    completed_at: str | None = None
    budget_used: BudgetSnapshot = Field(default_factory=BudgetSnapshot)


# ---------------------------------------------------------------------------
# Pause exception
# ---------------------------------------------------------------------------

class RecipePausedError(Exception):
    """Raised when a recipe step requires pausing (wait_for_event, etc.)."""

    def __init__(self, step_id: str, pause_reason: str, pause_data: dict | None = None):
        self.step_id = step_id
        self.pause_reason = pause_reason
        self.pause_data = pause_data
        super().__init__(f"Recipe paused at step '{step_id}': {pause_reason}")
