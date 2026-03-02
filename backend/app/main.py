from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from threading import Lock
from time import monotonic
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import MutableMapping
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.agents.head_agent_adapter import CoderAgentAdapter, HeadAgentAdapter, ReviewAgentAdapter
from app.app_setup import build_fastapi_app, build_lifespan_context
from app.app_state import LazyMappingProxy, LazyObjectProxy, LazyRuntimeRegistry, RuntimeComponents
from app.control_router_wiring import include_control_routers
from app.config import resolved_prompt_settings, settings
from app.contracts.agent_contract import AgentContract
from app.custom_agents import (
    CustomAgentAdapter,
    CustomAgentCreateRequest,
    CustomAgentDefinition,
    CustomAgentStore,
)
from app.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError
from app.interfaces import OrchestratorApi, RequestContext
from app.orchestrator.events import LifecycleStage, build_lifecycle_event, classify_error
from app.orchestrator.subrun_lane import SubrunLane
from app.run_endpoints import (
    AgentTestDependencies,
    RunEndpointsDependencies,
    run_agent_test,
    start_run as run_endpoint_start,
    wait_run as run_endpoint_wait,
)
from app.routers import (
    build_agents_router,
    build_run_api_router,
    build_runtime_debug_router,
    build_subruns_router,
    build_ws_agent_router,
)
from app.routers.run_api import RunApiRouterHandlers
from app.runtime_debug_endpoints import (
    RuntimeDebugDependencies,
    api_resolved_prompt_settings,
    api_runtime_status,
    api_test_ping,
)
from app.runtime_manager import RuntimeManager
from app.skills.discovery import discover_skills
from app.skills.eligibility import filter_eligible_skills
from app.skills.snapshot import build_skill_snapshot
from app.startup_tasks import run_shutdown_sequence, run_startup_sequence
from app.subrun_endpoints import (
    SubrunEndpointsDependencies,
    api_subruns_get,
    api_subruns_kill,
    api_subruns_kill_all_async,
    api_subruns_list,
    api_subruns_log,
)
from app.services import (
    PRESET_TOOL_POLICIES,
    PolicyApprovalService,
    TOOL_POLICY_BY_MODEL,
    TOOL_POLICY_BY_PROVIDER,
    TOOL_POLICY_RESOLUTION_ORDER,
    TOOL_PROFILES,
    SessionQueryService,
    build_run_start_fingerprint as _build_run_start_fingerprint,
    build_session_patch_fingerprint as _build_session_patch_fingerprint,
    build_session_reset_fingerprint as _build_session_reset_fingerprint,
    build_workflow_create_fingerprint as _build_workflow_create_fingerprint,
    build_workflow_delete_fingerprint as _build_workflow_delete_fingerprint,
    build_workflow_execute_fingerprint as _build_workflow_execute_fingerprint,
    idempotency_lookup_or_raise,
    idempotency_register,
    merge_tool_policy,
    normalize_policy_values,
    policy_payload,
    resolve_tool_policy,
)
from app.state import SqliteStateStore, StateStore
from app.tool_policy import ToolPolicyDict, ToolPolicyPayload, tool_policy_to_dict
from app.ws_handler import WsHandlerDependencies

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app.main")

app = build_fastapi_app(title="AI Agent Starter Kit", settings=settings)

PRIMARY_AGENT_ID = "head-agent"
CODER_AGENT_ID = "coder-agent"
REVIEW_AGENT_ID = "review-agent"
LEGACY_AGENT_ALIASES = {"head-coder": PRIMARY_AGENT_ID}


def _startup_sequence() -> None:
    run_startup_sequence(
        settings=settings,
        logger=logger,
        ensure_runtime_components_initialized=_ensure_runtime_components_initialized,
    )


def _shutdown_sequence() -> None:
    run_shutdown_sequence(active_run_tasks=active_run_tasks, logger=logger)


app.router.lifespan_context = build_lifespan_context(
    on_startup=_startup_sequence,
    on_shutdown=_shutdown_sequence,
)

def _build_runtime_components() -> RuntimeComponents:
    base_agent_registry: dict[str, AgentContract] = {
        PRIMARY_AGENT_ID: HeadAgentAdapter(),
        CODER_AGENT_ID: CoderAgentAdapter(),
        REVIEW_AGENT_ID: ReviewAgentAdapter(),
    }
    runtime = RuntimeManager()
    if settings.orchestrator_state_backend == "sqlite":
        store = SqliteStateStore(persist_dir=settings.orchestrator_state_dir)
    else:
        store = StateStore(persist_dir=settings.orchestrator_state_dir)
    query_service = SessionQueryService(state_store=store)
    policy_approval_service = PolicyApprovalService()
    orchestrators: dict[str, OrchestratorApi] = {
        agent_id: OrchestratorApi(agent=agent_instance, state_store=store)
        for agent_id, agent_instance in base_agent_registry.items()
    }
    custom_store = CustomAgentStore(persist_dir=settings.custom_agents_dir)
    return RuntimeComponents(
        agent_registry=base_agent_registry,
        runtime_manager=runtime,
        state_store=store,
        session_query_service=query_service,
        policy_approval_service=policy_approval_service,
        orchestrator_registry=orchestrators,
        custom_agent_store=custom_store,
    )


def _initialize_runtime_components(components: RuntimeComponents) -> None:
    _sync_custom_agents(components)
    components.agent = components.agent_registry[PRIMARY_AGENT_ID]
    components.orchestrator_api = components.orchestrator_registry[PRIMARY_AGENT_ID]
    components.subrun_lane = SubrunLane(
        orchestrator_api=components.orchestrator_api,
        state_store=components.state_store,
        max_concurrent=settings.subrun_max_concurrent,
        max_spawn_depth=settings.subrun_max_spawn_depth,
        max_children_per_parent=settings.subrun_max_children_per_parent,
        announce_retry_max_attempts=settings.subrun_announce_retry_max_attempts,
        announce_retry_base_delay_ms=settings.subrun_announce_retry_base_delay_ms,
        announce_retry_max_delay_ms=settings.subrun_announce_retry_max_delay_ms,
        announce_retry_jitter=settings.subrun_announce_retry_jitter,
        leaf_spawn_depth_guard_enabled=settings.subrun_leaf_spawn_depth_guard_enabled,
        orchestrator_agent_ids=list(_effective_orchestrator_agent_ids(components)),
        restore_orphan_reconcile_enabled=settings.subrun_restore_orphan_reconcile_enabled,
        restore_orphan_grace_seconds=settings.subrun_restore_orphan_grace_seconds,
        lifecycle_delivery_error_grace_enabled=settings.subrun_lifecycle_delivery_error_grace_enabled,
    )

    async def _spawn_subrun_from_agent(
        *,
        parent_request_id: str,
        parent_session_id: str,
        user_message: str,
        model: str | None,
        timeout_seconds: int,
        tool_policy: ToolPolicyDict | None,
        send_event,
        agent_id: str,
        mode: str,
    ) -> str:
        _sync_custom_agents(components)

        runtime_state = components.runtime_manager.get_state()
        selected_model = (model or "").strip() or runtime_state.model
        if runtime_state.runtime == "local":
            selected_model = await components.runtime_manager.ensure_model_ready(
                send_event,
                parent_session_id,
                selected_model,
            )
        else:
            selected_model = await components.runtime_manager.resolve_api_request_model(selected_model)

        normalized_agent_id = _normalize_agent_id(agent_id)
        selected_orchestrator = components.orchestrator_registry.get(normalized_agent_id)
        if selected_orchestrator is None:
            raise GuardrailViolation(f"Unsupported subrun agent: {agent_id}")

        effective_timeout = max(0, int(timeout_seconds))
        if effective_timeout == 0:
            effective_timeout = int(settings.subrun_timeout_seconds)

        return await components.subrun_lane.spawn(
            parent_request_id=parent_request_id,
            parent_session_id=parent_session_id,
            user_message=user_message,
            runtime=runtime_state.runtime,
            model=selected_model,
            timeout_seconds=effective_timeout,
            tool_policy=tool_policy,
            preset=None,
            send_event=send_event,
            agent_id=normalized_agent_id,
            mode=mode,
            orchestrator_agent_ids=sorted(_effective_orchestrator_agent_ids(components)),
            orchestrator_api=selected_orchestrator,
        )

    async def _request_policy_override_from_agent(
        *,
        send_event,
        session_id: str,
        request_id: str,
        agent_name: str,
        tool: str,
        resource: str,
        display_text: str,
    ) -> bool:
        if await components.policy_approval_service.is_preapproved(
            tool=tool,
            resource=resource,
            session_id=session_id,
        ):
            return True

        approval = await components.policy_approval_service.create(
            run_id=request_id,
            session_id=session_id,
            agent_name=agent_name,
            tool=tool,
            resource=resource,
            display_text=display_text,
        )

        await send_event(
            {
                "type": "policy_approval_required",
                "agent": agent_name,
                "request_id": request_id,
                "session_id": session_id,
                "approval": {
                    "approval_id": approval["approval_id"],
                    "tool": tool,
                    "resource": resource,
                    "display_text": display_text,
                    "options": ["allow_once", "allow_always", "deny"],
                    "scope": "tool_resource",
                    "status": "pending",
                },
            }
        )

        decision = await components.policy_approval_service.wait_for_decision(
            approval_id=approval["approval_id"],
            timeout_seconds=settings.policy_approval_wait_seconds,
        )
        return decision in {"allow_once", "allow_always"}

    for agent_instance in components.agent_registry.values():
        set_handler = getattr(agent_instance, "set_spawn_subrun_handler", None)
        if callable(set_handler):
            set_handler(_spawn_subrun_from_agent)
        set_policy_handler = getattr(agent_instance, "set_policy_approval_handler", None)
        if callable(set_policy_handler):
            set_policy_handler(_request_policy_override_from_agent)


_runtime_registry = LazyRuntimeRegistry(
    builder=_build_runtime_components,
    initializer=_initialize_runtime_components,
)


def _get_runtime_components() -> RuntimeComponents:
    return _runtime_registry.get_components()


def _ensure_runtime_components_initialized() -> RuntimeComponents:
    return _runtime_registry.ensure_initialized()


agent_registry: MutableMapping[str, AgentContract] = LazyMappingProxy(
    lambda: _get_runtime_components().agent_registry
)
runtime_manager = LazyObjectProxy(lambda: _get_runtime_components().runtime_manager)
state_store = LazyObjectProxy(lambda: _get_runtime_components().state_store)
session_query_service = LazyObjectProxy(lambda: _get_runtime_components().session_query_service)
policy_approval_service = LazyObjectProxy(lambda: _get_runtime_components().policy_approval_service)
orchestrator_registry: MutableMapping[str, OrchestratorApi] = LazyMappingProxy(
    lambda: _get_runtime_components().orchestrator_registry
)
custom_agent_store = LazyObjectProxy(lambda: _get_runtime_components().custom_agent_store)
agent = LazyObjectProxy(lambda: _get_runtime_components().agent)
orchestrator_api = LazyObjectProxy(lambda: _get_runtime_components().orchestrator_api)
subrun_lane = LazyObjectProxy(lambda: _get_runtime_components().subrun_lane)


