"""Session-scoped manager for persistent REPL instances.

Maintains at most ``max_sessions`` concurrent :class:`PersistentRepl`
processes and evicts the least-recently-used session when the limit is
reached.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from pathlib import Path

from app.services.persistent_repl import PersistentRepl

logger = logging.getLogger(__name__)


class ReplSessionManager:
    """One global instance manages all REPL sessions."""

    def __init__(
        self,
        *,
        max_sessions: int = 10,
        timeout_seconds: int = 60,
        max_memory_mb: int = 512,
        max_output_chars: int = 10_000,
        sandbox_base: str | Path | None = None,
    ):
        self.max_sessions = max(1, max_sessions)
        self.timeout_seconds = timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.max_output_chars = max_output_chars
        self.sandbox_base = sandbox_base

        # LRU order: most recently used sessions are moved to the end
        self._sessions: OrderedDict[str, PersistentRepl] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> PersistentRepl:
        """Return the REPL for *session_id*, creating one if needed.

        Evicts the oldest session when the pool is at capacity.
        """
        async with self._lock:
            if session_id in self._sessions:
                self._sessions.move_to_end(session_id)
                return self._sessions[session_id]

            # Evict oldest if at capacity
            while len(self._sessions) >= self.max_sessions:
                oldest_id, oldest_repl = self._sessions.popitem(last=False)
                logger.info("repl_session_evicted session=%s", oldest_id)
                await self._safe_shutdown(oldest_repl)

            repl = PersistentRepl(
                session_id,
                timeout_seconds=self.timeout_seconds,
                max_memory_mb=self.max_memory_mb,
                max_output_chars=self.max_output_chars,
                sandbox_base=self.sandbox_base,
            )
            await repl.start()
            self._sessions[session_id] = repl
            logger.info(
                "repl_session_created session=%s active=%d",
                session_id,
                len(self._sessions),
            )
            return repl

    async def reset(self, session_id: str) -> bool:
        """Reset the REPL for *session_id* (clears all state).

        Returns ``True`` if a session existed and was reset.
        """
        async with self._lock:
            repl = self._sessions.get(session_id)
            if repl is None:
                return False
            await repl.reset()
            self._sessions.move_to_end(session_id)
            return True

    async def shutdown_session(self, session_id: str) -> bool:
        """Shut down and remove the REPL for *session_id*.

        Returns ``True`` if a session existed.
        """
        async with self._lock:
            repl = self._sessions.pop(session_id, None)
            if repl is None:
                return False
            await self._safe_shutdown(repl)
            logger.info(
                "repl_session_shutdown session=%s active=%d",
                session_id,
                len(self._sessions),
            )
            return True

    async def shutdown_all(self) -> int:
        """Shut down every active REPL.  Returns the number of sessions closed."""
        async with self._lock:
            count = len(self._sessions)
            for sid, repl in list(self._sessions.items()):
                await self._safe_shutdown(repl)
            self._sessions.clear()
            logger.info("repl_session_manager_shutdown_all closed=%d", count)
            return count

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    @property
    def active_session_ids(self) -> list[str]:
        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe_shutdown(repl: PersistentRepl) -> None:
        try:
            await repl.shutdown()
        except Exception:
            logger.debug(
                "repl_safe_shutdown_error session=%s",
                repl.session_id,
                exc_info=True,
            )
