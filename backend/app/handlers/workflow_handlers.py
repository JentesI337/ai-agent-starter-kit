from __future__ import annotations

import uuid
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import HTTPException

from app.custom_agents import CustomAgentCreateRequest, CustomAgentDefinition
from app.errors import GuardrailViolation
from app.control_models import (
    ControlWorkflowsCreateRequest,
    ControlWorkflowsDeleteRequest,
    ControlWorkflowsExecuteRequest,
    ControlWorkflowsGetRequest,
    ControlWorkflowsListRequest,
    ControlWorkflowsUpdateRequest,
)
from app.handlers.tools_handlers import normalize_tool_policy_payload
from app.services.request_normalization import normalize_idempotency_key


@dataclass
class WorkflowHandlerDependencies:
    settings: Any
    custom_agent_store: Any
    agent_registry: MutableMapping[str, Any]
    idempotency_mgr: Any
    runtime_manager: Any
    subrun_lane: Any
    workflow_version_registry: dict[str, int]
    workflow_version_lock: Lock
    normalize_agent_id: Callable[[str | None], str]
    resolve_agent: Callable[[str | None], tuple[str, Any, Any]]
    sync_custom_agents: Callable[[], None]
    effective_orchestrator_agent_ids: Callable[[], set[str]]
    start_run_background: Callable[..., str]
    build_workflow_create_fingerprint: Callable[..., str]
    build_workflow_execute_fingerprint: Callable[..., str]
    build_workflow_delete_fingerprint: Callable[..., str]


_deps: WorkflowHandlerDependencies | None = None


