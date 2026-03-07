from __future__ import annotations

from fastapi import HTTPException

from app.config import settings
from app.errors import GuardrailViolation
from app.tool_catalog import TOOL_NAME_SET
from app.tool_policy import ToolPolicyDict

PRESET_TOOL_POLICIES: dict[str, ToolPolicyDict] = {
    "research": {
        "allow": [
            "web_search",
            "web_fetch",
            "read_file",
            "file_search",
            "grep_search",
            "list_code_usages",
            "list_dir",
            "get_changed_files",
        ],
        "deny": [
            "write_file",
            "apply_patch",
            "run_command",
            "http_request",
            "start_background_command",
            "kill_background_process",
            "spawn_subrun",
        ],
    },
    "review": {
        "allow": [
            "read_file",
            "file_search",
            "grep_search",
            "list_code_usages",
            "list_dir",
            "get_changed_files",
            "web_search",
            "web_fetch",
        ],
        "deny": [
            "write_file",
            "apply_patch",
            "run_command",
            "http_request",
            "start_background_command",
            "kill_background_process",
            "spawn_subrun",
        ],
    },
}

TOOL_PROFILES: dict[str, ToolPolicyDict] = {
    "minimal": {
        "allow": [
            "list_dir",
            "read_file",
            "file_search",
            "grep_search",
            "list_code_usages",
            "get_changed_files",
            "web_search",
            "web_fetch",
        ],
        "deny": [
            "write_file",
            "apply_patch",
            "run_command",
            "start_background_command",
            "kill_background_process",
        ],
    },
    "coding": {
        "allow": [
            "list_dir",
            "read_file",
            "write_file",
            "apply_patch",
            "file_search",
            "grep_search",
            "list_code_usages",
            "get_changed_files",
            "run_command",
            "start_background_command",
            "get_background_output",
            "kill_background_process",
            "web_search",
            "web_fetch",
            "spawn_subrun",
        ],
        "deny": [],
    },
    "review": {
        "allow": [
            "list_dir",
            "read_file",
            "file_search",
            "grep_search",
            "list_code_usages",
            "get_changed_files",
            "web_search",
            "web_fetch",
        ],
        "deny": [
            "write_file",
            "apply_patch",
            "run_command",
            "http_request",
            "start_background_command",
            "kill_background_process",
            "spawn_subrun",
        ],
    },
}

TOOL_POLICY_BY_PROVIDER: dict[str, ToolPolicyDict] = {
    "local": {
        "deny": [],
    },
    "api": {
        "deny": [
            "start_background_command",
            "kill_background_process",
        ],
    },
}

TOOL_POLICY_BY_MODEL: dict[str, ToolPolicyDict] = {
    # Deny-only: tools not listed here are allowed by default.
    # Add model-specific deny entries only when a model cannot
    # handle certain tools reliably.
    "minimax-m2:cloud": {
        "deny": [
            "start_background_command",
            "kill_background_process",
        ],
    },
}

TOOL_POLICY_RESOLUTION_ORDER = [
    "global",
    "profile",
    "preset",
    "provider",
    "model",
    "agent_override",
    "agent_depth",
    "request",
]


def _normalize_preset(value: str | None) -> str | None:
    preset = (value or "").strip().lower()
    return preset or None


def merge_tool_policy(
    base: ToolPolicyDict | None,
    incoming: ToolPolicyDict | None,
) -> ToolPolicyDict | None:
    allow_values: list[str] = []
    deny_values: list[str] = []

    for source in (base or {}, incoming or {}):
        for item in source.get("allow") or []:
            if isinstance(item, str):
                value = item.strip()
                if value and value not in allow_values:
                    allow_values.append(value)
        for item in source.get("deny") or []:
            if isinstance(item, str):
                value = item.strip()
                if value and value not in deny_values:
                    deny_values.append(value)

    if not allow_values and not deny_values:
        return None

    payload: ToolPolicyDict = {}
    if allow_values:
        payload["allow"] = allow_values
    if deny_values:
        payload["deny"] = deny_values
    return payload


def policy_payload(policy: ToolPolicyDict | None) -> ToolPolicyDict:
    if not policy:
        return {}
    payload: ToolPolicyDict = {}
    allow_values = [item for item in (policy.get("allow") or []) if isinstance(item, str) and item.strip()]
    deny_values = [item for item in (policy.get("deny") or []) if isinstance(item, str) and item.strip()]
    if allow_values:
        payload["allow"] = list(allow_values)
    if deny_values:
        payload["deny"] = list(deny_values)
    return payload


def _normalized_policy_from_mapping(value: object) -> ToolPolicyDict | None:
    if not isinstance(value, dict):
        return None
    payload: ToolPolicyDict = {}
    for key in ("allow", "deny", "also_allow"):
        items = value.get(key)
        if not isinstance(items, list):
            continue
        normalized = [item for item in items if isinstance(item, str) and item.strip()]
        if normalized:
            payload[key] = normalized
    return payload or None


