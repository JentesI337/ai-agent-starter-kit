from __future__ import annotations

import asyncio
import json
import os
from itertools import count
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.mcp_types import McpServerConfig, McpToolDefinition
from app.services.tool_registry import ToolSpec

# SEC (OE-05): Allowlist of MCP server commands.
# Only executables in this set (or resolved via shutil.which to one of these
# base names) are permitted.  Configurable via MCP_COMMAND_ALLOWLIST env var.
_DEFAULT_MCP_COMMAND_ALLOWLIST: frozenset[str] = frozenset({
    "node", "npx", "python", "python3", "uvx",
    "deno", "bun",
    "docker",
    "mcp-server",
})


def _load_mcp_command_allowlist() -> frozenset[str]:
    """Load MCP command allowlist from env or use defaults."""
    raw = os.getenv("MCP_COMMAND_ALLOWLIST", "").strip()
    if not raw:
        return _DEFAULT_MCP_COMMAND_ALLOWLIST
    items = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return frozenset(items) | _DEFAULT_MCP_COMMAND_ALLOWLIST


def _validate_mcp_command(command: str, *, server_name: str) -> str:
    """SEC (OE-05): Validate that an MCP server command is in the allowlist.

    Resolves the command to its base name and checks against the allowlist.
    Raises ValueError if the command is not permitted.
    """
    import shutil

    if not command or not command.strip():
        raise ValueError(f"MCP server '{server_name}' has an empty command")

    clean = command.strip()
    base_name = Path(clean).stem.lower()
    # Remove common extensions
    for ext in (".exe", ".cmd", ".bat", ".ps1", ".sh"):
        if base_name.endswith(ext):
            base_name = base_name[: -len(ext)]

    allowlist = _load_mcp_command_allowlist()

    if base_name in allowlist:
        return clean

    # Check if the full path resolves to an allowed name
    resolved = shutil.which(clean)
    if resolved:
        resolved_name = Path(resolved).stem.lower()
        for ext in (".exe", ".cmd", ".bat"):
            if resolved_name.endswith(ext):
                resolved_name = resolved_name[: -len(ext)]
        if resolved_name in allowlist:
            return clean

    raise ValueError(
        f"MCP server '{server_name}' command '{clean}' (base: '{base_name}') is not in the "
        f"MCP command allowlist. Allowed: {sorted(allowlist)}. "
        f"Set MCP_COMMAND_ALLOWLIST env var to extend."
    )


class McpConnection(Protocol):
    async def list_tools(self) -> list[McpToolDefinition]: ...

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...

    async def close(self) -> None: ...


