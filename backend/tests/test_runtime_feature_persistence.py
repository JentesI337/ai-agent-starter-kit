from __future__ import annotations

from dataclasses import dataclass

from app.runtime_debug_endpoints import RuntimeDebugDependencies, api_runtime_update_features


@dataclass
class _DummyRuntimeManager:
    feature_flags: dict[str, bool]

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
            }
        },
    )

    assert response["ok"] is True
    assert response["persisted"] is True
    assert response["featureFlags"]["long_term_memory_enabled"] is False
    assert response["featureFlags"]["session_distillation_enabled"] is False
    assert response["featureFlags"]["failure_journal_enabled"] is True

    content = env_file.read_text(encoding="utf-8")
    assert "LLM_BASE_URL=http://localhost:11434/v1" in content
    assert "LONG_TERM_MEMORY_ENABLED=false" in content
    assert "SESSION_DISTILLATION_ENABLED=false" in content
    assert "FAILURE_JOURNAL_ENABLED=true" in content
