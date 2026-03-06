from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.config import settings, validate_environment_config
from app.control_models import (
    ControlConfigHealthRequest,
    ControlContextDetailRequest,
    ControlContextListRequest,
    ControlMemoryOverviewRequest,
    ControlToolsCatalogRequest,
    ControlToolsPolicyMatrixRequest,
    ControlToolsPolicyPreviewRequest,
    ControlToolsProfileRequest,
)
from app.services import (
    PRESET_TOOL_POLICIES,
    TOOL_POLICY_BY_MODEL,
    TOOL_POLICY_BY_PROVIDER,
    TOOL_POLICY_RESOLUTION_ORDER,
    TOOL_PROFILES,
    normalize_policy_values,
    resolve_tool_policy,
)
from app.tool_policy import ToolPolicyDict, ToolPolicyPayload, tool_policy_to_dict


@dataclass
class ToolsHandlerDependencies:
    sync_custom_agents: Callable[[], None]
    normalize_agent_id: Callable[[str | None], str]
    resolve_agent: Callable[[str | None], tuple[str, Any, Any]]
    effective_orchestrator_agent_ids: Callable[[], set[str]]
    agent_registry: MutableMapping[str, Any]
    state_store: Any


_deps: ToolsHandlerDependencies | None = None


def configure(deps: ToolsHandlerDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> ToolsHandlerDependencies:
    if _deps is None:
        raise RuntimeError("tools_handlers is not configured")
    return _deps


def get_agent_tools(agent_contract) -> list[str]:
    delegate = getattr(agent_contract, "_delegate", None)
    if delegate is None:
        delegate = getattr(agent_contract, "_base_agent", None)
    if delegate is not None:
        nested_delegate = getattr(delegate, "_delegate", None)
        if nested_delegate is not None:
            delegate = nested_delegate
    registry = getattr(delegate, "tool_registry", None)
    if isinstance(registry, dict):
        return sorted(str(name) for name in registry)
    if registry is not None:
        keys = getattr(registry, "keys", None)
        if callable(keys):
            try:
                return sorted(str(name) for name in keys())
            except Exception:
                return []
        try:
            return sorted(str(name) for name in registry)
        except Exception:
            return []
    return []


def extract_also_allow(tool_policy: ToolPolicyDict | None) -> list[str] | None:
    if not isinstance(tool_policy, dict):
        return None
    raw = tool_policy.get("also_allow")
    if not isinstance(raw, list):
        return None
    values = [str(item).strip() for item in raw if isinstance(item, str) and str(item).strip()]
    return values or None


def normalize_tool_policy_payload(value: ToolPolicyPayload | ToolPolicyDict | None) -> ToolPolicyDict | None:
    return tool_policy_to_dict(value, include_also_allow=True)


def _build_tools_catalog(*, agent_id: str | None = None) -> dict:
    deps = _require_deps()
    deps.sync_custom_agents()

    agents: list[dict] = []
    selected_ids: set[str] | None = None
    if agent_id:
        normalized = deps.normalize_agent_id(agent_id)
        if normalized not in deps.agent_registry:
            raise HTTPException(status_code=400, detail=f"Unsupported agent: {agent_id}")
        selected_ids = {normalized}

    for item_agent_id, item_agent in sorted(deps.agent_registry.items(), key=lambda pair: pair[0]):
        if selected_ids is not None and item_agent_id not in selected_ids:
            continue
        agents.append(
            {
                "id": item_agent_id,
                "role": getattr(item_agent, "role", "agent"),
                "tools": get_agent_tools(item_agent),
            }
        )

    all_tools: set[str] = set()
    for item in agents:
        all_tools |= set(item.get("tools") or [])

    return {
        "schema": "tools.catalog.v1",
        "count": len(agents),
        "agents": agents,
        "presets": [
            {
                "id": preset_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
            for preset_id, policy in sorted(PRESET_TOOL_POLICIES.items(), key=lambda pair: pair[0])
        ],
        "globalPolicy": {
            "allow": list(settings.agent_tools_allow or []),
            "deny": list(settings.agent_tools_deny or []),
        },
        "tools": sorted(all_tools),
    }


def _build_tools_profiles(*, profile_id: str | None = None) -> dict:
    normalized_profile = (profile_id or "").strip().lower() or None
    if normalized_profile and normalized_profile not in TOOL_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unsupported profile: {profile_id}")

    profiles = []
    for item_id, policy in sorted(TOOL_PROFILES.items(), key=lambda pair: pair[0]):
        if normalized_profile and item_id != normalized_profile:
            continue
        profiles.append(
            {
                "id": item_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
        )

    return {
        "schema": "tools.profile.v1",
        "count": len(profiles),
        "profiles": profiles,
        "selected": normalized_profile,
    }


def _build_tools_policy_matrix(*, agent_id: str | None = None) -> dict:
    deps = _require_deps()
    normalized_agent_id = None
    selected_tools: list[str] = []
    if agent_id is not None:
        try:
            normalized_agent_id, selected_agent, _ = deps.resolve_agent(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        selected_tools = get_agent_tools(selected_agent)

    return {
        "schema": "tools.policy.matrix.v1",
        "agent_id": normalized_agent_id,
        "base_tools": selected_tools,
        "resolution_order": list(TOOL_POLICY_RESOLUTION_ORDER),
        "global": {
            "allow": list(settings.agent_tools_allow or []),
            "deny": list(settings.agent_tools_deny or []),
        },
        "profiles": [
            {
                "id": item_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
            for item_id, policy in sorted(TOOL_PROFILES.items(), key=lambda pair: pair[0])
        ],
        "presets": [
            {
                "id": item_id,
                "toolPolicy": {
                    "allow": list(policy.get("allow") or []),
                    "deny": list(policy.get("deny") or []),
                },
            }
            for item_id, policy in sorted(PRESET_TOOL_POLICIES.items(), key=lambda pair: pair[0])
        ],
        "by_provider": {
            item_id: {
                "allow": list(policy.get("allow") or []),
                "deny": list(policy.get("deny") or []),
            }
            for item_id, policy in sorted(TOOL_POLICY_BY_PROVIDER.items(), key=lambda pair: pair[0])
        },
        "by_model": {
            item_id: {
                "allow": list(policy.get("allow") or []),
                "deny": list(policy.get("deny") or []),
            }
            for item_id, policy in sorted(TOOL_POLICY_BY_MODEL.items(), key=lambda pair: pair[0])
        },
    }


def _build_tools_policy_preview(
    *,
    agent_id: str | None,
    profile: str | None,
    preset: str | None,
    provider: str | None,
    model: str | None,
    tool_policy: ToolPolicyDict | None,
    also_allow: list[str] | None,
) -> dict:
    deps = _require_deps()
    try:
        resolved_agent_id, selected_agent, _ = deps.resolve_agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    base_tools = set(get_agent_tools(selected_agent))

    resolved = resolve_tool_policy(
        profile=profile,
        preset=preset,
        provider=provider,
        model=model,
        request_policy=tool_policy,
        also_allow=also_allow,
        agent_id=resolved_agent_id,
        depth=0,
        orchestrator_agent_ids=sorted(deps.effective_orchestrator_agent_ids()),
    )

    merged_policy = resolved["merged_policy"]
    applied_preset = resolved["applied_preset"]
    normalized_profile = resolved["profile"]
    normalized_provider = resolved["provider"]
    normalized_model = resolved["model"]

    merged_policy = selected_agent.normalize_tool_policy(merged_policy)

    effective = set(base_tools)
    if not bool(getattr(settings, "vision_enabled", False)):
        effective.discard("analyze_image")

    config_allow = normalize_policy_values(settings.agent_tools_allow, base_tools)
    if config_allow is not None:
        effective &= config_allow

    requested_allow = normalize_policy_values((merged_policy or {}).get("allow"), base_tools)
    if requested_allow is not None:
        effective &= requested_allow

    deny = set()
    deny |= normalize_policy_values(settings.agent_tools_deny, base_tools) or set()
    deny |= normalize_policy_values((merged_policy or {}).get("deny"), base_tools) or set()
    effective -= deny

    also_allow_set = normalize_policy_values(also_allow, base_tools) or set()
    effective |= (also_allow_set - deny)

    return {
        "schema": "tools.policy.preview.v1",
        "agent_id": resolved_agent_id,
        "profile": normalized_profile,
        "preset": applied_preset,
        "provider": normalized_provider,
        "model": normalized_model,
        "base_tools": sorted(base_tools),
        "effective_allow": sorted(effective),
        "effective_deny": sorted(deny),
        "also_allow": sorted(also_allow_set),
        "scoped": resolved["scoped"],
        "requested": merged_policy or {},
        "explain": resolved["explain"],
        "global": {
            "allow": list(settings.agent_tools_allow or []),
            "deny": list(settings.agent_tools_deny or []),
        },
    }


def api_control_tools_catalog(request_data: dict) -> dict:
    request = ControlToolsCatalogRequest.model_validate(request_data)
    return _build_tools_catalog(agent_id=request.agent_id)


def api_control_tools_profile(request_data: dict) -> dict:
    request = ControlToolsProfileRequest.model_validate(request_data)
    return _build_tools_profiles(profile_id=request.profile_id)


def api_control_tools_policy_matrix(request_data: dict) -> dict:
    request = ControlToolsPolicyMatrixRequest.model_validate(request_data)
    return _build_tools_policy_matrix(agent_id=request.agent_id)


def api_control_tools_policy_preview(request_data: dict) -> dict:
    request = ControlToolsPolicyPreviewRequest.model_validate(request_data)
    normalized_tool_policy = normalize_tool_policy_payload(request.tool_policy)
    return _build_tools_policy_preview(
        agent_id=request.agent_id,
        profile=request.profile,
        preset=request.preset,
        provider=request.provider,
        model=request.model,
        tool_policy=normalized_tool_policy,
        also_allow=request.also_allow,
    )


def _estimate_tokens_from_chars(chars: int) -> int:
    if chars <= 0:
        return 0
    return max(1, round(chars / 4.0))


def _build_context_segments_payload(run_state: dict) -> dict:
    events = run_state.get("events") or []
    context_segmented_events = [
        evt
        for evt in events
        if isinstance(evt, dict)
        and str(evt.get("type") or "") == "lifecycle"
        and str(evt.get("stage") or "") == "context_segmented"
        and isinstance(evt.get("details"), dict)
    ]

    phase_breakdown: dict[str, dict[str, float | int]] = {}
    for event in context_segmented_events:
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        phase = str(details.get("phase") or "").strip().lower()
        if not phase:
            continue
        used_tokens = int(details.get("used_tokens") or 0)
        segments = details.get("segments") if isinstance(details.get("segments"), dict) else {}
        rendered_prompt = segments.get("rendered_prompt") if isinstance(segments.get("rendered_prompt"), dict) else {}
        chars = int(rendered_prompt.get("chars") or 0)

        current = phase_breakdown.get(phase)
        if current is None:
            phase_breakdown[phase] = {
                "tokens_est": used_tokens,
                "chars": chars,
            }
        else:
            current["tokens_est"] = int(current.get("tokens_est") or 0) + used_tokens
            current["chars"] = int(current.get("chars") or 0) + chars

    if context_segmented_events:
        preferred = context_segmented_events[-1]
        details = preferred.get("details") if isinstance(preferred.get("details"), dict) else {}
        raw_segments = details.get("segments") if isinstance(details.get("segments"), dict) else {}
        result: dict[str, dict] = {}
        for name, value in raw_segments.items():
            if not isinstance(name, str) or not isinstance(value, dict):
                continue
            tokens_est = int(value.get("tokens_est") or 0)
            chars = int(value.get("chars") or 0)
            share_pct = float(value.get("share_pct") or 0.0)
            result[name] = {
                "tokens_est": tokens_est,
                "chars": chars,
                "share_pct": round(share_pct, 2),
            }
        if result:
            return {
                "segments": result,
                "segment_source": "event",
                "degraded_estimation": False,
                "phase_breakdown": phase_breakdown,
            }

    input_payload = run_state.get("input") or {}
    user_message = str(input_payload.get("user_message") or "")

    memory_chars = 0
    plan_chars = 0
    tool_chars = 0
    response_chars = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        stage = str(event.get("stage") or "")
        details = event.get("details") if isinstance(event.get("details"), dict) else {}
        if stage == "memory_updated":
            memory_chars += int(details.get("memory_chars") or 0)
        if stage in {"planning_completed", "replanning_completed"}:
            plan_chars += int(details.get("plan_chars") or 0)
        if stage == "tool_completed":
            tool_chars += int(details.get("result_chars") or 0)
        if stage == "run_completed":
            response_chars += int(details.get("response_chars") or 0)

    final_events = [evt for evt in events if isinstance(evt, dict) and evt.get("type") == "final"]
    if final_events:
        final_text = str(final_events[-1].get("message") or "")
        if response_chars <= 0:
            response_chars = len(final_text)

    segments = {
        "system_prompt": {"chars": 0, "tokens_est": 0},
        "policy": {"chars": 0, "tokens_est": 0},
        "user_payload": {"chars": len(user_message), "tokens_est": _estimate_tokens_from_chars(len(user_message))},
        "memory": {"chars": memory_chars, "tokens_est": _estimate_tokens_from_chars(memory_chars)},
        "planning": {"chars": plan_chars, "tokens_est": _estimate_tokens_from_chars(plan_chars)},
        "tool_results": {"chars": tool_chars, "tokens_est": _estimate_tokens_from_chars(tool_chars)},
        "response": {"chars": response_chars, "tokens_est": _estimate_tokens_from_chars(response_chars)},
    }
    total_tokens = sum(item["tokens_est"] for item in segments.values())
    total_tokens = max(1, total_tokens)
    for item in segments.values():
        item["share_pct"] = round((item["tokens_est"] / total_tokens) * 100.0, 2)
    return {
        "segments": segments,
        "segment_source": "fallback",
        "degraded_estimation": True,
        "phase_breakdown": phase_breakdown,
    }


def api_control_context_list(request_data: dict) -> dict:
    deps = _require_deps()
    request = ControlContextListRequest.model_validate(request_data)
    runs = deps.state_store.list_runs(limit=max(1, int(request.limit)))
    if request.session_id:
        target = request.session_id.strip()
        runs = [item for item in runs if isinstance(item, dict) and str(item.get("session_id") or "") == target]

    items: list[dict] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        context_payload = _build_context_segments_payload(run)
        segments = context_payload["segments"]
        total_tokens_est = sum(item["tokens_est"] for item in segments.values())
        top_overhead = sorted(
            (
                {"segment": name, "tokens_est": value["tokens_est"], "share_pct": value["share_pct"]}
                for name, value in segments.items()
                if name != "user_payload"
            ),
            key=lambda item: item["tokens_est"],
            reverse=True,
        )[:3]
        items.append(
            {
                "run_id": run.get("run_id"),
                "session_id": run.get("session_id"),
                "status": run.get("status"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
                "total_tokens_est": total_tokens_est,
                "segment_source": context_payload["segment_source"],
                "degraded_estimation": context_payload["degraded_estimation"],
                "phase_breakdown": context_payload["phase_breakdown"],
                "top_overhead": top_overhead,
            }
        )

    return {
        "schema": "context.list.v1",
        "count": len(items),
        "items": items,
    }


def api_control_context_detail(request_data: dict) -> dict:
    deps = _require_deps()
    request = ControlContextDetailRequest.model_validate(request_data)
    run_state = deps.state_store.get_run(request.run_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {request.run_id}")

    context_payload = _build_context_segments_payload(run_state)
    segments = context_payload["segments"]
    return {
        "schema": "context.detail.v1",
        "run_id": run_state.get("run_id"),
        "session_id": run_state.get("session_id"),
        "status": run_state.get("status"),
        "segments": segments,
        "segment_source": context_payload["segment_source"],
        "degraded_estimation": context_payload["degraded_estimation"],
        "phase_breakdown": context_payload["phase_breakdown"],
        "total_tokens_est": sum(item["tokens_est"] for item in segments.values()),
    }


_CONFIG_REDACTED_FIELDS = frozenset({
    "api_auth_token", "llm_api_key", "state_encryption_key",
    "session_signing_key", "policy_hmac_key", "web_search_api_key",
    "vision_api_key",
})


def api_control_config_health(request_data: dict) -> dict:
    request = ControlConfigHealthRequest.model_validate(request_data)
    config_dump = settings.model_dump()
    validation = validate_environment_config(settings)

    active_overrides: dict[str, str] = {}
    for key in config_dump:
        env_key = str(key).upper()
        if env_key in os.environ:
            active_overrides[key] = env_key

    isolation_pairs = list(getattr(settings, "agent_isolation_allowed_scope_pairs", []) or [])
    wildcard_pair_present = any("*" in str(item) for item in isolation_pairs)
    excessive_pair_count = len(isolation_pairs) > 20

    risk_flags = {
        "run_state_violation_hard_fail_enabled": bool(getattr(settings, "run_state_violation_hard_fail_enabled", False)),
        "skills_engine_enabled": bool(getattr(settings, "skills_engine_enabled", False)),
        "queue_mode_default": str(getattr(settings, "queue_mode_default", "wait")),
        "isolation_allowlist_wildcard": wildcard_pair_present,
        "isolation_allowlist_excessive": excessive_pair_count,
        "isolation_allowlist_pair_count": len(isolation_pairs),
    }

    payload = {
        "schema": "config.health.v1",
        "schema_version": "config.v1",
        "active_overrides": active_overrides,
        "invalid_or_unknown": list(validation.get("unknown_keys") or []),
        "validation_status": str(validation.get("validation_status") or "ok"),
        "strict_unknown_keys_enabled": bool(validation.get("strict_mode", False)),
        "unknown_key_count": len(list(validation.get("unknown_keys") or [])),
        "risk_flags": risk_flags,
    }
    if request.include_effective_values:
        # SEC (CFG-01): Redact sensitive fields to prevent secret leakage
        for key in _CONFIG_REDACTED_FIELDS:
            if config_dump.get(key):
                config_dump[key] = "[REDACTED]"
        payload["effective_values"] = config_dump
    return payload


def _resolve_path(value: str, *, workspace_root: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (Path(workspace_root) / candidate).resolve()
    return candidate


def _sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _read_long_term_memory_sections(*, db_path: Path, include_content: bool, limit: int, search_query: str | None) -> dict[str, Any]:
    section_payload: dict[str, Any] = {
        "available": False,
        "tables": {
            "episodic": False,
            "semantic": False,
            "failure_journal": False,
        },
        "counts": {
            "episodic": 0,
            "semantic": 0,
            "failure_journal": 0,
        },
        "episodic": [],
        "semantic": [],
        "failure_journal": [],
        "read_errors": [],
    }

    if not db_path.exists() or not db_path.is_file():
        return section_payload

    section_payload["available"] = True

    try:
        connection = sqlite3.connect(str(db_path))
    except Exception as exc:
        section_payload["read_errors"].append(f"db_open_failed: {exc}")
        return section_payload

    normalized_query = (search_query or "").strip().lower()
    has_query = bool(normalized_query)

    try:
        with connection:
            has_episodic = _sqlite_table_exists(connection, "episodic")
            has_semantic = _sqlite_table_exists(connection, "semantic")
            has_failure = _sqlite_table_exists(connection, "failure_journal")

            section_payload["tables"]["episodic"] = has_episodic
            section_payload["tables"]["semantic"] = has_semantic
            section_payload["tables"]["failure_journal"] = has_failure

            if has_episodic:
                count_row = connection.execute("SELECT COUNT(*) FROM episodic").fetchone()
                section_payload["counts"]["episodic"] = int((count_row or [0])[0] or 0)
                if has_query:
                    like = f"%{normalized_query}%"
                    rows = connection.execute(
                        """
                        SELECT session_id, timestamp, summary, key_actions, outcome, tags
                        FROM episodic
                        WHERE lower(session_id) LIKE ?
                           OR lower(summary) LIKE ?
                           OR lower(key_actions) LIKE ?
                           OR lower(tags) LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (like, like, like, like, max(1, int(limit))),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT session_id, timestamp, summary, key_actions, outcome, tags
                        FROM episodic
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (max(1, int(limit)),),
                    ).fetchall()
                episodic_items: list[dict[str, Any]] = []
                for row in rows:
                    key_actions_raw = str(row[3] or "")
                    tags_raw = str(row[5] or "")
                    item: dict[str, Any] = {
                        "session_id": str(row[0] or ""),
                        "timestamp": str(row[1] or ""),
                        "outcome": str(row[4] or ""),
                        "key_actions": key_actions_raw,
                        "tags": tags_raw,
                    }
                    if include_content:
                        item["summary"] = str(row[2] or "")
                    episodic_items.append(item)
                section_payload["episodic"] = episodic_items

            if has_semantic:
                count_row = connection.execute("SELECT COUNT(*) FROM semantic").fetchone()
                section_payload["counts"]["semantic"] = int((count_row or [0])[0] or 0)
                if has_query:
                    like = f"%{normalized_query}%"
                    rows = connection.execute(
                        """
                        SELECT key, value, confidence, source_sessions, last_updated
                        FROM semantic
                        WHERE lower(key) LIKE ?
                           OR lower(value) LIKE ?
                           OR lower(source_sessions) LIKE ?
                        ORDER BY last_updated DESC
                        LIMIT ?
                        """,
                        (like, like, like, max(1, int(limit))),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT key, value, confidence, source_sessions, last_updated
                        FROM semantic
                        ORDER BY last_updated DESC
                        LIMIT ?
                        """,
                        (max(1, int(limit)),),
                    ).fetchall()
                semantic_items: list[dict[str, Any]] = []
                for row in rows:
                    item: dict[str, Any] = {
                        "key": str(row[0] or ""),
                        "confidence": float(row[2] or 0.0),
                        "source_sessions": str(row[3] or ""),
                        "last_updated": str(row[4] or ""),
                    }
                    if include_content:
                        item["value"] = str(row[1] or "")
                    semantic_items.append(item)
                section_payload["semantic"] = semantic_items

            if has_failure:
                count_row = connection.execute("SELECT COUNT(*) FROM failure_journal").fetchone()
                section_payload["counts"]["failure_journal"] = int((count_row or [0])[0] or 0)
                if has_query:
                    like = f"%{normalized_query}%"
                    rows = connection.execute(
                        """
                        SELECT id, timestamp, task_description, error_type, root_cause, solution, prevention, tags
                        FROM failure_journal
                        WHERE lower(id) LIKE ?
                           OR lower(task_description) LIKE ?
                           OR lower(error_type) LIKE ?
                           OR lower(root_cause) LIKE ?
                           OR lower(solution) LIKE ?
                           OR lower(prevention) LIKE ?
                           OR lower(tags) LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (like, like, like, like, like, like, like, max(1, int(limit))),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT id, timestamp, task_description, error_type, root_cause, solution, prevention, tags
                        FROM failure_journal
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (max(1, int(limit)),),
                    ).fetchall()
                failure_items: list[dict[str, Any]] = []
                for row in rows:
                    item: dict[str, Any] = {
                        "id": str(row[0] or ""),
                        "timestamp": str(row[1] or ""),
                        "error_type": str(row[3] or ""),
                        "tags": str(row[7] or ""),
                    }
                    if include_content:
                        item["task_description"] = str(row[2] or "")
                        item["root_cause"] = str(row[4] or "")
                        item["solution"] = str(row[5] or "")
                        item["prevention"] = str(row[6] or "")
                    failure_items.append(item)
                section_payload["failure_journal"] = failure_items

    except Exception as exc:
        section_payload["read_errors"].append(f"db_read_failed: {exc}")
    finally:
        connection.close()

    return section_payload


def api_control_memory_overview(request_data: dict) -> dict:
    request = ControlMemoryOverviewRequest.model_validate(request_data)

    memory_dir = _resolve_path(settings.memory_persist_dir, workspace_root=settings.workspace_root)
    long_term_db_path = _resolve_path(settings.long_term_memory_db_path, workspace_root=settings.workspace_root)

    requested_session = (request.session_id or "").strip()
    search_query = (request.search_query or "").strip()
    normalized_query = search_query.lower()
    has_query = bool(normalized_query)
    selected_session = requested_session or None
    session_limit = max(1, int(request.limit_sessions))
    entry_limit = max(1, int(request.limit_entries_per_session))

    session_items: list[dict[str, Any]] = []
    total_entries = 0
    total_chars = 0

    if memory_dir.exists() and memory_dir.is_dir():
        files = sorted(memory_dir.glob("*.jsonl"), key=lambda path: path.name)
        if selected_session:
            files = [path for path in files if path.stem == selected_session]
        if has_query:
            files = [path for path in files if normalized_query in path.stem.lower()]

        for file_path in files[:session_limit]:
            entries: list[dict[str, Any]] = []
            parse_errors = 0
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []
                parse_errors += 1

            for index, line in enumerate(lines[-entry_limit:], start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue

                role = str(payload.get("role") or "").strip()
                content = str(payload.get("content") or "")
                if not role:
                    parse_errors += 1
                    continue

                if has_query:
                    hay = f"{role} {content}".lower()
                    if normalized_query not in hay and normalized_query not in file_path.stem.lower():
                        continue

                total_entries += 1
                total_chars += len(content)

                entry: dict[str, Any] = {
                    "index": index,
                    "role": role,
                    "chars": len(content),
                }
                if request.include_content:
                    entry["content"] = content
                entries.append(entry)

            session_items.append(
                {
                    "session_id": file_path.stem,
                    "file": file_path.name,
                    "entry_count": len(entries),
                    "parse_errors": parse_errors,
                    "entries": entries,
                }
            )

        if has_query:
            session_items = [item for item in session_items if item.get("entries") or normalized_query in str(item.get("session_id") or "").lower()]

    db_exists = long_term_db_path.exists() and long_term_db_path.is_file()
    db_size_bytes = long_term_db_path.stat().st_size if db_exists else 0
    long_term_sections = _read_long_term_memory_sections(
        db_path=long_term_db_path,
        include_content=bool(request.include_content),
        limit=entry_limit,
        search_query=search_query,
    )

    return {
        "schema": "memory.overview.v1",
        "memory_store_dir": str(memory_dir),
        "selected_session_id": selected_session,
        "search_query": search_query or None,
        "session_count": len(session_items),
        "total_entries": total_entries,
        "total_content_chars": total_chars,
        "flags": {
            "long_term_memory_enabled": bool(getattr(settings, "long_term_memory_enabled", False)),
            "session_distillation_enabled": bool(getattr(settings, "session_distillation_enabled", False)),
            "failure_journal_enabled": bool(getattr(settings, "failure_journal_enabled", False)),
            "vision_enabled": bool(getattr(settings, "vision_enabled", False)),
        },
        "long_term_db": {
            "path": str(long_term_db_path),
            "exists": db_exists,
            "size_bytes": db_size_bytes,
        },
        "long_term_memory": long_term_sections,
        "sessions": session_items,
    }
