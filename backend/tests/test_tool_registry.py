from __future__ import annotations

from app.services.tool_registry import ToolRegistryFactory, ToolSpec, build_default_tool_registry


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


def test_registry_exposes_dispatcher_when_built_with_tooling() -> None:
    class _Tooling:
        def read_file(self, path: str) -> str:
            return path

    registry = ToolRegistryFactory.build(
        tooling=_Tooling(),
        allowed_tools={"read_file", "spawn_subrun"},
        command_timeout_seconds=30,
    )

    dispatcher = registry.get_dispatcher("read_file")
    assert dispatcher is not None
    assert dispatcher(path="x") == "x"
    assert registry.get_dispatcher("spawn_subrun") is None


def test_registry_can_register_spec_and_build_policy() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=30)
    registry.register(
        ToolSpec(
            name="custom_tool",
            required_args=(),
            optional_args=(),
            timeout_seconds=12.0,
            max_retries=2,
        )
    )

    assert "custom_tool" in registry.tool_names()
    policy = registry.build_execution_policy("custom_tool")
    assert policy.timeout_seconds == 12.0
    assert policy.max_retries == 2
    assert policy.retry_class == "none"
