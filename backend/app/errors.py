from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": self.message}
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.details:
            payload["details"] = dict(self.details)
        return payload


class GuardrailViolation(AppError):
    pass


class ToolExecutionError(AppError):
    pass


class LlmClientError(AppError):
    pass


class RuntimeSwitchError(AppError):
    pass


class PolicyApprovalCancelledError(AppError):
    pass
