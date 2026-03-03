from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.config import settings, validate_environment_config
from app.control_models import (
    ControlConfigHealthRequest,
    ControlContextDetailRequest,
    ControlContextListRequest,
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
        return sorted(str(name) for name in registry.keys())
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
    return max(1, int(round(chars / 4.0)))


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


def api_control_config_health(request_data: dict) -> dict:
    request = ControlConfigHealthRequest.model_validate(request_data)
    config_dump = settings.model_dump()
    validation = validate_environment_config(settings)

    active_overrides: dict[str, str] = {}
    for key in config_dump.keys():
        env_key = str(key).upper()
        if env_key in os.environ:
            active_overrides[key] = env_key

    risk_flags = {
        "run_state_violation_hard_fail_enabled": bool(getattr(settings, "run_state_violation_hard_fail_enabled", False)),
        "skills_engine_enabled": bool(getattr(settings, "skills_engine_enabled", False)),
        "queue_mode_default": str(getattr(settings, "queue_mode_default", "wait")),
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
        payload["effective_values"] = config_dump
    return payload
