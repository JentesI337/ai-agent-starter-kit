from __future__ import annotations

from app.config import Settings


def test_settings_mcp_servers_parses_inline_json_config() -> None:
    settings = Settings(
        mcp_enabled=True,
        mcp_servers_config='[{"name":"filesystem","transport":"stdio","command":"npx","args":["@modelcontextprotocol/server-filesystem","/workspace"],"env":{"MCP_LOG_LEVEL":"debug"}}]',
    )

    servers = settings.mcp_servers

    assert len(servers) == 1
    server = servers[0]
    assert server.name == "filesystem"
    assert server.transport == "stdio"
    assert server.command == "npx"
    assert server.args == ["@modelcontextprotocol/server-filesystem", "/workspace"]
    assert server.env == {"MCP_LOG_LEVEL": "debug"}


def test_settings_mcp_servers_returns_empty_when_disabled() -> None:
    settings = Settings(
        mcp_enabled=False,
        mcp_servers_config='[{"name":"x","transport":"stdio","command":"python"}]',
    )

    assert settings.mcp_servers == []
