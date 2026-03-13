from __future__ import annotations

from app.tools.execution.manager import ToolExecutionConfig


class _Settings:
    run_tool_call_cap = 0
    run_tool_time_cap_seconds = 0
    tool_loop_warn_threshold = 0
    tool_loop_critical_threshold = 1
    tool_loop_circuit_breaker_threshold = 1
    tool_loop_detector_generic_repeat_enabled = False
    tool_loop_detector_ping_pong_enabled = True
    tool_loop_detector_poll_no_progress_enabled = False
    tool_loop_poll_no_progress_threshold = 1
    tool_loop_warning_bucket_size = 0


def test_tool_execution_config_from_settings_applies_guards() -> None:
    config = ToolExecutionConfig.from_settings(_Settings())

    assert config.call_cap == 1
    assert config.time_cap_seconds == 1.0
    assert config.loop_warn_threshold == 1
    assert config.loop_critical_threshold == 2
    assert config.loop_circuit_breaker_threshold == 3
    assert config.generic_repeat_enabled is False
    assert config.ping_pong_enabled is True
    assert config.poll_no_progress_enabled is False
    assert config.poll_no_progress_threshold == 2
    assert config.warning_bucket_size == 1