def _sync_custom_agents(components: RuntimeComponents | None = None) -> None:
    if components is None:
        components = _get_runtime_components()

    for custom_id in list(components.custom_agent_ids):
        components.agent_registry.pop(custom_id, None)
        components.orchestrator_registry.pop(custom_id, None)

    components.custom_agent_ids = set()
    components.custom_orchestrator_agent_ids = set()

    definitions = components.custom_agent_store.list()
    for definition in definitions:
        custom_id = LEGACY_AGENT_ALIASES.get((definition.id or "").strip().lower(), (definition.id or "").strip().lower())
        if not custom_id or custom_id in {PRIMARY_AGENT_ID, CODER_AGENT_ID, REVIEW_AGENT_ID}:
            continue

        base_id = LEGACY_AGENT_ALIASES.get(
            (definition.base_agent_id or "").strip().lower(),
            (definition.base_agent_id or "").strip().lower(),
        )
        base_agent = components.agent_registry.get(base_id)
        if base_agent is None:
            continue

        adapter = CustomAgentAdapter(definition=definition, base_agent=base_agent)
        components.agent_registry[custom_id] = adapter
        components.orchestrator_registry[custom_id] = OrchestratorApi(
            agent=adapter,
            state_store=components.state_store,
        )
        components.custom_agent_ids.add(custom_id)
        if bool(getattr(definition, "allow_subrun_delegation", False)):
            components.custom_orchestrator_agent_ids.add(custom_id)

    if components.subrun_lane is not None:
        components.subrun_lane._orchestrator_agent_ids = _effective_orchestrator_agent_ids(components)


def _effective_orchestrator_agent_ids(components: RuntimeComponents | None = None) -> set[str]:
    if components is None:
        components = _get_runtime_components()

    configured = {
        str(item).strip().lower()
        for item in (settings.subrun_orchestrator_agent_ids or [PRIMARY_AGENT_ID])
        if isinstance(item, str) and str(item).strip()
    }
    configured.add(PRIMARY_AGENT_ID)
    configured |= {
        str(item).strip().lower()
        for item in (components.custom_orchestrator_agent_ids or set())
        if isinstance(item, str) and str(item).strip()
    }
    return configured
active_run_tasks: dict[str, asyncio.Task] = {}
idempotency_registry: dict[str, dict] = {}
idempotency_lock = Lock()
workflow_idempotency_registry: dict[str, dict] = {}
workflow_idempotency_lock = Lock()
workflow_execute_idempotency_registry: dict[str, dict] = {}
workflow_execute_idempotency_lock = Lock()
workflow_delete_idempotency_registry: dict[str, dict] = {}
workflow_delete_idempotency_lock = Lock()
workflow_version_registry: dict[str, int] = {}
workflow_version_lock = Lock()
session_patch_idempotency_registry: dict[str, dict] = {}
session_patch_idempotency_lock = Lock()
session_reset_idempotency_registry: dict[str, dict] = {}
session_reset_idempotency_lock = Lock()


def _normalize_agent_id(agent_id: str | None) -> str:
    raw = (agent_id or PRIMARY_AGENT_ID).strip().lower()
    return LEGACY_AGENT_ALIASES.get(raw, raw)


def _resolve_agent(agent_id: str | None) -> tuple[str, AgentContract, OrchestratorApi]:
    _sync_custom_agents()
    normalized_agent_id = _normalize_agent_id(agent_id)
    selected_agent = agent_registry.get(normalized_agent_id)
    selected_orchestrator = orchestrator_registry.get(normalized_agent_id)
    if selected_agent is None or selected_orchestrator is None:
        raise ValueError(f"Unsupported agent: {agent_id}")
    return normalized_agent_id, selected_agent, selected_orchestrator


def _looks_like_coding_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    keyword_markers = (
        "code",
        "python",
        "javascript",
        "typescript",
        "java",
        "c++",
        "c#",
        "golang",
        "rust",
        "sql",
        "html",
        "css",
        "bug",
        "debug",
        "fix",
        "refactor",
        "implement",
        "function",
        "class",
        "api",
        "endpoint",
        "test",
        "pytest",
        "unit test",
        "write file",
        "apply patch",
    )
    if any(marker in text for marker in keyword_markers):
        return True

    return bool(re.search(r"\b(build|create|generate|update)\b.*\b(script|module|component|service|backend|frontend)\b", text))


def _looks_like_review_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    keyword_markers = (
        "review",
        "code review",
        "audit",
        "critique",
        "quality check",
        "security review",
        "find issues",
        "what is wrong",
        "smell",
    )
    return any(marker in text for marker in keyword_markers)


def _get_agent_tools(agent_contract: AgentContract) -> list[str]:
    delegate = getattr(agent_contract, "_delegate", None)
    if delegate is None:
        delegate = getattr(agent_contract, "_base_agent", None)
    if delegate is not None:
        nested_delegate = getattr(delegate, "_delegate", None)
        if nested_delegate is not None:
            delegate = nested_delegate
    registry = getattr(delegate, "tool_registry", None)
    if isinstance(registry, dict):
        return sorted(str(name) for name in registry.keys())
    return []


def _remove_active_task(run_id: str) -> None:
    active_run_tasks.pop(run_id, None)


def _normalize_contract_run_status(status: str | None) -> str | None:
    normalized = (status or "").strip().lower()
    if not normalized:
        return None
    if normalized == "failed":
        return "error"
    return normalized


def _is_terminal_run_status(status: str | None) -> bool:
    normalized = (status or "").strip().lower()
    return normalized in {"completed", "failed", "timed_out", "cancelled"}


def _build_wait_payload(run_id: str, run_state: dict, *, wait_status: str | None = None) -> dict:
    run_status_raw = run_state.get("status")
    run_status = _normalize_contract_run_status(run_status_raw)
    started_at = run_state.get("created_at")
    ended_at = run_state.get("updated_at") if _is_terminal_run_status(run_status_raw) else None

    if wait_status is None:
        if run_status_raw == "completed":
            wait_status = "ok"
        elif run_status_raw in {"failed", "timed_out", "cancelled"}:
            wait_status = "error"
        else:
            wait_status = "timeout"

    payload = {
        "status": wait_status,
        "runId": run_id,
        "runStatus": run_status,
        "run_status": run_status,
        "startedAt": started_at,
        "started_at": started_at,
        "endedAt": ended_at,
        "ended_at": ended_at,
        "error": run_state.get("error"),
    }

    if wait_status in {"ok", "error"}:
        payload["final"] = _extract_final_message(run_state)

    return payload


def _lifecycle_status_from_stage(stage: str) -> str | None:
    normalized = (stage or "").strip().lower()
    if not normalized:
        return None
    if normalized.endswith(("_received", "_accepted", "_requested")):
        return "accepted"
    if normalized.endswith(("_started", "_dispatched")):
        return "running"
    if normalized.endswith(("_completed", "_done")):
        return "completed"
    if normalized.endswith("_timeout") or "timeout" in normalized:
        return "timed_out"
    if normalized.endswith("_cancelled"):
        return "cancelled"
    if normalized.endswith(("_failed", "_rejected")):
        return "failed"
    return None


def _state_append_event_safe(run_id: str, event: dict) -> None:
    try:
        state_store.append_event(run_id=run_id, event=event)
    except Exception:
        logger.debug("state_append_event_failed run_id=%s", run_id, exc_info=True)


def _state_mark_failed_safe(run_id: str, error: str) -> None:
    try:
        state_store.mark_failed(run_id=run_id, error=error)
    except Exception:
        logger.debug("state_mark_failed_failed run_id=%s", run_id, exc_info=True)


def _state_mark_completed_safe(run_id: str) -> None:
    try:
        state_store.mark_completed(run_id=run_id)
    except Exception:
        logger.debug("state_mark_completed_failed run_id=%s", run_id, exc_info=True)


class AgentTestRequest(BaseModel):
    message: str = "hi"
    model: str | None = None
    preset: str | None = None
    tool_policy: ToolPolicyPayload | None = None


class RunStartRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None
    preset: str | None = None
    tool_policy: ToolPolicyPayload | None = None


class ControlRunStartRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None
    preset: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlRunWaitRequest(BaseModel):
    run_id: str
    timeout_ms: int | None = None
    poll_interval_ms: int | None = None


class ControlSessionsListRequest(BaseModel):
    limit: int = 100
    active_only: bool = False


class ControlSessionsResolveRequest(BaseModel):
    session_id: str
    active_only: bool = False


class ControlSessionsHistoryRequest(BaseModel):
    session_id: str
    limit: int = 50


class ControlSessionsSendRequest(BaseModel):
    session_id: str
    message: str
    model: str | None = None
    preset: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlSessionsSpawnRequest(BaseModel):
    parent_session_id: str
    message: str
    model: str | None = None
    preset: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlSessionsStatusRequest(BaseModel):
    session_id: str


class ControlSessionsGetRequest(BaseModel):
    session_id: str


class ControlSessionsPatchRequest(BaseModel):
    session_id: str
    meta: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ControlSessionsResetRequest(BaseModel):
    session_id: str
    idempotency_key: str | None = None


class ControlToolsCatalogRequest(BaseModel):
    agent_id: str | None = None


class ControlToolsProfileRequest(BaseModel):
    profile_id: str | None = None


class ControlToolsPolicyMatrixRequest(BaseModel):
    agent_id: str | None = None


class ControlSkillsListRequest(BaseModel):
    skills_dir: str | None = None
    max_discovered: int | None = None


class ControlSkillsPreviewRequest(BaseModel):
    skills_dir: str | None = None
    max_discovered: int | None = None
    max_prompt_chars: int | None = None


class ControlSkillsCheckRequest(BaseModel):
    skills_dir: str | None = None
    max_discovered: int | None = None


class ControlSkillsSyncRequest(BaseModel):
    source_skills_dir: str | None = None
    target_skills_dir: str | None = None
    max_discovered: int | None = None
    max_sync_items: int = 200
    apply: bool = False
    clean_target: bool = False
    confirm_clean_target: bool = False


class ControlWorkflowsListRequest(BaseModel):
    limit: int = 100
    base_agent_id: str | None = None


class ControlWorkflowsGetRequest(BaseModel):
    workflow_id: str


class ControlWorkflowsCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    base_agent_id: str = PRIMARY_AGENT_ID
    steps: list[str] = Field(default_factory=list)
    tool_policy: ToolPolicyPayload | None = None
    allow_subrun_delegation: bool = False
    idempotency_key: str | None = None


