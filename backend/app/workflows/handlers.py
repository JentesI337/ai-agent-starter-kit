from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.control_models import (
    ControlWorkflowsCreateRequest,
    ControlWorkflowsDeleteRequest,
    ControlWorkflowsExecuteRequest,
    ControlWorkflowsGetRequest,
    ControlWorkflowsListRequest,
    ControlWorkflowsUpdateRequest,
)
from app.errors import GuardrailViolation
from app.services.request_normalization import normalize_idempotency_key
from app.workflows.engine import RunAgentFn
from app.workflows.models import (
    WorkflowGraphDef,
    WorkflowRecord,
    WorkflowStepDef,
    WorkflowToolPolicy,
    WorkflowTrigger,
    _extract_flat_steps,
)
from app.workflows.store import SqliteWorkflowAuditStore, SqliteWorkflowStore

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDependencies:
    settings: Any
    workflow_store: SqliteWorkflowStore
    audit_store: SqliteWorkflowAuditStore | None
    idempotency_mgr: Any
    run_agent: RunAgentFn
    build_workflow_create_fingerprint: Callable[..., str]
    build_workflow_execute_fingerprint: Callable[..., str]
    build_workflow_delete_fingerprint: Callable[..., str]


_deps: WorkflowDependencies | None = None


def configure(deps: WorkflowDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> WorkflowDependencies:
    if _deps is None:
        raise RuntimeError("workflow handlers not configured")
    return _deps


def _normalize_workflow_id(raw: str) -> str:
    """Normalize a raw string to a valid workflow ID."""
    candidate = (raw or "").strip().lower()
    candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
    candidate = re.sub(r"-+", "-", candidate).strip("-")
    return candidate[:80]


def _find_workflow_or_404(workflow_id: str) -> WorkflowRecord:
    deps = _require_deps()
    normalized = _normalize_workflow_id(workflow_id)
    record = deps.workflow_store.get(normalized)
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return record


def _record_to_response(record: WorkflowRecord) -> dict:
    """Build a response dict from a WorkflowRecord with backward-compatible fields."""
    steps = _extract_flat_steps(record)
    tp = None
    if record.tool_policy is not None:
        tp = {"allow": record.tool_policy.allow, "deny": record.tool_policy.deny}
    triggers = [t.model_dump() for t in record.triggers]
    graph = record.workflow_graph.model_dump() if record.workflow_graph else None
    return {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "base_agent_id": record.base_agent_id,
        "allow_subrun_delegation": record.allow_subrun_delegation,
        "execution_mode": record.execution_mode,
        "workflow_graph": graph,
        "tool_policy": tp,
        "triggers": triggers,
        "version": record.version,
        "steps": steps,
        "step_count": len(steps),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _find_idempotent_workflow_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="workflow",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different workflow payload.",
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {"key": key, "reused": True},
        },
    )


def _register_idempotent_workflow(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="workflow",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
    )


def _find_idempotent_workflow_execute_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="workflow_execute",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different workflow execute payload.",
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {"key": key, "reused": True},
        },
    )


def _register_idempotent_workflow_execute(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="workflow_execute",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
    )


def _find_idempotent_workflow_delete_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="workflow_delete",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different workflow delete payload.",
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {"key": key, "reused": True},
        },
    )


