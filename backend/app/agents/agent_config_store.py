"""JSON-persistent store for agent runtime configurations."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from app.agents.agent_config_schema import AgentRuntimeConfig
from app.agents.agent_definition import BUILTIN_AGENT_DEFINITIONS

logger = logging.getLogger(__name__)


def _builtin_defaults() -> dict[str, dict[str, Any]]:
    """Derive builtin defaults from the canonical agent definitions."""
    result: dict[str, dict[str, Any]] = {}
    for agent_id, defn in BUILTIN_AGENT_DEFINITIONS.items():
        entry: dict[str, Any] = {
            "temperature": defn.constraints.temperature,
            "reflection_passes": defn.constraints.reflection_passes,
            "reasoning_depth": defn.constraints.reasoning_depth,
            "read_only": defn.tool_policy.read_only,
        }
        if defn.constraints.max_context is not None:
            entry["max_context"] = defn.constraints.max_context
        if defn.tool_policy.mandatory_deny:
            entry["mandatory_deny_tools"] = list(defn.tool_policy.mandatory_deny)
        result[agent_id] = entry
    return result


BUILTIN_AGENT_DEFAULTS: dict[str, dict[str, Any]] = _builtin_defaults()


class AgentConfigStore:
    """Manages runtime agent configurations with JSON persistence."""

    def __init__(self, persist_dir: str | Path) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._configs: dict[str, AgentRuntimeConfig] = {}
        self._load_all()

    def _config_path(self, agent_id: str) -> Path:
        safe_name = agent_id.replace("/", "_").replace("\\", "_")
        return self._persist_dir / f"{safe_name}.json"

    def _load_all(self) -> None:
        for agent_id, defaults in BUILTIN_AGENT_DEFAULTS.items():
            config_data = {"agent_id": agent_id, **defaults}
            path = self._config_path(agent_id)
            if path.exists():
                try:
                    override_data = json.loads(path.read_text(encoding="utf-8"))
                    config_data.update(override_data)
                    config_data["agent_id"] = agent_id
                except Exception:
                    logger.warning("agent_config_load_failed agent_id=%s", agent_id, exc_info=True)
            self._configs[agent_id] = AgentRuntimeConfig.model_validate(config_data)

    def get(self, agent_id: str) -> AgentRuntimeConfig:
        with self._lock:
            if agent_id in self._configs:
                return self._configs[agent_id]
            defaults = BUILTIN_AGENT_DEFAULTS.get(agent_id, {})
            config = AgentRuntimeConfig(agent_id=agent_id, **defaults)
            self._configs[agent_id] = config
            return config

    def get_all(self) -> dict[str, AgentRuntimeConfig]:
        with self._lock:
            return dict(self._configs)

    def update(self, agent_id: str, updates: dict[str, Any]) -> AgentRuntimeConfig:
        with self._lock:
            current = self._configs.get(agent_id)
            if current is None:
                defaults = BUILTIN_AGENT_DEFAULTS.get(agent_id, {})
                current = AgentRuntimeConfig(agent_id=agent_id, **defaults)

            # Security floor: if builtin says read_only=True, mandatory_deny cannot be weakened
            builtin = BUILTIN_AGENT_DEFAULTS.get(agent_id, {})
            builtin_read_only = builtin.get("read_only", False)
            builtin_mandatory_deny = builtin.get("mandatory_deny_tools", [])

            merged = current.model_dump()
            merged.update(updates)
            merged["agent_id"] = agent_id

            # Enforce security floor
            if builtin_read_only and not merged.get("read_only", True):
                merged["read_only"] = True
            if builtin_mandatory_deny:
                existing_deny = set(merged.get("mandatory_deny_tools", []))
                for tool in builtin_mandatory_deny:
                    existing_deny.add(tool)
                merged["mandatory_deny_tools"] = sorted(existing_deny)

            config = AgentRuntimeConfig.model_validate(merged)
            self._configs[agent_id] = config
            self._persist(agent_id, config)
            return config

    def reset(self, agent_id: str) -> AgentRuntimeConfig:
        with self._lock:
            defaults = BUILTIN_AGENT_DEFAULTS.get(agent_id, {})
            config = AgentRuntimeConfig(agent_id=agent_id, **defaults)
            self._configs[agent_id] = config
            path = self._config_path(agent_id)
            if path.exists():
                path.unlink()
            return config

    def snapshot(self, agent_id: str) -> AgentRuntimeConfig:
        """Return a frozen copy for use during a run."""
        return self.get(agent_id).model_copy(deep=True)

    def _persist(self, agent_id: str, config: AgentRuntimeConfig) -> None:
        try:
            path = self._config_path(agent_id)
            data = config.model_dump(exclude={"agent_id"})
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            logger.warning("agent_config_persist_failed agent_id=%s", agent_id, exc_info=True)


_instance: AgentConfigStore | None = None
_init_lock = threading.Lock()


def get_agent_config_store() -> AgentConfigStore:
    global _instance
    if _instance is not None:
        return _instance
    with _init_lock:
        if _instance is not None:
            return _instance
        from app.config import settings
        persist_dir = Path(settings.workspace_root) / "agent_configs"
        _instance = AgentConfigStore(persist_dir=persist_dir)
        return _instance


def init_agent_config_store(persist_dir: str | Path) -> AgentConfigStore:
    global _instance
    with _init_lock:
        _instance = AgentConfigStore(persist_dir=persist_dir)
        return _instance
