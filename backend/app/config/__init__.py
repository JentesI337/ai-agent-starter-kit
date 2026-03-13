"""Configuration domain — loaded by all modules, imports nothing from domains."""
from app.config.service import init_config_service
from app.config.settings import *

# Explicit re-exports for the most common symbols
from app.config.settings import (
    APP_DIR,
    BACKEND_DIR,
    DEFAULT_WORKSPACE_ROOT,
    Settings,
    _default_reset_on_startup,
    _parse_bool_env,
    _resolve_path_from_workspace,
    _resolve_prompt,
    _resolve_workspace_root,
    load_cognitive_framework,
    resolved_prompt_settings,
    settings,
    validate_environment_config,
)
