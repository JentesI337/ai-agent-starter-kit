"""SQLite-backed workflow storage — replaces JSON-file-per-workflow pattern.

Three stores in one module:
- SqliteWorkflowStore: workflow definitions (CRUD)
- SqliteWorkflowRunStore: execution state + SSE broadcasting
- SqliteWorkflowAuditStore: step/summary audit trail

Follows the raw-sqlite3 + WAL + threading.Lock pattern from long_term_memory.py.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import sqlite3
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.workflows.models import (
    StepResult,
    WorkflowExecutionState,
    WorkflowGraphDef,
    WorkflowRecord,
    WorkflowStepDef,
    WorkflowToolPolicy,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    base_agent_id TEXT DEFAULT 'head-agent',
    execution_mode TEXT DEFAULT 'parallel',
    workflow_graph TEXT,
    tool_policy TEXT,
    triggers TEXT,
    allow_subrun_delegation INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    current_step_id TEXT,
    step_results TEXT,
    status TEXT DEFAULT 'running',
    context TEXT,
    started_at TEXT DEFAULT '',
    completed_at TEXT,
    output_dir TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_wf ON workflow_runs(workflow_id, started_at DESC);

CREATE TABLE IF NOT EXISTS workflow_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    step_id TEXT,
    entry_type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_run ON workflow_audit(run_id);
"""


