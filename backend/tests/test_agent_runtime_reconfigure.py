from __future__ import annotations

from app.agent import HeadAgent
from app.llm_client import LlmClient
from app.memory import MemoryStore


def test_head_agent_accepts_injected_dependencies(tmp_path) -> None:
    injected_client = LlmClient(base_url="http://localhost:11434/v1", model="test-model")
    injected_memory = MemoryStore(max_items_per_session=5, persist_dir=str(tmp_path / "memory"))

    agent = HeadAgent(client=injected_client, memory=injected_memory)

    assert agent.client is injected_client
    assert agent.memory is injected_memory


def test_configure_runtime_updates_subagents_without_rebuild() -> None:
    agent = HeadAgent()

    planner_before = id(agent.planner_agent)
    tool_selector_before = id(agent.tool_selector_agent)
    synthesizer_before = id(agent.synthesizer_agent)

    agent.configure_runtime(base_url="http://example.local/v1", model="runtime-model")

    assert id(agent.planner_agent) == planner_before
    assert id(agent.tool_selector_agent) == tool_selector_before
    assert id(agent.synthesizer_agent) == synthesizer_before

    assert agent.client.base_url == "http://example.local/v1"
    assert agent.client.model == "runtime-model"
    assert agent.planner_agent.client.base_url == "http://example.local/v1"
    assert agent.planner_agent.client.model == "runtime-model"
    assert agent.synthesizer_agent.client.base_url == "http://example.local/v1"
    assert agent.synthesizer_agent.client.model == "runtime-model"
