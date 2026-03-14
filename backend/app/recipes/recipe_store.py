"""SQLite-backed recipe storage — CRUD for recipe definitions and run state.

Follows the same raw-sqlite3 + WAL + threading.Lock pattern as store.py.
Uses a separate DB file (recipe_store.sqlite3) to avoid schema collisions.
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

from app.recipes.recipe_models import (
    BudgetSnapshot,
    CheckpointResult,
    RecipeCheckpoint,
    RecipeConstraints,
    RecipeDef,
    RecipeRunState,
    StrictStep,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    goal TEXT DEFAULT '',
    mode TEXT DEFAULT 'adaptive',
    constraints TEXT,
    checkpoints TEXT,
    strict_steps TEXT,
    agent_id TEXT DEFAULT NULL,
    triggers TEXT,
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_runs (
    run_id TEXT PRIMARY KEY,
    recipe_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    mode TEXT DEFAULT 'adaptive',
    checkpoints_reached TEXT,
    step_results TEXT,
    current_step_id TEXT,
    context TEXT,
    pause_reason TEXT,
    pause_data TEXT,
    paused_at TEXT,
    started_at TEXT DEFAULT '',
    completed_at TEXT,
    budget_used TEXT
);
CREATE INDEX IF NOT EXISTS idx_recipe_runs_recipe ON recipe_runs(recipe_id, started_at DESC);
"""


def _ensure_schema(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA_SQL)
        # Migration: add paused_at column if missing (pre-M5 DBs)
        try:
            conn.execute("ALTER TABLE recipe_runs ADD COLUMN paused_at TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()


# ---------------------------------------------------------------------------
# ID normalization
# ---------------------------------------------------------------------------

def _normalize_id(raw: str) -> str:
    candidate = (raw or "").strip().lower()
    candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
    candidate = re.sub(r"-+", "-", candidate).strip("-")
    return candidate[:80]


# ---------------------------------------------------------------------------
# RecipeDef ↔ row helpers
# ---------------------------------------------------------------------------

_SELECT_COLS = (
    "id, name, description, goal, mode, constraints, checkpoints, "
    "strict_steps, agent_id, triggers, version, created_at, updated_at"
)


def _recipe_to_row(r: RecipeDef) -> tuple:
    return (
        r.id, r.name, r.description, r.goal, r.mode,
        json.dumps(r.constraints.model_dump(mode="json")) if r.constraints else "{}",
        json.dumps([c.model_dump(mode="json") for c in r.checkpoints]) if r.checkpoints else "[]",
        json.dumps([s.model_dump(mode="json") for s in r.strict_steps]) if r.strict_steps else None,
        r.agent_id,
        json.dumps(r.triggers) if r.triggers else "[]",
        r.version,
        r.created_at,
        r.updated_at,
    )


def _row_to_recipe(row: tuple) -> RecipeDef:
    (id_, name, description, goal, mode,
     constraints_json, checkpoints_json, strict_steps_json,
     agent_id, triggers_json, version, created_at, updated_at) = row

    constraints = RecipeConstraints()
    if constraints_json:
        with contextlib.suppress(Exception):
            constraints = RecipeConstraints.model_validate(json.loads(constraints_json))

    checkpoints: list[RecipeCheckpoint] = []
    if checkpoints_json:
        try:
            checkpoints = [RecipeCheckpoint.model_validate(c) for c in json.loads(checkpoints_json)]
        except Exception:
            pass

    strict_steps: list[StrictStep] | None = None
    if strict_steps_json:
        try:
            strict_steps = [StrictStep.model_validate(s) for s in json.loads(strict_steps_json)]
        except Exception:
            pass

    triggers: list[dict[str, Any]] = []
    if triggers_json:
        with contextlib.suppress(Exception):
            triggers = json.loads(triggers_json)

    return RecipeDef(
        id=id_,
        name=name,
        description=description or "",
        goal=goal or "",
        mode=mode or "adaptive",
        constraints=constraints,
        checkpoints=checkpoints,
        strict_steps=strict_steps,
        agent_id=agent_id,
        triggers=triggers,
        version=version or 1,
        created_at=created_at or "",
        updated_at=updated_at or "",
    )


# ---------------------------------------------------------------------------
# SqliteRecipeStore
# ---------------------------------------------------------------------------

class SqliteRecipeStore:
    """CRUD for recipe definitions."""

    def __init__(self, *, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        _ensure_schema(self._db_path)

    def list(self, *, limit: int = 500) -> list[RecipeDef]:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} FROM recipes ORDER BY updated_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [_row_to_recipe(r) for r in rows]

    def get(self, recipe_id: str) -> RecipeDef | None:
        normalized = _normalize_id(recipe_id)
        if not normalized:
            return None
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM recipes WHERE id = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        return _row_to_recipe(row) if row else None

    def create(self, recipe: RecipeDef) -> RecipeDef:
        now = datetime.now(UTC).isoformat()
        recipe = recipe.model_copy(update={
            "created_at": now,
            "updated_at": now,
            "version": 1,
        })
        row = _recipe_to_row(recipe)
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            existing = conn.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe.id,)).fetchone()
            if existing:
                raise ValueError(f"Recipe already exists: {recipe.id}")
            conn.execute(
                f"INSERT INTO recipes ({_SELECT_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.commit()
        return recipe

    def update(self, recipe_id: str, recipe: RecipeDef) -> RecipeDef:
        now = datetime.now(UTC).isoformat()
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            existing_row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM recipes WHERE id = ? LIMIT 1",
                (recipe_id,),
            ).fetchone()
            if existing_row is None:
                raise KeyError(f"Recipe not found: {recipe_id}")
            existing = _row_to_recipe(existing_row)
            recipe = recipe.model_copy(update={
                "id": recipe_id,
                "created_at": existing.created_at,
                "updated_at": now,
                "version": existing.version + 1,
            })
            row = _recipe_to_row(recipe)
            conn.execute(
                """UPDATE recipes SET name=?, description=?, goal=?, mode=?,
                   constraints=?, checkpoints=?, strict_steps=?, agent_id=?,
                   triggers=?, version=?, created_at=?, updated_at=?
                   WHERE id=?""",
                (*row[1:], row[0]),
            )
            conn.commit()
        return recipe

    def delete(self, recipe_id: str) -> bool:
        normalized = _normalize_id(recipe_id)
        if not normalized:
            return False
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute("DELETE FROM recipes WHERE id = ?", (normalized,))
            conn.commit()
            return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# SqliteRecipeRunStore
