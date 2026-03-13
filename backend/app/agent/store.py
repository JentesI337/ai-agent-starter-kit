"""Unified agent store — single persistence layer for all agents.

Replaces ``AgentConfigStore``, ``CustomAgentStore``, and the in-memory
``BUILTIN_AGENT_DEFINITIONS`` dict with one JSON-file-per-agent store.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from app.agent.factory_defaults import FACTORY_DEFAULTS
from app.agent.record import UnifiedAgentRecord

logger = logging.getLogger(__name__)


class UnifiedAgentStore:
    """Manages all agent records (built-in and custom) as JSON files.

    On startup, ``_ensure_builtins()`` writes factory defaults for any
    missing built-in agent.  The manifest controls which agents are
    enabled by default on a fresh install.
    """

    def __init__(
        self,
        persist_dir: str | Path,
        manifest_path: str | Path | None = None,
    ) -> None:
        self._persist_dir = Path(persist_dir).resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # Load manifest
        self._manifest_path = Path(manifest_path) if manifest_path else None
        self._manifest = self._load_manifest()

        # Bootstrap built-in agents on first run
        self._ensure_builtins()

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _load_manifest(self) -> dict[str, Any]:
        if self._manifest_path and self._manifest_path.exists():
            try:
                return json.loads(self._manifest_path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("agent_manifest_load_failed path=%s", self._manifest_path, exc_info=True)
        return {"enabled_agents": list(FACTORY_DEFAULTS.keys()), "disabled_agents": []}

    def get_manifest(self) -> dict[str, Any]:
        return dict(self._manifest)

    def update_manifest(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if "enabled_agents" in data:
                self._manifest["enabled_agents"] = list(data["enabled_agents"])
            if "disabled_agents" in data:
                self._manifest["disabled_agents"] = list(data["disabled_agents"])
            if self._manifest_path:
                self._persist_json(self._manifest_path, self._manifest)
            return dict(self._manifest)

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _ensure_builtins(self) -> None:
        """Write factory defaults for any missing built-in agent files."""
        disabled = set(self._manifest.get("disabled_agents", []))
        for agent_id, default_record in FACTORY_DEFAULTS.items():
            path = self._agent_path(agent_id)
            if path.exists():
                continue
            record = default_record.model_copy(deep=True)
            if agent_id in disabled:
                record.enabled = False
            self._write_record(record)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_all(self) -> list[UnifiedAgentRecord]:
        """Return all agents (enabled + disabled)."""
        items: list[UnifiedAgentRecord] = []
        with self._lock:
            for path in sorted(self._persist_dir.glob("*.json")):
                record = self._read_record(path)
                if record is not None:
                    items.append(record)
        return items

    def list_enabled(self) -> list[UnifiedAgentRecord]:
        """Return only enabled agents (used for runtime registry)."""
        return [r for r in self.list_all() if r.enabled]

    def get(self, agent_id: str) -> UnifiedAgentRecord | None:
        normalized = self._normalize_id(agent_id)
        if not normalized:
            return None
        with self._lock:
            return self._read_record(self._agent_path(normalized))

    def update(self, agent_id: str, patch: dict[str, Any]) -> UnifiedAgentRecord:
        """Partial update with security floor enforcement."""
        with self._lock:
            current = self._read_record(self._agent_path(agent_id))
            if current is None:
                raise KeyError(f"Agent not found: {agent_id}")

            merged = current.model_dump()
            _deep_merge(merged, patch)

            # Immutable fields
            merged["agent_id"] = current.agent_id
            merged["origin"] = current.origin

            # Security floor enforcement for built-in agents
            factory = FACTORY_DEFAULTS.get(agent_id)
            if factory is not None:
                self._enforce_security_floor(merged, factory)

            merged["version"] = current.version + 1
            record = UnifiedAgentRecord.model_validate(merged)
            self._write_record(record)
            return record

    def create(self, data: dict[str, Any]) -> UnifiedAgentRecord:
        """Create a new custom agent."""
        data["origin"] = "custom"
        data.setdefault("category", "custom")
        data.setdefault("enabled", True)
        data.setdefault("version", 1)

        # Generate ID if not provided
        if not data.get("agent_id"):
            name = data.get("display_name", "custom-agent")
            data["agent_id"] = self._normalize_id(f"custom-{name}")

        record = UnifiedAgentRecord.model_validate(data)

        with self._lock:
            path = self._agent_path(record.agent_id)
            if path.exists():
                raise ValueError(f"Agent already exists: {record.agent_id}")
            self._write_record(record)
        return record

    def delete(self, agent_id: str) -> bool:
        """Delete a custom agent. Built-in agents cannot be deleted."""
        normalized = self._normalize_id(agent_id)
        if not normalized:
            return False

        with self._lock:
            record = self._read_record(self._agent_path(normalized))
            if record is None:
                return False
            if record.origin == "builtin":
                raise ValueError(f"Cannot delete built-in agent: {normalized}")
            path = self._agent_path(normalized)
            path.unlink(missing_ok=True)
            return True

    def reset(self, agent_id: str) -> UnifiedAgentRecord:
        """Restore a built-in agent to factory defaults."""
        factory = FACTORY_DEFAULTS.get(agent_id)
        if factory is None:
            raise KeyError(f"No factory default for agent: {agent_id}")

        with self._lock:
            current = self._read_record(self._agent_path(agent_id))
            record = factory.model_copy(deep=True)
            # Preserve enabled state from current if it exists
            if current is not None:
                record.enabled = current.enabled
            record.version = (current.version + 1) if current else 1
            self._write_record(record)
            return record

    # ------------------------------------------------------------------
    # Security floor
    # ------------------------------------------------------------------

    @staticmethod
    def _enforce_security_floor(merged: dict[str, Any], factory: UnifiedAgentRecord) -> None:
        """Prevent weakening of factory security constraints."""
        factory_tp = factory.tool_policy

        tp = merged.setdefault("tool_policy", {})

        # read_only floor
        if factory_tp.read_only and not tp.get("read_only", True):
            tp["read_only"] = True

        # mandatory_deny floor — factory tools can never be removed
        if factory_tp.mandatory_deny:
            current_deny = set(tp.get("mandatory_deny", []))
            for tool in factory_tp.mandatory_deny:
                current_deny.add(tool)
            tp["mandatory_deny"] = sorted(current_deny)

    # ------------------------------------------------------------------
    # IO helpers
    # ------------------------------------------------------------------

    def _agent_path(self, agent_id: str) -> Path:
        safe = agent_id.replace("/", "_").replace("\\", "_")
        return self._persist_dir / f"{safe}.json"

    def _read_record(self, path: Path) -> UnifiedAgentRecord | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return UnifiedAgentRecord.model_validate(data)
        except Exception:
            logger.warning("agent_record_load_failed path=%s", path, exc_info=True)
            return None

    def _write_record(self, record: UnifiedAgentRecord) -> None:
        path = self._agent_path(record.agent_id)
        self._persist_json(path, record.model_dump())

    @staticmethod
    def _persist_json(path: Path, data: Any) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _normalize_id(raw: str) -> str:
        candidate = (raw or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate[:80]


# ---------------------------------------------------------------------------
# Deep merge utility
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ---------------------------------------------------------------------------
# Backward-compatibility wrapper for code still using CustomAgentStore API
# ---------------------------------------------------------------------------


class CustomAgentStoreCompat:
    """Thin wrapper around UnifiedAgentStore that mimics the old CustomAgentStore API.

    Handlers and tools that expect ``CustomAgentDefinition`` objects can use
    this until they are fully migrated.
    """

    def __init__(self, store: UnifiedAgentStore) -> None:
        self._store = store

    def list(self):
        """Return custom agents as compat objects."""
        return [
            _record_to_compat(r)
            for r in self._store.list_all()
            if r.origin == "custom"
        ]

    def get(self, agent_id: str):
        record = self._store.get(agent_id)
        if record is None or record.origin != "custom":
            return None
        return _record_to_compat(record)

    def upsert(self, request, id_factory=None):
        """Create or update a custom agent from a legacy request object."""
        data = _compat_request_to_dict(request, id_factory)
        agent_id = data.get("agent_id", "")
        existing = self._store.get(agent_id)
        record = self._store.update(agent_id, data) if existing is not None else self._store.create(data)
        return _record_to_compat(record)

    def delete(self, agent_id: str) -> bool:
        try:
            return self._store.delete(agent_id)
        except ValueError:
            return False


class _CompatAgentDef:
    """Minimal duck-type stand-in for CustomAgentDefinition."""

    def __init__(self, record: UnifiedAgentRecord) -> None:
        self._record = record
        self.id = record.agent_id
        self.name = record.display_name
        self.description = record.description
        self.base_agent_id = "head-agent"
        self.tool_policy = None
        if record.tool_policy.additional_allow or record.tool_policy.additional_deny:
            tp: dict[str, list[str]] = {}
            if record.tool_policy.additional_allow:
                tp["allow"] = list(record.tool_policy.additional_allow)
            if record.tool_policy.additional_deny:
                tp["deny"] = list(record.tool_policy.additional_deny)
            self.tool_policy = tp
        self.allow_subrun_delegation = False
        self.execution_mode = "parallel"
        self.triggers: list[dict] = []
        self.capabilities = list(record.capabilities)
        self.workspace_scope = None
        self.skills_scope = None
        self.credential_scope = None

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "base_agent_id": self.base_agent_id,
            "tool_policy": self.tool_policy,
            "allow_subrun_delegation": self.allow_subrun_delegation,
            "capabilities": self.capabilities,
            "workspace_scope": self.workspace_scope,
            "skills_scope": self.skills_scope,
            "credential_scope": self.credential_scope,
        }


def _record_to_compat(record: UnifiedAgentRecord) -> _CompatAgentDef:
    return _CompatAgentDef(record)


def _compat_request_to_dict(request, id_factory=None) -> dict[str, Any]:
    """Convert a legacy CustomAgentCreateRequest to a UnifiedAgentRecord dict."""
    import re as _re

    def _norm(raw: str) -> str:
        c = (raw or "").strip().lower()
        c = _re.sub(r"[^a-z0-9_-]+", "-", c)
        c = _re.sub(r"-+", "-", c).strip("-")
        return c[:80]

    source_id = getattr(request, "id", None) or getattr(request, "name", "custom-agent")
    agent_id = _norm(source_id)
    if not agent_id and id_factory is not None:
        agent_id = _norm(id_factory(getattr(request, "name", "custom-agent")))
    if not agent_id:
        agent_id = "custom-agent"

    capabilities = [
        str(c).strip().lower() for c in (getattr(request, "capabilities", None) or [])
        if isinstance(c, str) and str(c).strip()
    ]
    tp = getattr(request, "tool_policy", None) or {}
    additional_allow = [s.strip() for s in (tp.get("allow") or []) if isinstance(s, str) and s.strip()] if isinstance(tp, dict) else []
    additional_deny = [s.strip() for s in (tp.get("deny") or []) if isinstance(s, str) and s.strip()] if isinstance(tp, dict) else []

    (getattr(request, "base_agent_id", None) or "head-agent").strip().lower()

    return {
        "agent_id": agent_id,
        "origin": "custom",
        "enabled": True,
        "display_name": (getattr(request, "name", "") or "").strip(),
        "description": (getattr(request, "description", "") or "").strip(),
        "category": "custom",
        "capabilities": capabilities,
        "tool_policy": {
            "additional_allow": additional_allow,
            "additional_deny": additional_deny,
        },
    }