def _register_idempotent_workflow_delete(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    deps = _require_deps()
    deps.idempotency_mgr.register(
        namespace="workflow_delete",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
    )


# ---------------------------------------------------------------------------
# Graph construction helpers
# ---------------------------------------------------------------------------

def _build_workflow_graph_from_steps(steps: list[str], base_agent_id: str = "head-agent") -> WorkflowGraphDef | None:
    """Build a linear WorkflowGraphDef from a flat step list (backward compat)."""
    if not steps:
        return None
    graph_steps: list[WorkflowStepDef] = []
    for i, instruction in enumerate(steps):
        step_id = f"step-{i + 1}"
        next_id = f"step-{i + 2}" if i + 1 < len(steps) else None
        graph_steps.append(WorkflowStepDef(
            id=step_id,
            type="agent",
            label=f"Step {i + 1}",
            instruction=instruction,
            next_step=next_id,
            agent_id=base_agent_id or "head-agent",
        ))
    return WorkflowGraphDef(steps=graph_steps, entry_step_id="step-1")


def _parse_tool_policy(raw: Any) -> WorkflowToolPolicy | None:
    """Parse a tool_policy dict into WorkflowToolPolicy."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        allow = [s.strip() for s in (raw.get("allow") or []) if isinstance(s, str) and s.strip()]
        deny = [s.strip() for s in (raw.get("deny") or []) if isinstance(s, str) and s.strip()]
        if allow or deny:
            return WorkflowToolPolicy(allow=allow, deny=deny)
    return None


def _parse_triggers(raw: Any) -> list[WorkflowTrigger]:
    """Parse raw triggers into WorkflowTrigger list."""
    if not raw:
        return []
    result = []
    for t in raw:
        if isinstance(t, dict):
            result.append(WorkflowTrigger.model_validate(t))
        elif hasattr(t, "model_dump"):
            result.append(t)
        else:
            result.append(WorkflowTrigger.model_validate(vars(t)))
    return result


def _normalize_tool_policy_payload(raw: Any) -> dict | None:
    """Normalize a tool_policy payload (same logic as tools_handlers had)."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return {
            "allow": [s.strip() for s in (raw.get("allow") or []) if isinstance(s, str) and s.strip()],
            "deny": [s.strip() for s in (raw.get("deny") or []) if isinstance(s, str) and s.strip()],
        }
    return None


# ---------------------------------------------------------------------------
# List / Get / Create / Update / Delete handlers
# ---------------------------------------------------------------------------

def _list_workflows_minimal(*, limit: int, base_agent_id: str | None = None) -> dict:
    deps = _require_deps()
    normalized_base_agent = _normalize_workflow_id(base_agent_id) if base_agent_id else None
    items: list[dict] = []

    for record in deps.workflow_store.list(limit=max(1, limit) * 2):
        if normalized_base_agent and record.base_agent_id != normalized_base_agent:
            continue
        items.append(_record_to_response(record))
        if len(items) >= max(1, limit):
            break

    return {
        "schema": "workflows.list.v1",
        "count": len(items),
        "items": items,
    }


def _get_workflow_minimal(*, workflow_id: str) -> dict:
    record = _find_workflow_or_404(workflow_id)
    return {
        "schema": "workflows.get.v1",
        "workflow": _record_to_response(record),
    }


