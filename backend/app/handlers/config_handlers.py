"""Handlers for config.* control endpoints."""
from __future__ import annotations

from typing import Any

from app.config_service import get_config_service


def handle_config_sections(request: dict[str, Any]) -> dict[str, Any]:
    svc = get_config_service()
    sections = svc.get_all_sections_metadata()
    return {
        "sections": [
            {
                "key": s.key,
                "label": s.key.replace("_", " ").title(),
                "field_count": len(s.fields),
                "fields": [
                    {"name": fname, **fmeta}
                    for fname, fmeta in s.fields.items()
                ],
            }
            for s in sections
        ],
    }


def handle_config_get(request: dict[str, Any]) -> dict[str, Any]:
    section_key = str(request.get("sectionKey") or "").strip()
    if not section_key:
        return {"error": "sectionKey is required"}
    svc = get_config_service()
    try:
        section = svc.get_section(section_key)
    except KeyError as exc:
        return {"error": str(exc)}
    return {
        "sectionKey": section_key,
        "values": section.model_dump(),
    }


def handle_config_update(request: dict[str, Any]) -> dict[str, Any]:
    section_key = str(request.get("sectionKey") or "").strip()
    updates = request.get("updates")
    if not section_key:
        return {"error": "sectionKey is required"}
    if not isinstance(updates, dict) or not updates:
        return {"error": "updates must be a non-empty object"}
    svc = get_config_service()
    results = svc.update_section(section_key, updates)
    errors = []
    applied = []
    for r in results:
        if not r.ok:
            errors.extend(r.validation_errors)
        else:
            applied.append({
                "field": r.field,
                "previousValue": r.previous_value,
                "newValue": r.new_value,
                "persisted": r.persisted,
            })
    return {
        "ok": len(errors) == 0,
        "changes": applied,
        "validation_errors": errors,
    }


def handle_config_diff(request: dict[str, Any]) -> dict[str, Any]:
    svc = get_config_service()
    raw = svc.export_diff()
    # Reshape to match frontend ConfigDiffResponse: {overrides: {section: {field: {env_value, runtime_value}}}}
    overrides: dict[str, dict[str, dict[str, Any]]] = {}
    for section_key, fields in raw.items():
        section_overrides: dict[str, dict[str, Any]] = {}
        for field_name, info in fields.items():
            env_value = getattr(svc._settings, field_name, None)
            runtime_value = svc.get_value(section_key, field_name)
            section_overrides[field_name] = {
                "env_value": env_value,
                "runtime_value": runtime_value,
            }
        if section_overrides:
            overrides[section_key] = section_overrides
    return {"overrides": overrides}


def handle_config_reset(request: dict[str, Any]) -> dict[str, Any]:
    section_key = str(request.get("sectionKey") or "").strip()
    if not section_key:
        return {"error": "sectionKey is required"}
    svc = get_config_service()
    # Collect field names that had overrides before reset
    from app.config_sections import SECTION_REGISTRY
    model_cls = SECTION_REGISTRY.get(section_key)
    reset_fields = list(model_cls.model_fields.keys()) if model_cls else []
    ok = svc.reset_section(section_key)
    return {"ok": ok, "sectionKey": section_key, "reset_fields": reset_fields if ok else []}
