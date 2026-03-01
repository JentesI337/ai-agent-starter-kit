from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import uuid

from app.errors import GuardrailViolation, LlmClientError, RuntimeSwitchError, ToolExecutionError


class LifecycleStage(StrEnum):
    RUN_STARTED = "run_started"
    GUARDRAILS_PASSED = "guardrails_passed"
    TOOLCHAIN_CHECKED = "toolchain_checked"
    MEMORY_UPDATED = "memory_updated"
    CONTEXT_REDUCED = "context_reduced"
    PLANNING_STARTED = "planning_started"
    PLANNING_COMPLETED = "planning_completed"
    TOOL_SELECTION_STARTED = "tool_selection_started"
    TOOL_SELECTION_COMPLETED = "tool_selection_completed"
    TOOL_SELECTION_PARSE_FAILED = "tool_selection_parse_failed"
    TOOL_SELECTION_REPAIR_STARTED = "tool_selection_repair_started"
    TOOL_SELECTION_REPAIR_COMPLETED = "tool_selection_repair_completed"
    TOOL_SELECTION_REPAIR_FAILED = "tool_selection_repair_failed"
    TOOL_SELECTION_EMPTY = "tool_selection_empty"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    STREAMING_STARTED = "streaming_started"
    STREAMING_COMPLETED = "streaming_completed"
    RUN_COMPLETED = "run_completed"
    REQUEST_RECEIVED = "request_received"
    REQUEST_DISPATCHED = "request_dispatched"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_FAILED = "request_failed"
    REQUEST_FAILED_GUARDRAIL = "request_failed_guardrail"
    REQUEST_FAILED_TOOLCHAIN = "request_failed_toolchain"
    REQUEST_FAILED_LLM = "request_failed_llm"
    MODEL_ROUTE_SELECTED = "model_route_selected"
    MODEL_FALLBACK_RETRY = "model_fallback_retry"


class ErrorCategory(StrEnum):
    GUARDRAIL = "guardrail"
    TOOLCHAIN = "toolchain"
    RUNTIME = "runtime"
    LLM = "llm"
    INTERNAL = "internal"


def build_lifecycle_event(
    *,
    request_id: str,
    session_id: str,
    stage: str,
    details: dict | None = None,
    agent: str | None = None,
) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    phase = "progress"
    if stage.endswith("_started") or stage.endswith("_received") or stage.endswith("_requested"):
        phase = "start"
    elif stage.endswith("_completed") or stage.endswith("_done"):
        phase = "end"
    elif stage.endswith("_failed") or stage.endswith("_rejected"):
        phase = "error"

    payload = {
        "type": "lifecycle",
        "schema": "lifecycle.v1",
        "event_id": str(uuid.uuid4()),
        "phase": phase,
        "stage": stage,
        "request_id": request_id,
        "run_id": request_id,
        "session_id": session_id,
        "ts": ts,
        "details": details or {},
    }
    if agent:
        payload["agent"] = agent
    return payload


def classify_error(error: Exception) -> ErrorCategory:
    if isinstance(error, GuardrailViolation):
        return ErrorCategory.GUARDRAIL
    if isinstance(error, ToolExecutionError):
        return ErrorCategory.TOOLCHAIN
    if isinstance(error, RuntimeSwitchError):
        return ErrorCategory.RUNTIME
    if isinstance(error, LlmClientError):
        return ErrorCategory.LLM
    return ErrorCategory.INTERNAL


def build_orchestrator_event(*, request_id: str, session_id: str, stage: str, details: dict | None = None) -> dict:
    return build_lifecycle_event(
        request_id=request_id,
        session_id=session_id,
        stage=stage,
        details=details,
    )