def _ensure_schema(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()


# ---------------------------------------------------------------------------
# WorkflowRecord ↔ row helpers
# ---------------------------------------------------------------------------

def _record_to_row(record: WorkflowRecord) -> tuple:
    graph_json = json.dumps(record.workflow_graph.model_dump(mode="json")) if record.workflow_graph else None
    tp_json = json.dumps(record.tool_policy.model_dump(mode="json")) if record.tool_policy else None
    triggers_json = json.dumps([t.model_dump(mode="json") for t in record.triggers]) if record.triggers else "[]"
    return (
        record.id, record.name, record.description,
        record.base_agent_id, record.execution_mode,
        graph_json, tp_json, triggers_json,
        int(record.allow_subrun_delegation), record.version,
        record.created_at, record.updated_at,
    )


def _row_to_record(row: tuple) -> WorkflowRecord:
    (id_, name, description, base_agent_id, execution_mode,
     graph_json, tp_json, triggers_json,
     allow_subrun, version, created_at, updated_at) = row

    workflow_graph = None
    if graph_json:
        try:
            workflow_graph = WorkflowGraphDef.model_validate(json.loads(graph_json))
        except Exception:
            logger.debug("workflow_graph_parse_failed id=%s", id_, exc_info=True)

    tool_policy = None
    if tp_json:
        with contextlib.suppress(Exception):
            tool_policy = WorkflowToolPolicy.model_validate(json.loads(tp_json))

    triggers: list[WorkflowTrigger] = []
    if triggers_json:
        try:
            triggers.extend(WorkflowTrigger.model_validate(t) for t in json.loads(triggers_json))
        except Exception:
            pass

    return WorkflowRecord(
        id=id_,
        name=name,
        description=description or "",
        base_agent_id=base_agent_id or "head-agent",
        execution_mode=execution_mode or "parallel",
        workflow_graph=workflow_graph,
        tool_policy=tool_policy,
        triggers=triggers,
        allow_subrun_delegation=bool(allow_subrun),
        version=version or 1,
        created_at=created_at or "",
        updated_at=updated_at or "",
    )


_SELECT_COLS = "id, name, description, base_agent_id, execution_mode, workflow_graph, tool_policy, triggers, allow_subrun_delegation, version, created_at, updated_at"


# ---------------------------------------------------------------------------
# SqliteWorkflowStore
# ---------------------------------------------------------------------------

class SqliteWorkflowStore:
    """SQLite workflow definition store."""

    def __init__(self, *, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        _ensure_schema(self._db_path)

    def list(self, *, limit: int = 500) -> list[WorkflowRecord]:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} FROM workflows ORDER BY updated_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        normalized = self._normalize_id(workflow_id)
        if not normalized:
            return None
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM workflows WHERE id = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def create(self, record: WorkflowRecord) -> WorkflowRecord:
        now = datetime.now(UTC).isoformat()
        record = record.model_copy(update={
            "created_at": now,
            "updated_at": now,
            "version": 1,
        })
        row = _record_to_row(record)
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            existing = conn.execute("SELECT 1 FROM workflows WHERE id = ?", (record.id,)).fetchone()
            if existing:
                raise ValueError(f"Workflow already exists: {record.id}")
            conn.execute(
                f"INSERT INTO workflows ({_SELECT_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.commit()
        return record

    def update(self, workflow_id: str, record: WorkflowRecord) -> WorkflowRecord:
        now = datetime.now(UTC).isoformat()
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            existing_row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM workflows WHERE id = ? LIMIT 1",
                (workflow_id,),
            ).fetchone()
            if existing_row is None:
                raise KeyError(f"Workflow not found: {workflow_id}")
            existing = _row_to_record(existing_row)
            record = record.model_copy(update={
                "id": workflow_id,
                "created_at": existing.created_at,
                "updated_at": now,
                "version": existing.version + 1,
            })
            row = _record_to_row(record)
            conn.execute(
                """UPDATE workflows SET name=?, description=?, base_agent_id=?,
                   execution_mode=?, workflow_graph=?, tool_policy=?, triggers=?,
                   allow_subrun_delegation=?, version=?, created_at=?, updated_at=?
                   WHERE id=?""",
                (*row[1:], row[0]),
            )
            conn.commit()
        return record

    def delete(self, workflow_id: str) -> bool:
        normalized = self._normalize_id(workflow_id)
        if not normalized:
            return False
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (normalized,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _normalize_id(raw: str) -> str:
        candidate = (raw or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate[:80]

    @staticmethod
    def _build_linear_graph(steps: list[str]) -> WorkflowGraphDef:
        graph_steps: list[WorkflowStepDef] = []
        for i, instruction in enumerate(steps):
            step_id = f"step-{i + 1}"
            next_id = f"step-{i + 2}" if i + 1 < len(steps) else None
            graph_steps.append(WorkflowStepDef(
                id=step_id, type="agent", label=f"Step {i + 1}",
                instruction=instruction, next_step=next_id,
            ))
        return WorkflowGraphDef(steps=graph_steps, entry_step_id="step-1")


# ---------------------------------------------------------------------------
# SqliteWorkflowRunStore
# ---------------------------------------------------------------------------

class SqliteWorkflowRunStore:
    """SQLite run state persistence + in-memory SSE broadcasting."""

    def __init__(self, *, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        _ensure_schema(self._db_path)
        # In-memory event queues
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._event_buffers: dict[str, list[dict]] = defaultdict(list)

    # ── Persistence ──────────────────────────────────

    def save(self, state: WorkflowExecutionState) -> None:
        step_results_json = json.dumps(
            {k: v.model_dump(mode="json") for k, v in state.step_results.items()},
            default=str,
        ) if state.step_results else "{}"
        context_json = json.dumps(state.context, default=str) if state.context else "{}"

        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO workflow_runs
                   (run_id, workflow_id, session_id, current_step_id, step_results,
                    status, context, started_at, completed_at, output_dir)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    state.run_id, state.workflow_id, state.session_id,
                    state.current_step_id, step_results_json,
                    state.status, context_json,
                    state.started_at or "", state.completed_at,
                    state.output_dir,
                ),
            )
            conn.commit()

    def get(self, workflow_id: str, run_id: str) -> WorkflowExecutionState | None:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                """SELECT run_id, workflow_id, session_id, current_step_id,
                          step_results, status, context, started_at, completed_at, output_dir
                   FROM workflow_runs WHERE run_id = ? AND workflow_id = ? LIMIT 1""",
                (run_id, workflow_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_state(row)

    def list_runs(self, workflow_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                """SELECT run_id, workflow_id, session_id, current_step_id,
                          step_results, status, context, started_at, completed_at, output_dir
                   FROM workflow_runs WHERE workflow_id = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (workflow_id, max(1, limit)),
            ).fetchall()

        runs: list[dict[str, Any]] = []
        for row in rows:
            step_results = {}
            with contextlib.suppress(Exception):
                step_results = json.loads(row[4]) if row[4] else {}
            runs.append({
                "run_id": row[0],
                "status": row[5],
                "started_at": row[7],
                "completed_at": row[8],
                "steps_completed": sum(
                    1 for r in step_results.values()
                    if isinstance(r, dict) and r.get("status") == "success"
                ),
                "steps_total": len(step_results),
            })
        return runs

    @staticmethod
    def _row_to_state(row: tuple) -> WorkflowExecutionState:
        (run_id, workflow_id, session_id, current_step_id,
         step_results_json, status, context_json,
         started_at, completed_at, output_dir) = row

        step_results = {}
        try:
            raw = json.loads(step_results_json) if step_results_json else {}
            for k, v in raw.items():
                if isinstance(v, dict):
                    step_results[k] = StepResult.model_validate(v)
        except Exception:
            pass

        context = {}
        with contextlib.suppress(Exception):
            context = json.loads(context_json) if context_json else {}

        return WorkflowExecutionState(
            workflow_id=workflow_id,
            run_id=run_id,
            session_id=session_id,
            current_step_id=current_step_id,
            step_results=step_results,
            status=status or "running",
            context=context,
            started_at=started_at or "",
            completed_at=completed_at,
            output_dir=output_dir,
        )

    # ── SSE Event Broadcasting ──────

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
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
            with contextlib.suppress(ValueError):
                subs.remove(queue)
            if not subs:
                del self._subscribers[run_id]

    async def broadcast(self, run_id: str, event: dict[str, Any]) -> None:
        self._event_buffers[run_id].append(event)
        subs = list(self._subscribers.get(run_id, []))
        for q in subs:
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(event)
        if event.get("type") in ("workflow_completed", "workflow_failed"):
            self._event_buffers.pop(run_id, None)

    def cleanup_stale_subscribers(self, run_id: str) -> None:
        subs = self._subscribers.get(run_id)
        if not subs:
            return
        self._subscribers[run_id] = [q for q in subs if not q.full()]
        if not self._subscribers[run_id]:
            del self._subscribers[run_id]

    def make_send_event(self, run_id: str) -> Any:
        store = self
        state_holder: list[WorkflowExecutionState | None] = [None]

        async def send_event(event: dict) -> None:
            await store.broadcast(run_id, event)
            event_type = event.get("type", "")
            if event_type in ("workflow_step_completed", "workflow_step_failed", "workflow_completed"):
                current_state = state_holder[0]
                if current_state is not None:
                    store.save(current_state)

        return send_event, state_holder


# ---------------------------------------------------------------------------
# SqliteWorkflowAuditStore
# ---------------------------------------------------------------------------

class SqliteWorkflowAuditStore:
    """SQLite audit trail — replaces filesystem step/summary JSON files."""

    def __init__(self, *, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        _ensure_schema(self._db_path)

    def write_step(self, *, workflow_id: str, run_id: str, step_id: str, data: dict) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT INTO workflow_audit (workflow_id, run_id, step_id, entry_type, data, created_at)
                   VALUES (?, ?, ?, 'step', ?, ?)""",
                (workflow_id, run_id, step_id, json.dumps(data, default=str), now),
            )
            conn.commit()

    def write_summary(self, *, workflow_id: str, run_id: str, data: dict) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT INTO workflow_audit (workflow_id, run_id, step_id, entry_type, data, created_at)
                   VALUES (?, ?, NULL, 'summary', ?, ?)""",
                (workflow_id, run_id, json.dumps(data, default=str), now),
            )
            conn.commit()

    def cleanup(self, workflow_id: str) -> None:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("DELETE FROM workflow_audit WHERE workflow_id = ?", (workflow_id,))
            conn.commit()

    def get_run_audit(self, run_id: str) -> list[dict]:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT step_id, entry_type, data, created_at FROM workflow_audit WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        results = []
        for step_id, entry_type, data_json, created_at in rows:
            try:
                data = json.loads(data_json)
            except Exception:
                data = {}
            results.append({
                "step_id": step_id,
                "entry_type": entry_type,
                "data": data,
                "created_at": created_at,
            })
        return results


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_wf_store: SqliteWorkflowStore | None = None
_run_store: SqliteWorkflowRunStore | None = None
_audit_store: SqliteWorkflowAuditStore | None = None
_init_lock = threading.Lock()


def init_workflow_sqlite_stores(*, db_path: str | Path) -> tuple[SqliteWorkflowStore, SqliteWorkflowRunStore, SqliteWorkflowAuditStore]:
    global _wf_store, _run_store, _audit_store
    with _init_lock:
        p = str(db_path)
        _wf_store = SqliteWorkflowStore(db_path=p)
        _run_store = SqliteWorkflowRunStore(db_path=p)
        _audit_store = SqliteWorkflowAuditStore(db_path=p)
    return _wf_store, _run_store, _audit_store


def get_workflow_store() -> SqliteWorkflowStore:
    if _wf_store is None:
        raise RuntimeError("SqliteWorkflowStore not initialized")
    return _wf_store


def get_workflow_run_store() -> SqliteWorkflowRunStore:
    if _run_store is None:
        raise RuntimeError("SqliteWorkflowRunStore not initialized")
    return _run_store


def get_workflow_audit_store() -> SqliteWorkflowAuditStore:
    if _audit_store is None:
        raise RuntimeError("SqliteWorkflowAuditStore not initialized")
    return _audit_store
