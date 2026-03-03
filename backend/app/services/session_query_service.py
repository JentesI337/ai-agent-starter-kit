from __future__ import annotations

from app.state import StateStore


class SessionQueryService:
    def __init__(self, state_store: StateStore):
        self._state_store = state_store

    def resolve_latest_session_run(self, *, session_id: str, limit: int = 2000) -> tuple[dict | None, int, int]:
        target = (session_id or "").strip()
        if not target:
            return None, 0, 0

        runs = self._state_store.list_runs(limit=limit)
        latest: dict | None = None
        runs_count = 0
        active_runs_count = 0

        for run in runs:
            if str(run.get("session_id", "")).strip() != target:
                continue

            runs_count += 1
            if run.get("status") == "active":
                active_runs_count += 1
            if latest is None:
                latest = run

        return latest, runs_count, active_runs_count