class McpBridge:
    def __init__(self, servers: list[McpServerConfig]):
        self._servers = {server.name: server for server in servers}
        self._connections: dict[str, McpConnection] = {}
        self._discovered_tools: dict[str, McpToolDefinition] = {}

    async def initialize(self) -> None:
        self._discovered_tools.clear()
        for name, config in self._servers.items():
            connection = await self._connect(config)
            self._connections[name] = connection
            tools = await connection.list_tools()
            for tool in tools:
                key = self._prefixed_tool_name(server_name=name, tool_name=tool.name)
                self._discovered_tools[key] = tool

    async def close(self) -> None:
        for connection in self._connections.values():
            await connection.close()
        self._connections.clear()
        self._discovered_tools.clear()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        tool_def = self._discovered_tools.get(tool_name)
        if tool_def is None:
            raise KeyError(f"Unknown MCP tool: {tool_name}")
        connection = self._connections.get(tool_def.server_name)
        if connection is None:
            raise RuntimeError(f"MCP server is not connected: {tool_def.server_name}")

        max_retries = 2
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    connection.call_tool(tool_def.name, arguments),
                    timeout=30.0,
                )
                return self._format_result(result)
            except (ConnectionError, OSError, asyncio.TimeoutError, RuntimeError) as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                # Try to reconnect before next attempt
                server_name = tool_def.server_name
                config = self._servers.get(server_name)
                if config is not None:
                    try:
                        await connection.close()
                    except Exception:
                        pass
                    try:
                        new_conn = await self._connect(config)
                        self._connections[server_name] = new_conn
                        connection = new_conn
                    except Exception:
                        pass  # reconnect failed, will retry with old connection or fail
                await asyncio.sleep(min(2 ** attempt, 8))

        raise RuntimeError(
            f"MCP call_tool failed after {max_retries + 1} attempts on '{tool_def.server_name}': {last_error}"
        )

    async def health_check(self, server_name: str | None = None) -> dict[str, bool]:
        """Check connection health for one or all MCP servers."""
        targets = (
            {server_name: self._connections[server_name]}
            if server_name and server_name in self._connections
            else dict(self._connections)
        )
        results: dict[str, bool] = {}
        for name, conn in targets.items():
            try:
                # Quick list_tools as a ping — lightweight and always supported
                await asyncio.wait_for(conn.list_tools(), timeout=5.0)
                results[name] = True
            except Exception:
                results[name] = False
        return results

    def get_tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for name, tool_def in sorted(self._discovered_tools.items()):
            schema = tool_def.input_schema if isinstance(tool_def.input_schema, dict) else {}
            required = tuple(self._schema_required_args(schema))
            optional = tuple(self._schema_optional_args(schema, required=required))
            specs.append(
                ToolSpec(
                    name=name,
                    required_args=required,
                    optional_args=optional,
                    timeout_seconds=30.0,
                    max_retries=0,
                    description=tool_def.description,
                    parameters=schema,
                    capabilities=("mcp_tool", "dynamic_tool"),
                )
            )
        return specs

    @staticmethod
    def _prefixed_tool_name(*, server_name: str, tool_name: str) -> str:
        safe_server = server_name.strip().replace(" ", "_")
        safe_tool = tool_name.strip().replace(" ", "_")
        return f"mcp_{safe_server}_{safe_tool}"

    @staticmethod
    def _schema_required_args(schema: dict[str, Any]) -> list[str]:
        required = schema.get("required")
        if not isinstance(required, list):
            return []
        return [str(item) for item in required if isinstance(item, str) and item.strip()]

    @staticmethod
    def _schema_optional_args(schema: dict[str, Any], *, required: tuple[str, ...]) -> list[str]:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return []
        required_set = set(required)
        return [
            str(key)
            for key in properties.keys()
            if isinstance(key, str) and key.strip() and str(key) not in required_set
        ]

    @staticmethod
    def _format_result(result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        text_value = item.get("text")
                        if isinstance(text_value, str) and text_value.strip():
                            text_parts.append(text_value)
                if text_parts:
                    return "\n".join(text_parts)
        return json.dumps(result, ensure_ascii=False)

    async def _connect(self, config: McpServerConfig) -> McpConnection:
        transport = config.transport.strip().lower()
        if transport == "stdio":
            if not config.command:
                raise ValueError(f"MCP stdio server '{config.name}' missing command")
            return await StdioMcpConnection.connect(
                command=config.command,
                args=config.args or [],
                env=config.env or {},
                server_name=config.name,
            )
        if transport == "sse":
            if not config.url:
                raise ValueError(f"MCP sse server '{config.name}' missing url")
            return await SseMcpConnection.connect(config.url, server_name=config.name)
        if transport == "streamable-http":
            if not config.url:
                raise ValueError(f"MCP streamable-http server '{config.name}' missing url")
            return await StreamableHttpMcpConnection.connect(config.url, server_name=config.name)
        raise ValueError(f"Unknown MCP transport: {config.transport}")


class _JsonRpcMcpConnection:
    def __init__(self, *, server_name: str):
        self._server_name = server_name
        self._id_counter = count(1)

    async def initialize(self) -> None:
        _ = await self._rpc_call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "ai-agent-starter-kit", "version": "1.0.0"},
            },
        )
        await self._rpc_notify("initialized", {})

    async def list_tools(self) -> list[McpToolDefinition]:
        payload = await self._rpc_call("tools/list", {})
        tools = payload.get("tools") if isinstance(payload, dict) else None
        if not isinstance(tools, list):
            return []
        result: list[McpToolDefinition] = []
        for raw_tool in tools:
            if not isinstance(raw_tool, dict):
                continue
            tool_name = str(raw_tool.get("name") or "").strip()
            if not tool_name:
                continue
            description = str(raw_tool.get("description") or "").strip()
            input_schema = raw_tool.get("inputSchema")
            if not isinstance(input_schema, dict):
                input_schema = {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                }
            result.append(
                McpToolDefinition(
                    name=tool_name,
                    description=description,
                    input_schema=input_schema,
                    server_name=self._server_name,
                )
            )
        return result

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        payload = await self._rpc_call(
            "tools/call",
            {
                "name": tool_name,
                "arguments": dict(arguments or {}),
            },
        )
        return payload

    async def _rpc_call(self, method: str, params: dict[str, Any]) -> dict[str, Any] | list[Any] | str:
        request_id = next(self._id_counter)
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        response = await self._send_rpc(payload)

        if not isinstance(response, dict):
            raise RuntimeError(f"Invalid MCP response type from '{self._server_name}'")
        if response.get("id") != request_id:
            raise RuntimeError(f"MCP response id mismatch from '{self._server_name}'")
        if "error" in response:
            raise RuntimeError(f"MCP call failed on '{self._server_name}': {response.get('error')}")
        return response.get("result")

    async def _rpc_notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._send_rpc(payload, expect_response=False)

    async def _send_rpc(self, payload: dict[str, Any], *, expect_response: bool = True) -> dict[str, Any] | None:
        raise NotImplementedError


