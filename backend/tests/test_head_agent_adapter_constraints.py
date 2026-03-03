from __future__ import annotations

from app.agents.head_agent_adapter import CoderAgentAdapter, HeadAgentAdapter, ReviewAgentAdapter
from app.config import settings


class _DummyDelegate:
    def __init__(self, name: str):
        self.name = name

    def configure_runtime(self, base_url: str, model: str) -> None:
        return None

    async def run(
        self,
        user_message,
        send_event,
        session_id,
        request_id,
        model=None,
        tool_policy=None,
        prompt_mode=None,
        should_steer_interrupt=None,
    ):
        return "ok"


def test_adapter_constraints_resolve_max_context_from_current_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_user_message_length", 2048)

    head = HeadAgentAdapter(delegate=_DummyDelegate("head"))
    coder = CoderAgentAdapter(delegate=_DummyDelegate("coder"))
    review = ReviewAgentAdapter(delegate=_DummyDelegate("review"))

    assert head.constraints.max_context == 2048
    assert coder.constraints.max_context == 2048
    assert review.constraints.max_context == 2048


def test_adapter_constraints_keep_role_specific_temperature_and_reflection() -> None:
    head = HeadAgentAdapter(delegate=_DummyDelegate("head"))
    coder = CoderAgentAdapter(delegate=_DummyDelegate("coder"))
    review = ReviewAgentAdapter(delegate=_DummyDelegate("review"))

    assert head.constraints.temperature == 0.3
    assert head.constraints.reflection_passes == 0
    assert coder.constraints.temperature == 0.3
    assert coder.constraints.reflection_passes == 0
    assert review.constraints.temperature == 0.2
    assert review.constraints.reflection_passes == 1
