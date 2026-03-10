"""Sequential workflow execution engine with data flow between steps."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.orchestrator.workflow_models import (
    StepResult,
    WorkflowExecutionState,
    WorkflowGraphDef,
    WorkflowStepDef,
)
from app.orchestrator.workflow_transforms import (
    evaluate_condition,
    resolve_params,
    resolve_templates,
)

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "failed", "timed_out", "cancelled"})


class WorkflowEngine:
    """Executes a WorkflowGraphDef sequentially with data flow between steps."""

    def __init__(
        self,
        *,
        subrun_lane: Any,
        connector_store: Any | None = None,
        credential_store: Any | None = None,
        connector_registry: Any | None = None,
    ) -> None:
        self._subrun_lane = subrun_lane
        self._connector_store = connector_store
        self._credential_store = credential_store
        self._connector_registry = connector_registry

    async def execute(
        self,
        *,
        graph: WorkflowGraphDef,
        run_id: str,
        session_id: str,
        initial_message: str,
        workflow_id: str,
        send_event: Callable,
        runtime: str = "api",
        model: str | None = None,
        preset: str | None = None,
        tool_policy: Any = None,
        orchestrator_agent_ids: list[str] | None = None,
        orchestrator_api: Any = None,
    ) -> WorkflowExecutionState:
        state = WorkflowExecutionState(
            workflow_id=workflow_id,
            run_id=run_id,
            session_id=session_id,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            context={"input": {"message": initial_message}},
        )

        current_step_id: str | None = graph.entry_step_id

        while current_step_id is not None:
            step_def = graph.get_step(current_step_id)
            if step_def is None:
                logger.error("workflow_step_not_found step_id=%s workflow=%s", current_step_id, workflow_id)
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
                runtime=runtime,
                model=model,
                preset=preset,
                tool_policy=tool_policy,
                orchestrator_agent_ids=orchestrator_agent_ids or [],
                orchestrator_api=orchestrator_api,
                send_event=send_event,
            )
            result.duration_ms = int((time.monotonic() - t0) * 1000)

            state.step_results[step_def.id] = result
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
        state.completed_at = datetime.now(timezone.utc).isoformat()

        total_ms = sum(r.duration_ms for r in state.step_results.values())
        await self._emit(send_event, "workflow_completed", {
            "status": state.status,
            "total_duration_ms": total_ms,
            "steps_completed": sum(1 for r in state.step_results.values() if r.status == "success"),
            "steps_total": len(graph.steps),
        })

        return state

    async def _execute_step(
        self,
        *,
        step_def: WorkflowStepDef,
        state: WorkflowExecutionState,
        run_id: str,
        session_id: str,
        runtime: str,
        model: str | None,
        preset: str | None,
        tool_policy: Any,
        orchestrator_agent_ids: list[str],
        orchestrator_api: Any,
        send_event: Callable,
    ) -> StepResult:
        try:
            if step_def.type == "agent":
                return await self._execute_agent_step(
                    step_def=step_def,
                    state=state,
                    run_id=run_id,
                    session_id=session_id,
                    runtime=runtime,
                    model=model,
                    preset=preset,
                    tool_policy=tool_policy,
                    orchestrator_agent_ids=orchestrator_agent_ids,
                    orchestrator_api=orchestrator_api,
                    send_event=send_event,
                )
            elif step_def.type == "connector":
                return await self._execute_connector_step(step_def, state)
            elif step_def.type == "transform":
                return self._execute_transform_step(step_def, state)
            elif step_def.type == "condition":
                return self._execute_condition_step(step_def, state)
            elif step_def.type == "delay":
                return await self._execute_delay_step(step_def)
            else:
                return StepResult(step_id=step_def.id, status="error", error=f"Unknown step type: {step_def.type}")
        except asyncio.TimeoutError:
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
        runtime: str,
        model: str | None,
        preset: str | None,
        tool_policy: Any,
        orchestrator_agent_ids: list[str],
        orchestrator_api: Any,
        send_event: Callable,
    ) -> StepResult:
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

        async def _noop_send(_event: dict) -> None:
            return None

        agent_id = step_def.agent_id
        subrun_id = await self._subrun_lane.spawn(
            parent_request_id=run_id,
            parent_session_id=session_id,
            user_message=step_message,
            runtime=runtime,
            model=model or "",
            timeout_seconds=step_def.timeout_seconds,
            tool_policy=tool_policy,
            send_event=_noop_send,
            agent_id=agent_id,
            mode="run",
            preset=preset,
            orchestrator_agent_ids=orchestrator_agent_ids,
            orchestrator_api=orchestrator_api,
        )

        # Poll for completion
        output = await self._await_subrun(subrun_id, step_def.timeout_seconds)
        return StepResult(step_id=step_def.id, status="success", output=output)

    async def _await_subrun(self, subrun_id: str, timeout_seconds: int) -> Any:
        """Poll SubrunLane until the subrun reaches a terminal state."""
        deadline = time.monotonic() + timeout_seconds
        poll_interval = 0.5

        while time.monotonic() < deadline:
            info = self._subrun_lane.get_info(subrun_id)
            if info is None:
                await asyncio.sleep(poll_interval)
                continue

            status = info.get("status", "")
            if status in _TERMINAL_STATUSES:
                handover = info.get("handover") or {}
                return handover.get("result_text") or handover.get("final_text") or ""

            await asyncio.sleep(poll_interval)
            # Gradually increase poll interval (up to 2s)
            poll_interval = min(poll_interval * 1.2, 2.0)

        raise asyncio.TimeoutError(f"Subrun {subrun_id} did not complete within {timeout_seconds}s")

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

        connector = self._connector_registry.create(config)
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

        return step_def.next_step

    async def _emit(self, send_event: Callable, event_type: str, data: dict) -> None:
        try:
            await send_event({"type": event_type, **data})
        except Exception:
            logger.debug("workflow_event_emit_failed type=%s", event_type, exc_info=True)
