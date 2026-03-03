from __future__ import annotations

import asyncio

from app.config import settings
from app.custom_agents import CustomAgentAdapter, CustomAgentCreateRequest, CustomAgentDefinition, CustomAgentStore
from app.services.agent_isolation import AgentIsolationPolicy, resolve_agent_isolation_profile


def test_isolation_blocks_cross_scope_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "agent_isolation_enabled", True)
    monkeypatch.setattr(settings, "agent_isolation_allowed_scope_pairs", [])

    policy = AgentIsolationPolicy.from_settings(settings)
    source = resolve_agent_isolation_profile(agent_id="head-agent")
    target = resolve_agent_isolation_profile(agent_id="coder-agent")

    decision = policy.evaluate(
        source_agent_id="head-agent",
        target_agent_id="coder-agent",
        source_profile=source,
        target_profile=target,
    )

    assert decision.allowed is False
    assert decision.reason == "cross_scope_blocked"


def test_isolation_allows_same_scope() -> None:
    policy = AgentIsolationPolicy(enabled=True, allowed_cross_scope_pairs=set())
    source = resolve_agent_isolation_profile(agent_id="head-agent")
    target = resolve_agent_isolation_profile(agent_id="head-agent")

    decision = policy.evaluate(
        source_agent_id="head-agent",
        target_agent_id="head-agent",
        source_profile=source,
        target_profile=target,
    )

    assert decision.allowed is True
    assert decision.reason == "scope_match"


def test_isolation_allows_allowlisted_pair(monkeypatch) -> None:
    monkeypatch.setattr(settings, "agent_isolation_enabled", True)
    monkeypatch.setattr(settings, "agent_isolation_allowed_scope_pairs", ["head-agent->coder-agent"])

    policy = AgentIsolationPolicy.from_settings(settings)
    source = resolve_agent_isolation_profile(agent_id="head-agent")
    target = resolve_agent_isolation_profile(agent_id="coder-agent")

    decision = policy.evaluate(
        source_agent_id="head-agent",
        target_agent_id="coder-agent",
        source_profile=source,
        target_profile=target,
    )

    assert decision.allowed is True
    assert decision.reason == "cross_scope_allowlisted"


def test_custom_agent_store_persists_isolation_scopes(tmp_path) -> None:
    store = CustomAgentStore(persist_dir=str(tmp_path / "custom_agents"))

    created = store.upsert(
        CustomAgentCreateRequest(
            id="specialist-a",
            name="Specialist A",
            description="scope test",
            base_agent_id="head-agent",
            workflow_steps=["step"],
            workspace_scope="ws-alpha",
            skills_scope="skills-alpha",
            credential_scope="cred-alpha",
        )
    )

    listed = {item.id: item for item in store.list()}
    loaded = listed[created.id]

    assert loaded.workspace_scope == "ws-alpha"
    assert loaded.skills_scope == "skills-alpha"
    assert loaded.credential_scope == "cred-alpha"


def test_resolve_profile_uses_custom_scope_fields() -> None:
    class _Definition:
        workspace_scope = "ws-shared"
        skills_scope = "skills-shared"
        credential_scope = "cred-shared"

    profile = resolve_agent_isolation_profile(agent_id="specialist-a", custom_definition=_Definition())

    assert profile.workspace_scope == "ws-shared"
    assert profile.skills_scope == "skills-shared"
    assert profile.credential_scope == "cred-shared"


def test_custom_agent_adapter_propagates_source_agent_context() -> None:
    class _BaseAgent:
        def __init__(self) -> None:
            self.current_source_agent_id: str | None = None

        def configure_runtime(self, base_url: str, model: str) -> None:
            _ = (base_url, model)

        def set_source_agent_context(self, source_agent_id: str | None):
            previous = self.current_source_agent_id
            self.current_source_agent_id = source_agent_id
            return previous

        def reset_source_agent_context(self, token) -> None:
            self.current_source_agent_id = token

        async def run(
            self,
            user_message: str,
            send_event,
            session_id: str,
            request_id: str,
            model: str | None = None,
            tool_policy=None,
            prompt_mode: str | None = None,
            should_steer_interrupt=None,
        ) -> str:
            _ = (user_message, send_event, session_id, request_id, model, tool_policy, prompt_mode, should_steer_interrupt)
            return self.current_source_agent_id or "none"

    definition = CustomAgentDefinition(
        id="specialist-a",
        name="Specialist A",
        description="",
        base_agent_id="head-agent",
        workflow_steps=[],
        allow_subrun_delegation=True,
    )
    base_agent = _BaseAgent()
    adapter = CustomAgentAdapter(definition=definition, base_agent=base_agent)

    async def _send_event(_: dict) -> None:
        return

    result = asyncio.run(
        adapter.run(
            user_message="delegate",
            send_event=_send_event,
            session_id="sess-1",
            request_id="req-1",
        )
    )

    assert result == "specialist-a"
    assert base_agent.current_source_agent_id is None
