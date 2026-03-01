from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from time import monotonic


class SessionLaneManager:
    def __init__(self, *, global_max_concurrent: int):
        self._session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_semaphore = asyncio.Semaphore(max(1, global_max_concurrent))

    @asynccontextmanager
    async def acquire(self, session_id: str):
        key = (session_id or "").strip() or "default"
        queue_started = monotonic()
        session_lock = self._session_locks[key]

        async with session_lock:
            async with self._global_semaphore:
                queue_wait_ms = int((monotonic() - queue_started) * 1000)
                yield {"queue_wait_ms": queue_wait_ms, "session_id": key}

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
            try:
                return await run()
            finally:
                if on_released is not None:
                    await on_released(details)
