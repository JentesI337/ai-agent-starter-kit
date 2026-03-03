from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
from time import monotonic
from uuid import uuid4

from app.config import Settings
from app.errors import ToolExecutionError
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.request_normalization import normalize_prompt_mode
from app.services.tool_call_gatekeeper import ToolCallGatekeeper
from app.services.tool_call_gatekeeper import prepare_action_for_execution

STEER_INTERRUPTED_MARKER = "__STEER_INTERRUPTED__"


@dataclass(frozen=True)
class ToolExecutionConfig:
    call_cap: int
    time_cap_seconds: float
    loop_warn_threshold: int
    loop_critical_threshold: int
    loop_circuit_breaker_threshold: int
    generic_repeat_enabled: bool
    ping_pong_enabled: bool
    poll_no_progress_enabled: bool
    poll_no_progress_threshold: int
    warning_bucket_size: int
    result_max_chars: int = 6000
    smart_truncate_enabled: bool = True
    parallel_read_only_enabled: bool = False

    @classmethod
    def from_settings(cls, app_settings: Settings) -> ToolExecutionConfig:
        loop_warn_threshold = max(1, int(getattr(app_settings, "tool_loop_warn_threshold", 2)))
        loop_critical_threshold = max(
            loop_warn_threshold + 1,
            int(getattr(app_settings, "tool_loop_critical_threshold", 5)),
        )
        return cls(
            call_cap=max(1, int(getattr(app_settings, "run_tool_call_cap", 8))),
            time_cap_seconds=max(1.0, float(getattr(app_settings, "run_tool_time_cap_seconds", 90.0))),
            result_max_chars=max(1000, int(getattr(app_settings, "tool_result_max_chars", 6000))),
            smart_truncate_enabled=bool(getattr(app_settings, "tool_result_smart_truncate_enabled", True)),
            parallel_read_only_enabled=bool(getattr(app_settings, "tool_execution_parallel_read_only_enabled", False)),
            loop_warn_threshold=loop_warn_threshold,
            loop_critical_threshold=loop_critical_threshold,
            loop_circuit_breaker_threshold=max(
                loop_critical_threshold + 1,
                int(getattr(app_settings, "tool_loop_circuit_breaker_threshold", 9)),
            ),
            generic_repeat_enabled=bool(getattr(app_settings, "tool_loop_detector_generic_repeat_enabled", True)),
            ping_pong_enabled=bool(getattr(app_settings, "tool_loop_detector_ping_pong_enabled", True)),
            poll_no_progress_enabled=bool(getattr(app_settings, "tool_loop_detector_poll_no_progress_enabled", True)),
            poll_no_progress_threshold=max(2, int(getattr(app_settings, "tool_loop_poll_no_progress_threshold", 3))),
            warning_bucket_size=max(1, int(getattr(app_settings, "tool_loop_warning_bucket_size", 2))),
        )


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_results: list[dict[str, object]]
    budget_exhausted: bool
    loop_detected: bool
    total_calls: int
    total_time_seconds: float
    audit_summary: dict[str, object]


