from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("OLLAMA_BIN", "python")

from app.config import settings
from app.errors import RuntimeSwitchError
from app.main import runtime_manager
from app.runtime_manager import RuntimeState


def _set_runtime(runtime: str) -> RuntimeState:
    previous = runtime_manager.get_state()
    runtime_manager._state = RuntimeState(
        runtime=runtime,
        base_url="http://localhost:11434/api" if runtime == "api" else "http://localhost:11434/v1",
        model="minimax-m2:cloud" if runtime == "api" else "llama3.3:70b-instruct-q4_K_M",
    )
    return previous


def test_is_runtime_authenticated_local_is_true_even_if_auth_required(monkeypatch) -> None:
    previous_runtime = _set_runtime("local")
    monkeypatch.setattr(settings, "api_auth_required", True)
    monkeypatch.setattr(settings, "api_auth_token", "")

    try:
        assert runtime_manager.is_runtime_authenticated() is True
    finally:
        runtime_manager._state = previous_runtime


def test_is_runtime_authenticated_api_requires_token_when_enabled(monkeypatch) -> None:
    previous_runtime = _set_runtime("api")
    monkeypatch.setattr(settings, "api_auth_required", True)
    monkeypatch.setattr(settings, "api_auth_token", "")

    try:
        assert runtime_manager.is_runtime_authenticated() is False
    finally:
        runtime_manager._state = previous_runtime


def test_ensure_api_runtime_authenticated_raises_without_token(monkeypatch) -> None:
    previous_runtime = _set_runtime("api")
    monkeypatch.setattr(settings, "api_auth_required", True)
    monkeypatch.setattr(settings, "api_auth_token", "")

    try:
        with pytest.raises(RuntimeSwitchError):
            asyncio.run(runtime_manager.ensure_api_runtime_authenticated())
    finally:
        runtime_manager._state = previous_runtime


def test_resolve_api_request_model_raises_without_token(monkeypatch) -> None:
    previous_runtime = _set_runtime("api")
    monkeypatch.setattr(settings, "api_auth_required", True)
    monkeypatch.setattr(settings, "api_auth_token", "")

    try:
        with pytest.raises(RuntimeSwitchError):
            asyncio.run(runtime_manager.resolve_api_request_model("minimax-m2:cloud"))
    finally:
        runtime_manager._state = previous_runtime
