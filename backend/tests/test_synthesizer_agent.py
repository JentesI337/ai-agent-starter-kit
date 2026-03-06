from __future__ import annotations

import asyncio
import json

import pytest

from app.agents.synthesizer_agent import SynthesizerAgent
from app.contracts.schemas import SynthesizerInput
from app.errors import LlmClientError
from app.services.dynamic_temperature import DynamicTemperatureResolver
from app.services.prompt_ab_registry import PromptAbRegistry


class _FakeClient:
    def __init__(self, tokens: list[str], *, delay_per_token: float = 0.0, repair_response: str | None = None):
        self._tokens = list(tokens)
        self._delay = delay_per_token
        self._repair_response = repair_response
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None
        self.last_repair_prompt: str | None = None
        self.last_stream_temperature: float | None = None

    async def stream_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ):
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        self.last_stream_temperature = temperature
        for token in self._tokens:
            if self._delay > 0:
                await asyncio.sleep(self._delay)
            yield token

    async def complete_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        _ = system_prompt, model, temperature
        self.last_repair_prompt = user_prompt
        if self._repair_response is not None:
            return self._repair_response
        return "\n".join(self._tokens)


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


def test_synthesizer_adds_hard_schema_prompt_for_depth_request() -> None:
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
            "Erstelle eine tiefe technische Research-Analyse rein textuell. "
            "Liefere einen Rollout-Plan in 3 Phasen und mindestens zwei KPI-Ziele. "
            "Verwende KEINE Tools und KEINE Shell/Systemkommandos."
        ),
        plan_text="plan",
        tool_results="",
        reduced_context="ctx",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s3b", request_id="r3b", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "Mandatory output schema" in client.last_user_prompt
    assert "Phase 1" in client.last_user_prompt
    assert "Messbare KPIs" in client.last_user_prompt


def test_synthesizer_adds_hard_schema_prompt_for_format_request_without_three_phases_phrase() -> None:
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
            "Erstelle eine umfangreiche technische Analyse rein textuell. "
            "Nutze zwingend die Abschnitte Architektur-Risiken, Performance-Hotspots, "
            "Guardrail-Lücken, Priorisierte Maßnahmen (Top 10), Messbare KPIs, Rollout-Plan."
        ),
        plan_text="plan",
        tool_results="",
        reduced_context="ctx",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s3c", request_id="r3c", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "Mandatory output schema" in client.last_user_prompt
    assert "Priorisierte Maßnahmen (Top 10)" in client.last_user_prompt


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
    assert "Mandatory output schema" in client.last_user_prompt
    assert "- Answer" in client.last_user_prompt
    assert "- Key points" in client.last_user_prompt
    assert "- Next step" in client.last_user_prompt


def test_synthesizer_uses_research_section_contract() -> None:
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
        user_message="Summarize latest platform incidents",
        plan_text="plan",
        tool_results="[web_fetch] ok source_url=https://example.com/postmortem",
        reduced_context="ctx",
        task_type="research",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s5", request_id="r5", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "- Summary" in client.last_user_prompt
    assert "- Findings" in client.last_user_prompt
    assert "- Evidence" in client.last_user_prompt
    assert "- Sources used" in client.last_user_prompt


def test_synthesizer_uses_orchestration_section_contract() -> None:
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
        user_message="Delegate architecture checks to helper agent",
        plan_text="plan",
        tool_results="spawned_subrun_id=subrun-1 mode=run agent_id=head-agent",
        reduced_context="ctx",
        task_type="orchestration",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s6", request_id="r6", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "- Goal" in client.last_user_prompt
    assert "- Delegation outcome" in client.last_user_prompt
    assert "- Child handover" in client.last_user_prompt
    assert "- Parent decision" in client.last_user_prompt


def test_synthesizer_uses_implementation_section_contract() -> None:
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
        user_message="Implement retry policy for timeout errors",
        plan_text="plan",
        tool_results="[read_file] ok",
        reduced_context="ctx",
        task_type="implementation",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s7", request_id="r7", model=None)

    asyncio.run(_run())

    assert client.last_user_prompt is not None
    assert "- Outcome" in client.last_user_prompt
    assert "- What changed" in client.last_user_prompt
    assert "- Validation" in client.last_user_prompt
    assert "- Next steps" in client.last_user_prompt


