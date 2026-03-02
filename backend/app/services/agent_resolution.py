from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping

from app.custom_agents import CustomAgentAdapter
from app.interfaces import OrchestratorApi


def normalize_agent_id(
    agent_id: str | None,
    *,
    primary_agent_id: str,
    legacy_agent_aliases: Mapping[str, str],
) -> str:
    raw = (agent_id or primary_agent_id).strip().lower()
    return legacy_agent_aliases.get(raw, raw)


def effective_orchestrator_agent_ids(
    *,
    configured_agent_ids: list[str] | None,
    primary_agent_id: str,
    custom_orchestrator_agent_ids: set[str] | None,
) -> set[str]:
    configured = {
        str(item).strip().lower()
        for item in (configured_agent_ids or [primary_agent_id])
        if isinstance(item, str) and str(item).strip()
    }
    configured.add(primary_agent_id)
    configured |= {
        str(item).strip().lower()
        for item in (custom_orchestrator_agent_ids or set())
        if isinstance(item, str) and str(item).strip()
    }
    return configured


def sync_custom_agents(
    *,
    components,
    normalize_agent_id_fn,
    primary_agent_id: str,
    coder_agent_id: str,
    review_agent_id: str,
    effective_orchestrator_agent_ids_fn,
) -> None:
    for custom_id in list(components.custom_agent_ids):
        components.agent_registry.pop(custom_id, None)
        components.orchestrator_registry.pop(custom_id, None)

    components.custom_agent_ids = set()
    components.custom_orchestrator_agent_ids = set()

    definitions = components.custom_agent_store.list()
    for definition in definitions:
        custom_id = normalize_agent_id_fn(definition.id)
        if not custom_id or custom_id in {primary_agent_id, coder_agent_id, review_agent_id}:
            continue

        base_id = normalize_agent_id_fn(definition.base_agent_id)
        base_agent = components.agent_registry.get(base_id)
        if base_agent is None:
            continue

        adapter = CustomAgentAdapter(definition=definition, base_agent=base_agent)
        components.agent_registry[custom_id] = adapter
        components.orchestrator_registry[custom_id] = OrchestratorApi(
            agent=adapter,
            state_store=components.state_store,
        )
        components.custom_agent_ids.add(custom_id)
        if bool(getattr(definition, "allow_subrun_delegation", False)):
            components.custom_orchestrator_agent_ids.add(custom_id)

    if components.subrun_lane is not None:
        components.subrun_lane._orchestrator_agent_ids = effective_orchestrator_agent_ids_fn(components)


def resolve_agent(
    *,
    agent_id: str | None,
    sync_custom_agents_fn,
    normalize_agent_id_fn,
    agent_registry: MutableMapping,
    orchestrator_registry: MutableMapping,
):
    sync_custom_agents_fn()
    normalized_agent_id = normalize_agent_id_fn(agent_id)
    selected_agent = agent_registry.get(normalized_agent_id)
    selected_orchestrator = orchestrator_registry.get(normalized_agent_id)
    if selected_agent is None or selected_orchestrator is None:
        raise ValueError(f"Unsupported agent: {agent_id}")
    return normalized_agent_id, selected_agent, selected_orchestrator


def looks_like_coding_request(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    keyword_markers = (
        "code",
        "python",
        "javascript",
        "typescript",
        "java",
        "c++",
        "c#",
        "golang",
        "rust",
        "sql",
        "html",
        "css",
        "bug",
        "debug",
        "fix",
        "refactor",
        "implement",
        "function",
        "class",
        "api",
        "endpoint",
        "test",
        "pytest",
        "unit test",
        "write file",
        "apply patch",
    )
    if any(marker in text for marker in keyword_markers):
        return True

    return bool(re.search(r"\b(build|create|generate|update)\b.*\b(script|module|component|service|backend|frontend)\b", text))
