from __future__ import annotations

import asyncio
import socket

import pytest

from app.errors import ToolExecutionError
from app.tools import AgentTooling
import app.tools as tools_module


class _FakeResponse:
    def __init__(self, *, status_code: int, headers: dict[str, str] | None = None, body: bytes = b""):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.encoding = "utf-8"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        if self._body:
            yield self._body


class _FakeClient:
    def __init__(self, *, responses: dict[str, _FakeResponse], called_urls: list[str]):
        self._responses = responses
        self._called_urls = called_urls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, **kwargs):
        self._called_urls.append(url)
        response = self._responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return response


def _patch_client(monkeypatch, responses: dict[str, _FakeResponse], called_urls: list[str]) -> None:
    class _ClientFactory:
        def __init__(self, *args, **kwargs):
            self._client = _FakeClient(responses=responses, called_urls=called_urls)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(tools_module.httpx, "AsyncClient", _ClientFactory)


def _public_getaddrinfo(host: str, port: int, *args, **kwargs):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
    ]


def test_web_fetch_blocks_localhost(tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    with pytest.raises(ToolExecutionError, match="blocked hostname"):
        asyncio.run(tooling.web_fetch("http://localhost:8080/health"))


def test_web_fetch_blocks_private_dns_resolution(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    def _private_getaddrinfo(host: str, port: int, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.10.10.10", port)),
        ]

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _private_getaddrinfo)

    with pytest.raises(ToolExecutionError, match="blocked non-public"):
        asyncio.run(tooling.web_fetch("https://example.com"))


def test_web_fetch_enforces_redirect_limit(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    called_urls: list[str] = []

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)

    # HTTPS: no DNS pinning — TLS cert validation prevents DNS-rebinding
    responses = {
        "https://a.example/start": _FakeResponse(status_code=302, headers={"location": "https://b.example/1"}),
        "https://b.example/1": _FakeResponse(status_code=302, headers={"location": "https://c.example/2"}),
        "https://c.example/2": _FakeResponse(status_code=302, headers={"location": "https://d.example/3"}),
        "https://d.example/3": _FakeResponse(status_code=302, headers={"location": "https://e.example/4"}),
    }
    _patch_client(monkeypatch, responses, called_urls)

    with pytest.raises(ToolExecutionError, match="redirect limit exceeded"):
        asyncio.run(tooling.web_fetch("https://a.example/start"))

    assert len(called_urls) == 4


def test_web_fetch_allows_public_target_and_follows_safe_redirect(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    called_urls: list[str] = []

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)

    # HTTPS: no DNS pinning — TLS cert validation prevents DNS-rebinding
    responses = {
        "https://example.com/start": _FakeResponse(
            status_code=302,
            headers={"location": "https://example.org/final"},
        ),
        "https://example.org/final": _FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/plain"},
            body=b"hello from public web",
        ),
    }
    _patch_client(monkeypatch, responses, called_urls)

    result = asyncio.run(tooling.web_fetch("https://example.com/start"))

    assert "content_type: text/plain" in result
    assert "hello from public web" in result
    assert len(called_urls) == 2


def test_web_fetch_blocks_large_content_length_header(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    called_urls: list[str] = []

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)

    # HTTPS: no DNS pinning — TLS cert validation prevents DNS-rebinding
    responses = {
        "https://example.com/huge": _FakeResponse(
            status_code=200,
            headers={
                "Content-Type": "text/plain",
                "Content-Length": str((5 * 1024 * 1024) + 1),
            },
            body=b"ignored",
        ),
    }
    _patch_client(monkeypatch, responses, called_urls)

    with pytest.raises(ToolExecutionError, match="response too large"):
        asyncio.run(tooling.web_fetch("https://example.com/huge"))


def test_web_fetch_blocks_binary_content_type(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    called_urls: list[str] = []

    monkeypatch.setattr(tools_module.socket, "getaddrinfo", _public_getaddrinfo)

    # HTTPS: no DNS pinning — TLS cert validation prevents DNS-rebinding
    responses = {
        "https://example.com/archive": _FakeResponse(
            status_code=200,
            headers={"Content-Type": "application/zip"},
            body=b"PK\x03\x04",
        ),
    }
    _patch_client(monkeypatch, responses, called_urls)

    with pytest.raises(ToolExecutionError, match="blocked content-type"):
        asyncio.run(tooling.web_fetch("https://example.com/archive"))
