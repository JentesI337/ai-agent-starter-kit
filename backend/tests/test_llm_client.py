from __future__ import annotations

import asyncio
import json

import httpx
import pytest

import app.llm_client as llm_module
from app.errors import LlmClientError
from app.llm_client import LlmClient


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        json_data: dict | None = None,
        text: str = "",
        lines: list[str] | None = None,
        body: bytes | None = None,
    ):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self._lines = list(lines or [])
        self._body = body if body is not None else text.encode("utf-8")

    async def aread(self) -> bytes:
        return self._body

    def json(self) -> dict:
        return self._json_data

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeAsyncClient:
    def __init__(self, *, queue: list[object]):
        self._queue = queue

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, headers: dict, json: dict):
        if not self._queue:
            raise AssertionError("No queued fake response for post().")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, _FakeResponse):
            raise AssertionError(f"Unsupported fake queue item for post: {item!r}")
        return item

    def stream(self, method: str, url: str, headers: dict, json: dict):
        if not self._queue:
            raise AssertionError("No queued fake response for stream().")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, _FakeResponse):
            raise AssertionError(f"Unsupported fake queue item for stream: {item!r}")
        return _FakeStreamContext(item)


def _patch_async_client(monkeypatch, queue: list[object]) -> None:
    class _Factory:
        def __init__(self, *args, **kwargs):
            self._client = _FakeAsyncClient(queue=queue)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _Factory)


def _patch_async_client_with_capture(monkeypatch, queue: list[object], captured_payloads: list[dict]) -> None:
    class _CapturingClient(_FakeAsyncClient):
        async def post(self, url: str, headers: dict, json: dict):
            captured_payloads.append(dict(json))
            return await super().post(url, headers, json)

        def stream(self, method: str, url: str, headers: dict, json: dict):
            captured_payloads.append(dict(json))
            return super().stream(method, url, headers, json)

    class _Factory:
        def __init__(self, *args, **kwargs):
            self._client = _CapturingClient(queue=queue)

        async def __aenter__(self):
            return self._client

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _Factory)


def test_complete_chat_retries_and_returns_content(monkeypatch) -> None:
    queue: list[object] = [
        _FakeResponse(status_code=429, text="rate limited"),
        _FakeResponse(
            status_code=200,
            json_data={"choices": [{"message": {"content": "final answer"}}]},
        ),
    ]
    _patch_async_client(monkeypatch, queue)

    client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")

    result = asyncio.run(client.complete_chat("sys", "user"))

    assert result == "final answer"


def test_complete_chat_raises_on_empty_content(monkeypatch) -> None:
    queue: list[object] = [
        _FakeResponse(status_code=200, json_data={"choices": [{"message": {"content": "   "}}]}),
    ]
    _patch_async_client(monkeypatch, queue)

    client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")

    with pytest.raises(LlmClientError, match="empty completion content"):
        asyncio.run(client.complete_chat("sys", "user"))


def test_complete_chat_maps_timeout_exception(monkeypatch) -> None:
    queue: list[object] = [
        httpx.TimeoutException("request timed out"),
    ]
    _patch_async_client(monkeypatch, queue)

    client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")

    with pytest.raises(LlmClientError, match="LLM timeout"):
        asyncio.run(client.complete_chat("sys", "user"))


def test_stream_chat_completion_retries_and_yields_tokens(monkeypatch) -> None:
    retry_response = _FakeResponse(status_code=503, text="temporary unavailable", body=b"temporary unavailable")
    stream_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hel"}}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": "lo"}}]}),
        "data: [DONE]",
    ]
    success_response = _FakeResponse(status_code=200, lines=stream_lines)
    queue: list[object] = [retry_response, success_response]
    _patch_async_client(monkeypatch, queue)

    client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")

    async def _collect() -> list[str]:
        return [token async for token in client.stream_chat_completion("sys", "user")]

    tokens = asyncio.run(_collect())

    assert tokens == ["Hel", "lo"]


def test_complete_chat_ollama_raises_on_empty_content(monkeypatch) -> None:
    queue: list[object] = [
        _FakeResponse(status_code=200, json_data={"message": {"content": ""}}),
    ]
    _patch_async_client(monkeypatch, queue)

    client = LlmClient(base_url="http://localhost:11434/api", model="test-model")

    with pytest.raises(LlmClientError, match="empty completion content"):
        asyncio.run(client.complete_chat("sys", "user"))


def test_complete_chat_includes_temperature_in_openai_payload(monkeypatch) -> None:
    queue: list[object] = [
        _FakeResponse(
            status_code=200,
            json_data={"choices": [{"message": {"content": "ok"}}]},
        ),
    ]
    captured_payloads: list[dict] = []
    _patch_async_client_with_capture(monkeypatch, queue, captured_payloads)

    client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")
    result = asyncio.run(client.complete_chat("sys", "user", temperature=0.42))

    assert result == "ok"
    assert captured_payloads
    assert captured_payloads[0].get("temperature") == pytest.approx(0.42)


def test_complete_chat_includes_temperature_in_ollama_options(monkeypatch) -> None:
    queue: list[object] = [
        _FakeResponse(
            status_code=200,
            json_data={"message": {"content": "ok"}},
        ),
    ]
    captured_payloads: list[dict] = []
    _patch_async_client_with_capture(monkeypatch, queue, captured_payloads)

    client = LlmClient(base_url="http://localhost:11434/api", model="test-model")
    result = asyncio.run(client.complete_chat("sys", "user", temperature=0.33))

    assert result == "ok"
    assert captured_payloads
    options = captured_payloads[0].get("options") or {}
    assert isinstance(options, dict)
    assert options.get("temperature") == pytest.approx(0.33)


def test_complete_chat_with_tools_uses_typed_tool_definitions_in_payload(monkeypatch) -> None:
    queue: list[object] = [
        _FakeResponse(
            status_code=200,
            json_data={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "run_command",
                                        "arguments": '{"command":"pytest -q"}',
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        ),
    ]
    captured_payloads: list[dict] = []
    _patch_async_client_with_capture(monkeypatch, queue, captured_payloads)

    client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")
    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "minLength": 1},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        }
    ]

    actions = asyncio.run(
        client.complete_chat_with_tools(
            system_prompt="sys",
            user_prompt="user",
            allowed_tools=["run_command"],
            tool_definitions=tool_definitions,
        )
    )

    assert actions == [{"tool": "run_command", "args": {"command": "pytest -q"}}]
    assert captured_payloads
    tools_payload = captured_payloads[0].get("tools")
    assert tools_payload == tool_definitions