class ToolExecutionManager:
    READ_ONLY_TOOLS = {
        "list_dir",
        "read_file",
        "file_search",
        "grep_search",
        "list_code_usages",
        "get_changed_files",
        "web_fetch",
    }

    def __init__(
        self,
        *,
        config: ToolExecutionConfig | None = None,
        registry: object | None = None,
        gatekeeper: object | None = None,
        intent_detector: object | None = None,
        arg_validator: object | None = None,
        action_parser: object | None = None,
        action_augmenter: object | None = None,
        llm_client: object | None = None,
        send_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._gatekeeper = gatekeeper
        self._intent_detector = intent_detector
        self._arg_validator = arg_validator
        self._action_parser = action_parser
        self._action_augmenter = action_augmenter
        self._llm_client = llm_client
        self._send_event = send_event
        self._prompt_kernel_builder = PromptKernelBuilder()

    @staticmethod
    def _normalize_prompt_mode_for_skills(prompt_mode: str | None) -> str:
        return normalize_prompt_mode(prompt_mode, default="minimal")

    @staticmethod
    def _should_inject_skills_preview_in_subagent(*, user_message: str, plan_text: str) -> bool:
        text = f"{user_message}\n{plan_text}".lower()
        markers = ("skill", "skills", "skill.md", "read_file", "manual", "runbook")
        return any(marker in text for marker in markers)

    @staticmethod
    def _contract_skills_prompt(*, prompt: str, prompt_mode: str, max_prompt_chars: int) -> tuple[str, bool]:
        source = (prompt or "").strip()
        if not source:
            return "", False

        configured_cap = max(0, int(max_prompt_chars))
        if configured_cap <= 0:
            return "", True

        normalized_mode = (prompt_mode or "minimal").strip().lower()
        if normalized_mode == "full":
            cap = configured_cap
        elif normalized_mode == "subagent":
            cap = min(configured_cap, 1200)
        else:
            cap = min(configured_cap, 3000)

        if len(source) <= cap:
            return source, False

        omitted = len(source) - cap
        return f"{source[:cap]}\n\n... [{omitted} chars truncated for {normalized_mode} skills mode]", True

    async def execute(
        self,
        *,
        user_message: str,
        plan_text: str,
        memory_context: str,
        prompt_mode: str,
        app_settings: Settings,
        model: str | None,
        allowed_tools: set[str],
        agent_name: str,
        request_id: str,
        session_id: str,
        client_model: str,
        skills_engine_enabled: bool,
        skills_canary_enabled: bool,
        skills_max_prompt_chars: int,
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
        emit_tool_selection_empty: Callable[[str, dict | None], Awaitable[None]],
        invoke_hooks: Callable[[str, dict], Awaitable[None]],
        send_event: Callable[[dict], Awaitable[None]],
        detect_intent_gate: Callable[[str], object],
        resolve_skills_enabled_for_request: Callable[..., tuple[bool, dict[str, object]]],
        build_skills_snapshot: Callable[[], object],
        empty_skills_snapshot: Callable[[], object],
        request_policy_override: Callable[..., Awaitable[bool]],
        complete_chat: Callable[[str, str, str | None], Awaitable[str]],
        complete_chat_with_tools: Callable[..., Awaitable[list[dict]]] | None = None,
        supports_function_calling: bool = False,
        tool_selection_function_calling_enabled: bool = True,
        tool_selector_system_prompt: str,
        extract_actions: Callable[[str], tuple[list[dict], str | None]],
        repair_tool_selection_json: Callable[..., Awaitable[str]],
        approve_blocked_process_tools_if_needed: Callable[..., Awaitable[set[str]]],
        validate_actions: Callable[[list[dict], set[str]], tuple[list[dict], int]],
        augment_actions_if_needed: Callable[..., Awaitable[list[dict]]],
        encode_blocked_tool_result: Callable[..., str],
        normalize_tool_name: Callable[[str], str],
        evaluate_action: Callable[[str, dict, set[str]], tuple[dict, str | None]],
        build_execution_policy: Callable[[str], object],
        run_tool_with_policy: Callable[..., Awaitable[str]],
        invoke_spawn_subrun_tool: Callable[..., Awaitable[str]],
        should_retry_web_fetch_on_404: Callable[[ToolExecutionError], bool],
        is_web_research_task: Callable[[str], bool],
        is_weather_lookup_task: Callable[[str], bool],
        build_web_research_url: Callable[[str], str],
        memory_add: Callable[[str, str], None],
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        effective_allowed_tools = set(allowed_tools)
        await emit_lifecycle("tool_selection_started", None)
        if not effective_allowed_tools:
            await emit_tool_selection_empty("policy_block", {"blocked_with_reason": "no_tools_allowed"})
            await emit_lifecycle("tool_selection_skipped", {"reason": "no_tools_allowed"})
            return ""

        intent_decision = detect_intent_gate(user_message)
        model_id = model or client_model
        effective_prompt_mode = self._normalize_prompt_mode_for_skills(prompt_mode)
        skills_enabled, skills_gating_details = resolve_skills_enabled_for_request(model_id=model_id)
        if skills_enabled:
            skills_snapshot = build_skills_snapshot()
            await emit_lifecycle(
                "skills_snapshot_built",
                {
                    "prompt_mode": effective_prompt_mode,
                    **skills_gating_details,
                },
            )
        else:
            skills_snapshot = empty_skills_snapshot()
            await emit_lifecycle(
                "skills_snapshot_skipped",
                {
                    "prompt_mode": effective_prompt_mode,
                    **skills_gating_details,
                },
            )

        if skills_engine_enabled and skills_canary_enabled and not skills_enabled:
            await emit_lifecycle("skills_skipped_canary", skills_gating_details)

        if skills_enabled:
            await emit_lifecycle(
                "skills_discovered",
                {
                    "discovered": getattr(skills_snapshot, "discovered_count", 0),
                    "eligible": getattr(skills_snapshot, "eligible_count", 0),
                    "selected": getattr(skills_snapshot, "selected_count", 0),
                    "truncated": getattr(skills_snapshot, "truncated", False),
                },
            )
            if getattr(skills_snapshot, "truncated", False):
                await emit_lifecycle(
                    "skills_truncated",
                    {
                        "max_prompt_chars": skills_max_prompt_chars,
                        "selected": getattr(skills_snapshot, "selected_count", 0),
                    },
                )

        effective_memory_context = memory_context
        snapshot_prompt = str(getattr(skills_snapshot, "prompt", "") or "").strip()
        if skills_enabled and snapshot_prompt:
            if effective_prompt_mode == "subagent" and not self._should_inject_skills_preview_in_subagent(
                user_message=user_message,
                plan_text=plan_text,
            ):
                await emit_lifecycle(
                    "skills_preview_omitted_by_prompt_mode",
                    {
                        "prompt_mode": effective_prompt_mode,
                        "reason": "subagent_low_relevance",
                        "source_chars": len(snapshot_prompt),
                    },
                )
            else:
                contracted_prompt, contracted = self._contract_skills_prompt(
                    prompt=snapshot_prompt,
                    prompt_mode=effective_prompt_mode,
                    max_prompt_chars=skills_max_prompt_chars,
                )
                if contracted_prompt:
                    effective_memory_context = f"{memory_context}\n\n{contracted_prompt}"
                    await emit_lifecycle(
                        "skills_preview_injected",
                        {
                            "prompt_mode": effective_prompt_mode,
                            "source_chars": len(snapshot_prompt),
                            "injected_chars": len(contracted_prompt),
                            "contracted": contracted,
                        },
                    )
                else:
                    await emit_lifecycle(
                        "skills_preview_omitted_by_prompt_mode",
                        {
                            "prompt_mode": effective_prompt_mode,
                            "reason": "contracted_to_empty",
                            "source_chars": len(snapshot_prompt),
                        },
                    )

        intent = getattr(intent_decision, "intent", None)
        confidence = getattr(intent_decision, "confidence", "low")
        extracted_command = getattr(intent_decision, "extracted_command", None)
        missing_slots = tuple(getattr(intent_decision, "missing_slots", ()) or ())

        if intent == "execute_command" and "run_command" not in effective_allowed_tools:
            approved = await request_policy_override(tool="run_command", resource=(extracted_command or "(missing command)"))
            if approved:
                effective_allowed_tools.add("run_command")

        if intent == "execute_command" and "run_command" not in effective_allowed_tools:
            blocked_message = (
                "I can execute commands for you, but command execution is currently blocked by the active tool policy. "
                "Please allow `run_command` (or switch to a coding-capable profile) and retry."
            )
            await emit_tool_selection_empty(
                "policy_block",
                {
                    "intent": intent,
                    "confidence": confidence,
                    "blocked_with_reason": "run_command_not_allowed",
                },
            )
            await emit_lifecycle("tool_selection_completed", {"actions": 0, "blocked_with_reason": "run_command_not_allowed"})
            return encode_blocked_tool_result(
                blocked_with_reason="run_command_not_allowed",
                message=blocked_message,
            )

        if intent == "execute_command" and missing_slots:
            blocked_message = (
                "Ich kann den Command ausführen, brauche aber den exakten Befehl. "
                "Bitte nenne genau den auszuführenden Command (z. B. `pytest -q` oder `npm test`)."
            )
            await emit_tool_selection_empty(
                "missing_slots",
                {
                    "intent": intent,
                    "confidence": confidence,
                    "missing_slots": list(missing_slots),
                    "blocked_with_reason": "missing_command",
                },
            )
            await emit_lifecycle("tool_selection_completed", {"actions": 0, "blocked_with_reason": "missing_command"})
            return encode_blocked_tool_result(
                blocked_with_reason="missing_command",
                message=blocked_message,
            )

        await invoke_hooks(
            "before_prompt_build",
            {
                "prompt_type": "tool_selection",
                "model": model,
                "prompt_mode": prompt_mode,
                "context_chars": len(effective_memory_context),
                "allowed_tools": sorted(effective_allowed_tools),
            },
        )

        tool_selector_prompt = self.build_tool_selector_prompt(
            allowed_tools=effective_allowed_tools,
            memory_context=effective_memory_context,
            user_message=user_message,
            plan_text=plan_text,
            prompt_mode=prompt_mode,
        )

        actions = await self.select_actions_with_repair(
            complete_chat=complete_chat,
            complete_chat_with_tools=complete_chat_with_tools,
            supports_function_calling=supports_function_calling,
            function_calling_enabled=tool_selection_function_calling_enabled,
            tool_selector_system_prompt=tool_selector_system_prompt,
            tool_selector_prompt=tool_selector_prompt,
            allowed_tools=effective_allowed_tools,
            model=model,
            extract_actions=extract_actions,
            repair_tool_selection_json=repair_tool_selection_json,
            emit_lifecycle=emit_lifecycle,
            send_event=send_event,
            request_id=request_id,
            session_id=session_id,
            agent_name=agent_name,
        )

        actions, effective_allowed_tools, rejected_count, blocked_result = await self.apply_action_pipeline(
            actions=actions,
            effective_allowed_tools=effective_allowed_tools,
            user_message=user_message,
            plan_text=plan_text,
            memory_context=memory_context,
            model=model,
            intent=intent,
            confidence=confidence,
            extracted_command=extracted_command,
            approve_blocked_process_tools_if_needed=approve_blocked_process_tools_if_needed,
            validate_actions=validate_actions,
            augment_actions_if_needed=augment_actions_if_needed,
            emit_lifecycle=emit_lifecycle,
            emit_tool_selection_empty=emit_tool_selection_empty,
            encode_blocked_tool_result=encode_blocked_tool_result,
        )
        if blocked_result is not None:
            return blocked_result

        if rejected_count > 0:
            await emit_lifecycle("tool_selection_actions_rejected", {"rejected": rejected_count})
        await emit_lifecycle("tool_selection_completed", {"actions": len(actions)})
        if not actions:
            empty_reason = "ambiguous_input"
            if intent is not None and confidence == "low":
                empty_reason = "low_confidence"
            await emit_tool_selection_empty(
                empty_reason,
                {
                    "intent": intent,
                    "confidence": confidence,
                    "rejected_actions": rejected_count,
                },
            )
            return ""

        config = ToolExecutionConfig.from_settings(app_settings)

        return await self.run_tool_loop(
            actions=actions,
            effective_allowed_tools=effective_allowed_tools,
            config=config,
            user_message=user_message,
            model=model,
            agent_name=agent_name,
            normalize_tool_name=normalize_tool_name,
            evaluate_action=evaluate_action,
            build_execution_policy=build_execution_policy,
            run_tool_with_policy=run_tool_with_policy,
            invoke_spawn_subrun_tool=invoke_spawn_subrun_tool,
            should_retry_web_fetch_on_404=should_retry_web_fetch_on_404,
            is_web_research_task=is_web_research_task,
            is_weather_lookup_task=is_weather_lookup_task,
            build_web_research_url=build_web_research_url,
            memory_add=memory_add,
            emit_lifecycle=emit_lifecycle,
            send_event=send_event,
            invoke_hooks=invoke_hooks,
            should_steer_interrupt=should_steer_interrupt,
        )

    @staticmethod
    def _smart_truncate(text: str, *, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        head_size = int(max_chars * 0.7)
        tail_size = max(0, max_chars - head_size - 50)
        if tail_size <= 0:
            return text[:max_chars]
        omitted = max(0, len(text) - (head_size + tail_size))
        separator = f"\n\n... [{omitted} chars truncated] ...\n\n"
        return f"{text[:head_size]}{separator}{text[-tail_size:]}"

    def build_tool_selector_prompt(
        self,
        *,
        allowed_tools: set[str],
        memory_context: str,
        user_message: str,
        plan_text: str,
        prompt_mode: str = "minimal",
    ) -> str:
        allowed_text = "|".join(sorted(allowed_tools)) if allowed_tools else "(none)"
        instructions = (
            "Choose up to 3 tool calls to support this task.\n"
            "Return strict JSON only in this schema:\n"
            f"{{\"actions\":[{{\"tool\":\"{allowed_text}\",\"args\":{{}}}}]}}\n"
            "If no tool is needed return {\"actions\":[]}.\n"
            "If the user explicitly asks to search/browse/check the web, include at least one web_fetch action whenever allowed.\n"
            "Key args by tool:\n"
            "- write_file: path, content\n"
            "- apply_patch: path, search, replace, optional replace_all\n"
            "- run_command/start_background_command: command, optional cwd\n"
            "- spawn_subrun: message, optional mode(run|session), optional agent_id, optional model, optional timeout_seconds, optional tool_policy\n"
            "- file_search: pattern, optional max_results\n"
            "- grep_search: query, optional include_pattern, optional is_regexp, optional max_results\n"
            "- list_code_usages: symbol, optional include_pattern, optional max_results\n"
            "- get_background_output/kill_background_process: job_id\n"
            "- web_fetch: url, optional max_chars\n\n"
            "Do not output markdown, explanations, [TOOL_CALL] wrappers, or any text outside the JSON object.\n"
            f"Allowed tool names are exactly: {', '.join(sorted(allowed_tools)) or 'none'}."
        )
        kernel = self._prompt_kernel_builder.build(
            prompt_type="tool_selection",
            prompt_mode=normalize_prompt_mode(prompt_mode, default="minimal"),
            sections={
                "instructions": instructions,
                "memory": memory_context,
                "task": user_message,
                "plan": plan_text,
            },
        )
        return kernel.rendered

    def _build_tool_selection_prompt(
        self,
        *,
        allowed_tools: set[str],
        memory_context: str,
        user_message: str,
        plan_text: str,
        prompt_mode: str = "minimal",
    ) -> str:
        return self.build_tool_selector_prompt(
            allowed_tools=allowed_tools,
            memory_context=memory_context,
            user_message=user_message,
            plan_text=plan_text,
            prompt_mode=prompt_mode,
        )

    def build_loop_gatekeeper(self, config: ToolExecutionConfig) -> ToolCallGatekeeper:
        return ToolCallGatekeeper(
            warn_threshold=config.loop_warn_threshold,
            critical_threshold=config.loop_critical_threshold,
            circuit_breaker_threshold=config.loop_circuit_breaker_threshold,
            warning_bucket_size=config.warning_bucket_size,
            generic_repeat_enabled=config.generic_repeat_enabled,
            ping_pong_enabled=config.ping_pong_enabled,
            poll_no_progress_enabled=config.poll_no_progress_enabled,
            poll_no_progress_threshold=config.poll_no_progress_threshold,
        )

    async def select_actions_with_repair(
        self,
        *,
        complete_chat: Callable[[str, str, str | None], Awaitable[str]],
        tool_selector_system_prompt: str,
        tool_selector_prompt: str,
        model: str | None,
        extract_actions: Callable[[str], tuple[list[dict], str | None]],
        repair_tool_selection_json: Callable[..., Awaitable[str]],
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
        send_event: Callable[[dict], Awaitable[None]],
        request_id: str,
        session_id: str,
        agent_name: str,
        complete_chat_with_tools: Callable[..., Awaitable[list[dict]]] | None = None,
        supports_function_calling: bool = False,
        function_calling_enabled: bool = False,
        allowed_tools: set[str] | None = None,
    ) -> list[dict]:
        effective_allowed_tools = set(allowed_tools or set())
        if function_calling_enabled and supports_function_calling and complete_chat_with_tools is not None:
            try:
                actions = await complete_chat_with_tools(
                    system_prompt=tool_selector_system_prompt,
                    user_prompt=tool_selector_prompt,
                    allowed_tools=sorted(effective_allowed_tools),
                    model=model,
                )
                if actions:
                    await emit_lifecycle(
                        "tool_selection_function_calling_used",
                        {"actions": len(actions), "allowed_tools": len(effective_allowed_tools)},
                    )
                    return actions
                await emit_lifecycle(
                    "tool_selection_function_calling_empty",
                    {"allowed_tools": len(effective_allowed_tools)},
                )
            except Exception as exc:
                await emit_lifecycle(
                    "tool_selection_function_calling_failed",
                    {"error": str(exc)},
                )

        raw = await complete_chat(tool_selector_system_prompt, tool_selector_prompt, model)
        actions, parse_error = extract_actions(raw)
        repaired = False

        if parse_error:
            await emit_lifecycle("tool_selection_repair_started", {"error": parse_error})
            repaired_raw = await repair_tool_selection_json(raw=raw, model=model)
            repaired_actions, repaired_error = extract_actions(repaired_raw)
            if repaired_error is None:
                actions = repaired_actions
                parse_error = None
                repaired = True
                await emit_lifecycle("tool_selection_repair_completed", None)
            else:
                parse_error = f"{parse_error} | repair_failed: {repaired_error}"
                await emit_lifecycle("tool_selection_repair_failed", {"error": repaired_error})

        if parse_error:
            await send_event(
                {
                    "type": "error",
                    "agent": agent_name,
                    "message": f"Tool-selection parse issue: {parse_error}",
                }
            )
            await emit_lifecycle(
                "tool_selection_parse_failed",
                {
                    "error": parse_error,
                    "raw_preview": raw[:300],
                },
            )

        if repaired:
            await send_event(
                {
                    "type": "status",
                    "agent": agent_name,
                    "message": "Tool-selection output recovered from malformed format.",
                }
            )

        return actions

    async def _validate_and_filter(self, **kwargs) -> tuple[list[dict], set[str], int, str | None]:
        return await self.apply_action_pipeline(**kwargs)

    async def _handle_augmentation(self, **kwargs) -> list[dict]:
        augment_fn = kwargs.pop("augment_actions_if_needed")
        return await augment_fn(**kwargs)

    def _check_loop_conditions(self, *, elapsed_seconds: float, total_calls: int, config: ToolExecutionConfig) -> bool:
        if total_calls >= config.call_cap:
            return True
        if elapsed_seconds >= config.time_cap_seconds:
            return True
        return False

    async def _execute_action_batch(self, **kwargs) -> str:
        return await self.run_tool_loop(**kwargs)

    async def apply_action_pipeline(
        self,
        *,
        actions: list[dict],
        effective_allowed_tools: set[str],
        user_message: str,
        plan_text: str,
        memory_context: str,
        model: str | None,
        intent: str | None,
        confidence: str,
        extracted_command: str | None,
        approve_blocked_process_tools_if_needed: Callable[..., Awaitable[set[str]]],
        validate_actions: Callable[[list[dict], set[str]], tuple[list[dict], int]],
        augment_actions_if_needed: Callable[..., Awaitable[list[dict]]],
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
        emit_tool_selection_empty: Callable[[str, dict | None], Awaitable[None]],
        encode_blocked_tool_result: Callable[..., str],
    ) -> tuple[list[dict], set[str], int, str | None]:
        updated_allowed_tools = await approve_blocked_process_tools_if_needed(
            actions=actions,
            allowed_tools=effective_allowed_tools,
        )

        validated_actions, rejected_count = validate_actions(actions, updated_allowed_tools)

        augmented_actions = await augment_actions_if_needed(
            actions=validated_actions,
            user_message=user_message,
            plan_text=plan_text,
            memory_context=memory_context,
            model=model,
            allowed_tools=updated_allowed_tools,
        )

        if not augmented_actions and intent == "execute_command" and confidence == "high":
            if extracted_command:
                augmented_actions = [
                    {
                        "tool": "run_command",
                        "args": {"command": extracted_command},
                    }
                ]
                await emit_lifecycle(
                    "tool_selection_followup_completed",
                    {
                        "reason": "intent_execute_command_forced_action",
                        "added_tool": "run_command",
                    },
                )
            else:
                blocked_message = (
                    "Ich kann den Command ausführen, brauche aber den exakten Befehl. "
                    "Bitte nenne genau den auszuführenden Command (z. B. `pytest -q` oder `npm test`)."
                )
                await emit_tool_selection_empty(
                    "missing_slots",
                    {
                        "intent": intent,
                        "confidence": confidence,
                        "missing_slots": ["command"],
                        "blocked_with_reason": "missing_command",
                    },
                )
                await emit_lifecycle(
                    "tool_selection_completed",
                    {"actions": 0, "blocked_with_reason": "missing_command"},
                )
                blocked_result = encode_blocked_tool_result(
                    blocked_with_reason="missing_command",
                    message=blocked_message,
                )
                return augmented_actions, updated_allowed_tools, rejected_count, blocked_result

        return augmented_actions, updated_allowed_tools, rejected_count, None

    async def run_tool_loop(
        self,
        *,
        actions: list[dict],
        effective_allowed_tools: set[str],
        config: ToolExecutionConfig,
        user_message: str,
        model: str | None,
        agent_name: str,
        normalize_tool_name: Callable[[str], str],
        evaluate_action: Callable[[str, dict, set[str]], tuple[dict, str | None]],
        build_execution_policy: Callable[[str], object],
        run_tool_with_policy: Callable[..., Awaitable[str]],
        invoke_spawn_subrun_tool: Callable[..., Awaitable[str]],
        should_retry_web_fetch_on_404: Callable[[ToolExecutionError], bool],
        is_web_research_task: Callable[[str], bool],
        is_weather_lookup_task: Callable[[str], bool],
        build_web_research_url: Callable[[str], str],
        memory_add: Callable[[str, str], None],
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
        send_event: Callable[[dict], Awaitable[None]],
        invoke_hooks: Callable[[str, dict], Awaitable[None]],
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        results: list[str] = []
        tool_call_cap = config.call_cap
        tool_time_cap_seconds = config.time_cap_seconds
        result_max_chars = config.result_max_chars
        loop_gatekeeper = self.build_loop_gatekeeper(config)
        tool_call_count = 0
        budget_blocked_count = 0
        tool_error_count = 0
        started_at = monotonic()

        await emit_lifecycle(
            "tool_loop_started",
            {
                "total_actions": len(actions),
                "call_cap": tool_call_cap,
                "time_cap_seconds": tool_time_cap_seconds,
            },
        )

        if config.parallel_read_only_enabled:
            read_only_actions = [
                action
                for action in actions
                if isinstance(action, dict)
                and str(action.get("tool", "")).strip() in self.READ_ONLY_TOOLS
            ]
            mutating_actions = [action for action in actions if action not in read_only_actions]
            if read_only_actions:
                await emit_lifecycle(
                    "tool_parallel_read_only_started",
                    {"count": len(read_only_actions)},
                )
                read_only_results = await asyncio.gather(
                    *[
                        self._execute_read_only_action(
                            action=action,
                            effective_allowed_tools=effective_allowed_tools,
                            normalize_tool_name=normalize_tool_name,
                            evaluate_action=evaluate_action,
                            build_execution_policy=build_execution_policy,
                            run_tool_with_policy=run_tool_with_policy,
                            invoke_spawn_subrun_tool=invoke_spawn_subrun_tool,
                            model=model,
                            max_chars=result_max_chars,
                            smart_truncate_enabled=config.smart_truncate_enabled,
                            memory_add=memory_add,
                        )
                        for action in read_only_actions
                    ],
                    return_exceptions=True,
                )
                for item in read_only_results:
                    if isinstance(item, Exception):
                        results.append(f"[read_only_parallel] ERROR: {item}")
                        tool_error_count += 1
                        continue
                    if item is None:
                        continue
                    results.append(item)
                    tool_call_count += 1
                await emit_lifecycle(
                    "tool_parallel_read_only_completed",
                    {"count": len(read_only_actions)},
                )
            actions = mutating_actions

        for idx, action in enumerate(actions, start=1):
            call_id = f"tool-call-{idx}-{uuid4().hex[:8]}"
            prep = prepare_action_for_execution(
                action=action,
                allowed_tools=effective_allowed_tools,
                normalize_tool_name=normalize_tool_name,
                evaluate_action=evaluate_action,
            )
            fallback_tool = action.get("tool") if isinstance(action, dict) else ""
            tool = prep.tool or (str(fallback_tool).strip() if isinstance(fallback_tool, str) else "")

            elapsed = monotonic() - started_at
            if elapsed >= tool_time_cap_seconds:
                budget_blocked_count += 1
                message = f"tool time budget exceeded ({tool_time_cap_seconds:.1f}s)"
                results.append(f"[{tool}] REJECTED: {message}")
                await emit_lifecycle(
                    "tool_budget_exceeded",
                    {
                        "tool": tool,
                        "index": idx,
                        "call_id": call_id,
                        "budget_type": "time",
                        "elapsed_seconds": round(elapsed, 3),
                        "limit_seconds": tool_time_cap_seconds,
                    },
                )
                break

            if tool_call_count >= tool_call_cap:
                budget_blocked_count += 1
                message = f"tool call budget exceeded ({tool_call_cap})"
                results.append(f"[{tool}] REJECTED: {message}")
                await emit_lifecycle(
                    "tool_budget_exceeded",
                    {
                        "tool": tool,
                        "index": idx,
                        "call_id": call_id,
                        "budget_type": "call_count",
                        "used_calls": tool_call_count,
                        "limit_calls": tool_call_cap,
                    },
                )
                break

            if prep.error:
                results.append(f"[{tool}] REJECTED: {prep.error}")
                await send_event(
                    {
                        "type": "error",
                        "agent": agent_name,
                        "message": f"Tool blocked ({tool}): {prep.error}",
                    }
                )
                await emit_lifecycle(
                    "tool_blocked",
                    {"tool": tool, "index": idx, "call_id": call_id, "error": prep.error},
                )
                continue
            evaluated_args = prep.normalized_args

            signature = loop_gatekeeper.build_signature(tool=tool, args=evaluated_args)
            pre_decision = loop_gatekeeper.before_tool_call(tool=tool, signature=signature, index=idx)
            for stage, details in pre_decision.lifecycle_events:
                await emit_lifecycle(stage, details)
            if pre_decision.blocked:
                results.append(f"[{tool}] REJECTED: {pre_decision.rejection_message}")
                if pre_decision.break_run:
                    break
                continue

            policy = build_execution_policy(tool)

            await send_event(
                {
                    "type": "agent_step",
                    "agent": agent_name,
                    "step": f"Tool {idx}: {tool}",
                }
            )
            await emit_lifecycle(
                "tool_started",
                {
                    "tool": tool,
                    "index": idx,
                    "call_id": call_id,
                    "status": "started",
                    "duration_ms": 0,
                },
            )

            await invoke_hooks(
                "before_tool_call",
                {
                    "tool": tool,
                    "args": dict(evaluated_args),
                    "index": idx,
                    "call_id": call_id,
                },
            )

            try:
                tool_started = monotonic()
                if tool == "spawn_subrun":
                    result = await invoke_spawn_subrun_tool(args=evaluated_args, model=model)
                else:
                    result = await run_tool_with_policy(tool=tool, args=evaluated_args, policy=policy)
                tool_call_count += 1
                tool_elapsed_ms = int((monotonic() - tool_started) * 1000)
                clipped = (
                    self._smart_truncate(result, max_chars=result_max_chars)
                    if config.smart_truncate_enabled
                    else result[:result_max_chars]
                )
                memory_add(tool, clipped)
                results.append(f"[{tool}]\n{clipped}")

                post_decision = loop_gatekeeper.after_tool_success(
                    tool=tool,
                    signature=signature,
                    index=idx,
                    result=clipped,
                )
                for stage, details in post_decision.lifecycle_events:
                    await emit_lifecycle(stage, details)
                if post_decision.blocked:
                    results.append(f"[{tool}] REJECTED: {post_decision.rejection_message}")
                    if post_decision.break_run:
                        break
                    continue

                await emit_lifecycle(
                    "tool_completed",
                    {
                        "tool": tool,
                        "index": idx,
                        "call_id": call_id,
                        "status": "ok",
                        "result_chars": len(clipped),
                        "duration_ms": tool_elapsed_ms,
                        "elapsed_ms": tool_elapsed_ms,
                    },
                )
                await invoke_hooks(
                    "after_tool_call",
                    {
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "index": idx,
                        "call_id": call_id,
                        "status": "ok",
                        "duration_ms": tool_elapsed_ms,
                        "result_chars": len(clipped),
                    },
                )
                if tool == "read_file":
                    path_candidate = str(evaluated_args.get("path") or evaluated_args.get("filePath") or "").strip()
                    if path_candidate.lower().endswith("skill.md"):
                        await emit_lifecycle(
                            "skills_manual_read",
                            {
                                "tool": tool,
                                "index": idx,
                                "call_id": call_id,
                                "path": path_candidate,
                            },
                        )
                if should_steer_interrupt is not None and should_steer_interrupt():
                    await emit_lifecycle(
                        "steer_detected",
                        {
                            "checkpoint_stage": "tool_completed",
                            "index": idx,
                            "tool": tool,
                        },
                    )
                    await emit_lifecycle(
                        "steer_applied",
                        {
                            "checkpoint_stage": "tool_completed",
                            "index": idx,
                            "tool": tool,
                        },
                    )
                    return STEER_INTERRUPTED_MARKER
            except ToolExecutionError as exc:
                error_elapsed_ms = int((monotonic() - tool_started) * 1000)
                attempt_calls = 1
                retried_successfully = False
                if (
                    tool == "web_fetch"
                    and should_retry_web_fetch_on_404(exc)
                    and (is_web_research_task(user_message) or is_weather_lookup_task(user_message))
                ):
                    fallback_url = build_web_research_url(user_message)
                    primary_url = str(evaluated_args.get("url", "")).strip()
                    if fallback_url and fallback_url != primary_url:
                        await send_event(
                            {
                                "type": "agent_step",
                                "agent": agent_name,
                                "step": f"Tool {idx}: web_fetch retry with fallback source",
                            }
                        )
                        await emit_lifecycle(
                            "tool_retry_started",
                            {
                                "tool": tool,
                                "index": idx,
                                "call_id": call_id,
                                "reason": "http_404",
                                "from_url": primary_url,
                                "to_url": fallback_url,
                            },
                        )
                        retry_args = dict(evaluated_args)
                        retry_args["url"] = fallback_url
                        attempt_calls += 1
                        try:
                            retry_started = monotonic()
                            retry_result = await run_tool_with_policy(tool=tool, args=retry_args, policy=policy)
                            retry_elapsed_ms = int((monotonic() - retry_started) * 1000)
                            clipped = (
                                self._smart_truncate(retry_result, max_chars=result_max_chars)
                                if config.smart_truncate_enabled
                                else retry_result[:result_max_chars]
                            )
                            memory_add(tool, clipped)
                            results.append(f"[{tool}]\n{clipped}")
                            await emit_lifecycle(
                                "tool_completed",
                                {
                                    "tool": tool,
                                    "index": idx,
                                    "call_id": call_id,
                                    "status": "ok",
                                    "result_chars": len(clipped),
                                    "duration_ms": retry_elapsed_ms,
                                    "elapsed_ms": retry_elapsed_ms,
                                    "retried": True,
                                },
                            )
                            await emit_lifecycle(
                                "tool_retry_completed",
                                {
                                    "tool": tool,
                                    "index": idx,
                                    "call_id": call_id,
                                    "reason": "http_404",
                                    "from_url": primary_url,
                                    "to_url": fallback_url,
                                },
                            )
                            await invoke_hooks(
                                "after_tool_call",
                                {
                                    "tool": tool,
                                    "args": dict(retry_args),
                                    "index": idx,
                                    "call_id": call_id,
                                    "status": "ok",
                                    "duration_ms": retry_elapsed_ms,
                                    "result_chars": len(clipped),
                                    "retried": True,
                                },
                            )
                            retried_successfully = True
                        except ToolExecutionError as retry_exc:
                            merged_details: dict[str, object] = {}
                            original_details = getattr(exc, "details", None)
                            if isinstance(original_details, dict):
                                merged_details.update(original_details)
                            retry_details = getattr(retry_exc, "details", None)
                            if isinstance(retry_details, dict):
                                merged_details["retry_error"] = dict(retry_details)
                            exc = ToolExecutionError(
                                f"{exc} | retry_failed: {retry_exc}",
                                error_code=getattr(exc, "error_code", None),
                                details=merged_details,
                            )
                            await emit_lifecycle(
                                "tool_retry_failed",
                                {
                                    "tool": tool,
                                    "index": idx,
                                    "call_id": call_id,
                                    "reason": "http_404",
                                    "from_url": primary_url,
                                    "to_url": fallback_url,
                                    "error": str(retry_exc),
                                },
                            )

                tool_call_count += attempt_calls
                if retried_successfully:
                    continue

                tool_error_count += 1
                results.append(f"[{tool}] ERROR: {exc}")
                error_code = getattr(exc, "error_code", None)
                error_details = getattr(exc, "details", None)
                error_category: str | None = None
                if isinstance(error_details, dict):
                    category_value = error_details.get("category")
                    if isinstance(category_value, str) and category_value.strip():
                        error_category = category_value.strip()
                await send_event(
                    {
                        "type": "error",
                        "agent": agent_name,
                        "message": f"Tool error ({tool}): {exc}",
                        **({"error_code": error_code} if isinstance(error_code, str) and error_code else {}),
                        **({"error_category": error_category} if error_category else {}),
                    }
                )
                failed_details: dict[str, object] = {
                    "tool": tool,
                    "index": idx,
                    "call_id": call_id,
                    "status": "error",
                    "duration_ms": error_elapsed_ms,
                    "error": str(exc),
                }
                if isinstance(error_code, str) and error_code:
                    failed_details["error_code"] = error_code
                if error_category:
                    failed_details["error_category"] = error_category
                await emit_lifecycle(
                    "tool_failed",
                    failed_details,
                )
                await invoke_hooks(
                    "after_tool_call",
                    {
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "index": idx,
                        "call_id": call_id,
                        "status": "error",
                        "duration_ms": error_elapsed_ms,
                        "error": str(exc),
                        **({"error_code": error_code} if isinstance(error_code, str) and error_code else {}),
                        **({"error_category": error_category} if error_category else {}),
                    },
                )
                if should_steer_interrupt is not None and should_steer_interrupt():
                    await emit_lifecycle(
                        "steer_detected",
                        {
                            "checkpoint_stage": "tool_failed",
                            "index": idx,
                            "tool": tool,
                        },
                    )
                    await emit_lifecycle(
                        "steer_applied",
                        {
                            "checkpoint_stage": "tool_failed",
                            "index": idx,
                            "tool": tool,
                        },
                    )
                    return STEER_INTERRUPTED_MARKER

        total_elapsed_ms = int((monotonic() - started_at) * 1000)
        await emit_lifecycle(
            "tool_audit_summary",
            {
                "tool_calls": tool_call_count,
                "tool_errors": tool_error_count,
                "budget_blocked": budget_blocked_count,
                "elapsed_ms": total_elapsed_ms,
                "call_cap": tool_call_cap,
                "time_cap_seconds": tool_time_cap_seconds,
                **loop_gatekeeper.summary_payload(),
            },
        )

        return "\n\n".join(results)

    async def _execute_read_only_action(
        self,
        *,
        action: dict,
        effective_allowed_tools: set[str],
        normalize_tool_name: Callable[[str], str],
        evaluate_action: Callable[[str, dict, set[str]], tuple[dict, str | None]],
        build_execution_policy: Callable[[str], object],
        run_tool_with_policy: Callable[..., Awaitable[str]],
        invoke_spawn_subrun_tool: Callable[..., Awaitable[str]],
        model: str | None,
        max_chars: int,
        smart_truncate_enabled: bool,
        memory_add: Callable[[str, str], None],
    ) -> str | None:
        prep = prepare_action_for_execution(
            action=action,
            allowed_tools=effective_allowed_tools,
            normalize_tool_name=normalize_tool_name,
            evaluate_action=evaluate_action,
        )
        fallback_tool = action.get("tool") if isinstance(action, dict) else ""
        tool = prep.tool or (str(fallback_tool).strip() if isinstance(fallback_tool, str) else "")
        if prep.error:
            return f"[{tool}] REJECTED: {prep.error}"
        evaluated_args = prep.normalized_args
        policy = build_execution_policy(tool)
        if tool == "spawn_subrun":
            result = await invoke_spawn_subrun_tool(args=evaluated_args, model=model)
        else:
            result = await run_tool_with_policy(tool=tool, args=evaluated_args, policy=policy)
        clipped = self._smart_truncate(result, max_chars=max_chars) if smart_truncate_enabled else result[:max_chars]
        memory_add(tool, clipped)
        return f"[{tool}]\n{clipped}"
