from __future__ import annotations

from types import SimpleNamespace

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


def test_validate_environment_config_detects_invalid_numeric_ranges() -> None:
    broken = SimpleNamespace(
        config_strict_unknown_keys_enabled=False,
        config_strict_unknown_keys_allowlist=[],
        command_timeout_seconds=0,
        session_inbox_max_queue_length=0,
        session_inbox_ttl_seconds=0,
        session_follow_up_max_deferrals=0,
        run_tool_call_cap=0,
        run_tool_time_cap_seconds=0.0,
        tool_loop_warn_threshold=5,
        tool_loop_critical_threshold=5,
        tool_loop_circuit_breaker_threshold=5,
        max_user_message_length=0,
        queue_mode_default="invalid",
        prompt_mode_default="invalid",
        hook_failure_policy_default="invalid",
        pipeline_runner_prompt_compaction_ratio=1.2,
    )

    payload = validate_environment_config(
        broken,
        environ={"APP_ENV": "development"},
        strict_unknown_keys_enabled=False,
        allowlist=[],
    )

    assert payload["is_valid"] is False
    assert payload["validation_status"] == "error"
    assert payload["errors"]
