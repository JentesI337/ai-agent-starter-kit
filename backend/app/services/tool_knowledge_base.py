"""L3.1–L3.3  ToolKnowledgeBase — lightweight SQLite-backed knowledge store.

Records what the agent learns about tools:
  - Which tools solve which capability?
  - What install commands are required?
  - What common pitfalls exist?

Provides:
  ``learn_from_outcome()`` — record knowledge after every tool execution.
  ``find_tools_for_capability()`` — fast keyword-based search.
  ``get_tool_hints()`` — lookup install/usage hints for a tool name.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolKnowledge:
    """One piece of knowledge about a tool / capability pair."""

    tool: str
    capability: str          # e.g. "json_processing", "git_operations"
    install_hint: str = ""   # e.g. "pip install jq" or "npm i -g prettier"
    pitfall: str = ""        # known issues
    confidence: float = 1.0  # 0.0–1.0
    source: str = "agent"    # agent | pkg_manager | web | user
    last_seen: float = 0.0   # epoch

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "capability": self.capability,
            "install_hint": self.install_hint,
            "pitfall": self.pitfall,
            "confidence": self.confidence,
            "source": self.source,
            "last_seen": self.last_seen,
        }


class ToolKnowledgeBase:
    """Thread-safe SQLite knowledge store.

    Usage::

        kb = ToolKnowledgeBase()       # in-memory
        kb = ToolKnowledgeBase("/path/to/knowledge.db")  # persistent

        kb.learn_from_outcome(tool="jq", capability="json_processing",
                              install_hint="apt install jq")

        results = kb.find_tools_for_capability("json")

    Confidence-Decay (X-10)::

        Returned confidence values are multiplied by  ``exp(-0.01 * days_since_last_seen)``
        so that stale entries gracefully lose influence without being deleted.
    """

    # X-10: per-day exponential decay rate for confidence scores
    CONFIDENCE_DECAY_RATE: float = 0.01

    _DDL = """
    CREATE TABLE IF NOT EXISTS tool_knowledge (
        tool        TEXT    NOT NULL,
        capability  TEXT    NOT NULL,
        install_hint TEXT   NOT NULL DEFAULT '',
        pitfall     TEXT    NOT NULL DEFAULT '',
        confidence  REAL   NOT NULL DEFAULT 1.0,
        source      TEXT   NOT NULL DEFAULT 'agent',
        last_seen   REAL   NOT NULL DEFAULT 0.0,
        PRIMARY KEY (tool, capability)
    );
    CREATE INDEX IF NOT EXISTS idx_capability ON tool_knowledge(capability);
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ":memory:"
        self._lock = threading.Lock()
        self._conn = self._connect()
        with self._conn:
            self._conn.executescript(self._DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── L3.2  learn_from_outcome ─────────────────────────────────────

    def learn_from_outcome(
        self,
        *,
        tool: str,
        capability: str,
        install_hint: str = "",
        pitfall: str = "",
        confidence: float = 1.0,
        source: str = "agent",
    ) -> None:
        """Upsert a knowledge record for *tool* × *capability*."""
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO tool_knowledge
                    (tool, capability, install_hint, pitfall, confidence, source, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool, capability) DO UPDATE SET
                    install_hint = CASE WHEN excluded.install_hint != '' THEN excluded.install_hint ELSE tool_knowledge.install_hint END,
                    pitfall      = CASE WHEN excluded.pitfall != '' THEN excluded.pitfall ELSE tool_knowledge.pitfall END,
                    confidence   = MAX(tool_knowledge.confidence, excluded.confidence),
                    source       = excluded.source,
                    last_seen    = excluded.last_seen
                """,
                (tool, capability, install_hint, pitfall, confidence, source, now),
            )

    # ── L3.3  find_tools_for_capability ──────────────────────────────

    def find_tools_for_capability(
        self,
        query: str,
        *,
        min_confidence: float = 0.3,
        limit: int = 10,
    ) -> list[ToolKnowledge]:
        """Keyword search over capabilities.

        Returns results sorted by *decayed* confidence desc.
        X-10: ``effective_conf = raw_conf * exp(-DECAY_RATE * days_since_last_seen)``
        """
        like_q = f"%{query}%"
        now = time.time()
        with self._lock:
            # Fetch all matching rows (no min-confidence filter yet — applied after decay)
            rows = self._conn.execute(
                """
                SELECT * FROM tool_knowledge
                WHERE capability LIKE ?
                ORDER BY confidence DESC, last_seen DESC
                """,
                (like_q,),
            ).fetchall()

        results: list[ToolKnowledge] = []
        for r in rows:
            days_since = max(0.0, (now - r["last_seen"]) / 86400.0)
            decayed_conf = r["confidence"] * math.exp(
                -self.CONFIDENCE_DECAY_RATE * days_since
            )
            if decayed_conf < min_confidence:
                continue
            results.append(
                ToolKnowledge(
                    tool=r["tool"],
                    capability=r["capability"],
                    install_hint=r["install_hint"],
                    pitfall=r["pitfall"],
                    confidence=round(decayed_conf, 6),
                    source=r["source"],
                    last_seen=r["last_seen"],
                )
            )
            if len(results) >= limit:
                break

        results.sort(key=lambda k: k.confidence, reverse=True)
        return results

    def get_tool_hints(self, tool: str) -> list[ToolKnowledge]:
        """Return all knowledge entries for *tool*."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tool_knowledge WHERE tool = ? ORDER BY confidence DESC",
                (tool,),
            ).fetchall()
        return [self._row_to_knowledge(r) for r in rows]

    def all_entries(self) -> list[ToolKnowledge]:
        """Return every entry (for debugging / export)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tool_knowledge ORDER BY tool, capability"
            ).fetchall()
        return [self._row_to_knowledge(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM tool_knowledge").fetchone()
            return row[0] if row else 0

    @staticmethod
    def _row_to_knowledge(row: sqlite3.Row) -> ToolKnowledge:
        return ToolKnowledge(
            tool=row["tool"],
            capability=row["capability"],
            install_hint=row["install_hint"],
            pitfall=row["pitfall"],
            confidence=row["confidence"],
            source=row["source"],
            last_seen=row["last_seen"],
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