def test_synthesizer_self_check_repairs_invalid_contract_when_task_type_present() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    client = _FakeClient(
        ["short invalid answer"],
        repair_response=(
            "Outcome\n"
            "- Implemented schema validation\n\n"
            "What changed\n"
            "- Added self-check loop\n\n"
            "Validation\n"
            "- Ran focused tests\n\n"
            "Risks\n"
            "- Minimal risk\n\n"
            "Next steps\n"
            "- Proceed with E5-T3"
        ),
    )
    agent = SynthesizerAgent(
        client=client,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    payload = SynthesizerInput(
        user_message="Implement and validate the fix",
        plan_text="plan",
        tool_results="[read_file] ok",
        reduced_context="ctx",
        task_type="implementation",
    )

    async def _run() -> str:
        result = await agent.execute(payload, send_event=send_event, session_id="s8", request_id="r8", model=None)
        return result.final_text

    final_text = asyncio.run(_run())

    assert "Outcome" in final_text
    assert "Next steps" in final_text
    assert client.last_repair_prompt is not None
    stages = [evt.get("stage") for evt in events if evt.get("type") == "lifecycle"]
    assert "synthesis_contract_check_started" in stages
    assert "synthesis_contract_check_completed" in stages


def test_hard_research_self_check_rejects_heading_phase_and_split_kpi_formats() -> None:
    agent = SynthesizerAgent(
        client=_FakeClient(["ok"]),
        agent_name="head-agent",
        emit_lifecycle_fn=lambda *args, **kwargs: asyncio.sleep(0),
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    invalid_text = (
        "Architektur-Risiken\n- risk\n\n"
        "Performance-Hotspots\n- hotspot\n\n"
        "Guardrail-Lücken\n- gap\n\n"
        "Priorisierte Maßnahmen (Top 10)\n"
        "1. a\n2. b\n3. c\n4. d\n5. e\n6. f\n7. g\n8. h\n9. i\n10. j\n\n"
        "Messbare KPIs\n"
        "- KPI:\n"
        "- latency <= 120 ms\n"
        "- KPI:\n"
        "- availability >= 99 %\n\n"
        "Rollout-Plan\n"
        "### Phase 1\n- a\n"
        "### Phase 2\n- b\n"
        "### Phase 3\n- c\n"
    )

    failures = agent._validate_hard_research_contract(invalid_text)

    assert "phase_line_format_invalid" in failures
    assert "kpi_line_format_invalid" in failures


def test_synthesizer_self_check_skips_when_task_type_not_present() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    client = _FakeClient(["Hello World"])
    agent = SynthesizerAgent(
        client=client,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    async def _run() -> str:
        result = await agent.execute(_payload(), send_event=send_event, session_id="s9", request_id="r9", model=None)
        return result.final_text

    final_text = asyncio.run(_run())

    assert final_text == "Hello World"
    assert client.last_repair_prompt is None
    stages = [evt.get("stage") for evt in events if evt.get("type") == "lifecycle"]
    assert "synthesis_contract_check_started" not in stages


def test_synthesizer_semantic_truth_marks_orchestration_invalid_without_completed_subrun() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    client = _FakeClient(
        [
            "Goal\n- Delegate checks\n\n"
            "Delegation outcome\n- Successfully delegated to helper\n\n"
            "Child handover\n- pending\n\n"
            "Parent decision\n- continue\n\n"
            "Next steps\n- wait"
        ],
        repair_response=(
            "Goal\n- Delegate checks\n\n"
            "Delegation failure\n- Subrun did not complete\n\n"
            "Failure reason\n- only pending evidence available\n\n"
            "Recovery options\n- rerun with mode=wait\n\n"
            "Next steps\n- retry"
        ),
    )
    agent = SynthesizerAgent(
        client=client,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    payload = SynthesizerInput(
        user_message="orchestrate architecture review",
        plan_text="plan",
        tool_results="spawned_subrun_id=subrun-1 mode=run agent_id=head-agent handover_contract={\"terminal_reason\":\"subrun-accepted\"}",
        reduced_context="ctx",
        task_type="orchestration",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s10", request_id="r10", model=None)

    asyncio.run(_run())

    check_completed = next(
        (
            evt
            for evt in events
            if evt.get("type") == "lifecycle" and evt.get("stage") == "synthesis_contract_check_completed"
        ),
        None,
    )
    assert check_completed is not None
    assert check_completed.get("details", {}).get("valid") is False


def test_synthesizer_semantic_truth_rejects_success_claim_for_pending_task() -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    client = _FakeClient(
        [
            "Goal\n- Delegate checks\n\n"
            "Delegation initiated\n- Successfully delegated to helper\n\n"
            "Pending status\n- awaiting child completion\n\n"
            "What to expect\n- async status\n\n"
            "Next steps\n- poll status"
        ],
        repair_response=(
            "Goal\n- Delegate checks\n\n"
            "Delegation initiated\n- Subrun accepted\n\n"
            "Pending status\n- awaiting child completion\n\n"
            "What to expect\n- async status\n\n"
            "Next steps\n- poll status"
        ),
    )
    agent = SynthesizerAgent(
        client=client,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
    )

    payload = SynthesizerInput(
        user_message="orchestrate architecture review",
        plan_text="plan",
        tool_results="spawned_subrun_id=subrun-1 mode=run agent_id=head-agent handover_contract={\"terminal_reason\":\"subrun-accepted\"}",
        reduced_context="ctx",
        task_type="orchestration_pending",
    )

    async def _run() -> None:
        await agent.execute(payload, send_event=send_event, session_id="s11", request_id="r11", model=None)

    asyncio.run(_run())

    check_completed = next(
        (
            evt
            for evt in events
            if evt.get("type") == "lifecycle" and evt.get("stage") == "synthesis_contract_check_completed"
        ),
        None,
    )
    assert check_completed is not None
    assert check_completed.get("details", {}).get("valid") is True
    assert check_completed.get("details", {}).get("correction_applied") is True


def test_synthesizer_dynamic_temperature_changes_by_task_type(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    async def send_event(payload: dict) -> None:
        events.append(payload)

    async def emit_lifecycle(send_event_fn, stage: str, request_id: str, session_id: str, details: dict | None):
        await send_event_fn({"type": "lifecycle", "stage": stage, "details": details or {}})

    monkeypatch.setattr("app.agents.synthesizer_agent.settings.dynamic_temperature_enabled", True)
    resolver = DynamicTemperatureResolver(base_temperature=0.3)

    client_hard = _FakeClient(["ok"])
    agent_hard = SynthesizerAgent(
        client=client_hard,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
        temperature_resolver=resolver,
    )

    hard_payload = SynthesizerInput(
        user_message="Deep architecture research",
        plan_text="plan",
        tool_results="",
        reduced_context="ctx",
        task_type="hard_research",
    )

    async def _run_hard() -> None:
        await agent_hard.execute(hard_payload, send_event=send_event, session_id="temp-1", request_id="req-1", model=None)

    asyncio.run(_run_hard())

    client_general = _FakeClient(["ok"])
    agent_general = SynthesizerAgent(
        client=client_general,
        agent_name="head-agent",
        emit_lifecycle_fn=emit_lifecycle,
        system_prompt="sys",
        stream_timeout_seconds=1.0,
        temperature_resolver=resolver,
    )

    general_payload = SynthesizerInput(
        user_message="Say hello",
        plan_text="plan",
        tool_results="",
        reduced_context="ctx",
        task_type="general",
    )

    async def _run_general() -> None:
        await agent_general.execute(general_payload, send_event=send_event, session_id="temp-2", request_id="req-2", model=None)

    asyncio.run(_run_general())

    assert client_hard.last_stream_temperature is not None
    assert client_general.last_stream_temperature is not None
    assert client_hard.last_stream_temperature < client_general.last_stream_temperature


def test_synthesizer_prompt_ab_selection_is_deterministic_per_session(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path = tmp_path / "prompt_variants.json"
    registry_path.write_text(
        json.dumps(
            {
                "synthesizer_research": [
                    {"variant_id": "v1_baseline", "prompt_text": "Baseline research prompt", "weight": 0.5},
                    {"variant_id": "v2_alt", "prompt_text": "Alternative research prompt", "weight": 0.5},
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = PromptAbRegistry(str(registry_path))
    monkeypatch.setattr("app.agents.synthesizer_agent.settings.prompt_ab_enabled", True)

    selected = [registry.select("synthesizer_research", "session-42") for _ in range(100)]
    variant_ids = {item.variant_id for item in selected if item is not None}
    assert len(variant_ids) == 1

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
        prompt_ab_registry=registry,
    )
    payload = SynthesizerInput(
        user_message="Research latest release",
        plan_text="plan",
        tool_results="source_url=https://example.com",
        reduced_context="ctx",
        task_type="research",
    )

    async def _run_once(session_id: str) -> str | None:
        await agent.execute(payload, send_event=send_event, session_id=session_id, request_id="req-ab", model=None)
        return agent.last_prompt_variant_id

    first = asyncio.run(_run_once("session-42"))
    second = asyncio.run(_run_once("session-42"))
    third = asyncio.run(_run_once("session-99"))

    assert first == second
    assert first in {"v1_baseline", "v2_alt"}
    assert third in {"v1_baseline", "v2_alt"}
