# DEPRECATED: moved to app.transport.routers.* (Phase 15)
from app.transport.routers.agents import build_agents_router, build_control_agent_config_router
from app.transport.routers.config import build_control_config_router, build_control_execution_config_router
from app.transport.routers.integrations import build_control_integrations_router
from app.transport.routers.policies import build_control_policy_approvals_router, build_policies_router
from app.transport.routers.runs import build_control_runs_router, build_run_api_router
from app.transport.routers.sessions import build_control_sessions_router
from app.transport.routers.tools import build_control_tool_config_router, build_control_tools_router
from app.transport.routers.workflows import build_control_workflows_router
from app.transport.routers.debug import build_runtime_debug_router
from app.transport.routers.subruns import build_subruns_router
from app.transport.routers.uploads import build_uploads_router
from app.transport.routers.ws_agent import build_ws_agent_router

__all__ = [
    "build_uploads_router",
    "build_agents_router",
    "build_control_agent_config_router",
    "build_control_config_router",
    "build_control_execution_config_router",
    "build_control_integrations_router",
    "build_control_policy_approvals_router",
    "build_control_runs_router",
    "build_control_sessions_router",
    "build_control_tool_config_router",
    "build_control_tools_router",
    "build_control_workflows_router",
    "build_policies_router",
    "build_run_api_router",
    "build_runtime_debug_router",
    "build_subruns_router",
    "build_ws_agent_router",
]
