"""Blackboard: Shared state visible to all agents in a coordination session.

Unlike parent-memory-only state, the Blackboard provides:
- Typed entries with provenance (which agent wrote what)
- Section-based access (agents can read/write specific sections)
- Conflict detection (two agents writing the same key)
- History tracking (full audit trail of all writes)
- Subscription: agents can watch for changes to specific keys
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)

ChangeCallback = Callable[["BlackboardEntry"], Awaitable[None]]


@dataclass(frozen=True)
class BlackboardEntry:
    """A single entry on the shared blackboard."""
    key: str
    value: Any
    section: str             # e.g. "plan", "tool_results", "analysis", "synthesis"
    author_agent_id: str     # who wrote this
    timestamp: str
    entry_id: str
    version: int             # auto-incremented per key
    confidence: float = 0.0  # how confident the author is in this value
    supersedes: str | None = None  # entry_id this replaces
    tags: tuple[str, ...] = ()


@dataclass
class ConflictRecord:
    """Records when two agents tried to write the same key concurrently."""
    key: str
    section: str
    agent_a: str
    agent_b: str
    entry_a_id: str
    entry_b_id: str
    timestamp: str
    resolution: str = "unresolved"  # "agent_a_wins", "agent_b_wins", "merged", "unresolved"


class Blackboard:
    """Thread-safe shared state for multi-agent coordination.
    
    Architecture:
    - Each entry has a key within a section (e.g. section="analysis", key="security_review")
    - Agents write with provenance (author_agent_id)
    - Watchers get notified on changes (async callbacks)
    - Conflict detection when two agents write the same section+key simultaneously
    - Full history maintained for audit
    """

    def __init__(self, *, session_id: str, max_history_per_key: int = 50):
        self._session_id = session_id
        self._max_history = max(1, max_history_per_key)
        self._lock = asyncio.Lock()
        # section -> key -> latest entry
        self._current: dict[str, dict[str, BlackboardEntry]] = defaultdict(dict)
        # section -> key -> version history
        self._history: dict[str, dict[str, list[BlackboardEntry]]] = defaultdict(lambda: defaultdict(list))
        # section -> key -> list of callbacks
        self._watchers: dict[str, dict[str, list[ChangeCallback]]] = defaultdict(lambda: defaultdict(list))
        # global watchers (all changes)
        self._global_watchers: list[ChangeCallback] = []
        self._conflicts: list[ConflictRecord] = []
        self._write_timestamps: dict[str, dict[str, tuple[str, float]]] = defaultdict(dict)
        # conflict window in seconds — writes within this window to same key = conflict
        self._conflict_window_seconds = 2.0

    @property
    def session_id(self) -> str:
        return self._session_id

    async def write(
        self,
        *,
        section: str,
        key: str,
        value: Any,
        author_agent_id: str,
        confidence: float = 0.0,
        tags: tuple[str, ...] = (),
    ) -> BlackboardEntry:
        """Write a value to the blackboard. Returns the created entry."""
        # Normalize author_agent_id so read_by_agent() lookups match consistently
        author_agent_id = (author_agent_id or "").strip().lower()
        async with self._lock:
            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()
            existing = self._current.get(section, {}).get(key)
            version = (existing.version + 1) if existing else 1
            supersedes = existing.entry_id if existing else None

            entry = BlackboardEntry(
                key=key,
                value=value,
                section=section,
                author_agent_id=author_agent_id,
                timestamp=now.isoformat(),
                entry_id=str(uuid4()),
                version=version,
                confidence=max(0.0, min(1.0, float(confidence))),
                supersedes=supersedes,
                tags=tags,
            )

            # Conflict detection: did another agent write to this exact key recently?
            last_write = self._write_timestamps.get(section, {}).get(key)
            if last_write is not None:
                last_agent, last_ts = last_write
                if last_agent != author_agent_id and (now_ts - last_ts) < self._conflict_window_seconds:
                    conflict = ConflictRecord(
                        key=key,
                        section=section,
                        agent_a=last_agent,
                        agent_b=author_agent_id,
                        entry_a_id=existing.entry_id if existing else "",
                        entry_b_id=entry.entry_id,
                        timestamp=now.isoformat(),
                    )
                    self._conflicts.append(conflict)
                    logger.warning(
                        "Blackboard conflict: section=%s key=%s agents=%s/%s",
                        section, key, last_agent, author_agent_id,
                    )

            self._current[section][key] = entry
            history = self._history[section][key]
            history.append(entry)
            if len(history) > self._max_history:
                self._history[section][key] = history[-self._max_history:]
            self._write_timestamps.setdefault(section, {})[key] = (author_agent_id, now_ts)

        # Notify watchers outside the lock
        await self._notify_watchers(section, key, entry)
        return entry

    async def read(self, *, section: str, key: str) -> BlackboardEntry | None:
        """Read the latest value for a section+key."""
        async with self._lock:
            return self._current.get(section, {}).get(key)

    async def read_section(self, section: str) -> dict[str, BlackboardEntry]:
        """Read all entries in a section."""
        async with self._lock:
            return dict(self._current.get(section, {}))

    async def read_all(self) -> dict[str, dict[str, BlackboardEntry]]:
        """Read entire blackboard state."""
        async with self._lock:
            return {sec: dict(entries) for sec, entries in self._current.items()}

    async def read_by_agent(self, agent_id: str) -> list[BlackboardEntry]:
        """Read all entries written by a specific agent."""
        normalized = (agent_id or "").strip().lower()
        result: list[BlackboardEntry] = []
        async with self._lock:
            for section_entries in self._current.values():
                for entry in section_entries.values():
                    if entry.author_agent_id == normalized:
                        result.append(entry)
        return result

    async def read_history(self, *, section: str, key: str) -> list[BlackboardEntry]:
        """Read version history for a section+key."""
        async with self._lock:
            return list(self._history.get(section, {}).get(key, []))

    async def get_conflicts(self) -> list[ConflictRecord]:
        """Get all conflict records."""
        async with self._lock:
            return list(self._conflicts)

    async def resolve_conflict(self, conflict_index: int, resolution: str) -> None:
        """Mark a conflict as resolved."""
        async with self._lock:
            if 0 <= conflict_index < len(self._conflicts):
                # ConflictRecord is a dataclass, mutable
                self._conflicts[conflict_index].resolution = resolution

    def watch(self, *, section: str, key: str, callback: ChangeCallback) -> None:
        """Register a watcher for a specific section+key."""
        self._watchers[section][key].append(callback)

    def watch_all(self, callback: ChangeCallback) -> None:
        """Register a global watcher for all changes."""
        self._global_watchers.append(callback)

    async def _notify_watchers(self, section: str, key: str, entry: BlackboardEntry) -> None:
        """Notify watchers of a change, with error isolation."""
        callbacks = list(self._watchers.get(section, {}).get(key, []))
        callbacks.extend(self._global_watchers)
        for cb in callbacks:
            try:
                await asyncio.wait_for(cb(entry), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Blackboard watcher timed out for section=%s key=%s", section, key)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Blackboard watcher error for section=%s key=%s", section, key)

    async def snapshot(self) -> dict[str, Any]:
        """Serializable snapshot of the entire blackboard for persistence/debugging."""
        async with self._lock:
            sections: dict[str, Any] = {}
            for section, entries in self._current.items():
                sections[section] = {
                    key: {
                        "value": entry.value,
                        "author": entry.author_agent_id,
                        "confidence": entry.confidence,
                        "version": entry.version,
                        "timestamp": entry.timestamp,
                        "tags": list(entry.tags),
                    }
                    for key, entry in entries.items()
                }
            return {
                "session_id": self._session_id,
                "sections": sections,
                "conflict_count": len(self._conflicts),
                "unresolved_conflicts": sum(
                    1 for c in self._conflicts if c.resolution == "unresolved"
                ),
            }
