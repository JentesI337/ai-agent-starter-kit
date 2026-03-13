from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from app.config import Settings
from app.errors import ToolExecutionError
from app.memory.learning_loop import LearningLoop
from app.reasoning.prompt.kernel_builder import PromptKernelBuilder
from app.reasoning.request_normalization import normalize_prompt_mode
from app.skills.retrieval import (
    ReliableRetrievalConfig,
    ReliableRetrievalService,
    format_retrieval_sources_for_prompt,
)
from app.tools.execution.gatekeeper import ToolCallGatekeeper, prepare_action_for_execution
from app.tools.execution.outcome_verifier import ToolOutcomeVerifier
from app.tools.registry.registry import ToolRegistry
from app.tools.telemetry import ToolTelemetry

STEER_INTERRUPTED_MARKER = "__STEER_INTERRUPTED__"

_HOOK_TIMEOUT_SECONDS = 0.5
_hook_logger = logging.getLogger("tool_execution_manager.hooks")


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
        registry: ToolRegistry | None = None,
        send_event: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._prompt_kernel_builder = PromptKernelBuilder()
        self._outcome_verifier = ToolOutcomeVerifier()
        self._telemetry = ToolTelemetry()
        self._learning_loop = LearningLoop()
        self._retrieval_service: ReliableRetrievalService | None = None
        self._retrieval_cache_key: tuple[bool, int, float, float, float] | None = None
        self._platform_summary = ""

    @staticmethod
    async def _safe_invoke_hooks(
        invoke_hooks: Callable[[str, dict], Awaitable[None]],
        hook_name: str,
        payload: dict,
    ) -> None:
        """Invoke hooks with timeout + exception isolation.

        Hooks must never crash a run or cause latency regressions.
        """
        try:
            await asyncio.wait_for(
                invoke_hooks(hook_name, payload),
                timeout=_HOOK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            _hook_logger.warning(
                "Hook '%s' timed out after %.1fs — skipped",
                hook_name,
                _HOOK_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise  # never swallow cancellation
        except Exception:
            _hook_logger.exception("Hook '%s' raised an exception — isolated", hook_name)

    def update_registry(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @staticmethod
    def _infer_required_capabilities(*, user_message: str, plan_text: str) -> set[str]:
        text = f"{user_message}\n{plan_text}".lower()
        capabilities: set[str] = set()

        if any(
            marker in text
            for marker in (
                "search on the web",
                "search the web",
                "browse the web",
                "web search",
                "find online",
                "source",
                "web",
                "internet",
            )
        ):
            capabilities.update({"web_retrieval", "knowledge_retrieval"})

        if any(marker in text for marker in ("write", "create file", "update", "edit", "patch", "implement", "fix")):
            capabilities.update({"filesystem_write", "code_modification"})

        if any(marker in text for marker in ("read", "inspect", "analyze", "grep", "find", "search in files")):
            capabilities.update({"filesystem_read", "code_search"})

        if any(marker in text for marker in (
            "execute", "run ", "ausführ", "führe", "starte", "start ",
            "command", "befehl", "shell", "terminal", "pip ", "pytest",
            "python --", "npm ", "git ", "docker ",
        )):
            capabilities.update({"command_execution", "build_and_test"})

        if any(marker in text for marker in ("code_execute", "code aus", "snippet", "sandbox")):
            capabilities.update({"command_execution", "code_sandbox"})

        if any(marker in text for marker in ("subrun", "delegate", "orchestrate", "parallel")):
            capabilities.update({"agent_delegation", "orchestration"})

        if not capabilities:
            # Detect conversational / knowledge-only prompts that need no tools.
            _conversational_markers = (
                "hallo", "hello", "hi ", "wer bist", "who are you",
                "was ist", "what is", "erkläre", "explain",
                "warum", "why", "wie funktioniert", "how does",
                "sag mir", "tell me", "hilfe", "help",
                "meinung", "opinion", "definition", "beschreibe",
                "describe", "zusammenfassung", "summary", "summarize",
                "vergleich", "compare", "unterschied", "difference",
                "respond", "answer", "reply", "introduction",
                "antworte", "einführung", "greet", "grüß",
            )
            if any(marker in text for marker in _conversational_markers):
                capabilities.add("conversational")
            else:
                capabilities.add("filesystem_read")
        return capabilities

    async def _apply_capability_preselection(
        self,
        *,
        allowed_tools: set[str],
        required_capabilities: set[str],
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
    ) -> set[str]:
        # Logging-only mode: infer which tools *would* match the capabilities
        # for telemetry, but always return all allowed tools so the LLM decides.
        registry = self._registry
        matched_tools: set[str] = set()
        if registry is not None and hasattr(registry, "filter_tools_by_capabilities"):
            matched_tools = registry.filter_tools_by_capabilities(
                candidate_tools=set(allowed_tools),
                required_capabilities=required_capabilities,
            )

        await emit_lifecycle(
            "tool_capability_preselection_logged",
            {
                "mode": "observe_only",
                "required_capabilities": sorted(required_capabilities),
                "allowed_tools": len(allowed_tools),
                "matched_tools": len(matched_tools),
                "matched_tool_names": sorted(matched_tools) if matched_tools else [],
            },
        )
        return set(allowed_tools)

    def _get_retrieval_service(self, app_settings: Settings) -> ReliableRetrievalService:
        config_key = (
            bool(getattr(app_settings, "reliable_retrieval_enabled", True)),
            max(1, int(getattr(app_settings, "reliable_retrieval_max_sources", 4))),
            max(0.0, float(getattr(app_settings, "reliable_retrieval_min_score", 0.02))),
            max(0.0, float(getattr(app_settings, "reliable_retrieval_cache_ttl_seconds", 30.0))),
            max(0.0, min(1.0, float(getattr(app_settings, "reliable_retrieval_default_source_trust", 0.8)))),
        )
        if self._retrieval_service is not None and self._retrieval_cache_key == config_key:
            return self._retrieval_service

        self._retrieval_cache_key = config_key
        self._retrieval_service = ReliableRetrievalService(
            ReliableRetrievalConfig(
                enabled=config_key[0],
                max_sources=config_key[1],
                min_score=config_key[2],
                cache_ttl_seconds=config_key[3],
                default_source_trust=config_key[4],
            )
        )
        return self._retrieval_service

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
            cap = min(configured_cap, 850)
        else:
            cap = min(configured_cap, 5500)

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
        resolve_skills_enabled_for_request: Callable[..., tuple[bool, dict[str, object]]],
        build_skills_snapshot: Callable[[], object],
        empty_skills_snapshot: Callable[[], object],
        complete_chat: Callable[[str, str, str | None], Awaitable[str]],
        complete_chat_with_tools: Callable[..., Awaitable[list[dict]]] | None = None,
        build_function_calling_tools: Callable[[set[str]], list[dict]] | None = None,
        supports_function_calling: bool = False,
        tool_selection_function_calling_enabled: bool = True,
        tool_selector_system_prompt: str,
        extract_actions: Callable[[str], tuple[list[dict], str | None]],
        repair_tool_selection_json: Callable[..., Awaitable[str]],
        approve_blocked_process_tools_if_needed: Callable[..., Awaitable[set[str]]],
        validate_actions: Callable[[list[dict], set[str]], tuple[list[dict], int]],
        augment_actions_if_needed: Callable[..., Awaitable[list[dict]]],
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

        required_capabilities = self._infer_required_capabilities(
            user_message=user_message,
            plan_text=plan_text,
        )
        effective_allowed_tools = await self._apply_capability_preselection(
            allowed_tools=effective_allowed_tools,
            required_capabilities=required_capabilities,
            emit_lifecycle=emit_lifecycle,
        )

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

        retrieval_prompt = ""
        retrieval_service = self._get_retrieval_service(app_settings)
        retrieval_result = retrieval_service.retrieve(
            query=f"{user_message}\n{plan_text}",
            snapshot=skills_snapshot,
        )
        if retrieval_result.has_sources:
            retrieval_prompt = format_retrieval_sources_for_prompt(retrieval_result)
            await emit_lifecycle(
                "retrieval_sources_selected",
                {
                    "source_count": len(retrieval_result.sources),
                    "from_cache": retrieval_result.from_cache,
                    "top_sources": [source.title for source in retrieval_result.sources[:3]],
                },
            )
        else:
            await emit_lifecycle(
                "retrieval_sources_empty",
                {
                    "from_cache": retrieval_result.from_cache,
                    "skills_selected": getattr(skills_snapshot, "selected_count", 0),
                },
            )

        effective_memory_context = memory_context
        snapshot_prompt = str(getattr(skills_snapshot, "prompt", "") or "").strip()
        if retrieval_prompt:
            effective_memory_context = f"{effective_memory_context}\n\n{retrieval_prompt}".strip()
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
                    effective_memory_context = f"{effective_memory_context}\n\n{contracted_prompt}"
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

        await self._safe_invoke_hooks(
            invoke_hooks,
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
            platform_summary=self._platform_summary,
        )

        actions = await self.select_actions_with_repair(
            complete_chat=complete_chat,
            complete_chat_with_tools=complete_chat_with_tools,
            build_function_calling_tools=build_function_calling_tools,
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
            memory_context=effective_memory_context,
            model=model,
            approve_blocked_process_tools_if_needed=approve_blocked_process_tools_if_needed,
            validate_actions=validate_actions,
            augment_actions_if_needed=augment_actions_if_needed,
            emit_lifecycle=emit_lifecycle,
            emit_tool_selection_empty=emit_tool_selection_empty,
        )
        if blocked_result is not None:
            return blocked_result

        if rejected_count > 0:
            await emit_lifecycle("tool_selection_actions_rejected", {"rejected": rejected_count})
        await emit_lifecycle("tool_selection_completed", {"actions": len(actions)})
        if not actions:
            await emit_tool_selection_empty(
                "ambiguous_input",
                {
                    "rejected_actions": rejected_count,
                },
            )
            return ""

        config = ToolExecutionConfig.from_settings(app_settings)

        return await self.run_tool_loop(
            actions=actions,
            effective_allowed_tools=effective_allowed_tools,
            config=config,
            app_settings=app_settings,
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
        result = f"{text[:head_size]}{separator}{text[-tail_size:]}"
        return result[:max_chars] if len(result) > max_chars else result

    @staticmethod
    def _build_tool_correction_hint(tool: str, error: str) -> str | None:
        """Return a human-readable correction hint for known tool argument errors."""
        if tool == "spawn_subrun" and "tool_policy" in error:
            return (
                'tool_policy must be a JSON object with optional "allow" and "deny" lists, '
                'e.g. {"allow": ["web_fetch", "read_file"], "deny": ["run_command"]}'
            )
        return None

    @staticmethod
    def _redact_secret_like_values(value: str) -> str:
        text = str(value)
        text = re.sub(
            r"(?i)(api[_-]?key|token|password|secret)\s*([:=])\s*(?:(?:\"([^\"]*)\")|(\S+))",
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
            text,
        )
        return re.sub(r"(?i)bearer\s+[a-z0-9\-_.=]+", "Bearer [REDACTED]", text)

    @staticmethod
    def _compact_result_text(value: str) -> str:
        lines = [line.rstrip() for line in str(value).splitlines()]
        compacted_lines: list[str] = []
        blank_count = 0
        for line in lines:
            if not line.strip():
                blank_count += 1
                if blank_count <= 1:
                    compacted_lines.append("")
                continue
            blank_count = 0
            compacted_lines.append(line)
        return "\n".join(compacted_lines).strip()

    @staticmethod
    def _chunk_for_persist(value: str, *, max_chars: int) -> tuple[str, int]:
        text = str(value)
        if len(text) <= max_chars:
            return text, 1

        chunk_size = max(512, min(2000, max_chars // 3))
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
        total_chunks = len(chunks)
        selected: list[tuple[int, str]] = []
        if total_chunks <= 3:
            selected = list(enumerate(chunks, start=1))
        else:
            selected = [
                (1, chunks[0]),
                (2, chunks[1]),
                (total_chunks, chunks[-1]),
            ]

        rendered = "\n\n".join(
            f"--- chunk {index}/{total_chunks} ---\n{chunk_text}" for index, chunk_text in selected
        )
        return rendered, total_chunks

    @staticmethod
    def _build_semantic_summary(value: str) -> str:
        lines = [line.strip() for line in str(value).splitlines() if line.strip()]
        if not lines:
            return ""

        head = lines[:2]
        tail: list[str] = []
        if len(lines) > 4:
            tail = [lines[-1]]
        summary_lines = head + tail
        summary = " | ".join(summary_lines)
        if len(summary) > 280:
            summary = f"{summary[:277]}..."
        return f"summary: {summary}"

    def _transform_tool_result_for_persist(
        self,
        *,
        tool: str,
        raw_result: str,
        config: ToolExecutionConfig,
        app_settings: Settings,
    ) -> tuple[str, dict[str, object]]:
        raw_text = str(raw_result or "")
        transformed = raw_text
        transform_stages: list[str] = []

        if bool(getattr(app_settings, "persist_transform_redact_secrets", True)):
            redacted = self._redact_secret_like_values(transformed)
            if redacted != transformed:
                transform_stages.append("redaction")
            transformed = redacted

        compacted = self._compact_result_text(transformed)
        if compacted != transformed:
            transform_stages.append("compaction")
        transformed = compacted

        chunk_count = 1
        if len(transformed) > config.result_max_chars:
            transformed, chunk_count = self._chunk_for_persist(
                transformed,
                max_chars=config.result_max_chars,
            )
            transform_stages.append("chunking")

            summary_line = self._build_semantic_summary(raw_text)
            if summary_line:
                transformed = f"{summary_line}\n\n{transformed}"
                transform_stages.append("semantic_summary")

        clipped = (
            self._smart_truncate(transformed, max_chars=config.result_max_chars)
            if config.smart_truncate_enabled
            else transformed[: config.result_max_chars]
        )
        if clipped != transformed and "chunking" not in transform_stages:
            transform_stages.append("chunking")

        metadata: dict[str, object] = {
            "tool": tool,
            "input_chars": len(raw_text),
            "output_chars": len(clipped),
            "transform_stages": transform_stages,
            "chunk_count": chunk_count,
            "redacted": "redaction" in transform_stages,
            "compacted": "compaction" in transform_stages,
            "chunked": "chunking" in transform_stages,
            "summarized": "semantic_summary" in transform_stages,
        }
        return clipped, metadata

    def build_tool_selector_prompt(
        self,
        *,
        allowed_tools: set[str],
        memory_context: str,
        user_message: str,
        plan_text: str,
        prompt_mode: str = "minimal",
        platform_summary: str = "",
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
            "- code_execute: code, optional language, optional timeout, optional max_output_chars, optional strategy\n"
            "- spawn_subrun: message, optional mode(run|session), optional agent_id, optional model, optional timeout_seconds, optional tool_policy={\"allow\":[\"tool_name\"],\"deny\":[\"tool_name\"]}\n"
            "- file_search: pattern, optional max_results\n"
            "- grep_search: query, optional include_pattern, optional is_regexp, optional max_results\n"
            "- list_code_usages: symbol, optional include_pattern, optional max_results\n"
            "- get_background_output/kill_background_process: job_id\n"
            "- web_fetch: url, optional max_chars\n\n"
            "Do not output markdown, explanations, [TOOL_CALL] wrappers, or any text outside the JSON object.\n"
            f"Allowed tool names are exactly: {', '.join(sorted(allowed_tools)) or 'none'}."
        )
        sections: dict[str, str] = {
            "instructions": instructions,
            "memory": memory_context,
            "task": user_message,
            "plan": plan_text,
        }
        if platform_summary:
            sections["platform_info"] = platform_summary
        kernel = self._prompt_kernel_builder.build(
            prompt_type="tool_selection",
            prompt_mode=normalize_prompt_mode(prompt_mode, default="minimal"),
            sections=sections,
        )
        return kernel.rendered

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
        build_function_calling_tools: Callable[[set[str]], list[dict]] | None = None,
        supports_function_calling: bool = False,
        function_calling_enabled: bool = False,
        allowed_tools: set[str] | None = None,
    ) -> list[dict]:
        effective_allowed_tools = set(allowed_tools or set())
        if function_calling_enabled and supports_function_calling and complete_chat_with_tools is not None:
            try:
                tool_definitions = None
                if build_function_calling_tools is not None:
                    tool_definitions = build_function_calling_tools(effective_allowed_tools)
                actions = await complete_chat_with_tools(
                    system_prompt=tool_selector_system_prompt,
                    user_prompt=tool_selector_prompt,
                    allowed_tools=sorted(effective_allowed_tools),
                    tool_definitions=tool_definitions,
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

    async def apply_action_pipeline(
        self,
        *,
        actions: list[dict],
        effective_allowed_tools: set[str],
        user_message: str,
        plan_text: str,
        memory_context: str,
        model: str | None,
        approve_blocked_process_tools_if_needed: Callable[..., Awaitable[set[str]]],
        validate_actions: Callable[[list[dict], set[str]], tuple[list[dict], int]],
        augment_actions_if_needed: Callable[..., Awaitable[list[dict]]],
        emit_lifecycle: Callable[[str, dict | None], Awaitable[None]],
        emit_tool_selection_empty: Callable[[str, dict | None], Awaitable[None]],
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

        return augmented_actions, updated_allowed_tools, rejected_count, None

    async def run_tool_loop(
        self,
        *,
        actions: list[dict],
        effective_allowed_tools: set[str],
        config: ToolExecutionConfig,
        app_settings: Settings,
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
                # --- Gate checks before parallel dispatch (Bug #2 / #3 fix) ---
                elapsed = monotonic() - started_at
                if elapsed >= tool_time_cap_seconds:
                    budget_blocked_count += len(read_only_actions)
                    results.append(
                        f"[read_only_parallel] REJECTED: tool time budget exceeded ({tool_time_cap_seconds:.1f}s)"
                    )
                    await emit_lifecycle(
                        "tool_budget_exceeded",
                        {
                            "tool": "read_only_parallel",
                            "budget_type": "time",
                            "elapsed_seconds": round(elapsed, 3),
                            "limit_seconds": tool_time_cap_seconds,
                            "skipped_count": len(read_only_actions),
                        },
                    )
                    read_only_actions = []

                if read_only_actions and should_steer_interrupt and should_steer_interrupt():
                    await emit_lifecycle(
                        "tool_parallel_read_only_steer_interrupted",
                        {"skipped_count": len(read_only_actions)},
                    )
                    read_only_actions = []

                remaining_budget = max(0, tool_call_cap - tool_call_count)
                if read_only_actions and len(read_only_actions) > remaining_budget:
                    skipped = len(read_only_actions) - remaining_budget
                    read_only_actions = read_only_actions[:remaining_budget]
                    budget_blocked_count += skipped
                    await emit_lifecycle(
                        "tool_budget_exceeded",
                        {
                            "tool": "read_only_parallel",
                            "budget_type": "call_count",
                            "used_calls": tool_call_count,
                            "limit_calls": tool_call_cap,
                            "skipped_count": skipped,
                        },
                    )

            if read_only_actions:
                gated_read_only_actions: list[dict] = []
                for ro_idx, ro_action in enumerate(read_only_actions):
                    ro_prep = prepare_action_for_execution(
                        action=ro_action,
                        allowed_tools=effective_allowed_tools,
                        normalize_tool_name=normalize_tool_name,
                        evaluate_action=evaluate_action,
                    )
                    ro_fallback = ro_action.get("tool") if isinstance(ro_action, dict) else ""
                    ro_tool = ro_prep.tool or (str(ro_fallback).strip() if isinstance(ro_fallback, str) else "")
                    if ro_prep.error:
                        results.append(f"[{ro_tool}] REJECTED: {ro_prep.error}")
                        continue
                    sig = loop_gatekeeper.build_signature(tool=ro_tool, args=ro_prep.normalized_args)
                    pre = loop_gatekeeper.before_tool_call(tool=ro_tool, signature=sig, index=ro_idx)
                    for stage, details in pre.lifecycle_events:
                        await emit_lifecycle(stage, details)
                    if pre.blocked:
                        results.append(f"[{ro_tool}] REJECTED: {pre.rejection_message}")
                        if pre.break_run:
                            break
                        continue
                    gated_read_only_actions.append(ro_action)
                read_only_actions = gated_read_only_actions

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
                            app_settings=app_settings,
                            memory_add=memory_add,
                            emit_lifecycle=emit_lifecycle,
                        )
                        for action in read_only_actions
                    ],
                    return_exceptions=True,
                )
                for ro_idx, item in enumerate(read_only_results):
                    if isinstance(item, Exception):
                        results.append(f"[read_only_parallel] ERROR: {item}")
                        tool_error_count += 1
                        tool_call_count += 1
                        continue
                    if item is None:
                        continue
                    results.append(item)
                    tool_call_count += 1
                    # H-1: update loop_gatekeeper for parallel read-only results
                    ro_tool_match = item.split("]", 1)[0].lstrip("[") if item.startswith("[") else ""
                    if ro_tool_match:
                        ro_sig = loop_gatekeeper.build_signature(tool=ro_tool_match, args={})
                        post = loop_gatekeeper.after_tool_success(
                            tool=ro_tool_match, signature=ro_sig, index=ro_idx, result=item,
                        )
                        for stage, details in post.lifecycle_events:
                            await emit_lifecycle(stage, details)
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
                correction_hint = self._build_tool_correction_hint(tool, prep.error)
                error_event: dict[str, object] = {
                    "type": "error",
                    "agent": agent_name,
                    "message": f"Tool blocked ({tool}): {prep.error}",
                }
                if correction_hint is not None:
                    error_event["correction_hint"] = correction_hint
                await send_event(error_event)
                blocked_details: dict[str, object] = {
                    "tool": tool,
                    "index": idx,
                    "call_id": call_id,
                    "error": prep.error,
                }
                if correction_hint is not None:
                    blocked_details["correction_hint"] = correction_hint
                await emit_lifecycle("tool_blocked", blocked_details)
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

            await self._safe_invoke_hooks(
                invoke_hooks,
                "before_tool_call",
                {
                    "tool": tool,
                    "args": dict(evaluated_args),
                    "index": idx,
                    "call_id": call_id,
                },
            )

            _tel_span = self._telemetry.start_span(
                tool=tool, call_id=call_id, args=dict(evaluated_args),
            )
            _tel_span_closed = False

            try:
                tool_started = monotonic()
                if tool == "spawn_subrun":
                    result = await invoke_spawn_subrun_tool(args=evaluated_args, model=model)
                else:
                    result = await run_tool_with_policy(tool=tool, args=evaluated_args, policy=policy)
                tool_call_count += 1
                tool_elapsed_ms = int((monotonic() - tool_started) * 1000)
                clipped, transform_meta = self._transform_tool_result_for_persist(
                    tool=tool,
                    raw_result=result,
                    config=config,
                    app_settings=app_settings,
                )
                await emit_lifecycle(
                    "tool_result_transformed",
                    {
                        "tool": tool,
                        "index": idx,
                        "call_id": call_id,
                        **transform_meta,
                    },
                )
                await self._safe_invoke_hooks(
                    invoke_hooks,
                    "tool_result_persist",
                    {
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "index": idx,
                        "call_id": call_id,
                        "status": "ok",
                        "result_chars": len(clipped),
                    },
                )
                memory_add(tool, clipped)
                await emit_lifecycle(
                    "tool_result_persisted",
                    {
                        "tool": tool,
                        "index": idx,
                        "call_id": call_id,
                        "result_chars": len(clipped),
                        "status": "ok",
                    },
                )
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

                # ── Outcome Verification ──────────────────────────────
                outcome = self._outcome_verifier.verify(
                    tool=tool, result=clipped, args=evaluated_args,
                )
                outcome_payload: dict[str, object] = {
                    "outcome_status": outcome.status,
                    "outcome_reason": outcome.reason,
                }
                if outcome.error_category:
                    outcome_payload["outcome_error_category"] = outcome.error_category

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
                        **outcome_payload,
                    },
                )
                await emit_lifecycle(
                    "tool_execution_detail",
                    {
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "resultPreview": clipped[:500],
                        "durationMs": tool_elapsed_ms,
                        "exitCode": 0,
                        "blocked": False,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
                await self._safe_invoke_hooks(
                    invoke_hooks,
                    "after_tool_call",
                    {
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "index": idx,
                        "call_id": call_id,
                        "status": "ok",
                        "duration_ms": tool_elapsed_ms,
                        "result_chars": len(clipped),
                        **outcome_payload,
                    },
                )
                self._telemetry.end_span(
                    _tel_span,
                    status="ok",
                    outcome_status=outcome_payload.get("outcome_status"),
                    result_chars=len(clipped),
                )
                _tel_span_closed = True
                # D-7: feed learning loop after every successful tool call
                self._learning_loop.on_tool_outcome(
                    tool=tool,
                    success=outcome.status != "failed",
                    duration_ms=tool_elapsed_ms,
                    capability=self._infer_capability_from_tool(tool),
                    args=dict(evaluated_args),
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
                        if tool_call_count + 1 >= tool_call_cap:
                            await emit_lifecycle(
                                "tool_retry_skipped_budget",
                                {
                                    "tool": tool,
                                    "index": idx,
                                    "call_id": call_id,
                                    "reason": "call_budget_exhausted",
                                    "used_calls": tool_call_count,
                                    "limit_calls": tool_call_cap,
                                },
                            )
                        else:
                            attempt_calls += 1
                            try:
                                retry_started = monotonic()
                                retry_result = await run_tool_with_policy(tool=tool, args=retry_args, policy=policy)
                                retry_elapsed_ms = int((monotonic() - retry_started) * 1000)
                                clipped, transform_meta = self._transform_tool_result_for_persist(
                                    tool=tool,
                                    raw_result=retry_result,
                                    config=config,
                                    app_settings=app_settings,
                                )
                                await emit_lifecycle(
                                    "tool_result_transformed",
                                    {
                                        "tool": tool,
                                        "index": idx,
                                        "call_id": call_id,
                                        "retried": True,
                                        **transform_meta,
                                    },
                                )
                                await self._safe_invoke_hooks(
                                    invoke_hooks,
                                    "tool_result_persist",
                                    {
                                        "tool": tool,
                                        "args": dict(retry_args),
                                        "index": idx,
                                        "call_id": call_id,
                                        "status": "ok",
                                        "result_chars": len(clipped),
                                        "retried": True,
                                    },
                                )
                                memory_add(tool, clipped)
                                await emit_lifecycle(
                                    "tool_result_persisted",
                                    {
                                        "tool": tool,
                                        "index": idx,
                                        "call_id": call_id,
                                        "result_chars": len(clipped),
                                        "status": "ok",
                                        "retried": True,
                                    },
                                )
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
                                await self._safe_invoke_hooks(
                                    invoke_hooks,
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
                                self._telemetry.end_span(
                                    _tel_span,
                                    status="ok",
                                    retried=True,
                                    result_chars=len(clipped),
                                )
                                _tel_span_closed = True
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
                    # M-10: update loop_gatekeeper after successful retry
                    post_decision = loop_gatekeeper.after_tool_success(
                        tool=tool,
                        signature=signature,
                        index=idx,
                        result=clipped,
                    )
                    for stage, details in post_decision.lifecycle_events:
                        await emit_lifecycle(stage, details)
                    continue

                # L-6: recalculate elapsed after potential retry
                error_elapsed_ms = int((monotonic() - tool_started) * 1000)
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
                await self._safe_invoke_hooks(
                    invoke_hooks,
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
                self._telemetry.end_span(
                    _tel_span,
                    status="error",
                    error_category=error_category,
                )
                _tel_span_closed = True
                # D-7: feed learning loop after every failed tool call
                self._learning_loop.on_tool_outcome(
                    tool=tool,
                    success=False,
                    duration_ms=error_elapsed_ms,
                    capability=self._infer_capability_from_tool(tool),
                    pitfall=str(exc)[:200],
                    args=dict(evaluated_args),
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
            finally:
                # F-5: ensure telemetry span is always closed, even on
                # CancelledError or unexpected BaseException.
                if not _tel_span_closed and _tel_span.is_open:
                    self._telemetry.end_span(
                        _tel_span, status="cancelled",
                    )

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

    # ------------------------------------------------------------------
    # D-7 helper: derive a rough capability tag from the tool name
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_capability_from_tool(tool: str) -> str:
        """Map tool names to high-level capability tags for the KB."""
        _map: dict[str, str] = {
            "read_file": "file_read",
            "write_file": "file_write",
            "create_file": "file_write",
            "list_dir": "file_list",
            "list_directory": "file_list",
            "run_command": "shell",
            "run_terminal_cmd": "shell",
            "execute_command": "shell",
            "spawn_subrun": "orchestration",
            "spawn_sub_agent": "orchestration",
            "web_search": "search",
            "web_fetch": "web_fetch",
            "fetch_webpage": "web_fetch",
        }
        if tool in _map:
            return _map[tool]
        # Fallback: use the tool name itself as capability
        return tool.replace("_", " ").strip()

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
        app_settings: Settings,
        memory_add: Callable[[str, str], None],
        emit_lifecycle: Callable[..., Awaitable[None]] | None = None,
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
        # M-13: emit tool_started lifecycle event
        if emit_lifecycle is not None:
            await emit_lifecycle("tool_started", {"tool": tool, "parallel_read_only": True})
        try:
            if tool == "spawn_subrun":
                result = await invoke_spawn_subrun_tool(args=evaluated_args, model=model)
            else:
                result = await run_tool_with_policy(tool=tool, args=evaluated_args, policy=policy)
        except Exception as exc:
            # M-13: emit tool_failed lifecycle event
            if emit_lifecycle is not None:
                await emit_lifecycle("tool_failed", {"tool": tool, "parallel_read_only": True, "error": str(exc)[:300]})
            raise
        temp_config = ToolExecutionConfig(
            call_cap=1,
            time_cap_seconds=1.0,
            loop_warn_threshold=1,
            loop_critical_threshold=2,
            loop_circuit_breaker_threshold=3,
            generic_repeat_enabled=True,
            ping_pong_enabled=True,
            poll_no_progress_enabled=True,
            poll_no_progress_threshold=2,
            warning_bucket_size=1,
            result_max_chars=max_chars,
            smart_truncate_enabled=smart_truncate_enabled,
            parallel_read_only_enabled=False,
        )
        clipped, _ = self._transform_tool_result_for_persist(
            tool=tool,
            raw_result=result,
            config=temp_config,
            app_settings=app_settings,
        )
        memory_add(tool, clipped)
        # M-13: emit tool_completed lifecycle event
        if emit_lifecycle is not None:
            await emit_lifecycle("tool_completed", {"tool": tool, "parallel_read_only": True, "result_chars": len(clipped), "status": "ok"})
        return f"[{tool}]\n{clipped}"
