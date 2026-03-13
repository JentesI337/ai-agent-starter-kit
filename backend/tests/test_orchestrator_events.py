from __future__ import annotations

from app.orchestration.events import ErrorCategory, build_lifecycle_event, classify_error
from app.shared.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError


def test_build_lifecycle_event_has_expected_shape() -> None:
    payload = build_lifecycle_event(
        request_id="r1",
        session_id="s1",
        stage="request_received",
        details={"x": 1},
        agent="head-agent",
    )

    assert payload["type"] == "lifecycle"
    assert payload["schema"] == "lifecycle.v1"
    assert payload["run_id"] == "r1"
    assert payload["request_id"] == "r1"
    assert payload["session_id"] == "s1"
    assert payload["stage"] == "request_received"
    assert payload["phase"] == "start"
    assert payload["details"]["x"] == 1
    assert isinstance(payload["event_id"], str)
    assert payload["event_id"]
    assert "ts" in payload


def test_classify_error_maps_known_types() -> None:
    assert classify_error(GuardrailViolation("x")) == ErrorCategory.GUARDRAIL
    assert classify_error(ToolExecutionError("x")) == ErrorCategory.TOOLCHAIN
    assert classify_error(RuntimeSwitchError("x")) == ErrorCategory.RUNTIME
    assert classify_error(LlmClientError("x")) == ErrorCategory.LLM
    assert classify_error(Exception("x")) == ErrorCategory.INTERNAL
