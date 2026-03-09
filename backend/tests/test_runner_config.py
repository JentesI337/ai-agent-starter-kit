"""Unit tests for runner settings in config.py."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure runner env vars dont leak between tests."""
    for key in list(os.environ):
        if key.startswith("RUNNER_") or key == "USE_CONTINUOUS_LOOP":
            monkeypatch.delenv(key, raising=False)


def _load_fresh_settings(**env_overrides):
    """Import Settings fresh with given env overrides."""
    environ_patch = {k: str(v) for k, v in env_overrides.items()}
    saved = {}
    for k, v in environ_patch.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        from app.config import Settings
        return Settings()
    finally:
        for k, orig in saved.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig


class TestRunnerDefaults:
    def test_use_continuous_loop_default_true(self):
        s = _load_fresh_settings()
        assert s.use_continuous_loop is True

    def test_runner_max_iterations_default(self):
        s = _load_fresh_settings()
        assert s.runner_max_iterations == 25

    def test_runner_max_tool_calls_default(self):
        s = _load_fresh_settings()
        assert s.runner_max_tool_calls == 50

    def test_runner_time_budget_seconds_default(self):
        s = _load_fresh_settings()
        assert s.runner_time_budget_seconds == 300

    def test_runner_context_budget_default(self):
        s = _load_fresh_settings()
        assert s.runner_context_budget == 4096

    def test_runner_loop_detection_enabled_default(self):
        s = _load_fresh_settings()
        assert s.runner_loop_detection_enabled is True

    def test_runner_loop_detection_threshold_default(self):
        s = _load_fresh_settings()
        assert s.runner_loop_detection_threshold == 3

    def test_runner_compaction_enabled_default(self):
        s = _load_fresh_settings()
        assert s.runner_compaction_enabled is True

    def test_runner_compaction_tail_keep_default(self):
        s = _load_fresh_settings()
        assert s.runner_compaction_tail_keep == 4

    def test_runner_tool_result_max_chars_default(self):
        s = _load_fresh_settings()
        assert s.runner_tool_result_max_chars == 5000

    def test_runner_reflection_enabled_default(self):
        s = _load_fresh_settings()
        assert s.runner_reflection_enabled is True

    def test_runner_reflection_max_passes_default(self):
        s = _load_fresh_settings()
        assert s.runner_reflection_max_passes == 1


class TestRunnerEnvOverride:
    """Verify that runner settings accept explicit overrides (matching
    the os.getenv pattern used in config.py where env values are read at
    class definition time)."""

    def test_use_continuous_loop_override(self):
        from app.config import Settings
        s = Settings(use_continuous_loop=True)
        assert s.use_continuous_loop is True

    def test_runner_max_iterations_override(self):
        from app.config import Settings
        s = Settings(runner_max_iterations=10)
        assert s.runner_max_iterations == 10

    def test_runner_time_budget_seconds_override(self):
        from app.config import Settings
        s = Settings(runner_time_budget_seconds=120)
        assert s.runner_time_budget_seconds == 120
