from __future__ import annotations

import asyncio

from app.tools.registry.registry import ToolRegistryFactory, ToolSpec


class _StubTooling:
    def read_file(self, path: str) -> str:
        return path


class _StubMcpBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="mcp_docs_search",
                required_args=("query",),
                optional_args=("limit",),
                timeout_seconds=30.0,
                max_retries=0,
                description="search via mcp",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                capabilities=("mcp_tool",),
            ),
            ToolSpec(
                name="mcp_docs_lookup",
                required_args=("id",),
                optional_args=(),
                timeout_seconds=30.0,
                max_retries=0,
                description="lookup via mcp",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
                capabilities=("mcp_tool",),
            ),
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, object]) -> str:
        self.calls.append((tool_name, dict(arguments)))
        return f"called:{tool_name}"


def test_tool_registry_factory_registers_mcp_tools_with_bound_dispatchers() -> None:
    bridge = _StubMcpBridge()
    registry = ToolRegistryFactory.build(
        tooling=_StubTooling(),
        allowed_tools=None,
        command_timeout_seconds=30,
        mcp_bridge=bridge,
    )

    search_dispatcher = registry.get_dispatcher("mcp_docs_search")
    lookup_dispatcher = registry.get_dispatcher("mcp_docs_lookup")

    assert search_dispatcher is not None
    assert lookup_dispatcher is not None

    search_result = asyncio.run(search_dispatcher(query="planner", limit=3))
    lookup_result = asyncio.run(lookup_dispatcher(id="doc-1"))

    assert search_result == "called:mcp_docs_search"
    assert lookup_result == "called:mcp_docs_lookup"
    assert bridge.calls == [
        ("mcp_docs_search", {"query": "planner", "limit": 3}),
        ("mcp_docs_lookup", {"id": "doc-1"}),
    ]
