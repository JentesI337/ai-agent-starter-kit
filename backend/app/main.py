"""AI Agent Starter Kit — Application Entry Point."""
from __future__ import annotations

import logging

from app.app_setup import build_fastapi_app, build_lifespan_context
from app.config import settings, validate_environment_config
from app.services.log_secret_filter import install_secret_filter
from app.startup_tasks import run_startup_sequence
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
from app.transport.handler_wiring import configure_all_handlers
from app.transport.router_wiring import register_all_routers

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
    "app",
    "agent",
    "agent_registry",
    "agent_store",
    "custom_agent_store",
    "orchestrator_api",
    "orchestrator_registry",
    "policy_approval_service",
    "runtime_manager",
    "session_query_service",
    "state_store",
    "subrun_lane",
    # Re-exported for test_main_startup_config_validation monkeypatching
    "validate_environment_config",
    "run_startup_sequence",
]
