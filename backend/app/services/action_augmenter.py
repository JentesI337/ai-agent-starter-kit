from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from app.services.intent_detector import IntentDetector


class ActionAugmenter:
    def __init__(
        self,
        intent_detector: IntentDetector | None = None,
        *,
        max_spawn_subrun_actions: int = 1,
        min_subrun_message_chars: int = 20,
    ):
        self._intent = intent_detector
        self._max_spawn_subrun_actions = max(1, int(max_spawn_subrun_actions))
        self._min_subrun_message_chars = max(1, int(min_subrun_message_chars))

    def _should_delegate_subrun(self, user_message: str) -> tuple[bool, str]:
        text = (user_message or "").strip()
        if len(text) < self._min_subrun_message_chars:
            return False, "message_too_short"

        lowered = text.lower()
        complexity_markers = (
            "parallel",
            "multi-step",
            "multiple files",
            "complex",
            "coordinate",
            "orchestrate",
            "delegate",
        )
        if not any(marker in lowered for marker in complexity_markers):
            return False, "no_complexity_markers"

        return True, "complexity_detected"

    def _apply_subrun_governance(self, actions: list[dict]) -> tuple[list[dict], bool]:
        governed_actions: list[dict] = []
        spawn_seen = 0
        reduced = False

        for action in actions:
            tool_name = str(action.get("tool", "")).strip()
            if tool_name != "spawn_subrun":
                governed_actions.append(action)
                continue

            spawn_seen += 1
            if spawn_seen <= self._max_spawn_subrun_actions:
                governed_actions.append(action)
                continue

            reduced = True

        return governed_actions, reduced

    def augment(self, actions: list[dict], user_message: str, allowed_tools: set[str]) -> list[dict]:
        augmented_actions = list(actions)

        if (
            self._intent is not None
            and self._intent.is_web_research_task(user_message)
            and not any(str(action.get("tool", "")).strip() == "web_search" for action in augmented_actions)
            and not any(str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions)
        ):
            if "web_search" in allowed_tools:
                augmented_actions.append(
                    {
                        "tool": "web_search",
                        "args": {"query": user_message.strip() or "latest news", "max_results": 5},
                    }
                )
            elif "web_fetch" in allowed_tools:
                fallback_url = self._intent.build_search_url(user_message)
                if fallback_url:
                    augmented_actions.append({"tool": "web_fetch", "args": {"url": fallback_url, "max_chars": 24000}})

        if (
            self._intent is not None
            and self._intent.is_subrun_orchestration_task(user_message)
            and "spawn_subrun" in allowed_tools
            and not any(str(action.get("tool", "")).strip() == "spawn_subrun" for action in augmented_actions)
        ):
            should_delegate, _ = self._should_delegate_subrun(user_message)
            if not should_delegate:
                return augmented_actions
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
        had_web_search_in_input = any(str(action.get("tool", "")).strip() == "web_search" for action in actions)
        had_spawn_subrun_in_input = any(
            str(action.get("tool", "")).strip() == "spawn_subrun" for action in actions
        )

        augmented_actions = self.augment(actions, user_message, allowed_tools)

        has_web_fetch_after_augment = any(
            str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions
        )
        has_web_search_after_augment = any(
            str(action.get("tool", "")).strip() == "web_search" for action in augmented_actions
        )
        if (
            is_web_research_task(user_message)
            and not had_web_fetch_in_input
            and not had_web_search_in_input
            and (has_web_search_after_augment or has_web_fetch_after_augment)
        ):
            search_action = next(
                (action for action in augmented_actions if str(action.get("tool", "")).strip() == "web_search"),
                None,
            ) or next(
                (action for action in augmented_actions if str(action.get("tool", "")).strip() == "web_fetch"),
                None,
            )
            added_tool = str(search_action.get("tool", "")).strip() if search_action else ""
            added_url = str(search_action.get("args", {}).get("url", "")) if search_action else ""
            added_query = str(search_action.get("args", {}).get("query", "")) if search_action else ""
            await emit_lifecycle(
                "tool_selection_followup_completed",
                {
                    "reason": "web_research_without_search_tool",
                    "added_tool": added_tool,
                    "url": added_url,
                    "query": added_query,
                },
            )

        has_spawn_subrun_after_augment = any(
            str(action.get("tool", "")).strip() == "spawn_subrun" for action in augmented_actions
        )
        should_delegate_subrun, delegate_reason = self._should_delegate_subrun(user_message)
        if (
            is_subrun_orchestration_task(user_message)
            and "spawn_subrun" in allowed_tools
            and not had_spawn_subrun_in_input
            and should_delegate_subrun
            and has_spawn_subrun_after_augment
        ):
            await emit_lifecycle(
                "tool_selection_followup_completed",
                {
                    "reason": "orchestration_without_spawn_subrun",
                    "added_tool": "spawn_subrun",
                    "delegation_reason": delegate_reason,
                },
            )

        if is_subrun_orchestration_task(user_message) and "spawn_subrun" in allowed_tools and not should_delegate_subrun:
            await emit_lifecycle(
                "subrun_delegation_skipped",
                {
                    "reason": delegate_reason,
                    "min_subrun_message_chars": self._min_subrun_message_chars,
                },
            )

        if (not uses_injected_intent) and is_web_research_task(user_message):
            has_web_search = any(str(action.get("tool", "")).strip() == "web_search" for action in augmented_actions)
            has_web_fetch = any(str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions)
            if not has_web_search and not has_web_fetch:
                if "web_search" in allowed_tools:
                    query = user_message.strip() or "latest news"
                    augmented_actions.append({"tool": "web_search", "args": {"query": query, "max_results": 5}})
                    await emit_lifecycle(
                        "tool_selection_followup_completed",
                        {
                            "reason": "web_research_without_search_tool",
                            "added_tool": "web_search",
                            "query": query,
                        },
                    )
                elif "web_fetch" in allowed_tools:
                    fallback_url = build_web_research_url(user_message)
                    if fallback_url:
                        augmented_actions.append({"tool": "web_fetch", "args": {"url": fallback_url, "max_chars": 24000}})
                        await emit_lifecycle(
                            "tool_selection_followup_completed",
                            {
                                "reason": "web_research_without_search_tool",
                                "added_tool": "web_fetch",
                                "url": fallback_url,
                            },
                        )

        if (not uses_injected_intent) and is_subrun_orchestration_task(user_message) and "spawn_subrun" in allowed_tools:
            has_spawn_subrun = any(str(action.get("tool", "")).strip() == "spawn_subrun" for action in augmented_actions)
            if not has_spawn_subrun and should_delegate_subrun:
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
                        "delegation_reason": delegate_reason,
                    },
                )

        augmented_actions, reduced_spawn_actions = self._apply_subrun_governance(augmented_actions)
        if reduced_spawn_actions:
            await emit_lifecycle(
                "subrun_governance_applied",
                {
                    "max_spawn_subrun_actions": self._max_spawn_subrun_actions,
                    "reason": "spawn_subrun_quota_enforced",
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
            "{\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command|code_execute|apply_patch|file_search|grep_search|list_code_usages|get_changed_files|start_background_command|get_background_output|kill_background_process|web_search|web_fetch|spawn_subrun\",\"args\":{}}]}\n"
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
