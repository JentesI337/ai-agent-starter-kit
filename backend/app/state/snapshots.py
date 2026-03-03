from __future__ import annotations

from datetime import datetime, timezone


def build_summary_snapshot(run_state: dict) -> dict:
    events = run_state.get("events", []) if isinstance(run_state, dict) else []
    stages: list[str] = []
    for event in events:
        if isinstance(event, dict):
            stage = event.get("stage")
            if isinstance(stage, str) and stage:
                stages.append(stage)

    return {
        "snapshot_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_state.get("run_id") if isinstance(run_state, dict) else None,
        "session_id": run_state.get("session_id") if isinstance(run_state, dict) else None,
        "request_id": run_state.get("request_id") if isinstance(run_state, dict) else None,
        "status": run_state.get("status") if isinstance(run_state, dict) else None,
        "stage_count": len(stages),
        "last_stage": stages[-1] if stages else None,
        "event_count": len(events),
    }