def _create_workflow_minimal(*, request: ControlWorkflowsCreateRequest) -> dict:
    deps = _require_deps()

    base_agent_id = _normalize_workflow_id(request.base_agent_id) if request.base_agent_id else "head-agent"
    if not base_agent_id:
        base_agent_id = "head-agent"

    steps = [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]
    raw_id = (request.id or "").strip()
    name = (request.name or "").strip()
    description = (request.description or "").strip()
    if not name:
        raise GuardrailViolation("Workflow name must not be empty.")

    fingerprint_id = _normalize_workflow_id(raw_id) if raw_id else None

    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)
    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_create_fingerprint(
        operation="create",
        workflow_id=fingerprint_id,
        name=name,
        description=description,
        base_agent_id=base_agent_id,
        steps=steps,
        tool_policy=normalized_tool_policy,
        allow_subrun_delegation=bool(request.allow_subrun_delegation),
    )
    existing = _find_idempotent_workflow_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    if raw_id:
        workflow_id = _normalize_workflow_id(raw_id)
    else:
        workflow_id = _normalize_workflow_id(f"workflow-{name}-{str(uuid.uuid4())[:8]}")

    execution_mode = (getattr(request, "execution_mode", None) or "parallel").strip().lower()
    if execution_mode not in ("parallel", "sequential"):
        execution_mode = "parallel"

    raw_graph = getattr(request, "workflow_graph", None)
    workflow_graph = None
    if raw_graph is not None:
        try:
            workflow_graph = WorkflowGraphDef.model_validate(raw_graph) if isinstance(raw_graph, dict) else raw_graph
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid workflow_graph definition")
    elif steps:
        workflow_graph = _build_workflow_graph_from_steps(steps, base_agent_id=base_agent_id)

    triggers = _parse_triggers(getattr(request, "triggers", None))
    tool_policy = _parse_tool_policy(normalized_tool_policy)

    record = WorkflowRecord(
        id=workflow_id,
        name=name,
        description=description,
        base_agent_id=base_agent_id,
        execution_mode=execution_mode,
        workflow_graph=workflow_graph,
        tool_policy=tool_policy,
        triggers=triggers,
        allow_subrun_delegation=bool(request.allow_subrun_delegation),
    )
    created = deps.workflow_store.create(record)

    response = {
        "schema": "workflows.create.v1",
        "status": "created",
        "workflow": _record_to_response(created),
        "idempotency": {"key": idempotency_key, "reused": False},
    }
    _register_idempotent_workflow(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def _update_workflow_minimal(*, request: ControlWorkflowsUpdateRequest) -> dict:
    deps = _require_deps()

    workflow_id = (request.id or "").strip().lower()
    if not workflow_id:
        raise GuardrailViolation("Workflow id must not be empty.")

    existing = deps.workflow_store.get(workflow_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    resolved_name = (request.name or existing.name or "").strip()
    if not resolved_name:
        raise GuardrailViolation("Workflow name must not be empty.")

    resolved_description = existing.description if request.description is None else (request.description or "").strip()
    resolved_base_agent = existing.base_agent_id if request.base_agent_id is None else (_normalize_workflow_id(request.base_agent_id) or "head-agent")

    resolved_execution_mode = existing.execution_mode if getattr(request, "execution_mode", None) is None else (request.execution_mode or "parallel").strip().lower()
    if resolved_execution_mode not in ("parallel", "sequential"):
        resolved_execution_mode = "parallel"

    raw_request_graph = getattr(request, "workflow_graph", None)
    if raw_request_graph is not None:
        try:
            resolved_graph = WorkflowGraphDef.model_validate(raw_request_graph) if isinstance(raw_request_graph, dict) else raw_request_graph
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid workflow_graph definition")
    else:
        resolved_graph = existing.workflow_graph

    if raw_request_graph is None and request.steps is not None:
        resolved_steps = [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]
        if resolved_steps:
            resolved_graph = _build_workflow_graph_from_steps(resolved_steps, base_agent_id=resolved_base_agent)

    if request.tool_policy is None:
        resolved_tool_policy = existing.tool_policy
    else:
        resolved_tool_policy = _parse_tool_policy(_normalize_tool_policy_payload(request.tool_policy))

    resolved_allow_subrun_delegation = existing.allow_subrun_delegation if request.allow_subrun_delegation is None else bool(request.allow_subrun_delegation)

    raw_triggers = getattr(request, "triggers", None)
    resolved_triggers = existing.triggers if raw_triggers is None else _parse_triggers(raw_triggers)

    steps_for_fingerprint = _extract_flat_steps(existing) if request.steps is None else [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]
    tp_for_fingerprint = None
    if resolved_tool_policy is not None:
        tp_for_fingerprint = {"allow": resolved_tool_policy.allow, "deny": resolved_tool_policy.deny}
    triggers_for_fingerprint = [t.model_dump() for t in resolved_triggers]
    graph_for_fingerprint = resolved_graph.model_dump() if resolved_graph else None

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_create_fingerprint(
        operation="update",
        workflow_id=workflow_id,
        name=resolved_name,
        description=resolved_description,
        base_agent_id=resolved_base_agent,
        steps=steps_for_fingerprint,
        tool_policy=tp_for_fingerprint,
        allow_subrun_delegation=resolved_allow_subrun_delegation,
        execution_mode=resolved_execution_mode,
        workflow_graph=graph_for_fingerprint,
        triggers=triggers_for_fingerprint,
    )
    existing_response = _find_idempotent_workflow_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing_response is not None:
        return existing_response

    updated_record = WorkflowRecord(
        id=workflow_id,
        name=resolved_name,
        description=resolved_description,
        base_agent_id=resolved_base_agent,
        execution_mode=resolved_execution_mode,
        workflow_graph=resolved_graph,
        tool_policy=resolved_tool_policy,
        triggers=resolved_triggers,
        allow_subrun_delegation=resolved_allow_subrun_delegation,
    )
    updated = deps.workflow_store.update(workflow_id, updated_record)

    response = {
        "schema": "workflows.update.v1",
        "status": "updated",
        "workflow": _record_to_response(updated),
        "idempotency": {"key": idempotency_key, "reused": False},
    }
    _register_idempotent_workflow(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

async def _execute_workflow_sequential(
    *,
    request: ControlWorkflowsExecuteRequest,
    record: WorkflowRecord,
    workflow_agent_id: str,
    session_id: str,
    run_id: str,
    graph: WorkflowGraphDef,
    execution_mode: str,
    deps: WorkflowDependencies,
    idempotency_key: str | None,
    fingerprint: str,
    pre_state: Any,
) -> dict:
    """Execute a workflow with sequential step-by-step processing."""
    from app.workflows.engine import WorkflowEngine

    # Get connector services if available
    connector_store = None
    credential_store = None
    connector_registry = None
    try:
        from app.connectors.connector_store import get_connector_store
        from app.connectors.credential_store import get_credential_store
        from app.connectors.registry import ConnectorRegistry
        connector_store = get_connector_store()
        credential_store = get_credential_store()
        connector_registry = ConnectorRegistry()
    except (ImportError, RuntimeError):
        pass

    engine = WorkflowEngine(
        run_agent=deps.run_agent,
        connector_store=connector_store,
        credential_store=credential_store,
        connector_registry=connector_registry,
        audit_store=deps.audit_store,
    )

    # Try to use the run store for persistence + SSE broadcasting
    try:
        from app.workflows.store import get_workflow_run_store
        run_store = get_workflow_run_store()
    except Exception:
        run_store = None

    if run_store is not None:
        send_event_fn, state_holder = run_store.make_send_event(run_id)
        state_holder[0] = pre_state
    else:
        async def send_event_fn(_event: dict) -> None:
            return None

    try:
        execution_state = await engine.execute(
            graph=graph,
            run_id=run_id,
            session_id=session_id,
            initial_message=request.message,
            workflow_id=workflow_agent_id,
            send_event=send_event_fn,
            mode=execution_mode,
            existing_state=pre_state,
        )
    except Exception:
        pre_state.status = "failed"
        if run_store is not None:
            run_store.save(pre_state)
        raise

    if run_store is not None:
        run_store.save(execution_state)

    step_summaries = []
    for step_id, result in execution_state.step_results.items():
        step_summaries.append({
            "step_id": step_id,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "output_preview": str(result.output)[:200] if result.output is not None else "",
        })

    response = {
        "schema": "workflows.execute.v2",
        "status": "completed" if execution_state.status == "completed" else "failed",
        "runId": run_id,
        "sessionId": session_id,
        "workflow": {
            "id": workflow_agent_id,
            "name": record.name,
            "base_agent_id": record.base_agent_id,
            "execution_mode": execution_mode,
            "version": record.version,
        },
        "execution": {
            "engine": f"workflow.{execution_mode}.v1",
            "mode": f"{execution_mode}_pipeline",
            "status": execution_state.status,
            "steps": step_summaries,
            "started_at": execution_state.started_at,
            "completed_at": execution_state.completed_at,
        },
        "idempotency": {"key": idempotency_key, "reused": False},
    }
    _register_idempotent_workflow_execute(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


async def _execute_workflow_minimal(*, request: ControlWorkflowsExecuteRequest) -> dict:
    deps = _require_deps()

    record = _find_workflow_or_404(request.workflow_id)
    workflow_agent_id = _normalize_workflow_id(record.id)

    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_execute_fingerprint(
        workflow_id=workflow_agent_id,
        message=request.message,
        session_id=request.session_id,
        model=request.model,
        preset=request.preset,
        queue_mode=getattr(request, "queue_mode", None),
        prompt_mode=getattr(request, "prompt_mode", None),
        tool_policy=normalized_tool_policy,
        allow_subrun_delegation=record.allow_subrun_delegation,
        runtime="api",
    )
    existing = _find_idempotent_workflow_execute_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    session_id = request.session_id or str(uuid.uuid4())

    if record.workflow_graph is None:
        raise HTTPException(status_code=400, detail="Workflow must have a workflow_graph. Flat-step-only workflows are no longer supported.")

    graph = record.workflow_graph
    run_id = str(uuid.uuid4())

    # Pre-create execution state so the SSE stream has something to connect to
    from app.workflows.models import WorkflowExecutionState
    _pre_state = WorkflowExecutionState(
        workflow_id=workflow_agent_id,
        run_id=run_id,
        session_id=session_id,
        output_dir=str(Path("workflow_outputs") / run_id),
    )
    try:
        from app.workflows.store import get_workflow_run_store
        run_store = get_workflow_run_store()
        run_store.save(_pre_state)
    except Exception:
        pass

    task = asyncio.create_task(
        _execute_workflow_sequential(
            request=request,
            record=record,
            workflow_agent_id=workflow_agent_id,
            session_id=session_id,
            run_id=run_id,
            graph=graph,
            execution_mode=record.execution_mode,
            deps=deps,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            pre_state=_pre_state,
        ),
        name=f"workflow-{run_id}",
    )

    def _on_task_done(t: asyncio.Task) -> None:
        exc = t.exception() if not t.cancelled() else None
        if exc is not None:
            logger.error("workflow_task_failed run_id=%s error=%s", run_id, exc)

    task.add_done_callback(_on_task_done)

    response = {
        "schema": "workflows.execute.v2",
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
        "workflow": {
            "id": workflow_agent_id,
            "name": record.name,
            "base_agent_id": record.base_agent_id,
            "execution_mode": record.execution_mode,
            "version": record.version,
        },
        "idempotency": {"key": idempotency_key, "reused": False},
    }
    _register_idempotent_workflow_execute(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def _delete_workflow_minimal(*, request: ControlWorkflowsDeleteRequest) -> dict:
    deps = _require_deps()
    workflow_id = _normalize_workflow_id(request.workflow_id)
    if not workflow_id:
        raise GuardrailViolation("Workflow id must not be empty.")

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_delete_fingerprint(workflow_id=workflow_id)
    existing = _find_idempotent_workflow_delete_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    record = _find_workflow_or_404(workflow_id)

    deleted = deps.workflow_store.delete(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if deps.audit_store is not None:
        deps.audit_store.cleanup(workflow_id)

    response = {
        "schema": "workflows.delete.v1",
        "status": "deleted",
        "workflow": {"id": workflow_id, "name": record.name},
        "idempotency": {"key": idempotency_key, "reused": False},
    }
    _register_idempotent_workflow_delete(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


# ---------------------------------------------------------------------------
# Public API handlers (same signature as before)
# ---------------------------------------------------------------------------

def api_control_workflows_list(request_data: dict) -> dict:
    request = ControlWorkflowsListRequest.model_validate(request_data)
    limit = max(1, min(int(request.limit), 500))
    return _list_workflows_minimal(limit=limit, base_agent_id=request.base_agent_id)


def api_control_workflows_get(request_data: dict) -> dict:
    request = ControlWorkflowsGetRequest.model_validate(request_data)
    return _get_workflow_minimal(workflow_id=request.workflow_id)


def api_control_workflows_create(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsCreateRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return _create_workflow_minimal(request=payload)


def api_control_workflows_update(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsUpdateRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return _update_workflow_minimal(request=payload)


async def api_control_workflows_execute(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsExecuteRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return await _execute_workflow_minimal(request=payload)


def api_control_workflows_delete(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsDeleteRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return _delete_workflow_minimal(request=payload)


def api_control_workflows_run_audit(run_id: str) -> dict:
    """Return the audit trail for a workflow run."""
    deps = _require_deps()
    if deps.audit_store is None:
        raise HTTPException(status_code=400, detail="Audit store not configured")
    entries = deps.audit_store.get_run_audit(run_id)
    return {"schema": "workflows.run_audit.v1", "runId": run_id, "entries": entries}
