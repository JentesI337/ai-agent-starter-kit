"""Handlers for execution.config.* control endpoints."""
from __future__ import annotations
from typing import Any

from app.config_service import get_config_service


def handle_execution_config_get(request: dict[str, Any]) -> dict[str, Any]:
    svc = get_config_service()
    tool_exec = svc.get_section("tool_execution")
    tool_loop = svc.get_section("tool_loop")
    return {
        "budget": {
            "call_cap": tool_exec.run_tool_call_cap,
            "time_cap_seconds": tool_exec.run_tool_time_cap_seconds,
        },
        "result_processing": {
            "max_chars": tool_exec.tool_result_max_chars,
            "smart_truncate_enabled": tool_exec.tool_result_smart_truncate_enabled,
            "context_guard_enabled": tool_exec.tool_result_context_guard_enabled,
            "context_headroom_ratio": tool_exec.tool_result_context_headroom_ratio,
            "single_share": tool_exec.tool_result_single_share,
        },
        "loop_detection": tool_loop.model_dump(),
        "parallel_read_only_enabled": tool_exec.tool_execution_parallel_read_only_enabled,
    }


def handle_execution_config_update(request: dict[str, Any]) -> dict[str, Any]:
    updates = request.get("updates")
    if not isinstance(updates, dict):
        return {"error": "updates must be an object"}
    svc = get_config_service()

    results = []
    for field, value in updates.items():
        # Route to the right section
        from app.config_sections import field_to_section
        section_key = field_to_section(field)
        if section_key:
            result = svc.update_value(section_key, field, value)
            results.append({"field": field, "ok": result.ok, "errors": result.validation_errors})
        else:
            results.append({"field": field, "ok": False, "errors": [f"Unknown field: {field}"]})

    return {"ok": all(r["ok"] for r in results), "results": results}


def handle_execution_loop_detection_get(request: dict[str, Any]) -> dict[str, Any]:
    svc = get_config_service()
    section = svc.get_section("tool_loop")
    return {"loop_detection": section.model_dump()}


def handle_execution_loop_detection_update(request: dict[str, Any]) -> dict[str, Any]:
    updates = request.get("updates")
    if not isinstance(updates, dict):
        return {"error": "updates must be an object"}
    svc = get_config_service()
    results = svc.update_section("tool_loop", updates)
    errors = []
    for r in results:
        if not r.ok:
            errors.extend(r.validation_errors)
    return {"ok": len(errors) == 0, "errors": errors}
