from __future__ import annotations

from fastapi import HTTPException

from app.config import settings
from app.errors import GuardrailViolation

PRESET_TOOL_POLICIES: dict[str, dict[str, list[str]]] = {
    "research": {
        "allow": [
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
            "start_background_command",
            "kill_background_process",
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
}

TOOL_PROFILES: dict[str, dict[str, list[str]]] = {
    "minimal": {
        "allow": [
            "list_dir",
            "read_file",
            "file_search",
            "grep_search",
            "list_code_usages",
            "get_changed_files",
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
            "web_fetch",
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
}

TOOL_POLICY_BY_PROVIDER: dict[str, dict[str, list[str]]] = {
    "local": {
        "allow": [
            "run_command",
            "start_background_command",
            "get_background_output",
            "kill_background_process",
        ],
        "deny": [],
    },
    "api": {
        "allow": [],
        "deny": [
            "start_background_command",
            "kill_background_process",
        ],
    },
}

TOOL_POLICY_BY_MODEL: dict[str, dict[str, list[str]]] = {
    "minimax-m2:cloud": {
        "allow": [],
        "deny": [
            "start_background_command",
            "kill_background_process",
        ],
    },
    "qwen3-coder:480b-cloud": {
        "allow": [
            "run_command",
            "start_background_command",
            "get_background_output",
            "kill_background_process",
        ],
        "deny": [],
    },
}

TOOL_POLICY_RESOLUTION_ORDER = [
    "global",
    "profile",
    "preset",
    "provider",
    "model",
    "agent_depth",
    "request",
]


def _normalize_preset(value: str | None) -> str | None:
    preset = (value or "").strip().lower()
    return preset or None


def merge_tool_policy(
    base: dict[str, list[str]] | None,
    incoming: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
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

    payload: dict[str, list[str]] = {}
    if allow_values:
        payload["allow"] = allow_values
    if deny_values:
        payload["deny"] = deny_values
    return payload


def policy_payload(policy: dict[str, list[str]] | None) -> dict[str, list[str]]:
    if not policy:
        return {}
    payload: dict[str, list[str]] = {}
    allow_values = [item for item in (policy.get("allow") or []) if isinstance(item, str) and item.strip()]
    deny_values = [item for item in (policy.get("deny") or []) if isinstance(item, str) and item.strip()]
    if allow_values:
        payload["allow"] = list(allow_values)
    if deny_values:
        payload["deny"] = list(deny_values)
    return payload


def resolve_tool_policy(
    *,
    profile: str | None = None,
    preset: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    request_policy: dict[str, list[str]] | None = None,
    agent_id: str | None = None,
    depth: int | None = None,
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

    agent_depth_policy = None

    merge_chain: list[tuple[str, str | None, dict[str, list[str]] | None]] = [
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
            f"{(agent_id or '').strip().lower() or None}:{depth if depth is not None else None}",
            agent_depth_policy,
        ),
        ("request", "inline", request_policy),
    ]

    merged_policy = None
    for layer_name, _, layer_policy in merge_chain:
        if layer_name == "global":
            continue
        merged_policy = merge_tool_policy(merged_policy, layer_policy)

    layers: list[dict] = []
    for layer_name, layer_id, layer_policy in merge_chain:
        layers.append(
            {
                "layer": layer_name,
                "id": layer_id,
                "toolPolicy": policy_payload(layer_policy),
            }
        )

    merged_payload = policy_payload(merged_policy)
    merged_allow_values = list(merged_payload.get("allow") or [])
    merged_deny_values = list(merged_payload.get("deny") or [])

    normalized_deny = {
        item.strip().lower() for item in merged_deny_values if isinstance(item, str) and item.strip()
    }
    normalized_allow = {
        item.strip().lower() for item in merged_allow_values if isinstance(item, str) and item.strip()
    }
    conflicted_tools = sorted(normalized_allow & normalized_deny)

    effective_allow_after_conflicts = [
        item
        for item in merged_allow_values
        if isinstance(item, str) and item.strip() and item.strip().lower() not in normalized_deny
    ]
    effective_deny_after_conflicts = [
        item for item in merged_deny_values if isinstance(item, str) and item.strip()
    ]

    return {
        "profile": normalized_profile,
        "applied_preset": normalized_preset,
        "provider": normalized_provider,
        "model": normalized_model,
        "merged_policy": merged_policy,
        "explain": {
            "order": list(TOOL_POLICY_RESOLUTION_ORDER),
            "layers": layers,
            "final_allow": merged_allow_values,
            "final_deny": merged_deny_values,
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
    incoming: dict[str, list[str]] | None,
) -> tuple[dict[str, list[str]] | None, str | None]:
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
