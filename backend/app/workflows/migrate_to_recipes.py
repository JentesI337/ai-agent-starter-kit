"""Migration script — converts WorkflowRecord → RecipeDef.

Reads all workflows from SqliteWorkflowStore and creates corresponding
RecipeDef entries in SqliteRecipeStore.  Supports dry-run mode to preview
the migration without writing anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.workflows.models import WorkflowRecord, WorkflowStepDef
from app.workflows.recipe_models import (
    RecipeCheckpoint,
    RecipeConstraints,
    RecipeDef,
    StrictStep,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------

@dataclass
class MigrationResult:
    workflow_id: str
    workflow_name: str
    recipe_id: str
    mode: str  # "strict" or "adaptive"
    step_count: int
    status: str  # "migrated", "skipped", "error"
    error: str | None = None


@dataclass
class MigrationReport:
    results: list[MigrationResult] = field(default_factory=list)
    total: int = 0
    migrated: int = 0
    skipped: int = 0
    errors: int = 0


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

_COMPLEX_TYPES = frozenset({"condition", "fork", "join", "loop"})
_SKIP_TYPES = frozenset({"trigger", "end"})


def _is_linear(record: WorkflowRecord) -> bool:
    """Return True if the workflow graph is strictly linear (no complex nodes)."""
    if record.workflow_graph is None:
        return True
    for step in record.workflow_graph.steps:
        if step.type in _COMPLEX_TYPES:
            return False
    return True


def _walk_linear_steps(record: WorkflowRecord) -> list[WorkflowStepDef]:
    """Walk graph from entry following next_step chain, skipping trigger/end."""
    if record.workflow_graph is None:
        return []
    graph = record.workflow_graph
    visited: set[str] = set()
    ordered: list[WorkflowStepDef] = []
    current_id: str | None = graph.entry_step_id

    while current_id and current_id not in visited:
        visited.add(current_id)
        step = graph.get_step(current_id)
        if step is None:
            break
        if step.type not in _SKIP_TYPES:
            ordered.append(step)
        current_id = step.next_step

    return ordered


def _convert_linear(record: WorkflowRecord) -> RecipeDef:
    """Convert a linear workflow to a strict-mode recipe."""
    steps = _walk_linear_steps(record)
    strict_steps: list[StrictStep] = []
    for step in steps:
        tool: str | None = None
        tool_params: dict[str, Any] | None = None
        if step.type == "connector" and step.connector_method:
            tool = step.connector_method
            tool_params = step.connector_params or None
        strict_steps.append(StrictStep(
            id=step.id,
            label=step.label or (step.instruction[:50] if step.instruction else step.id),
            instruction=step.instruction,
            tool=tool,
            tool_params=tool_params,
            timeout_seconds=step.timeout_seconds,
            retry_count=step.retry_count,
        ))

    constraints = _map_constraints(record)
    triggers = _map_triggers(record)

    return RecipeDef(
        id=f"recipe-migrated-{record.id}",
        name=record.name,
        description=record.description,
        goal=record.description or f"Execute the '{record.name}' workflow steps in sequence.",
        mode="strict",
        constraints=constraints,
        strict_steps=strict_steps,
        agent_id=record.base_agent_id,
        triggers=triggers,
    )


def _convert_complex(record: WorkflowRecord) -> RecipeDef:
    """Convert a complex (fork/join/condition/loop) workflow to an adaptive-mode recipe."""
    # Extract goal from description or step instructions
    if record.description:
        goal = record.description
    elif record.workflow_graph:
        agent_instructions = [
            s.instruction for s in record.workflow_graph.steps
            if s.type == "agent" and s.instruction.strip()
        ]
        goal = "; ".join(agent_instructions[:5]) if agent_instructions else f"Execute '{record.name}' workflow."
    else:
        goal = f"Execute '{record.name}' workflow."

    # Generate checkpoints from agent steps
    checkpoints: list[RecipeCheckpoint] = []
    if record.workflow_graph:
        order = 0
        for step in record.workflow_graph.steps:
            if step.type == "agent" and step.instruction.strip():
                checkpoints.append(RecipeCheckpoint(
                    id=f"cp-{step.id}",
                    label=step.label or step.instruction[:50],
                    verification=step.instruction,
                    verification_mode="agent",
                    required=True,
                    order=order,
                ))
                order += 1

    constraints = _map_constraints(record)
    triggers = _map_triggers(record)

    return RecipeDef(
        id=f"recipe-migrated-{record.id}",
        name=record.name,
        description=record.description,
        goal=goal,
        mode="adaptive",
        constraints=constraints,
        checkpoints=checkpoints,
        agent_id=record.base_agent_id,
        triggers=triggers,
    )


def _map_constraints(record: WorkflowRecord) -> RecipeConstraints:
    """Map workflow tool_policy → recipe constraints."""
    tools_allowed: list[str] | None = None
    tools_denied: list[str] | None = None
    if record.tool_policy:
        if record.tool_policy.allow:
            tools_allowed = list(record.tool_policy.allow)
        if record.tool_policy.deny:
            tools_denied = list(record.tool_policy.deny)
    return RecipeConstraints(
        tools_allowed=tools_allowed,
        tools_denied=tools_denied,
    )


def _map_triggers(record: WorkflowRecord) -> list[dict[str, Any]]:
    """Map WorkflowTrigger list → recipe trigger dicts."""
    triggers: list[dict[str, Any]] = []
    for t in record.triggers:
        entry: dict[str, Any] = {"type": t.type}
        if t.cron_expression:
            entry["cron_expression"] = t.cron_expression
        if t.webhook_secret:
            entry["webhook_secret"] = t.webhook_secret
        if t.command_name:
            entry["command_name"] = t.command_name
        if t.last_run_at:
            entry["last_run_at"] = t.last_run_at
        if t.next_run_at:
            entry["next_run_at"] = t.next_run_at
        triggers.append(entry)
    return triggers


# ---------------------------------------------------------------------------
# Main migration function
# ---------------------------------------------------------------------------

def migrate_workflows(*, dry_run: bool = True) -> MigrationReport:
    """Migrate all workflows to recipes.

    Args:
        dry_run: If True, only report what would happen without writing.

    Returns:
        MigrationReport with per-workflow results.
    """
    from app.workflows.store import get_workflow_store
    from app.workflows.recipe_store import get_recipe_store

    wf_store = get_workflow_store()
    recipe_store = get_recipe_store()

    workflows = wf_store.list()
    report = MigrationReport(total=len(workflows))

    for record in workflows:
        recipe_id = f"recipe-migrated-{record.id}"

        # Skip if already migrated
        existing = recipe_store.get(recipe_id)
        if existing is not None:
            report.results.append(MigrationResult(
                workflow_id=record.id,
                workflow_name=record.name,
                recipe_id=recipe_id,
                mode="",
                step_count=0,
                status="skipped",
                error="Recipe already exists",
            ))
            report.skipped += 1
            continue

        try:
            if _is_linear(record):
                recipe = _convert_linear(record)
                mode = "strict"
                step_count = len(recipe.strict_steps) if recipe.strict_steps else 0
            else:
                recipe = _convert_complex(record)
                mode = "adaptive"
                step_count = len(recipe.checkpoints)

            if not dry_run:
                recipe_store.create(recipe)

            report.results.append(MigrationResult(
                workflow_id=record.id,
                workflow_name=record.name,
                recipe_id=recipe_id,
                mode=mode,
                step_count=step_count,
                status="migrated",
            ))
            report.migrated += 1
            logger.info(
                "workflow_migrated%s workflow_id=%s recipe_id=%s mode=%s",
                " (dry_run)" if dry_run else "",
                record.id, recipe_id, mode,
            )

        except Exception as exc:
            report.results.append(MigrationResult(
                workflow_id=record.id,
                workflow_name=record.name,
                recipe_id=recipe_id,
                mode="",
                step_count=0,
                status="error",
                error=str(exc),
            ))
            report.errors += 1
            logger.error("workflow_migration_failed workflow_id=%s error=%s", record.id, exc)

    return report
