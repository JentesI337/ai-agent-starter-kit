from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from app.services.idempotency_service import idempotency_lookup_or_raise, idempotency_register


class IdempotencyManager:
    def __init__(self, *, ttl_seconds: int, max_entries: int):
        self._namespaces: dict[str, dict[str, dict]] = {}
        self._lock = Lock()
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries

    def _get_registry(self, namespace: str) -> dict[str, dict]:
        key = (namespace or "default").strip().lower() or "default"
        registry = self._namespaces.get(key)
        if registry is None:
            registry = {}
            self._namespaces[key] = registry
        return registry

    def lookup_or_raise(
        self,
        *,
        namespace: str,
        idempotency_key: str | None,
        fingerprint: str,
        conflict_message: str,
        replay_builder: Callable[[str, dict], dict],
    ) -> dict | None:
        return idempotency_lookup_or_raise(
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            registry=self._get_registry(namespace),
            lock=self._lock,
            conflict_message=conflict_message,
            replay_builder=replay_builder,
            ttl_seconds=self._ttl_seconds,
            max_entries=self._max_entries,
        )

    def register(
        self,
        *,
        namespace: str,
        idempotency_key: str | None,
        fingerprint: str,
        value: dict,
    ) -> None:
        idempotency_register(
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            value=value,
            registry=self._get_registry(namespace),
            lock=self._lock,
            ttl_seconds=self._ttl_seconds,
            max_entries=self._max_entries,
        )
