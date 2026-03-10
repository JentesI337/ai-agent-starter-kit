"""Connector configuration store — JSON persistence for ConnectorConfig objects."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from app.connectors.base import ConnectorConfig

logger = logging.getLogger(__name__)


class ConnectorStore:
    """Thread-safe JSON store for connector configurations (no secrets)."""

    def __init__(self, persist_path: str | Path) -> None:
        self._persist_path = Path(persist_path)
        self._lock = threading.Lock()
        self._configs: dict[str, ConnectorConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for cid, cfg_data in data.items():
                    cfg_data["connector_id"] = cid
                    self._configs[cid] = ConnectorConfig.model_validate(cfg_data)
        except Exception:
            logger.warning("connector_store_load_failed", exc_info=True)

    def _persist(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                cid: cfg.model_dump(exclude={"connector_id"})
                for cid, cfg in self._configs.items()
            }
            tmp = self._persist_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception:
            logger.warning("connector_store_persist_failed", exc_info=True)

    def get(self, connector_id: str) -> ConnectorConfig | None:
        with self._lock:
            return self._configs.get(connector_id)

    def get_all(self) -> dict[str, ConnectorConfig]:
        with self._lock:
            return dict(self._configs)

    def upsert(self, config: ConnectorConfig) -> ConnectorConfig:
        with self._lock:
            self._configs[config.connector_id] = config
            self._persist()
            return config

    def delete(self, connector_id: str) -> bool:
        with self._lock:
            removed = self._configs.pop(connector_id, None)
            if removed is not None:
                self._persist()
            return removed is not None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_instance: ConnectorStore | None = None
_init_lock = threading.Lock()


def get_connector_store() -> ConnectorStore:
    global _instance
    if _instance is not None:
        return _instance
    with _init_lock:
        if _instance is not None:
            return _instance
        from app.config import settings
        path = Path(settings.workspace_root) / "connectors.json"
        _instance = ConnectorStore(persist_path=path)
        return _instance


def init_connector_store(persist_path: str | Path) -> ConnectorStore:
    global _instance
    with _init_lock:
        _instance = ConnectorStore(persist_path=persist_path)
        return _instance
