from __future__ import annotations

from dataclasses import dataclass

from app.services.long_term_memory import LongTermMemoryStore


@dataclass(frozen=True)
class FailureRetrievalItem:
    failure_id: str
    task_description: str
    error_type: str
    root_cause: str
    solution: str
    prevention: str
    tags: list[str]


class FailureRetriever:
    def __init__(self, store: LongTermMemoryStore):
        self._store = store

    def retrieve(self, query: str, *, sources: tuple[str, ...] = ("failure_journal",), top_k: int = 3) -> list[FailureRetrievalItem]:
        if "failure_journal" not in sources:
            return []
        rows = self._store.search_failures(query, limit=max(1, int(top_k)))
        return [
            FailureRetrievalItem(
                failure_id=row.failure_id,
                task_description=row.task_description,
                error_type=row.error_type,
                root_cause=row.root_cause,
                solution=row.solution,
                prevention=row.prevention,
                tags=list(row.tags),
            )
            for row in rows
        ]
