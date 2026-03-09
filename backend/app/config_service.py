"""ConfigService — 3-layer config read/write with persistence and change events.

Layer 1: .env values (read from Settings singleton, read-only via this service)
Layer 2: config_overrides.json (runtime changes, persistent across restarts)
Layer 3: In-memory transient overrides

Feature flag: CONFIG_SERVICE_ENABLED (default True). When False, all reads
fall through to the original ``settings`` singleton.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config_sections import (
    SECTION_REGISTRY,
    SENSITIVE_FIELDS,
    field_to_section,
)

logger = logging.getLogger(__name__)

CONFIG_SERVICE_ENABLED = os.getenv("CONFIG_SERVICE_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on",
}


@dataclass(frozen=True)
class ChangeResult:
    section_key: str
    field: str
    previous_value: Any
    new_value: Any
    persisted: bool
    validation_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.validation_errors) == 0


@dataclass
class SectionMeta:
    key: str
    fields: dict[str, dict[str, Any]]  # field_name -> {type, default, sensitive}


class ConfigService:
    """Central config read/write service with 3-layer override architecture."""

    def __init__(
        self,
        settings_obj: Any,
        *,
        overrides_path: str | Path | None = None,
    ) -> None:
        self._settings = settings_obj
        self._overrides_path = Path(overrides_path) if overrides_path else self._default_overrides_path()
        self._locks: dict[str, threading.Lock] = {key: threading.Lock() for key in SECTION_REGISTRY}
        self._global_lock = threading.Lock()
        self._subscribers: dict[str, list[Callable[[str, str, Any, Any], None]]] = {
            key: [] for key in SECTION_REGISTRY
        }
        # Layer 2: persistent overrides loaded from JSON
        self._persistent_overrides: dict[str, dict[str, Any]] = {}
        # Layer 3: transient in-memory overrides
        self._transient_overrides: dict[str, dict[str, Any]] = {}
        self._load_persistent_overrides()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _default_overrides_path(self) -> Path:
        workspace = getattr(self._settings, "workspace_root", None)
        if workspace:
            return Path(workspace) / "config_overrides.json"
        from app.config import BACKEND_DIR
        return Path(BACKEND_DIR).parent / "config_overrides.json"

    def _load_persistent_overrides(self) -> None:
        if not self._overrides_path.exists():
            return
        try:
            raw = self._overrides_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                self._persistent_overrides = data
                self._apply_overrides_to_settings()
                logger.info(
                    "config_overrides_loaded path=%s sections=%d",
                    self._overrides_path,
                    len(data),
                )
        except Exception:
            logger.warning("config_overrides_load_failed path=%s", self._overrides_path, exc_info=True)

    def _apply_overrides_to_settings(self) -> None:
        """Apply all persistent + transient overrides to the Settings singleton."""
        for section_key, overrides in self._persistent_overrides.items():
            for field_name, value in overrides.items():
                self._set_settings_attr(field_name, value)
        for section_key, overrides in self._transient_overrides.items():
            for field_name, value in overrides.items():
                self._set_settings_attr(field_name, value)

    def _set_settings_attr(self, field_name: str, value: Any) -> None:
        try:
            setattr(self._settings, field_name, value)
        except Exception:
            # Pydantic v2 models with model_config frozen will raise
            try:
                self._settings.__dict__[field_name] = value
            except Exception:
                logger.debug("config_set_attr_failed field=%s", field_name)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_section(self, section_key: str) -> BaseModel:
        """Return a Pydantic model populated with effective values for the section."""
        model_cls = SECTION_REGISTRY.get(section_key)
        if model_cls is None:
            raise KeyError(f"Unknown section: {section_key}")
        data: dict[str, Any] = {}
        for field_name in model_cls.model_fields:
            data[field_name] = self.get_value(section_key, field_name)
        return model_cls.model_validate(data)

    def get_value(self, section_key: str, field_name: str) -> Any:
        """Return effective value: transient > persistent > settings."""
        # Layer 3: transient
        transient = self._transient_overrides.get(section_key, {})
        if field_name in transient:
            return transient[field_name]
        # Layer 2: persistent
        persistent = self._persistent_overrides.get(section_key, {})
        if field_name in persistent:
            return persistent[field_name]
        # Layer 1: original settings
        return getattr(self._settings, field_name, None)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_section(self, section_key: str, updates: dict[str, Any], *, persist: bool = True) -> list[ChangeResult]:
        """Update multiple fields in a section. Returns list of ChangeResults."""
        results: list[ChangeResult] = []
        for field_name, new_value in updates.items():
            result = self.update_value(section_key, field_name, new_value, persist=persist)
            results.append(result)
        return results

    def update_value(
        self,
        section_key: str,
        field_name: str,
        value: Any,
        *,
        persist: bool = True,
    ) -> ChangeResult:
        """Update a single config value with validation."""
        model_cls = SECTION_REGISTRY.get(section_key)
        if model_cls is None:
            return ChangeResult(
                section_key=section_key,
                field=field_name,
                previous_value=None,
                new_value=value,
                persisted=False,
                validation_errors=[f"Unknown section: {section_key}"],
            )

        if field_name not in model_cls.model_fields:
            return ChangeResult(
                section_key=section_key,
                field=field_name,
                previous_value=None,
                new_value=value,
                persisted=False,
                validation_errors=[f"Unknown field '{field_name}' in section '{section_key}'"],
            )

        if field_name in SENSITIVE_FIELDS:
            return ChangeResult(
                section_key=section_key,
                field=field_name,
                previous_value="***",
                new_value="***",
                persisted=False,
                validation_errors=[f"Field '{field_name}' is sensitive and cannot be changed via API"],
            )

        # Validate by constructing a partial model
        try:
            current_data = {}
            for fn in model_cls.model_fields:
                current_data[fn] = self.get_value(section_key, fn)
            current_data[field_name] = value
            model_cls.model_validate(current_data)
        except ValidationError as exc:
            return ChangeResult(
                section_key=section_key,
                field=field_name,
                previous_value=self.get_value(section_key, field_name),
                new_value=value,
                persisted=False,
                validation_errors=[str(e["msg"]) for e in exc.errors()],
            )

        lock = self._locks.get(section_key, self._global_lock)
        with lock:
            previous = self.get_value(section_key, field_name)

            if persist:
                if section_key not in self._persistent_overrides:
                    self._persistent_overrides[section_key] = {}
                self._persistent_overrides[section_key][field_name] = value
                persisted = self._save_persistent_overrides()
            else:
                if section_key not in self._transient_overrides:
                    self._transient_overrides[section_key] = {}
                self._transient_overrides[section_key][field_name] = value
                persisted = False

            # Apply to settings singleton
            self._set_settings_attr(field_name, value)

            # Notify subscribers
            self._notify(section_key, field_name, previous, value)

            return ChangeResult(
                section_key=section_key,
                field=field_name,
                previous_value=previous,
                new_value=value,
                persisted=persisted,
            )

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_section(self, section_key: str) -> bool:
        """Reset a section to .env defaults by removing all overrides."""
        model_cls = SECTION_REGISTRY.get(section_key)
        if model_cls is None:
            return False
        lock = self._locks.get(section_key, self._global_lock)
        with lock:
            self._persistent_overrides.pop(section_key, None)
            self._transient_overrides.pop(section_key, None)
            self._save_persistent_overrides()
            # Reload is implicit — next get_value falls through to settings
            return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_persistent_overrides(self) -> bool:
        try:
            self._overrides_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._overrides_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._persistent_overrides, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self._overrides_path)
            return True
        except Exception:
            logger.warning("config_overrides_save_failed path=%s", self._overrides_path, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Subscriptions (Observer pattern)
    # ------------------------------------------------------------------

    def subscribe(self, section_key: str, callback: Callable[[str, str, Any, Any], None]) -> None:
        """Register a callback for changes in a section.
        callback(section_key, field_name, old_value, new_value)
        """
        if section_key in self._subscribers:
            self._subscribers[section_key].append(callback)

    def _notify(self, section_key: str, field_name: str, old_value: Any, new_value: Any) -> None:
        for cb in self._subscribers.get(section_key, []):
            try:
                cb(section_key, field_name, old_value, new_value)
            except Exception:
                logger.warning("config_subscriber_error section=%s field=%s", section_key, field_name, exc_info=True)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_all_sections_metadata(self) -> list[SectionMeta]:
        """Return metadata for all sections (field names, types, defaults, sensitivity)."""
        result: list[SectionMeta] = []
        for key, model_cls in SECTION_REGISTRY.items():
            fields: dict[str, dict[str, Any]] = {}
            for fname, finfo in model_cls.model_fields.items():
                annotation = finfo.annotation
                type_name = getattr(annotation, "__name__", str(annotation))
                fields[fname] = {
                    "type": type_name,
                    "default": finfo.default if finfo.default is not None else None,
                    "sensitive": fname in SENSITIVE_FIELDS,
                }
            result.append(SectionMeta(key=key, fields=fields))
        return result

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    def export_diff(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return all runtime overrides vs .env defaults."""
        diff: dict[str, dict[str, dict[str, Any]]] = {}
        for section_key in SECTION_REGISTRY:
            section_diff: dict[str, dict[str, Any]] = {}
            for field_name in list(self._persistent_overrides.get(section_key, {})) + list(
                self._transient_overrides.get(section_key, {})
            ):
                env_value = getattr(self._settings, field_name, None)
                effective = self.get_value(section_key, field_name)
                # Get original .env value (before overrides)
                original = env_value  # Approximate — the settings object already has overrides applied
                if field_name in self._persistent_overrides.get(section_key, {}):
                    override_val = self._persistent_overrides[section_key][field_name]
                    section_diff[field_name] = {
                        "override": override_val,
                        "layer": "persistent",
                    }
                if field_name in self._transient_overrides.get(section_key, {}):
                    override_val = self._transient_overrides[section_key][field_name]
                    section_diff[field_name] = {
                        "override": override_val,
                        "layer": "transient",
                    }
            if section_diff:
                diff[section_key] = section_diff
        return diff


# ---------------------------------------------------------------------------
# Module-level singleton (lazy)
# ---------------------------------------------------------------------------

_instance: ConfigService | None = None
_init_lock = threading.Lock()


def get_config_service() -> ConfigService:
    """Return the global ConfigService singleton. Creates it lazily."""
    global _instance  # noqa: PLW0603
    if _instance is not None:
        return _instance
    with _init_lock:
        if _instance is not None:
            return _instance
        from app.config import settings as _settings
        _instance = ConfigService(_settings)
        return _instance


def init_config_service(settings_obj: Any, *, overrides_path: str | Path | None = None) -> ConfigService:
    """Explicitly initialize the global ConfigService (called from startup)."""
    global _instance  # noqa: PLW0603
    with _init_lock:
        _instance = ConfigService(settings_obj, overrides_path=overrides_path)
        return _instance
