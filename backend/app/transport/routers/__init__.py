"""Router registration — replaces control_router_wiring.py."""
from __future__ import annotations

from fastapi import FastAPI

from app.transport.routers.agents import (
    build_control_agent_config_router,
)
from app.transport.routers.config import (
    build_control_config_router,
    build_control_execution_config_router,
)
from app.transport.routers.integrations import (
    build_control_integrations_router,
)
from app.transport.routers.policies import (
    build_control_policy_approvals_router,
)
from app.transport.routers.runs import (
    build_control_runs_router,
)
from app.transport.routers.sessions import (
    build_control_sessions_router,
)
from app.transport.routers.tools import (
    build_control_tool_config_router,
    build_control_tools_router,
)
def include_all_routers(
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
    skills_get_handler=None,
    skills_create_handler=None,
    skills_update_handler=None,
    skills_delete_handler=None,
    config_sections_handler=None,
    config_get_handler=None,
    config_update_handler=None,
    config_diff_handler=None,
    config_reset_handler=None,
    agents_config_list_handler=None,
    agents_config_get_handler=None,
    agents_config_update_handler=None,
    agents_config_reset_handler=None,
    execution_config_get_handler=None,
    execution_config_update_handler=None,
    execution_loop_detection_get_handler=None,
    execution_loop_detection_update_handler=None,
    tools_config_list_handler=None,
    tools_config_get_handler=None,
    tools_config_update_handler=None,
    tools_config_reset_handler=None,
    tools_security_patterns_handler=None,
    tools_security_update_handler=None,
    # Integration handlers
    integrations_connectors_list_handler=None,
    integrations_connectors_get_handler=None,
    integrations_connectors_create_handler=None,
    integrations_connectors_update_handler=None,
    integrations_connectors_delete_handler=None,
    integrations_connectors_test_handler=None,
    integrations_oauth_start_handler=None,
    integrations_oauth_callback_handler=None,
    integrations_oauth_status_handler=None,
    # Audio dependency handlers
    config_deps_check_handler=None,
    config_deps_install_handler=None,
) -> None:
    """Register all control routers with the FastAPI application.

    Accepts the same kwargs as the legacy include_control_routers() for
    full backward compatibility.
    """
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
        build_control_tools_router(
            tools_catalog_handler=tools_catalog_handler,
            tools_profile_handler=tools_profile_handler,
            tools_policy_matrix_handler=tools_policy_matrix_handler,
            tools_policy_preview_handler=tools_policy_preview_handler,
            skills_list_handler=skills_list_handler,
            skills_preview_handler=skills_preview_handler,
            skills_check_handler=skills_check_handler,
            skills_sync_handler=skills_sync_handler,
            skills_get_handler=skills_get_handler,
            skills_create_handler=skills_create_handler,
            skills_update_handler=skills_update_handler,
            skills_delete_handler=skills_delete_handler,
            context_list_handler=context_list_handler,
            context_detail_handler=context_detail_handler,
            config_health_handler=config_health_handler,
            memory_overview_handler=memory_overview_handler,
        )
    )

    # R1: Config management router
    if config_sections_handler is not None:
        from app.transport.routers.config import (
            handle_config_diff,
            handle_config_get,
            handle_config_reset,
            handle_config_sections,
            handle_config_update,
        )
        app.include_router(
            build_control_config_router(
                config_sections_handler=config_sections_handler or handle_config_sections,
                config_get_handler=config_get_handler or handle_config_get,
                config_update_handler=config_update_handler or handle_config_update,
                config_diff_handler=config_diff_handler or handle_config_diff,
                config_reset_handler=config_reset_handler or handle_config_reset,
                config_deps_check_handler=config_deps_check_handler,
                config_deps_install_handler=config_deps_install_handler,
            )
        )

    # R2: Agent config management router
    if agents_config_list_handler is not None:
        from app.transport.routers.agents import (
            handle_agents_config_get,
            handle_agents_config_list,
            handle_agents_config_reset,
            handle_agents_config_update,
        )
        app.include_router(
            build_control_agent_config_router(
                agents_config_list_handler=agents_config_list_handler or handle_agents_config_list,
                agents_config_get_handler=agents_config_get_handler or handle_agents_config_get,
                agents_config_update_handler=agents_config_update_handler or handle_agents_config_update,
                agents_config_reset_handler=agents_config_reset_handler or handle_agents_config_reset,
            )
        )

    # R3: Tool config and security management router
    if tools_config_list_handler is not None:
        from app.transport.routers.tools import (
            handle_tools_config_get,
            handle_tools_config_list,
            handle_tools_config_reset,
            handle_tools_config_update,
            handle_tools_security_patterns,
            handle_tools_security_update,
        )
        app.include_router(
            build_control_tool_config_router(
                tools_config_list_handler=tools_config_list_handler or handle_tools_config_list,
                tools_config_get_handler=tools_config_get_handler or handle_tools_config_get,
                tools_config_update_handler=tools_config_update_handler or handle_tools_config_update,
                tools_config_reset_handler=tools_config_reset_handler or handle_tools_config_reset,
                tools_security_patterns_handler=tools_security_patterns_handler or handle_tools_security_patterns,
                tools_security_update_handler=tools_security_update_handler or handle_tools_security_update,
            )
        )

    # R4: Execution config management router
    if execution_config_get_handler is not None:
        from app.transport.routers.config import (
            handle_execution_config_get,
            handle_execution_config_update,
            handle_execution_loop_detection_get,
            handle_execution_loop_detection_update,
        )
        app.include_router(
            build_control_execution_config_router(
                execution_config_get_handler=execution_config_get_handler or handle_execution_config_get,
                execution_config_update_handler=execution_config_update_handler or handle_execution_config_update,
                execution_loop_detection_get_handler=execution_loop_detection_get_handler or handle_execution_loop_detection_get,
                execution_loop_detection_update_handler=execution_loop_detection_update_handler or handle_execution_loop_detection_update,
            )
        )

    # R5: Integrations router
    if integrations_connectors_list_handler is not None:
        from app.transport.routers.integrations import (
            handle_connectors_create,
            handle_connectors_delete,
            handle_connectors_get,
            handle_connectors_list,
            handle_connectors_test,
            handle_connectors_update,
            handle_oauth_callback,
            handle_oauth_start,
            handle_oauth_status,
        )
        app.include_router(
            build_control_integrations_router(
                connectors_list_handler=integrations_connectors_list_handler or handle_connectors_list,
                connectors_get_handler=integrations_connectors_get_handler or handle_connectors_get,
                connectors_create_handler=integrations_connectors_create_handler or handle_connectors_create,
                connectors_update_handler=integrations_connectors_update_handler or handle_connectors_update,
                connectors_delete_handler=integrations_connectors_delete_handler or handle_connectors_delete,
                connectors_test_handler=integrations_connectors_test_handler or handle_connectors_test,
                oauth_start_handler=integrations_oauth_start_handler or handle_oauth_start,
                oauth_callback_handler=integrations_oauth_callback_handler or handle_oauth_callback,
                oauth_status_handler=integrations_oauth_status_handler or handle_oauth_status,
            )
        )


# Backward-compat alias
include_control_routers = include_all_routers