def _resolve_agent_override_policy(
    *,
    request_policy: ToolPolicyDict | None,
    normalized_agent_id: str | None,
) -> ToolPolicyDict | None:
    if not isinstance(request_policy, dict):
        return None
    raw_agents = request_policy.get("agents")
    if not isinstance(raw_agents, dict):
        return None

    selected: object | None = None
    if normalized_agent_id and normalized_agent_id in raw_agents:
        selected = raw_agents.get(normalized_agent_id)
    elif "*" in raw_agents:
        selected = raw_agents.get("*")

    return _normalized_policy_from_mapping(selected)


def _apply_agent_override_precedence(
    *,
    merged_policy: ToolPolicyDict | None,
    agent_override_policy: ToolPolicyDict | None,
) -> ToolPolicyDict | None:
    if not agent_override_policy:
        return merged_policy

    base_allow = [item for item in (merged_policy or {}).get("allow") or [] if isinstance(item, str) and item.strip()]
    base_deny = [item for item in (merged_policy or {}).get("deny") or [] if isinstance(item, str) and item.strip()]
    override_allow = [
        item for item in (agent_override_policy.get("allow") or []) if isinstance(item, str) and item.strip()
    ]
    override_deny = [
        item for item in (agent_override_policy.get("deny") or []) if isinstance(item, str) and item.strip()
    ]
    override_also_allow = [
        item
        for item in (agent_override_policy.get("also_allow") or [])
        if isinstance(item, str) and item.strip()
    ]

    if not (override_allow or override_deny or override_also_allow):
        return merged_policy

    overridden_tools = {*(item.strip().lower() for item in override_allow), *(item.strip().lower() for item in override_deny)}

    allow_values = [item for item in base_allow if item.strip().lower() not in overridden_tools]
    deny_values = [item for item in base_deny if item.strip().lower() not in overridden_tools]

    for item in override_allow:
        if item not in allow_values:
            allow_values.append(item)
    for item in override_deny:
        if item not in deny_values:
            deny_values.append(item)

    payload: ToolPolicyDict = {}
    if allow_values:
        payload["allow"] = allow_values
    if deny_values:
        payload["deny"] = deny_values
    if override_also_allow:
        payload["also_allow"] = sorted(set(override_also_allow))
    return payload or None


