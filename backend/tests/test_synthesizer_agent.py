from __future__ import annotations

import asyncio

import pytest

from app.agents.synthesizer_agent import SynthesizerAgent
from app.contracts.schemas import SynthesizerInput
from app.errors import LlmClientError


class _FakeClient:
    def __init__(self, tokens: list[str], *, delay_per_token: float = 0.0):
        self._tokens = list(tokens)
        self._delay = delay_per_token
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None

    async def stream_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ):
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        for token in self._tokens:
            if self._delay > 0:
                await asyncio.sleep(self._delay)
            yield token


def _payload() -> SynthesizerInput:
    return SynthesizerInput(
        user_message="hello",
        plan_text="plan",
        tool_results="",
        reduced_context="ctx",
    )


def test_synthesizer_execute_streams_and_completes() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    agent = SynthesizerAgent(
        client=_FakeClient(["Hello", " ", "World"]),
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    async def _run() -> str:
        result = await agent.execute(
            _payload(),
            send_event=send_event,
            session_id="s1",
            request_id="r1",
            model=None,
        )
        return result.final_text

    final_text = asyncio.run(_run())

    assert final_text == "Hello World"
    stages = [evt.get("stage") for evt in events if evt.get("type") == "lifecycle"]
    assert "streaming_started" in stages
    assert "streaming_completed" in stages
    assert "streaming_timeout" not in stages


def test_synthesizer_execute_times_out_and_emits_timeout_lifecycle() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    agent = SynthesizerAgent(
        client=_FakeClient(["slow-token"], delay_per_token=0.2),
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=0.05,
    )

    async def _run() -> None:
        await agent.execute(
            _payload(),
            send_event=send_event,
            session_id="s2",
            request_id="r2",
            model=None,
        )

    with pytest.raises(LlmClientError, match="Synthesizer streaming timeout"):
        asyncio.run(_run())

    stages = [evt.get("stage") for evt in events if evt.get("type") == "lifecycle"]
    assert "streaming_started" in stages
    assert "streaming_timeout" in stages
    assert "streaming_completed" not in stages


def test_synthesizer_adds_hard_schema_prompt_for_matching_request() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    client = _FakeClient(["ok"])
    agent = SynthesizerAgent(
        client=client,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    payload = SynthesizerInput(
        user_message=(
            "Erstelle eine Analyse mit Architektur-Risiken, Performance-Hotspots, Guardrail-Lücken "
            "und einem Rollout-Plan in 3 Phasen."
        ),
        plan_text="plan",
        tool_results="",
        reduced_context="ctx",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s3", request_id="r3", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "Mandatory output schema" in client.last_user_prompt
    assert "Phase 1" in client.last_user_prompt
    assert "Top 10" in client.last_user_prompt


def test_synthesizer_does_not_force_hard_schema_for_normal_request() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    client = _FakeClient(["ok"])
    agent = SynthesizerAgent(
        client=client,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    async def _run() -> None:
        await agent.execute(_payload(), send_event=send_event, session_id="s4", request_id="r4", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "Mandatory output schema" not in client.last_user_prompt
