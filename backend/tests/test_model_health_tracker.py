"""Comprehensive tests for T2.1: ModelHealthTracker."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.llm.health_tracker import (
    ModelHealthSnapshot,
    ModelHealthTracker,
)
from app.llm.routing.capability_profile import ModelCapabilityProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(model_id: str = "test-model", **overrides) -> ModelCapabilityProfile:
    defaults = {
        "model_id": model_id,
        "max_context": 128_000,
        "reasoning_depth": 1,
        "reflection_passes": 0,
        "temperature": 0.3,
        "health_score": 0.95,
        "expected_latency_ms": 500,
        "cost_score": 0.5,
    }
    defaults.update(overrides)
    return ModelCapabilityProfile(**defaults)


async def _record_n(
    tracker: ModelHealthTracker,
    model_id: str,
    n: int,
    *,
    success: bool = True,
    latency_ms: int = 100,
) -> None:
    """Helper: record *n* samples quickly."""
    for i in range(n):
        await tracker.record(
            model_id=model_id,
            latency_ms=latency_ms,
            success=success,
            request_id=f"req-{i}",
        )


# ---------------------------------------------------------------------------
# Ring-buffer rotation
# ---------------------------------------------------------------------------

def test_buffer_does_not_exceed_max_size() -> None:
    tracker = ModelHealthTracker(ring_buffer_size=5, min_samples=1)
    asyncio.run(_record_n(tracker, "m1", 10, latency_ms=50))
    snap = tracker.snapshot("m1")
    assert snap is not None
    assert snap.sample_count == 5  # oldest 5 evicted


def test_oldest_samples_evicted_first() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=3, min_samples=1)
        await _record_n(tracker, "m1", 3, success=False, latency_ms=10)
        await _record_n(tracker, "m1", 3, success=True, latency_ms=20)
        snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.health_score == 1.0
        assert snap.sample_count == 3
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Snapshot computation
# ---------------------------------------------------------------------------

def test_snapshot_returns_none_for_unknown_model() -> None:
    tracker = ModelHealthTracker()
    assert tracker.snapshot("nonexistent") is None


def test_snapshot_health_score() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=10, min_samples=1)
        await _record_n(tracker, "m1", 8, success=True, latency_ms=100)
        await _record_n(tracker, "m1", 2, success=False, latency_ms=100)
        snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.health_score == 0.8
    asyncio.run(_run())


def test_snapshot_p50_and_p95() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=100, min_samples=1)
        for i in range(1, 101):
            await tracker.record(
                model_id="m1", latency_ms=i, success=True, request_id=f"r{i}"
            )
        snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.p50_latency_ms == 50
        assert snap.p95_latency_ms == 95
    asyncio.run(_run())


def test_snapshot_frozen() -> None:
    async def _run() -> ModelHealthSnapshot:
        tracker = ModelHealthTracker(ring_buffer_size=10, min_samples=1)
        await _record_n(tracker, "m1", 5, latency_ms=100)
        snap = tracker.snapshot("m1")
        assert snap is not None
        return snap

    snap = asyncio.run(_run())
    with pytest.raises(AttributeError):
        snap.model_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Stale detection
# ---------------------------------------------------------------------------

def test_not_stale_when_recent() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(stale_after_seconds=300, min_samples=1)
        await _record_n(tracker, "m1", 5, latency_ms=50)
        snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.is_stale is False
    asyncio.run(_run())


def test_stale_when_old() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(stale_after_seconds=1, min_samples=1)
        await _record_n(tracker, "m1", 5, latency_ms=50)
        real_mono = time.monotonic
        with patch("app.llm.health_tracker.time.monotonic", return_value=real_mono() + 100):
            snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.is_stale is True
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# apply_to_profile immutability
# ---------------------------------------------------------------------------

def test_apply_returns_new_profile_when_enough_samples() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=20, min_samples=5)
        await _record_n(tracker, "test-model", 10, latency_ms=200, success=True)
        original = _make_profile(expected_latency_ms=500, health_score=0.5)
        modified = tracker.apply_to_profile(original)
        assert modified is not original
        assert modified.health_score == 1.0
        assert modified.expected_latency_ms == 200
        assert original.health_score == 0.5
        assert original.expected_latency_ms == 500
    asyncio.run(_run())


def test_apply_returns_original_when_below_min_samples() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=20, min_samples=10)
        await _record_n(tracker, "test-model", 5, latency_ms=200)
        profile = _make_profile()
        result = tracker.apply_to_profile(profile)
        assert result is profile
    asyncio.run(_run())


def test_apply_returns_original_when_stale() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(stale_after_seconds=1, min_samples=1)
        await _record_n(tracker, "test-model", 5, latency_ms=200)
        profile = _make_profile()
        real_mono = time.monotonic
        with patch("app.llm.health_tracker.time.monotonic", return_value=real_mono() + 100):
            result = tracker.apply_to_profile(profile)
        assert result is profile
    asyncio.run(_run())


def test_apply_returns_original_when_no_data() -> None:
    tracker = ModelHealthTracker()
    profile = _make_profile()
    result = tracker.apply_to_profile(profile)
    assert result is profile


# ---------------------------------------------------------------------------
# Min-samples guard
# ---------------------------------------------------------------------------

def test_snapshot_exists_below_min_but_apply_ignores() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=50, min_samples=20)
        await _record_n(tracker, "test-model", 10, latency_ms=100)
        snap = tracker.snapshot("test-model")
        assert snap is not None
        assert snap.sample_count == 10
        profile = _make_profile()
        result = tracker.apply_to_profile(profile)
        assert result is profile
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Persist / load round-trip
# ---------------------------------------------------------------------------

def test_persist_and_load_roundtrip(tmp_path: Path) -> None:
    async def _run() -> None:
        persist_file = tmp_path / "health.json"
        tracker1 = ModelHealthTracker(
            ring_buffer_size=20, min_samples=5, persist_path=persist_file
        )
        await _record_n(tracker1, "model-a", 10, latency_ms=150, success=True)
        await _record_n(tracker1, "model-b", 8, latency_ms=300, success=True)
        await _record_n(tracker1, "model-b", 2, latency_ms=300, success=False)
        await tracker1.persist()
        assert persist_file.exists()

        tracker2 = ModelHealthTracker(
            ring_buffer_size=20, min_samples=5, persist_path=persist_file
        )
        tracker2.load_persisted()
        snap_a = tracker2.snapshot("model-a")
        snap_b = tracker2.snapshot("model-b")
        assert snap_a is not None
        assert snap_b is not None
        assert snap_a.sample_count == 10
        assert snap_a.health_score == 1.0
        assert snap_b.health_score == 0.8
    asyncio.run(_run())


def test_persist_sync_equivalent(tmp_path: Path) -> None:
    async def _run() -> None:
        persist_file = tmp_path / "health_sync.json"
        tracker = ModelHealthTracker(ring_buffer_size=10, min_samples=1, persist_path=persist_file)
        await _record_n(tracker, "m1", 5, latency_ms=100)
        tracker.persist_sync()
        assert persist_file.exists()
        data = json.loads(persist_file.read_text())
        assert data["version"] == 1
        assert len(data["snapshots"]) == 1
    asyncio.run(_run())


def test_load_handles_missing_file() -> None:
    tracker = ModelHealthTracker(persist_path="/nonexistent/path.json")
    tracker.load_persisted()  # should not raise


def test_load_handles_corrupt_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("NOT VALID JSON", encoding="utf-8")
    tracker = ModelHealthTracker(persist_path=bad_file)
    tracker.load_persisted()  # should not raise


def test_load_handles_wrong_version(tmp_path: Path) -> None:
    bad_file = tmp_path / "v999.json"
    bad_file.write_text(json.dumps({"version": 999}), encoding="utf-8")
    tracker = ModelHealthTracker(persist_path=bad_file)
    tracker.load_persisted()
    assert tracker.snapshot("anything") is None


def test_persist_no_path_is_noop() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(persist_path=None)
        await _record_n(tracker, "m1", 5, latency_ms=100)
        await tracker.persist()
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# all_snapshots diagnostic
# ---------------------------------------------------------------------------

def test_all_snapshots_returns_all_models() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=10, min_samples=1)
        await _record_n(tracker, "a", 3, latency_ms=10)
        await _record_n(tracker, "b", 3, latency_ms=20)
        await _record_n(tracker, "c", 3, latency_ms=30)
        snaps = tracker.all_snapshots()
        ids = {s.model_id for s in snaps}
        assert ids == {"a", "b", "c"}
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Async safety
# ---------------------------------------------------------------------------

def test_concurrent_records_do_not_corrupt() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=1000, min_samples=1)

        async def _writer(model: str, count: int) -> None:
            for i in range(count):
                await tracker.record(
                    model_id=model, latency_ms=i, success=True, request_id=f"{model}-{i}"
                )

        await asyncio.gather(
            _writer("m1", 200),
            _writer("m2", 200),
            _writer("m1", 200),
        )
        snap1 = tracker.snapshot("m1")
        snap2 = tracker.snapshot("m2")
        assert snap1 is not None
        assert snap2 is not None
        assert snap1.sample_count <= 1000
        assert snap2.sample_count == 200
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_negative_latency_clamped_to_zero() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=10, min_samples=1)
        await tracker.record(
            model_id="m1", latency_ms=-50, success=True, request_id="neg"
        )
        snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.p50_latency_ms == 0
    asyncio.run(_run())


def test_single_sample_snapshot() -> None:
    async def _run() -> None:
        tracker = ModelHealthTracker(ring_buffer_size=10, min_samples=1)
        await tracker.record(
            model_id="m1", latency_ms=42, success=True, request_id="single"
        )
        snap = tracker.snapshot("m1")
        assert snap is not None
        assert snap.p50_latency_ms == 42
        assert snap.p95_latency_ms == 42
        assert snap.health_score == 1.0
        assert snap.sample_count == 1
    asyncio.run(_run())


def test_ring_buffer_size_floor_is_1() -> None:
    tracker = ModelHealthTracker(ring_buffer_size=0)
    assert tracker._ring_buffer_size == 1
