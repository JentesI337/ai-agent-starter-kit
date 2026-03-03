from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeDebugDependencies:
    runtime_manager: Any
    settings: Any
    resolved_prompt_settings: Callable[[Any], dict]


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
