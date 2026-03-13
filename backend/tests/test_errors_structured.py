from __future__ import annotations

from app.shared.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError


def test_error_classes_keep_message_string_compatibility() -> None:
    exc = ToolExecutionError("tool failed")

    assert str(exc) == "tool failed"
    assert exc.message == "tool failed"
    assert exc.error_code is None
    assert exc.details == {}


def test_error_classes_support_structured_metadata() -> None:
    exc = RuntimeSwitchError(
        "runtime auth missing",
        error_code="runtime.auth.required",
        details={"runtime": "api", "hint": "set API_AUTH_TOKEN"},
    )

    assert str(exc) == "runtime auth missing"
    assert exc.error_code == "runtime.auth.required"
    assert exc.details["runtime"] == "api"

    payload = exc.to_dict()
    assert payload["message"] == "runtime auth missing"
    assert payload["error_code"] == "runtime.auth.required"
    assert payload["details"]["hint"] == "set API_AUTH_TOKEN"


def test_all_public_error_types_inherit_same_structured_shape() -> None:
    errors = [
        GuardrailViolation("guardrail"),
        ToolExecutionError("tool"),
        LlmClientError("llm"),
        RuntimeSwitchError("runtime"),
    ]

    for exc in errors:
        assert hasattr(exc, "message")
        assert hasattr(exc, "error_code")
        assert hasattr(exc, "details")
        assert isinstance(exc.to_dict(), dict)
