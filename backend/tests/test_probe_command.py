"""Unit tests for L3.8 probe_command."""

from __future__ import annotations

from app.tools.implementations.base import AgentTooling


class TestProbeCommand:
    def test_known_command_found(self):
        available, _detail = AgentTooling.probe_command("python")
        assert available or AgentTooling.probe_command("python3")[0]

    def test_unknown_command_not_found(self):
        available, detail = AgentTooling.probe_command("this_command_definitely_does_not_exist_abc123")
        assert not available
        assert "not found" in detail

    def test_empty_command(self):
        available, detail = AgentTooling.probe_command("")
        assert not available
        assert "empty" in detail

    def test_command_with_args_uses_first_token(self):
        available, _detail = AgentTooling.probe_command("python --version")
        assert available or AgentTooling.probe_command("python3 --version")[0]

    def test_whitespace_only(self):
        available, _detail = AgentTooling.probe_command("   ")
        assert not available
