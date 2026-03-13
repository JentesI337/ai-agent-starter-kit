"""Encrypted credential store for connector secrets."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.connectors.base import ConnectorCredentials
from app.state.encryption import decrypt_state, encrypt_state

logger = logging.getLogger(__name__)


class CredentialStore:
    """Thread-safe, encrypted-at-rest credential persistence."""

    def __init__(self, persist_path: str | Path) -> None:
        self._persist_path = Path(persist_path)
        self._lock = threading.Lock()
        self._entries: dict[str, str] = {}  # connector_id -> encrypted JSON
        self._load()

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._entries = {k: v for k, v in data.items() if isinstance(v, str)}
        except Exception:
            logger.warning("credential_store_load_failed", exc_info=True)

    def _persist(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception:
            logger.warning("credential_store_persist_failed", exc_info=True)

    def store(self, connector_id: str, credentials: ConnectorCredentials) -> None:
        encrypted = encrypt_state(credentials.model_dump_json())
        with self._lock:
            self._entries[connector_id] = encrypted
            self._persist()

    def retrieve(self, connector_id: str) -> ConnectorCredentials | None:
        with self._lock:
            encrypted = self._entries.get(connector_id)
        if encrypted is None:
            return None
        try:
            plaintext = decrypt_state(encrypted)
            return ConnectorCredentials.model_validate_json(plaintext)
        except Exception:
            logger.warning("credential_decrypt_failed connector_id=%s", connector_id)
            return None

    def delete(self, connector_id: str) -> None:
        with self._lock:
            self._entries.pop(connector_id, None)
            self._persist()

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._entries.keys())

    def has(self, connector_id: str) -> bool:
        with self._lock:
            return connector_id in self._entries


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_instance: CredentialStore | None = None
_init_lock = threading.Lock()


def get_credential_store() -> CredentialStore:
    global _instance
    if _instance is not None:
        return _instance
    with _init_lock:
        if _instance is not None:
            return _instance
        from app.config import settings
        path = Path(settings.workspace_root) / "connector_credentials.json"
        _instance = CredentialStore(persist_path=path)
        return _instance


def init_credential_store(persist_path: str | Path) -> CredentialStore:
    global _instance
    with _init_lock:
        _instance = CredentialStore(persist_path=persist_path)
        return _instance
