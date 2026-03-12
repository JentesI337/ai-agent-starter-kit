from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReflectionRecord:
    record_id: str
    session_id: str
    request_id: str
    task_type: str
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    model_id: str
    prompt_variant: str | None
    retry_triggered: bool
    timestamp_utc: str


class ReflectionFeedbackStore:
    def __init__(self, db_path: str):
        self._raw_db_path = str(db_path)
        self._memory_connection: sqlite3.Connection | None = None
        if self._raw_db_path == ":memory:":
            self._memory_connection = sqlite3.connect(self._raw_db_path)
            self._ensure_schema(self._memory_connection)
        else:
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        return sqlite3.connect(str(self._db_path))

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
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

    def store(self, record: ReflectionRecord) -> None:
        try:
            connection = self._connect()
            self._ensure_schema(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO reflection_feedback (
                    id,
                    session_id,
                    request_id,
                    task_type,
                    score,
                    goal_alignment,
                    completeness,
                    factual_grounding,
                    issues,
                    suggested_fix,
                    model_id,
                    prompt_variant,
                    retry_triggered,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.session_id,
                    record.request_id,
                    record.task_type,
                    float(record.score),
                    float(record.goal_alignment),
                    float(record.completeness),
                    float(record.factual_grounding),
                    json.dumps(list(record.issues or []), ensure_ascii=False),
                    record.suggested_fix,
                    record.model_id,
                    record.prompt_variant,
                    1 if record.retry_triggered else 0,
                    record.timestamp_utc,
                ),
            )
            connection.commit()
        except Exception:
            logger.warning("reflection_feedback_store_failed", exc_info=True)

    def get_avg_scores_by_task_type(self, *, last_n: int = 100) -> dict[str, dict[str, float]]:
        try:
            connection = self._connect()
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                WITH recent AS (
                    SELECT task_type, score, goal_alignment, completeness, factual_grounding
                    FROM reflection_feedback
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                SELECT
                    task_type,
                    AVG(score) AS avg_score,
                    AVG(goal_alignment) AS avg_goal_alignment,
                    AVG(completeness) AS avg_completeness,
                    AVG(factual_grounding) AS avg_factual_grounding,
                    COUNT(*) AS samples
                FROM recent
                GROUP BY task_type
                """,
                (max(1, int(last_n)),),
            ).fetchall()
        except Exception:
            logger.warning("reflection_feedback_store_read_failed", exc_info=True)
            return {}

        result: dict[str, dict[str, float]] = {}
        for row in rows:
            task_type = str(row[0] or "").strip()
            if not task_type:
                continue
            result[task_type] = {
                "score": round(float(row[1] or 0.0), 4),
                "goal_alignment": round(float(row[2] or 0.0), 4),
                "completeness": round(float(row[3] or 0.0), 4),
                "factual_grounding": round(float(row[4] or 0.0), 4),
                "samples": float(int(row[5] or 0)),
            }
        return result

    def get_weak_task_types(self, threshold: float = 0.65, *, last_n: int = 100) -> list[str]:
        averages = self.get_avg_scores_by_task_type(last_n=last_n)
        weak: list[str] = []
        cutoff = max(0.0, min(1.0, float(threshold)))
        for task_type, metrics in averages.items():
            if float(metrics.get("score", 0.0)) < cutoff:
                weak.append(task_type)
        return weak

    def get_retry_rate_by_model(self, *, last_n: int = 100) -> dict[str, float]:
        try:
            connection = self._connect()
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                WITH recent AS (
                    SELECT model_id, retry_triggered
                    FROM reflection_feedback
                    WHERE COALESCE(model_id, '') <> ''
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                SELECT model_id, AVG(retry_triggered), COUNT(*)
                FROM recent
                GROUP BY model_id
                """,
                (max(1, int(last_n)),),
            ).fetchall()
        except Exception:
            logger.warning("reflection_feedback_store_retry_rate_failed", exc_info=True)
            return {}

        return {str(row[0]): round(float(row[1] or 0.0), 4) for row in rows if int(row[2] or 0) > 0}
