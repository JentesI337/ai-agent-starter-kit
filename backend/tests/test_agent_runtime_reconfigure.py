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


def test_configure_runtime_updates_runner_client_without_rebuild() -> None:
    agent = HeadAgent()

    runner_before = id(agent._agent_runner)

    agent.configure_runtime(base_url="http://localhost:9999/v1", model="runtime-model")

    assert id(agent._agent_runner) == runner_before
    assert agent.client.base_url == "http://localhost:9999/v1"
    assert agent.client.model == "runtime-model"
    assert agent._agent_runner.client.base_url == "http://localhost:9999/v1"
    assert agent._agent_runner.client.model == "runtime-model"
