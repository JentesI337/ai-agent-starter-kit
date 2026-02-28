from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.state.snapshots import build_summary_snapshot
from app.state.task_graph import TaskGraph


class StateStore:
    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir).resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir = self.persist_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir = self.persist_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def init_run(
        self,
        *,
        run_id: str,
        session_id: str,
        request_id: str,
        user_message: str,
        runtime: str,
        model: str,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "run_id": run_id,
            "session_id": session_id,
            "request_id": request_id,
            "status": "active",
            "runtime": runtime,
            "model": model,
            "created_at": now,
            "updated_at": now,
            "input": {
                "user_message": user_message,
            },
            "task_graph": TaskGraph().to_dict(),
            "events": [],
            "error": None,
        }
        self._write_run(run_id, state)
        return state

    def append_event(self, run_id: str, event: dict) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["events"].append(event)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_run(run_id, state)
            return state

    def set_task_status(self, run_id: str, task_id: str, label: str, status: str) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            graph = TaskGraph()
            existing = state.get("task_graph", {}).get("nodes", [])
            if isinstance(existing, list):
                for item in existing:
                    if isinstance(item, dict):
                        existing_id = str(item.get("task_id", "")).strip()
                        if not existing_id:
                            continue
                        existing_label = str(item.get("label", existing_id))
                        graph.ensure_task(existing_id, existing_label)
                        existing_status = str(item.get("status", "pending"))
                        if existing_status in {"pending", "active", "completed", "failed"}:
                            graph.set_status(existing_id, existing_status)

            graph.ensure_task(task_id, label)
            if status in {"pending", "active", "completed", "failed"}:
                graph.set_status(task_id, status)
            state["task_graph"] = graph.to_dict()
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_run(run_id, state)
            return state

    def mark_completed(self, run_id: str) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["status"] = "completed"
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_run(run_id, state)
            self._write_snapshot(run_id, state)
            return state

    def mark_failed(self, run_id: str, error: str) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["status"] = "failed"
            state["error"] = error
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_run(run_id, state)
            self._write_snapshot(run_id, state)
            return state

    def _run_file(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _snapshot_file(self, run_id: str) -> Path:
        return self.snapshots_dir / f"{run_id}.summary.json"

    def _read_run(self, run_id: str) -> dict:
        file_path = self._run_file(run_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Run state not found: {run_id}")
        return json.loads(file_path.read_text(encoding="utf-8"))

    def _write_run(self, run_id: str, state: dict) -> None:
        file_path = self._run_file(run_id)
        tmp = file_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(file_path)

    def _write_snapshot(self, run_id: str, state: dict) -> None:
        snapshot = build_summary_snapshot(state)
        file_path = self._snapshot_file(run_id)
        tmp = file_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(file_path)
