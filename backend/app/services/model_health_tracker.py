"""T2.1: ModelHealthTracker — misst Latenz und Erfolgsrate im laufenden Betrieb.

Ring-Buffer pro Modell-ID, async-safe via asyncio.Lock.
Persistiert aggregierten Snapshot in state_store (JSON).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.model_routing.capability_profile import ModelCapabilityProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelHealthSample:
    model_id: str
    latency_ms: int
    success: bool
    timestamp_mono: float        # time.monotonic() when recorded
    timestamp_utc: str           # ISO-8601 for persistence
    request_id: str


@dataclass(frozen=True)
class ModelHealthSnapshot:
    model_id: str
    p50_latency_ms: int
    p95_latency_ms: int
    health_score: float          # success_rate over ring buffer
    sample_count: int
    last_updated_utc: str
    is_stale: bool


class ModelHealthTracker:
    """In-memory ring-buffer health tracker per model, async-safe.

    Design principles:
    - ``asyncio.Lock`` guards all mutations (no GIL assumptions).
    - ``apply_to_profile`` returns a **new** immutable profile; originals are never mutated.
    - ``time.monotonic()`` for latency; ``datetime.utcnow`` only for persistence snapshots.
    - Stale detection: if last sample is older than ``stale_after_seconds`` (monotonic), snapshot
      is marked ``is_stale=True`` and ``apply_to_profile`` returns the original profile unchanged.
    """

    def __init__(
        self,
        *,
        ring_buffer_size: int = 50,
        min_samples: int = 10,
        stale_after_seconds: int = 300,
        persist_path: Path | str | None = None,
    ) -> None:
        self._ring_buffer_size = max(1, int(ring_buffer_size))
        self._min_samples = max(1, int(min_samples))
        self._stale_after_seconds = max(1, int(stale_after_seconds))
        self._persist_path: Path | None = Path(persist_path) if persist_path else None
        self._lock = asyncio.Lock()
        # model_id → deque of ModelHealthSample
        self._buffers: dict[str, deque[ModelHealthSample]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record(
        self,
        *,
        model_id: str,
        latency_ms: int,
        success: bool,
        request_id: str,
    ) -> None:
        """Append a health sample.  Async-safe."""
        sample = ModelHealthSample(
            model_id=model_id,
            latency_ms=max(0, int(latency_ms)),
            success=bool(success),
            timestamp_mono=time.monotonic(),
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            request_id=request_id,
        )
        async with self._lock:
            buf = self._buffers.setdefault(
                model_id,
                deque(maxlen=self._ring_buffer_size),
            )
            buf.append(sample)

    def snapshot(self, model_id: str) -> ModelHealthSnapshot | None:
        """Compute a point-in-time snapshot.

        This is intentionally not async-locked.
        ``deque`` operations are thread-safe under CPython's GIL for single
        append/pop, but ``list(buf)`` iterates without holding ``self._lock``.
        This is acceptable for a *best-effort* health snapshot: a concurrent
        ``record()`` call could append during iteration, leading to a mildly
        inconsistent read — but never a crash, since ``deque`` is C-level
        thread-safe for iteration in CPython.
        """
        buf = self._buffers.get(model_id)
        if not buf:
            return None
        samples = list(buf)  # snapshot copy
        if not samples:
            return None

        latencies = sorted(s.latency_ms for s in samples)
        success_count = sum(1 for s in samples if s.success)
        count = len(samples)

        p50_idx = max(0, int(count * 0.50) - 1)
        p95_idx = max(0, int(count * 0.95) - 1)

        latest_mono = max(s.timestamp_mono for s in samples)
        is_stale = (time.monotonic() - latest_mono) > self._stale_after_seconds

        return ModelHealthSnapshot(
            model_id=model_id,
            p50_latency_ms=latencies[p50_idx],
            p95_latency_ms=latencies[min(p95_idx, count - 1)],
            health_score=round(success_count / count, 4) if count else 0.0,
            sample_count=count,
            last_updated_utc=max(s.timestamp_utc for s in samples),
            is_stale=is_stale,
        )

    def apply_to_profile(self, profile: ModelCapabilityProfile) -> ModelCapabilityProfile:
        """Return a *new* profile with measured values overlaid.  Original is never mutated."""
        snap = self.snapshot(profile.model_id)
        if snap is None or snap.is_stale or snap.sample_count < self._min_samples:
            return profile
        return profile.model_copy(
            update={
                "health_score": snap.health_score,
                "expected_latency_ms": snap.p50_latency_ms,
            }
        )

    def all_snapshots(self) -> list[ModelHealthSnapshot]:
        """Return snapshots for all tracked models (for debug/diagnostics)."""
        result: list[ModelHealthSnapshot] = []
        for model_id in list(self._buffers.keys()):
            snap = self.snapshot(model_id)
            if snap is not None:
                result.append(snap)
        return result

    # ------------------------------------------------------------------
    # Persistence  (best-effort, never raises)
    # ------------------------------------------------------------------

    async def persist(self) -> None:
        """Save aggregated snapshots to disk.  Fire-and-forget safe."""
        self.persist_sync()

    def persist_sync(self) -> None:
        """Synchronous variant — usable from shutdown hooks that are not async."""
        if self._persist_path is None:
            return
        try:
            snapshots = self.all_snapshots()
            payload: dict[str, Any] = {
                "version": 1,
                "snapshots": [
                    {
                        "model_id": s.model_id,
                        "p50_latency_ms": s.p50_latency_ms,
                        "p95_latency_ms": s.p95_latency_ms,
                        "health_score": s.health_score,
                        "sample_count": s.sample_count,
                        "last_updated_utc": s.last_updated_utc,
                    }
                    for s in snapshots
                ],
            }
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            logger.debug("model_health_tracker_persist_failed", exc_info=True)

    def load_persisted(self) -> None:
        """Warm ring-buffers from a persisted snapshot file (best-effort).

        This restores *synthetic* samples so that ``apply_to_profile`` works immediately
        after a cold restart, without waiting for ``min_samples`` real calls.
        """
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != 1:
                return
            for entry in raw.get("snapshots", []):
                model_id = str(entry.get("model_id", "")).strip()
                if not model_id:
                    continue
                sample_count = max(0, int(entry.get("sample_count", 0)))
                if sample_count == 0:
                    continue
                health_score = max(0.0, min(1.0, float(entry.get("health_score", 0.9))))
                p50 = max(1, int(entry.get("p50_latency_ms", 1000)))
                last_updated = str(entry.get("last_updated_utc", ""))
                synthetic_count = min(sample_count, self._ring_buffer_size)
                success_count = round(synthetic_count * health_score)
                buf = deque(maxlen=self._ring_buffer_size)
                now_mono = time.monotonic()
                for i in range(synthetic_count):
                    buf.append(
                        ModelHealthSample(
                            model_id=model_id,
                            latency_ms=p50,
                            success=(i < success_count),
                            timestamp_mono=now_mono,
                            timestamp_utc=last_updated or datetime.now(timezone.utc).isoformat(),
                            request_id="persisted",
                        )
                    )
                self._buffers[model_id] = buf
            logger.info(
                "model_health_tracker_loaded models=%d",
                len(self._buffers),
            )
        except Exception:
            logger.debug("model_health_tracker_load_failed", exc_info=True)
