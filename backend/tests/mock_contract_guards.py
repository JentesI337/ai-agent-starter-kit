from __future__ import annotations

import inspect
from collections.abc import Callable


def assert_agent_run_mock_signature_compatible(run_mock: Callable[..., object]) -> None:
    required_parameters = (
        "user_message",
        "send_event",
        "session_id",
        "request_id",
        "model",
        "tool_policy",
        "prompt_mode",
        "should_steer_interrupt",
    )
    signature = inspect.signature(run_mock)
    missing = [name for name in required_parameters if name not in signature.parameters]
    assert not missing, f"run mock signature missing parameters: {', '.join(missing)}"
