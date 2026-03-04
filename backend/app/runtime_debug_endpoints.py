from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable

from app.config import BACKEND_DIR


@dataclass(frozen=True)
class RuntimeDebugDependencies:
    runtime_manager: Any
    settings: Any
    resolved_prompt_settings: Callable[[Any], dict]


BACKEND_ENV_FILE = Path(BACKEND_DIR) / ".env"
RUNTIME_FEATURE_ENV_MAP: dict[str, str] = {
    "LONG_TERM_MEMORY_ENABLED": "long_term_memory_enabled",
    "SESSION_DISTILLATION_ENABLED": "session_distillation_enabled",
    "FAILURE_JOURNAL_ENABLED": "failure_journal_enabled",
}


def _upsert_env_line(lines: list[str], env_name: str, env_value: str) -> list[str]:
    pattern = re.compile(rf"^\s*{re.escape(env_name)}=")
    updated: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            if not replaced:
                updated.append(f"{env_name}={env_value}")
                replaced = True
            continue
        updated.append(line)

    if not replaced:
        updated.append(f"{env_name}={env_value}")
    return updated


def _persist_feature_flags_to_backend_env(feature_flags: dict[str, bool]) -> None:
    BACKEND_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if BACKEND_ENV_FILE.exists():
        existing_lines = BACKEND_ENV_FILE.read_text(encoding="utf-8-sig").splitlines()
    else:
        existing_lines = []

    updated_lines = list(existing_lines)
    for env_name, feature_key in RUNTIME_FEATURE_ENV_MAP.items():
        env_value = "true" if bool(feature_flags.get(feature_key, False)) else "false"
        updated_lines = _upsert_env_line(updated_lines, env_name, env_value)

    output = "\n".join(updated_lines).rstrip("\n") + "\n"
    temp_file = BACKEND_ENV_FILE.with_suffix(".env.tmp")
    temp_file.write_text(output, encoding="utf-8")
    temp_file.replace(BACKEND_ENV_FILE)


async def api_runtime_status(deps: RuntimeDebugDependencies) -> dict:
    state = deps.runtime_manager.get_state()
    api_models = await deps.runtime_manager.get_api_models_summary()
    return {
        "runtime": state.runtime,
        "baseUrl": state.base_url,
        "model": state.model,
        "authenticated": deps.runtime_manager.is_runtime_authenticated(),
        "apiSupportedModels": deps.settings.api_supported_models,
        "apiModelsAvailable": api_models["available"],
        "apiModelsCount": api_models["count"],
        "apiModelsError": api_models["error"],
        "featureFlags": deps.runtime_manager.get_feature_flags(),
    }


def api_runtime_features(deps: RuntimeDebugDependencies) -> dict:
    return {
        "featureFlags": deps.runtime_manager.get_feature_flags(),
    }


def api_runtime_update_features(deps: RuntimeDebugDependencies, payload: dict[str, Any]) -> dict:
    raw_feature_flags = payload.get("featureFlags")
    if not isinstance(raw_feature_flags, dict):
        raise ValueError("featureFlags must be an object")

    updated = deps.runtime_manager.update_feature_flags(raw_feature_flags)
    _persist_feature_flags_to_backend_env(updated)
    return {
        "ok": True,
        "persisted": True,
        "featureFlags": updated,
    }


def api_resolved_prompt_settings(deps: RuntimeDebugDependencies) -> dict:
    return {
        "prompts": deps.resolved_prompt_settings(deps.settings),
    }


def api_test_ping(deps: RuntimeDebugDependencies) -> dict:
    state = deps.runtime_manager.get_state()
    return {
        "ok": True,
        "service": "backend",
        "runtime": state.runtime,
        "model": state.model,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
