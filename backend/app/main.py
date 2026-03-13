"""AI Agent Starter Kit — Application Entry Point."""
from __future__ import annotations

import logging

from app.transport.app_factory import build_fastapi_app, build_lifespan_context
from app.config import settings, validate_environment_config
from app.policy.log_secret_filter import install_secret_filter
from app.transport.startup import run_startup_sequence
from app.transport.handler_wiring import configure_all_handlers
from app.transport.router_wiring import register_all_routers
from app.transport.runtime_wiring import (
    _shutdown_sequence,
    _startup_sequence,
    agent,
    agent_registry,
    agent_store,
    custom_agent_store,
    orchestrator_api,
    orchestrator_registry,
    policy_approval_service,
    runtime_manager,
    session_query_service,
    state_store,
    subrun_lane,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
install_secret_filter()

app = build_fastapi_app(title="AI Agent Starter Kit", settings=settings)
app.router.lifespan_context = build_lifespan_context(
    on_startup=_startup_sequence,
    on_shutdown=_shutdown_sequence,
)
configure_all_handlers()
register_all_routers(app)

__all__ = [
    "agent",
    "agent_registry",
    "agent_store",
    "app",
    "custom_agent_store",
    "orchestrator_api",
    "orchestrator_registry",
    "policy_approval_service",
    "run_startup_sequence",
    "runtime_manager",
    "session_query_service",
    "state_store",
    "subrun_lane",
    # Re-exported for test_main_startup_config_validation monkeypatching
    "validate_environment_config",
]
