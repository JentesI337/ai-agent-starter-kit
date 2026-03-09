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
                "fields": s.fields,
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
        "applied": applied,
        "errors": errors,
    }


def handle_config_diff(request: dict[str, Any]) -> dict[str, Any]:
    svc = get_config_service()
    return {"diff": svc.export_diff()}


def handle_config_reset(request: dict[str, Any]) -> dict[str, Any]:
    section_key = str(request.get("sectionKey") or "").strip()
    if not section_key:
        return {"error": "sectionKey is required"}
    svc = get_config_service()
    ok = svc.reset_section(section_key)
    return {"ok": ok, "sectionKey": section_key}
