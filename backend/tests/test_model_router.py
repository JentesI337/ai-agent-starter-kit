from __future__ import annotations

import asyncio

from app.contracts.agent_contract import AgentConstraints, AgentContract
from app.errors import LlmClientError
from app.model_routing.router import ModelRouter
from app.orchestrator.pipeline_runner import PipelineRunner
from app.state import StateStore
from pydantic import BaseModel


class _FakeInput(BaseModel):
    text: str = ""


class _FakeOutput(BaseModel):
    text: str = ""


class _FakeAgent(AgentContract):
    role = "fake"
    input_schema = _FakeInput
    output_schema = _FakeOutput
    constraints = AgentConstraints(
        max_context=2048,
        temperature=0.3,
        reasoning_depth=1,
        reflection_passes=0,
        combine_steps=False,
    )

    def __init__(self):
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "fake-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        return

    async def run(self, user_message, send_event, session_id, request_id, model=None, tool_policy=None):
        active_model = model or ""
        self.calls.append(active_model)
        if len(self.calls) == 1:
            raise LlmClientError("model not found")
        return "ok"


def test_model_router_prefers_requested_then_runtime_defaults() -> None:
    router = ModelRouter()

    decision = router.route(runtime="local", requested_model="custom-model")

    assert decision.primary_model == "custom-model"
    assert len(decision.fallback_models) >= 1
    assert "custom-model" in decision.scores


def test_model_router_prefers_runtime_optimized_model_when_not_requested() -> None:
    router = ModelRouter()

    local_decision = router.route(runtime="local", requested_model=None)
    api_decision = router.route(runtime="api", requested_model=None)

    assert local_decision.primary_model != ""
    assert api_decision.primary_model != ""


def test_pipeline_runner_retries_on_model_not_found(tmp_path) -> None:
    store = StateStore(persist_dir=str(tmp_path / "state"))
    agent = _FakeAgent()
    runner = PipelineRunner(agent=agent, state_store=store)

    request_id = "req-1"
    store.init_run(
        run_id=request_id,
        session_id="sess-1",
        request_id=request_id,
        user_message="hi",
        runtime="local",
        model="custom-model",
    )

    async def send_event(_: dict):
        return

    result = asyncio.run(
        runner.run(
            user_message="hello",
            send_event=send_event,
            session_id="sess-1",
            request_id=request_id,
            runtime="local",
            model="custom-model",
        )
    )

    assert result == "ok"
    assert len(agent.calls) == 2
