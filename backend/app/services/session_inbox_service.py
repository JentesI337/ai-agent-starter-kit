from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class InboxMessage:
    session_id: str
    run_id: str
    message: str
    meta: dict[str, object]
    enqueued_at: datetime


class SessionInboxService:
    def __init__(self, *, max_queue_length: int = 100, ttl_seconds: int = 600):
        self._max_queue_length = max(1, int(max_queue_length))
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._lock = Lock()
        self._queues: dict[str, deque[InboxMessage]] = {}

    def enqueue(self, session_id: str, run_id: str, message: str, meta: dict[str, object] | None = None) -> InboxMessage:
        normalized_session = (session_id or "").strip()
        if not normalized_session:
            raise ValueError("session_id must not be empty")

        payload = InboxMessage(
            session_id=normalized_session,
            run_id=(run_id or "").strip(),
            message=message or "",
            meta=dict(meta or {}),
            enqueued_at=_utc_now(),
        )

        with self._lock:
            queue = self._queues.setdefault(normalized_session, deque())
            self._purge_expired_locked(queue)
            if len(queue) >= self._max_queue_length:
                raise OverflowError(f"session inbox overflow for session '{normalized_session}'")
            queue.append(payload)
        return payload

    def dequeue(self, session_id: str) -> InboxMessage | None:
        normalized_session = (session_id or "").strip()
        if not normalized_session:
            return None
        with self._lock:
            queue = self._queues.get(normalized_session)
            if not queue:
                return None
            self._purge_expired_locked(queue)
            if not queue:
                self._queues.pop(normalized_session, None)
                return None
            item = queue.popleft()
            if not queue:
                self._queues.pop(normalized_session, None)
            return item

    def peek_newer_than(self, session_id: str, run_id: str) -> list[InboxMessage]:
        normalized_session = (session_id or "").strip()
        if not normalized_session:
            return []
        marker = (run_id or "").strip()
        with self._lock:
            queue = self._queues.get(normalized_session)
            if not queue:
                return []
            self._purge_expired_locked(queue)
            if not queue:
                self._queues.pop(normalized_session, None)
                return []
            if not marker:
                return list(queue)
            return [item for item in queue if item.run_id and item.run_id != marker]

    def has_newer_than(self, session_id: str, run_id: str) -> bool:
        return bool(self.peek_newer_than(session_id, run_id))

    def size(self, session_id: str) -> int:
        normalized_session = (session_id or "").strip()
        if not normalized_session:
            return 0
        with self._lock:
            queue = self._queues.get(normalized_session)
            if not queue:
                return 0
            self._purge_expired_locked(queue)
            if not queue:
                self._queues.pop(normalized_session, None)
                return 0
            return len(queue)

    def _purge_expired_locked(self, queue: deque[InboxMessage]) -> None:
        now = _utc_now()
        while queue:
            age = (now - queue[0].enqueued_at).total_seconds()
            if age <= self._ttl_seconds:
                break
            queue.popleft()