# ---------------------------------------------------------------------------

class SqliteRecipeRunStore:
    """Recipe run state persistence + in-memory SSE broadcasting."""

    def __init__(self, *, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        _ensure_schema(self._db_path)
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._event_buffers: dict[str, list[dict]] = defaultdict(list)

    # ── Persistence ──────────────────────────────────

    def save(self, state: RecipeRunState) -> None:
        checkpoints_json = json.dumps(
            {k: v.model_dump(mode="json") for k, v in state.checkpoints_reached.items()},
            default=str,
        ) if state.checkpoints_reached else "{}"
        step_results_json = json.dumps(state.step_results, default=str) if state.step_results else "{}"
        context_json = json.dumps(state.context, default=str) if state.context else "{}"
        pause_data_json = json.dumps(state.pause_data, default=str) if state.pause_data else None
        budget_json = json.dumps(state.budget_used.model_dump(mode="json")) if state.budget_used else "{}"

        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO recipe_runs
                   (run_id, recipe_id, session_id, status, mode,
                    checkpoints_reached, step_results, current_step_id,
                    context, pause_reason, pause_data, paused_at,
                    started_at, completed_at, budget_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    state.run_id, state.recipe_id, state.session_id,
                    state.status, state.mode,
                    checkpoints_json, step_results_json, state.current_step_id,
                    context_json, state.pause_reason, pause_data_json,
                    state.paused_at,
                    state.started_at or "", state.completed_at, budget_json,
                ),
            )
            conn.commit()

    def get(self, recipe_id: str, run_id: str) -> RecipeRunState | None:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                """SELECT run_id, recipe_id, session_id, status, mode,
                          checkpoints_reached, step_results, current_step_id,
                          context, pause_reason, pause_data, paused_at,
                          started_at, completed_at, budget_used
                   FROM recipe_runs WHERE run_id = ? AND recipe_id = ? LIMIT 1""",
                (run_id, recipe_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_state(row)

    def get_by_run_id(self, run_id: str) -> RecipeRunState | None:
        """Look up a run by run_id only (no recipe_id needed)."""
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                """SELECT run_id, recipe_id, session_id, status, mode,
                          checkpoints_reached, step_results, current_step_id,
                          context, pause_reason, pause_data, paused_at,
                          started_at, completed_at, budget_used
                   FROM recipe_runs WHERE run_id = ? LIMIT 1""",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_state(row)

    def list_active_runs(self) -> list[RecipeRunState]:
        """Return all running or paused runs."""
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                """SELECT run_id, recipe_id, session_id, status, mode,
                          checkpoints_reached, step_results, current_step_id,
                          context, pause_reason, pause_data, paused_at,
                          started_at, completed_at, budget_used
                   FROM recipe_runs WHERE status IN ('running', 'paused')""",
            ).fetchall()
        return [self._row_to_state(r) for r in rows]

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a run by setting status to 'cancelled' and completed_at."""
        now = datetime.now(UTC).isoformat()
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute(
                "UPDATE recipe_runs SET status = 'cancelled', completed_at = ? WHERE run_id = ?",
                (now, run_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_old_runs(self, before_iso: str) -> int:
        """Delete completed/failed/cancelled runs older than before_iso."""
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute(
                """DELETE FROM recipe_runs
                   WHERE status IN ('completed', 'failed', 'cancelled')
                   AND completed_at < ?""",
                (before_iso,),
            )
            conn.commit()
            return cursor.rowcount

    def list_runs(self, recipe_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                """SELECT run_id, status, mode, started_at, completed_at, budget_used,
                          pause_reason, paused_at
                   FROM recipe_runs WHERE recipe_id = ?
                   ORDER BY started_at DESC LIMIT ?""",
                (recipe_id, max(1, limit)),
            ).fetchall()

        runs: list[dict[str, Any]] = []
        for row in rows:
            budget = {}
            with contextlib.suppress(Exception):
                budget = json.loads(row[5]) if row[5] else {}
            entry: dict[str, Any] = {
                "run_id": row[0],
                "status": row[1],
                "mode": row[2],
                "started_at": row[3],
                "completed_at": row[4],
                "budget_used": budget,
            }
            if row[6]:
                entry["pause_reason"] = row[6]
            if row[7]:
                entry["paused_at"] = row[7]
            runs.append(entry)
        return runs

    @staticmethod
    def _row_to_state(row: tuple) -> RecipeRunState:
        (run_id, recipe_id, session_id, status, mode,
         checkpoints_json, step_results_json, current_step_id,
         context_json, pause_reason, pause_data_json, paused_at,
         started_at, completed_at, budget_json) = row

        checkpoints_reached: dict[str, CheckpointResult] = {}
        try:
            raw = json.loads(checkpoints_json) if checkpoints_json else {}
            for k, v in raw.items():
                if isinstance(v, dict):
                    checkpoints_reached[k] = CheckpointResult.model_validate(v)
        except Exception:
            pass

        step_results: dict[str, dict[str, Any]] = {}
        with contextlib.suppress(Exception):
            step_results = json.loads(step_results_json) if step_results_json else {}

        context: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            context = json.loads(context_json) if context_json else {}

        pause_data: dict[str, Any] | None = None
        if pause_data_json:
            with contextlib.suppress(Exception):
                pause_data = json.loads(pause_data_json)

        budget = BudgetSnapshot()
        if budget_json:
            with contextlib.suppress(Exception):
                budget = BudgetSnapshot.model_validate(json.loads(budget_json))

        return RecipeRunState(
            run_id=run_id,
            recipe_id=recipe_id,
            session_id=session_id or "",
            status=status or "pending",
            mode=mode or "adaptive",
            checkpoints_reached=checkpoints_reached,
            step_results=step_results,
            current_step_id=current_step_id,
            context=context,
            pause_reason=pause_reason,
            pause_data=pause_data,
            paused_at=paused_at,
            started_at=started_at or "",
            completed_at=completed_at,
            budget_used=budget,
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
        if event.get("type") in ("recipe_completed", "recipe_failed"):
            self._event_buffers.pop(run_id, None)

    def make_send_event(self, run_id: str) -> Any:
        store = self
        state_holder: list[RecipeRunState | None] = [None]

        async def send_event(event: dict) -> None:
            await store.broadcast(run_id, event)
            event_type = event.get("type", "")
            if event_type in ("recipe_checkpoint_passed", "recipe_step_completed",
                              "recipe_step_failed", "recipe_completed", "recipe_failed",
                              "recipe_paused", "recipe_resumed"):
                current_state = state_holder[0]
                if current_state is not None:
                    store.save(current_state)

        return send_event, state_holder


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_recipe_store: SqliteRecipeStore | None = None
_recipe_run_store: SqliteRecipeRunStore | None = None
_init_lock = threading.Lock()


def init_recipe_sqlite_stores(*, db_path: str | Path) -> tuple[SqliteRecipeStore, SqliteRecipeRunStore]:
    global _recipe_store, _recipe_run_store
    with _init_lock:
        p = str(db_path)
        _recipe_store = SqliteRecipeStore(db_path=p)
        _recipe_run_store = SqliteRecipeRunStore(db_path=p)
    return _recipe_store, _recipe_run_store


def get_recipe_store() -> SqliteRecipeStore:
    if _recipe_store is None:
        raise RuntimeError("SqliteRecipeStore not initialized")
    return _recipe_store


def get_recipe_run_store() -> SqliteRecipeRunStore:
    if _recipe_run_store is None:
        raise RuntimeError("SqliteRecipeRunStore not initialized")
    return _recipe_run_store
