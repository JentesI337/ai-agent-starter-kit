"""Persist workflow execution state and provide run history."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.orchestrator.workflow_models import WorkflowExecutionState

logger = logging.getLogger(__name__)

_instance: WorkflowRunStore | None = None
_init_lock = threading.Lock()


class WorkflowRunStore:
    """JSON-file-per-run storage + in-memory event broadcasting."""

    def __init__(self, *, persist_dir: str | Path) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # In-memory event queues for SSE subscribers (run_id -> list[asyncio.Queue])
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        # Per-run event buffer so late subscribers can replay missed events
        self._event_buffers: dict[str, list[dict]] = defaultdict(list)

    # ── Persistence ──────────────────────────────────

    def save(self, state: WorkflowExecutionState) -> None:
        wf_dir = self._persist_dir / state.workflow_id
        wf_dir.mkdir(parents=True, exist_ok=True)
        path = wf_dir / f"{state.run_id}.json"
        data = state.model_dump(mode="json")
        with self._lock:
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def get(self, workflow_id: str, run_id: str) -> WorkflowExecutionState | None:
        path = self._persist_dir / workflow_id / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkflowExecutionState.model_validate(data)
        except Exception:
            logger.debug("workflow_run_load_failed path=%s", path, exc_info=True)
            return None

    def list_runs(self, workflow_id: str, limit: int = 50) -> list[dict[str, Any]]:
        wf_dir = self._persist_dir / workflow_id
        if not wf_dir.exists():
            return []
        runs: list[dict[str, Any]] = []
        files = sorted(wf_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                runs.append({
                    "run_id": data.get("run_id"),
                    "status": data.get("status"),
                    "started_at": data.get("started_at"),
                    "completed_at": data.get("completed_at"),
                    "steps_completed": sum(
                        1 for r in (data.get("step_results") or {}).values()
                        if isinstance(r, dict) and r.get("status") == "success"
                    ),
                    "steps_total": len(data.get("step_results") or {}),
                })
            except Exception:
                continue
        return runs

    # ── SSE Event Broadcasting ───────────────────────

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        # Replay buffered events so late subscribers catch up
        for event in self._event_buffers.get(run_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                break
        self._subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id)
        if subs:
            try:
                subs.remove(queue)
            except ValueError:
                pass
            if not subs:
                del self._subscribers[run_id]

    async def broadcast(self, run_id: str, event: dict[str, Any]) -> None:
        self._event_buffers[run_id].append(event)
        subs = list(self._subscribers.get(run_id, []))  # snapshot to avoid mutation during iteration
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        # Clean up buffer on terminal events (no longer needed after run ends)
        if event.get("type") in ("workflow_completed", "workflow_failed"):
            self._event_buffers.pop(run_id, None)

    def cleanup_stale_subscribers(self, run_id: str) -> None:
        """Remove subscriber queues that are full (likely disconnected clients)."""
        subs = self._subscribers.get(run_id)
        if not subs:
            return
        self._subscribers[run_id] = [q for q in subs if not q.full()]
        if not self._subscribers[run_id]:
            del self._subscribers[run_id]

    def make_send_event(self, run_id: str) -> Any:
        """Return a (send_event, state_holder) tuple.

        The caller must set ``state_holder[0]`` to the actual execution state
        so that intermediate saves persist the correct object.
        """
        store = self
        state_holder: list[WorkflowExecutionState | None] = [None]

        async def send_event(event: dict) -> None:
            await store.broadcast(run_id, event)
            # Persist after each step completion
            event_type = event.get("type", "")
            if event_type in ("workflow_step_completed", "workflow_step_failed", "workflow_completed"):
                current_state = state_holder[0]
                if current_state is not None:
                    store.save(current_state)

        return send_event, state_holder


def init_workflow_run_store(*, persist_dir: str | Path) -> WorkflowRunStore:
    global _instance
    with _init_lock:
        _instance = WorkflowRunStore(persist_dir=persist_dir)
    return _instance


def get_workflow_run_store() -> WorkflowRunStore:
    if _instance is None:
        raise RuntimeError("WorkflowRunStore not initialized")
    return _instance
