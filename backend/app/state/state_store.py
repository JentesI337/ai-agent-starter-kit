from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.config import settings
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
        meta: dict | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        transformed_message = self._transform_value(user_message)
        transformed_meta = self._transform_value(meta or {})
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
                "user_message": transformed_message,
            },
            "task_graph": TaskGraph().to_dict(),
            "events": [],
            "error": None,
            "meta": transformed_meta,
        }
        self._write_run(run_id, state)
        return state

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            try:
                return self._read_run(run_id)
            except FileNotFoundError:
                return None

    def list_runs(self, limit: int = 200) -> list[dict]:
        items: list[dict] = []
        for run_file in sorted(self.runs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
            if len(items) >= max(1, limit):
                break
            try:
                items.append(json.loads(run_file.read_text(encoding="utf-8")))
            except Exception:
                continue
        return items

    def append_event(self, run_id: str, event: dict) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["events"].append(self._transform_value(event))
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
            state["error"] = self._transform_value(error, key="error")
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_run(run_id, state)
            self._write_snapshot(run_id, state)
            return state

    def clear_all(self) -> None:
        with self._lock:
            for run_file in self.runs_dir.glob("*.json"):
                try:
                    run_file.unlink(missing_ok=True)
                except Exception:
                    continue
            for snapshot_file in self.snapshots_dir.glob("*.json"):
                try:
                    snapshot_file.unlink(missing_ok=True)
                except Exception:
                    continue

    def _transform_value(self, value, key: str | None = None):
        if isinstance(value, str):
            return self._transform_string(value, key=key)
        if isinstance(value, list):
            return [self._transform_value(item, key=key) for item in value]
        if isinstance(value, dict):
            transformed: dict[str, object] = {}
            for item_key, item in value.items():
                normalized_key = str(item_key)
                transformed[normalized_key] = self._transform_value(item, key=normalized_key)
            return transformed
        return value

    def _transform_string(self, value: str, key: str | None = None) -> str:
        text = value
        if settings.persist_transform_redact_secrets:
            if self._is_sensitive_key(key):
                text = "[REDACTED]"
            else:
                text = self._redact_secret_like_values(text)

        max_chars = max(64, int(settings.persist_transform_max_string_chars))
        if len(text) > max_chars:
            omitted = len(text) - max_chars
            text = f"{text[:max_chars]}...[truncated:{omitted}]"
        return text

    def _is_sensitive_key(self, key: str | None) -> bool:
        if not key:
            return False
        normalized = key.strip().lower()
        markers = ("password", "secret", "token", "api_key", "apikey", "authorization", "auth")
        return any(marker in normalized for marker in markers)

    def _redact_secret_like_values(self, value: str) -> str:
        text = value
        text = re.sub(
            r"(?i)(api[_-]?key|token|password|secret)\s*([:=])\s*([^\s,;\"']+)",
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
            text,
        )
        text = re.sub(r"(?i)bearer\s+[a-z0-9\-_.=]+", "Bearer [REDACTED]", text)
        return text

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
