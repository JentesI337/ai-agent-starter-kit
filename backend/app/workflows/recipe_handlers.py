"""Recipe CRUD handlers — mirrors the pattern from workflows/handlers.py.

Provides list, get, create, update, delete, validate, and execute operations for recipes.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.workflows.recipe_models import (
    RecipeCheckpoint,
    RecipeConstraints,
    RecipeDef,
    StrictStep,
)
from app.workflows.recipe_store import SqliteRecipeRunStore, SqliteRecipeStore

logger = logging.getLogger(__name__)


@dataclass
class RecipeDependencies:
    settings: Any
    recipe_store: SqliteRecipeStore
    run_agent_fn: Callable[[str, str, str], Awaitable[str]] | None = None
    recipe_run_store: SqliteRecipeRunStore | None = None
    llm_client: Any = None
    invoke_tool_fn: Callable | None = None


_deps: RecipeDependencies | None = None


def configure(deps: RecipeDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> RecipeDependencies:
    if _deps is None:
        raise RuntimeError("recipe handlers not configured")
    return _deps


def _normalize_recipe_id(raw: str) -> str:
    candidate = (raw or "").strip().lower()
    candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
    candidate = re.sub(r"-+", "-", candidate).strip("-")
    return candidate[:80]


def _find_recipe_or_404(recipe_id: str) -> RecipeDef:
    deps = _require_deps()
    normalized = _normalize_recipe_id(recipe_id)
    record = deps.recipe_store.get(normalized)
    if record is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return record


def _recipe_to_response(recipe: RecipeDef) -> dict:
    return {
        "id": recipe.id,
        "name": recipe.name,
        "description": recipe.description,
        "goal": recipe.goal,
        "mode": recipe.mode,
        "constraints": recipe.constraints.model_dump(mode="json"),
        "checkpoints": [c.model_dump(mode="json") for c in recipe.checkpoints],
        "strict_steps": [s.model_dump(mode="json") for s in recipe.strict_steps] if recipe.strict_steps else None,
        "agent_id": recipe.agent_id,
        "triggers": recipe.triggers,
        "checkpoint_count": len(recipe.checkpoints),
        "step_count": len(recipe.strict_steps) if recipe.strict_steps else 0,
        "version": recipe.version,
        "created_at": recipe.created_at,
        "updated_at": recipe.updated_at,
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_checkpoints(checkpoints: list[RecipeCheckpoint]) -> list[str]:
    """Validate checkpoint ordering and return warnings."""
    warnings: list[str] = []
    ids_seen: set[str] = set()
    for cp in checkpoints:
        if cp.id in ids_seen:
            warnings.append(f"Duplicate checkpoint id: {cp.id}")
        ids_seen.add(cp.id)
    orders = [cp.order for cp in checkpoints]
    if orders != sorted(orders):
        warnings.append("Checkpoint orders are not sequential")
    return warnings


def _validate_strict_steps(steps: list[StrictStep]) -> list[str]:
    """Validate strict step definitions and return warnings."""
    from app.tools.catalog import TOOL_NAMES

    warnings: list[str] = []
    ids_seen: set[str] = set()
    ordered_ids: list[str] = []

    for step in steps:
        if step.id in ids_seen:
            warnings.append(f"Duplicate step id: {step.id}")
        ids_seen.add(step.id)
        if not step.instruction and not step.tool:
            warnings.append(f"Step {step.id} has no instruction and no tool")

        # Validate tool name exists in catalog
        if step.tool and step.tool not in TOOL_NAMES:
            warnings.append(f"Step {step.id} references unknown tool: {step.tool}")

        # Validate template references don't use forward references
        if step.tool_params:
            import re
            for val in step.tool_params.values():
                if isinstance(val, str):
                    refs = re.findall(r"\{\{(\w+)\.", val)
                    for ref in refs:
                        if ref != "input" and ref not in ordered_ids:
                            warnings.append(
                                f"Step {step.id} references '{ref}' which is not a prior step"
                            )

        ordered_ids.append(step.id)

    return warnings


def _validate_recipe(recipe: RecipeDef) -> list[str]:
    """Full recipe validation, returns list of warning strings."""
    warnings: list[str] = []
    if not recipe.name:
        warnings.append("Recipe name is empty")
    if not recipe.goal:
        warnings.append("Recipe goal is empty")
    if recipe.mode == "adaptive":
        warnings.extend(_validate_checkpoints(recipe.checkpoints))
    elif recipe.mode == "strict":
        if not recipe.strict_steps:
            warnings.append("Strict mode recipe has no steps")
        else:
            warnings.extend(_validate_strict_steps(recipe.strict_steps))
    return warnings


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _parse_constraints(raw: Any) -> RecipeConstraints:
    if raw is None:
        return RecipeConstraints()
    if isinstance(raw, dict):
        return RecipeConstraints.model_validate(raw)
    return RecipeConstraints()


def _parse_checkpoints(raw: Any) -> list[RecipeCheckpoint]:
    if not raw or not isinstance(raw, list):
        return []
    result: list[RecipeCheckpoint] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(RecipeCheckpoint.model_validate(item))
    return result


def _parse_strict_steps(raw: Any) -> list[StrictStep] | None:
    if not raw or not isinstance(raw, list):
        return None
    result: list[StrictStep] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(StrictStep.model_validate(item))
    return result if result else None


def _parse_triggers(raw: Any) -> list[dict[str, Any]]:
    if not raw or not isinstance(raw, list):
        return []
    return [t if isinstance(t, dict) else {} for t in raw]


# ---------------------------------------------------------------------------
# CRUD handlers
# ---------------------------------------------------------------------------

def api_control_recipes_list(request_data: dict) -> dict:
    deps = _require_deps()
    limit = max(1, min(int(request_data.get("limit", 100)), 500))
    items = deps.recipe_store.list(limit=limit)
    return {
        "schema": "recipes.list.v1",
        "count": len(items),
        "items": [_recipe_to_response(r) for r in items],
    }


def api_control_recipes_get(request_data: dict) -> dict:
    recipe_id = request_data.get("recipe_id", "")
    recipe = _find_recipe_or_404(recipe_id)
    return {
        "schema": "recipes.get.v1",
        "recipe": _recipe_to_response(recipe),
    }


def api_control_recipes_create(request_data: dict) -> dict:
    deps = _require_deps()

    name = (request_data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Recipe name must not be empty")

    raw_id = (request_data.get("id") or "").strip()
    if raw_id:
        recipe_id = _normalize_recipe_id(raw_id)
    else:
        recipe_id = _normalize_recipe_id(f"recipe-{name}-{str(uuid.uuid4())[:8]}")

    mode = (request_data.get("mode") or "adaptive").strip().lower()
    if mode not in ("adaptive", "strict"):
        mode = "adaptive"

    recipe = RecipeDef(
        id=recipe_id,
        name=name,
        description=(request_data.get("description") or "").strip(),
        goal=(request_data.get("goal") or "").strip(),
        mode=mode,
        constraints=_parse_constraints(request_data.get("constraints")),
        checkpoints=_parse_checkpoints(request_data.get("checkpoints")),
        strict_steps=_parse_strict_steps(request_data.get("strict_steps")),
        agent_id=request_data.get("agent_id"),
        triggers=_parse_triggers(request_data.get("triggers")),
    )

    warnings = _validate_recipe(recipe)

    created = deps.recipe_store.create(recipe)

    return {
        "schema": "recipes.create.v1",
        "status": "created",
        "recipe": _recipe_to_response(created),
        "warnings": warnings,
    }


def api_control_recipes_update(request_data: dict) -> dict:
    deps = _require_deps()

    recipe_id = (request_data.get("id") or "").strip()
    if not recipe_id:
        raise HTTPException(status_code=400, detail="Recipe id must not be empty")

    recipe_id = _normalize_recipe_id(recipe_id)
    existing = deps.recipe_store.get(recipe_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    name = request_data.get("name", existing.name) or existing.name
    description = request_data.get("description") if request_data.get("description") is not None else existing.description
    goal = request_data.get("goal") if request_data.get("goal") is not None else existing.goal
    mode = request_data.get("mode", existing.mode) or existing.mode

    constraints = (
        _parse_constraints(request_data["constraints"])
        if "constraints" in request_data
        else existing.constraints
    )
    checkpoints = (
        _parse_checkpoints(request_data["checkpoints"])
        if "checkpoints" in request_data
        else existing.checkpoints
    )
    strict_steps = (
        _parse_strict_steps(request_data["strict_steps"])
        if "strict_steps" in request_data
        else existing.strict_steps
    )
    triggers = (
        _parse_triggers(request_data["triggers"])
        if "triggers" in request_data
        else existing.triggers
    )
    agent_id = request_data.get("agent_id", existing.agent_id)

    updated_recipe = RecipeDef(
        id=recipe_id,
        name=name,
        description=description,
        goal=goal,
        mode=mode,
        constraints=constraints,
        checkpoints=checkpoints,
        strict_steps=strict_steps,
        agent_id=agent_id,
        triggers=triggers,
    )

    warnings = _validate_recipe(updated_recipe)
    updated = deps.recipe_store.update(recipe_id, updated_recipe)

    return {
        "schema": "recipes.update.v1",
        "status": "updated",
        "recipe": _recipe_to_response(updated),
        "warnings": warnings,
    }


def api_control_recipes_delete(request_data: dict) -> dict:
    deps = _require_deps()

    recipe_id = _normalize_recipe_id(request_data.get("recipe_id", ""))
    if not recipe_id:
        raise HTTPException(status_code=400, detail="Recipe id must not be empty")

    recipe = _find_recipe_or_404(recipe_id)
    deleted = deps.recipe_store.delete(recipe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return {
        "schema": "recipes.delete.v1",
        "status": "deleted",
        "recipe": {"id": recipe_id, "name": recipe.name},
    }


def api_control_recipes_validate(request_data: dict) -> dict:
    """Validate a recipe definition without saving it."""
    mode = (request_data.get("mode") or "adaptive").strip().lower()
    recipe = RecipeDef(
        id="validation-tmp",
        name=request_data.get("name", ""),
        description=request_data.get("description", ""),
        goal=request_data.get("goal", ""),
        mode=mode,
        constraints=_parse_constraints(request_data.get("constraints")),
        checkpoints=_parse_checkpoints(request_data.get("checkpoints")),
        strict_steps=_parse_strict_steps(request_data.get("strict_steps")),
    )

    warnings = _validate_recipe(recipe)
    return {
        "schema": "recipes.validate.v1",
        "valid": len(warnings) == 0,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Execute handler
# ---------------------------------------------------------------------------

def api_control_recipes_execute(request_data: dict) -> dict:
    """Start executing a recipe. Returns immediately with run_id."""
    deps = _require_deps()

    recipe_id = (request_data.get("recipe_id") or "").strip()
    if not recipe_id:
        raise HTTPException(status_code=400, detail="recipe_id is required")

    recipe = _find_recipe_or_404(recipe_id)
    message = (request_data.get("message") or "").strip()

    if deps.run_agent_fn is None or deps.recipe_run_store is None:
        raise HTTPException(status_code=500, detail="Recipe execution not configured")

    from app.workflows.recipe_runner import RecipeRunner

    runner = RecipeRunner(
        run_agent_fn=deps.run_agent_fn,
        recipe_run_store=deps.recipe_run_store,
        llm_client=deps.llm_client,
        invoke_tool_fn=deps.invoke_tool_fn,
        recipe_store=deps.recipe_store,
    )

    # Generate run_id upfront so we can return it immediately
    run_id = str(uuid.uuid4())

    async def _run() -> None:
        try:
            await runner.execute(recipe, message, run_id=run_id)
        except Exception as exc:
            logger.error("recipe_execute_task_failed recipe_id=%s error=%s", recipe_id, exc)

    task = asyncio.ensure_future(_run())

    def _on_done(t: asyncio.Task) -> None:
        exc = t.exception() if not t.cancelled() else None
        if exc:
            logger.error("recipe_task_exception recipe_id=%s error=%s", recipe_id, exc)

    task.add_done_callback(_on_done)

    return {
        "schema": "recipes.execute.v1",
        "status": "started",
        "recipe_id": recipe_id,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Resume handler
# ---------------------------------------------------------------------------

def api_control_recipes_resume(request_data: dict) -> dict:
    """Resume a paused recipe run."""
    deps = _require_deps()

    run_id = (request_data.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required")

    if deps.recipe_run_store is None:
        raise HTTPException(status_code=500, detail="Recipe execution not configured")

    state = deps.recipe_run_store.get_by_run_id(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if state.status != "paused":
        raise HTTPException(status_code=409, detail=f"Run is not paused (status={state.status})")

    recipe = deps.recipe_store.get(state.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if deps.run_agent_fn is None:
        raise HTTPException(status_code=500, detail="Recipe execution not configured")

    resume_data = request_data.get("resume_data")

    from app.workflows.recipe_runner import RecipeRunner

    runner = RecipeRunner(
        run_agent_fn=deps.run_agent_fn,
        recipe_run_store=deps.recipe_run_store,
        llm_client=deps.llm_client,
        invoke_tool_fn=deps.invoke_tool_fn,
        recipe_store=deps.recipe_store,
    )

    async def _run() -> None:
        try:
            await runner.resume(run_id, resume_data)
        except Exception as exc:
            logger.error("recipe_resume_task_failed run_id=%s error=%s", run_id, exc)

    task = asyncio.ensure_future(_run())

    def _on_done(t: asyncio.Task) -> None:
        exc = t.exception() if not t.cancelled() else None
        if exc:
            logger.error("recipe_resume_exception run_id=%s error=%s", run_id, exc)

    task.add_done_callback(_on_done)

    return {
        "schema": "recipes.resume.v1",
        "status": "resumed",
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Migration handler
# ---------------------------------------------------------------------------

def api_control_recipes_migrate(request_data: dict) -> dict:
    """Migrate workflows to recipes.  dry_run=True (default) previews only."""
    from app.workflows.migrate_to_recipes import migrate_workflows
    from dataclasses import asdict

    dry_run = request_data.get("dry_run", True)
    if isinstance(dry_run, str):
        dry_run = dry_run.lower() not in ("false", "0", "no")

    report = migrate_workflows(dry_run=dry_run)
    return {
        "schema": "recipes.migrate.v1",
        "dry_run": dry_run,
        "total": report.total,
        "migrated": report.migrated,
        "skipped": report.skipped,
        "errors": report.errors,
        "results": [asdict(r) for r in report.results],
    }
