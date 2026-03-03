from __future__ import annotations

from app.config import settings, validate_environment_config


def test_validate_environment_config_soft_mode_reports_unknown_keys() -> None:
    payload = validate_environment_config(
        settings,
        environ={
            "APP_ENV": "development",
            "QUEUE_MODE_DEFAULT": "wait",
            "CONFIG_FAKE_UNKNOWN": "1",
        },
        strict_unknown_keys_enabled=False,
        allowlist=[],
    )

    assert payload["is_valid"] is True
    assert payload["validation_status"] == "warning"
    assert "CONFIG_FAKE_UNKNOWN" in payload["unknown_keys"]


def test_validate_environment_config_strict_mode_fails_on_unknown_keys() -> None:
    payload = validate_environment_config(
        settings,
        environ={
            "APP_ENV": "development",
            "QUEUE_MODE_DEFAULT": "wait",
            "CONFIG_FAKE_UNKNOWN": "1",
        },
        strict_unknown_keys_enabled=True,
        allowlist=[],
    )

    assert payload["is_valid"] is False
    assert payload["validation_status"] == "error"
    assert "CONFIG_FAKE_UNKNOWN" in payload["unknown_keys"]


def test_validate_environment_config_allowlist_suppresses_known_unknown_key() -> None:
    payload = validate_environment_config(
        settings,
        environ={
            "APP_ENV": "development",
            "QUEUE_MODE_DEFAULT": "wait",
            "CONFIG_FAKE_UNKNOWN": "1",
        },
        strict_unknown_keys_enabled=True,
        allowlist=["CONFIG_FAKE_UNKNOWN"],
    )

    assert payload["is_valid"] is True
    assert payload["validation_status"] == "ok"
    assert payload["unknown_keys"] == []
