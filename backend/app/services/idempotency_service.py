from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import HTTPException


def _parse_created_at(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.fromtimestamp(0, tz=timezone.utc)
    else:
        parsed = datetime.fromtimestamp(0, tz=timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def prune_idempotency_registry(
    *,
    registry: dict[str, dict],
    ttl_seconds: int | None,
    max_entries: int | None,
) -> None:
    ttl = max(0, int(ttl_seconds or 0))
    cap = max(0, int(max_entries or 0))

    if ttl > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl)
        expired_keys = [
            key
            for key, payload in registry.items()
            if _parse_created_at(payload.get("created_at")) < cutoff
        ]
        for key in expired_keys:
            registry.pop(key, None)

    if cap > 0 and len(registry) > cap:
        overflow = len(registry) - cap
        ordered_keys = sorted(
            registry.keys(),
            key=lambda key: _parse_created_at((registry.get(key) or {}).get("created_at")),
        )
        for key in ordered_keys[:overflow]:
            registry.pop(key, None)


def idempotency_lookup_or_raise(
    *,
    idempotency_key: str | None,
    fingerprint: str,
    registry: dict[str, dict],
    lock: Lock,
    conflict_message: str,
    replay_builder: Callable[[str, dict], dict],
    ttl_seconds: int | None = None,
    max_entries: int | None = None,
) -> dict | None:
    if not idempotency_key:
        return None

    with lock:
        prune_idempotency_registry(registry=registry, ttl_seconds=ttl_seconds, max_entries=max_entries)
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
    ttl_seconds: int | None = None,
    max_entries: int | None = None,
) -> None:
    if not idempotency_key:
        return
    with lock:
        prune_idempotency_registry(registry=registry, ttl_seconds=ttl_seconds, max_entries=max_entries)
        registry[idempotency_key] = {
            "fingerprint": fingerprint,
            **value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        prune_idempotency_registry(registry=registry, ttl_seconds=ttl_seconds, max_entries=max_entries)
