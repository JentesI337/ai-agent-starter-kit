from __future__ import annotations
import logging
from collections.abc import MutableMapping
from app.agents.head_agent_adapter import CoderAgentAdapter, HeadAgentAdapter, ReviewAgentAdapter
from app.app_setup import build_fastapi_app, build_lifespan_context
from app.app_state import ControlPlaneState, LazyMappingProxy, LazyObjectProxy, LazyRuntimeRegistry, RuntimeComponents
from app.config import resolved_prompt_settings, settings
from app.control_router_wiring import include_control_routers
from app.contracts.agent_contract import AgentContract
from app.custom_agents import CustomAgentStore
from app.errors import GuardrailViolation
from app.handlers import (
    agent_handlers,
    policy_handlers,
    run_handlers,
    session_handlers,
    skills_handlers,
    tools_handlers,
    workflow_handlers,
)
from app.interfaces import OrchestratorApi
from app.control_models import AgentTestRequest, RunStartRequest
from app.orchestrator.subrun_lane import SubrunLane
from app.routers import (
    build_agents_router,
    build_run_api_router,
    build_runtime_debug_router,
    build_subruns_router,
    build_ws_agent_router,
)
from app.routers.run_api import RunApiRouterHandlers
from app.run_endpoints import (
    AgentTestDependencies,
    RunEndpointsDependencies,
    run_agent_test,
    start_run as run_endpoint_start,
    wait_run as run_endpoint_wait,
)
from app.runtime_debug_endpoints import (
    RuntimeDebugDependencies,
    api_resolved_prompt_settings,
    api_runtime_status,
    api_test_ping,
)
from app.runtime_manager import RuntimeManager
from app.services import (
    PolicyApprovalService,
    SessionQueryService,
    build_run_start_fingerprint as _build_run_start_fingerprint,
    build_session_patch_fingerprint as _build_session_patch_fingerprint,
    build_session_reset_fingerprint as _build_session_reset_fingerprint,
    build_workflow_create_fingerprint as _build_workflow_create_fingerprint,
    build_workflow_delete_fingerprint as _build_workflow_delete_fingerprint,
    build_workflow_execute_fingerprint as _build_workflow_execute_fingerprint,
)
from app.services.agent_resolution import (
    effective_orchestrator_agent_ids as _effective_orchestrator_agent_ids_impl,
    looks_like_coding_request,
    normalize_agent_id as _normalize_agent_id_impl,
    resolve_agent as _resolve_agent_impl,
    sync_custom_agents as _sync_custom_agents_impl,
)
from app.services.idempotency_manager import IdempotencyManager
from app.services.request_normalization import normalize_preset
from app.startup_tasks import run_shutdown_sequence, run_startup_sequence
from app.state import SqliteStateStore, StateStore
from app.subrun_endpoints import (
    SubrunEndpointsDependencies,
    api_subruns_get,
    api_subruns_kill,
    api_subruns_kill_all_async,
    api_subruns_list,
    api_subruns_log,
)
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
control_plane_state = ControlPlaneState()
idempotency_mgr = IdempotencyManager(
    ttl_seconds=settings.idempotency_registry_ttl_seconds,
    max_entries=settings.idempotency_registry_max_entries,
)
def _startup_sequence() -> None:
    run_startup_sequence(
        settings=settings,
        logger=logger,
        ensure_runtime_components_initialized=_ensure_runtime_components_initialized,
    )
def _shutdown_sequence() -> None:
    run_shutdown_sequence(active_run_tasks=control_plane_state.active_run_tasks, logger=logger)
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
        tool_policy,
        send_event,
        agent_id: str,
        mode: str,
    ) -> str:
        _sync_custom_agents(components)
        runtime_state = components.runtime_manager.get_state()
        selected_model = (model or "").strip() or runtime_state.model
        if runtime_state.runtime == "local":
            selected_model = await components.runtime_manager.ensure_model_ready(send_event, parent_session_id, selected_model)
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
        if await components.policy_approval_service.is_preapproved(tool=tool, resource=resource, session_id=session_id):
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
_runtime_registry = LazyRuntimeRegistry(builder=_build_runtime_components, initializer=_initialize_runtime_components)
def _get_runtime_components() -> RuntimeComponents:
    return _runtime_registry.get_components()
