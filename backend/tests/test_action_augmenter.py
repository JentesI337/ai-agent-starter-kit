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
