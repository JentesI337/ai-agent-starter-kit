from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from app.services.intent_detector import IntentDetector


class ActionAugmenter:
    def __init__(self, intent_detector: IntentDetector | None = None):
        self._intent = intent_detector

    def augment(self, actions: list[dict], user_message: str, allowed_tools: set[str]) -> list[dict]:
        augmented_actions = list(actions)

        if (
            self._intent is not None
            and self._intent.is_web_research_task(user_message)
            and "web_fetch" in allowed_tools
            and not any(str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions)
        ):
            fallback_url = self._intent.build_search_url(user_message)
            if fallback_url:
                augmented_actions.append({"tool": "web_fetch", "args": {"url": fallback_url, "max_chars": 24000}})

        if (
            self._intent is not None
            and self._intent.is_subrun_orchestration_task(user_message)
            and "spawn_subrun" in allowed_tools
            and not any(str(action.get("tool", "")).strip() == "spawn_subrun" for action in augmented_actions)
        ):
            augmented_actions.append(
                {
                    "tool": "spawn_subrun",
                    "args": {
                        "message": user_message.strip() or "Execute delegated orchestration task",
                        "mode": "run",
                        "agent_id": "head-agent",
                    },
                }
            )

        return augmented_actions

    async def augment_actions(
        self,
        *,
        actions: list[dict],
        user_message: str,
        plan_text: str,
        memory_context: str,
        model: str | None,
        allowed_tools: set[str],
        complete_chat: Callable[[str, str, str | None], Awaitable[str]],
        tool_selector_system_prompt: str,
        extract_actions: Callable[[str], tuple[list[dict], str | None]],
        validate_actions: Callable[[list[dict], set[str]], tuple[list[dict], int]],
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
        is_web_research_task: Callable[[str], bool],
        build_web_research_url: Callable[[str], str],
        is_subrun_orchestration_task: Callable[[str], bool],
        is_file_creation_task: Callable[[str], bool],
    ) -> list[dict]:
        uses_injected_intent = self._intent is not None
        if uses_injected_intent:
            is_web_research_task = self._intent.is_web_research_task
            build_web_research_url = self._intent.build_search_url
            is_subrun_orchestration_task = self._intent.is_subrun_orchestration_task
            is_file_creation_task = self._intent.is_file_creation_task

        had_web_fetch_in_input = any(str(action.get("tool", "")).strip() == "web_fetch" for action in actions)
        had_spawn_subrun_in_input = any(
            str(action.get("tool", "")).strip() == "spawn_subrun" for action in actions
        )

        augmented_actions = self.augment(actions, user_message, allowed_tools)

        has_web_fetch_after_augment = any(
            str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions
        )
        if (
            is_web_research_task(user_message)
            and "web_fetch" in allowed_tools
            and not had_web_fetch_in_input
            and has_web_fetch_after_augment
        ):
            web_fetch_action = next(
                (action for action in augmented_actions if str(action.get("tool", "")).strip() == "web_fetch"),
                None,
            )
            added_url = str(web_fetch_action.get("args", {}).get("url", "")) if web_fetch_action else ""
            await emit_lifecycle(
                "tool_selection_followup_completed",
                {
                    "reason": "web_research_without_web_fetch",
                    "added_tool": "web_fetch",
                    "url": added_url,
                },
            )

        has_spawn_subrun_after_augment = any(
            str(action.get("tool", "")).strip() == "spawn_subrun" for action in augmented_actions
        )
        if (
            is_subrun_orchestration_task(user_message)
            and "spawn_subrun" in allowed_tools
            and not had_spawn_subrun_in_input
            and has_spawn_subrun_after_augment
        ):
            await emit_lifecycle(
                "tool_selection_followup_completed",
                {
                    "reason": "orchestration_without_spawn_subrun",
                    "added_tool": "spawn_subrun",
                },
            )

        if (not uses_injected_intent) and is_web_research_task(user_message) and "web_fetch" in allowed_tools:
            has_web_fetch = any(str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions)
            if not has_web_fetch:
                fallback_url = build_web_research_url(user_message)
                if fallback_url:
                    augmented_actions.append({"tool": "web_fetch", "args": {"url": fallback_url, "max_chars": 24000}})
                    await emit_lifecycle(
                        "tool_selection_followup_completed",
                        {
                            "reason": "web_research_without_web_fetch",
                            "added_tool": "web_fetch",
                            "url": fallback_url,
                        },
                    )

        if (not uses_injected_intent) and is_subrun_orchestration_task(user_message) and "spawn_subrun" in allowed_tools:
            has_spawn_subrun = any(str(action.get("tool", "")).strip() == "spawn_subrun" for action in augmented_actions)
            if not has_spawn_subrun:
                augmented_actions.append(
                    {
                        "tool": "spawn_subrun",
                        "args": {
                            "message": user_message.strip() or "Execute delegated orchestration task",
                            "mode": "run",
                            "agent_id": "head-agent",
                        },
                    }
                )
                await emit_lifecycle(
                    "tool_selection_followup_completed",
                    {
                        "reason": "orchestration_without_spawn_subrun",
                        "added_tool": "spawn_subrun",
                    },
                )

        if not is_file_creation_task(user_message):
            return augmented_actions

        has_write_action = any(str(action.get("tool", "")).strip() == "write_file" for action in augmented_actions)
        if has_write_action:
            return augmented_actions

        await emit_lifecycle(
            "tool_selection_followup_started",
            {"reason": "file_task_without_write_file"},
        )

        followup_prompt = (
            "You previously selected tools for a task.\n"
            "The user intent likely requires creating or updating files, but no write_file action was selected.\n"
            "Return strict JSON only:\n"
            "{\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command|apply_patch|file_search|grep_search|list_code_usages|get_changed_files|start_background_command|get_background_output|kill_background_process|web_fetch|spawn_subrun\",\"args\":{}}]}\n"
            "Choose up to 2 additional actions. Include write_file when enough content is available.\n"
            "If still insufficient context, return {\"actions\":[]}\n\n"
            "Memory:\n"
            f"{memory_context}\n\n"
            "Task:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}"
        )

        followup_raw = await complete_chat(
            tool_selector_system_prompt,
            followup_prompt,
            model=model,
        )
        followup_actions, followup_error = extract_actions(followup_raw)
        if followup_error:
            await emit_lifecycle(
                "tool_selection_followup_failed",
                {"error": followup_error},
            )
            return augmented_actions

        validated_followups, _ = validate_actions(followup_actions, allowed_tools)
        merged = augmented_actions + validated_followups
        deduped: list[dict] = []
        seen_keys: set[str] = set()
        for action in merged:
            key = json.dumps(action, sort_keys=True)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(action)

        await emit_lifecycle(
            "tool_selection_followup_completed",
            {"base_actions": len(actions), "merged_actions": len(deduped)},
        )
        return deduped