def resolve_tool_policy(
    *,
    profile: str | None = None,
    preset: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    request_policy: ToolPolicyDict | None = None,
    also_allow: list[str] | None = None,
    agent_id: str | None = None,
    depth: int | None = None,
    orchestrator_agent_ids: list[str] | None = None,
) -> dict:
    normalized_profile = (profile or "").strip().lower() or None
    profile_policy = None
    if normalized_profile is not None:
        profile_policy = TOOL_PROFILES.get(normalized_profile)
        if profile_policy is None:
            raise HTTPException(status_code=400, detail=f"Unsupported profile: {profile}")

    normalized_preset = _normalize_preset(preset)
    preset_policy = None
    if normalized_preset is not None:
        preset_policy = PRESET_TOOL_POLICIES.get(normalized_preset)
        if preset_policy is None:
            raise GuardrailViolation(f"Unsupported preset: {preset}")

    normalized_provider = (provider or "").strip().lower() or None
    provider_policy = None
    if normalized_provider is not None:
        provider_policy = TOOL_POLICY_BY_PROVIDER.get(normalized_provider)
        if provider_policy is None:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    normalized_model = (model or "").strip() or None
    model_policy = TOOL_POLICY_BY_MODEL.get(normalized_model) if normalized_model is not None else None

    normalized_agent_id = (agent_id or "").strip().lower() or None
    normalized_depth = int(depth) if depth is not None else None
    effective_orchestrator_agent_ids = {
        str(item).strip().lower()
        for item in (orchestrator_agent_ids or settings.subrun_orchestrator_agent_ids or ["head-agent"])
        if isinstance(item, str) and str(item).strip()
    }
    agent_depth_deny: set[str] = set()
    if normalized_depth is not None and normalized_depth >= 2:
        agent_depth_deny.add("spawn_subrun")
    if normalized_depth is not None and normalized_agent_id and normalized_agent_id not in effective_orchestrator_agent_ids:
        agent_depth_deny.add("spawn_subrun")

    agent_depth_policy = None
    if agent_depth_deny:
        agent_depth_policy = {"deny": sorted(agent_depth_deny)}

    known_tool_names = {item.strip().lower() for item in TOOL_NAME_SET}
    agent_override_policy = _resolve_agent_override_policy(
        request_policy=request_policy,
        normalized_agent_id=normalized_agent_id,
    )

    merge_chain: list[tuple[str, str | None, ToolPolicyDict | None]] = [
        (
            "global",
            "settings",
            {
                "allow": list(settings.agent_tools_allow or []),
                "deny": list(settings.agent_tools_deny or []),
            },
        ),
        ("profile", normalized_profile, profile_policy),
        ("preset", normalized_preset, preset_policy),
        ("provider", normalized_provider, provider_policy),
        ("model", normalized_model, model_policy),
        (
            "agent_depth",
            f"{normalized_agent_id}:{normalized_depth}",
            agent_depth_policy,
        ),
        ("request", "inline", request_policy),
    ]

    merged_policy = None
    for _, _, layer_policy in merge_chain:
        merged_policy = merge_tool_policy(merged_policy, layer_policy)
    merged_policy = _apply_agent_override_precedence(
        merged_policy=merged_policy,
        agent_override_policy=agent_override_policy,
    )

    layers: list[dict] = []
    for layer_name, layer_id, layer_policy in merge_chain:
        layers.append(
            {
                "layer": layer_name,
                "id": layer_id,
                "toolPolicy": policy_payload(layer_policy),
            }
        )
    layers.append(
        {
            "layer": "agent_override",
            "id": normalized_agent_id,
            "toolPolicy": policy_payload(agent_override_policy),
        }
    )

    merged_payload = policy_payload(merged_policy)
    merged_allow_values = list(merged_payload.get("allow") or [])
    merged_deny_values = list(merged_payload.get("deny") or [])

    warnings: list[str] = []
    unknown_allowlist_by_layer: dict[str, list[str]] = {}
    for layer_name, _, layer_policy in merge_chain:
        layer_allow = [
            str(item).strip().lower()
            for item in (layer_policy or {}).get("allow") or []
            if isinstance(item, str) and str(item).strip()
        ]
        unknown = sorted({item for item in layer_allow if item not in known_tool_names and item != "*"})
        if unknown:
            unknown_allowlist_by_layer[layer_name] = unknown
            warnings.append(
                f"Unknown allow entries in layer '{layer_name}': {', '.join(unknown)}"
            )

    normalized_also_allow: list[str] = []
    unknown_also_allow: list[str] = []
    for raw in also_allow or []:
        if not isinstance(raw, str):
            continue
        candidate = raw.strip().lower()
        if not candidate:
            continue
        if candidate in known_tool_names and candidate not in normalized_also_allow:
            normalized_also_allow.append(candidate)
        elif candidate not in known_tool_names and candidate not in unknown_also_allow:
            unknown_also_allow.append(candidate)
    if unknown_also_allow:
        warnings.append(f"Unknown also_allow entries ignored: {', '.join(sorted(unknown_also_allow))}")

    normalized_deny = {
        item.strip().lower() for item in merged_deny_values if isinstance(item, str) and item.strip()
    }
    normalized_allow = {
        item.strip().lower() for item in merged_allow_values if isinstance(item, str) and item.strip()
    }
    conflicted_tools = sorted(normalized_allow & normalized_deny)
    if conflicted_tools:
        warnings.append(f"deny overrides allow for: {', '.join(conflicted_tools)}")

    effective_allow_after_conflicts = [
        item
        for item in merged_allow_values
        if isinstance(item, str) and item.strip() and item.strip().lower() not in normalized_deny
    ]
    effective_deny_after_conflicts = [
        item for item in merged_deny_values if isinstance(item, str) and item.strip()
    ]

    merged_policy_with_additive = dict(merged_policy or {})
    if normalized_also_allow:
        merged_policy_with_additive["also_allow"] = sorted(normalized_also_allow)

    return {
        "profile": normalized_profile,
        "applied_preset": normalized_preset,
        "provider": normalized_provider,
        "model": normalized_model,
        "merged_policy": merged_policy_with_additive or None,
        "explain": {
            "order": list(TOOL_POLICY_RESOLUTION_ORDER),
            "layers": layers,
            "final_allow": merged_allow_values,
            "final_deny": merged_deny_values,
            "warnings": warnings,
            "unknown_allowlist_by_layer": unknown_allowlist_by_layer,
            "also_allow": sorted(normalized_also_allow),
            "unknown_also_allow": sorted(unknown_also_allow),
            "conflict_resolution": {
                "strategy": "deny_overrides_allow",
                "conflicted_tools": conflicted_tools,
                "effective_allow_after_conflicts": effective_allow_after_conflicts,
                "effective_deny_after_conflicts": effective_deny_after_conflicts,
            },
        },
        "scoped": {
            "provider": policy_payload(provider_policy),
            "model": policy_payload(model_policy),
        },
    }


def resolve_tool_policy_with_preset(
    preset: str | None,
    incoming: ToolPolicyDict | None,
) -> tuple[ToolPolicyDict | None, str | None]:
    resolved = resolve_tool_policy(
        preset=preset,
        request_policy=incoming,
    )
    return resolved["merged_policy"], resolved["applied_preset"]


def normalize_policy_values(values: list[str] | None, allowed_universe: set[str]) -> set[str] | None:
    if values is None:
        return None
    normalized: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        candidate = item.strip().lower()
        if candidate and candidate in allowed_universe:
            normalized.add(candidate)
    return normalized
