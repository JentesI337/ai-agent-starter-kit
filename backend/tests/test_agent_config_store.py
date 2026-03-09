"""Tests for AgentConfigStore (Sprint R2)."""
from __future__ import annotations
import pytest
from app.agents.agent_config_schema import AgentRuntimeConfig
from app.agents.agent_config_store import AgentConfigStore, BUILTIN_AGENT_DEFAULTS


@pytest.fixture()
def store(tmp_path):
    return AgentConfigStore(persist_dir=tmp_path / "agent_configs")


class TestAgentConfigStore:
    def test_get_builtin(self, store):
        config = store.get("head-agent")
        assert config.agent_id == "head-agent"
        assert config.temperature == 0.3

    def test_get_all(self, store):
        configs = store.get_all()
        assert len(configs) == len(BUILTIN_AGENT_DEFAULTS)

    def test_update_persists(self, store, tmp_path):
        store.update("head-agent", {"temperature": 0.5})
        config = store.get("head-agent")
        assert config.temperature == 0.5

        store2 = AgentConfigStore(persist_dir=tmp_path / "agent_configs")
        config2 = store2.get("head-agent")
        assert config2.temperature == 0.5

    def test_reset(self, store):
        store.update("head-agent", {"temperature": 0.9})
        store.reset("head-agent")
        config = store.get("head-agent")
        assert config.temperature == 0.3

    def test_security_floor_read_only(self, store):
        config = store.update("review-agent", {"read_only": False})
        assert config.read_only is True

    def test_snapshot_is_copy(self, store):
        snap = store.snapshot("head-agent")
        store.update("head-agent", {"temperature": 0.9})
        assert snap.temperature == 0.3

    def test_unknown_agent_gets_defaults(self, store):
        config = store.get("custom-agent")
        assert config.agent_id == "custom-agent"
        assert config.temperature == 0.3
