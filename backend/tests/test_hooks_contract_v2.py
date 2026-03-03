import asyncio

import pytest

from app.agent import HeadAgent
from app.config import settings
from app.services.hook_contract import resolve_hook_execution_contract


def test_resolve_hook_execution_contract_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "hook_contract_version", "hook-contract.v2")
    monkeypatch.setattr(settings, "hook_timeout_ms_default", 1500)
    monkeypatch.setattr(settings, "hook_timeout_ms_overrides", {})
    monkeypatch.setattr(settings, "hook_failure_policy_default", "soft_fail")
    monkeypatch.setattr(settings, "hook_failure_policy_overrides", {})

    contract = resolve_hook_execution_contract(settings=settings, hook_name="before_tool_call")

    assert contract.hook_name == "before_tool_call"
    assert contract.hook_contract_version == "hook-contract.v2"
    assert contract.timeout_ms == 1500
    assert contract.failure_policy == "soft_fail"


def test_resolve_hook_execution_contract_applies_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "hook_contract_version", "hook-contract.v2")
    monkeypatch.setattr(settings, "hook_timeout_ms_default", 1500)
    monkeypatch.setattr(settings, "hook_timeout_ms_overrides", {"before_tool_call": 3210})
    monkeypatch.setattr(settings, "hook_failure_policy_default", "soft_fail")
    monkeypatch.setattr(settings, "hook_failure_policy_overrides", {"before_tool_call": "hard_fail"})

    contract = resolve_hook_execution_contract(settings=settings, hook_name="before_tool_call")

    assert contract.timeout_ms == 3210
    assert contract.failure_policy == "hard_fail"


def test_invoke_hooks_soft_fail_emits_contract_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "hook_contract_version", "hook-contract.v2")
    monkeypatch.setattr(settings, "hook_timeout_ms_default", 1500)
    monkeypatch.setattr(settings, "hook_timeout_ms_overrides", {})
    monkeypatch.setattr(settings, "hook_failure_policy_default", "soft_fail")
    monkeypatch.setattr(settings, "hook_failure_policy_overrides", {"before_tool_call": "soft_fail"})

    class _FailingHook:
        async def before_tool_call(self, payload: dict) -> None:
            raise ValueError("boom")

    events: list[dict] = []

    async def _send_event(payload: dict) -> None:
        events.append(payload)

    agent = HeadAgent()
    agent.register_hook(_FailingHook())

    asyncio.run(
        agent._invoke_hooks(
            hook_name="before_tool_call",
            send_event=_send_event,
            request_id="req-soft",
            session_id="sess-soft",
            payload={"tool": "read_file"},
        )
    )

    failed_event = next(
        event
        for event in events
        if event.get("type") == "lifecycle" and event.get("stage") == "hook_failed"
    )
    details = failed_event.get("details", {})

    assert details.get("hook_contract_version") == "hook-contract.v2"
    assert details.get("timeout_ms") == 1500
    assert details.get("failure_policy") == "soft_fail"
    assert details.get("status") == "error"


def test_invoke_hooks_hard_fail_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "hook_contract_version", "hook-contract.v2")
    monkeypatch.setattr(settings, "hook_timeout_ms_default", 1500)
    monkeypatch.setattr(settings, "hook_timeout_ms_overrides", {"before_tool_call": 5})
    monkeypatch.setattr(settings, "hook_failure_policy_default", "soft_fail")
    monkeypatch.setattr(settings, "hook_failure_policy_overrides", {"before_tool_call": "hard_fail"})

    class _SlowHook:
        async def before_tool_call(self, payload: dict) -> None:
            await asyncio.sleep(0.05)

    events: list[dict] = []

    async def _send_event(payload: dict) -> None:
        events.append(payload)

    agent = HeadAgent()
    agent.register_hook(_SlowHook())

    with pytest.raises(RuntimeError, match="Hook 'before_tool_call' timed out"):
        asyncio.run(
            agent._invoke_hooks(
                hook_name="before_tool_call",
                send_event=_send_event,
                request_id="req-hard",
                session_id="sess-hard",
                payload={"tool": "read_file"},
            )
        )

    timeout_event = next(
        event
        for event in events
        if event.get("type") == "lifecycle" and event.get("stage") == "hook_timeout"
    )
    details = timeout_event.get("details", {})

    assert details.get("hook_contract_version") == "hook-contract.v2"
    assert details.get("timeout_ms") == 5
    assert details.get("failure_policy") == "hard_fail"
    assert details.get("status") == "timeout"
