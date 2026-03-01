from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock

from fastapi import HTTPException


def idempotency_lookup_or_raise(
    *,
    idempotency_key: str | None,
    fingerprint: str,
    registry: dict[str, dict],
    lock: Lock,
    conflict_message: str,
    replay_builder: Callable[[str, dict], dict],
) -> dict | None:
    if not idempotency_key:
        return None

    with lock:
        existing = registry.get(idempotency_key)

    if existing is None:
        return None

    if existing.get("fingerprint") != fingerprint:
        raise HTTPException(
            status_code=409,
            detail={
                "message": conflict_message,
                "idempotency_key": idempotency_key,
            },
        )

    return replay_builder(idempotency_key, existing)


def idempotency_register(
    *,
    idempotency_key: str | None,
    fingerprint: str,
    value: dict,
    registry: dict[str, dict],
    lock: Lock,
) -> None:
    if not idempotency_key:
        return
    with lock:
        registry[idempotency_key] = {
            "fingerprint": fingerprint,
            **value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
