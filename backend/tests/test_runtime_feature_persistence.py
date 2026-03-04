from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.runtime_debug_endpoints import RuntimeDebugDependencies, api_runtime_update_features


@dataclass
class _DummyRuntimeManager:
    feature_flags: dict[str, bool]

    def get_feature_flags(self) -> dict[str, bool]:
        return dict(self.feature_flags)

    def update_feature_flags(self, updates: dict[str, object]) -> dict[str, bool]:
        for key, value in updates.items():
            self.feature_flags[key] = bool(value)
        return dict(self.feature_flags)


def test_runtime_feature_update_persists_to_env_file(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_BASE_URL=http://localhost:11434/v1\nLONG_TERM_MEMORY_ENABLED=true\n", encoding="utf-8")

    manager = _DummyRuntimeManager(
        feature_flags={
            "long_term_memory_enabled": True,
            "session_distillation_enabled": True,
            "failure_journal_enabled": True,
            "vision_enabled": False,
        }
    )
    deps = RuntimeDebugDependencies(runtime_manager=manager, settings=None, resolved_prompt_settings=lambda _: {})

    import app.runtime_debug_endpoints as runtime_debug_endpoints

    monkeypatch.setattr(runtime_debug_endpoints, "BACKEND_ENV_FILE", env_file)

    response = api_runtime_update_features(
        deps,
        {
            "featureFlags": {
                "long_term_memory_enabled": False,
                "session_distillation_enabled": False,
                "failure_journal_enabled": True,
                "vision_enabled": True,
            }
        },
    )

    assert response["ok"] is True
    assert response["persisted"] is True
    assert response["featureFlags"]["long_term_memory_enabled"] is False
    assert response["featureFlags"]["session_distillation_enabled"] is False
    assert response["featureFlags"]["failure_journal_enabled"] is True
    assert response["featureFlags"]["vision_enabled"] is True

    content = env_file.read_text(encoding="utf-8")
    assert "LLM_BASE_URL=http://localhost:11434/v1" in content
    assert "LONG_TERM_MEMORY_ENABLED=false" in content
    assert "SESSION_DISTILLATION_ENABLED=false" in content
    assert "FAILURE_JOURNAL_ENABLED=true" in content
    assert "VISION_ENABLED=true" in content


def test_runtime_feature_update_persists_long_term_memory_db_path(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LONG_TERM_MEMORY_ENABLED=true\n", encoding="utf-8")

    manager = _DummyRuntimeManager(
        feature_flags={
            "long_term_memory_enabled": True,
            "session_distillation_enabled": True,
            "failure_journal_enabled": True,
            "vision_enabled": False,
        }
    )

    settings = type("_Settings", (), {})()
    settings.workspace_root = str(tmp_path)
    settings.long_term_memory_enabled = True
    settings.session_distillation_enabled = True
    settings.failure_journal_enabled = True
    settings.vision_enabled = False
    settings.long_term_memory_db_path = str(tmp_path / "memory_store" / "long_term.db")

    deps = RuntimeDebugDependencies(runtime_manager=manager, settings=settings, resolved_prompt_settings=lambda _: {})

    import app.runtime_debug_endpoints as runtime_debug_endpoints

    monkeypatch.setattr(runtime_debug_endpoints, "BACKEND_ENV_FILE", env_file)

    response = api_runtime_update_features(
        deps,
        {
            "featureFlags": {
                "long_term_memory_enabled": True,
            },
            "longTermMemoryDbPath": "memory_store/override.db",
        },
    )

    assert response["ok"] is True
    assert response["longTermMemoryDbPath"].endswith(str(Path("memory_store") / "override.db"))
    assert settings.long_term_memory_db_path.endswith(str(Path("memory_store") / "override.db"))

    content = env_file.read_text(encoding="utf-8")
    assert "LONG_TERM_MEMORY_DB_PATH=memory_store/override.db" in content


def test_runtime_feature_update_rejects_db_path_outside_workspace(tmp_path) -> None:
    manager = _DummyRuntimeManager(
        feature_flags={
            "long_term_memory_enabled": True,
            "session_distillation_enabled": True,
            "failure_journal_enabled": True,
            "vision_enabled": False,
        }
    )

    settings = type("_Settings", (), {})()
    settings.workspace_root = str(tmp_path)
    settings.long_term_memory_enabled = True
    settings.session_distillation_enabled = True
    settings.failure_journal_enabled = True
    settings.vision_enabled = False
    settings.long_term_memory_db_path = str(tmp_path / "memory_store" / "long_term.db")

    deps = RuntimeDebugDependencies(runtime_manager=manager, settings=settings, resolved_prompt_settings=lambda _: {})

    with pytest.raises(ValueError, match="must stay inside workspace root"):
        api_runtime_update_features(
            deps,
            {
                "featureFlags": {},
                "longTermMemoryDbPath": "../outside/unsafe.db",
            },
        )
