from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class FailureEntry:
    failure_id: str
    task_description: str
    error_type: str
    root_cause: str
    solution: str
    prevention: str
    tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class SemanticEntry:
    key: str
    value: str
    confidence: float
    source_sessions: list[str] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class EpisodicEntry:
    session_id: str
    summary: str
    key_actions: list[str] = field(default_factory=list)
    outcome: str = "success"
    tags: list[str] = field(default_factory=list)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class LongTermMemoryStore:
    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    @staticmethod
    def _parse_list_field(raw: object) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except (json.JSONDecodeError, ValueError):
                pass
        return [item.strip() for item in text.split(",") if item.strip()]

    def add_failure(self, entry: FailureEntry) -> None:
        tags_text = json.dumps([tag.strip() for tag in entry.tags if str(tag).strip()])
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO failure_journal (
                    id,
                    timestamp,
                    task_description,
                    error_type,
                    root_cause,
                    solution,
                    prevention,
                    tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.failure_id,
                    entry.timestamp,
                    entry.task_description,
                    entry.error_type,
                    entry.root_cause,
                    entry.solution,
                    entry.prevention,
                    tags_text,
                ),
            )
            connection.commit()

    def add_episodic(
        self,
        *,
        session_id: str,
        summary: str,
        key_actions: list[str] | None = None,
        outcome: str = "success",
        tags: list[str] | None = None,
        entry_id: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        key_actions_text = json.dumps(
            [action.strip() for action in (key_actions or []) if str(action).strip()]
        )
        tags_text = json.dumps([tag.strip() for tag in (tags or []) if str(tag).strip()])
        row_id = (entry_id or "").strip() or uuid.uuid4().hex
        row_timestamp = (timestamp or "").strip() or datetime.now(UTC).isoformat()

        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO episodic (
                    id,
                    session_id,
                    timestamp,
                    summary,
                    key_actions,
                    outcome,
                    tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    session_id,
                    row_timestamp,
                    summary,
                    key_actions_text,
                    outcome,
                    tags_text,
                ),
            )
            connection.commit()

    def add_semantic(
        self,
        entry: SemanticEntry | None = None,
        *,
        key: str | None = None,
        value: str | None = None,
        confidence: float | None = None,
        source_sessions: list[str] | None = None,
        last_updated: str | None = None,
    ) -> None:
        if entry is None:
            if key is None or value is None:
                raise ValueError("key and value are required when entry is not provided")
            entry = SemanticEntry(
                key=key,
                value=value,
                confidence=float(confidence or 0.0),
                source_sessions=list(source_sessions or []),
                last_updated=(last_updated or "").strip() or datetime.now(UTC).isoformat(),
            )
        source_sessions_text = ",".join(
            session.strip() for session in entry.source_sessions if str(session).strip()
        )
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO semantic (
                    key,
                    value,
                    confidence,
                    source_sessions,
                    last_updated
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entry.key,
                    entry.value,
                    float(entry.confidence),
                    source_sessions_text,
                    entry.last_updated,
                ),
            )
            connection.commit()

    def search_failures(self, task_description: str, limit: int = 3) -> list[FailureEntry]:
        normalized_query = str(task_description or "").strip().lower()
        rows: list[tuple] = []
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            if normalized_query:
                terms = [token for token in normalized_query.split() if len(token) >= 3][:6]
                if not terms:
                    terms = [normalized_query]

                where_clauses: list[str] = []
                params: list[object] = []
                for term in terms:
                    like = f"%{term}%"
                    where_clauses.append(
                        "(lower(task_description) LIKE ? OR lower(root_cause) LIKE ? OR lower(solution) LIKE ? OR lower(tags) LIKE ?)"
                    )
                    params.extend([like, like, like, like])
                params.append(max(1, int(limit)))

                rows = connection.execute(
                    f"""
                    SELECT id, timestamp, task_description, error_type, root_cause, solution, prevention, tags
                    FROM failure_journal
                    WHERE {' OR '.join(where_clauses)}
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, timestamp, task_description, error_type, root_cause, solution, prevention, tags
                    FROM failure_journal
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()

        entries: list[FailureEntry] = []
        for row in rows:
            tags = self._parse_list_field(row[7])
            entries.append(
                FailureEntry(
                    failure_id=str(row[0] or ""),
                    timestamp=str(row[1] or ""),
                    task_description=str(row[2] or ""),
                    error_type=str(row[3] or ""),
                    root_cause=str(row[4] or ""),
                    solution=str(row[5] or ""),
                    prevention=str(row[6] or ""),
                    tags=tags,
                )
            )
        return entries

    def search_episodic(self, query: str, limit: int = 5) -> list[EpisodicEntry]:
        normalized_query = str(query or "").strip().lower()
        rows: list[tuple] = []
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            if normalized_query:
                terms = [token for token in normalized_query.split() if len(token) >= 3][:6]
                if not terms:
                    terms = [normalized_query]

                where_clauses: list[str] = []
                params: list[object] = []
                for term in terms:
                    like = f"%{term}%"
                    where_clauses.append(
                        "(lower(summary) LIKE ? OR lower(key_actions) LIKE ? OR lower(tags) LIKE ? OR lower(outcome) LIKE ?)"
                    )
                    params.extend([like, like, like, like])
                params.append(max(1, int(limit)))

                rows = connection.execute(
                    f"""
                    SELECT id, session_id, timestamp, summary, key_actions, outcome, tags
                    FROM episodic
                    WHERE {' OR '.join(where_clauses)}
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, session_id, timestamp, summary, key_actions, outcome, tags
                    FROM episodic
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()

        entries: list[EpisodicEntry] = []
        for row in rows:
            key_actions = self._parse_list_field(row[4])
            tags = self._parse_list_field(row[6])
            entries.append(
                EpisodicEntry(
                    session_id=str(row[1] or ""),
                    timestamp=str(row[2] or ""),
                    summary=str(row[3] or ""),
                    key_actions=key_actions,
                    outcome=str(row[5] or ""),
                    tags=tags,
                    entry_id=str(row[0] or ""),
                )
            )
        return entries

    def get_semantic(self, key: str) -> SemanticEntry | None:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return None

        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            row = connection.execute(
                """
                SELECT key, value, confidence, source_sessions, last_updated
                FROM semantic
                WHERE key = ?
                LIMIT 1
                """,
                (normalized_key,),
            ).fetchone()

        if row is None:
            return None

        source_sessions = [item.strip() for item in str(row[3] or "").split(",") if item.strip()]
        return SemanticEntry(
            key=str(row[0] or ""),
            value=str(row[1] or ""),
            confidence=float(row[2] or 0.0),
            source_sessions=source_sessions,
            last_updated=str(row[4] or ""),
        )

    def get_all_semantic(self, limit: int = 100) -> list[SemanticEntry]:
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            rows = connection.execute(
                """
                SELECT key, value, confidence, source_sessions, last_updated
                FROM semantic
                ORDER BY last_updated DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        entries: list[SemanticEntry] = []
        for row in rows:
            source_sessions = [item.strip() for item in str(row[3] or "").split(",") if item.strip()]
            entries.append(
                SemanticEntry(
                    key=str(row[0] or ""),
                    value=str(row[1] or ""),
                    confidence=float(row[2] or 0.0),
                    source_sessions=source_sessions,
                    last_updated=str(row[4] or ""),
                )
            )
        return entries

    def _ensure_schema(self) -> None:
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            # SEC (LTM-01): Enable WAL mode for better concurrency and reduced locking
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    timestamp TEXT,
                    summary TEXT,
                    key_actions TEXT,
                    outcome TEXT,
                    tags TEXT
                );

                CREATE TABLE IF NOT EXISTS semantic (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    confidence REAL,
                    source_sessions TEXT,
                    last_updated TEXT
                );

                CREATE TABLE IF NOT EXISTS failure_journal (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    task_description TEXT,
                    error_type TEXT,
                    root_cause TEXT,
                    solution TEXT,
                    prevention TEXT,
                    tags TEXT
                );

                CREATE TABLE IF NOT EXISTS reflection_feedback (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    score REAL NOT NULL,
                    goal_alignment REAL,
                    completeness REAL,
                    factual_grounding REAL,
                    issues TEXT,
                    suggested_fix TEXT,
                    model_id TEXT,
                    prompt_variant TEXT,
                    retry_triggered INTEGER,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_rf_task_type ON reflection_feedback(task_type);
                CREATE INDEX IF NOT EXISTS idx_rf_model ON reflection_feedback(model_id);
                """
            )
            connection.commit()
