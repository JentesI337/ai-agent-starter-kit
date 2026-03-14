"""Recipe tools — checkpoint signaling, create, and update.

Mixin that gives agents the `recipe_checkpoint`, `create_recipe`, and
`update_recipe` tools.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.shared.errors import ToolExecutionError

logger = logging.getLogger(__name__)


def _generate_mermaid(recipe_data: dict) -> str:
    """Build a mermaid flowchart string from recipe response data."""
    mode = recipe_data.get("mode", "adaptive")
    lines = ["graph TD"]

    if mode == "strict" and recipe_data.get("strict_steps"):
        steps = recipe_data["strict_steps"]
        for i, step in enumerate(steps):
            label = step.get("label") or step.get("instruction", f"Step {i + 1}")
            tool = step.get("tool")
            node_id = f"S{i + 1}"
            if tool:
                lines.append(f'    {node_id}["{label}\\ntool: {tool}"]')
            else:
                lines.append(f'    {node_id}["{label}"]')
        for i in range(len(steps) - 1):
            lines.append(f"    S{i + 1} --> S{i + 2}")
    else:
        checkpoints = recipe_data.get("checkpoints", [])
        if not checkpoints:
            lines.append('    START["Start"] --> END["End"]')
        else:
            for i, cp in enumerate(checkpoints):
                label = cp.get("label", f"Checkpoint {i + 1}")
                node_id = f"CP{i + 1}"
                lines.append(f'    {node_id}["{label}"]')
            for i in range(len(checkpoints) - 1):
                lines.append(f"    CP{i + 1} --> CP{i + 2}")

    return "\n".join(lines)


class RecipeToolMixin:
    """Tool mixin for recipe checkpoint signaling and recipe management."""

    async def recipe_checkpoint(
        self,
        *,
        checkpoint_id: str,
        evidence: str,
        **_kwargs,
    ) -> str:
        """Signal that a recipe checkpoint has been reached."""
        from app.recipes.recipe_runner import _ACTIVE_RUNS

        # Find the active run from the session_id pattern "recipe-{run_id}"
        # We need to search _ACTIVE_RUNS for a matching checkpoint
        run_ctx = None
        for run_id, ctx in _ACTIVE_RUNS.items():
            for cp in ctx.recipe.checkpoints:
                if cp.id == checkpoint_id:
                    run_ctx = ctx
                    break
            if run_ctx:
                break

        if run_ctx is None:
            raise ToolExecutionError(
                f"No active recipe run found with checkpoint '{checkpoint_id}'. "
                "Make sure you are in a recipe execution context."
            )

        # Find the checkpoint definition
        checkpoint = None
        for cp in run_ctx.recipe.checkpoints:
            if cp.id == checkpoint_id:
                checkpoint = cp
                break

        if checkpoint is None:
            raise ToolExecutionError(f"Unknown checkpoint_id: {checkpoint_id}")

        # Evaluate the checkpoint
        from app.recipes import checkpoint_eval

        if checkpoint.verification_mode == "assert":
            context = {
                "evidence": evidence,
                "checkpoint_id": checkpoint_id,
                **run_ctx.state.context,
            }
            passed, explanation = checkpoint_eval.evaluate_assert(
                checkpoint.verification, context
            )
        else:
            passed, explanation = await checkpoint_eval.evaluate_agent(
                rubric=checkpoint.verification,
                evidence=evidence,
                context=run_ctx.state.context,
                llm_client=run_ctx.llm_client,
            )

        # Record result
        from app.recipes.recipe_models import CheckpointResult

        result = CheckpointResult(
            checkpoint_id=checkpoint_id,
            reached_at=datetime.now(UTC).isoformat(),
            verification_passed=passed,
            verification_output=explanation,
        )
        run_ctx.state.checkpoints_reached[checkpoint_id] = result

        # Broadcast SSE event
        event_type = "recipe_checkpoint_passed" if passed else "recipe_checkpoint_failed"
        await run_ctx.send_event({
            "type": event_type,
            "run_id": run_ctx.run_id,
            "checkpoint_id": checkpoint_id,
            "label": checkpoint.label,
            "passed": passed,
            "explanation": explanation,
        })

        status = "PASSED" if passed else "FAILED"
        return json.dumps({
            "status": status,
            "checkpoint_id": checkpoint_id,
            "label": checkpoint.label,
            "explanation": explanation,
        })

    async def create_recipe(
        self,
        *,
        name: str,
        description: str = "",
        goal: str = "",
        mode: str = "adaptive",
        checkpoints: str = "[]",
        strict_steps: str = "[]",
        constraints: str = "{}",
        **_kwargs,
    ) -> str:
        """Create a new recipe via the internal handler, returning preview + mermaid diagram."""
        try:
            checkpoints_parsed = json.loads(checkpoints) if isinstance(checkpoints, str) else checkpoints
        except json.JSONDecodeError:
            raise ToolExecutionError("checkpoints must be valid JSON")

        try:
            strict_steps_parsed = json.loads(strict_steps) if isinstance(strict_steps, str) else strict_steps
        except json.JSONDecodeError:
            raise ToolExecutionError("strict_steps must be valid JSON")

        try:
            constraints_parsed = json.loads(constraints) if isinstance(constraints, str) else constraints
        except json.JSONDecodeError:
            constraints_parsed = {}

        try:
            from app.recipes import recipe_handlers

            request_data = {
                "name": name,
                "description": description,
                "goal": goal,
                "mode": mode,
                "checkpoints": checkpoints_parsed,
                "strict_steps": strict_steps_parsed,
                "constraints": constraints_parsed,
            }

            result = recipe_handlers.api_control_recipes_create(request_data)
            recipe = result.get("recipe", {})
            recipe_id = recipe.get("id", "unknown")
            mermaid = _generate_mermaid(recipe)

            return json.dumps({
                "status": "created",
                "recipe_created": True,
                "recipe_id": recipe_id,
                "name": recipe.get("name", name),
                "mode": recipe.get("mode", mode),
                "checkpoint_count": recipe.get("checkpoint_count", 0),
                "step_count": recipe.get("step_count", 0),
                "warnings": result.get("warnings", []),
                "message": f"Recipe '{name}' created successfully.",
                "type": "visualization",
                "viz_type": "mermaid",
                "data": mermaid,
            })
        except Exception as exc:
            raise ToolExecutionError(f"Failed to create recipe: {exc}") from exc

    async def update_recipe(
        self,
        *,
        recipe_id: str,
        name: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        mode: str | None = None,
        checkpoints: str | None = None,
        strict_steps: str | None = None,
        constraints: str | None = None,
        **_kwargs,
    ) -> str:
        """Update an existing recipe via the internal handler, returning refreshed preview."""
        request_data: dict = {"id": recipe_id}

        if name is not None:
            request_data["name"] = name
        if description is not None:
            request_data["description"] = description
        if goal is not None:
            request_data["goal"] = goal
        if mode is not None:
            request_data["mode"] = mode

        if checkpoints is not None:
            try:
                request_data["checkpoints"] = json.loads(checkpoints) if isinstance(checkpoints, str) else checkpoints
            except json.JSONDecodeError:
                raise ToolExecutionError("checkpoints must be valid JSON")

        if strict_steps is not None:
            try:
                request_data["strict_steps"] = json.loads(strict_steps) if isinstance(strict_steps, str) else strict_steps
            except json.JSONDecodeError:
                raise ToolExecutionError("strict_steps must be valid JSON")

        if constraints is not None:
            try:
                request_data["constraints"] = json.loads(constraints) if isinstance(constraints, str) else constraints
            except json.JSONDecodeError:
                request_data["constraints"] = {}

        try:
            from app.recipes import recipe_handlers

            result = recipe_handlers.api_control_recipes_update(request_data)
            recipe = result.get("recipe", {})
            mermaid = _generate_mermaid(recipe)

            return json.dumps({
                "status": "updated",
                "recipe_created": True,
                "recipe_id": recipe.get("id", recipe_id),
                "name": recipe.get("name", ""),
                "mode": recipe.get("mode", ""),
                "checkpoint_count": recipe.get("checkpoint_count", 0),
                "step_count": recipe.get("step_count", 0),
                "warnings": result.get("warnings", []),
                "message": f"Recipe '{recipe.get('name', recipe_id)}' updated successfully.",
                "type": "visualization",
                "viz_type": "mermaid",
                "data": mermaid,
            })
        except Exception as exc:
            raise ToolExecutionError(f"Failed to update recipe: {exc}") from exc
