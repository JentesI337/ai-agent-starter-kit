"""Handlers for tools.config.* and tools.security.* control endpoints."""
from __future__ import annotations

from typing import Any

from app.tool_modules.tool_config_store import get_tool_config_store
from app.tools.provisioning.command_security import (
    BUILTIN_COMMAND_SAFETY_PATTERNS,
    add_pattern,
    get_all_patterns,
    get_extended_patterns,
)


def handle_tools_config_list(request: dict[str, Any]) -> dict[str, Any]:
    store = get_tool_config_store()
    configs = store.get_all()
    return {
        "configs": {
            name: config.model_dump()
            for name, config in configs.items()
        },
    }


def handle_tools_config_get(request: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(request.get("toolName") or "").strip()
    if not tool_name:
        return {"error": "toolName is required"}
    store = get_tool_config_store()
    config = store.get(tool_name)
    return {"config": config.model_dump()}


def handle_tools_config_update(request: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(request.get("toolName") or "").strip()
    updates = request.get("updates")
    if not tool_name:
        return {"error": "toolName is required"}
    if not isinstance(updates, dict) or not updates:
        return {"error": "updates must be a non-empty object"}
    store = get_tool_config_store()
    try:
        config = store.update(tool_name, updates)
        return {"ok": True, "config": config.model_dump()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def handle_tools_config_reset(request: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(request.get("toolName") or "").strip()
    if not tool_name:
        return {"error": "toolName is required"}
    store = get_tool_config_store()
    config = store.reset(tool_name)
    return {"ok": True, "config": config.model_dump()}


def handle_tools_security_patterns(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "builtin": [{"pattern": p, "reason": r} for p, r in BUILTIN_COMMAND_SAFETY_PATTERNS],
        "extended": [{"pattern": p, "reason": r} for p, r in get_extended_patterns()],
        "total": len(get_all_patterns()),
    }


def handle_tools_security_update(request: dict[str, Any]) -> dict[str, Any]:
    pattern = str(request.get("pattern") or "").strip()
    reason = str(request.get("reason") or "").strip()
    if not pattern or not reason:
        return {"error": "pattern and reason are required"}
    ok = add_pattern(pattern, reason)
    if not ok:
        return {"ok": False, "error": "Invalid regex pattern"}
    return {"ok": True, "total": len(get_all_patterns())}
