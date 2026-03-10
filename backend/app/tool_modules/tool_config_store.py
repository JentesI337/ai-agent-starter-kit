"""JSON store for per-tool runtime configuration."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolRuntimeConfig(BaseModel):
    tool_name: str
    enabled: bool = True
    timeout_seconds: int | None = None
    max_retries: int = Field(default=0, ge=0, le=5)
    max_result_chars: int | None = None


# ---------------------------------------------------------------------------
# Default configs for well-known tools
# ---------------------------------------------------------------------------
BUILTIN_TOOL_DEFAULTS: dict[str, dict[str, Any]] = {
    "run_command": {"timeout_seconds": 300, "enabled": True},
    "web_fetch": {"timeout_seconds": 30, "enabled": True},
    "web_search": {"timeout_seconds": 30, "enabled": True},
    "http_request": {"timeout_seconds": 30, "enabled": True},
    "code_execute": {"timeout_seconds": 60, "enabled": True},
    "browser_open": {"timeout_seconds": 30, "enabled": True},
}


class ToolConfigStore:
    """Manages per-tool runtime configurations with JSON persistence."""

    def __init__(self, persist_path: str | Path) -> None:
        self._persist_path = Path(persist_path)
        self._lock = threading.Lock()
        self._configs: dict[str, ToolRuntimeConfig] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for tool_name, config_data in data.items():
                    config_data["tool_name"] = tool_name
                    self._configs[tool_name] = ToolRuntimeConfig.model_validate(config_data)
        except Exception:
            logger.warning("tool_config_load_failed", exc_info=True)

    def _persist(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                name: config.model_dump(exclude={"tool_name"})
                for name, config in self._configs.items()
            }
            tmp = self._persist_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception:
            logger.warning("tool_config_persist_failed", exc_info=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, tool_name: str) -> ToolRuntimeConfig:
        with self._lock:
            if tool_name in self._configs:
                return self._configs[tool_name]
            defaults = BUILTIN_TOOL_DEFAULTS.get(tool_name, {})
            return ToolRuntimeConfig(tool_name=tool_name, **defaults)

    def get_all(self) -> dict[str, ToolRuntimeConfig]:
        with self._lock:
            result: dict[str, ToolRuntimeConfig] = {}
            from app.tool_catalog import TOOL_NAMES

            for name in TOOL_NAMES:
                result[name] = self.get(name)
            result.update(self._configs)
            return result

    def update(self, tool_name: str, updates: dict[str, Any]) -> ToolRuntimeConfig:
        with self._lock:
            current = self._configs.get(tool_name)
            if current is None:
                defaults = BUILTIN_TOOL_DEFAULTS.get(tool_name, {})
                current = ToolRuntimeConfig(tool_name=tool_name, **defaults)
            merged = current.model_dump()
            merged.update(updates)
            merged["tool_name"] = tool_name
            config = ToolRuntimeConfig.model_validate(merged)
            self._configs[tool_name] = config
            self._persist()
            return config

    def reset(self, tool_name: str) -> ToolRuntimeConfig:
        with self._lock:
            self._configs.pop(tool_name, None)
            self._persist()
            defaults = BUILTIN_TOOL_DEFAULTS.get(tool_name, {})
            return ToolRuntimeConfig(tool_name=tool_name, **defaults)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_instance: ToolConfigStore | None = None
_init_lock = threading.Lock()


def get_tool_config_store() -> ToolConfigStore:
    """Return the module-level singleton, lazily creating it if needed."""
    global _instance
    if _instance is not None:
        return _instance
    with _init_lock:
        if _instance is not None:
            return _instance
        from app.config import settings

        path = Path(settings.workspace_root) / "tool_configs.json"
        _instance = ToolConfigStore(persist_path=path)
        return _instance


def init_tool_config_store(persist_path: str | Path) -> ToolConfigStore:
    """Explicitly initialize the singleton with the given path."""
    global _instance
    with _init_lock:
        _instance = ToolConfigStore(persist_path=persist_path)
        return _instance
