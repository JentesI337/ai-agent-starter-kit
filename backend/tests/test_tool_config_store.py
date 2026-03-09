"""Tests for ToolConfigStore and CommandSecurity (Sprint R3)."""
from __future__ import annotations

import pytest

from app.tool_modules.tool_config_store import ToolConfigStore
from app.tool_modules.command_security import (
    BUILTIN_COMMAND_SAFETY_PATTERNS,
    add_pattern,
    find_command_safety_violation,
    get_all_patterns,
)


@pytest.fixture()
def store(tmp_path):
    return ToolConfigStore(persist_path=tmp_path / "tool_configs.json")


class TestToolConfigStore:
    def test_get_default(self, store):
        config = store.get("run_command")
        assert config.tool_name == "run_command"
        assert config.enabled is True

    def test_update_persists(self, store, tmp_path):
        store.update("run_command", {"timeout_seconds": 120})
        store2 = ToolConfigStore(persist_path=tmp_path / "tool_configs.json")
        config = store2.get("run_command")
        assert config.timeout_seconds == 120

    def test_reset(self, store):
        store.update("run_command", {"timeout_seconds": 999})
        config = store.reset("run_command")
        assert config.timeout_seconds == 300  # back to BUILTIN default

    def test_unknown_tool(self, store):
        config = store.get("nonexistent_tool")
        assert config.enabled is True
        assert config.timeout_seconds is None


class TestCommandSecurity:
    def test_builtin_patterns_count(self):
        assert len(BUILTIN_COMMAND_SAFETY_PATTERNS) >= 15

    def test_violation_detected(self):
        result = find_command_safety_violation("rm -rf /")
        assert result is not None

    def test_no_violation_simple(self):
        # "ls" alone should not trigger any pattern
        assert find_command_safety_violation("ls") is None

    def test_add_pattern(self):
        initial_count = len(get_all_patterns())
        ok = add_pattern(r"\bdrop\s+table\b", "drop table is blocked")
        assert ok
        assert len(get_all_patterns()) == initial_count + 1

    def test_add_invalid_pattern(self):
        ok = add_pattern(r"[invalid", "bad regex")
        assert not ok
