"""Unit tests for LlmClient.stream_chat_with_tools()."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.agent.runner_types import StreamResult
from app.llm.client import LlmClient


def _make_sse_line(data: dict) -> str:
    return f"data: {json.dumps(data)}"


def _sse_text_chunk(text: str, finish_reason: str | None = None) -> str:
    choice: dict = {"delta": {"content": text}, "index": 0}
    if finish_reason:
        choice["finish_reason"] = finish_reason
    return _make_sse_line({"choices": [choice]})


def _sse_tool_call_chunk(
    index: int,
    *,
    tc_id: str = "",
    name: str = "",
    arguments_fragment: str = "",
    finish_reason: str | None = None,
) -> str:
    func: dict = {}
    if name:
        func["name"] = name
    if arguments_fragment:
        func["arguments"] = arguments_fragment
    tc: dict = {"index": index, "function": func}
    if tc_id:
        tc["id"] = tc_id
    choice: dict = {"delta": {"tool_calls": [tc]}, "index": 0}
    if finish_reason:
        choice["finish_reason"] = finish_reason
    return _make_sse_line({"choices": [choice]})


def _sse_done() -> str:
    return "data: [DONE]"


class _FakeResponse:
    """Mock httpx streaming response."""

    def __init__(self, lines: list[str], status_code: int = 200):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def stream(self, method, url, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def client():
    return LlmClient(base_url="http://localhost:11434/v1", model="test-model")


class TestStreamChatWithToolsTextOnly:
    @pytest.mark.asyncio
    async def test_collects_text_chunks(self, client):
        lines = [
            _sse_text_chunk("Hello "),
            _sse_text_chunk("world", finish_reason="stop"),
            _sse_done(),
        ]
        fake_resp = _FakeResponse(lines)
        fake_http = _FakeClient(fake_resp)

        with patch("httpx.AsyncClient", return_value=fake_http):
            result = await client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert isinstance(result, StreamResult)
        assert result.text == "Hello world"
        assert result.finish_reason == "stop"
        assert result.tool_calls == ()

    @pytest.mark.asyncio
    async def test_calls_on_text_chunk_callback(self, client):
        lines = [
            _sse_text_chunk("A"),
            _sse_text_chunk("B", finish_reason="stop"),
            _sse_done(),
        ]
        fake_resp = _FakeResponse(lines)
        fake_http = _FakeClient(fake_resp)
        chunks: list[str] = []

        async def on_chunk(text: str):
            chunks.append(text)

        with patch("httpx.AsyncClient", return_value=fake_http):
            await client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "Hi"}],
                on_text_chunk=on_chunk,
            )

        assert chunks == ["A", "B"]


class TestStreamChatWithToolsToolCalls:
    @pytest.mark.asyncio
    async def test_collects_tool_calls(self, client):
        lines = [
            _sse_tool_call_chunk(0, tc_id="call_1", name="read_file", arguments_fragment='{"path":'),
            _sse_tool_call_chunk(0, arguments_fragment=' "x.py"}', finish_reason="tool_calls"),
            _sse_done(),
        ]
        fake_resp = _FakeResponse(lines)
        fake_http = _FakeClient(fake_resp)

        with patch("httpx.AsyncClient", return_value=fake_http):
            result = await client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "read x.py"}],
                tools=[{"type": "function", "function": {"name": "read_file"}}],
            )

        assert result.finish_reason == "tool_calls"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "x.py"}
        assert result.tool_calls[0].id == "call_1"

    @pytest.mark.asyncio
    async def test_handles_invalid_json_arguments(self, client):
        lines = [
            _sse_tool_call_chunk(0, tc_id="call_1", name="foo", arguments_fragment="not-json"),
            _sse_tool_call_chunk(0, finish_reason="tool_calls"),
            _sse_done(),
        ]
        fake_resp = _FakeResponse(lines)
        fake_http = _FakeClient(fake_resp)

        with patch("httpx.AsyncClient", return_value=fake_http):
            result = await client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "?"}],
                tools=[{"type": "function", "function": {"name": "foo"}}],
            )

        assert result.tool_calls[0].arguments == {"_raw": "not-json"}


class TestStreamChatWithToolsMultipleToolCalls:
    @pytest.mark.asyncio
    async def test_collects_parallel_tool_calls(self, client):
        lines = [
            _sse_tool_call_chunk(0, tc_id="c1", name="read_file", arguments_fragment='{"path":"a"}'),
            _sse_tool_call_chunk(1, tc_id="c2", name="run_command", arguments_fragment='{"command":"ls"}'),
            _sse_tool_call_chunk(0, finish_reason="tool_calls"),
            _sse_done(),
        ]
        fake_resp = _FakeResponse(lines)
        fake_http = _FakeClient(fake_resp)

        with patch("httpx.AsyncClient", return_value=fake_http):
            result = await client.stream_chat_with_tools(
                messages=[{"role": "user", "content": "?"}],
                tools=[],
            )

        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[1].name == "run_command"