def _ensure_runtime_components_initialized() -> RuntimeComponents:
    return _runtime_registry.ensure_initialized()
agent_registry: MutableMapping[str, AgentContract] = LazyMappingProxy(lambda: _get_runtime_components().agent_registry)
runtime_manager = LazyObjectProxy(lambda: _get_runtime_components().runtime_manager)
state_store = LazyObjectProxy(lambda: _get_runtime_components().state_store)
session_query_service = LazyObjectProxy(lambda: _get_runtime_components().session_query_service)
policy_approval_service = LazyObjectProxy(lambda: _get_runtime_components().policy_approval_service)
orchestrator_registry: MutableMapping[str, OrchestratorApi] = LazyMappingProxy(lambda: _get_runtime_components().orchestrator_registry)
custom_agent_store = LazyObjectProxy(lambda: _get_runtime_components().custom_agent_store)
agent = LazyObjectProxy(lambda: _get_runtime_components().agent)
orchestrator_api = LazyObjectProxy(lambda: _get_runtime_components().orchestrator_api)
subrun_lane = LazyObjectProxy(lambda: _get_runtime_components().subrun_lane)
def _normalize_agent_id(agent_id: str | None) -> str:
    return _normalize_agent_id_impl(
        agent_id,
        primary_agent_id=PRIMARY_AGENT_ID,
        legacy_agent_aliases=LEGACY_AGENT_ALIASES,
    )
def _effective_orchestrator_agent_ids(components: RuntimeComponents | None = None) -> set[str]:
    if components is None:
        components = _get_runtime_components()
    return _effective_orchestrator_agent_ids_impl(
        configured_agent_ids=settings.subrun_orchestrator_agent_ids,
        primary_agent_id=PRIMARY_AGENT_ID,
        custom_orchestrator_agent_ids=components.custom_orchestrator_agent_ids,
    )
def _sync_custom_agents(components: RuntimeComponents | None = None) -> None:
    if components is None:
        components = _get_runtime_components()
    _sync_custom_agents_impl(
        components=components,
        normalize_agent_id_fn=_normalize_agent_id,
        primary_agent_id=PRIMARY_AGENT_ID,
        coder_agent_id=CODER_AGENT_ID,
        review_agent_id=REVIEW_AGENT_ID,
        effective_orchestrator_agent_ids_fn=_effective_orchestrator_agent_ids,
    )
def _resolve_agent(agent_id: str | None):
    return _resolve_agent_impl(
        agent_id=agent_id,
        sync_custom_agents_fn=_sync_custom_agents,
        normalize_agent_id_fn=_normalize_agent_id,
        agent_registry=agent_registry,
        orchestrator_registry=orchestrator_registry,
    )
