"""Recipe execution engine — runs adaptive and strict recipes.

The RecipeRunner orchestrates recipe execution by:
1. Building a recipe-specific system prompt
2. Registering the run in _ACTIVE_RUNS for checkpoint tool lookup
3. Delegating to run_agent_fn (the normal agent loop) OR executing strict steps
4. Tracking budget and checkpoint/step results
5. Broadcasting SSE events
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.workflows.recipe_models import (
    BudgetSnapshot,
    CheckpointResult,
    RecipeDef,
    RecipePausedError,
    RecipeRunState,
    StrictStepResult,
)
from app.workflows.recipe_store import SqliteRecipeRunStore, SqliteRecipeStore
from app.workflows.transforms import resolve_params, resolve_templates

logger = logging.getLogger(__name__)

# Module-level registry — checkpoint tool looks up its context here
_ACTIVE_RUNS: dict[str, "RecipeRunContext"] = {}


@dataclass
class RecipeRunContext:
    run_id: str
    recipe: RecipeDef
    state: RecipeRunState
    send_event: Callable
    llm_client: Any  # for agent-mode checkpoint evaluation


RunAgentFn = Callable[[str, str, str], Awaitable[str]]
InvokeToolFn = Callable[[str, dict], Awaitable[str]]


class RecipeRunner:
    """Executes adaptive and strict recipes."""

    def __init__(
        self,
        *,
        run_agent_fn: RunAgentFn,
        recipe_run_store: SqliteRecipeRunStore,
        llm_client: Any,
        invoke_tool_fn: InvokeToolFn | None = None,
        recipe_store: SqliteRecipeStore | None = None,
    ) -> None:
        self._run_agent_fn = run_agent_fn
        self._recipe_run_store = recipe_run_store
        self._llm_client = llm_client
        self._invoke_tool_fn = invoke_tool_fn
        self._recipe_store = recipe_store

    async def execute(self, recipe: RecipeDef, message: str, *, run_id: str | None = None) -> RecipeRunState:
        run_id = run_id or str(uuid.uuid4())
        session_id = f"recipe-{run_id}"
        agent_id = recipe.agent_id or "head-agent"
        started_at = datetime.now(UTC).isoformat()

        # 1. Create initial run state
        state = RecipeRunState(
            recipe_id=recipe.id,
            run_id=run_id,
            session_id=session_id,
            status="running",
            mode=recipe.mode,
            started_at=started_at,
        )

        # Store max_duration for lifecycle management
        if recipe.constraints.max_duration_seconds:
            state.context["_max_duration_seconds"] = recipe.constraints.max_duration_seconds

        # 2. Setup SSE broadcasting
        send_event, state_holder = self._recipe_run_store.make_send_event(run_id)
        state_holder[0] = state

        # 3. Register in _ACTIVE_RUNS
        ctx = RecipeRunContext(
            run_id=run_id,
            recipe=recipe,
            state=state,
            send_event=send_event,
            llm_client=self._llm_client,
        )
        _ACTIVE_RUNS[run_id] = ctx

        # 4. Save initial state
        self._recipe_run_store.save(state)

        # 5. Broadcast start (include steps for strict, checkpoints for adaptive)
        start_event: dict[str, Any] = {
            "type": "recipe_started",
            "run_id": run_id,
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
        }
        if recipe.mode == "strict" and recipe.strict_steps:
            start_event["steps"] = [
                {"id": s.id, "label": s.label, "tool": s.tool}
                for s in recipe.strict_steps
            ]
        else:
            start_event["checkpoints"] = [
                {"id": cp.id, "label": cp.label, "required": cp.required}
                for cp in recipe.checkpoints
            ]
        await send_event(start_event)

        start_time = time.monotonic()
        try:
            if recipe.mode == "strict":
                # Strict mode: execute steps deterministically
                await self._execute_strict(ctx, recipe, message)
            else:
                # Adaptive mode: delegate to agent
                enriched_message = self._build_recipe_prompt(recipe, message)
                agent_response = await self._run_agent_fn(agent_id, enriched_message, session_id)

            elapsed = time.monotonic() - start_time

            # Update budget
            state.budget_used = BudgetSnapshot(
                duration_seconds=round(elapsed, 2),
            )

            if recipe.mode == "adaptive":
                # Determine final status from checkpoints
                required_cps = [cp for cp in recipe.checkpoints if cp.required]
                all_required_passed = all(
                    cp.id in state.checkpoints_reached
                    and state.checkpoints_reached[cp.id].verification_passed
                    for cp in required_cps
                )
                if all_required_passed:
                    state.status = "completed"
                else:
                    missing = [
                        cp.label for cp in required_cps
                        if cp.id not in state.checkpoints_reached
                        or not state.checkpoints_reached[cp.id].verification_passed
                    ]
                    state.status = "completed"
                    state.context["missing_checkpoints"] = missing
            else:
                state.status = "completed"

            state.completed_at = datetime.now(UTC).isoformat()

            completed_event: dict[str, Any] = {
                "type": "recipe_completed",
                "run_id": run_id,
                "status": state.status,
                "budget_used": state.budget_used.model_dump(mode="json"),
            }
            if recipe.mode == "adaptive":
                completed_event["checkpoints_reached"] = {
                    k: v.model_dump(mode="json")
                    for k, v in state.checkpoints_reached.items()
                }
                completed_event["agent_response_preview"] = (agent_response or "")[:500]
            else:
                completed_event["step_results"] = state.step_results

            await send_event(completed_event)

        except RecipePausedError as pause_exc:
            elapsed = time.monotonic() - start_time
            state.budget_used = BudgetSnapshot(duration_seconds=round(elapsed, 2))
            # State already set to "paused" by _execute_strict
            logger.info("recipe_paused run_id=%s step=%s reason=%s", run_id, pause_exc.step_id, pause_exc.pause_reason)

            await send_event({
                "type": "recipe_paused",
                "run_id": run_id,
                "pause_reason": pause_exc.pause_reason,
                "step_id": pause_exc.step_id,
            })

            _ACTIVE_RUNS.pop(run_id, None)
            self._recipe_run_store.save(state)
            return state

        except Exception as exc:
            elapsed = time.monotonic() - start_time
            state.status = "failed"
            state.completed_at = datetime.now(UTC).isoformat()
            state.budget_used = BudgetSnapshot(duration_seconds=round(elapsed, 2))
            state.context["error"] = str(exc)

            logger.error("recipe_execution_failed run_id=%s error=%s", run_id, exc)

            await send_event({
                "type": "recipe_failed",
                "run_id": run_id,
                "error": str(exc),
            })

        finally:
            _ACTIVE_RUNS.pop(run_id, None)
            self._recipe_run_store.save(state)

        return state

    # ── Strict mode execution ─────────────────────────────────

    async def _execute_strict(
        self, ctx: RecipeRunContext, recipe: RecipeDef, message: str,
    ) -> None:
        """Execute strict steps in sequence with template resolution."""
        steps = recipe.strict_steps or []
        template_context: dict[str, Any] = {"input": {"message": message}}

        for step in steps:
            ctx.state.current_step_id = step.id

            # Wait step detection — pause execution for external events
            if step.tool == "__wait_for_event":
                params = step.tool_params or {}
                pause_reason = params.get("wait_type", "webhook")
                ctx.state.status = "paused"
                ctx.state.pause_reason = pause_reason
                ctx.state.pause_data = params
                ctx.state.paused_at = datetime.now(UTC).isoformat()
                raise RecipePausedError(step.id, pause_reason, params)

            # Resolve tool_params templates
            resolved_params = (
                resolve_params(step.tool_params, template_context)
                if step.tool_params else {}
            )

            await ctx.send_event({
                "type": "recipe_step_started",
                "run_id": ctx.run_id,
                "step_id": step.id,
                "label": step.label,
                "tool": step.tool,
            })

            result = await self._execute_single_step(step, resolved_params, ctx, template_context)

            # Store result
            ctx.state.step_results[step.id] = result.model_dump(mode="json")
            template_context[step.id] = {
                "output": result.tool_output,
                "status": result.status,
                "error": result.error,
            }

            if result.status in ("success",):
                await ctx.send_event({
                    "type": "recipe_step_completed",
                    "run_id": ctx.run_id,
                    "step_id": step.id,
                    "tool": result.tool_called,
                    "output_preview": str(result.tool_output or "")[:500],
                    "duration_ms": result.duration_ms,
                    "retry_attempts": result.retry_attempts,
                })
            else:
                await ctx.send_event({
                    "type": "recipe_step_failed",
                    "run_id": ctx.run_id,
                    "step_id": step.id,
                    "error": result.error or f"Step failed with status: {result.status}",
                    "duration_ms": result.duration_ms,
                    "retry_attempts": result.retry_attempts,
                })
                raise RuntimeError(
                    f"Strict step '{step.id}' failed: {result.error}"
                )

        ctx.state.current_step_id = None

    async def _execute_single_step(
        self, step, resolved_params: dict, ctx: RecipeRunContext,
        template_context: dict[str, Any],
    ) -> StrictStepResult:
        """Execute a single step with retry and timeout support."""
        max_attempts = step.retry_count + 1
        last_error: str | None = None

        for attempt in range(max_attempts):
            step_start = time.monotonic()
            started_at = datetime.now(UTC).isoformat()

            try:
                if step.timeout_seconds:
                    raw_output = await asyncio.wait_for(
                        self._invoke_step(step, resolved_params, ctx, template_context),
                        timeout=step.timeout_seconds,
                    )
                else:
                    raw_output = await self._invoke_step(
                        step, resolved_params, ctx, template_context,
                    )

                elapsed_ms = int((time.monotonic() - step_start) * 1000)

                # Try parsing JSON output
                tool_output: Any = raw_output
                if isinstance(raw_output, str):
                    try:
                        tool_output = json.loads(raw_output)
                    except (json.JSONDecodeError, TypeError):
                        pass

                return StrictStepResult(
                    step_id=step.id,
                    status="success",
                    tool_called=step.tool,
                    tool_output=tool_output,
                    started_at=started_at,
                    completed_at=datetime.now(UTC).isoformat(),
                    duration_ms=elapsed_ms,
                    retry_attempts=attempt,
                )

            except asyncio.TimeoutError:
                last_error = f"Step timed out after {step.timeout_seconds}s"
                logger.warning(
                    "strict_step_timeout step_id=%s attempt=%d/%d",
                    step.id, attempt + 1, max_attempts,
                )
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "strict_step_error step_id=%s attempt=%d/%d error=%s",
                    step.id, attempt + 1, max_attempts, exc,
                )

        # All attempts exhausted
        elapsed_ms = int((time.monotonic() - step_start) * 1000)
        status = "timeout" if "timed out" in (last_error or "") else "failed"
        return StrictStepResult(
            step_id=step.id,
            status=status,
            tool_called=step.tool,
            started_at=started_at,
            completed_at=datetime.now(UTC).isoformat(),
            duration_ms=elapsed_ms,
            retry_attempts=max_attempts - 1,
            error=last_error,
        )

    async def _invoke_step(
        self, step, resolved_params: dict, ctx: RecipeRunContext,
        template_context: dict[str, Any],
    ) -> str:
        """Invoke a single step — either via tool or agent."""
        if step.tool:
            # Direct tool invocation
            if self._invoke_tool_fn is None:
                raise RuntimeError(
                    f"Step '{step.id}' requires tool '{step.tool}' but invoke_tool_fn is not configured"
                )
            return await self._invoke_tool_fn(step.tool, resolved_params)
        else:
            # Agent-decided step: resolve instruction templates and run agent
            instruction = step.instruction or ""
            if instruction:
                instruction = resolve_templates(instruction, template_context)
            else:
                instruction = f"Execute step: {step.label}"

            agent_id = ctx.recipe.agent_id or "head-agent"
            session_id = ctx.state.session_id
            return await self._run_agent_fn(agent_id, instruction, session_id)

    # ── Resume ────────────────────────────────────────────────

    async def resume(self, run_id: str, resume_data: dict[str, Any] | None = None) -> RecipeRunState:
        """Resume a paused recipe run."""
        state = self._recipe_run_store.get_by_run_id(run_id)
        if state is None:
            raise ValueError(f"Run not found: {run_id}")
        if state.status != "paused":
            raise ValueError(f"Run {run_id} is not paused (status={state.status})")

        if self._recipe_store is None:
            raise RuntimeError("recipe_store is required for resume")
        recipe = self._recipe_store.get(state.recipe_id)
        if recipe is None:
            raise ValueError(f"Recipe not found: {state.recipe_id}")

        # Update state
        paused_step_id = state.current_step_id
        state.status = "running"
        state.pause_reason = None
        state.pause_data = None
        state.paused_at = None
        state.resume_data = resume_data
        if resume_data:
            state.context["_resume_payload"] = resume_data

        # Setup SSE broadcasting
        send_event, state_holder = self._recipe_run_store.make_send_event(run_id)
        state_holder[0] = state

        # Register in _ACTIVE_RUNS
        ctx = RecipeRunContext(
            run_id=run_id,
            recipe=recipe,
            state=state,
            send_event=send_event,
            llm_client=self._llm_client,
        )
        _ACTIVE_RUNS[run_id] = ctx

        self._recipe_run_store.save(state)

        await send_event({
            "type": "recipe_resumed",
            "run_id": run_id,
        })

        start_time = time.monotonic()
        try:
            if recipe.mode == "strict":
                await self._resume_strict(ctx, recipe, paused_step_id)
            else:
                # Adaptive mode: re-invoke agent with continuation prompt
                agent_id = recipe.agent_id or "head-agent"
                resume_prompt = self._build_resume_prompt(recipe, resume_data)
                await self._run_agent_fn(agent_id, resume_prompt, state.session_id)

            elapsed = time.monotonic() - start_time
            state.budget_used.duration_seconds += round(elapsed, 2)
            state.status = "completed"
            state.completed_at = datetime.now(UTC).isoformat()

            await send_event({
                "type": "recipe_completed",
                "run_id": run_id,
                "status": state.status,
                "budget_used": state.budget_used.model_dump(mode="json"),
                "step_results": state.step_results if recipe.mode == "strict" else None,
            })

        except RecipePausedError as pause_exc:
            elapsed = time.monotonic() - start_time
            state.budget_used.duration_seconds += round(elapsed, 2)
            logger.info("recipe_paused run_id=%s step=%s reason=%s", run_id, pause_exc.step_id, pause_exc.pause_reason)
            await send_event({
                "type": "recipe_paused",
                "run_id": run_id,
                "pause_reason": pause_exc.pause_reason,
                "step_id": pause_exc.step_id,
            })
            _ACTIVE_RUNS.pop(run_id, None)
            self._recipe_run_store.save(state)
            return state

        except Exception as exc:
            elapsed = time.monotonic() - start_time
            state.status = "failed"
            state.completed_at = datetime.now(UTC).isoformat()
            state.budget_used.duration_seconds += round(elapsed, 2)
            state.context["error"] = str(exc)
            logger.error("recipe_resume_failed run_id=%s error=%s", run_id, exc)
            await send_event({
                "type": "recipe_failed",
                "run_id": run_id,
                "error": str(exc),
            })

        finally:
            _ACTIVE_RUNS.pop(run_id, None)
            self._recipe_run_store.save(state)

        return state

    async def _resume_strict(
        self, ctx: RecipeRunContext, recipe: RecipeDef, paused_step_id: str | None,
    ) -> None:
        """Resume strict mode execution from the step after the paused one."""
        steps = recipe.strict_steps or []

        # Rebuild template_context from completed step results
        template_context: dict[str, Any] = {"input": {"message": ctx.state.context.get("_original_message", "")}}
        for step in steps:
            if step.id in ctx.state.step_results:
                result = ctx.state.step_results[step.id]
                template_context[step.id] = {
                    "output": result.get("tool_output"),
                    "status": result.get("status"),
                    "error": result.get("error"),
                }

        # Find the paused step and skip past it
        skip = True
        for step in steps:
            if skip:
                if step.id == paused_step_id:
                    # Mark the wait step as completed (it was satisfied by resume)
                    ctx.state.step_results[step.id] = StrictStepResult(
                        step_id=step.id,
                        status="success",
                        tool_called="__wait_for_event",
                        tool_output=ctx.state.resume_data,
                        started_at=ctx.state.paused_at or "",
                        completed_at=datetime.now(UTC).isoformat(),
                    ).model_dump(mode="json")
                    template_context[step.id] = {
                        "output": ctx.state.resume_data,
                        "status": "success",
                        "error": None,
                    }
                    skip = False
                continue

            # Execute remaining steps (reuses the same logic as _execute_strict)
            ctx.state.current_step_id = step.id

            # Check for another wait step
            if step.tool == "__wait_for_event":
                params = step.tool_params or {}
                pause_reason = params.get("wait_type", "webhook")
                ctx.state.status = "paused"
                ctx.state.pause_reason = pause_reason
                ctx.state.pause_data = params
                ctx.state.paused_at = datetime.now(UTC).isoformat()
                raise RecipePausedError(step.id, pause_reason, params)

            resolved_params = (
                resolve_params(step.tool_params, template_context)
                if step.tool_params else {}
            )

            await ctx.send_event({
                "type": "recipe_step_started",
                "run_id": ctx.run_id,
                "step_id": step.id,
                "label": step.label,
                "tool": step.tool,
            })

            result = await self._execute_single_step(step, resolved_params, ctx, template_context)
            ctx.state.step_results[step.id] = result.model_dump(mode="json")
            template_context[step.id] = {
                "output": result.tool_output,
                "status": result.status,
                "error": result.error,
            }

            if result.status == "success":
                await ctx.send_event({
                    "type": "recipe_step_completed",
                    "run_id": ctx.run_id,
                    "step_id": step.id,
                    "tool": result.tool_called,
                    "output_preview": str(result.tool_output or "")[:500],
                    "duration_ms": result.duration_ms,
                    "retry_attempts": result.retry_attempts,
                })
            else:
                await ctx.send_event({
                    "type": "recipe_step_failed",
                    "run_id": ctx.run_id,
                    "step_id": step.id,
                    "error": result.error or f"Step failed with status: {result.status}",
                    "duration_ms": result.duration_ms,
                    "retry_attempts": result.retry_attempts,
                })
                raise RuntimeError(f"Strict step '{step.id}' failed: {result.error}")

        ctx.state.current_step_id = None

    @staticmethod
    def _build_resume_prompt(recipe: RecipeDef, resume_data: dict | None) -> str:
        lines = [
            "[RECIPE RESUMED]",
            f'Continuing recipe: "{recipe.name}"',
            f"Goal: {recipe.goal}",
            "",
            "The recipe was paused and has now been resumed.",
        ]
        if resume_data:
            lines.append(f"Resume data: {json.dumps(resume_data, default=str)}")
        lines.extend([
            "",
            "Continue executing the recipe goal from where you left off.",
        ])
        return "\n".join(lines)

    # ── Adaptive mode prompt builder ──────────────────────────

    @staticmethod
    def _build_recipe_prompt(recipe: RecipeDef, user_message: str) -> str:
        lines = [
            "[RECIPE EXECUTION MODE]",
            f'You are executing recipe: "{recipe.name}"',
            f"Goal: {recipe.goal}",
            "",
        ]

        if recipe.checkpoints:
            lines.append("Checkpoints to reach (in order):")
            for i, cp in enumerate(sorted(recipe.checkpoints, key=lambda c: c.order), 1):
                req = " (required)" if cp.required else " (optional)"
                lines.append(f"  {i}. [{cp.id}] {cp.label} — verify by: {cp.verification}{req}")
            lines.append("")

        if recipe.constraints:
            constraint_parts = []
            if recipe.constraints.max_duration_seconds:
                constraint_parts.append(f"max duration: {recipe.constraints.max_duration_seconds}s")
            if recipe.constraints.max_tool_calls:
                constraint_parts.append(f"max tool calls: {recipe.constraints.max_tool_calls}")
            if recipe.constraints.tools_denied:
                constraint_parts.append(f"tools denied: {', '.join(recipe.constraints.tools_denied)}")
            if constraint_parts:
                lines.append(f"Constraints: {'; '.join(constraint_parts)}")
                lines.append("")

        lines.extend([
            "IMPORTANT: After completing each checkpoint, call the `recipe_checkpoint` tool",
            "with the checkpoint_id and evidence of completion.",
            "",
            "---",
            "",
            user_message or "Begin executing the recipe goal.",
        ])

        return "\n".join(lines)