class StdioMcpConnection(_JsonRpcMcpConnection):
    def __init__(self, *, process: asyncio.subprocess.Process, server_name: str):
        super().__init__(server_name=server_name)
        self._process = process
        self._io_lock = asyncio.Lock()

    @classmethod
    async def connect(
        cls,
        command: str,
        args: list[str],
        env: dict[str, str],
        *,
        server_name: str,
    ) -> StdioMcpConnection:
        # SEC (OE-05): Validate command against allowlist before execution
        validated_command = _validate_mcp_command(command, server_name=server_name)

        # SEC (OE-05): Validate args don't contain shell injection patterns
        for arg in (args or []):
            if any(c in str(arg) for c in (";", "&&", "||", "|", "`", "$(")):
                raise ValueError(
                    f"MCP server '{server_name}' arg contains shell metacharacter: '{arg}'"
                )

        merged_env = os.environ.copy()
        merged_env.update({str(key): str(value) for key, value in (env or {}).items()})
        process = await asyncio.create_subprocess_exec(
            validated_command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        connection = cls(process=process, server_name=server_name)
        await connection.initialize()
        return connection

    async def close(self) -> None:
        process = self._process
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def _send_rpc(self, payload: dict[str, Any], *, expect_response: bool = True) -> dict[str, Any] | None:
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("MCP stdio connection has no stdin/stdout")

        async with self._io_lock:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            self._process.stdin.write(header + body)
            await self._process.stdin.drain()

            if not expect_response:
                return None

            while True:
                message = await self._read_message()
                if message is None:
                    raise RuntimeError(f"MCP stdio server '{self._server_name}' closed connection")
                if "id" in message:
                    return message

    async def _read_message(self) -> dict[str, Any] | None:
        if self._process.stdout is None:
            return None

        content_length = 0
        while True:
            header_line = await self._process.stdout.readline()
            if not header_line:
                return None
            if header_line in {b"\r\n", b"\n"}:
                break
            decoded = header_line.decode("ascii", errors="ignore").strip()
            if decoded.lower().startswith("content-length:"):
                raw_len = decoded.split(":", 1)[1].strip()
                try:
                    content_length = int(raw_len)
                except ValueError:
                    content_length = 0

        if content_length <= 0:
            return None

        max_content_length = 10 * 1024 * 1024
        if content_length > max_content_length:
            raise ValueError(
                f"MCP content_length {content_length} exceeds maximum {max_content_length}"
            )

        payload = await self._process.stdout.readexactly(content_length)
        parsed = json.loads(payload.decode("utf-8"))
        if not isinstance(parsed, dict):
            return None
        return parsed


class _HttpMcpConnection(_JsonRpcMcpConnection):
    def __init__(self, *, server_name: str, url: str):
        super().__init__(server_name=server_name)
        self._url = url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _send_rpc(self, payload: dict[str, Any], *, expect_response: bool = True) -> dict[str, Any] | None:
        response = await self._client.post(self._url, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"MCP http request failed ({response.status_code})")
        if not expect_response:
            return None
        body = response.json()
        if isinstance(body, dict):
            return body
        raise RuntimeError("MCP http response must be a JSON object")


class SseMcpConnection(_HttpMcpConnection):
    @classmethod
    async def connect(cls, url: str, *, server_name: str) -> SseMcpConnection:
        connection = cls(server_name=server_name, url=url)
        await connection.initialize()
        return connection


class StreamableHttpMcpConnection(_HttpMcpConnection):
    @classmethod
    async def connect(cls, url: str, *, server_name: str) -> StreamableHttpMcpConnection:
        connection = cls(server_name=server_name, url=url)
        await connection.initialize()
        return connection
