from __future__ import annotations

import asyncio

from app.services.action_augmenter import ActionAugmenter


async def _noop_emit(stage: str, details: dict | None = None) -> None:
    return None


async def _fake_complete_chat(system_prompt: str, user_prompt: str, model: str | None = None) -> str:
    return '{"actions":[{"tool":"write_file","args":{"path":"x.txt","content":"hi"}}]}'


def test_augment_adds_web_fetch_when_missing() -> None:
    augmenter = ActionAugmenter()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def emit(stage: str, details: dict | None = None) -> None:
        lifecycle_events.append((stage, details))

    actions = asyncio.run(
        augmenter.augment_actions(
            actions=[],
            user_message="search on the web for llm news",
            plan_text="",
            memory_context="",
            model=None,
            allowed_tools={"web_fetch"},
            complete_chat=_fake_complete_chat,
            tool_selector_system_prompt="system",
            extract_actions=lambda raw: ([], None),
            validate_actions=lambda actions, allowed: (actions, 0),
            emit_lifecycle=emit,
            is_web_research_task=lambda message: True,
            build_web_research_url=lambda message: "https://duckduckgo.com/html/?q=llm",
            is_subrun_orchestration_task=lambda message: False,
            is_file_creation_task=lambda message: False,
        )
    )

    assert any(action.get("tool") == "web_fetch" for action in actions)
    assert any(stage == "tool_selection_followup_completed" for stage, _ in lifecycle_events)


def test_augment_prefers_web_search_when_available() -> None:
    augmenter = ActionAugmenter()

    actions = asyncio.run(
        augmenter.augment_actions(
            actions=[],
            user_message="search on the web for llm news",
            plan_text="",
            memory_context="",
            model=None,
            allowed_tools={"web_search", "web_fetch"},
            complete_chat=_fake_complete_chat,
            tool_selector_system_prompt="system",
            extract_actions=lambda raw: ([], None),
            validate_actions=lambda actions, allowed: (actions, 0),
            emit_lifecycle=_noop_emit,
            is_web_research_task=lambda message: True,
            build_web_research_url=lambda message: "https://duckduckgo.com/html/?q=llm",
            is_subrun_orchestration_task=lambda message: False,
            is_file_creation_task=lambda message: False,
        )
    )

    assert any(action.get("tool") == "web_search" for action in actions)
    assert not any(action.get("tool") == "web_fetch" for action in actions)


def test_augment_adds_spawn_subrun_when_missing() -> None:
    augmenter = ActionAugmenter()

    actions = asyncio.run(
        augmenter.augment_actions(
            actions=[],
            user_message="orchestrate a parallel research",
            plan_text="",
            memory_context="",
            model=None,
            allowed_tools={"spawn_subrun"},
            complete_chat=_fake_complete_chat,
            tool_selector_system_prompt="system",
            extract_actions=lambda raw: ([], None),
            validate_actions=lambda actions, allowed: (actions, 0),
            emit_lifecycle=_noop_emit,
            is_web_research_task=lambda message: False,
            build_web_research_url=lambda message: "",
            is_subrun_orchestration_task=lambda message: True,
            is_file_creation_task=lambda message: False,
        )
    )

    assert any(action.get("tool") == "spawn_subrun" for action in actions)
    spawn_action = next(action for action in actions if action.get("tool") == "spawn_subrun")
    assert spawn_action.get("args", {}).get("mode") == "wait"


def test_augment_skips_spawn_subrun_for_too_short_orchestration_prompt() -> None:
    augmenter = ActionAugmenter()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def emit(stage: str, details: dict | None = None) -> None:
        lifecycle_events.append((stage, details))

    actions = asyncio.run(
        augmenter.augment_actions(
            actions=[],
            user_message="orchestrate quickly",
            plan_text="",
            memory_context="",
            model=None,
            allowed_tools={"spawn_subrun"},
            complete_chat=_fake_complete_chat,
            tool_selector_system_prompt="system",
            extract_actions=lambda raw: ([], None),
            validate_actions=lambda actions, allowed: (actions, 0),
            emit_lifecycle=emit,
            is_web_research_task=lambda message: False,
            build_web_research_url=lambda message: "",
            is_subrun_orchestration_task=lambda message: True,
            is_file_creation_task=lambda message: False,
        )
    )

    assert not any(action.get("tool") == "spawn_subrun" for action in actions)
    assert any(stage == "subrun_delegation_skipped" for stage, _ in lifecycle_events)


def test_augment_applies_spawn_subrun_quota() -> None:
    augmenter = ActionAugmenter(max_spawn_subrun_actions=1)
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def emit(stage: str, details: dict | None = None) -> None:
        lifecycle_events.append((stage, details))

    actions = asyncio.run(
        augmenter.augment_actions(
            actions=[
                {"tool": "spawn_subrun", "args": {"message": "task A", "mode": "run", "agent_id": "head-agent"}},
                {"tool": "spawn_subrun", "args": {"message": "task B", "mode": "run", "agent_id": "head-agent"}},
            ],
            user_message="orchestrate a complex multi-step parallel research plan",
            plan_text="",
            memory_context="",
            model=None,
            allowed_tools={"spawn_subrun"},
            complete_chat=_fake_complete_chat,
            tool_selector_system_prompt="system",
            extract_actions=lambda raw: ([], None),
            validate_actions=lambda actions, allowed: (actions, 0),
            emit_lifecycle=emit,
            is_web_research_task=lambda message: False,
            build_web_research_url=lambda message: "",
            is_subrun_orchestration_task=lambda message: True,
            is_file_creation_task=lambda message: False,
        )
    )

    spawn_actions = [action for action in actions if action.get("tool") == "spawn_subrun"]
    assert len(spawn_actions) == 1
    assert any(stage == "subrun_governance_applied" for stage, _ in lifecycle_events)


def test_augment_file_task_merges_validated_followups() -> None:
    augmenter = ActionAugmenter()
    lifecycle_events: list[tuple[str, dict | None]] = []

    async def emit(stage: str, details: dict | None = None) -> None:
        lifecycle_events.append((stage, details))

    actions = asyncio.run(
        augmenter.augment_actions(
            actions=[{"tool": "read_file", "args": {"path": "README.md"}}],
            user_message="create a file with hello world",
            plan_text="",
            memory_context="ctx",
            model=None,
            allowed_tools={"read_file", "write_file"},
            complete_chat=_fake_complete_chat,
            tool_selector_system_prompt="system",
            extract_actions=lambda raw: ([{"tool": "write_file", "args": {"path": "x.txt", "content": "hi"}}], None),
            validate_actions=lambda actions, allowed: (actions, 0),
            emit_lifecycle=emit,
            is_web_research_task=lambda message: False,
            build_web_research_url=lambda message: "",
            is_subrun_orchestration_task=lambda message: False,
            is_file_creation_task=lambda message: True,
        )
    )

    assert any(action.get("tool") == "write_file" for action in actions)
    assert any(stage == "tool_selection_followup_started" for stage, _ in lifecycle_events)
    assert any(stage == "tool_selection_followup_completed" for stage, _ in lifecycle_events)
