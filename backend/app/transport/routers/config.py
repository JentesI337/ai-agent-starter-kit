"""RPC routers for config.* and execution.config.* control endpoints."""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Body

from app.config_service import get_config_service

JsonDict = dict


# ---------------------------------------------------------------------------
# Async/sync compatibility
# ---------------------------------------------------------------------------

def _maybe_await(result):
    if inspect.isawaitable(result):
        return result
    return None


# ---------------------------------------------------------------------------
# Handler dependencies — config.*
# ---------------------------------------------------------------------------

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
        for field_name in fields:
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


# ---------------------------------------------------------------------------
# Handler dependencies — execution.config.* / execution.loop-detection.*
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Router builder — config.*
# ---------------------------------------------------------------------------

def build_control_config_router(
    *,
    config_sections_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    config_diff_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    config_reset_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    config_deps_check_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    config_deps_install_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/config.sections")
    async def control_config_sections(request: JsonDict = Body(...)):
        result = (config_sections_handler or handle_config_sections)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.get")
    async def control_config_get(request: JsonDict = Body(...)):
        result = (config_get_handler or handle_config_get)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.update")
    async def control_config_update(request: JsonDict = Body(...)):
        result = (config_update_handler or handle_config_update)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.diff")
    async def control_config_diff(request: JsonDict = Body(...)):
        result = (config_diff_handler or handle_config_diff)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/config.reset")
    async def control_config_reset(request: JsonDict = Body(...)):
        result = (config_reset_handler or handle_config_reset)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    if config_deps_check_handler is not None:
        @router.post("/api/control/config.deps.check")
        async def control_config_deps_check(request: JsonDict = Body(...)):
            result = config_deps_check_handler(request)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    if config_deps_install_handler is not None:
        @router.post("/api/control/config.deps.install")
        async def control_config_deps_install(request: JsonDict = Body(...)):
            result = config_deps_install_handler(request)
            awaited = _maybe_await(result)
            return await awaited if awaited is not None else result

    return router


# ---------------------------------------------------------------------------
# Router builder — execution.config.* / execution.loop-detection.*
# ---------------------------------------------------------------------------

def build_control_execution_config_router(
    *,
    execution_config_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    execution_config_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    execution_loop_detection_get_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
    execution_loop_detection_update_handler: Callable[[JsonDict], JsonDict | Awaitable[JsonDict]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/control/execution.config.get")
    async def control_execution_config_get(request: JsonDict = Body(...)):
        result = (execution_config_get_handler or handle_execution_config_get)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/execution.config.update")
    async def control_execution_config_update(request: JsonDict = Body(...)):
        result = (execution_config_update_handler or handle_execution_config_update)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/execution.loop-detection.get")
    async def control_execution_loop_detection_get(request: JsonDict = Body(...)):
        result = (execution_loop_detection_get_handler or handle_execution_loop_detection_get)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    @router.post("/api/control/execution.loop-detection.update")
    async def control_execution_loop_detection_update(request: JsonDict = Body(...)):
        result = (execution_loop_detection_update_handler or handle_execution_loop_detection_update)(request)
        awaited = _maybe_await(result)
        return await awaited if awaited is not None else result

    return router
