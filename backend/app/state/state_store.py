from __future__ import annotations

import contextlib
import heapq
import json
import re
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from app.config import settings
from app.state.encryption import decrypt_state, encrypt_state
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
        self._run_index: dict[str, float] = {}
        self._run_index_dirty = True

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
        now = datetime.now(UTC).isoformat()
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
        with self._lock:
            self._write_run(run_id, state)
        return state

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            try:
                return self._read_run(run_id)
            except FileNotFoundError:
                return None

    def list_runs(self, limit: int = 200) -> list[dict]:
        with self._lock:
            if self._run_index_dirty:
                self._rebuild_run_index()

            cap = max(1, limit)
            ordered_ids = [
                run_id for run_id, _ in heapq.nlargest(cap, self._run_index.items(), key=lambda item: item[1])
            ]

            items: list[dict] = []
            stale_ids: list[str] = []
            for run_id in ordered_ids:
                try:
                    items.append(self._read_run(run_id))
                except FileNotFoundError:
                    stale_ids.append(run_id)
                except Exception:
                    continue

            for run_id in stale_ids:
                self._run_index.pop(run_id, None)

            return items

    def append_event(self, run_id: str, event: dict) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["events"].append(self._transform_value(event))
            state["updated_at"] = datetime.now(UTC).isoformat()
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
                        existing_created_at = str(item.get("created_at", "")).strip() or None
                        graph.ensure_task(existing_id, existing_label, created_at=existing_created_at)
                        existing_status = str(item.get("status", "pending"))
                        if existing_status in {"pending", "active", "completed", "failed"}:
                            graph.set_status(existing_id, existing_status)

            graph.ensure_task(task_id, label)
            if status in {"pending", "active", "completed", "failed"}:
                graph.set_status(task_id, status)
            state["task_graph"] = graph.to_dict()
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._write_run(run_id, state)
            return state

    def mark_completed(self, run_id: str) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["status"] = "completed"
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._write_run(run_id, state)
            self._write_snapshot(run_id, state)
            return state

    def mark_failed(self, run_id: str, error: str) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            state["status"] = "failed"
            state["error"] = self._transform_value(error, key="error")
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._write_run(run_id, state)
            self._write_snapshot(run_id, state)
            return state

    def patch_run_meta(self, run_id: str, meta_patch: dict | None) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            current_meta = state.get("meta")
            if not isinstance(current_meta, dict):
                current_meta = {}

            if isinstance(meta_patch, dict):
                for key, value in meta_patch.items():
                    current_meta[str(key)] = self._transform_value(value, key=str(key))

            state["meta"] = current_meta
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._write_run(run_id, state)
            return state

    def set_run_meta(self, run_id: str, meta: dict | None) -> dict:
        with self._lock:
            state = self._read_run(run_id)
            transformed_meta = self._transform_value(meta or {})
            state["meta"] = transformed_meta
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._write_run(run_id, state)
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
            self._run_index.clear()
            self._run_index_dirty = True

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
            text = "[REDACTED]" if self._is_sensitive_key(key) else self._redact_secret_like_values(text)

        max_chars = max(64, int(settings.persist_transform_max_string_chars))
        if len(text) > max_chars:
            omitted = len(text) - max_chars
            text = f"{text[:max_chars]}...[truncated:{omitted}]"
        return text

    _SENSITIVE_KEY_RE = re.compile(
        r"(?:^|_|-)(password|secret|token|api_key|apikey|authorization|auth_token)(?:$|_|-)",
        re.IGNORECASE,
    )

    def _is_sensitive_key(self, key: str | None) -> bool:
        if not key:
            return False
        return bool(self._SENSITIVE_KEY_RE.search(key.strip()))

    def _redact_secret_like_values(self, value: str) -> str:
        text = value
        text = re.sub(
            r"(?i)(api[_-]?key|token|password|secret)\s*([:=])\s*([^\s,;\"']+)",
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
            text,
        )
        return re.sub(r"(?i)bearer\s+[a-z0-9\-_.=]+", "Bearer [REDACTED]", text)

    # SEC (STATE-01): Validate run_id format to prevent path traversal
    _SAFE_RUN_ID = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")

    def _validate_run_id(self, run_id: str) -> None:
        if not self._SAFE_RUN_ID.match(run_id):
            raise ValueError(f"Invalid run_id format: {run_id!r}")

    def _run_file(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self.runs_dir / f"{run_id}.json"

    def _snapshot_file(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self.snapshots_dir / f"{run_id}.summary.json"

    def _read_run(self, run_id: str) -> dict:
        file_path = self._run_file(run_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Run state not found: {run_id}")
        raw = file_path.read_text(encoding="utf-8")
        # SEC (OE-08): Decrypt state at rest
        decrypted = decrypt_state(raw)
        return json.loads(decrypted)

    def _write_run(self, run_id: str, state: dict) -> None:
        file_path = self._run_file(run_id)
        tmp = file_path.with_suffix(".tmp")
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        # SEC (OE-08): Encrypt state at rest
        encrypted = encrypt_state(payload)
        tmp.write_text(encrypted, encoding="utf-8")
        self._replace_with_retry(tmp, file_path)
        # SEC (STATE-02): Restrict file permissions to owner-only on non-Windows
        self._restrict_file_permissions(file_path)
        self._run_index_dirty = True

    def _rebuild_run_index(self) -> None:
        index: dict[str, float] = {}
        for run_file in self.runs_dir.glob("*.json"):
            try:
                index[run_file.stem] = run_file.stat().st_mtime
            except Exception:
                continue
        self._run_index = index
        self._run_index_dirty = False

    def _write_snapshot(self, run_id: str, state: dict) -> None:
        snapshot = build_summary_snapshot(state)
        file_path = self._snapshot_file(run_id)
        tmp = file_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        self._replace_with_retry(tmp, file_path)
        # SEC (STATE-02): Restrict file permissions to owner-only on non-Windows
        self._restrict_file_permissions(file_path)

    def _replace_with_retry(self, tmp: Path, target: Path) -> None:
        delays = (0.005, 0.02, 0.05)
        last_error: PermissionError | None = None
        for delay in delays:
            try:
                tmp.replace(target)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(delay)

        if last_error is not None:
            raise last_error

    @staticmethod
    def _restrict_file_permissions(file_path: Path) -> None:
        """SEC (STATE-02): Set file permissions to owner-only (0o600) on non-Windows systems."""
        import os as _os

        if _os.name != "nt":
            import stat as _stat

            with contextlib.suppress(OSError):
                file_path.chmod(_stat.S_IRUSR | _stat.S_IWUSR)


class SqliteStateStore(StateStore):
    def __init__(self, persist_dir: str, db_filename: str = "state_store.sqlite3"):
        super().__init__(persist_dir=persist_dir)
        self._db_path = (self.persist_dir / db_filename).resolve()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at_ts REAL NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_updated_at_ts ON runs(updated_at_ts DESC)")

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
        now = datetime.now(UTC).isoformat()
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
        with self._lock:
            self._upsert_run(run_id=run_id, state=state)
        return state

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT state_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            # SEC (OE-08): Decrypt state at rest
            decrypted = decrypt_state(str(row["state_json"]))
            return json.loads(decrypted)

    def list_runs(self, limit: int = 200) -> list[dict]:
        with self._lock:
            cap = max(1, int(limit))
            rows = self._conn.execute(
                "SELECT state_json FROM runs ORDER BY updated_at_ts DESC LIMIT ?",
                (cap,),
            ).fetchall()
            items: list[dict] = []
            for row in rows:
                try:
                    # SEC (OE-08): Decrypt state at rest
                    decrypted = decrypt_state(str(row["state_json"]))
                    items.append(json.loads(decrypted))
                except Exception:
                    continue
            return items

    def append_event(self, run_id: str, event: dict) -> dict:
        with self._lock:
            state = self._require_run(run_id)
            state["events"].append(self._transform_value(event))
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._upsert_run(run_id=run_id, state=state)
            return state

    def set_task_status(self, run_id: str, task_id: str, label: str, status: str) -> dict:
        with self._lock:
            state = self._require_run(run_id)
            graph = TaskGraph()
            existing = state.get("task_graph", {}).get("nodes", [])
            if isinstance(existing, list):
                for item in existing:
                    if isinstance(item, dict):
                        existing_id = str(item.get("task_id", "")).strip()
                        if not existing_id:
                            continue
                        existing_label = str(item.get("label", existing_id))
                        existing_created_at = str(item.get("created_at", "")).strip() or None
                        graph.ensure_task(existing_id, existing_label, created_at=existing_created_at)
                        existing_status = str(item.get("status", "pending"))
                        if existing_status in {"pending", "active", "completed", "failed"}:
                            graph.set_status(existing_id, existing_status)

            graph.ensure_task(task_id, label)
            if status in {"pending", "active", "completed", "failed"}:
                graph.set_status(task_id, status)
            state["task_graph"] = graph.to_dict()
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._upsert_run(run_id=run_id, state=state)
            return state

    def mark_completed(self, run_id: str) -> dict:
        with self._lock:
            state = self._require_run(run_id)
            state["status"] = "completed"
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._upsert_run(run_id=run_id, state=state)
            self._write_snapshot(run_id, state)
            return state

    def mark_failed(self, run_id: str, error: str) -> dict:
        with self._lock:
            state = self._require_run(run_id)
            state["status"] = "failed"
            state["error"] = self._transform_value(error, key="error")
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._upsert_run(run_id=run_id, state=state)
            self._write_snapshot(run_id, state)
            return state

    def patch_run_meta(self, run_id: str, meta_patch: dict | None) -> dict:
        with self._lock:
            state = self._require_run(run_id)
            current_meta = state.get("meta")
            if not isinstance(current_meta, dict):
                current_meta = {}

            if isinstance(meta_patch, dict):
                for key, value in meta_patch.items():
                    current_meta[str(key)] = self._transform_value(value, key=str(key))

            state["meta"] = current_meta
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._upsert_run(run_id=run_id, state=state)
            return state

    def set_run_meta(self, run_id: str, meta: dict | None) -> dict:
        with self._lock:
            state = self._require_run(run_id)
            state["meta"] = self._transform_value(meta or {})
            state["updated_at"] = datetime.now(UTC).isoformat()
            self._upsert_run(run_id=run_id, state=state)
            return state

    def clear_all(self) -> None:
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM runs")
            for snapshot_file in self.snapshots_dir.glob("*.json"):
                try:
                    snapshot_file.unlink(missing_ok=True)
                except Exception:
                    continue

    def _require_run(self, run_id: str) -> dict:
        row = self._conn.execute("SELECT state_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"Run state not found: {run_id}")
        # SEC (OE-08): Decrypt state at rest
        decrypted = decrypt_state(str(row["state_json"]))
        return json.loads(decrypted)

    def _upsert_run(self, *, run_id: str, state: dict) -> None:
        updated_at_ts = datetime.now(UTC).timestamp()
        payload = json.dumps(state, ensure_ascii=False)
        # SEC (OE-08): Encrypt state at rest
        encrypted = encrypt_state(payload)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO runs(run_id, state_json, updated_at_ts)
                VALUES(?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at_ts=excluded.updated_at_ts
                """,
                (run_id, encrypted, updated_at_ts),
            )
