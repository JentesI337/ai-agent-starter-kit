from __future__ import annotations

from fastapi import FastAPI

from app.routers import (
    build_control_policy_approvals_router,
    build_control_runs_router,
    build_control_sessions_router,
    build_control_tools_router,
    build_control_workflows_router,
)


def include_control_routers(
    app: FastAPI,
    *,
    run_start_handler,
    run_wait_handler,
    agent_run_handler,
    agent_wait_handler,
    runs_get_handler,
    runs_list_handler,
    runs_events_handler,
    runs_audit_handler,
    policy_approvals_pending_handler,
    policy_approvals_allow_handler,
    policy_approvals_decide_handler,
    sessions_list_handler,
    sessions_resolve_handler,
    sessions_history_handler,
    sessions_send_handler,
    sessions_spawn_handler,
    sessions_status_handler,
    sessions_get_handler,
    sessions_patch_handler,
    sessions_reset_handler,
    workflows_list_handler,
    workflows_get_handler,
    workflows_create_handler,
    workflows_update_handler,
    workflows_execute_handler,
    workflows_delete_handler,
    tools_catalog_handler,
    tools_profile_handler,
    tools_policy_matrix_handler,
    tools_policy_preview_handler,
    skills_list_handler,
    skills_preview_handler,
    skills_check_handler,
    skills_sync_handler,
    context_list_handler,
    context_detail_handler,
    config_health_handler,
    memory_overview_handler,
) -> None:
    app.include_router(
        build_control_runs_router(
            run_start_handler=run_start_handler,
            run_wait_handler=run_wait_handler,
            agent_run_handler=agent_run_handler,
            agent_wait_handler=agent_wait_handler,
            runs_get_handler=runs_get_handler,
            runs_list_handler=runs_list_handler,
            runs_events_handler=runs_events_handler,
            runs_audit_handler=runs_audit_handler,
        )
    )

    app.include_router(
        build_control_policy_approvals_router(
            policy_approvals_pending_handler=policy_approvals_pending_handler,
            policy_approvals_allow_handler=policy_approvals_allow_handler,
            policy_approvals_decide_handler=policy_approvals_decide_handler,
        )
    )

    app.include_router(
        build_control_sessions_router(
            sessions_list_handler=sessions_list_handler,
            sessions_resolve_handler=sessions_resolve_handler,
            sessions_history_handler=sessions_history_handler,
            sessions_send_handler=sessions_send_handler,
            sessions_spawn_handler=sessions_spawn_handler,
            sessions_status_handler=sessions_status_handler,
            sessions_get_handler=sessions_get_handler,
            sessions_patch_handler=sessions_patch_handler,
            sessions_reset_handler=sessions_reset_handler,
        )
    )

    app.include_router(
        build_control_workflows_router(
            workflows_list_handler=workflows_list_handler,
            workflows_get_handler=workflows_get_handler,
            workflows_create_handler=workflows_create_handler,
            workflows_update_handler=workflows_update_handler,
            workflows_execute_handler=workflows_execute_handler,
            workflows_delete_handler=workflows_delete_handler,
        )
    )

    app.include_router(
        build_control_tools_router(
            tools_catalog_handler=tools_catalog_handler,
            tools_profile_handler=tools_profile_handler,
            tools_policy_matrix_handler=tools_policy_matrix_handler,
            tools_policy_preview_handler=tools_policy_preview_handler,
            skills_list_handler=skills_list_handler,
            skills_preview_handler=skills_preview_handler,
            skills_check_handler=skills_check_handler,
            skills_sync_handler=skills_sync_handler,
            context_list_handler=context_list_handler,
            context_detail_handler=context_detail_handler,
            config_health_handler=config_health_handler,
            memory_overview_handler=memory_overview_handler,
        )
    )
