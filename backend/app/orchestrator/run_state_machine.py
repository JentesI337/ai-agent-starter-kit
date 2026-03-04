from __future__ import annotations

from datetime import datetime, timezone

RUN_STATE_CONTRACT_VERSION = "run-state.v1"

RUN_STATES_ORDER: tuple[str, ...] = (
    "received",
    "queued",
    "planning",
    "tool_loop",
    "synthesis",
    "finalizing",
    "persisted",
)

TERMINAL_RUN_STATES: set[str] = {"completed", "failed", "cancelled"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_run_state_from_stage(stage: str) -> str | None:
    normalized = (stage or "").strip().lower()
    if not normalized:
        return None

    if normalized.endswith("_cancelled"):
        return "cancelled"
    if normalized.endswith("_failed") or normalized.endswith("_rejected"):
        return "failed"
    if normalized in {"request_completed", "run_completed"}:
        return "completed"

    if normalized in {"request_received"}:
        return "received"
    if normalized in {
        "accepted",
        "queued",
        "inbox_enqueued",
        "run_dequeued",
        "lane_acquired",
        "request_dispatched",
    }:
        return "queued"
    if normalized.startswith("planning") or normalized.startswith("replanning") or normalized == "run_started":
        return "planning"
    if (
        normalized.startswith("tool_")
        or normalized.startswith("skills_")
        or normalized == "terminal_wait_started"
        or normalized == "terminal_wait_completed"
    ):
        return "tool_loop"
    if (
        normalized.startswith("streaming")
        or normalized.startswith("synthesis")
        or normalized.startswith("reply_shaping")
    ):
        return "synthesis"
    if normalized in {"reply_suppressed", "response_emitted", "response_stream_completed"}:
        return "finalizing"
    if normalized in {"tool_result_persisted", "run_accounted", "memory_write_applied", "memory_write_skipped"}:
        return "persisted"

    return None


def is_allowed_run_state_transition(previous: str | None, target: str) -> bool:
    prev = (previous or "").strip().lower() or None
    nxt = (target or "").strip().lower()
    if not nxt:
        return False
    if prev is None:
        return True
    if prev == nxt:
        return nxt not in TERMINAL_RUN_STATES

    if prev in TERMINAL_RUN_STATES:
        return False
    if nxt in {"failed", "cancelled", "completed"}:
        return True

    if prev not in RUN_STATES_ORDER or nxt not in RUN_STATES_ORDER:
        return False
    return RUN_STATES_ORDER.index(nxt) >= RUN_STATES_ORDER.index(prev)


def build_stage_event(*, run_id: str, session_id: str, stage: str, status: str | None = None, ts: str | None = None) -> dict:
    return {
        "type": "stage_event",
        "schema": "stage_event.v1",
        "run_id": run_id,
        "session_id": session_id,
        "stage": stage,
        "event": "stage_event",
        "status": status or "ok",
        "timestamp": ts or _iso_now(),
        "contract_version": RUN_STATE_CONTRACT_VERSION,
    }


def build_run_state_event(
    *,
    run_id: str,
    session_id: str,
    stage: str,
    previous_state: str | None,
    target_state: str,
    allowed: bool,
    reason: str | None = None,
    ts: str | None = None,
) -> dict:
    return {
        "type": "run_state_event",
        "schema": "run_state_event.v1",
        "run_id": run_id,
        "session_id": session_id,
        "stage": stage,
        "event": "run_state_transition",
        "status": "ok" if allowed else "failed",
        "from": previous_state,
        "to": target_state,
        "allowed": allowed,
        "reason": reason,
        "timestamp": ts or _iso_now(),
        "latency_ms": 0,
        "contract_version": RUN_STATE_CONTRACT_VERSION,
    }


def build_run_state_violation(
    *,
    run_id: str,
    session_id: str,
    stage: str,
    previous_state: str | None,
    target_state: str,
    ts: str | None = None,
) -> dict:
    return {
        "type": "run_state_violation",
        "schema": "run_state_violation.v1",
        "run_id": run_id,
        "session_id": session_id,
        "stage": stage,
        "event": "run_state_violation",
        "status": "failed",
        "from": previous_state,
        "to": target_state,
        "reason": "invalid_transition",
        "timestamp": ts or _iso_now(),
        "latency_ms": 0,
        "contract_version": RUN_STATE_CONTRACT_VERSION,
    }
