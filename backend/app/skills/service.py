from __future__ import annotations

import hashlib
from pathlib import Path
from time import monotonic
from dataclasses import dataclass

from app.skills.discovery import discover_skills
from app.skills.eligibility import filter_eligible_skills
from app.skills.models import SkillSnapshot
from app.skills.snapshot import build_skill_snapshot


@dataclass(frozen=True)
class SkillsRuntimeConfig:
    enabled: bool
    skills_dir: str
    max_discovered: int
    max_prompt_chars: int
    snapshot_cache_ttl_seconds: float = 0.0
    snapshot_cache_use_mtime: bool = True


@dataclass(frozen=True)
class _SnapshotCacheEntry:
    snapshot: SkillSnapshot
    cached_at_monotonic: float
    signature: str


class SkillsService:
    def __init__(self, config: SkillsRuntimeConfig):
        self._config = config
        self._snapshot_cache: _SnapshotCacheEntry | None = None

    def _empty_snapshot(self) -> SkillSnapshot:
        return SkillSnapshot(
            prompt="",
            skills=(),
            discovered_count=0,
            eligible_count=0,
            selected_count=0,
            truncated=False,
        )

    def _build_mtime_signature(self) -> str:
        if not self._config.snapshot_cache_use_mtime:
            return "mtime-disabled"

        root = Path(self._config.skills_dir)
        if not root.exists() or not root.is_dir():
            return "skills-dir-missing"

        material: list[tuple[str, int, int]] = []
        for skill_file in root.rglob("SKILL.md"):
            try:
                stat = skill_file.stat()
            except OSError:
                continue
            material.append((
                str(skill_file.relative_to(root)).replace("\\", "/").lower(),
                int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
                int(stat.st_size),
            ))

        digest = hashlib.sha256(repr(sorted(material)).encode("utf-8")).hexdigest()
        return digest

    def _try_read_snapshot_cache_ttl_only(self) -> SkillSnapshot | None:
        ttl_seconds = max(0.0, float(self._config.snapshot_cache_ttl_seconds))
        entry = self._snapshot_cache
        if entry is None:
            return None
        if ttl_seconds <= 0.0:
            return None
        if (monotonic() - entry.cached_at_monotonic) > ttl_seconds:
            return None
        return entry.snapshot

    def _try_read_snapshot_cache(self, *, signature: str) -> SkillSnapshot | None:
        ttl_seconds = max(0.0, float(self._config.snapshot_cache_ttl_seconds))
        entry = self._snapshot_cache
        if entry is None:
            return None
        if ttl_seconds <= 0.0:
            return None
        if (monotonic() - entry.cached_at_monotonic) > ttl_seconds:
            return None
        if entry.signature != signature:
            return None
        return entry.snapshot

    def _write_snapshot_cache(self, *, signature: str, snapshot: SkillSnapshot) -> None:
        ttl_seconds = max(0.0, float(self._config.snapshot_cache_ttl_seconds))
        if ttl_seconds <= 0.0:
            return
        self._snapshot_cache = _SnapshotCacheEntry(
            snapshot=snapshot,
            cached_at_monotonic=monotonic(),
            signature=signature,
        )

    def build_snapshot(self) -> SkillSnapshot:
        if not self._config.enabled:
            return self._empty_snapshot()

        fresh_snapshot = self._try_read_snapshot_cache_ttl_only()
        if fresh_snapshot is not None:
            return fresh_snapshot

        signature = self._build_mtime_signature()
        cached_snapshot = self._try_read_snapshot_cache(signature=signature)
        if cached_snapshot is not None:
            return cached_snapshot

        discovered = discover_skills(
            skills_root=self._config.skills_dir,
            max_discovered=self._config.max_discovered,
        )
        eligible, _ = filter_eligible_skills(discovered)
        snapshot = build_skill_snapshot(
            discovered=discovered,
            eligible=eligible,
            max_prompt_chars=self._config.max_prompt_chars,
        )
        self._write_snapshot_cache(signature=signature, snapshot=snapshot)
        return snapshot
