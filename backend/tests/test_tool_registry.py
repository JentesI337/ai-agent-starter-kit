from __future__ import annotations

from app.services.tool_registry import ToolRegistryFactory, ToolSpec, build_default_tool_registry


def test_build_default_tool_registry_contains_known_tools() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=60)

    assert "read_file" in set(registry.keys())
    assert "run_command" in set(registry.keys())
    assert "web_search" in set(registry.keys())
    assert "http_request" in set(registry.keys())
    assert "analyze_image" in set(registry.keys())
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


def test_http_request_default_retry_class_is_none() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=30)

    policy = registry.build_execution_policy("http_request")

    assert policy.retry_class == "none"


def test_build_function_calling_tools_uses_typed_parameters() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=30)

    tools = registry.build_function_calling_tools(allowed_tools={"run_command", "spawn_subrun"})

    assert len(tools) == 2
    by_name = {
        item["function"]["name"]: item["function"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    }
    run_command = by_name["run_command"]
    run_schema = run_command["parameters"]
    assert run_schema["additionalProperties"] is False
    assert run_schema["required"] == ["command"]
    assert run_schema["properties"]["command"]["type"] == "string"

    spawn_subrun = by_name["spawn_subrun"]
    spawn_schema = spawn_subrun["parameters"]
    assert spawn_schema["additionalProperties"] is False
    assert spawn_schema["required"] == ["message"]
    assert spawn_schema["properties"]["mode"]["enum"] == ["run", "wait"]


def test_registry_exposes_tool_capabilities() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=30)

    run_caps = set(registry.capabilities_for_tool("run_command"))
    read_caps = set(registry.capabilities_for_tool("read_file"))

    assert "command_execution" in run_caps
    assert "filesystem_read" in read_caps


def test_registry_filters_tools_by_capabilities() -> None:
    registry = build_default_tool_registry(command_timeout_seconds=30)

    filtered = registry.filter_tools_by_capabilities(
        candidate_tools={"read_file", "run_command", "web_fetch"},
        required_capabilities={"command_execution", "web_retrieval"},
    )

    assert filtered == {"run_command", "web_fetch"}