class ControlWorkflowsUpdateRequest(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    base_agent_id: str | None = None
    steps: list[str] | None = None
    tool_policy: ToolPolicyPayload | None = None
    allow_subrun_delegation: bool | None = None
    idempotency_key: str | None = None


class ControlWorkflowsExecuteRequest(BaseModel):
    workflow_id: str
    message: str
    session_id: str | None = None
    model: str | None = None
    preset: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    idempotency_key: str | None = None


class ControlWorkflowsDeleteRequest(BaseModel):
    workflow_id: str
    idempotency_key: str | None = None


class ControlRunsGetRequest(BaseModel):
    run_id: str


class ControlRunsListRequest(BaseModel):
    limit: int = 100
    session_id: str | None = None


class ControlRunsEventsRequest(BaseModel):
    run_id: str
    limit: int = 200


class ControlRunsAuditRequest(BaseModel):
    run_id: str


class ControlToolsPolicyPreviewRequest(BaseModel):
    agent_id: str | None = None
    profile: str | None = None
    preset: str | None = None
    provider: str | None = None
    model: str | None = None
    tool_policy: ToolPolicyPayload | None = None
    also_allow: list[str] | None = None


class ControlPolicyApprovalsPendingRequest(BaseModel):
    run_id: str | None = None
    session_id: str | None = None
    limit: int = 100


class ControlPolicyApprovalsAllowRequest(BaseModel):
    approval_id: str


class ControlPolicyApprovalsDecideRequest(BaseModel):
    approval_id: str
    decision: str
    scope: str | None = None


def _normalize_preset(value: str | None) -> str | None:
    preset = (value or "").strip().lower()
    return preset or None


def _normalize_idempotency_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key:
        return None
    if len(key) > 200:
        raise GuardrailViolation("Idempotency key too long (max 200).")
    return key


def _idempotency_registry_limits() -> dict[str, int]:
    return {
        "ttl_seconds": settings.idempotency_registry_ttl_seconds,
        "max_entries": settings.idempotency_registry_max_entries,
    }


def _find_idempotent_run_or_raise(
    *,
    idempotency_key: str | None,
    fingerprint: str,
) -> dict | None:
    return idempotency_lookup_or_raise(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        registry=idempotency_registry,
        lock=idempotency_lock,
        conflict_message="Idempotency key replayed with a different request payload.",
        **_idempotency_registry_limits(),
        replay_builder=lambda key, existing: {
            "status": "accepted",
            "runId": existing.get("run_id"),
            "sessionId": existing.get("session_id"),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_run(
    *,
    idempotency_key: str | None,
    fingerprint: str,
    run_id: str,
    session_id: str,
) -> None:
    idempotency_register(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={
            "run_id": run_id,
            "session_id": session_id,
        },
        registry=idempotency_registry,
        lock=idempotency_lock,
        **_idempotency_registry_limits(),
    )


def _start_run_background(
    *,
    agent_id: str | None,
    message: str,
    session_id: str,
    model: str | None,
    preset: str | None,
    tool_policy: ToolPolicyDict | None,
    meta: dict | None = None,
) -> str:
    runtime_state = runtime_manager.get_state()
    run_id = str(uuid.uuid4())

    state_store.init_run(
        run_id=run_id,
        session_id=session_id,
        request_id=run_id,
        user_message=message or "",
        runtime=runtime_state.runtime,
        model=model or runtime_state.model,
        meta={"source": "rest", "async": True, **(meta or {})},
    )
    state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="pending")
    _state_append_event_safe(
        run_id=run_id,
        event=build_lifecycle_event(
            request_id=run_id,
            session_id=session_id,
            stage="accepted",
            details={"source": "api", "chars": len(message or "")},
            agent=agent.name,
        ),
    )

    task = asyncio.create_task(
        _run_background_message(
            agent_id=agent_id,
            run_id=run_id,
            session_id=session_id,
            message=message,
            model=model,
            preset=preset,
            tool_policy=tool_policy,
        )
    )
    active_run_tasks[run_id] = task
    return run_id


async def _wait_for_run_result(run_id: str, timeout_ms: int | None = None, poll_interval_ms: int | None = None) -> dict:
    run_state = state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    timeout = max(0, int(timeout_ms if timeout_ms is not None else settings.run_wait_default_timeout_ms))
    poll = max(10, int(poll_interval_ms if poll_interval_ms is not None else settings.run_wait_poll_interval_ms))
    elapsed = 0

    while elapsed <= timeout:
        run_state = state_store.get_run(run_id)
        if run_state is None:
            raise HTTPException(status_code=404, detail="Run not found")

        status = run_state.get("status")
        if status in {"completed", "failed"}:
            return _build_wait_payload(
                run_id=run_id,
                run_state=run_state,
                wait_status="ok" if status == "completed" else "error",
            )

        task = active_run_tasks.get(run_id)
        if task and task.done():
            refreshed = state_store.get_run(run_id)
            refreshed_state = refreshed or run_state
            return _build_wait_payload(
                run_id=run_id,
                run_state=refreshed_state,
                wait_status="ok" if refreshed_state.get("status") == "completed" else "error",
            )

        await asyncio.sleep(poll / 1000.0)
        elapsed += poll

    timed_out_state = state_store.get_run(run_id) or run_state
    return _build_wait_payload(
        run_id=run_id,
        run_state=timed_out_state,
        wait_status="timeout",
    )


def _list_sessions_minimal(*, limit: int, active_only: bool) -> dict:
    runs = state_store.list_runs(limit=max(limit * 5, 200))
    by_session: dict[str, dict] = {}
    for run in runs:
        session_id = str(run.get("session_id", "")).strip()
        if not session_id:
            continue
        if active_only and run.get("status") != "active":
            continue
        if session_id in by_session:
            continue
        by_session[session_id] = {
            "session_id": session_id,
            "latest_run_id": run.get("run_id"),
            "status": _normalize_contract_run_status(run.get("status")),
            "runtime": run.get("runtime"),
            "model": run.get("model"),
            "updated_at": run.get("updated_at"),
            "created_at": run.get("created_at"),
        }
        if len(by_session) >= max(1, limit):
            break

    items = list(by_session.values())
    return {
        "schema": "sessions.list.v1",
        "count": len(items),
        "items": items,
    }


def _resolve_latest_session_run(*, session_id: str, limit: int = 2000) -> tuple[dict | None, int, int]:
    return session_query_service.resolve_latest_session_run(session_id=session_id, limit=limit)


def _resolve_session_minimal(*, session_id: str, active_only: bool) -> dict | None:
    target = (session_id or "").strip()
    if not target:
        return None

    latest, runs_count, active_runs_count = _resolve_latest_session_run(session_id=target)

    if latest is None:
        return None

    if active_only and latest.get("status") != "active":
        return None

    return {
        "schema": "sessions.resolve.v1",
        "session": {
            "session_id": target,
            "latest_run_id": latest.get("run_id"),
            "status": _normalize_contract_run_status(latest.get("status")),
            "runtime": latest.get("runtime"),
            "model": latest.get("model"),
            "updated_at": latest.get("updated_at"),
            "created_at": latest.get("created_at"),
            "runs_count": runs_count,
            "active_runs_count": active_runs_count,
        },
    }


def _session_history_minimal(*, session_id: str, limit: int) -> dict:
    target = (session_id or "").strip()
    runs = state_store.list_runs(limit=max(limit * 5, 250))
    items: list[dict] = []

    for run in runs:
        if str(run.get("session_id", "")).strip() != target:
            continue

        items.append(
            {
                "run_id": run.get("run_id"),
                "status": _normalize_contract_run_status(run.get("status")),
                "runtime": run.get("runtime"),
                "model": run.get("model"),
                "updated_at": run.get("updated_at"),
                "created_at": run.get("created_at"),
                "error": run.get("error"),
                "final": _extract_final_message(run),
            }
        )

        if len(items) >= max(1, limit):
            break

    return {
        "schema": "sessions.history.v1",
        "session_id": target,
        "count": len(items),
        "items": items,
    }


def _send_session_minimal(*, request: ControlSessionsSendRequest, idempotency_key_header: str | None) -> dict:
    runtime_state = runtime_manager.get_state()
    session_id = (request.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)

    idempotency_key = _normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = _build_run_start_fingerprint(
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_run_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return {
            "schema": "sessions.send.v1",
            **existing,
        }

    run_id = _start_run_background(
        agent_id=None,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
    )
    _register_idempotent_run(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        run_id=run_id,
        session_id=session_id,
    )

    return {
        "schema": "sessions.send.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }


def _spawn_session_minimal(*, request: ControlSessionsSpawnRequest, idempotency_key_header: str | None) -> dict:
    runtime_state = runtime_manager.get_state()
    parent_session_id = (request.parent_session_id or "").strip()
    if not parent_session_id:
        raise HTTPException(status_code=400, detail="Parent session id must not be empty")

    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)

    idempotency_key = _normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = _build_run_start_fingerprint(
        message=request.message,
        session_id=parent_session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_run_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return {
            "schema": "sessions.spawn.v1",
            "status": existing.get("status"),
            "runId": existing.get("runId"),
            "sessionId": existing.get("sessionId"),
            "parentSessionId": parent_session_id,
            "idempotency": existing.get("idempotency"),
        }

    child_session_id = str(uuid.uuid4())
    run_id = _start_run_background(
        agent_id=None,
        message=request.message,
        session_id=child_session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        meta={
            "source": "control.sessions.spawn",
            "parent_session_id": parent_session_id,
        },
    )
    _register_idempotent_run(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        run_id=run_id,
        session_id=child_session_id,
    )

    return {
        "schema": "sessions.spawn.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": child_session_id,
        "parentSessionId": parent_session_id,
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }


def _session_status_minimal(*, session_id: str) -> dict:
    target = (session_id or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    latest, runs_count, active_runs_count = _resolve_latest_session_run(session_id=target)

    if latest is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "schema": "sessions.status.v1",
        "session": {
            "session_id": target,
            "latest_run_id": latest.get("run_id"),
            "status": _normalize_contract_run_status(latest.get("status")),
            "runtime": latest.get("runtime"),
            "model": latest.get("model"),
            "updated_at": latest.get("updated_at"),
            "created_at": latest.get("created_at"),
            "runs_count": runs_count,
            "active_runs_count": active_runs_count,
            "latest_final": _extract_final_message(latest),
            "latest_error": latest.get("error"),
        },
    }


def _get_session_minimal(*, session_id: str) -> dict:
    payload = _session_status_minimal(session_id=session_id)
    return {
        "schema": "sessions.get.v1",
        "session": payload.get("session"),
    }


def _find_idempotent_session_patch_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    return idempotency_lookup_or_raise(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        registry=session_patch_idempotency_registry,
        lock=session_patch_idempotency_lock,
        conflict_message="Idempotency key replayed with a different session patch payload.",
        **_idempotency_registry_limits(),
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_session_patch(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    idempotency_register(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
        registry=session_patch_idempotency_registry,
        lock=session_patch_idempotency_lock,
        **_idempotency_registry_limits(),
    )


def _patch_session_minimal(*, request: ControlSessionsPatchRequest, idempotency_key_header: str | None) -> dict:
    session_id = (request.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    patch_meta = request.meta if isinstance(request.meta, dict) else {}
    idempotency_key = _normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = _build_session_patch_fingerprint(session_id=session_id, meta=patch_meta)
    existing = _find_idempotent_session_patch_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    latest, _, _ = _resolve_latest_session_run(session_id=session_id)

    if latest is None:
        raise HTTPException(status_code=404, detail="Session not found")

    run_id = str(latest.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=500, detail="Session latest run is missing run_id")

    updated = state_store.patch_run_meta(run_id, patch_meta)
    response = {
        "schema": "sessions.patch.v1",
        "session": {
            "session_id": session_id,
            "latest_run_id": run_id,
            "meta": updated.get("meta") or {},
            "updated_at": updated.get("updated_at"),
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_session_patch(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def _find_idempotent_session_reset_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    return idempotency_lookup_or_raise(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        registry=session_reset_idempotency_registry,
        lock=session_reset_idempotency_lock,
        conflict_message="Idempotency key replayed with a different session reset payload.",
        **_idempotency_registry_limits(),
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_session_reset(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    idempotency_register(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
        registry=session_reset_idempotency_registry,
        lock=session_reset_idempotency_lock,
        **_idempotency_registry_limits(),
    )


def _reset_session_minimal(*, request: ControlSessionsResetRequest, idempotency_key_header: str | None) -> dict:
    session_id = (request.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="Session id must not be empty")

    idempotency_key = _normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    fingerprint = _build_session_reset_fingerprint(session_id=session_id)
    existing = _find_idempotent_session_reset_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    latest, _, _ = _resolve_latest_session_run(session_id=session_id)

    if latest is None:
        raise HTTPException(status_code=404, detail="Session not found")

    run_id = str(latest.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=500, detail="Session latest run is missing run_id")

    updated = state_store.set_run_meta(run_id, {})
    response = {
        "schema": "sessions.reset.v1",
        "session": {
            "session_id": session_id,
            "latest_run_id": run_id,
            "meta": updated.get("meta") or {},
            "updated_at": updated.get("updated_at"),
        },
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }
    _register_idempotent_session_reset(idempotency_key=idempotency_key, fingerprint=fingerprint, response=response)
    return response


def _merge_tool_policy(
    base: ToolPolicyDict | None,
    incoming: ToolPolicyDict | None,
) -> ToolPolicyDict | None:
    return merge_tool_policy(base=base, incoming=incoming)


def _policy_payload(policy: ToolPolicyDict | None) -> ToolPolicyDict:
    return policy_payload(policy)


def _resolve_tool_policy(
    *,
    profile: str | None = None,
    preset: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    request_policy: ToolPolicyDict | None = None,
    also_allow: list[str] | None = None,
    agent_id: str | None = None,
    depth: int | None = None,
    orchestrator_agent_ids: list[str] | None = None,
) -> dict:
    return resolve_tool_policy(
        profile=profile,
        preset=preset,
        provider=provider,
        model=model,
        request_policy=request_policy,
        also_allow=also_allow,
        agent_id=agent_id,
        depth=depth,
        orchestrator_agent_ids=orchestrator_agent_ids,
    )


def _normalize_policy_values(values: list[str] | None, allowed_universe: set[str]) -> set[str] | None:
    return normalize_policy_values(values=values, allowed_universe=allowed_universe)


def _extract_also_allow(tool_policy: ToolPolicyDict | None) -> list[str] | None:
    if not isinstance(tool_policy, dict):
        return None
    raw = tool_policy.get("also_allow")
    if not isinstance(raw, list):
        return None
    values = [str(item).strip() for item in raw if isinstance(item, str) and str(item).strip()]
    return values or None


def _normalize_tool_policy_payload(value: ToolPolicyPayload | ToolPolicyDict | None) -> ToolPolicyDict | None:
    return tool_policy_to_dict(value, include_also_allow=True)


def _build_tools_catalog(*, agent_id: str | None = None) -> dict:
    _sync_custom_agents()

    agents: list[dict] = []
    selected_ids: set[str] | None = None
    if agent_id:
        normalized = _normalize_agent_id(agent_id)
        if normalized not in agent_registry:
            raise HTTPException(status_code=400, detail=f"Unsupported agent: {agent_id}")
        selected_ids = {normalized}

    for item_agent_id, item_agent in sorted(agent_registry.items(), key=lambda pair: pair[0]):
        if selected_ids is not None and item_agent_id not in selected_ids:
            continue
        agents.append(
            {
                "id": item_agent_id,
                "role": getattr(item_agent, "role", "agent"),
                "tools": _get_agent_tools(item_agent),
            }
        )

    all_tools: set[str] = set()
    for item in agents:
        all_tools |= set(item.get("tools") or [])

    return {
        "schema": "tools.catalog.v1",
        "count": len(agents),
        "agents": agents,
        "presets": [
            {
                "id": preset_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
            for preset_id, policy in sorted(PRESET_TOOL_POLICIES.items(), key=lambda pair: pair[0])
        ],
        "globalPolicy": {
            "allow": list(settings.agent_tools_allow or []),
            "deny": list(settings.agent_tools_deny or []),
        },
        "tools": sorted(all_tools),
    }


def _build_tools_profiles(*, profile_id: str | None = None) -> dict:
    normalized_profile = (profile_id or "").strip().lower() or None
    if normalized_profile and normalized_profile not in TOOL_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unsupported profile: {profile_id}")

    profiles = []
    for item_id, policy in sorted(TOOL_PROFILES.items(), key=lambda pair: pair[0]):
        if normalized_profile and item_id != normalized_profile:
            continue
        profiles.append(
            {
                "id": item_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
        )

    return {
        "schema": "tools.profile.v1",
        "count": len(profiles),
        "profiles": profiles,
        "selected": normalized_profile,
    }


def _build_tools_policy_matrix(*, agent_id: str | None = None) -> dict:
    normalized_agent_id = None
    selected_tools: list[str] = []
    if agent_id is not None:
        try:
            normalized_agent_id, selected_agent, _ = _resolve_agent(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        selected_tools = _get_agent_tools(selected_agent)

    return {
        "schema": "tools.policy.matrix.v1",
        "agent_id": normalized_agent_id,
        "base_tools": selected_tools,
        "resolution_order": list(TOOL_POLICY_RESOLUTION_ORDER),
        "global": {
            "allow": list(settings.agent_tools_allow or []),
            "deny": list(settings.agent_tools_deny or []),
        },
        "profiles": [
            {
                "id": item_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
            for item_id, policy in sorted(TOOL_PROFILES.items(), key=lambda pair: pair[0])
        ],
        "presets": [
            {
                "id": item_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
            for item_id, policy in sorted(PRESET_TOOL_POLICIES.items(), key=lambda pair: pair[0])
        ],
        "by_provider": {
            item_id: {
                "allow": list(policy.get("allow") or []),
                "deny": list(policy.get("deny") or []),
            }
            for item_id, policy in sorted(TOOL_POLICY_BY_PROVIDER.items(), key=lambda pair: pair[0])
        },
        "by_model": {
            item_id: {
                "allow": list(policy.get("allow") or []),
                "deny": list(policy.get("deny") or []),
            }
            for item_id, policy in sorted(TOOL_POLICY_BY_MODEL.items(), key=lambda pair: pair[0])
        },
    }


def _build_skills_list(*, skills_dir: str | None = None, max_discovered: int | None = None) -> dict:
    resolved_skills_dir = (skills_dir or "").strip() or settings.skills_dir
    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))

    discovered = discover_skills(
        skills_root=resolved_skills_dir,
        max_discovered=resolved_max_discovered,
    )
    eligible, rejected = filter_eligible_skills(discovered)
    eligible_names = {item.name for item in eligible}

    items: list[dict] = []
    for skill in discovered:
        items.append(
            {
                "name": skill.name,
                "description": skill.description,
                "file_path": skill.file_path,
                "base_dir": skill.base_dir,
                "user_invocable": bool(skill.user_invocable),
                "disable_model_invocation": bool(skill.disable_model_invocation),
                "metadata": {
                    "requires_bins": list(skill.metadata.requires_bins),
                    "requires_env": list(skill.metadata.requires_env),
                    "os": list(skill.metadata.os),
                },
                "eligible": skill.name in eligible_names,
                "rejected_reason": rejected.get(skill.name),
            }
        )

    return {
        "schema": "skills.list.v1",
        "count": len(items),
        "discovered_count": len(discovered),
        "eligible_count": len(eligible),
        "skills_dir": resolved_skills_dir,
        "max_discovered": resolved_max_discovered,
        "items": items,
    }


def _build_skills_preview(
    *,
    skills_dir: str | None = None,
    max_discovered: int | None = None,
    max_prompt_chars: int | None = None,
) -> dict:
    resolved_skills_dir = (skills_dir or "").strip() or settings.skills_dir
    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))
    resolved_max_prompt_chars = max(1000, int(max_prompt_chars or settings.skills_max_prompt_chars))

    discovered = discover_skills(
        skills_root=resolved_skills_dir,
        max_discovered=resolved_max_discovered,
    )
    eligible, _ = filter_eligible_skills(discovered)
    snapshot = build_skill_snapshot(
        discovered=discovered,
        eligible=eligible,
        max_prompt_chars=resolved_max_prompt_chars,
    )

    return {
        "schema": "skills.preview.v1",
        "skills_dir": resolved_skills_dir,
        "max_discovered": resolved_max_discovered,
        "max_prompt_chars": resolved_max_prompt_chars,
        "snapshot": {
            "discovered_count": snapshot.discovered_count,
            "eligible_count": snapshot.eligible_count,
            "selected_count": snapshot.selected_count,
            "truncated": snapshot.truncated,
            "skills": list(snapshot.skills),
            "prompt": snapshot.prompt,
        },
    }


def _build_skills_check(*, skills_dir: str | None = None, max_discovered: int | None = None) -> dict:
    resolved_skills_dir = (skills_dir or "").strip() or settings.skills_dir
    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))

    discovered = discover_skills(
        skills_root=resolved_skills_dir,
        max_discovered=resolved_max_discovered,
    )
    eligible, rejected = filter_eligible_skills(discovered)

    missing_env: dict[str, list[str]] = {}
    missing_bins: dict[str, list[str]] = {}
    os_mismatch: dict[str, list[str]] = {}

    for skill in discovered:
        reasons: list[str] = []
        reason = rejected.get(skill.name)
        if reason:
            reasons.append(reason)
        for item in reasons:
            if item.startswith("missing_env:"):
                missing_env.setdefault(skill.name, []).append(item.split(":", 1)[1])
            elif item.startswith("missing_bin:"):
                missing_bins.setdefault(skill.name, []).append(item.split(":", 1)[1])
            elif item.startswith("os_mismatch:"):
                os_mismatch.setdefault(skill.name, []).append(item.split(":", 1)[1])

    return {
        "schema": "skills.check.v1",
        "skills_dir": resolved_skills_dir,
        "max_discovered": resolved_max_discovered,
        "discovered_count": len(discovered),
        "eligible_count": len(eligible),
        "ineligible_count": max(0, len(discovered) - len(eligible)),
        "issues": {
            "missing_env": missing_env,
            "missing_bins": missing_bins,
            "os_mismatch": os_mismatch,
        },
        "rejected": rejected,
    }


def _build_skills_sync(
    *,
    source_skills_dir: str | None = None,
    target_skills_dir: str | None = None,
    max_discovered: int | None = None,
    max_sync_items: int = 200,
    apply: bool = False,
    clean_target: bool = False,
    confirm_clean_target: bool = False,
) -> dict:
    started_at = datetime.now(timezone.utc)
    started_monotonic = monotonic()
    workspace_root = Path(settings.workspace_root).resolve()

    source_raw = (source_skills_dir or "").strip() or settings.skills_dir
    source_path = Path(source_raw)
    if not source_path.is_absolute():
        source_path = (workspace_root / source_path).resolve()
    else:
        source_path = source_path.resolve()

    target_raw = (target_skills_dir or "").strip() or "skills_synced"
    target_path = Path(target_raw)
    if not target_path.is_absolute():
        target_path = (workspace_root / target_path).resolve()
    else:
        target_path = target_path.resolve()

    try:
        target_path.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="target_skills_dir must be inside workspace_root") from exc

    if source_path == target_path:
        raise HTTPException(status_code=400, detail="source_skills_dir and target_skills_dir must differ")
    if not source_path.exists() or not source_path.is_dir():
        raise HTTPException(status_code=400, detail="source_skills_dir not found or not a directory")

    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))
    resolved_max_sync_items = max(1, min(int(max_sync_items), 1000))

    if clean_target and apply and not confirm_clean_target:
        raise HTTPException(
            status_code=400,
            detail="clean_target apply requires confirm_clean_target=true",
        )

    discovered = discover_skills(
        skills_root=str(source_path),
        max_discovered=resolved_max_discovered,
    )
    eligible, _ = filter_eligible_skills(discovered)

    actions: list[dict] = []
    used_dirs: set[str] = set()
    for skill in eligible:
        base_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", skill.name).strip("-") or "skill"
        candidate = base_name
        suffix = 2
        while candidate.lower() in used_dirs:
            candidate = f"{base_name}-{suffix}"
            suffix += 1
        used_dirs.add(candidate.lower())

        destination = target_path / candidate
        action = "create" if not destination.exists() else "update"
        actions.append(
            {
                "skill_name": skill.name,
                "action": action,
                "source_dir": skill.base_dir,
                "target_dir": str(destination),
            }
        )
        if len(actions) >= resolved_max_sync_items:
            break

    if clean_target and target_path.exists() and target_path.is_dir() and len(actions) < resolved_max_sync_items:
        for child in sorted(target_path.iterdir(), key=lambda item: item.name.lower()):
            if len(actions) >= resolved_max_sync_items:
                break
            if not child.is_dir():
                continue
            if child.name.lower() in used_dirs:
                continue
            if not (child / "SKILL.md").exists():
                continue
            actions.append(
                {
                    "skill_name": child.name,
                    "action": "delete",
                    "source_dir": None,
                    "target_dir": str(child),
                }
            )

    planned_delete_count = sum(1 for item in actions if item["action"] == "delete")
    planned_upsert_count = len(actions) - planned_delete_count

    applied_count = 0
    applied_delete_count = 0
    if apply:
        target_path.mkdir(parents=True, exist_ok=True)
        for item in actions:
            action = str(item.get("action", ""))
            dst = Path(str(item["target_dir"]))

            if action == "delete":
                if dst.exists():
                    shutil.rmtree(dst)
                    applied_count += 1
                    applied_delete_count += 1
                continue

            src_value = item.get("source_dir")
            if src_value is None:
                continue
            src = Path(str(src_value))
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            applied_count += 1

    duration_ms = int((monotonic() - started_monotonic) * 1000)
    logger.info(
        "skills_sync_audit mode=%s source=%s target=%s clean_target=%s planned=%s planned_upsert=%s planned_delete=%s applied=%s applied_delete=%s duration_ms=%s",
        "apply" if apply else "dry_run",
        source_path,
        target_path,
        clean_target,
        len(actions),
        planned_upsert_count,
        planned_delete_count,
        applied_count,
        applied_delete_count,
        duration_ms,
    )

    return {
        "schema": "skills.sync.v1",
        "mode": "apply" if apply else "dry_run",
        "source_skills_dir": str(source_path),
        "target_skills_dir": str(target_path),
        "clean_target": clean_target,
        "max_discovered": resolved_max_discovered,
        "max_sync_items": resolved_max_sync_items,
        "eligible_count": len(eligible),
        "planned_count": len(actions),
        "planned_upsert_count": planned_upsert_count,
        "planned_delete_count": planned_delete_count,
        "applied_count": applied_count,
        "applied_delete_count": applied_delete_count,
        "audit": {
            "started_at": started_at.isoformat(),
            "duration_ms": duration_ms,
        },
        "actions": actions,
        "guardrails": {
            "target_must_be_within_workspace": True,
            "max_sync_items_cap": 1000,
            "clean_target_requires_confirmation_for_apply": True,
            "clean_target_deletes_only_skill_dirs": True,
        },
    }


def _list_workflows_minimal(*, limit: int, base_agent_id: str | None = None) -> dict:
    normalized_base_agent = _normalize_agent_id(base_agent_id) if base_agent_id else None
    items: list[dict] = []

    for definition in custom_agent_store.list():
        base_id = _normalize_agent_id(definition.base_agent_id)
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
    definition = _find_workflow_or_404(workflow_id)
    steps = [step for step in (definition.workflow_steps or []) if isinstance(step, str) and step.strip()]
    return {
        "schema": "workflows.get.v1",
        "workflow": {
            "id": definition.id,
            "name": definition.name,
            "description": definition.description,
            "base_agent_id": _normalize_agent_id(definition.base_agent_id),
            "allow_subrun_delegation": bool(getattr(definition, "allow_subrun_delegation", False)),
            "version": _get_workflow_version(definition.id),
            "steps": steps,
            "step_count": len(steps),
            "tool_policy": definition.tool_policy,
        },
    }


def _get_workflow_version(workflow_id: str) -> int:
    normalized = _normalize_agent_id(workflow_id)
    with workflow_version_lock:
        return int(workflow_version_registry.get(normalized, 1))


def _set_workflow_version(workflow_id: str, version: int) -> None:
    normalized = _normalize_agent_id(workflow_id)
    with workflow_version_lock:
        workflow_version_registry[normalized] = max(1, int(version))


def _increment_workflow_version(workflow_id: str) -> int:
    normalized = _normalize_agent_id(workflow_id)
    with workflow_version_lock:
        current = int(workflow_version_registry.get(normalized, 1))
        next_version = current + 1
        workflow_version_registry[normalized] = next_version
        return next_version


def _delete_workflow_version(workflow_id: str) -> None:
    normalized = _normalize_agent_id(workflow_id)
    with workflow_version_lock:
        workflow_version_registry.pop(normalized, None)


def _find_idempotent_workflow_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    return idempotency_lookup_or_raise(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        registry=workflow_idempotency_registry,
        lock=workflow_idempotency_lock,
        conflict_message="Idempotency key replayed with a different workflow payload.",
        **_idempotency_registry_limits(),
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_workflow(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    idempotency_register(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
        registry=workflow_idempotency_registry,
        lock=workflow_idempotency_lock,
        **_idempotency_registry_limits(),
    )


def _create_workflow_minimal(*, request: ControlWorkflowsCreateRequest) -> dict:
    _sync_custom_agents()

    normalized_base_agent = _normalize_agent_id(request.base_agent_id)
    if normalized_base_agent not in agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    steps = [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]
    workflow_id = (request.id or "").strip() or None
    name = (request.name or "").strip()
    description = (request.description or "").strip()
    if not name:
        raise GuardrailViolation("Workflow name must not be empty.")

    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)

    idempotency_key = _normalize_idempotency_key(request.idempotency_key)
    fingerprint = _build_workflow_create_fingerprint(
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

    created = custom_agent_store.upsert(
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
    _sync_custom_agents()
    _set_workflow_version(created.id, 1)

    response = {
        "schema": "workflows.create.v1",
        "status": "created",
        "workflow": {
            "id": created.id,
            "name": created.name,
            "description": created.description,
            "base_agent_id": _normalize_agent_id(created.base_agent_id),
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
    _sync_custom_agents()

    workflow_id = (request.id or "").strip().lower()
    if not workflow_id:
        raise GuardrailViolation("Workflow id must not be empty.")

    existing = next((item for item in custom_agent_store.list() if item.id == workflow_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    resolved_name = (request.name or existing.name or "").strip()
    if not resolved_name:
        raise GuardrailViolation("Workflow name must not be empty.")

    resolved_description = (
        existing.description
        if request.description is None
        else (request.description or "").strip()
    )

    if request.base_agent_id is None:
        normalized_base_agent = _normalize_agent_id(existing.base_agent_id)
    else:
        normalized_base_agent = _normalize_agent_id(request.base_agent_id)
    if normalized_base_agent not in agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    if request.steps is None:
        resolved_steps = [step for step in (existing.workflow_steps or []) if isinstance(step, str) and step.strip()]
    else:
        resolved_steps = [step.strip() for step in (request.steps or []) if isinstance(step, str) and step.strip()]

    resolved_tool_policy = (
        existing.tool_policy if request.tool_policy is None else _normalize_tool_policy_payload(request.tool_policy)
    )
    resolved_allow_subrun_delegation = (
        bool(getattr(existing, "allow_subrun_delegation", False))
        if request.allow_subrun_delegation is None
        else bool(request.allow_subrun_delegation)
    )

    idempotency_key = _normalize_idempotency_key(request.idempotency_key)
    fingerprint = _build_workflow_create_fingerprint(
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

    updated = custom_agent_store.upsert(
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
    _sync_custom_agents()
    next_version = _increment_workflow_version(updated.id)

    response = {
        "schema": "workflows.update.v1",
        "status": "updated",
        "workflow": {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "base_agent_id": _normalize_agent_id(updated.base_agent_id),
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


def _find_workflow_or_404(workflow_id: str) -> CustomAgentDefinition:
    target = _normalize_agent_id(workflow_id)
    match = next((item for item in custom_agent_store.list() if _normalize_agent_id(item.id) == target), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return match


def _find_idempotent_workflow_execute_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    return idempotency_lookup_or_raise(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        registry=workflow_execute_idempotency_registry,
        lock=workflow_execute_idempotency_lock,
        conflict_message="Idempotency key replayed with a different workflow execute payload.",
        **_idempotency_registry_limits(),
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_workflow_execute(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    idempotency_register(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
        registry=workflow_execute_idempotency_registry,
        lock=workflow_execute_idempotency_lock,
        **_idempotency_registry_limits(),
    )


async def _execute_workflow_minimal(*, request: ControlWorkflowsExecuteRequest) -> dict:
    _sync_custom_agents()

    workflow = _find_workflow_or_404(request.workflow_id)
    workflow_agent_id = _normalize_agent_id(workflow.id)
    _, _, workflow_orchestrator = _resolve_agent(workflow_agent_id)

    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)

    runtime_state = runtime_manager.get_state()
    idempotency_key = _normalize_idempotency_key(request.idempotency_key)
    fingerprint = _build_workflow_execute_fingerprint(
        workflow_id=workflow_agent_id,
        message=request.message,
        session_id=request.session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        allow_subrun_delegation=bool(getattr(workflow, "allow_subrun_delegation", False)),
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_workflow_execute_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    session_id = request.session_id or str(uuid.uuid4())
    run_id = _start_run_background(
        agent_id=workflow_agent_id,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        meta={
            "workflow_execute": True,
            "workflow_id": workflow_agent_id,
            "workflow_version": _get_workflow_version(workflow_agent_id),
        },
    )

    steps = [step for step in (workflow.workflow_steps or []) if isinstance(step, str) and step.strip()]
    step_spawn_cap = max(1, int(settings.subrun_max_children_per_parent))
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
            subrun_id = await subrun_lane.spawn(
                parent_request_id=run_id,
                parent_session_id=session_id,
                user_message=step_message,
                runtime=runtime_state.runtime,
                model=request.model or runtime_state.model,
                timeout_seconds=settings.subrun_timeout_seconds,
                tool_policy=normalized_tool_policy,
                send_event=_noop_send_event,
                agent_id=workflow_agent_id,
                mode="run",
                preset=request.preset,
                orchestrator_agent_ids=sorted(_effective_orchestrator_agent_ids()),
                orchestrator_api=workflow_orchestrator,
            )
            info = subrun_lane.get_info(subrun_id) or {}
            allowed, decision = subrun_lane.evaluate_visibility(
                subrun_id,
                requester_session_id=session_id,
                visibility_scope=settings.session_visibility_default,
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
            "base_agent_id": _normalize_agent_id(workflow.base_agent_id),
            "version": _get_workflow_version(workflow_agent_id),
            "steps": steps,
            "step_count": len(steps),
        },
        "execution": {
            "engine": "workflow.revision_flow.v1",
            "mode": "subrun_graph",
            "root_run_id": run_id,
            "visibility_scope": settings.session_visibility_default,
            "a2a_policy": "parent_child_session_tree",
            "steps": spawned_subruns,
            "warnings": subrun_warnings,
            "budgets": {
                "step_spawn_cap": step_spawn_cap,
                "step_total": len(steps),
                "step_executed": len(executable_steps),
                "subrun_timeout_seconds": settings.subrun_timeout_seconds,
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


def _find_idempotent_workflow_delete_or_raise(*, idempotency_key: str | None, fingerprint: str) -> dict | None:
    return idempotency_lookup_or_raise(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        registry=workflow_delete_idempotency_registry,
        lock=workflow_delete_idempotency_lock,
        conflict_message="Idempotency key replayed with a different workflow delete payload.",
        **_idempotency_registry_limits(),
        replay_builder=lambda key, existing: {
            **dict(existing.get("response") or {}),
            "idempotency": {
                "key": key,
                "reused": True,
            },
        },
    )


def _register_idempotent_workflow_delete(*, idempotency_key: str | None, fingerprint: str, response: dict) -> None:
    idempotency_register(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        value={"response": response},
        registry=workflow_delete_idempotency_registry,
        lock=workflow_delete_idempotency_lock,
        **_idempotency_registry_limits(),
    )


def _delete_workflow_minimal(*, request: ControlWorkflowsDeleteRequest) -> dict:
    workflow_id = _normalize_agent_id(request.workflow_id)
    if not workflow_id:
        raise GuardrailViolation("Workflow id must not be empty.")

    idempotency_key = _normalize_idempotency_key(request.idempotency_key)
    fingerprint = _build_workflow_delete_fingerprint(workflow_id=workflow_id)
    existing = _find_idempotent_workflow_delete_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return existing

    workflow = _find_workflow_or_404(workflow_id)

    deleted = custom_agent_store.delete(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    _delete_workflow_version(workflow_id)
    _sync_custom_agents()

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


def _get_run_minimal(*, run_id: str) -> dict:
    run_state = state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    events = run_state.get("events") or []
    lifecycle_events = [event for event in events if event.get("type") == "lifecycle"]
    return {
        "schema": "runs.get.v1",
        "run": {
            "run_id": run_state.get("run_id"),
            "request_id": run_state.get("request_id"),
            "session_id": run_state.get("session_id"),
            "status": _normalize_contract_run_status(run_state.get("status")),
            "runtime": run_state.get("runtime"),
            "model": run_state.get("model"),
            "created_at": run_state.get("created_at"),
            "updated_at": run_state.get("updated_at"),
            "error": run_state.get("error"),
            "final": _extract_final_message(run_state),
            "event_count": len(events),
            "lifecycle_count": len(lifecycle_events),
        },
    }


def _list_runs_minimal(*, limit: int, session_id: str | None) -> dict:
    capped_limit = max(1, min(limit, 200))
    session_filter = (session_id or "").strip()

    runs = state_store.list_runs(limit=max(capped_limit * 5, 200))
    items: list[dict] = []

    for run in runs:
        if session_filter and str(run.get("session_id", "")).strip() != session_filter:
            continue

        items.append(
            {
                "run_id": run.get("run_id"),
                "request_id": run.get("request_id"),
                "session_id": run.get("session_id"),
                "status": _normalize_contract_run_status(run.get("status")),
                "runtime": run.get("runtime"),
                "model": run.get("model"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "error": run.get("error"),
                "final": _extract_final_message(run),
            }
        )

        if len(items) >= capped_limit:
            break

    return {
        "schema": "runs.list.v1",
        "count": len(items),
        "items": items,
    }


def _list_run_events_minimal(*, run_id: str, limit: int) -> dict:
    run_state = state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    capped_limit = max(1, min(limit, 1000))
    events = list(run_state.get("events") or [])
    items = events[-capped_limit:]

    return {
        "schema": "runs.events.v1",
        "run_id": run_id,
        "count": len(items),
        "total_count": len(events),
        "items": items,
    }


def _get_run_audit_minimal(*, run_id: str) -> dict:
    run_state = state_store.get_run(run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    events = list(run_state.get("events") or [])
    lifecycle_events = [event for event in events if event.get("type") == "lifecycle"]
    lifecycle_stage_counts: dict[str, int] = {}
    blocked_with_reason_counts: dict[str, int] = {}
    tool_selection_empty_reason_counts: dict[str, int] = {}
    last_tool_audit_summary: dict = {}
    for event in lifecycle_events:
        stage = str(event.get("stage") or "").strip()
        if not stage:
            continue
        lifecycle_stage_counts[stage] = lifecycle_stage_counts.get(stage, 0) + 1

        details = event.get("details")
        if not isinstance(details, dict):
            details = {}

        blocked_with_reason = details.get("blocked_with_reason")
        if isinstance(blocked_with_reason, str) and blocked_with_reason.strip():
            key = blocked_with_reason.strip()
            blocked_with_reason_counts[key] = blocked_with_reason_counts.get(key, 0) + 1

        if stage == "tool_selection_empty":
            reason = details.get("reason")
            if isinstance(reason, str) and reason.strip():
                key = reason.strip()
                tool_selection_empty_reason_counts[key] = tool_selection_empty_reason_counts.get(key, 0) + 1

        if stage == "tool_audit_summary":
            last_tool_audit_summary = dict(details)

    return {
        "schema": "runs.audit.v1",
        "run": {
            "run_id": run_state.get("run_id"),
            "session_id": run_state.get("session_id"),
            "status": _normalize_contract_run_status(run_state.get("status")),
            "created_at": run_state.get("created_at"),
            "updated_at": run_state.get("updated_at"),
        },
        "telemetry": {
            "event_count": len(events),
            "lifecycle_count": len(lifecycle_events),
            "lifecycle_stages": lifecycle_stage_counts,
            "blocked_with_reason": blocked_with_reason_counts,
            "tool_selection_empty_reasons": tool_selection_empty_reason_counts,
            "tool_started": lifecycle_stage_counts.get("tool_started", 0),
            "tool_completed": lifecycle_stage_counts.get("tool_completed", 0),
            "tool_failed": lifecycle_stage_counts.get("tool_failed", 0),
            "tool_loop_warn": lifecycle_stage_counts.get("tool_loop_warn", 0),
            "tool_loop_blocked": lifecycle_stage_counts.get("tool_loop_blocked", 0),
            "tool_budget_exceeded": lifecycle_stage_counts.get("tool_budget_exceeded", 0),
            "tool_audit_summary": lifecycle_stage_counts.get("tool_audit_summary", 0),
            "guardrail_summary": {
                "loop_warn_count": lifecycle_stage_counts.get("tool_loop_warn", 0),
                "loop_blocked_count": lifecycle_stage_counts.get("tool_loop_blocked", 0),
                "budget_exceeded_count": lifecycle_stage_counts.get("tool_budget_exceeded", 0),
                "tool_audit": {
                    "tool_calls": int(last_tool_audit_summary.get("tool_calls", 0) or 0),
                    "tool_errors": int(last_tool_audit_summary.get("tool_errors", 0) or 0),
                    "loop_blocked": int(last_tool_audit_summary.get("loop_blocked", 0) or 0),
                    "budget_blocked": int(last_tool_audit_summary.get("budget_blocked", 0) or 0),
                    "elapsed_ms": int(last_tool_audit_summary.get("elapsed_ms", 0) or 0),
                    "call_cap": int(last_tool_audit_summary.get("call_cap", 0) or 0),
                    "time_cap_seconds": float(last_tool_audit_summary.get("time_cap_seconds", 0.0) or 0.0),
                    "loop_warn_threshold": int(last_tool_audit_summary.get("loop_warn_threshold", 0) or 0),
                    "loop_critical_threshold": int(last_tool_audit_summary.get("loop_critical_threshold", 0) or 0),
                },
            },
        },
    }


def _build_tools_policy_preview(
    *,
    agent_id: str | None,
    profile: str | None,
    preset: str | None,
    provider: str | None,
    model: str | None,
    tool_policy: ToolPolicyDict | None,
    also_allow: list[str] | None,
) -> dict:
    try:
        resolved_agent_id, selected_agent, _ = _resolve_agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    base_tools = set(_get_agent_tools(selected_agent))

    resolved = _resolve_tool_policy(
        profile=profile,
        preset=preset,
        provider=provider,
        model=model,
        request_policy=tool_policy,
        also_allow=also_allow,
        agent_id=resolved_agent_id,
        depth=0,
        orchestrator_agent_ids=sorted(_effective_orchestrator_agent_ids()),
    )

    merged_policy = resolved["merged_policy"]
    applied_preset = resolved["applied_preset"]
    normalized_profile = resolved["profile"]
    normalized_provider = resolved["provider"]
    normalized_model = resolved["model"]

    merged_policy = selected_agent.normalize_tool_policy(merged_policy)

    effective = set(base_tools)

    config_allow = _normalize_policy_values(settings.agent_tools_allow, base_tools)
    if config_allow is not None:
        effective &= config_allow

    requested_allow = _normalize_policy_values((merged_policy or {}).get("allow"), base_tools)
    if requested_allow is not None:
        effective &= requested_allow

    deny = set()
    deny |= _normalize_policy_values(settings.agent_tools_deny, base_tools) or set()
    deny |= _normalize_policy_values((merged_policy or {}).get("deny"), base_tools) or set()
    effective -= deny

    also_allow_set = _normalize_policy_values(also_allow, base_tools) or set()
    effective |= (also_allow_set - deny)

    return {
        "schema": "tools.policy.preview.v1",
        "agent_id": resolved_agent_id,
        "profile": normalized_profile,
        "preset": applied_preset,
        "provider": normalized_provider,
        "model": normalized_model,
        "base_tools": sorted(base_tools),
        "effective_allow": sorted(effective),
        "effective_deny": sorted(deny),
        "also_allow": sorted(also_allow_set),
        "scoped": resolved["scoped"],
        "requested": merged_policy or {},
        "explain": resolved["explain"],
        "global": {
            "allow": list(settings.agent_tools_allow or []),
            "deny": list(settings.agent_tools_deny or []),
        },
    }


def _extract_final_message(run_state: dict) -> str | None:
    events = run_state.get("events") or []
    for event in reversed(events):
        if event.get("type") == "final" and event.get("message"):
            return event.get("message")
    return None


async def _run_background_message(
    *,
    agent_id: str | None,
    run_id: str,
    session_id: str,
    message: str,
    model: str | None,
    preset: str | None,
    tool_policy: ToolPolicyDict | None,
) -> None:
    async def collect_event(payload: dict) -> None:
        _state_append_event_safe(run_id=run_id, event=payload)

    try:
        resolved_agent_id, selected_agent, selected_orchestrator = _resolve_agent(agent_id)
        applied_preset = _normalize_preset(preset)
        state_store.set_task_status(run_id=run_id, task_id="request", label="request", status="active")
        _state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_started",
                details={"preset": applied_preset, "agent_id": resolved_agent_id},
                agent=selected_agent.name,
            ),
        )

        runtime_state = runtime_manager.get_state()
        selected_model = (model or "").strip() or runtime_state.model

        selected_agent.configure_runtime(
            base_url=runtime_state.base_url,
            model=runtime_state.model,
        )

        if runtime_state.runtime == "local":
            selected_model = await runtime_manager.ensure_model_ready(collect_event, session_id, selected_model)
        else:
            selected_model = await runtime_manager.resolve_api_request_model(selected_model)

        await selected_orchestrator.run_user_message(
            user_message=message,
            send_event=collect_event,
            request_context=RequestContext(
                session_id=session_id,
                request_id=run_id,
                runtime=runtime_state.runtime,
                model=selected_model,
                tool_policy=tool_policy,
                also_allow=_extract_also_allow(tool_policy),
                agent_id=resolved_agent_id,
                depth=0,
                preset=applied_preset,
                orchestrator_agent_ids=sorted(_effective_orchestrator_agent_ids()),
            ),
        )
        _state_mark_completed_safe(run_id=run_id)
        _state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_completed",
                details={"agent_id": resolved_agent_id},
                agent=selected_agent.name,
            ),
        )
    except Exception as exc:
        _state_mark_failed_safe(run_id=run_id, error=str(exc))
        _state_append_event_safe(
            run_id=run_id,
            event=build_lifecycle_event(
                request_id=run_id,
                session_id=session_id,
                stage="processing_failed",
                details={"error": str(exc)},
                agent=(selected_agent.name if "selected_agent" in locals() else agent.name),
            ),
        )
        logger.exception("background_run_failed run_id=%s session_id=%s", run_id, session_id)
    finally:
        _remove_active_task(run_id)


def _api_agents_list() -> list[dict]:
    _sync_custom_agents()
    active = runtime_manager.get_state()
    items: list[dict] = []
    for agent_id, agent_instance in agent_registry.items():
        items.append(
            {
                "id": agent_id,
                "name": agent_instance.name,
                "role": getattr(agent_instance, "role", "agent"),
                "status": "ready",
                "defaultModel": active.model,
            }
        )
    items.sort(key=lambda item: item["id"])
    return items


def _api_presets_list() -> list[dict]:
    items: list[dict] = []
    for preset_id in sorted(PRESET_TOOL_POLICIES.keys()):
        policy = PRESET_TOOL_POLICIES[preset_id]
        items.append(
            {
                "id": preset_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
        )
    return items


def _api_custom_agents_list() -> list[CustomAgentDefinition]:
    return custom_agent_store.list()


def _api_custom_agents_create(request_data: dict) -> CustomAgentDefinition:
    request = CustomAgentCreateRequest.model_validate(request_data)
    base_agent_id = _normalize_agent_id(request.base_agent_id)
    if base_agent_id not in agent_registry:
        raise HTTPException(status_code=400, detail=f"Unsupported base agent: {request.base_agent_id}")

    created = custom_agent_store.upsert(
        request,
        id_factory=lambda name: f"custom-{name}-{str(uuid.uuid4())[:8]}",
    )
    _sync_custom_agents()
    return created


def _api_custom_agents_delete(agent_id: str) -> dict:
    normalized = _normalize_agent_id(agent_id)
    if normalized in {PRIMARY_AGENT_ID, CODER_AGENT_ID, REVIEW_AGENT_ID}:
        raise HTTPException(status_code=400, detail="Built-in agents cannot be deleted")

    deleted = custom_agent_store.delete(normalized)
    if not deleted:
        raise HTTPException(status_code=404, detail="Custom agent not found")

    _sync_custom_agents()
    return {"ok": True, "deletedId": normalized}


def _api_monitoring_schema() -> dict:
    _sync_custom_agents()
    return {
        "lifecycleStages": [stage.value for stage in LifecycleStage],
        "eventTypes": [
            "status",
            "lifecycle",
            "agent_step",
            "token",
            "final",
            "error",
            "subrun_status",
            "subrun_announce",
            "runtime_switch_done",
            "runtime_switch_error",
        ],
        "reasoningVisibility": {
            "chainOfThought": "hidden",
            "observableTrace": "available_via_lifecycle_and_tool_events",
        },
        "agents": [
            {
                "id": agent_id,
                "name": agent_instance.name,
                "role": getattr(agent_instance, "role", "agent"),
                "tools": _get_agent_tools(agent_instance),
            }
            for agent_id, agent_instance in agent_registry.items()
        ],
    }


app.include_router(
    build_agents_router(
        agents_list_handler=_api_agents_list,
        presets_list_handler=_api_presets_list,
        custom_agents_list_handler=_api_custom_agents_list,
        custom_agents_create_handler=_api_custom_agents_create,
        custom_agents_delete_handler=_api_custom_agents_delete,
        monitoring_schema_handler=_api_monitoring_schema,
    )
)

_agent_test_dependencies = AgentTestDependencies(
    logger=logger,
    runtime_manager=runtime_manager,
    state_store=state_store,
    agent=agent,
    orchestrator_api=orchestrator_api,
    normalize_preset=_normalize_preset,
    extract_also_allow=_extract_also_allow,
    effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
    mark_completed=_state_mark_completed_safe,
    mark_failed=_state_mark_failed_safe,
    primary_agent_id=PRIMARY_AGENT_ID,
)

_run_endpoint_dependencies = RunEndpointsDependencies(
    start_run_background=_start_run_background,
    wait_for_run_result=_wait_for_run_result,
)

_runtime_debug_dependencies = RuntimeDebugDependencies(
    runtime_manager=runtime_manager,
    settings=settings,
    resolved_prompt_settings=resolved_prompt_settings,
)

_subrun_endpoint_dependencies = SubrunEndpointsDependencies(
    subrun_lane=subrun_lane,
    session_visibility_default=settings.session_visibility_default,
    state_append_event_safe=_state_append_event_safe,
)

app.include_router(
    build_run_api_router(
        handlers=RunApiRouterHandlers(
            agent_test_handler=lambda request_data: run_agent_test(
                request=AgentTestRequest.model_validate(request_data),
                deps=_agent_test_dependencies,
            ),
            start_run_handler=lambda request_data: run_endpoint_start(
                request=RunStartRequest.model_validate(request_data),
                deps=_run_endpoint_dependencies,
            ),
            wait_run_handler=lambda run_id, timeout_ms, poll_interval_ms: run_endpoint_wait(
                run_id=run_id,
                timeout_ms=timeout_ms,
                poll_interval_ms=poll_interval_ms,
                deps=_run_endpoint_dependencies,
            ),
        )
    )
)


async def _api_control_run_start(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlRunStartRequest.model_validate(request_data)
    runtime_state = runtime_manager.get_state()
    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)
    idempotency_key = _normalize_idempotency_key(request.idempotency_key or idempotency_key_header)
    session_id = request.session_id or str(uuid.uuid4())

    fingerprint = _build_run_start_fingerprint(
        message=request.message,
        session_id=request.session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
        runtime=runtime_state.runtime,
    )
    existing = _find_idempotent_run_or_raise(idempotency_key=idempotency_key, fingerprint=fingerprint)
    if existing is not None:
        return {
            "schema": "run.start.v1",
            **existing,
        }

    run_id = _start_run_background(
        agent_id=None,
        message=request.message,
        session_id=session_id,
        model=request.model,
        preset=request.preset,
        tool_policy=normalized_tool_policy,
    )
    _register_idempotent_run(
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
        run_id=run_id,
        session_id=session_id,
    )

    return {
        "schema": "run.start.v1",
        "status": "accepted",
        "runId": run_id,
        "sessionId": session_id,
        "idempotency": {
            "key": idempotency_key,
            "reused": False,
        },
    }


async def _api_control_run_wait(request_data: dict) -> dict:
    request = ControlRunWaitRequest.model_validate(request_data)
    payload = await _wait_for_run_result(
        request.run_id,
        timeout_ms=request.timeout_ms,
        poll_interval_ms=request.poll_interval_ms,
    )
    return {
        "schema": "run.wait.v1",
        **payload,
    }


async def _api_control_agent_run(request_data: dict, idempotency_key_header: str | None) -> dict:
    payload = await _api_control_run_start(request_data=request_data, idempotency_key_header=idempotency_key_header)
    return {
        "schema": "agent.run.v1",
        **{key: value for key, value in payload.items() if key != "schema"},
    }


async def _api_control_agent_wait(request_data: dict) -> dict:
    payload = await _api_control_run_wait(request_data=request_data)
    return {
        "schema": "agent.wait.v1",
        **{key: value for key, value in payload.items() if key != "schema"},
    }


def _api_control_sessions_list(request_data: dict) -> dict:
    request = ControlSessionsListRequest.model_validate(request_data)
    limit = max(1, min(int(request.limit), 500))
    return _list_sessions_minimal(limit=limit, active_only=bool(request.active_only))


def _api_control_sessions_resolve(request_data: dict) -> dict:
    request = ControlSessionsResolveRequest.model_validate(request_data)
    payload = _resolve_session_minimal(
        session_id=request.session_id,
        active_only=bool(request.active_only),
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return payload


def _api_control_sessions_history(request_data: dict) -> dict:
    request = ControlSessionsHistoryRequest.model_validate(request_data)
    limit = max(1, min(int(request.limit), 500))
    return _session_history_minimal(session_id=request.session_id, limit=limit)


def _api_control_sessions_send(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsSendRequest.model_validate(request_data)
    return _send_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def _api_control_sessions_spawn(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsSpawnRequest.model_validate(request_data)
    return _spawn_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def _api_control_sessions_status(request_data: dict) -> dict:
    request = ControlSessionsStatusRequest.model_validate(request_data)
    return _session_status_minimal(session_id=request.session_id)


def _api_control_sessions_get(request_data: dict) -> dict:
    request = ControlSessionsGetRequest.model_validate(request_data)
    return _get_session_minimal(session_id=request.session_id)


def _api_control_sessions_patch(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsPatchRequest.model_validate(request_data)
    return _patch_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def _api_control_sessions_reset(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlSessionsResetRequest.model_validate(request_data)
    return _reset_session_minimal(request=request, idempotency_key_header=idempotency_key_header)


def _api_control_tools_catalog(request_data: dict) -> dict:
    request = ControlToolsCatalogRequest.model_validate(request_data)
    return _build_tools_catalog(agent_id=request.agent_id)


def _api_control_tools_profile(request_data: dict) -> dict:
    request = ControlToolsProfileRequest.model_validate(request_data)
    return _build_tools_profiles(profile_id=request.profile_id)


def _api_control_tools_policy_matrix(request_data: dict) -> dict:
    request = ControlToolsPolicyMatrixRequest.model_validate(request_data)
    return _build_tools_policy_matrix(agent_id=request.agent_id)


def _api_control_skills_list(request_data: dict) -> dict:
    request = ControlSkillsListRequest.model_validate(request_data)
    return _build_skills_list(
        skills_dir=request.skills_dir,
        max_discovered=request.max_discovered,
    )


def _api_control_skills_preview(request_data: dict) -> dict:
    request = ControlSkillsPreviewRequest.model_validate(request_data)
    return _build_skills_preview(
        skills_dir=request.skills_dir,
        max_discovered=request.max_discovered,
        max_prompt_chars=request.max_prompt_chars,
    )


def _api_control_skills_check(request_data: dict) -> dict:
    request = ControlSkillsCheckRequest.model_validate(request_data)
    return _build_skills_check(
        skills_dir=request.skills_dir,
        max_discovered=request.max_discovered,
    )


def _api_control_skills_sync(request_data: dict) -> dict:
    request = ControlSkillsSyncRequest.model_validate(request_data)
    return _build_skills_sync(
        source_skills_dir=request.source_skills_dir,
        target_skills_dir=request.target_skills_dir,
        max_discovered=request.max_discovered,
        max_sync_items=request.max_sync_items,
        apply=request.apply,
        clean_target=request.clean_target,
        confirm_clean_target=request.confirm_clean_target,
    )


def _api_control_workflows_list(request_data: dict) -> dict:
    request = ControlWorkflowsListRequest.model_validate(request_data)
    limit = max(1, min(int(request.limit), 500))
    return _list_workflows_minimal(limit=limit, base_agent_id=request.base_agent_id)


def _api_control_workflows_get(request_data: dict) -> dict:
    request = ControlWorkflowsGetRequest.model_validate(request_data)
    return _get_workflow_minimal(workflow_id=request.workflow_id)


def _api_control_workflows_create(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsCreateRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return _create_workflow_minimal(request=payload)


def _api_control_workflows_update(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsUpdateRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return _update_workflow_minimal(request=payload)


async def _api_control_workflows_execute(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsExecuteRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return await _execute_workflow_minimal(request=payload)


def _api_control_workflows_delete(request_data: dict, idempotency_key_header: str | None) -> dict:
    request = ControlWorkflowsDeleteRequest.model_validate(request_data)
    payload = request.model_copy(update={"idempotency_key": request.idempotency_key or idempotency_key_header})
    return _delete_workflow_minimal(request=payload)


def _api_control_runs_get(request_data: dict) -> dict:
    request = ControlRunsGetRequest.model_validate(request_data)
    return _get_run_minimal(run_id=request.run_id)


def _api_control_runs_list(request_data: dict) -> dict:
    request = ControlRunsListRequest.model_validate(request_data)
    return _list_runs_minimal(limit=request.limit, session_id=request.session_id)


def _api_control_runs_events(request_data: dict) -> dict:
    request = ControlRunsEventsRequest.model_validate(request_data)
    return _list_run_events_minimal(run_id=request.run_id, limit=request.limit)


def _api_control_runs_audit(request_data: dict) -> dict:
    request = ControlRunsAuditRequest.model_validate(request_data)
    return _get_run_audit_minimal(run_id=request.run_id)


def _api_control_tools_policy_preview(request_data: dict) -> dict:
    request = ControlToolsPolicyPreviewRequest.model_validate(request_data)
    normalized_tool_policy = _normalize_tool_policy_payload(request.tool_policy)
    return _build_tools_policy_preview(
        agent_id=request.agent_id,
        profile=request.profile,
        preset=request.preset,
        provider=request.provider,
        model=request.model,
        tool_policy=normalized_tool_policy,
        also_allow=request.also_allow,
    )


async def _api_control_policy_approvals_pending(request_data: dict) -> dict:
    request = ControlPolicyApprovalsPendingRequest.model_validate(request_data)
    items = await policy_approval_service.list_pending(
        run_id=request.run_id,
        session_id=request.session_id,
        limit=request.limit,
    )
    return {
        "schema": "policy.approvals.pending.v1",
        "items": items,
        "count": len(items),
    }


async def _api_control_policy_approvals_allow(request_data: dict) -> dict:
    request = ControlPolicyApprovalsAllowRequest.model_validate(request_data)
    updated = await policy_approval_service.allow(request.approval_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "schema": "policy.approvals.allow.v1",
        "approval": updated,
    }


async def _api_control_policy_approvals_decide(request_data: dict) -> dict:
    request = ControlPolicyApprovalsDecideRequest.model_validate(request_data)
    normalized_decision = (request.decision or "").strip().lower()
    if normalized_decision not in {"allow_once", "allow_always", "deny"}:
        raise HTTPException(status_code=400, detail="Unsupported policy approval decision")

    try:
        updated = await policy_approval_service.decide(
            request.approval_id,
            normalized_decision,
            scope=request.scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "schema": "policy.approvals.decide.v1",
        "approval": updated,
    }


include_control_routers(
    app,
    run_start_handler=_api_control_run_start,
    run_wait_handler=_api_control_run_wait,
    agent_run_handler=_api_control_agent_run,
    agent_wait_handler=_api_control_agent_wait,
    runs_get_handler=_api_control_runs_get,
    runs_list_handler=_api_control_runs_list,
    runs_events_handler=_api_control_runs_events,
    runs_audit_handler=_api_control_runs_audit,
    policy_approvals_pending_handler=_api_control_policy_approvals_pending,
    policy_approvals_allow_handler=_api_control_policy_approvals_allow,
    policy_approvals_decide_handler=_api_control_policy_approvals_decide,
    sessions_list_handler=_api_control_sessions_list,
    sessions_resolve_handler=_api_control_sessions_resolve,
    sessions_history_handler=_api_control_sessions_history,
    sessions_send_handler=_api_control_sessions_send,
    sessions_spawn_handler=_api_control_sessions_spawn,
    sessions_status_handler=_api_control_sessions_status,
    sessions_get_handler=_api_control_sessions_get,
    sessions_patch_handler=_api_control_sessions_patch,
    sessions_reset_handler=_api_control_sessions_reset,
    workflows_list_handler=_api_control_workflows_list,
    workflows_get_handler=_api_control_workflows_get,
    workflows_create_handler=_api_control_workflows_create,
    workflows_update_handler=_api_control_workflows_update,
    workflows_execute_handler=_api_control_workflows_execute,
    workflows_delete_handler=_api_control_workflows_delete,
    tools_catalog_handler=_api_control_tools_catalog,
    tools_profile_handler=_api_control_tools_profile,
    tools_policy_matrix_handler=_api_control_tools_policy_matrix,
    tools_policy_preview_handler=_api_control_tools_policy_preview,
    skills_list_handler=_api_control_skills_list,
    skills_preview_handler=_api_control_skills_preview,
    skills_check_handler=_api_control_skills_check,
    skills_sync_handler=_api_control_skills_sync,
)


app.include_router(
    build_runtime_debug_router(
        runtime_status_handler=lambda: api_runtime_status(_runtime_debug_dependencies),
        resolved_prompts_handler=lambda: api_resolved_prompt_settings(_runtime_debug_dependencies),
        ping_handler=lambda: api_test_ping(_runtime_debug_dependencies),
    )
)


app.include_router(
    build_subruns_router(
        subruns_list_handler=lambda parent_session_id, parent_request_id, requester_session_id, visibility_scope, limit: api_subruns_list(
            parent_session_id=parent_session_id,
            parent_request_id=parent_request_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            limit=limit,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_get_handler=lambda run_id, requester_session_id, visibility_scope: api_subruns_get(
            run_id=run_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_log_handler=lambda run_id, requester_session_id, visibility_scope: api_subruns_log(
            run_id=run_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_kill_handler=lambda run_id, requester_session_id, visibility_scope, cascade: api_subruns_kill(
            run_id=run_id,
            requester_session_id=requester_session_id,
            visibility_scope=visibility_scope,
            cascade=cascade,
            deps=_subrun_endpoint_dependencies,
        ),
        subrun_kill_all_handler=lambda request_data: api_subruns_kill_all_async(
            request_data,
            _subrun_endpoint_dependencies,
        ),
    )
)


ws_handler_dependencies = WsHandlerDependencies(
    logger=logger,
    settings=settings,
    agent=agent,
    agent_registry=agent_registry,
    runtime_manager=runtime_manager,
    state_store=state_store,
    subrun_lane=subrun_lane,
    sync_custom_agents=_sync_custom_agents,
    normalize_agent_id=_normalize_agent_id,
    effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
    looks_like_review_request=_looks_like_review_request,
    looks_like_coding_request=_looks_like_coding_request,
    resolve_agent=_resolve_agent,
    state_append_event_safe=_state_append_event_safe,
    state_mark_failed_safe=_state_mark_failed_safe,
    state_mark_completed_safe=_state_mark_completed_safe,
    lifecycle_status_from_stage=_lifecycle_status_from_stage,
    primary_agent_id=PRIMARY_AGENT_ID,
    coder_agent_id=CODER_AGENT_ID,
    review_agent_id=REVIEW_AGENT_ID,
)

app.include_router(build_ws_agent_router(dependencies=ws_handler_dependencies))
