"""
External State Store — the orchestrator owns all state. Models never do.

Supports Redis / DB / JSON file backends (environment-dependent).
Default implementation uses a thread-safe in-memory store with optional
JSON file persistence.

Models receive *slices* of state only — they never read or write the full
state directly.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.orchestrator.contracts.schemas import TaskEnvelope, TaskStatus

logger = logging.getLogger(__name__)


class StateStore:
    """
    Thread-safe external state store.

    All orchestrator state lives here — not in prompts, not in model memory.
    Provides:
     - Task storage (CRUD by task_id)
     - Key-value metadata store
     - Optional JSON file persistence
    """

    def __init__(self, persist_path: str | None = None):
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskEnvelope] = {}
        self._metadata: dict[str, Any] = {}
        self._persist_path: Path | None = Path(persist_path) if persist_path else None
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def create_task(self, envelope: TaskEnvelope) -> TaskEnvelope:
        """Insert a new task. Raises if task_id already exists."""
        with self._lock:
            if envelope.task_id in self._tasks:
                raise ValueError(f"Task {envelope.task_id} already exists")
            self._tasks[envelope.task_id] = envelope
            self._persist()
            logger.debug("state_store task_created id=%s role=%s", envelope.task_id, envelope.agent_role)
            return envelope

    def get_task(self, task_id: str) -> TaskEnvelope | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update_task(self, task_id: str, **fields: Any) -> TaskEnvelope:
        """Partial update of task fields. Returns updated envelope."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Task {task_id} not found")
            updated = task.model_copy(update=fields)
            self._tasks[task_id] = updated
            self._persist()
            return updated

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            removed = self._tasks.pop(task_id, None)
            if removed:
                self._persist()
            return removed is not None

    def list_tasks(self, status: TaskStatus | None = None) -> list[TaskEnvelope]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def get_tasks_by_parent(self, parent_task_id: str) -> list[TaskEnvelope]:
        with self._lock:
            return [t for t in self._tasks.values() if t.parent_task_id == parent_task_id]

    # ------------------------------------------------------------------
    # Key-value metadata
    # ------------------------------------------------------------------

    def set_meta(self, key: str, value: Any) -> None:
        with self._lock:
            self._metadata[key] = value
            self._persist()

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._metadata.get(key, default)

    def delete_meta(self, key: str) -> bool:
        with self._lock:
            removed = self._metadata.pop(key, None)
            if removed is not None:
                self._persist()
            return removed is not None

    # ------------------------------------------------------------------
    # Bulk / query helpers
    # ------------------------------------------------------------------

    def count_tasks(self, status: TaskStatus | None = None) -> int:
        with self._lock:
            if status is None:
                return len(self._tasks)
            return sum(1 for t in self._tasks.values() if t.status == status)

    def clear(self) -> None:
        """Wipe all tasks and metadata."""
        with self._lock:
            self._tasks.clear()
            self._metadata.clear()
            self._persist()

    def generate_task_id(self) -> str:
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # State slicing — models receive slices only
    # ------------------------------------------------------------------

    def get_task_slice(self, task_id: str) -> dict[str, Any]:
        """
        Return a minimal dict suitable for injecting into a model prompt.
        Contains only what the model needs — no internal bookkeeping.
        """
        task = self.get_task(task_id)
        if task is None:
            return {}
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "agent_role": task.agent_role.value,
            "input_data": task.input_data,
            "output_data": task.output_data,
            "error": task.error,
        }

    def get_session_summary(self) -> dict[str, Any]:
        """High-level summary of all tasks for context injection."""
        with self._lock:
            total = len(self._tasks)
            by_status = {}
            for t in self._tasks.values():
                by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            return {
                "total_tasks": total,
                "by_status": by_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    # ------------------------------------------------------------------
    # Persistence (JSON file)
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        if self._persist_path is None:
            return
        try:
            data = {
                "tasks": {tid: t.model_dump(mode="json") for tid, t in self._tasks.items()},
                "metadata": self._metadata,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception:
            logger.exception("state_store persist_failed path=%s", self._persist_path)

    def _load_from_disk(self) -> None:
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for tid, tdata in raw.get("tasks", {}).items():
                self._tasks[tid] = TaskEnvelope.model_validate(tdata)
            self._metadata = raw.get("metadata", {})
            logger.info("state_store loaded %d tasks from %s", len(self._tasks), self._persist_path)
        except Exception:
            logger.exception("state_store load_failed path=%s", self._persist_path)