def _looks_like_review_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    review_keywords = (
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
    if not any(marker in text for marker in review_keywords):
        return False

    evidence_patterns = (
        r"https?://",
        r"```",
        r"diff\s+--git",
        r"\b[a-f0-9]{7,40}\b",
        r"\b[\w./-]+\.(py|ts|js|java|go|rs|json|yml|yaml|md|html|css)\b",
        r"\b(\+\+\+|---|@@)\b",
    )
    has_evidence = any(re.search(pattern, text, re.IGNORECASE) for pattern in evidence_patterns)
    if not has_evidence:
        return False

    execution_or_research_markers = (
        "orchestrate",
        "research",
        "fact check",
        "fact-check",
        "write",
        "save",
        "create",
        "build",
        "implement",
        "run",
        "execute",
        "generate",
    )
    if any(marker in text for marker in execution_or_research_markers):
        return False

    return True
tools_handlers.configure(
    tools_handlers.ToolsHandlerDependencies(
        sync_custom_agents=_sync_custom_agents,
        normalize_agent_id=_normalize_agent_id,
        resolve_agent=_resolve_agent,
        effective_orchestrator_agent_ids=lambda: _effective_orchestrator_agent_ids(),
        agent_registry=agent_registry,
    )
)
run_handlers.configure(
    run_handlers.RunHandlerDependencies(
        logger=logger,
        settings=settings,
        runtime_manager=runtime_manager,
        state_store=state_store,
        agent=agent,
        active_run_tasks=control_plane_state.active_run_tasks,
        idempotency_mgr=idempotency_mgr,
        resolve_agent=_resolve_agent,
        effective_orchestrator_agent_ids=lambda: _effective_orchestrator_agent_ids(),
        build_run_start_fingerprint=_build_run_start_fingerprint,
        extract_also_allow=tools_handlers.extract_also_allow,
    )
)
session_handlers.configure(
    session_handlers.SessionHandlerDependencies(
        runtime_manager=runtime_manager,
        state_store=state_store,
        session_query_service=session_query_service,
        idempotency_mgr=idempotency_mgr,
        build_run_start_fingerprint=_build_run_start_fingerprint,
        build_session_patch_fingerprint=_build_session_patch_fingerprint,
        build_session_reset_fingerprint=_build_session_reset_fingerprint,
        start_run_background=run_handlers.start_run_background,
    )
)
workflow_handlers.configure(
    workflow_handlers.WorkflowHandlerDependencies(
        settings=settings,
        custom_agent_store=custom_agent_store,
        agent_registry=agent_registry,
        idempotency_mgr=idempotency_mgr,
        runtime_manager=runtime_manager,
        subrun_lane=subrun_lane,
        workflow_version_registry=control_plane_state.workflow_version_registry,
        workflow_version_lock=control_plane_state.workflow_version_lock,
        normalize_agent_id=_normalize_agent_id,
        resolve_agent=_resolve_agent,
        sync_custom_agents=_sync_custom_agents,
        effective_orchestrator_agent_ids=lambda: _effective_orchestrator_agent_ids(),
        start_run_background=run_handlers.start_run_background,
        build_workflow_create_fingerprint=_build_workflow_create_fingerprint,
        build_workflow_execute_fingerprint=_build_workflow_execute_fingerprint,
        build_workflow_delete_fingerprint=_build_workflow_delete_fingerprint,
    )
)
policy_handlers.configure(policy_handlers.PolicyHandlerDependencies(policy_approval_service=policy_approval_service))
skills_handlers.configure(skills_handlers.SkillsHandlerDependencies())
agent_handlers.configure(
    agent_handlers.AgentHandlerDependencies(
        runtime_manager=runtime_manager,
        agent_registry=agent_registry,
        custom_agent_store=custom_agent_store,
        sync_custom_agents=_sync_custom_agents,
        normalize_agent_id=_normalize_agent_id,
        get_agent_tools=tools_handlers.get_agent_tools,
        primary_agent_id=PRIMARY_AGENT_ID,
        coder_agent_id=CODER_AGENT_ID,
        review_agent_id=REVIEW_AGENT_ID,
    )
)
app.include_router(
    build_agents_router(
        agents_list_handler=agent_handlers.api_agents_list,
        presets_list_handler=agent_handlers.api_presets_list,
        custom_agents_list_handler=agent_handlers.api_custom_agents_list,
        custom_agents_create_handler=agent_handlers.api_custom_agents_create,
        custom_agents_delete_handler=agent_handlers.api_custom_agents_delete,
        monitoring_schema_handler=agent_handlers.api_monitoring_schema,
    )
)
_agent_test_dependencies = AgentTestDependencies(
    logger=logger,
    runtime_manager=runtime_manager,
    state_store=state_store,
    agent=agent,
    orchestrator_api=orchestrator_api,
    normalize_preset=normalize_preset,
    extract_also_allow=tools_handlers.extract_also_allow,
    effective_orchestrator_agent_ids=lambda: _effective_orchestrator_agent_ids(),
    mark_completed=run_handlers.state_mark_completed_safe,
    mark_failed=run_handlers.state_mark_failed_safe,
    primary_agent_id=PRIMARY_AGENT_ID,
)
_run_endpoint_dependencies = RunEndpointsDependencies(
    start_run_background=run_handlers.start_run_background,
    wait_for_run_result=run_handlers.wait_for_run_result,
)
_runtime_debug_dependencies = RuntimeDebugDependencies(
    runtime_manager=runtime_manager,
    settings=settings,
    resolved_prompt_settings=resolved_prompt_settings,
)
_subrun_endpoint_dependencies = SubrunEndpointsDependencies(
    subrun_lane=subrun_lane,
    session_visibility_default=settings.session_visibility_default,
    state_append_event_safe=run_handlers.state_append_event_safe,
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
include_control_routers(
    app,
    run_start_handler=run_handlers.api_control_run_start,
    run_wait_handler=run_handlers.api_control_run_wait,
    agent_run_handler=run_handlers.api_control_agent_run,
    agent_wait_handler=run_handlers.api_control_agent_wait,
    runs_get_handler=run_handlers.api_control_runs_get,
    runs_list_handler=run_handlers.api_control_runs_list,
    runs_events_handler=run_handlers.api_control_runs_events,
    runs_audit_handler=run_handlers.api_control_runs_audit,
    policy_approvals_pending_handler=policy_handlers.api_control_policy_approvals_pending,
    policy_approvals_allow_handler=policy_handlers.api_control_policy_approvals_allow,
    policy_approvals_decide_handler=policy_handlers.api_control_policy_approvals_decide,
    sessions_list_handler=session_handlers.api_control_sessions_list,
    sessions_resolve_handler=session_handlers.api_control_sessions_resolve,
    sessions_history_handler=session_handlers.api_control_sessions_history,
    sessions_send_handler=session_handlers.api_control_sessions_send,
    sessions_spawn_handler=session_handlers.api_control_sessions_spawn,
    sessions_status_handler=session_handlers.api_control_sessions_status,
    sessions_get_handler=session_handlers.api_control_sessions_get,
    sessions_patch_handler=session_handlers.api_control_sessions_patch,
    sessions_reset_handler=session_handlers.api_control_sessions_reset,
    workflows_list_handler=workflow_handlers.api_control_workflows_list,
    workflows_get_handler=workflow_handlers.api_control_workflows_get,
    workflows_create_handler=workflow_handlers.api_control_workflows_create,
    workflows_update_handler=workflow_handlers.api_control_workflows_update,
    workflows_execute_handler=workflow_handlers.api_control_workflows_execute,
    workflows_delete_handler=workflow_handlers.api_control_workflows_delete,
    tools_catalog_handler=tools_handlers.api_control_tools_catalog,
    tools_profile_handler=tools_handlers.api_control_tools_profile,
    tools_policy_matrix_handler=tools_handlers.api_control_tools_policy_matrix,
    tools_policy_preview_handler=tools_handlers.api_control_tools_policy_preview,
    skills_list_handler=skills_handlers.api_control_skills_list,
    skills_preview_handler=skills_handlers.api_control_skills_preview,
    skills_check_handler=skills_handlers.api_control_skills_check,
    skills_sync_handler=skills_handlers.api_control_skills_sync,
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
        subrun_kill_all_handler=lambda request_data: api_subruns_kill_all_async(request_data, _subrun_endpoint_dependencies),
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
    effective_orchestrator_agent_ids=lambda: _effective_orchestrator_agent_ids(),
    looks_like_review_request=_looks_like_review_request,
    looks_like_coding_request=looks_like_coding_request,
    resolve_agent=_resolve_agent,
    state_append_event_safe=run_handlers.state_append_event_safe,
    state_mark_failed_safe=run_handlers.state_mark_failed_safe,
    state_mark_completed_safe=run_handlers.state_mark_completed_safe,
    lifecycle_status_from_stage=run_handlers.lifecycle_status_from_stage,
    primary_agent_id=PRIMARY_AGENT_ID,
    coder_agent_id=CODER_AGENT_ID,
    review_agent_id=REVIEW_AGENT_ID,
)
app.include_router(build_ws_agent_router(dependencies=ws_handler_dependencies))
