from __future__ import annotations

from app.services.tool_registry import build_default_tool_registry


def test_build_default_tool_registry_contains_known_tools() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=60)

    assert "read_file" in set(registry.keys())
    assert "run_command" in set(registry.keys())
    assert registry.get("spawn_subrun") is not None


def test_run_command_timeout_uses_command_timeout_setting() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=42)

    spec = registry["run_command"]

    assert spec.timeout_seconds == 42.0
    assert spec.max_retries == 1