def configure(deps: WorkflowHandlerDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> WorkflowHandlerDependencies:
    if _deps is None:
        raise RuntimeError("workflow_handlers is not configured")
    return _deps


def _get_workflow_version(workflow_id: str) -> int:
    deps = _require_deps()
    normalized = deps.normalize_agent_id(workflow_id)
    with deps.workflow_version_lock:
        return int(deps.workflow_version_registry.get(normalized, 1))


def _set_workflow_version(workflow_id: str, version: int) -> None:
    deps = _require_deps()
    normalized = deps.normalize_agent_id(workflow_id)
    with deps.workflow_version_lock:
        deps.workflow_version_registry[normalized] = max(1, int(version))


def _increment_workflow_version(workflow_id: str) -> int:
    deps = _require_deps()
    normalized = deps.normalize_agent_id(workflow_id)
    with deps.workflow_version_lock:
        current = int(deps.workflow_version_registry.get(normalized, 1))
        next_version = current + 1
        deps.workflow_version_registry[normalized] = next_version
        return next_version


def _delete_workflow_version(workflow_id: str) -> None:
    deps = _require_deps()
    normalized = deps.normalize_agent_id(workflow_id)
    with deps.workflow_version_lock:
        deps.workflow_version_registry.pop(normalized, None)


def _find_workflow_or_404(workflow_id: str) -> CustomAgentDefinition:
    deps = _require_deps()
    target = deps.normalize_agent_id(workflow_id)
    match = next((item for item in deps.custom_agent_store.list() if deps.normalize_agent_id(item.id) == target), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return match


def _find_idempotent_workflow_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    deps = _require_deps()
    return deps.idempotency_mgr.lookup_or_raise(
        namespace="workflow",
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        conflict_message="Idempotency key replayed with a different workflow payload.",
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
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
            "idempotency": {
                "key": key,
                "reused": True,
            },
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
            "idempotency": {
                "key": key,
                "reused": True,
            },
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


def _list_workflows_minimal(*, limit: int, base_agent_id: str | None = None) -> dict:
    deps = _require_deps()
    normalized_base_agent = deps.normalize_agent_id(base_agent_id) if base_agent_id else None
    items: list[dict] = []

    for definition in deps.custom_agent_store.list():
        base_id = deps.normalize_agent_id(definition.base_agent_id)
        if normalized_base_agent and base_id != normalized_base_agent:
            continue

        steps = [step for step in (definition.workflow_steps or []) if isinstance(step, str) and step.strip()]
        items.append(
            {
                "id": definition.id,
                "name": definition.name,
                "base_agent_id": base_id,
                "allow_subrun_delegation": bool(getattr(definition, "allow_subrun_delegation", False)),
                "version": _get_workflow_version(definition.id),
                "steps": steps,
                "step_count": len(steps),
            }
        )
        if len(items) >= max(1, limit):
            break

    return {
        "schema": "workflows.list.v1",
        "count": len(items),
        "items": items,
    }


def _get_workflow_minimal(*, workflow_id: str) -> dict:
    deps = _require_deps()
    definition = _find_workflow_or_404(workflow_id)
    steps = [step for step in (definition.workflow_steps or []) if isinstance(step, str) and step.strip()]
    return {
        "schema": "workflows.get.v1",
        "workflow": {
            "id": definition.id,
            "name": definition.name,
            "description": definition.description,
            "base_agent_id": deps.normalize_agent_id(definition.base_agent_id),
            "allow_subrun_delegation": bool(getattr(definition, "allow_subrun_delegation", False)),
            "version": _get_workflow_version(definition.id),
            "steps": steps,
            "step_count": len(steps),
            "tool_policy": definition.tool_policy,
        },
    }


def _create_workflow_minimal(*, request: ControlWorkflowsCreateRequest) -> dict:
    deps = _require_deps()
    deps.sync_custom_agents()

    normalized_base_agent = deps.normalize_agent_id(request.base_agent_id)
    if normalized_base_agent not in deps.agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    steps = [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]
    workflow_id = (request.id or "").strip() or None
    name = (request.name or "").strip()
    description = (request.description or "").strip()
    if not name:
        raise GuardrailViolation("Workflow name must not be empty.")

    normalized_tool_policy = normalize_tool_policy_payload(request.tool_policy)
    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_create_fingerprint(
        operation="create",
        workflow_id=workflow_id,
        name=name,
        description=description,
        base_agent_id=normalized_base_agent,
        steps=steps,
        tool_policy=normalized_tool_policy,
        allow_subrun_delegation=bool(request.allow_subrun_delegation),
    )
    existing = _find_idempotent_workflow_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    created = deps.custom_agent_store.upsert(
        CustomAgentCreateRequest(
            id=workflow_id,
            name=name,
            description=description,
            base_agent_id=normalized_base_agent,
            workflow_steps=steps,
            tool_policy=normalized_tool_policy,
            allow_subrun_delegation=bool(request.allow_subrun_delegation),
        ),
        id_factory=lambda base_name: f"workflow-{base_name}-{str(uuid.uuid4())[:8]}",
    )
    deps.sync_custom_agents()
    _set_workflow_version(created.id, 1)

    response = {
        "schema": "workflows.create.v1",
        "status": "created",
        "workflow": {
            "id": created.id,
            "name": created.name,
            "description": created.description,
            "base_agent_id": deps.normalize_agent_id(created.base_agent_id),
            "allow_subrun_delegation": bool(getattr(created, "allow_subrun_delegation", False)),
            "version": _get_workflow_version(created.id),
            "steps": list(created.workflow_steps or []),
            "step_count": len(created.workflow_steps or []),
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_workflow(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def _update_workflow_minimal(*, request: ControlWorkflowsUpdateRequest) -> dict:
    deps = _require_deps()
    deps.sync_custom_agents()

    workflow_id = (request.id or "").strip().lower()
    if not workflow_id:
        raise GuardrailViolation("Workflow id must not be empty.")

    existing = next((item for item in deps.custom_agent_store.list() if item.id == workflow_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    resolved_name = (request.name or existing.name or "").strip()
    if not resolved_name:
        raise GuardrailViolation("Workflow name must not be empty.")

    resolved_description = existing.description if request.description is None else (request.description or "").strip()
    normalized_base_agent = deps.normalize_agent_id(existing.base_agent_id) if request.base_agent_id is None else deps.normalize_agent_id(request.base_agent_id)
    if normalized_base_agent not in deps.agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    if request.steps is None:
        resolved_steps = [step for step in (existing.workflow_steps or []) if isinstance(step, str) and step.strip()]
    else:
        resolved_steps = [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]

    resolved_tool_policy = existing.tool_policy if request.tool_policy is None else normalize_tool_policy_payload(request.tool_policy)
    resolved_allow_subrun_delegation = bool(getattr(existing, "allow_subrun_delegation", False)) if request.allow_subrun_delegation is None else bool(request.allow_subrun_delegation)

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_create_fingerprint(
        operation="update",
        workflow_id=workflow_id,
        name=resolved_name,
        description=resolved_description,
        base_agent_id=normalized_base_agent,
        steps=resolved_steps,
        tool_policy=resolved_tool_policy,
        allow_subrun_delegation=resolved_allow_subrun_delegation,
    )
    existing_response = _find_idempotent_workflow_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing_response is not None:
        return existing_response

    updated = deps.custom_agent_store.upsert(
        CustomAgentCreateRequest(
            id=workflow_id,
            name=resolved_name,
            description=resolved_description,
            base_agent_id=normalized_base_agent,
            workflow_steps=resolved_steps,
            tool_policy=resolved_tool_policy,
            allow_subrun_delegation=resolved_allow_subrun_delegation,
        )
    )
    deps.sync_custom_agents()
    next_version = _increment_workflow_version(updated.id)

    response = {
        "schema": "workflows.update.v1",
        "status": "updated",
        "workflow": {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "base_agent_id": deps.normalize_agent_id(updated.base_agent_id),
            "allow_subrun_delegation": bool(getattr(updated, "allow_subrun_delegation", False)),
            "version": next_version,
            "steps": list(updated.workflow_steps or []),
            "step_count": len(updated.workflow_steps or []),
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_workflow(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


async def _execute_workflow_minimal(*, request: ControlWorkflowsExecuteRequest) -> dict:
    deps = _require_deps()
    deps.sync_custom_agents()

    workflow = _find_workflow_or_404(request.workflow_id)
    workflow_agent_id = deps.normalize_agent_id(workflow.id)
    _, _, workflow_orchestrator = deps.resolve_agent(workflow_agent_id)

    normalized_tool_policy = normalize_tool_policy_payload(request.tool_policy)

    runtime_state = deps.runtime_manager.get_state()
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
        allow_subrun_delegation=bool(getattr(workflow, "allow_subrun_delegation", False)),
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_workflow_execute_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    session_id = request.session_id or str(uuid.uuid4())
    run_id = deps.start_run_background(
        agent_id=workflow_agent_id,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        queue_mode=getattr(request, "queue_mode", None),
        prompt_mode=getattr(request, "prompt_mode", None),
        tool_policy=normalized_tool_policy,
        meta={
            "workflow_execute": True,
            "workflow_id": workflow_agent_id,
            "workflow_version": _get_workflow_version(workflow_agent_id),
        },
    )

    steps = [step for step in (workflow.workflow_steps or []) if isinstance(step, str) and step.strip()]
    step_spawn_cap = max(1, int(deps.settings.subrun_max_children_per_parent))
    executable_steps = steps[:step_spawn_cap]
    spawned_subruns: list[dict] = []
    subrun_warnings: list[str] = []

    if len(steps) > len(executable_steps):
        subrun_warnings.append(
            f"workflow step cap reached ({step_spawn_cap}); skipped {len(steps) - len(executable_steps)} steps"
        )

    async def _noop_send_event(_event: dict) -> None:
        return None

    for index, step in enumerate(executable_steps, start=1):
        step_message = f"Workflow step {index}/{len(executable_steps)}: {step}\n\nParent message:\n{request.message}"
        try:
            subrun_id = await deps.subrun_lane.spawn(
                parent_request_id=run_id,
                parent_session_id=session_id,
                user_message=step_message,
                runtime=runtime_state.runtime,
                model=request.model or runtime_state.model,
                timeout_seconds=deps.settings.subrun_timeout_seconds,
                tool_policy=normalized_tool_policy,
                send_event=_noop_send_event,
                agent_id=workflow_agent_id,
                mode="run",
                preset=request.preset,
                orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
                orchestrator_api=workflow_orchestrator,
            )
            info = deps.subrun_lane.get_info(subrun_id) or {}
            allowed, decision = deps.subrun_lane.evaluate_visibility(
                subrun_id,
                requester_session_id=session_id,
                visibility_scope=deps.settings.session_visibility_default,
            )
            spawned_subruns.append(
                {
                    "index": index,
                    "name": step,
                    "run_id": subrun_id,
                    "child_session_id": info.get("child_session_id"),
                    "status": info.get("status"),
                    "a2a": {
                        "parent_session_id": session_id,
                        "allowed": allowed,
                        "visibility": decision,
                    },
                }
            )
        except Exception as exc:
            subrun_warnings.append(f"step[{index}] {step}: {exc}")

    graph_nodes = [{"id": run_id, "kind": "workflow_root"}] + [
        {
            "id": item.get("run_id"),
            "kind": "workflow_step_subrun",
            "index": item.get("index"),
            "name": item.get("name"),
        }
        for item in spawned_subruns
    ]
    graph_edges = [
        {
            "from": run_id,
            "to": item.get("run_id"),
            "type": "step_subrun",
            "index": item.get("index"),
        }
        for item in spawned_subruns
    ]

    response = {
        "schema": "workflows.execute.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
        "workflow": {
            "id": workflow_agent_id,
            "name": workflow.name,
            "base_agent_id": deps.normalize_agent_id(workflow.base_agent_id),
            "version": _get_workflow_version(workflow_agent_id),
            "steps": steps,
            "step_count": len(steps),
        },
        "execution": {
            "engine": "workflow.revision_flow.v1",
            "mode": "subrun_graph",
            "root_run_id": run_id,
            "visibility_scope": deps.settings.session_visibility_default,
            "a2a_policy": "parent_child_session_tree",
            "steps": spawned_subruns,
            "warnings": subrun_warnings,
            "budgets": {
                "step_spawn_cap": step_spawn_cap,
                "step_total": len(steps),
                "step_executed": len(executable_steps),
                "subrun_timeout_seconds": deps.settings.subrun_timeout_seconds,
            },
            "graph": {
                "nodes": graph_nodes,
                "edges": graph_edges,
            },
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_workflow_execute(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def _delete_workflow_minimal(*, request: ControlWorkflowsDeleteRequest) -> dict:
    deps = _require_deps()
    workflow_id = deps.normalize_agent_id(request.workflow_id)
    if not workflow_id:
        raise GuardrailViolation("Workflow id must not be empty.")

    idempotency_key = normalize_idempotency_key(request.idempotency_key)
    fingerprint = deps.build_workflow_delete_fingerprint(workflow_id=workflow_id)
    existing = _find_idempotent_workflow_delete_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    workflow = _find_workflow_or_404(workflow_id)

    deleted = deps.custom_agent_store.delete(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    _delete_workflow_version(workflow_id)
    deps.sync_custom_agents()

    response = {
        "schema": "workflows.delete.v1",
        "status": "deleted",
        "workflow": {
            "id": workflow_id,
            "name": workflow.name,
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_workflow_delete(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


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
