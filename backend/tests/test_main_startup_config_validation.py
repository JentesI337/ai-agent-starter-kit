from __future__ import annotations

import pytest

import app.transport.runtime_wiring as runtime_wiring


def test_startup_sequence_raises_on_strict_unknown_key_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    startup_called = {"value": False}

    def _fake_validate(_settings):
        return {
            "is_valid": False,
            "validation_status": "error",
            "unknown_keys": ["CONFIG_FAKE_UNKNOWN"],
            "strict_mode": True,
        }

    def _fake_startup_sequence(*, settings, logger, ensure_runtime_components_initialized):
        _ = settings
        _ = logger
        _ = ensure_runtime_components_initialized
        startup_called["value"] = True

    monkeypatch.setattr(runtime_wiring, "validate_environment_config", _fake_validate)
    monkeypatch.setattr(runtime_wiring, "run_startup_sequence", _fake_startup_sequence)

    with pytest.raises(RuntimeError) as exc:
        runtime_wiring._startup_sequence()

    assert "Strict config validation failed" in str(exc.value)
    assert startup_called["value"] is False


def test_startup_sequence_continues_on_warning_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    startup_called = {"value": False}

    def _fake_validate(_settings):
        return {
            "is_valid": True,
            "validation_status": "warning",
            "unknown_keys": ["CONFIG_FAKE_UNKNOWN"],
            "strict_mode": False,
        }

    def _fake_startup_sequence(*, settings, logger, ensure_runtime_components_initialized):
        _ = settings
        _ = logger
        _ = ensure_runtime_components_initialized
        startup_called["value"] = True

    monkeypatch.setattr(runtime_wiring, "validate_environment_config", _fake_validate)
    monkeypatch.setattr(runtime_wiring, "run_startup_sequence", _fake_startup_sequence)

    runtime_wiring._startup_sequence()

    assert startup_called["value"] is True
