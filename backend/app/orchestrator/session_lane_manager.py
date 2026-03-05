from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from time import monotonic

_logger = logging.getLogger(__name__)


class SessionLaneManager:
    def __init__(
        self,
        *,
        global_max_concurrent: int,
        max_cached_session_locks: int = 2048,
        session_lock_idle_ttl_seconds: float = 900.0,
    ):
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_active_counts: dict[str, int] = {}
        self._session_last_used: dict[str, float] = {}
        self._session_meta_lock = asyncio.Lock()
        self._global_semaphore = asyncio.Semaphore(max(1, global_max_concurrent))
        self._max_cached_session_locks = max(32, int(max_cached_session_locks))
        self._session_lock_idle_ttl_seconds = max(1.0, float(session_lock_idle_ttl_seconds))

    async def _get_or_create_session_lock(self, key: str) -> asyncio.Lock:
        async with self._session_meta_lock:
            lock = self._session_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[key] = lock
            self._session_last_used[key] = monotonic()
            self._session_active_counts[key] = self._session_active_counts.get(key, 0) + 1
            return lock

    async def _mark_session_active(self, key: str) -> None:
        async with self._session_meta_lock:
            self._session_active_counts[key] = self._session_active_counts.get(key, 0) + 1
            self._session_last_used[key] = monotonic()

    async def _mark_session_released(self, key: str) -> None:
        async with self._session_meta_lock:
            active = self._session_active_counts.get(key, 0)
            if active <= 1:
                self._session_active_counts.pop(key, None)
            else:
                self._session_active_counts[key] = active - 1
            self._session_last_used[key] = monotonic()
            self._evict_idle_session_locks_locked(exclude_key=key)

    def _evict_idle_session_locks_locked(self, *, exclude_key: str | None = None) -> None:
        now = monotonic()
        evictable: list[tuple[float, str]] = []
        for key, lock in self._session_locks.items():
            if key == exclude_key:
                continue
            if self._session_active_counts.get(key, 0) > 0:
                continue
            if lock.locked():
                continue
            last_used = self._session_last_used.get(key, now)
            idle_seconds = now - last_used
            if idle_seconds >= self._session_lock_idle_ttl_seconds:
                evictable.append((last_used, key))

        for _, key in sorted(evictable):
            self._session_locks.pop(key, None)
            self._session_last_used.pop(key, None)
            self._session_active_counts.pop(key, None)

        overflow = len(self._session_locks) - self._max_cached_session_locks
        if overflow <= 0:
            return

        capacity_candidates: list[tuple[float, str]] = []
        for key, lock in self._session_locks.items():
            if key == exclude_key:
                continue
            if self._session_active_counts.get(key, 0) > 0:
                continue
            if lock.locked():
                continue
            capacity_candidates.append((self._session_last_used.get(key, now), key))

        for _, key in sorted(capacity_candidates)[:overflow]:
            self._session_locks.pop(key, None)
            self._session_last_used.pop(key, None)
            self._session_active_counts.pop(key, None)

    @asynccontextmanager
    async def acquire(self, session_id: str):
        key = (session_id or "").strip() or "default"
        queue_started = monotonic()
        session_lock = await self._get_or_create_session_lock(key)
        entered = False

        try:
            async with session_lock:
                async with self._global_semaphore:
                    entered = True
                    queue_wait_ms = int((monotonic() - queue_started) * 1000)
                    try:
                        yield {"queue_wait_ms": queue_wait_ms, "session_id": key}
                    finally:
                        await self._mark_session_released(key)
        except BaseException:
            if not entered:
                await self._mark_session_released(key)
            raise

    async def run_in_lane(
        self,
        *,
        session_id: str,
        on_acquired: Callable[[dict], Awaitable[None]] | None,
        run: Callable[[], Awaitable[str]],
        on_released: Callable[[dict], Awaitable[None]] | None = None,
    ) -> str:
        async with self.acquire(session_id) as details:
            if on_acquired is not None:
                await on_acquired(details)
            result: str = ""
            run_error: Exception | None = None
            try:
                result = await run()
                return result
            except Exception as exc:
                run_error = exc
                raise
            finally:
                if on_released is not None:
                    try:
                        await on_released(details)
                    except Exception:
                        _logger.warning(
                            "on_released callback failed for session %s",
                            session_id,
                            exc_info=True,
                        )
                        if run_error is None:
                            # Don't let on_released error override the successful result
                            pass
