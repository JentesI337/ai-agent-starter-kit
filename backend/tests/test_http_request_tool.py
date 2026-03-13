from __future__ import annotations

import asyncio
import socket

import pytest

import app.tools.implementations.web as web_module
import app.tools.url_validator as url_validator_module
from app.shared.errors import ToolExecutionError
from app.tools.implementations.base import AgentTooling


class _FakeResponse:
    def __init__(self, *, status_code: int, headers: dict[str, str] | None = None, body: bytes = b"", url: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.encoding = "utf-8"
        self.url = url or "https://api.example.com/result"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        if self._body:
            yield self._body


class _FakeClient:
    def __init__(self, *, response: _FakeResponse, calls: list[dict]):
        self._response = response
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, **kwargs):
        self._calls.append({"method": method, "url": url, **kwargs})
        return self._response


def _patch_client(monkeypatch, response: _FakeResponse, calls: list[dict]) -> None:
    class _ClientFactory:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)
            self._client = _FakeClient(response=response, calls=calls)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(web_module.httpx, "AsyncClient", _ClientFactory)


def _public_getaddrinfo(host: str, port: int, *args, **kwargs):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
    ]


def test_http_request_blocks_localhost(tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    with pytest.raises(ToolExecutionError, match="blocked hostname"):
        asyncio.run(tooling.http_request("http://localhost:8080/health"))


def test_http_request_post_json_body(monkeypatch, tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))
    calls: list[dict] = []
    monkeypatch.setattr(url_validator_module.socket, "getaddrinfo", _public_getaddrinfo)
    _patch_client(
        monkeypatch,
        _FakeResponse(
            status_code=201,
            headers={"Content-Type": "application/json", "X-Test": "ok"},
            body=b'{"ok":true}',
            url="https://api.example.com/create",
        ),
        calls,
    )

    result = asyncio.run(
        tooling.http_request(
            "https://api.example.com/create",
            method="POST",
            headers='{"Authorization":"Bearer token"}',
            body='{"name":"demo"}',
        )
    )

    assert calls
    call = calls[0]
    assert call["method"] == "POST"
    assert call["json"] == {"name": "demo"}
    assert call["content"] is None
    assert "status: 201" in result
    assert "source_url: https://api.example.com/create" in result


def test_http_request_rejects_large_body(tmp_path) -> None:
    tooling = AgentTooling(workspace_root=str(tmp_path))

    with pytest.raises(ToolExecutionError, match="body too large"):
        asyncio.run(
            tooling.http_request(
                "https://example.com",
                method="POST",
                body="x" * 1_000_001,
            )
        )
