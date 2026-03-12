"""Configuration domain — loaded by all modules, imports nothing from domains."""
from app.config.settings import *  # noqa: F401, F403
# Explicit re-exports for the most common symbols
from app.config.settings import (
    APP_DIR,
    BACKEND_DIR,
    DEFAULT_WORKSPACE_ROOT,
    Settings,
    settings,
    resolved_prompt_settings,
    validate_environment_config,
    load_cognitive_framework,
    _parse_bool_env,
    _default_reset_on_startup,
    _resolve_prompt,
    _resolve_path_from_workspace,
    _resolve_workspace_root,
)
from app.config.service import init_config_service
