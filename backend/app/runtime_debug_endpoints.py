from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable

from app.services.benchmark_calibration import BenchmarkCalibrationService
from app.services.reflection_feedback_store import ReflectionFeedbackStore
from app.config import BACKEND_DIR


@dataclass(frozen=True)
class RuntimeDebugDependencies:
    runtime_manager: Any
    settings: Any
    resolved_prompt_settings: Callable[[Any], dict]
    model_health_tracker: Any | None = None


BACKEND_ENV_FILE = Path(BACKEND_DIR) / ".env"
RUNTIME_FEATURE_ENV_MAP: dict[str, str] = {
    "LONG_TERM_MEMORY_ENABLED": "long_term_memory_enabled",
    "SESSION_DISTILLATION_ENABLED": "session_distillation_enabled",
    "FAILURE_JOURNAL_ENABLED": "failure_journal_enabled",
    "VISION_ENABLED": "vision_enabled",
}
LONG_TERM_MEMORY_DB_PATH_ENV = "LONG_TERM_MEMORY_DB_PATH"


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


def _workspace_root_from_settings(settings_obj: Any) -> Path:
    root = getattr(settings_obj, "workspace_root", None) if settings_obj is not None else None
    if isinstance(root, str) and root.strip():
        return Path(root).resolve()
    return Path(BACKEND_DIR).parent.resolve()


def _normalize_long_term_memory_db_path(
    raw_path: str,
    *,
    workspace_root: Path,
) -> tuple[str, str]:
    candidate = (raw_path or "").strip()
    if not candidate:
        raise ValueError("longTermMemoryDbPath must not be empty")
    if any(token in candidate for token in ("\x00", "\r", "\n")):
        raise ValueError("longTermMemoryDbPath contains unsupported characters")

    path_obj = Path(candidate)
    resolved = (workspace_root / path_obj).resolve() if not path_obj.is_absolute() else path_obj.resolve()
    try:
        relative = resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("longTermMemoryDbPath must stay inside workspace root") from exc

    if resolved.suffix.lower() != ".db":
        raise ValueError("longTermMemoryDbPath must point to a .db file")

    if len(str(resolved)) > 4096:
        raise ValueError("longTermMemoryDbPath is too long")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    return relative.as_posix(), str(resolved)


def _persist_feature_flags_to_backend_env(
    feature_flags: dict[str, bool],
    *,
    long_term_memory_db_path_env: str | None = None,
) -> None:
    BACKEND_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if BACKEND_ENV_FILE.exists():
        existing_lines = BACKEND_ENV_FILE.read_text(encoding="utf-8-sig").splitlines()
    else:
        existing_lines = []

    updated_lines = list(existing_lines)
    for env_name, feature_key in RUNTIME_FEATURE_ENV_MAP.items():
        env_value = "true" if bool(feature_flags.get(feature_key, False)) else "false"
        updated_lines = _upsert_env_line(updated_lines, env_name, env_value)
    if long_term_memory_db_path_env is not None:
        updated_lines = _upsert_env_line(updated_lines, LONG_TERM_MEMORY_DB_PATH_ENV, long_term_memory_db_path_env)

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
        "longTermMemoryDbPath": str(getattr(deps.settings, "long_term_memory_db_path", "")),
    }


def api_runtime_features(deps: RuntimeDebugDependencies) -> dict:
    return {
        "featureFlags": deps.runtime_manager.get_feature_flags(),
        "longTermMemoryDbPath": str(getattr(deps.settings, "long_term_memory_db_path", "")),
    }


def api_runtime_update_features(deps: RuntimeDebugDependencies, payload: dict[str, Any]) -> dict:
    raw_feature_flags = payload.get("featureFlags", {})
    if raw_feature_flags is None:
        raw_feature_flags = {}
    if not isinstance(raw_feature_flags, dict):
        raise ValueError("featureFlags must be an object")
    raw_db_path = payload.get("longTermMemoryDbPath")
    if raw_db_path is not None and not isinstance(raw_db_path, str):
        raise ValueError("longTermMemoryDbPath must be a string")

    previous_flags = deps.runtime_manager.get_feature_flags()

    workspace_root = _workspace_root_from_settings(deps.settings)
    persisted_db_path_env: str | None = None
    effective_db_path = str(getattr(deps.settings, "long_term_memory_db_path", ""))
    if raw_db_path is not None:
        persisted_db_path_env, effective_db_path = _normalize_long_term_memory_db_path(
            raw_db_path,
            workspace_root=workspace_root,
        )

    updated = deps.runtime_manager.update_feature_flags(raw_feature_flags)
    try:
        _persist_feature_flags_to_backend_env(updated, long_term_memory_db_path_env=persisted_db_path_env)
    except Exception:
        deps.runtime_manager.update_feature_flags(previous_flags)
        raise

    if deps.settings is not None:
        setattr(deps.settings, "long_term_memory_enabled", bool(updated.get("long_term_memory_enabled", False)))
        setattr(deps.settings, "session_distillation_enabled", bool(updated.get("session_distillation_enabled", False)))
        setattr(deps.settings, "failure_journal_enabled", bool(updated.get("failure_journal_enabled", False)))
        setattr(deps.settings, "vision_enabled", bool(updated.get("vision_enabled", False)))
        if raw_db_path is not None:
            setattr(deps.settings, "long_term_memory_db_path", effective_db_path)

    return {
        "ok": True,
        "persisted": True,
        "featureFlags": updated,
        "longTermMemoryDbPath": str(getattr(deps.settings, "long_term_memory_db_path", effective_db_path)),
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


def api_calibration_recommendations(deps: RuntimeDebugDependencies) -> dict:
    db_path = str(getattr(deps.settings, "long_term_memory_db_path", "") or "").strip()
    if not db_path:
        return {"recommendations": []}

    reflection_store = ReflectionFeedbackStore(db_path)
    recovery_metrics_path = str(Path(getattr(deps.settings, "orchestrator_state_dir", "")) / "pipeline_recovery_metrics.json")
    service = BenchmarkCalibrationService(
        reflection_feedback_store=reflection_store,
        model_health_tracker=deps.model_health_tracker,
        recovery_metrics_path=recovery_metrics_path,
        min_samples=20,
    )
    recommendations = service.analyze()
    return {
        "recommendations": [
            {
                "parameter": item.parameter,
                "current_value": item.current_value,
                "recommended_value": item.recommended_value,
                "confidence": item.confidence,
                "evidence": item.evidence,
            }
            for item in recommendations
        ],
        "env_patch": service.export_env_patch(recommendations),
    }


def api_tool_telemetry_stats(telemetry: Any) -> dict:
    """L2.6  Return per-tool statistics and session summary.

    *telemetry* is the ``ToolTelemetry`` instance from the
    ``ToolExecutionManager``.
    """
    if telemetry is None:
        return {"summary": {}, "tools": {}, "trace": []}
    return {
        "summary": telemetry.get_summary(),
        "tools": telemetry.get_tool_stats(),
        "trace": telemetry.get_session_trace(last_n=50),
    }
