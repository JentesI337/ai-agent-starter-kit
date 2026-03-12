from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


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
    def __init__(self, db_path: str, *, fts_enabled: bool = True):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fts_enabled = fts_enabled
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

    # ── FTS5 query builder ─────────────────────────────────────────────

    _FTS_UNSAFE_RE = re.compile(r'[^\w\s]', re.UNICODE)

    @classmethod
    def _build_fts_query(cls, text: str) -> str:
        """Build an FTS5 MATCH query from free text.

        Tokenizes, strips short terms, quotes each, joins with OR.
        Returns empty string if no usable terms.
        """
        normalized = cls._FTS_UNSAFE_RE.sub(" ", str(text or "")).strip().lower()
        terms = [t for t in normalized.split() if len(t) >= 3][:8]
        if not terms:
            return ""
        return " OR ".join(f'"{t}"' for t in terms)

    # ── Write methods (unchanged API) ──────────────────────────────────

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
        key_actions_text = json.dumps([action.strip() for action in (key_actions or []) if str(action).strip()])
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
        source_sessions_text = ",".join(session.strip() for session in entry.source_sessions if str(session).strip())
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

    # ── Search methods (FTS5 with LIKE fallback) ───────────────────────

    def search_failures(self, task_description: str, limit: int = 3) -> list[FailureEntry]:
        if self._fts_enabled:
            fts_query = self._build_fts_query(task_description)
            if fts_query:
                try:
                    return self._search_failures_fts(fts_query, limit)
                except Exception:
                    logger.debug("FTS5 failure search failed, falling back to LIKE", exc_info=True)
        return self._search_failures_like(task_description, limit)

    def _search_failures_fts(self, fts_query: str, limit: int) -> list[FailureEntry]:
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            rows = connection.execute(
                """
                SELECT f.id, f.timestamp, f.task_description, f.error_type,
                       f.root_cause, f.solution, f.prevention, f.tags
                FROM failure_journal f
                JOIN failure_journal_fts fts ON f.rowid = fts.rowid
                WHERE failure_journal_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
                """,
                (fts_query, max(1, int(limit))),
            ).fetchall()
        return self._parse_failure_rows(rows)

    def _search_failures_like(self, task_description: str, limit: int) -> list[FailureEntry]:
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
                    WHERE {" OR ".join(where_clauses)}
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
        return self._parse_failure_rows(rows)

    def _parse_failure_rows(self, rows: list[tuple]) -> list[FailureEntry]:
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
        if self._fts_enabled:
            fts_query = self._build_fts_query(query)
            if fts_query:
                try:
                    return self._search_episodic_fts(fts_query, limit)
                except Exception:
                    logger.debug("FTS5 episodic search failed, falling back to LIKE", exc_info=True)
        return self._search_episodic_like(query, limit)

    def _search_episodic_fts(self, fts_query: str, limit: int) -> list[EpisodicEntry]:
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            rows = connection.execute(
                """
                SELECT e.id, e.session_id, e.timestamp, e.summary,
                       e.key_actions, e.outcome, e.tags
                FROM episodic e
                JOIN episodic_fts fts ON e.rowid = fts.rowid
                WHERE episodic_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
                """,
                (fts_query, max(1, int(limit))),
            ).fetchall()
        return self._parse_episodic_rows(rows)

    def _search_episodic_like(self, query: str, limit: int) -> list[EpisodicEntry]:
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
                    WHERE {" OR ".join(where_clauses)}
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
        return self._parse_episodic_rows(rows)

    def _parse_episodic_rows(self, rows: list[tuple]) -> list[EpisodicEntry]:
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

    def search_semantic(self, query: str, limit: int = 10) -> list[SemanticEntry]:
        """Search semantic facts by relevance using FTS5, with fallback to get_all_semantic."""
        if self._fts_enabled:
            fts_query = self._build_fts_query(query)
            if fts_query:
                try:
                    return self._search_semantic_fts(fts_query, limit)
                except Exception:
                    logger.debug("FTS5 semantic search failed, falling back to get_all", exc_info=True)
        return self.get_all_semantic(limit=limit)

    def _search_semantic_fts(self, fts_query: str, limit: int) -> list[SemanticEntry]:
        with self._lock, sqlite3.connect(str(self._db_path)) as connection:
            rows = connection.execute(
                """
                SELECT s.key, s.value, s.confidence, s.source_sessions, s.last_updated
                FROM semantic s
                JOIN semantic_fts fts ON s.rowid = fts.rowid
                WHERE semantic_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
                """,
                (fts_query, max(1, int(limit))),
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

    # ── Exact lookups (unchanged) ──────────────────────────────────────

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

    # ── Schema ─────────────────────────────────────────────────────────

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

                """
            )
            connection.commit()

            # FTS5 full-text search indexes (external content, no storage duplication)
            if self._fts_enabled:
                self._ensure_fts_schema(connection)

    def _ensure_fts_schema(self, connection: sqlite3.Connection) -> None:
        try:
            connection.executescript(
                """
                -- FTS5 virtual tables
                CREATE VIRTUAL TABLE IF NOT EXISTS failure_journal_fts USING fts5(
                    task_description, error_type, root_cause, solution, prevention, tags,
                    content='failure_journal', content_rowid='rowid'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
                    summary, key_actions, outcome, tags,
                    content='episodic', content_rowid='rowid'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(
                    key, value,
                    content='semantic', content_rowid='rowid'
                );

                -- Sync triggers: failure_journal
                CREATE TRIGGER IF NOT EXISTS failure_journal_fts_ai AFTER INSERT ON failure_journal BEGIN
                    INSERT INTO failure_journal_fts(rowid, task_description, error_type, root_cause, solution, prevention, tags)
                    VALUES (new.rowid, new.task_description, new.error_type, new.root_cause, new.solution, new.prevention, new.tags);
                END;
                CREATE TRIGGER IF NOT EXISTS failure_journal_fts_ad AFTER DELETE ON failure_journal BEGIN
                    INSERT INTO failure_journal_fts(failure_journal_fts, rowid, task_description, error_type, root_cause, solution, prevention, tags)
                    VALUES ('delete', old.rowid, old.task_description, old.error_type, old.root_cause, old.solution, old.prevention, old.tags);
                END;
                CREATE TRIGGER IF NOT EXISTS failure_journal_fts_au AFTER UPDATE ON failure_journal BEGIN
                    INSERT INTO failure_journal_fts(failure_journal_fts, rowid, task_description, error_type, root_cause, solution, prevention, tags)
                    VALUES ('delete', old.rowid, old.task_description, old.error_type, old.root_cause, old.solution, old.prevention, old.tags);
                    INSERT INTO failure_journal_fts(rowid, task_description, error_type, root_cause, solution, prevention, tags)
                    VALUES (new.rowid, new.task_description, new.error_type, new.root_cause, new.solution, new.prevention, new.tags);
                END;

                -- Sync triggers: episodic
                CREATE TRIGGER IF NOT EXISTS episodic_fts_ai AFTER INSERT ON episodic BEGIN
                    INSERT INTO episodic_fts(rowid, summary, key_actions, outcome, tags)
                    VALUES (new.rowid, new.summary, new.key_actions, new.outcome, new.tags);
                END;
                CREATE TRIGGER IF NOT EXISTS episodic_fts_ad AFTER DELETE ON episodic BEGIN
                    INSERT INTO episodic_fts(episodic_fts, rowid, summary, key_actions, outcome, tags)
                    VALUES ('delete', old.rowid, old.summary, old.key_actions, old.outcome, old.tags);
                END;
                CREATE TRIGGER IF NOT EXISTS episodic_fts_au AFTER UPDATE ON episodic BEGIN
                    INSERT INTO episodic_fts(episodic_fts, rowid, summary, key_actions, outcome, tags)
                    VALUES ('delete', old.rowid, old.summary, old.key_actions, old.outcome, old.tags);
                    INSERT INTO episodic_fts(rowid, summary, key_actions, outcome, tags)
                    VALUES (new.rowid, new.summary, new.key_actions, new.outcome, new.tags);
                END;

                -- Sync triggers: semantic
                CREATE TRIGGER IF NOT EXISTS semantic_fts_ai AFTER INSERT ON semantic BEGIN
                    INSERT INTO semantic_fts(rowid, key, value)
                    VALUES (new.rowid, new.key, new.value);
                END;
                CREATE TRIGGER IF NOT EXISTS semantic_fts_ad AFTER DELETE ON semantic BEGIN
                    INSERT INTO semantic_fts(semantic_fts, rowid, key, value)
                    VALUES ('delete', old.rowid, old.key, old.value);
                END;
                CREATE TRIGGER IF NOT EXISTS semantic_fts_au AFTER UPDATE ON semantic BEGIN
                    INSERT INTO semantic_fts(semantic_fts, rowid, key, value)
                    VALUES ('delete', old.rowid, old.key, old.value);
                    INSERT INTO semantic_fts(rowid, key, value)
                    VALUES (new.rowid, new.key, new.value);
                END;
                """
            )
            # Rebuild FTS indexes from existing data (idempotent)
            connection.execute("INSERT INTO failure_journal_fts(failure_journal_fts) VALUES('rebuild')")
            connection.execute("INSERT INTO episodic_fts(episodic_fts) VALUES('rebuild')")
            connection.execute("INSERT INTO semantic_fts(semantic_fts) VALUES('rebuild')")
            connection.commit()
        except Exception:
            logger.warning("FTS5 schema creation failed — full-text search disabled", exc_info=True)
            self._fts_enabled = False
