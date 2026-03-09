"""Integration tests for the AgentRunner feature-flag router in HeadAgent."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.setenv("USE_CONTINUOUS_LOOP", "false")
    monkeypatch.setenv("TESTING", "1")


def _make_settings_with_loop(enabled: bool):
    """Create a Settings object with use_continuous_loop overridden."""
    from app.config import Settings
    return Settings(use_continuous_loop=enabled)


class TestFeatureFlagRouter:
    """Verify that HeadAgent.run() correctly delegates to AgentRunner."""

    def test_agent_runner_created_when_flag_on(self):
        """When USE_CONTINUOUS_LOOP=true, _agent_runner should be an AgentRunner."""
        fresh_settings = _make_settings_with_loop(True)

        with patch("app.agent.settings", fresh_settings), \
             patch("app.agent_runner.settings", fresh_settings):
            from app.agent import HeadAgent
            from app.agent_runner import AgentRunner

            agent = HeadAgent(name="test-agent")
            assert isinstance(agent._agent_runner, AgentRunner)

    @pytest.mark.asyncio
    async def test_run_delegates_to_runner_when_flag_on(self):
        """When flag is on and runner exists, run() should delegate to runner."""
        fresh_settings = _make_settings_with_loop(True)

        with patch("app.agent.settings", fresh_settings), \
             patch("app.agent_runner.settings", fresh_settings):
            from app.agent import HeadAgent

            agent = HeadAgent(name="test-agent")
            # Mock the runner's run method
            agent._agent_runner.run = AsyncMock(return_value="runner result")

            result = await agent.run(
                user_message="hello",
                send_event=AsyncMock(),
                session_id="s1",
                request_id="r1",
            )

            agent._agent_runner.run.assert_awaited_once()
            assert result == "runner result"


class TestConfigureRuntimeUpdatesRunner:
    """Verify configure_runtime propagates the new client to the runner."""

    def test_configure_runtime_updates_runner_client(self):
        fresh_settings = _make_settings_with_loop(True)

        with patch("app.agent.settings", fresh_settings), \
             patch("app.agent_runner.settings", fresh_settings):
            from app.agent import HeadAgent

            agent = HeadAgent(name="test-agent")
            old_client = agent._agent_runner.client

            agent.configure_runtime(
                base_url="http://localhost:9999/v1",
                model="new-model",
            )

            # Client should have been updated
            assert agent._agent_runner.client is agent.client
            assert agent._agent_runner.client is not old_client
