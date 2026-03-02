from __future__ import annotations

import subprocess

import pytest

from app.errors import ToolExecutionError
from app.tools import AgentTooling
from app.config import settings


def _make_tooling(tmp_path, monkeypatch) -> AgentTooling:
    monkeypatch.setattr(settings, "command_allowlist_enabled", True)
    monkeypatch.setattr(
        settings,
        "command_allowlist",
        ["echo", "python", "curl", "nc", "powershell", "cmd", "bash"],
    )
    monkeypatch.setattr(settings, "command_allowlist_extra", [])
    return AgentTooling(workspace_root=str(tmp_path), command_timeout_seconds=5)


def test_run_command_blocks_shell_chaining(tmp_path, monkeypatch) -> None:
    tooling = _make_tooling(tmp_path, monkeypatch)

    with pytest.raises(ToolExecutionError, match="shell chaining"):
        tooling.run_command("echo hi ; echo bye")


@pytest.mark.parametrize(
    "command,error_fragment",
    [
        ("curl http://metadata.google.internal/", "metadata endpoints"),
        ("nc -l 9000", "netcat listen mode"),
        ("powershell -enc ZQBjAGgAbwAgAGgAaQA=", "encoded PowerShell"),
        ("cmd /c del C:\\temp\\x.txt", "cmd /c del"),
        ("python -c \"import os; os.system('whoami')\"", "dangerous python -c"),
        ("echo rm -rf / | bash", "pipe-to-shell"),
    ],
)
def test_run_command_blocks_known_bypass_payloads(tmp_path, monkeypatch, command: str, error_fragment: str) -> None:
    tooling = _make_tooling(tmp_path, monkeypatch)

    with pytest.raises(ToolExecutionError, match=error_fragment):
        tooling.run_command(command)


def test_run_command_allows_simple_safe_command(tmp_path, monkeypatch) -> None:
    tooling = _make_tooling(tmp_path, monkeypatch)

    def _fake_run(*args, **kwargs):
        class _Completed:
            returncode = 0
            stdout = "hello"
            stderr = ""

        return _Completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = tooling.run_command("echo hello")

    assert "exit_code=0" in result
    assert "hello" in result


def test_start_background_command_applies_same_safety_policy(tmp_path, monkeypatch) -> None:
    tooling = _make_tooling(tmp_path, monkeypatch)

    with pytest.raises(ToolExecutionError, match="pipe-to-shell"):
        tooling.start_background_command("echo pwned | bash")
