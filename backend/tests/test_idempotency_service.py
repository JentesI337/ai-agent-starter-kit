from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from app.services.idempotency_manager import IdempotencyManager
from app.services.idempotency_service import (
    idempotency_lookup_or_raise,
    idempotency_register,
    prune_idempotency_registry,
)


def _iso_ago(seconds: int) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def test_prune_idempotency_registry_removes_expired_entries() -> None:
    registry = {
        "old": {"created_at": _iso_ago(120), "fingerprint": "a"},
        "new": {"created_at": _iso_ago(5), "fingerprint": "b"},
    }

    prune_idempotency_registry(registry=registry, ttl_seconds=60, max_entries=0)

    assert "old" not in registry
    assert "new" in registry


def test_prune_idempotency_registry_enforces_max_entries_oldest_first() -> None:
    registry = {
        "k1": {"created_at": _iso_ago(30), "fingerprint": "1"},
        "k2": {"created_at": _iso_ago(20), "fingerprint": "2"},
        "k3": {"created_at": _iso_ago(10), "fingerprint": "3"},
    }

    prune_idempotency_registry(registry=registry, ttl_seconds=0, max_entries=2)

    assert set(registry.keys()) == {"k2", "k3"}


def test_lookup_prunes_expired_before_read() -> None:
    registry = {
        "exp": {
            "created_at": _iso_ago(120),
            "fingerprint": "fp",
            "run_id": "run-1",
        }
    }

    replay = idempotency_lookup_or_raise(
        idempotency_key="exp",
        fingerprint="fp",
        registry=registry,
        lock=Lock(),
        conflict_message="conflict",
        ttl_seconds=60,
        max_entries=100,
        replay_builder=lambda key, existing: {"key": key, "run_id": existing.get("run_id")},
    )

    assert replay is None
    assert "exp" not in registry


def test_register_prunes_and_caps_registry() -> None:
    registry = {
        "old": {"created_at": _iso_ago(120), "fingerprint": "old"},
        "mid": {"created_at": _iso_ago(20), "fingerprint": "mid"},
    }

    idempotency_register(
        idempotency_key="new",
        fingerprint="new",
        value={"response": {"ok": True}},
        registry=registry,
        lock=Lock(),
        ttl_seconds=60,
        max_entries=2,
    )

    assert "old" not in registry
    assert len(registry) == 2
    assert "new" in registry
    assert "mid" in registry


def test_idempotency_manager_isolates_namespaces() -> None:
    manager = IdempotencyManager(ttl_seconds=60, max_entries=100)

    manager.register(
        namespace="run",
        idempotency_key="dup-key",
        fingerprint="fp-run",
        value={"run_id": "run-1"},
    )
    manager.register(
        namespace="workflow",
        idempotency_key="dup-key",
        fingerprint="fp-workflow",
        value={"workflow_id": "wf-1"},
    )

    run_replay = manager.lookup_or_raise(
        namespace="run",
        idempotency_key="dup-key",
        fingerprint="fp-run",
        conflict_message="conflict",
        replay_builder=lambda key, existing: {"key": key, "run_id": existing.get("run_id")},
    )
    workflow_replay = manager.lookup_or_raise(
        namespace="workflow",
        idempotency_key="dup-key",
        fingerprint="fp-workflow",
        conflict_message="conflict",
        replay_builder=lambda key, existing: {"key": key, "workflow_id": existing.get("workflow_id")},
    )

    assert run_replay == {"key": "dup-key", "run_id": "run-1"}
    assert workflow_replay == {"key": "dup-key", "workflow_id": "wf-1"}


def test_idempotency_manager_lookup_is_namespace_scoped() -> None:
    manager = IdempotencyManager(ttl_seconds=60, max_entries=100)
    manager.register(
        namespace="run",
        idempotency_key="run-only",
        fingerprint="fp-run",
        value={"run_id": "run-1"},
    )

    replay = manager.lookup_or_raise(
        namespace="workflow",
        idempotency_key="run-only",
        fingerprint="fp-run",
        conflict_message="conflict",
        replay_builder=lambda key, existing: {"key": key, "value": existing},
    )

    assert replay is None
