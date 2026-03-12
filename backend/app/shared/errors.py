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


# T2.3: Typisierte LLM-Fehler für direkten reason-Abruf (kein String-Matching nötig)
# Alle Unterklassen definieren 'reason' als Klassen-Attribut.
# FallbackStateMachine prüft hasattr(exc, 'reason') vor String-Klassifizierung.
class LlmContextOverflowError(LlmClientError):
    reason: str = "context_overflow"


class LlmCompactionFailureError(LlmClientError):
    reason: str = "compaction_failure"


class LlmTruncationRequiredError(LlmClientError):
    reason: str = "truncation_required"


class LlmRateLimitError(LlmClientError):
    reason: str = "rate_limited"


class LlmModelNotFoundError(LlmClientError):
    reason: str = "model_not_found"


class ClientDisconnectedError(Exception):
    """Raised by send_event when the WebSocket connection is no longer alive.

    Must NOT be caught by retry/fallback logic — the client has gone away and
    no further events can be delivered.
    """


class LlmTimeoutError(LlmClientError):
    reason: str = "timeout"


class LlmTemporarilyUnavailableError(LlmClientError):
    reason: str = "temporary_unavailable"


class LlmResourceExhaustedError(LlmClientError):
    reason: str = "resource_exhausted"


class RuntimeSwitchError(AppError):
    pass


class PolicyApprovalCancelledError(AppError):
    pass
