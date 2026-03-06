from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import TypeVar

import anyio
import pytest
from starlette.websockets import WebSocketDisconnect

T = TypeVar("T")


def run_async_with_timeout(coro: Coroutine[object, object, T], *, timeout_seconds: float = 2.0) -> T:
    async def _runner() -> T:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)

    try:
        return asyncio.run(_runner())
    except TimeoutError as exc:
        pytest.fail(f"Async operation exceeded timeout ({timeout_seconds:.2f}s): {exc}")


def receive_json_with_timeout(
    ws,
    timeout_seconds: float = 2.0,
    *,
    fail_on_timeout: bool = True,
) -> dict | None:
    async def _receive_message() -> dict:
        with anyio.fail_after(timeout_seconds):
            return await ws._send_rx.receive()

    try:
        message = ws.portal.call(_receive_message)
    except TimeoutError as exc:
        if fail_on_timeout:
            pytest.fail(f"WebSocket receive timed out after {timeout_seconds:.2f}s: {exc}")
        return None

    if message.get("type") == "websocket.close":
        raise WebSocketDisconnect(code=message.get("code", 1000), reason=message.get("reason", ""))

    if message.get("type") != "websocket.send":
        pytest.fail(f"Unexpected websocket message type: {message.get('type')}")

    if "text" in message and isinstance(message.get("text"), str):
        return json.loads(message["text"])

    payload = message.get("bytes")
    if isinstance(payload, (bytes, bytearray)):
        return json.loads(bytes(payload).decode("utf-8"))

    pytest.fail("WebSocket message missing text/bytes payload")
