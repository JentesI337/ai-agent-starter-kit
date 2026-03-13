"""Router registration — mounts all routers onto the FastAPI app.

Extracted from main.py (Phase 16).  Called once at application startup
after handler_wiring.configure_all_handlers() has run.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.agent.factory_defaults import CODER_AGENT_ID, PRIMARY_AGENT_ID, REVIEW_AGENT_ID
from app.app_state import LazyObjectProxy
from app.config import resolved_prompt_settings, settings
from app.control_models import AgentTestRequest, RunStartRequest
from app.control_router_wiring import include_control_routers
from app.transport.routers import agents as agent_handlers
from app.transport.routers import integrations as integration_handlers
from app.transport.routers import policies as policy_handlers
from app.transport.routers import runs as run_handlers
from app.transport.routers import sessions as session_handlers
from app.transport.routers import skills as skills_handlers
from app.transport.routers import tools as tools_handlers
from app.transport.routers.agents import (
    handle_agents_config_get,
    handle_agents_config_list,
    handle_agents_config_reset,
    handle_agents_config_update,
)
from app.transport.routers.audio_deps import (
    handle_deps_check,
    handle_deps_install,
)
from app.transport.routers.config import (
    handle_config_diff,
    handle_config_get,
    handle_config_reset,
    handle_config_sections,
    handle_config_update,
)
from app.transport.routers.config import (
    handle_execution_config_get,
    handle_execution_config_update,
    handle_execution_loop_detection_get,
    handle_execution_loop_detection_update,
)
from app.transport.routers.tools import (
    handle_tools_config_get,
    handle_tools_config_list,
    handle_tools_config_reset,
    handle_tools_config_update,
    handle_tools_security_patterns,
    handle_tools_security_update,
)
from app.policy_store import PolicyStore
from app.transport.routers.agents import build_agents_router
from app.transport.routers.debug import build_runtime_debug_router
from app.transport.routers.runs import build_run_api_router
from app.transport.routers.subruns import build_subruns_router
from app.transport.routers.uploads import build_uploads_router
from app.transport.routers.ws_agent import build_ws_agent_router
from app.transport.routers.runs import RunApiRouterHandlers
from app.transport.routers.policies import build_policies_router
from app.run_endpoints import (
    AgentTestDependencies,
    RunEndpointsDependencies,
    run_agent_test,
    start_run as run_endpoint_start,
    wait_run as run_endpoint_wait,
)
from app.runtime_debug_endpoints import (
    RuntimeDebugDependencies,
    api_calibration_recommendations,
    api_resolved_prompt_settings,
    api_runtime_features,
    api_runtime_status,
    api_runtime_update_features,
    api_test_ping,
    api_tool_telemetry_stats,
)
from app.agent.resolution import looks_like_coding_request
from app.reasoning.request_normalization import normalize_preset
from app.subrun_endpoints import (
    SubrunEndpointsDependencies,
    api_subruns_get,
    api_subruns_kill,
    api_subruns_kill_all_async,
    api_subruns_list,
    api_subruns_log,
)
from app.workflows import handlers as workflow_handlers
from app.ws_handler import WsHandlerDependencies
from app.transport import runtime_wiring
from app.transport.runtime_wiring import (
    _effective_orchestrator_agent_ids,
    _get_runtime_components,
    _get_tool_telemetry,
    _looks_like_review_request,
    _normalize_agent_id,
    _resolve_agent,
    _route_agent_for_message,
    _sync_custom_agents,
    agent,
    agent_registry,
    orchestrator_api,
    policy_approval_service,
    runtime_manager,
    state_store,
    subrun_lane,
)

logger = logging.getLogger("app.main")


def register_all_routers(app: FastAPI) -> None:
    """Mount every router onto *app*."""
    app.include_router(
        build_agents_router(
            agents_list_handler=agent_handlers.api_agents_list,
            agents_list_enriched_handler=agent_handlers.api_agents_list_enriched,
            agent_detail_handler=agent_handlers.api_agent_detail,
            presets_list_handler=agent_handlers.api_presets_list,
            custom_agents_list_handler=agent_handlers.api_custom_agents_list,
            custom_agents_create_handler=agent_handlers.api_custom_agents_create,
            custom_agents_update_handler=agent_handlers.api_custom_agents_update,
            custom_agents_delete_handler=agent_handlers.api_custom_agents_delete,
            monitoring_schema_handler=agent_handlers.api_monitoring_schema,
            # Unified store endpoints
            agent_patch_handler=agent_handlers.api_agent_patch,
            agent_create_handler=agent_handlers.api_agent_create,
            agent_delete_handler=agent_handlers.api_agent_delete,
            agent_reset_handler=agent_handlers.api_agent_reset,
            manifest_get_handler=agent_handlers.api_manifest_get,
            manifest_update_handler=agent_handlers.api_manifest_update,
            agents_list_unified_handler=agent_handlers.api_agents_list_unified,
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
        effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
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
        model_health_tracker=getattr(_get_runtime_components(), "model_health_tracker", None),
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
        skills_get_handler=skills_handlers.api_control_skill_get,
        skills_create_handler=skills_handlers.api_control_skill_create,
        skills_update_handler=skills_handlers.api_control_skill_update,
        skills_delete_handler=skills_handlers.api_control_skill_delete,
        context_list_handler=tools_handlers.api_control_context_list,
        context_detail_handler=tools_handlers.api_control_context_detail,
        config_health_handler=tools_handlers.api_control_config_health,
        memory_overview_handler=tools_handlers.api_control_memory_overview,
        config_sections_handler=handle_config_sections,
        config_get_handler=handle_config_get,
        config_update_handler=handle_config_update,
        config_diff_handler=handle_config_diff,
        config_reset_handler=handle_config_reset,
        config_deps_check_handler=handle_deps_check,
        config_deps_install_handler=handle_deps_install,
        agents_config_list_handler=handle_agents_config_list,
        agents_config_get_handler=handle_agents_config_get,
        agents_config_update_handler=handle_agents_config_update,
        agents_config_reset_handler=handle_agents_config_reset,
        execution_config_get_handler=handle_execution_config_get,
        execution_config_update_handler=handle_execution_config_update,
        execution_loop_detection_get_handler=handle_execution_loop_detection_get,
        execution_loop_detection_update_handler=handle_execution_loop_detection_update,
        tools_config_list_handler=handle_tools_config_list,
        tools_config_get_handler=handle_tools_config_get,
        tools_config_update_handler=handle_tools_config_update,
        tools_config_reset_handler=handle_tools_config_reset,
        tools_security_patterns_handler=handle_tools_security_patterns,
        tools_security_update_handler=handle_tools_security_update,
        integrations_connectors_list_handler=integration_handlers.handle_connectors_list,
        integrations_connectors_get_handler=integration_handlers.handle_connectors_get,
        integrations_connectors_create_handler=integration_handlers.handle_connectors_create,
        integrations_connectors_update_handler=integration_handlers.handle_connectors_update,
        integrations_connectors_delete_handler=integration_handlers.handle_connectors_delete,
        integrations_connectors_test_handler=integration_handlers.handle_connectors_test,
        integrations_oauth_start_handler=integration_handlers.handle_oauth_start,
        integrations_oauth_callback_handler=integration_handlers.handle_oauth_callback,
        integrations_oauth_status_handler=integration_handlers.handle_oauth_status,
    )
    app.include_router(
        build_runtime_debug_router(
            runtime_status_handler=lambda: api_runtime_status(_runtime_debug_dependencies),
            runtime_features_handler=lambda: api_runtime_features(_runtime_debug_dependencies),
            runtime_update_features_handler=lambda payload: api_runtime_update_features(
                _runtime_debug_dependencies, payload
            ),
            resolved_prompts_handler=lambda: api_resolved_prompt_settings(_runtime_debug_dependencies),
            ping_handler=lambda: api_test_ping(_runtime_debug_dependencies),
            calibration_recommendations_handler=lambda: api_calibration_recommendations(_runtime_debug_dependencies),
            tool_telemetry_handler=lambda: api_tool_telemetry_stats(_get_tool_telemetry()),
        )
    )
    app.include_router(
        build_subruns_router(
            subruns_list_handler=lambda parent_session_id, parent_request_id, requester_session_id, visibility_scope, limit: (
                api_subruns_list(
                    parent_session_id=parent_session_id,
                    parent_request_id=parent_request_id,
                    requester_session_id=requester_session_id,
                    visibility_scope=visibility_scope,
                    limit=limit,
                    deps=_subrun_endpoint_dependencies,
                )
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
                request_data, _subrun_endpoint_dependencies
            ),
        )
    )
    ws_handler_dependencies = WsHandlerDependencies(
        logger=logger,
        settings=settings,
        agent=agent,
        agent_registry=agent_registry,
        runtime_manager=runtime_manager,
        policy_approval_service=policy_approval_service,
        state_store=state_store,
        subrun_lane=subrun_lane,
        sync_custom_agents=_sync_custom_agents,
        normalize_agent_id=_normalize_agent_id,
        effective_orchestrator_agent_ids=_effective_orchestrator_agent_ids,
        looks_like_review_request=_looks_like_review_request,
        looks_like_coding_request=looks_like_coding_request,
        route_agent_for_message=_route_agent_for_message,
        resolve_agent=_resolve_agent,
        state_append_event_safe=run_handlers.state_append_event_safe,
        state_mark_failed_safe=run_handlers.state_mark_failed_safe,
        state_mark_completed_safe=run_handlers.state_mark_completed_safe,
        lifecycle_status_from_stage=run_handlers.lifecycle_status_from_stage,
        primary_agent_id=PRIMARY_AGENT_ID,
        coder_agent_id=CODER_AGENT_ID,
        review_agent_id=REVIEW_AGENT_ID,
        repl_session_manager=LazyObjectProxy(lambda: runtime_wiring._repl_session_manager),
        browser_pool=LazyObjectProxy(lambda: runtime_wiring._browser_pool),
    )
    app.include_router(build_ws_agent_router(dependencies=ws_handler_dependencies))

    # --- Policy CRUD ---
    _policy_store = PolicyStore(persist_dir=settings.policies_dir)
    app.include_router(build_policies_router(policy_store=_policy_store))

    # --- File Uploads ---
    app.include_router(build_uploads_router())

    # --- Webhook Triggers ---
    from app.transport.routers.webhooks import build_webhooks_router
    app.include_router(build_webhooks_router())
