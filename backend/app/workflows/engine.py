"""Sequential workflow execution engine with data flow between steps.

Uses a RunAgentFn callback to execute agent steps — no direct dependency
on OrchestratorApi, RequestContext, or any agent-domain code.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.workflows.models import (
    StepResult,
    WorkflowExecutionState,
    WorkflowGraphDef,
    WorkflowStepDef,
)
from app.workflows.transforms import (
    evaluate_condition,
    resolve_params,
    resolve_templates,
)

logger = logging.getLogger(__name__)

# Callback type: (agent_id, message, session_id) → output
RunAgentFn = Callable[[str, str, str], Awaitable[str]]


class WorkflowEngine:
    """Executes a WorkflowGraphDef with data flow between steps."""

    def __init__(
        self,
        *,
        run_agent: RunAgentFn | None = None,
        connector_store: Any | None = None,
        credential_store: Any | None = None,
        connector_registry: Any | None = None,
        audit_store: Any | None = None,
    ) -> None:
        self._run_agent = run_agent
        self._connector_store = connector_store
        self._credential_store = credential_store
        self._connector_registry = connector_registry
        self._audit_store = audit_store

    async def execute(
        self,
        *,
        graph: WorkflowGraphDef,
        run_id: str,
        session_id: str,
        initial_message: str,
        workflow_id: str,
        send_event: Callable,
        mode: str = "sequential",
        existing_state: WorkflowExecutionState | None = None,
    ) -> WorkflowExecutionState:
        if existing_state is not None:
            state = existing_state
            state.status = "running"
            state.started_at = datetime.now(UTC).isoformat()
            state.context = {"input": {"message": initial_message}}
        else:
            state = WorkflowExecutionState(
                workflow_id=workflow_id,
                run_id=run_id,
                session_id=session_id,
                status="running",
                started_at=datetime.now(UTC).isoformat(),
                context={"input": {"message": initial_message}},
            )

        exec_kwargs = {
            "graph": graph,
            "state": state,
            "run_id": run_id,
            "session_id": session_id,
            "send_event": send_event,
        }

        if mode == "parallel":
            return await self._execute_parallel(**exec_kwargs)
        return await self._execute_sequential(**exec_kwargs)

    async def _execute_sequential(
        self,
        *,
        graph: WorkflowGraphDef,
        state: WorkflowExecutionState,
        run_id: str,
        session_id: str,
        send_event: Callable,
    ) -> WorkflowExecutionState:
        self._current_graph = graph
        current_step_id: str | None = graph.entry_step_id

        # Repair broken chains: if steps are unreachable, infer linear order
        reachable: set[str] = set()
        visit_queue: list[str] = [graph.entry_step_id] if graph.entry_step_id else []
        while visit_queue:
            sid = visit_queue.pop()
            if sid in reachable:
                continue
            reachable.add(sid)
            s = graph.get_step(sid)
            if not s:
                continue
            visit_queue.extend(
                target for target in [s.next_step, s.on_true, s.on_false, s.loop_body_entry]
                if target and target not in reachable
            )
            visit_queue.extend(
                target for target in (s.next_steps or [])
                if target not in reachable
            )

        if len(reachable) < len(graph.steps):
            logger.warning("workflow_chain_broken: %d/%d steps reachable, repairing",
                           len(reachable), len(graph.steps))
            for i, step in enumerate(graph.steps):
                if i + 1 < len(graph.steps) and not step.next_step and not step.on_true and not step.next_steps:
                    step.next_step = graph.steps[i + 1].id

        while current_step_id is not None:
            step_def = graph.get_step(current_step_id)
            if step_def is None:
                logger.error("workflow_step_not_found step_id=%s workflow=%s", current_step_id, state.workflow_id)
                state.status = "failed"
                break

            state.current_step_id = current_step_id
            await self._emit(send_event, "workflow_step_started", {
                "step_id": step_def.id,
                "step_type": step_def.type,
                "label": step_def.label or step_def.id,
            })

            t0 = time.monotonic()
            result = await self._execute_step(
                step_def=step_def,
                state=state,
                run_id=run_id,
                session_id=session_id,
                send_event=send_event,
            )
            result.duration_ms = int((time.monotonic() - t0) * 1000)

            state.step_results[step_def.id] = result
            self._write_step_audit(state, result)
            if result.output is not None:
                state.context[step_def.id] = {"output": result.output}

            if result.status == "error":
                await self._emit(send_event, "workflow_step_failed", {
                    "step_id": step_def.id,
                    "error": result.error or "Unknown error",
                })
                state.status = "failed"
                break

            output_preview = str(result.output)[:200] if result.output is not None else ""
            await self._emit(send_event, "workflow_step_completed", {
                "step_id": step_def.id,
                "status": result.status,
                "output_preview": output_preview,
                "duration_ms": result.duration_ms,
            })

            # Determine next step
            current_step_id = self._resolve_next_step(step_def, result, state)

        if state.status == "running":
            state.status = "completed"

        state.current_step_id = None
        state.completed_at = datetime.now(UTC).isoformat()

        self._write_summary_audit(state, graph)

        total_ms = sum(r.duration_ms for r in state.step_results.values())
        await self._emit(send_event, "workflow_completed", {
            "status": state.status,
            "total_duration_ms": total_ms,
            "steps_completed": sum(1 for r in state.step_results.values() if r.status == "success"),
            "steps_total": len(graph.steps),
            "output_dir": state.output_dir or "",
        })

        return state

    async def _execute_parallel(
        self,
        *,
        graph: WorkflowGraphDef,
        state: WorkflowExecutionState,
        run_id: str,
        session_id: str,
        send_event: Callable,
    ) -> WorkflowExecutionState:
        # Emit started for all steps at once
        for step_def in graph.steps:
            await self._emit(send_event, "workflow_step_started", {
                "step_id": step_def.id,
                "step_type": step_def.type,
                "label": step_def.label or step_def.id,
            })

        context_lock = asyncio.Lock()

        async def _run_one(step_def: WorkflowStepDef) -> StepResult:
            t0 = time.monotonic()
            result = await self._execute_step(
                step_def=step_def,
                state=state,
                run_id=run_id,
                session_id=session_id,
                send_event=send_event,
            )
            result.duration_ms = int((time.monotonic() - t0) * 1000)

            async with context_lock:
                state.step_results[step_def.id] = result
                self._write_step_audit(state, result)
                if result.output is not None:
                    state.context[step_def.id] = {"output": result.output}

            if result.status == "error":
                await self._emit(send_event, "workflow_step_failed", {
                    "step_id": step_def.id,
                    "error": result.error or "Unknown",
                })
            else:
                await self._emit(send_event, "workflow_step_completed", {
                    "step_id": step_def.id,
                    "status": result.status,
                    "output_preview": str(result.output)[:200] if result.output else "",
                    "duration_ms": result.duration_ms,
                })
            return result

        results = await asyncio.gather(*[_run_one(s) for s in graph.steps], return_exceptions=True)

        # Log any exceptions from gather
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                step_id = graph.steps[i].id if i < len(graph.steps) else f"step-{i}"
                logger.error("workflow_parallel_step_exception step_id=%s error=%s", step_id, r)

        # Finalize
        has_errors = any(r.status == "error" for r in state.step_results.values())
        state.status = "failed" if has_errors else "completed"
        state.current_step_id = None
        state.completed_at = datetime.now(UTC).isoformat()

        self._write_summary_audit(state, graph)

        total_ms = sum(r.duration_ms for r in state.step_results.values())
        await self._emit(send_event, "workflow_completed", {
            "status": state.status,
            "total_duration_ms": total_ms,
            "steps_completed": sum(1 for r in state.step_results.values() if r.status == "success"),
            "steps_total": len(graph.steps),
            "output_dir": state.output_dir or "",
        })

        return state

    async def _execute_step(
        self,
        *,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
        run_id: str,
        session_id: str,
        send_event: Callable,
    ) -> StepResult:
        try:
            if step_def.type == "agent":
                return await self._execute_agent_step(
                    step_def=step_def,
                    state=state,
                    run_id=run_id,
                    session_id=session_id,
                    send_event=send_event,
                )
            if step_def.type == "connector":
                return await self._execute_connector_step(step_def, state)
            if step_def.type == "transform":
                return self._execute_transform_step(step_def, state)
            if step_def.type == "condition":
                return self._execute_condition_step(step_def, state)
            if step_def.type == "delay":
                return await self._execute_delay_step(step_def)
            if step_def.type == "fork":
                return await self._execute_fork_step(
                    step_def=step_def,
                    state=state,
                    graph=getattr(self, '_current_graph', None),
                    run_id=run_id,
                    session_id=session_id,
                    send_event=send_event,
                )
            if step_def.type == "join":
                return self._execute_join_step(step_def, state)
            if step_def.type == "loop":
                return self._execute_loop_step(step_def, state)
            if step_def.type in ("trigger", "end"):
                return self._execute_passthrough_step(step_def, state)
            return StepResult(step_id=step_def.id, status="error", error=f"Unknown step type: {step_def.type}")
        except TimeoutError:
            return StepResult(step_id=step_def.id, status="timeout", error="Step timed out")
        except Exception as exc:
            logger.exception("workflow_step_error step_id=%s", step_def.id)
            return StepResult(step_id=step_def.id, status="error", error=str(exc))

    async def _execute_agent_step(
        self,
        *,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
        run_id: str,
        session_id: str,
        send_event: Callable,
    ) -> StepResult:
        if self._run_agent is None:
            return StepResult(step_id=step_def.id, status="error", error="No run_agent callback configured")

        # Build the step message with context injection
        instruction = resolve_templates(step_def.instruction, state.context)
        step_message = f"Workflow step [{step_def.label or step_def.id}]: {instruction}"

        # Add context summary from previous steps
        if state.step_results:
            context_lines = []
            for sid, sr in state.step_results.items():
                if sr.output is not None:
                    preview = str(sr.output)[:500]
                    context_lines.append(f"  {sid}: {preview}")
            if context_lines:
                step_message += "\n\nPrevious step outputs:\n" + "\n".join(context_lines)

        agent_id = step_def.agent_id or "head-agent"

        if step_def.timeout_seconds > 0:
            output = await asyncio.wait_for(
                self._run_agent(agent_id, step_message, session_id),
                timeout=step_def.timeout_seconds,
            )
        else:
            output = await self._run_agent(agent_id, step_message, session_id)

        # Handle file output: save agent text to disk
        if step_def.output_type == "file" and output:
            file_path = resolve_templates(step_def.output_path or f"{step_def.id}.txt", state.context)
            output_dir = state.output_dir or str(Path("workflow_outputs") / state.run_id)
            full_path = Path(output_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(str(output), encoding="utf-8")
            return StepResult(
                step_id=step_def.id,
                status="success",
                output={"text": output, "file_path": str(full_path), "file_name": full_path.name},
            )

        return StepResult(step_id=step_def.id, status="success", output=output)

    async def _execute_connector_step(
        self, step_def: WorkflowStepDef, state: WorkflowExecutionState
    ) -> StepResult:
        if not self._connector_store or not self._connector_registry:
            return StepResult(
                step_id=step_def.id, status="error",
                error="Connector services not configured",
            )

        connector_id = step_def.connector_id
        if not connector_id:
            return StepResult(step_id=step_def.id, status="error", error="No connector_id specified")

        config = self._connector_store.get(connector_id)
        if config is None:
            return StepResult(step_id=step_def.id, status="error", error=f"Connector not found: {connector_id}")

        connector = self._connector_registry.create_connector(config)
        method = step_def.connector_method or ""
        params = resolve_params(step_def.connector_params, state.context)

        # Load credentials if available
        if self._credential_store:
            creds = self._credential_store.get(connector_id)
            if creds:
                connector.set_credentials(creds)

        result = await connector.call(method, params)
        return StepResult(step_id=step_def.id, status="success", output=result)

    def _execute_transform_step(
        self, step_def: WorkflowStepDef, state: WorkflowExecutionState
    ) -> StepResult:
        expr = step_def.transform_expr or ""
        # Auto-wrap bare expressions (without {{...}}) so template resolution works
        if expr and "{{" not in expr:
            expr = "{{" + expr + "}}"
        resolved = resolve_templates(expr, state.context)

        # Try to parse as JSON for structured output
        try:
            output = json.loads(resolved)
        except (json.JSONDecodeError, ValueError):
            output = resolved

        return StepResult(step_id=step_def.id, status="success", output=output)

    def _execute_condition_step(
        self, step_def: WorkflowStepDef, state: WorkflowExecutionState
    ) -> StepResult:
        expr = step_def.condition_expr or ""
        try:
            result = evaluate_condition(expr, state.context)
        except ValueError as e:
            return StepResult(step_id=step_def.id, status="error", error=str(e))

        return StepResult(
            step_id=step_def.id,
            status="success",
            output={"condition_result": result, "branch": "true" if result else "false"},
        )

    async def _execute_delay_step(self, step_def: WorkflowStepDef) -> StepResult:
        delay = step_def.timeout_seconds
        await asyncio.sleep(delay)
        return StepResult(step_id=step_def.id, status="success", output={"delayed_seconds": delay})

    def _resolve_next_step(
        self,
        step_def: WorkflowStepDef,
        result: StepResult,
        state: WorkflowExecutionState,
    ) -> str | None:
        """Determine the next step ID based on step type and result."""
        if step_def.type == "condition" and result.status == "success":
            output = result.output or {}
            branch = output.get("branch", "false") if isinstance(output, dict) else "false"
            return step_def.on_true if branch == "true" else step_def.on_false

        if step_def.type == "fork":
            # Fork handles its own dispatch via _execute_fork_step;
            # after fork completes, jump to the join node's next_step.
            if result.output and isinstance(result.output, dict):
                resume_from = result.output.get("_resume_from")
                if resume_from:
                    return resume_from
            return None

        if step_def.type == "loop":
            output = result.output or {}
            if isinstance(output, dict) and output.get("_loop_continue"):
                return step_def.loop_body_entry
            return step_def.next_step  # done port

        return step_def.next_step

    # ── Fork / Join / Loop / Passthrough ─────────────────

    async def _execute_subchain(
        self,
        *,
        entry_step_id: str,
        graph: WorkflowGraphDef,
        state: WorkflowExecutionState,
        run_id: str,
        session_id: str,
        send_event: Callable,
        stop_at_types: set[str],
        context_lock: asyncio.Lock,
    ) -> str | None:
        """Execute steps linearly until hitting a step type in stop_at_types.

        Returns the step_id it stopped at (the join/end), or None.
        """
        current = entry_step_id
        while current is not None:
            step_def = graph.get_step(current)
            if step_def is None:
                break
            if step_def.type in stop_at_types:
                return current  # stop before executing the join/end

            await self._emit(send_event, "workflow_step_started", {
                "step_id": step_def.id,
                "step_type": step_def.type,
                "label": step_def.label or step_def.id,
            })

            t0 = time.monotonic()
            result = await self._execute_step(
                step_def=step_def, state=state,
                run_id=run_id, session_id=session_id,
                send_event=send_event,
            )
            result.duration_ms = int((time.monotonic() - t0) * 1000)

            async with context_lock:
                state.step_results[step_def.id] = result
                self._write_step_audit(state, result)
                if result.output is not None:
                    state.context[step_def.id] = {"output": result.output}

            if result.status == "error":
                await self._emit(send_event, "workflow_step_failed", {
                    "step_id": step_def.id,
                    "error": result.error or "Unknown error",
                })
                return None

            await self._emit(send_event, "workflow_step_completed", {
                "step_id": step_def.id,
                "status": result.status,
                "output_preview": str(result.output)[:200] if result.output else "",
                "duration_ms": result.duration_ms,
            })

            current = self._resolve_next_step(step_def, result, state)

        return None

    async def _execute_fork_step(
        self,
        *,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
        graph: WorkflowGraphDef | None,
        run_id: str,
        session_id: str,
        send_event: Callable,
    ) -> StepResult:
        """Fan-out: run all branch subchains concurrently via asyncio.gather."""
        branch_targets = step_def.next_steps or []
        if not branch_targets:
            return StepResult(
                step_id=step_def.id, status="success",
                output={"branches": 0, "message": "No branches defined"},
            )

        if graph is None:
            return StepResult(
                step_id=step_def.id, status="error",
                error="Fork step requires graph context",
            )

        # Pass through input to all branches
        input_data = None
        for ctx in state.context.values():
            if isinstance(ctx, dict) and "output" in ctx:
                input_data = ctx["output"]

        state.context[step_def.id] = {"output": input_data, "_type": "fork"}

        context_lock = asyncio.Lock()
        join_step_ids: list[str | None] = []

        async def run_branch(target_id: str) -> str | None:
            return await self._execute_subchain(
                entry_step_id=target_id,
                graph=graph,
                state=state,
                run_id=run_id,
                session_id=session_id,
                send_event=send_event,
                stop_at_types={"join", "end"},
                context_lock=context_lock,
            )

        results = await asyncio.gather(
            *[run_branch(t) for t in branch_targets],
            return_exceptions=True,
        )

        # Collect join step IDs
        for r in results:
            if isinstance(r, str):
                join_step_ids.append(r)
            elif isinstance(r, BaseException):
                logger.error("fork_branch_exception: %s", r)

        # Find the join node and its next_step for resumption
        resume_from = None
        for jsid in join_step_ids:
            if jsid:
                join_step = graph.get_step(jsid)
                if join_step and join_step.type == "join":
                    # Execute the join step itself
                    join_result = self._execute_join_step(join_step, state)
                    state.step_results[jsid] = join_result
                    if join_result.output is not None:
                        state.context[jsid] = {"output": join_result.output}
                    await self._emit(send_event, "workflow_step_completed", {
                        "step_id": jsid,
                        "status": join_result.status,
                        "output_preview": str(join_result.output)[:200] if join_result.output else "",
                        "duration_ms": 0,
                    })
                    resume_from = join_step.next_step
                    break

        return StepResult(
            step_id=step_def.id, status="success",
            output={
                "branches": len(branch_targets),
                "_resume_from": resume_from,
            },
        )

    def _execute_join_step(
        self,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
    ) -> StepResult:
        """Fan-in: merge results from join_from steps into JSON dict."""
        sources = step_def.join_from or []
        merged: dict[str, Any] = {}

        for src_id in sources:
            ctx = state.context.get(src_id)
            if ctx and isinstance(ctx, dict) and "output" in ctx:
                merged[src_id] = ctx["output"]

        # If no explicit join_from, gather all completed step outputs
        if not sources:
            for sid, ctx in state.context.items():
                if sid != "input" and isinstance(ctx, dict) and "output" in ctx:
                    merged[sid] = ctx["output"]

        return StepResult(
            step_id=step_def.id, status="success",
            output=merged,
        )

    def _execute_loop_step(
        self,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
    ) -> StepResult:
        """Evaluate loop_condition. Returns result with routing metadata."""
        loop_key = f"_loop_{step_def.id}"
        iteration = state.context.get(loop_key, {}).get("_iteration", 0)

        # Check max iterations
        if iteration >= step_def.loop_max_iterations:
            logger.warning(
                "loop_max_iterations_reached step_id=%s iterations=%d",
                step_def.id, iteration,
            )
            return StepResult(
                step_id=step_def.id, status="success",
                output={"_loop_continue": False, "iteration": iteration, "reason": "max_iterations"},
            )

        # Evaluate condition
        condition = step_def.loop_condition or ""
        if condition:
            from app.workflows.transforms import evaluate_condition
            try:
                should_continue = evaluate_condition(condition, state.context)
            except ValueError:
                should_continue = False
        else:
            should_continue = False

        # Update iteration counter
        state.context[loop_key] = {"_iteration": iteration + 1}

        return StepResult(
            step_id=step_def.id, status="success",
            output={"_loop_continue": should_continue, "iteration": iteration},
        )

    def _execute_passthrough_step(
        self,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
    ) -> StepResult:
        """Trigger/end: pass through input message or context."""
        # For trigger: pass the input message
        if step_def.type == "trigger":
            input_msg = state.context.get("input", {}).get("message", "")
            return StepResult(
                step_id=step_def.id, status="success",
                output=input_msg,
            )
        # For end: pass through last available output
        last_output = None
        for sid, ctx in state.context.items():
            if sid != "input" and isinstance(ctx, dict) and "output" in ctx:
                last_output = ctx["output"]
        return StepResult(
            step_id=step_def.id, status="success",
            output=last_output,
        )

    def _is_audit_enabled(self) -> bool:
        """Check if workflow auditing is enabled via settings."""
        try:
            from app.config.service import get_config_service
            svc = get_config_service()
            return bool(svc.get_value("core", "workflows_audit_enabled"))
        except Exception:
            return False

    def _write_step_audit(self, state: WorkflowExecutionState, result: StepResult) -> None:
        """Write step result to the audit store (if auditing is enabled)."""
        if self._audit_store is None or not self._is_audit_enabled():
            return
        try:
            self._audit_store.write_step(
                workflow_id=state.workflow_id,
                run_id=state.run_id,
                step_id=result.step_id,
                data={
                    "step_id": result.step_id,
                    "status": result.status,
                    "duration_ms": result.duration_ms,
                    "output": result.output,
                    "error": result.error,
                },
            )
        except Exception:
            logger.debug("audit_write_step_failed step_id=%s", result.step_id, exc_info=True)

    def _write_summary_audit(self, state: WorkflowExecutionState, graph: WorkflowGraphDef) -> None:
        """Write final run summary to the audit store (if auditing is enabled)."""
        if self._audit_store is None or not self._is_audit_enabled():
            return
        try:
            self._audit_store.write_summary(
                workflow_id=state.workflow_id,
                run_id=state.run_id,
                data={
                    "workflow_id": state.workflow_id,
                    "run_id": state.run_id,
                    "status": state.status,
                    "started_at": state.started_at,
                    "completed_at": state.completed_at,
                    "steps": {
                        sid: {
                            "step_id": sr.step_id,
                            "status": sr.status,
                            "duration_ms": sr.duration_ms,
                            "output": sr.output,
                            "error": sr.error,
                        }
                        for sid, sr in state.step_results.items()
                    },
                },
            )
        except Exception:
            logger.debug("audit_write_summary_failed run_id=%s", state.run_id, exc_info=True)

    async def _emit(self, send_event: Callable, event_type: str, data: dict) -> None:
        try:
            await send_event({"type": event_type, **data})
        except Exception:
            logger.debug("workflow_event_emit_failed type=%s", event_type, exc_info=True)
