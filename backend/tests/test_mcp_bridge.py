from __future__ import annotations

import asyncio

from app.mcp.bridge import McpBridge, McpServerConfig, McpToolDefinition


class _StubConnection:
    async def list_tools(self) -> list[McpToolDefinition]:
        return [
            McpToolDefinition(
                name="search_docs",
                description="Search indexed docs",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                server_name="docs",
            )
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {
            "tool": tool_name,
            "args": arguments,
            "content": [{"type": "text", "text": "ok from mcp"}],
        }

    async def close(self) -> None:
        return


def test_mcp_bridge_discovers_tools_and_builds_specs(monkeypatch) -> None:
    bridge = McpBridge(
        [
            McpServerConfig(
                name="docs",
                transport="stdio",
                command="python",
                args=["-m", "dummy"],
                env={},
            )
        ]
    )

    async def _fake_connect(config: McpServerConfig):
        _ = config
        return _StubConnection()

    monkeypatch.setattr(bridge, "_connect", _fake_connect)

    asyncio.run(bridge.initialize())

    specs = bridge.get_tool_specs()
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "mcp_docs_search_docs"
    assert spec.required_args == ("query",)
    assert spec.optional_args == ("max_results",)
    assert spec.capabilities == ("mcp_tool", "dynamic_tool")


def test_mcp_bridge_calls_tool_and_formats_text_result(monkeypatch) -> None:
    bridge = McpBridge(
        [
            McpServerConfig(
                name="docs",
                transport="stdio",
                command="python",
                args=["-m", "dummy"],
                env={},
            )
        ]
    )

    async def _fake_connect(config: McpServerConfig):
        _ = config
        return _StubConnection()

    monkeypatch.setattr(bridge, "_connect", _fake_connect)
    asyncio.run(bridge.initialize())

    result = asyncio.run(bridge.call_tool("mcp_docs_search_docs", {"query": "mcp"}))

    assert result == "ok from mcp"
