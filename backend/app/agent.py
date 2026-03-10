from __future__ import annotations

import asyncio
import contextlib
import contextvars
import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from app.agent_runner import AgentRunner, build_unified_system_prompt
from app.config import settings
from app.contracts.tool_protocol import ToolProvider
from app.errors import GuardrailViolation, PolicyApprovalCancelledError, ToolExecutionError
from app.llm_client import LlmClient
from app.memory import MemoryStore
from app.model_routing import ModelRegistry
from app.orchestrator.events import build_lifecycle_event
from app.services.action_augmenter import ActionAugmenter
from app.services.action_parser import ActionParser
from app.services.failure_retriever import FailureRetriever
from app.services.hook_contract import resolve_hook_execution_contract
from app.services.intent_detector import IntentDetector
from app.services.long_term_memory import FailureEntry, LongTermMemoryStore
from app.services.mcp_bridge import McpBridge
from app.services.platform_info import detect_platform
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.reflection_feedback_store import ReflectionFeedbackStore, ReflectionRecord
from app.services.reflection_service import ReflectionService
from app.services.reply_shaper import ReplyShaper
from app.services.request_normalization import normalize_prompt_mode
from app.services.tool_arg_validator import ToolArgValidator
from app.services.tool_call_gatekeeper import (
    collect_policy_override_candidates,
)
from app.services.tool_execution_manager import ToolExecutionManager
from app.services.tool_registry import ToolExecutionPolicy, ToolRegistry, ToolRegistryFactory
from app.services.tool_result_context_guard import enforce_tool_result_context_budget
from app.services.tool_retry_strategy import ToolRetryStrategy
from app.services.verification_service import VerificationService
from app.skills.models import SkillSnapshot
from app.skills.service import SkillsRuntimeConfig, SkillsService
from app.state.context_reducer import ContextReducer
from app.tool_catalog import TOOL_NAME_ALIASES, TOOL_NAME_SET
from app.tool_policy import ToolPolicyDict
from app.tools import AgentTooling, find_command_safety_violation

SendEvent = Callable[[dict], Awaitable[None]]
SpawnSubrunHandler = Callable[..., Awaitable[str | dict]]
PolicyApprovalHandler = Callable[..., Awaitable[bool]]
ALLOWED_TOOLS = set(TOOL_NAME_SET)
_IMPLEMENTATION_RE = re.compile(
    r"\b(?:implement|fix|refactor|coding|bugfix|bug\s*fix|feature)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class ReplyShapeResult:
    text: str
    suppressed: bool
    reason: str | None
    removed_tokens: list[str]
    deduped_lines: int


@dataclass(frozen=True)
class IntentGateDecision:
    intent: str | None
    confidence: str
    extracted_command: str | None
    missing_slots: tuple[str, ...]


@dataclass(frozen=True)
class PromptProfile:
    system_prompt: str
    plan_prompt: str
    tool_selector_prompt: str
    tool_repair_prompt: str
    final_prompt: str



class HeadAgent:
    def __init__(
        self,
        name: str | None = None,
        role: str = "head-agent",
        client: LlmClient | None = None,
        memory: MemoryStore | None = None,
        tools: ToolProvider | None = None,
        model_registry: ModelRegistry | None = None,
        context_reducer: ContextReducer | None = None,
        spawn_subrun_handler: SpawnSubrunHandler | None = None,
        policy_approval_handler: PolicyApprovalHandler | None = None,
    ):
        self.name = name or settings.agent_name
        self.role = role
        self.prompt_profile = self._resolve_prompt_profile(role)
        self.client = client or LlmClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )

        if memory is not None:
            self.memory = memory
        else:
            persist_dir = Path(settings.memory_persist_dir)
            if not persist_dir.is_absolute():
                persist_dir = (Path(settings.workspace_root) / persist_dir).resolve()
            self.memory = MemoryStore(
                max_items_per_session=settings.memory_max_items,
                persist_dir=str(persist_dir),
            )

        self.tools = tools or AgentTooling(
            workspace_root=settings.workspace_root,
            command_timeout_seconds=settings.command_timeout_seconds,
        )
        self.model_registry = model_registry or ModelRegistry()
        self.context_reducer = context_reducer or ContextReducer()
        self.prompt_kernel_builder = PromptKernelBuilder()
        self._spawn_subrun_handler = spawn_subrun_handler
        self._policy_approval_handler = policy_approval_handler
        self.skills_service = SkillsService(
            SkillsRuntimeConfig(
                enabled=settings.skills_engine_enabled,
                skills_dir=settings.skills_dir,
                max_discovered=max(1, int(settings.skills_max_discovered)),
                max_prompt_chars=max(1000, int(settings.skills_max_prompt_chars)),
                snapshot_cache_ttl_seconds=max(0.0, float(settings.skills_snapshot_cache_ttl_seconds)),
                snapshot_cache_use_mtime=bool(settings.skills_snapshot_cache_use_mtime),
            )
        )
        self._intent = IntentDetector()
        self._intent_detector = self._intent
        self._action_parser = ActionParser()
        self._action_augmenter = ActionAugmenter(intent_detector=self._intent)
        self._reply_shaper = ReplyShaper()
        self._verification = VerificationService()
        self._reflection_service = (
            ReflectionService(
                client=self.client,
                threshold=settings.reflection_threshold,
                factual_grounding_hard_min=settings.reflection_factual_grounding_hard_min,
                tool_results_max_chars=settings.reflection_tool_results_max_chars,
                plan_max_chars=settings.reflection_plan_max_chars,
            )
            if settings.reflection_enabled
            else None
        )
        self._long_term_memory: LongTermMemoryStore | None = None
        self._long_term_memory_db_path: str | None = None
        self._reflection_feedback_store: ReflectionFeedbackStore | None = None
        self._failure_retriever: FailureRetriever | None = None
        self._refresh_long_term_memory_store()
        self._mcp_bridge: McpBridge | None = None
        self._mcp_initialized = False
        self._mcp_init_lock = asyncio.Lock()
        self._configure_lock = asyncio.Lock()  # H-6: guards configure_runtime vs concurrent run()
        self._run_lock = asyncio.Lock()  # H-6: protects _active_run_count
        self._reconfiguring = False
        self._active_run_count = 0  # H-6: tracks concurrently executing run() calls
        self._background_tasks: set[asyncio.Task] = set()  # keeps bg tasks alive (prevents GC)
        if settings.mcp_enabled and settings.mcp_servers:
            self._mcp_bridge = McpBridge(settings.mcp_servers)
        # Registry muss vor ToolExecutionManager gebaut werden, damit
        # filter_tools_by_capabilities verfügbar ist und capability preselection
        # nicht mit "registry_missing_filter" abbricht.
        self.tool_registry = self._build_tool_registry()
        self._tool_execution_manager = ToolExecutionManager(registry=self.tool_registry)
        self._retry_strategy = ToolRetryStrategy()
        self._platform = detect_platform()
        platform_summary = self._platform.summary()
        platform_summary += f"\nworkspace_root={self.tools.workspace_root}"
        self._tool_execution_manager._platform_summary = platform_summary
        self._arg_validator = ToolArgValidator(violates_command_policy=self._violates_command_policy)
        self._validate_tool_registry_dispatch()
        self._hooks: list[object] = []
        self._source_agent_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            f"source_agent_id_{id(self)}",
            default=None,
        )
        self._active_send_event_context: contextvars.ContextVar[SendEvent | None] = contextvars.ContextVar(
            f"active_send_event_{id(self)}",
            default=None,
        )
        self._active_session_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            f"active_session_id_{id(self)}",
            default=None,
        )
        self._active_request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            f"active_request_id_{id(self)}",
            default=None,
        )
        self._build_sub_agents()
        # Debug infrastructure
        self._debug_continue_event: asyncio.Event = asyncio.Event()
        self._debug_continue_event.set()  # Default: not paused
        self._debug_breakpoints: set[str] = set()
        self._debug_mode_active: bool = False

    def set_source_agent_context(self, source_agent_id: str | None):
        normalized = (source_agent_id or "").strip().lower() or None
        return self._source_agent_id_context.set(normalized)

    def reset_source_agent_context(self, token) -> None:
        self._source_agent_id_context.reset(token)

    def register_hook(self, hook: object) -> None:
        if hook not in self._hooks:
            self._hooks.append(hook)

    def _build_sub_agents(self) -> None:
        system_prompt = build_unified_system_prompt(
            role=self.role,
            plan_prompt=self.prompt_profile.plan_prompt,
            tool_hints=self.prompt_profile.tool_selector_prompt,
            final_instructions=self.prompt_profile.final_prompt,
            platform_summary=self._tool_execution_manager._platform_summary,
        )
        self._agent_runner = AgentRunner(
            client=self.client,
            memory=self.memory,
            tool_registry=self.tool_registry,
            tool_execution_manager=self._tool_execution_manager,
            context_reducer=self.context_reducer,
            system_prompt=system_prompt,
            execute_tool_fn=self._runner_execute_tool,
            allowed_tools_resolver=self._resolve_effective_allowed_tools,
            guardrail_validator=self._validate_guardrails,
            mcp_initializer=self._ensure_mcp_tools_registered,
            reflection_service=self._reflection_service,
            emit_lifecycle_fn=self._emit_lifecycle,
            intent_detector=self._intent,
            reply_shaper=self._reply_shaper,
            verification_service=self._verification,
            reflection_feedback_store=self._reflection_feedback_store,
            agent_name=self.name,
            distill_fn=self._distill_session_knowledge,
            long_term_context_fn=self._build_long_term_memory_context,
            policy_approval_fn=self._request_policy_override,
            debug_checkpoint_fn=self._debug_checkpoint,
        )

    @staticmethod
    def _matches_canary_rule(value: str, rules: list[str]) -> bool:
        normalized_value = (value or "").strip().lower()
        normalized_rules = [str(item).strip().lower() for item in (rules or []) if str(item).strip()]
        if not normalized_rules:
            return True
        if "*" in normalized_rules:
            return True
        for rule in normalized_rules:
            if rule.endswith("*") and normalized_value.startswith(rule[:-1]):
                return True
            if normalized_value == rule:
                return True
        return False

    def _resolve_skills_enabled_for_request(self, *, model_id: str) -> tuple[bool, dict[str, object]]:
        if not settings.skills_engine_enabled:
            return False, {
                "reason": "skills_engine_disabled",
                "agent": self.role,
                "model": model_id,
            }

        if not settings.skills_canary_enabled:
            return True, {
                "reason": "skills_enabled_global",
                "agent": self.role,
                "model": model_id,
            }

        agent_match = self._matches_canary_rule(self.role, settings.skills_canary_agent_ids)
        model_match = self._matches_canary_rule(model_id, settings.skills_canary_model_profiles)
        enabled = agent_match and model_match
        return enabled, {
            "reason": "skills_enabled_canary" if enabled else "skills_blocked_canary",
            "agent": self.role,
            "model": model_id,
            "agent_match": agent_match,
            "model_match": model_match,
            "canary_agent_ids": settings.skills_canary_agent_ids,
            "canary_model_profiles": settings.skills_canary_model_profiles,
        }

    @staticmethod
    def _empty_skills_snapshot() -> SkillSnapshot:
        return SkillSnapshot(
            prompt="",
            skills=(),
            discovered_count=0,
            eligible_count=0,
            selected_count=0,
            truncated=False,
        )

    def _resolve_prompt_profile(self, role: str) -> PromptProfile:
        normalized_role = (role or "").strip().lower()
        if normalized_role == "coding-agent":
            return PromptProfile(
                system_prompt=settings.coder_agent_system_prompt,
                plan_prompt=settings.coder_agent_plan_prompt,
                tool_selector_prompt=settings.coder_agent_tool_selector_prompt,
                tool_repair_prompt=settings.coder_agent_tool_repair_prompt,
                final_prompt=settings.coder_agent_final_prompt,
            )
        if normalized_role == "researcher-agent":
            return PromptProfile(
                system_prompt=settings.researcher_agent_system_prompt,
                plan_prompt=settings.researcher_agent_plan_prompt,
                tool_selector_prompt=settings.researcher_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.researcher_agent_final_prompt,
            )
        if normalized_role == "architect-agent":
            return PromptProfile(
                system_prompt=settings.architect_agent_system_prompt,
                plan_prompt=settings.architect_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.architect_agent_final_prompt,
            )
        if normalized_role == "test-agent":
            return PromptProfile(
                system_prompt=settings.test_agent_system_prompt,
                plan_prompt=settings.test_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.test_agent_final_prompt,
            )
        if normalized_role == "security-agent":
            return PromptProfile(
                system_prompt=settings.security_agent_system_prompt,
                plan_prompt=settings.head_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.security_agent_final_prompt,
            )
        if normalized_role == "doc-agent":
            return PromptProfile(
                system_prompt=settings.doc_agent_system_prompt,
                plan_prompt=settings.head_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.doc_agent_final_prompt,
            )
        if normalized_role == "refactor-agent":
            return PromptProfile(
                system_prompt=settings.refactor_agent_system_prompt,
                plan_prompt=settings.head_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.refactor_agent_final_prompt,
            )
        if normalized_role == "devops-agent":
            return PromptProfile(
                system_prompt=settings.devops_agent_system_prompt,
                plan_prompt=settings.head_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.devops_agent_final_prompt,
            )
        if normalized_role == "fintech-agent":
            return PromptProfile(
                system_prompt=settings.fintech_agent_system_prompt,
                plan_prompt=settings.fintech_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.fintech_agent_final_prompt,
            )
        if normalized_role == "healthtech-agent":
            return PromptProfile(
                system_prompt=settings.healthtech_agent_system_prompt,
                plan_prompt=settings.healthtech_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.healthtech_agent_final_prompt,
            )
        if normalized_role == "legaltech-agent":
            return PromptProfile(
                system_prompt=settings.legaltech_agent_system_prompt,
                plan_prompt=settings.legaltech_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.legaltech_agent_final_prompt,
            )
        if normalized_role == "ecommerce-agent":
            return PromptProfile(
                system_prompt=settings.ecommerce_agent_system_prompt,
                plan_prompt=settings.ecommerce_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.ecommerce_agent_final_prompt,
            )
        if normalized_role == "industrytech-agent":
            return PromptProfile(
                system_prompt=settings.industrytech_agent_system_prompt,
                plan_prompt=settings.industrytech_agent_plan_prompt,
                tool_selector_prompt=settings.head_agent_tool_selector_prompt,
                tool_repair_prompt=settings.head_agent_tool_repair_prompt,
                final_prompt=settings.industrytech_agent_final_prompt,
            )
        # review-agent intentionally uses head-agent prompts (no dedicated prompts)
        _KNOWN_FALLBACK_ROLES = {"head-agent", "review-agent"}
        if normalized_role and normalized_role not in _KNOWN_FALLBACK_ROLES:
            logging.getLogger(__name__).warning(
                "unknown_agent_role role=%s — falling back to head-agent prompts",
                normalized_role,
            )
        return PromptProfile(
            system_prompt=settings.head_agent_system_prompt,
            plan_prompt=settings.head_agent_plan_prompt,
            tool_selector_prompt=settings.head_agent_tool_selector_prompt,
            tool_repair_prompt=settings.head_agent_tool_repair_prompt,
            final_prompt=settings.head_agent_final_prompt,
        )

    def configure_runtime(self, base_url: str, model: str) -> None:
        # H-6: guard — reject reconfiguration while run() calls are in flight
        if self._active_run_count > 0:
            raise RuntimeError(
                f"configure_runtime() abgewiesen: {self._active_run_count} aktive(r) "
                "run()-Aufruf/Aufrufe. Bitte warten und erneut versuchen."
            )
        self._reconfiguring = True
        try:
            self.client = LlmClient(
                base_url=base_url,
                model=model,
            )
            self._reflection_service = (
                ReflectionService(
                    client=self.client,
                    threshold=settings.reflection_threshold,
                    factual_grounding_hard_min=settings.reflection_factual_grounding_hard_min,
                    tool_results_max_chars=settings.reflection_tool_results_max_chars,
                    plan_max_chars=settings.reflection_plan_max_chars,
                )
                if settings.reflection_enabled
                else None
            )
            self._agent_runner.client = self.client
            self._agent_runner._reflection_service = self._reflection_service
            self._agent_runner.system_prompt = build_unified_system_prompt(
                role=self.role,
                plan_prompt=self.prompt_profile.plan_prompt,
                tool_hints=self.prompt_profile.tool_selector_prompt,
                final_instructions=self.prompt_profile.final_prompt,
                platform_summary=self._tool_execution_manager._platform_summary,
            )
        finally:
            self._reconfiguring = False

    def set_spawn_subrun_handler(self, handler: SpawnSubrunHandler | None) -> None:
        self._spawn_subrun_handler = handler

    def set_policy_approval_handler(self, handler: PolicyApprovalHandler | None) -> None:
        self._policy_approval_handler = handler

    def _refresh_long_term_memory_store(self) -> None:
        def _clear_all() -> None:
            self._long_term_memory = None
            self._long_term_memory_db_path = None
            self._reflection_feedback_store = None
            self._failure_retriever = None

        if not bool(settings.long_term_memory_enabled):
            # N-2: LTM bereits deaktiviert und Stores bereits gecleart → kein Overhead.
            if self._long_term_memory is None and self._failure_retriever is None:
                return
            _clear_all()
            return

        configured_path = str(getattr(settings, "long_term_memory_db_path", "") or "").strip()
        if not configured_path:
            # N-2: kein Pfad konfiguriert und bereits gecleart → kein Overhead.
            if self._long_term_memory is None and self._failure_retriever is None:
                return
            _clear_all()
            return

        if self._long_term_memory is not None and self._long_term_memory_db_path == configured_path:
            return

        try:
            self._long_term_memory = LongTermMemoryStore(configured_path)
            self._reflection_feedback_store = ReflectionFeedbackStore(configured_path)
            self._failure_retriever = FailureRetriever(self._long_term_memory)
            self._long_term_memory_db_path = configured_path
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to initialise long-term memory store",
                exc_info=True,
            )
            _clear_all()

    def _build_long_term_memory_context(self, user_message: str) -> str:
        if self._long_term_memory is None:
            return ""

        sections: list[str] = []

        try:
            similar_failures = self._long_term_memory.search_failures(user_message, limit=2)
        except Exception:
            similar_failures = []
        if similar_failures:
            failure_lines: list[str] = [
                f"- Task: {failure.task_description[:100]} "
                f"→ Error: {failure.root_cause[:100]} "
                f"→ Fix: {failure.solution[:100]}"
                for failure in similar_failures
            ]
            sections.append("[Past failures with similar tasks]\n" + "\n".join(failure_lines))

        try:
            semantic_facts = self._long_term_memory.get_all_semantic()
        except Exception:
            semantic_facts = []
        if semantic_facts:
            preference_lines = [f"- {item.key}: {item.value}" for item in semantic_facts[:10]]
            sections.append("[Known user preferences]\n" + "\n".join(preference_lines))

        return "\n\n".join(sections).strip()

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        prompt_mode: str | None = None,
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        self._refresh_long_term_memory_store()
        # H-6: guard — refuse to start if configure_runtime() is mid-flight
        async with self._run_lock:
            if self._reconfiguring:
                raise RuntimeError("run() abgewiesen: Agent wird gerade rekonfiguriert. Bitte erneut versuchen.")
            self._active_run_count += 1

        send_event_token = self._active_send_event_context.set(send_event)
        session_id_token = self._active_session_id_context.set(session_id)
        request_id_token = self._active_request_id_context.set(request_id)
        _runner_status = "failed"
        _runner_final = ""
        try:
            _runner_final = await self._agent_runner.run(
                user_message=user_message,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                model=model,
                tool_policy=tool_policy,
                should_steer_interrupt=should_steer_interrupt,
            )
            _runner_status = "completed"
            return _runner_final
        except Exception as exc:
            if self._long_term_memory is not None:
                with contextlib.suppress(Exception):
                    self._long_term_memory.add_failure(
                        FailureEntry(
                            failure_id=request_id,
                            task_description=user_message[:500],
                            error_type=type(exc).__name__,
                            root_cause=str(exc)[:500],
                            solution=f"Review {type(exc).__name__} handling in agent run",
                            prevention=f"Add guard for {type(exc).__name__} before reaching this code path",
                            tags=[type(exc).__name__],
                        )
                    )
            await self._emit_lifecycle(
                send_event,
                stage="run_error",
                request_id=request_id,
                session_id=session_id,
                details={"error": str(exc), "error_type": type(exc).__name__},
            )
            raise
        finally:
            async with self._run_lock:
                self._active_run_count -= 1
            with contextlib.suppress(Exception):
                await self._invoke_hooks(
                    hook_name="agent_end",
                    send_event=send_event,
                    request_id=request_id,
                    session_id=session_id,
                    payload={
                        "status": _runner_status,
                        "error": None if _runner_status == "completed" else "runner_error",
                        "final_chars": len(_runner_final),
                        "model": model or self.client.model,
                    },
                )
            self._active_request_id_context.reset(request_id_token)
            self._active_session_id_context.reset(session_id_token)
            self._active_send_event_context.reset(send_event_token)

    async def _distill_session_knowledge(
        self,
        *,
        session_id: str,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_text: str,
        model: str | None,
    ) -> None:
        if self._long_term_memory is None:
            return

        # Skip distillation on early-exit paths where final_text is empty/trivial
        if not (final_text or "").strip() or len((final_text or "").strip()) < 10:
            return

        distillation_prompt = (
            "Summarize this interaction in 2-3 sentences.\n"
            "Extract key facts about the user's preferences/project.\n"
            'Return JSON: {"summary": "...", "key_facts": [{"key": "...", "value": "..."}], "tags": ["..."]}\n\n'
            f"User: {user_message[:500]}\n"
            f"Plan: {plan_text[:300]}\n"
            f"Tools: {(tool_results or '')[:300]}\n"
            f"Result: {final_text[:500]}"
        )
        raw = await self.client.complete_chat(
            "You distill knowledge.",
            distillation_prompt,
            model=model,
            temperature=0.1,
        )

        normalized_raw = str(raw or "").strip()
        if not normalized_raw:
            return

        parsed: dict[str, Any]
        try:
            parsed = json.loads(normalized_raw)
        except Exception:
            start = normalized_raw.find("{")
            end = normalized_raw.rfind("}")
            if start < 0 or end <= start:
                return
            try:
                parsed = json.loads(normalized_raw[start : end + 1])
            except Exception:
                return

        summary = str(parsed.get("summary", "") or "").strip()
        tags_raw = parsed.get("tags", [])
        tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else []

        if summary:
            self._long_term_memory.add_episodic(
                session_id=session_id,
                summary=summary,
                key_actions=[],
                outcome="success",
                tags=tags,
            )

        key_facts = parsed.get("key_facts", [])
        if not isinstance(key_facts, list):
            return
        for fact in key_facts:
            if not isinstance(fact, dict):
                continue
            key = str(fact.get("key", "") or "").strip()
            value = str(fact.get("value", "") or "").strip()
            if not key or not value:
                continue
            self._long_term_memory.add_semantic(
                key=key,
                value=value,
                confidence=0.7,
                source_sessions=[session_id],
            )

    def _validate_guardrails(self, user_message: str, session_id: str, model: str | None) -> list[dict]:
        """Run all 5 guardrail checks and return a list of check results.

        Each result is a dict with keys: name, passed, actual_value, limit, reason (optional).
        Raises GuardrailViolation on the first failing check after collecting all results.
        """
        max_msg = settings.max_user_message_length
        msg_len = len(user_message)
        stripped_len = len(user_message.strip())
        sid_len = len(session_id)
        sid_valid = bool(re.fullmatch(r"[A-Za-z0-9_-]+", session_id))
        model_len = len(model) if model else 0

        checks: list[dict] = [
            {
                "name": "message_not_empty",
                "passed": stripped_len > 0,
                "actual_value": stripped_len,
                "limit": "> 0",
                **({"reason": "Message must not be empty."} if stripped_len == 0 else {}),
            },
            {
                "name": "message_length",
                "passed": msg_len <= max_msg,
                "actual_value": msg_len,
                "limit": max_msg,
                **({"reason": f"Message exceeds max length ({max_msg})."} if msg_len > max_msg else {}),
            },
            {
                "name": "session_id_length",
                "passed": sid_len <= 120,
                "actual_value": sid_len,
                "limit": 120,
                **({"reason": "session_id too long."} if sid_len > 120 else {}),
            },
            {
                "name": "session_id_charset",
                "passed": sid_valid,
                "actual_value": "valid" if sid_valid else "invalid",
                "limit": "[A-Za-z0-9_-]",
                **({"reason": "session_id contains unsupported characters."} if not sid_valid else {}),
            },
            {
                "name": "model_name_length",
                "passed": model_len <= 120,
                "actual_value": model_len,
                "limit": 120,
                **({"reason": "model name too long."} if model_len > 120 else {}),
            },
        ]

        # Raise on the first failure (preserves original behavior)
        for check in checks:
            if not check["passed"]:
                raise GuardrailViolation(check["reason"], details={"checks": checks})

        # Layer 1: Prompt injection pattern detection (observe-only, never blocks)
        injection_patterns = [
            r"ignor(?:iere|e)\b.*(?:anweisung|instruction|prompt|regel)",
            r"(?:vergiss|forget)\b.*(?:alles|everything|all)",
            r"du bist (?:jetzt|ab sofort|nun)\b",
            r"you are now\b",
            r"act as\b",
            r"neue (?:rolle|anweisung|persona)",
            r"new (?:role|instruction|persona)",
            r"override.*(?:system|prompt|instruction)",
            r"(?:system|prompt)\s*(?:override|injection|hack)",
            r"(?:disregard|bypass)\b.*(?:instruction|rule|prompt|system)",
            r"jailbreak",
            r"(?:do not|don'?t)\s+follow\b.*(?:rule|instruction|guideline|policy)",
        ]
        msg_lower = user_message.lower()
        matched_pattern = None
        for pat in injection_patterns:
            if re.search(pat, msg_lower):
                matched_pattern = pat
                break
        injection_suspect = matched_pattern is not None
        checks.append({
            "name": "prompt_injection_suspect",
            "passed": True,  # never blocks — observe only
            "actual_value": injection_suspect,
            "limit": "observe_only",
            **({"reason": f"Injection pattern detected: {matched_pattern}"} if injection_suspect else {}),
        })

        return checks

    def _validate_tool_policy(self, tool_policy: ToolPolicyDict | None) -> None:
        if tool_policy is None:
            return
        for key in ("allow", "deny", "also_allow"):
            values = tool_policy.get(key)
            if values is None:
                continue
            if not isinstance(values, list):
                raise GuardrailViolation(f"tool_policy.{key} must be a list.")
            if len(values) > 20:
                raise GuardrailViolation(f"tool_policy.{key} too large (max 20).")
            for item in values:
                if not isinstance(item, str) or len(item.strip()) == 0 or len(item) > 80:
                    raise GuardrailViolation(f"tool_policy.{key} contains invalid tool name.")

    def _normalize_tool_set(self, values: list[str] | None) -> set[str] | None:
        if values is None:
            return None
        known_tools = self._available_tools_catalog()
        normalized: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            candidate = self._normalize_tool_name(value)
            if candidate in known_tools:
                normalized.add(candidate)
        return normalized

    def _unknown_tool_names(self, values: list[str] | None) -> list[str]:
        if values is None:
            return []
        known_tools = self._available_tools_catalog()
        unknown: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            candidate = self._normalize_tool_name(value)
            if candidate and candidate not in known_tools:
                unknown.add(candidate)
        return sorted(unknown)

    def _available_tools_catalog(self) -> set[str]:
        return set(ALLOWED_TOOLS) | set(self.tool_registry.keys())

    def _build_tool_policy_resolution_details(
        self,
        *,
        tool_policy: ToolPolicyDict | None,
        effective_allowed_tools: set[str],
    ) -> dict[str, object]:
        requested_allow_values = [
            item for item in ((tool_policy or {}).get("allow") or []) if isinstance(item, str) and item.strip()
        ]
        requested_allow = self._normalize_tool_set((tool_policy or {}).get("allow"))
        unknown_requested_allow = self._unknown_tool_names((tool_policy or {}).get("allow"))
        unknown_requested_deny = self._unknown_tool_names((tool_policy or {}).get("deny"))
        unknown_requested_also_allow = self._unknown_tool_names((tool_policy or {}).get("also_allow"))
        request_allow_ignored_unknown_only = bool(requested_allow_values) and not bool(requested_allow)

        warnings: list[str] = []
        if request_allow_ignored_unknown_only:
            warnings.append("request allowlist contains only unknown tools; ignoring it to preserve baseline tools")
        if unknown_requested_allow:
            warnings.append(f"unknown allow entries ignored: {', '.join(unknown_requested_allow)}")
        if unknown_requested_deny:
            warnings.append(f"unknown deny entries ignored: {', '.join(unknown_requested_deny)}")
        if unknown_requested_also_allow:
            warnings.append(f"unknown also_allow entries ignored: {', '.join(unknown_requested_also_allow)}")

        return {
            "allowed": sorted(effective_allowed_tools),
            "requested_allow": sorted((tool_policy or {}).get("allow", [])),
            "requested_deny": sorted((tool_policy or {}).get("deny", [])),
            "requested_also_allow": sorted((tool_policy or {}).get("also_allow", [])),
            "request_allow_ignored_unknown_only": request_allow_ignored_unknown_only,
            "unknown_requested_allow": unknown_requested_allow,
            "unknown_requested_deny": unknown_requested_deny,
            "unknown_requested_also_allow": unknown_requested_also_allow,
            "warnings": warnings,
        }

    def _resolve_effective_allowed_tools(self, tool_policy: ToolPolicyDict | None) -> set[str]:
        base_allowed = self._available_tools_catalog()

        if not bool(settings.vision_enabled):
            base_allowed.discard("analyze_image")

        config_allow = self._normalize_tool_set(settings.agent_tools_allow)
        if config_allow is not None:
            base_allowed &= config_allow

        requested_allow_values = [
            item for item in ((tool_policy or {}).get("allow") or []) if isinstance(item, str) and item.strip()
        ]
        requested_allow = self._normalize_tool_set((tool_policy or {}).get("allow"))
        if requested_allow is not None and (requested_allow or not requested_allow_values):
            base_allowed &= requested_allow

        deny_set = set()
        deny_set |= self._normalize_tool_set(settings.agent_tools_deny) or set()
        deny_set |= self._normalize_tool_set((tool_policy or {}).get("deny")) or set()

        base_allowed -= deny_set

        also_allow_set = self._normalize_tool_set((tool_policy or {}).get("also_allow")) or set()
        base_allowed |= also_allow_set - deny_set

        # M-27: apply per-agent tool policy overrides
        agents_policy = (tool_policy or {}).get("agents")
        if isinstance(agents_policy, dict):
            agent_id = (self.name or "").strip().lower()
            agent_override = agents_policy.get(agent_id)
            if isinstance(agent_override, dict):
                agent_allow = self._normalize_tool_set(agent_override.get("allow"))
                if agent_allow is not None and agent_allow:
                    base_allowed &= agent_allow
                agent_deny = self._normalize_tool_set(agent_override.get("deny"))
                if agent_deny:
                    base_allowed -= agent_deny
                agent_also_allow = self._normalize_tool_set(agent_override.get("also_allow"))
                if agent_also_allow:
                    base_allowed |= agent_also_allow - deny_set

        return base_allowed

    async def _execute_tools(
        self,
        user_message: str,
        plan_text: str,
        memory_context: str,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
        prompt_mode: str | None = None,
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        async def _emit_lifecycle_proxy(stage: str, details: dict | None = None) -> None:
            await self._emit_lifecycle(
                send_event,
                stage=stage,
                request_id=request_id,
                session_id=session_id,
                details=details,
            )

        async def _emit_tool_selection_empty_proxy(reason: str, details: dict | None = None) -> None:
            await self._emit_tool_selection_empty(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                reason=reason,
                details=details,
            )

        async def _invoke_hooks_proxy(hook_name: str, payload: dict) -> None:
            await self._invoke_hooks(
                hook_name=hook_name,
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload=payload,
            )

        async def _request_policy_override_proxy(*, tool: str, resource: str) -> bool:
            return await self._request_policy_override(
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                tool=tool,
                resource=resource,
            )

        async def _approve_blocked_process_tools_if_needed_proxy(
            *, actions: list[dict], allowed_tools: set[str]
        ) -> set[str]:
            return await self._approve_blocked_process_tools_if_needed(
                actions=actions,
                allowed_tools=allowed_tools,
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
            )

        async def _augment_actions_if_needed_proxy(
            *,
            actions: list[dict],
            user_message: str,
            plan_text: str,
            memory_context: str,
            model: str | None,
            allowed_tools: set[str],
        ) -> list[dict]:
            return await self._augment_actions_if_needed(
                actions=actions,
                user_message=user_message,
                plan_text=plan_text,
                memory_context=memory_context,
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                model=model,
                allowed_tools=allowed_tools,
            )

        async def _invoke_spawn_subrun_tool_proxy(*, args: dict, model: str | None) -> str:
            return await self._invoke_spawn_subrun_tool(
                args=args,
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                model=model,
            )

        def _memory_add_proxy(tool: str, clipped: str) -> None:
            self.memory.add(session_id, f"tool:{tool}", clipped)

        return await self._tool_execution_manager.execute(
            user_message=user_message,
            plan_text=plan_text,
            memory_context=memory_context,
            prompt_mode=prompt_mode,
            app_settings=settings,
            model=model,
            allowed_tools=allowed_tools,
            agent_name=self.name,
            request_id=request_id,
            session_id=session_id,
            client_model=self.client.model,
            skills_engine_enabled=settings.skills_engine_enabled,
            skills_canary_enabled=settings.skills_canary_enabled,
            skills_max_prompt_chars=settings.skills_max_prompt_chars,
            emit_lifecycle=_emit_lifecycle_proxy,
            emit_tool_selection_empty=_emit_tool_selection_empty_proxy,
            invoke_hooks=_invoke_hooks_proxy,
            send_event=send_event,
            resolve_skills_enabled_for_request=self._resolve_skills_enabled_for_request,
            build_skills_snapshot=self.skills_service.build_snapshot,
            empty_skills_snapshot=self._empty_skills_snapshot,
            complete_chat=self.client.complete_chat,
            complete_chat_with_tools=self.client.complete_chat_with_tools,
            build_function_calling_tools=self._build_function_calling_tools,
            supports_function_calling=self.client.supports_function_calling,
            tool_selection_function_calling_enabled=settings.tool_selection_function_calling_enabled,
            tool_selector_system_prompt=self.prompt_profile.tool_selector_prompt,
            extract_actions=self._extract_actions,
            repair_tool_selection_json=self._repair_tool_selection_json,
            approve_blocked_process_tools_if_needed=_approve_blocked_process_tools_if_needed_proxy,
            validate_actions=self._validate_actions,
            augment_actions_if_needed=_augment_actions_if_needed_proxy,
            encode_blocked_tool_result=self._encode_blocked_tool_result,
            normalize_tool_name=self._normalize_tool_name,
            evaluate_action=self._evaluate_action,
            build_execution_policy=self._build_execution_policy,
            run_tool_with_policy=self._run_tool_with_policy,
            invoke_spawn_subrun_tool=_invoke_spawn_subrun_tool_proxy,
            should_retry_web_fetch_on_404=self._should_retry_web_fetch_on_404,
            is_web_research_task=self._is_web_research_task,
            is_weather_lookup_task=self._is_weather_lookup_task,
            build_web_research_url=self._build_web_research_url,
            memory_add=_memory_add_proxy,
            should_steer_interrupt=should_steer_interrupt,
        )

    def _build_function_calling_tools(self, allowed_tools: set[str]) -> list[dict]:
        provider = getattr(self.client, "provider", "openai") or "openai"
        return self.tool_registry.build_function_calling_tools(
            allowed_tools=allowed_tools,
            provider=provider,
        )

    def _detect_intent_gate(self, user_message: str) -> IntentGateDecision:
        # Neutralised: LLM-based tool selection handles intent classification.
        # The IntentDetector instance is kept alive for ActionAugmenter convenience
        # methods (is_web_research_task, is_subrun_orchestration_task, etc.).
        return IntentGateDecision(
            intent=None,
            confidence="low",
            extracted_command=None,
            missing_slots=(),
        )

    def _looks_like_shell_command(self, candidate: str) -> bool:
        return self._intent.is_shell_command(candidate)

    def _extract_explicit_command(self, user_message: str) -> str | None:
        return self._intent.extract_command(user_message)

    async def _emit_tool_selection_empty(
        self,
        *,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
        reason: str,
        details: dict | None = None,
    ) -> None:
        payload = dict(details or {})
        payload["reason"] = reason
        await self._emit_lifecycle(
            send_event,
            stage="tool_selection_empty",
            request_id=request_id,
            session_id=session_id,
            details=payload,
        )

    def _encode_blocked_tool_result(self, *, blocked_with_reason: str, message: str) -> str:
        return f"__BLOCKED_WITH_REASON__:{json.dumps({'blocked_with_reason': blocked_with_reason, 'message': message}, ensure_ascii=False)}"

    def _parse_blocked_tool_result(self, tool_results: str | None) -> dict | None:
        if not tool_results:
            return None
        prefix = "__BLOCKED_WITH_REASON__:"
        if not tool_results.startswith(prefix):
            return None
        payload_text = tool_results[len(prefix) :].strip()
        if not payload_text:
            return None
        try:
            parsed = json.loads(payload_text)
        except Exception:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    async def _augment_actions_if_needed(
        self,
        *,
        actions: list[dict],
        user_message: str,
        plan_text: str,
        memory_context: str,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
        model: str | None,
        allowed_tools: set[str],
    ) -> list[dict]:
        async def _emit_lifecycle_proxy(stage: str, details: dict | None = None) -> None:
            await self._emit_lifecycle(
                send_event,
                stage=stage,
                request_id=request_id,
                session_id=session_id,
                details=details,
            )

        return await self._action_augmenter.augment_actions(
            actions=actions,
            user_message=user_message,
            plan_text=plan_text,
            memory_context=memory_context,
            model=model,
            allowed_tools=allowed_tools,
            complete_chat=self.client.complete_chat,
            tool_selector_system_prompt=self.prompt_profile.tool_selector_prompt,
            extract_actions=self._extract_actions,
            validate_actions=self._validate_actions,
            emit_lifecycle=_emit_lifecycle_proxy,
            is_web_research_task=self._is_web_research_task,
            build_web_research_url=self._build_web_research_url,
            is_subrun_orchestration_task=self._is_subrun_orchestration_task,
            is_file_creation_task=self._is_file_creation_task,
        )

    async def _approve_blocked_process_tools_if_needed(
        self,
        *,
        actions: list[dict],
        allowed_tools: set[str],
        send_event: SendEvent,
        request_id: str,
        session_id: str,
    ) -> set[str]:
        effective_allowed = set(allowed_tools)
        candidates = collect_policy_override_candidates(
            actions=actions,
            allowed_tools=effective_allowed,
            normalize_tool_name=self._normalize_tool_name,
        )
        for candidate in candidates:
            approved = await self._request_policy_override(
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                tool=candidate.tool,
                resource=candidate.resource,
            )
            if approved:
                effective_allowed.add(candidate.tool)

        return effective_allowed

    async def _request_policy_override(
        self,
        *,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        tool: str,
        resource: str,
    ) -> bool:
        if self._policy_approval_handler is None:
            return False

        display_text = self._build_policy_approval_display_text(tool=tool, resource=resource)
        try:
            approved = await self._policy_approval_handler(
                send_event=send_event,
                session_id=session_id,
                request_id=request_id,
                agent_name=self.name,
                tool=tool,
                resource=resource,
                display_text=display_text,
            )
        except PolicyApprovalCancelledError:
            raise
        except Exception:
            approved = False

        await self._emit_lifecycle(
            send_event,
            stage="policy_override_decision",
            request_id=request_id,
            session_id=session_id,
            details={
                "tool": tool,
                "resource": resource[:500],
                "approved": bool(approved),
            },
        )
        return bool(approved)

    def _build_policy_approval_display_text(self, *, tool: str, resource: str) -> str:
        if tool == "run_command":
            return (
                f"Agent tries to run '{resource}' but is blocked because of policy restrictions. "
                "Do you want to allow this command?"
            )
        if tool == "code_execute":
            return (
                f"Agent tries to execute sandboxed code '{resource}' but is blocked because of policy restrictions. "
                "Do you want to allow this code execution?"
            )
        if tool == "spawn_subrun":
            return (
                f"Agent tries to spawn subprocess '{resource}' but is blocked because of policy restrictions. "
                "Do you want to allow this subprocess?"
            )
        return (
            f"Agent tries to use '{tool}' with '{resource}' but is blocked because of policy restrictions. "
            "Do you want to allow it for this run?"
        )

    def _is_web_research_task(self, user_message: str) -> bool:
        return self._intent.is_web_research_task(user_message)

    def _is_subrun_orchestration_task(self, user_message: str) -> bool:
        return self._intent.is_subrun_orchestration_task(user_message)

    def _is_weather_lookup_task(self, user_message: str) -> bool:
        return self._intent.is_weather_lookup_task(user_message)

    def _should_retry_web_fetch_on_404(self, error: ToolExecutionError) -> bool:
        return self._intent.should_retry_fetch(error)

    def _has_successful_web_fetch(self, tool_results: str) -> bool:
        return self._intent.has_successful_fetch(tool_results)

    def _extract_tool_errors(self, tool_results: str, *, tool_name: str) -> list[str]:
        if not tool_results:
            return []
        pattern = re.compile(rf"\[{re.escape(tool_name)}\]\s+ERROR:\s*(.+)", re.IGNORECASE)
        errors = [match.group(1).strip() for match in pattern.finditer(tool_results)]
        return [item for item in errors if item]

    def _build_web_fetch_unavailable_reply(self, web_errors: list[str]) -> str:
        return self._intent.build_fetch_unavailable_reply(web_errors)

    def _build_web_research_url(self, user_message: str) -> str:
        return self._intent.build_search_url(user_message)

    def _is_file_creation_task(self, user_message: str) -> bool:
        return self._intent.is_file_creation_task(user_message)

    def _requires_implementation_evidence(self, *, user_message: str, synthesis_task_type: str) -> bool:
        if synthesis_task_type == "implementation":
            return True
        return self._is_file_creation_task(user_message)

    def _requires_orchestration_evidence(self, synthesis_task_type: str) -> bool:
        """Gibt True zurück wenn der Task-Typ eine erfolgreiche Subrun-Ausführung voraussetzt.
        Gilt für 'orchestration' (mode=wait, Kind war completed) und
        'orchestration_pending' / 'orchestration_failed' (freigegebene Fehlerbehandlung).
        """
        return synthesis_task_type in {"orchestration", "orchestration_failed", "orchestration_pending"}

    def _has_orchestration_evidence(self, tool_results: str | None) -> bool:
        """Prüft ob ein abgeschlossener erfolgreicher Subrun im Tool-Result belegt ist.
        Gibt False zurück wenn nur 'accepted' oder kein Subrun vorhanden.
        """
        tr = tool_results or ""
        if "spawned_subrun_id=" in tr and "subrun-complete" in tr:
            return True
        return bool("subrun_announce" in tr and "subrun-complete" in tr)

    def _has_orchestration_attempted(self, tool_results: str | None) -> bool:
        """Gibt True zurück, wenn spawn_subrun aufgerufen wurde (egal ob erfolgreich)."""
        return "spawned_subrun_id=" in (tool_results or "")

    def _has_successful_tool_output(self, tool_results: str | None, tool_name: str) -> bool:
        if not tool_results:
            return False
        pattern = re.compile(rf"\[{re.escape(tool_name)}\]\s*\n?(?!\s*ERROR:)", re.IGNORECASE)
        return bool(pattern.search(tool_results))

    def _all_tools_failed(self, tool_results: str | None) -> bool:
        """Returns True when tool_results is non-empty, contains at least one [ERROR] entry,
        and contains zero successful [OK] entries.

        Used by the all_tools_failed evidence gate to prevent the synthesizer from emitting
        fabricated success responses when every tool call was rejected or failed.
        """
        if not tool_results or not tool_results.strip():
            return False
        lowered = tool_results.lower()
        has_error = "[error]" in lowered or "] error" in lowered
        has_ok = "] ok" in lowered or "[ok]" in lowered
        return has_error and not has_ok

    def _response_acknowledges_failures(self, final_text: str) -> bool:
        """Returns True when the synthesized text contains at least one phrase that
        explicitly acknowledges a failure or an inability to complete the task.

        If the text is entirely optimistic despite all tools having failed, this returns
        False and the all_tools_failed gate replaces it with an honest summary.
        """
        lowered = (final_text or "").lower()
        acknowledgement_phrases = (
            "error",
            "fail",
            "unable",
            "could not",
            "cannot",
            "can't",
            "couldn't",
            "not able",
            "not allowed",
            "blocked",
            "policy",
            "permission",
            "denied",
            "unsuccessful",
            "not complete",
            "unfortunately",
            "did not succeed",
            "did not complete",
            "was not",
        )
        return any(phrase in lowered for phrase in acknowledgement_phrases)

    def _has_implementation_evidence(self, tool_results: str | None) -> bool:
        return any(
            self._has_successful_tool_output(tool_results, tool_name)
            for tool_name in ("write_file", "apply_patch", "run_command", "code_execute")
        )

    def _sanitize_final_response(self, final_text: str) -> str:
        return self._reply_shaper.sanitize(final_text)

    def _shape_final_response(self, final_text: str, tool_results: str | None) -> ReplyShapeResult:
        shape = self._reply_shaper.shape(
            final_text=final_text,
            tool_results=tool_results,
            tool_markers=set(self.tool_registry.keys()),
        )
        return ReplyShapeResult(
            text=shape.text,
            suppressed=shape.was_suppressed,
            reason=shape.suppression_reason,
            removed_tokens=shape.removed_tokens,
            deduped_lines=shape.dedup_lines_removed,
        )

    def _extract_actions(self, raw: str) -> tuple[list[dict], str | None]:
        actions, parse_error = self._action_parser.parse(raw)
        # CB-1: parse_error=None mit leerer Liste ist in zwei Szenarien möglich:
        #   (a) LLM hat explizit {"actions":[]} zurückgegeben → valides "keine Aktion"-Signal
        #   (b) ActionParser hat kein JSON gefunden und "{}" fabriziert → echter Parse-Fehler
        # Unterscheidung: enthält die Rohausgabe ein "{", stammt das leere Ergebnis
        # aus einem echten JSON-Objekt (Fall a). Kein "{" → Fall b → als Fehler werten.
        if parse_error is None:
            if not actions and "{" not in str(raw or ""):
                return [], "invalid_tool_json"
            return actions, None
        return actions, parse_error

    async def _repair_tool_selection_json(self, raw: str, model: str | None) -> str:
        return await self._action_parser.repair(
            raw=raw,
            model=model,
            complete_chat=self.client.complete_chat,
            system_prompt=self.prompt_profile.tool_repair_prompt,
        )

    def _extract_json_candidate(self, raw: str) -> str:
        return self._action_parser.extract_json_candidate(raw)

    def _validate_actions(self, actions: list[dict], allowed_tools: set[str]) -> tuple[list[dict], int]:
        valid_actions: list[dict] = []
        rejected = 0

        for action in actions:
            if not isinstance(action, dict):
                rejected += 1
                continue
            tool = action.get("tool")
            args = action.get("args", {})
            if not isinstance(tool, str):
                rejected += 1
                continue
            normalized_tool = self._normalize_tool_name(tool)
            if normalized_tool not in allowed_tools:
                rejected += 1
                continue
            if not isinstance(args, dict):
                rejected += 1
                continue
            valid_actions.append({"tool": normalized_tool, "args": args})

        return valid_actions, rejected

    def _build_tool_registry(self) -> ToolRegistry:
        return ToolRegistryFactory.build(
            tooling=self.tools,
            allowed_tools=None,
            command_timeout_seconds=settings.command_timeout_seconds,
            mcp_bridge=self._mcp_bridge if self._mcp_initialized else None,
        )

    def _validate_tool_registry_dispatch(self) -> None:
        missing_tooling_methods = [
            tool_name
            for tool_name in self.tool_registry
            if tool_name != "spawn_subrun" and not tool_name.startswith("mcp_") and not hasattr(self.tools, tool_name)
        ]
        missing_arg_validators = [
            tool_name
            for tool_name in self.tool_registry
            if not tool_name.startswith("mcp_") and not self._arg_validator.has_validator(tool_name)
        ]
        if missing_tooling_methods:
            raise RuntimeError(
                "Tool registry contains tools without AgentTooling implementation: "
                + ", ".join(sorted(missing_tooling_methods))
            )
        if missing_arg_validators:
            raise RuntimeError(
                "Tool registry contains tools without argument validator: " + ", ".join(sorted(missing_arg_validators))
            )

    async def _ensure_mcp_tools_registered(
        self,
        *,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
    ) -> None:
        if self._mcp_bridge is None or self._mcp_initialized:
            return

        async with self._mcp_init_lock:
            if self._mcp_initialized:
                return
            try:
                # M-8: only call initialize() if bridge has no connections yet
                # to avoid double-init leaking connections on partial failure retry
                if not self._mcp_bridge._connections:
                    await self._mcp_bridge.initialize()
                self._mcp_initialized = True
                self.tool_registry = self._build_tool_registry()
                self._validate_tool_registry_dispatch()
                # Registry neu verdrahten, damit ToolExecutionManager
                # nach MCP-Init die aktualisierten Tool-Capabilities sieht.
                self._tool_execution_manager.update_registry(self.tool_registry)
                await self._emit_lifecycle(
                    send_event,
                    stage="mcp_tools_initialized",
                    request_id=request_id,
                    session_id=session_id,
                    details={"tool_count": len(self._mcp_bridge.get_tool_specs())},
                )
            except Exception as exc:
                self._mcp_initialized = False
                await self._emit_lifecycle(
                    send_event,
                    stage="mcp_tools_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)[:400]},
                )

    def _normalize_tool_name(self, tool_name: str) -> str:
        normalized = tool_name.strip()
        if not normalized:
            return normalized
        lowered = normalized.lower()
        if lowered in TOOL_NAME_ALIASES:
            return TOOL_NAME_ALIASES[lowered]
        return lowered

    def _evaluate_action(self, tool: str, args: dict, allowed_tools: set[str]) -> tuple[dict, str | None]:
        if tool not in allowed_tools:
            return {}, "tool is not allowed by active policy"

        spec = self.tool_registry.get(tool)
        if spec is None:
            return {}, "tool is not in registry"

        normalized_args: dict[str, object] = {}
        allowed_keys = set(spec.required_args) | set(spec.optional_args)
        if set(args.keys()) - allowed_keys:
            return {}, "arguments contain unsupported fields"

        for required_name in spec.required_args:
            if required_name not in args:
                return {}, f"missing required argument '{required_name}'"
            normalized_args[required_name] = args[required_name]

        for optional_name in spec.optional_args:
            if optional_name in args:
                normalized_args[optional_name] = args[optional_name]

        validation_error = self._arg_validator.validate(tool, normalized_args)
        if validation_error:
            return {}, validation_error

        return normalized_args, None

    def _violates_command_policy(self, command: str) -> bool:
        return find_command_safety_violation(command) is not None

    def _build_execution_policy(self, tool: str) -> ToolExecutionPolicy:
        return self.tool_registry.build_execution_policy(tool)

    async def _runner_execute_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict,
        session_id: str,
        request_id: str,
    ) -> str:
        """Bridge: AgentRunner → HeadAgent tool dispatch."""
        policy = self._build_execution_policy(tool_name)
        return await self._run_tool_with_policy(tool_name, tool_args, policy)

    async def _run_tool_with_policy(self, tool: str, args: dict, policy: ToolExecutionPolicy) -> str:
        max_attempts = policy.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                invoke_tool_fn = self._invoke_tool
                if asyncio.iscoroutinefunction(invoke_tool_fn):
                    return await asyncio.wait_for(
                        invoke_tool_fn(tool, args),
                        timeout=policy.timeout_seconds,
                    )
                phase1_start = asyncio.get_event_loop().time()
                sync_result = await asyncio.wait_for(
                    asyncio.to_thread(invoke_tool_fn, tool, args),
                    timeout=policy.timeout_seconds,
                )
                if inspect.isawaitable(sync_result):
                    elapsed = asyncio.get_event_loop().time() - phase1_start
                    remaining = max(0.1, policy.timeout_seconds - elapsed)
                    return await asyncio.wait_for(sync_result, timeout=remaining)
                return sync_result
            except TimeoutError as exc:
                last_error = exc
                if attempt >= max_attempts:
                    raise ToolExecutionError(f"Tool timeout ({tool}) after {policy.timeout_seconds:.1f}s") from exc
                if policy.retry_class not in {"timeout", "transient"}:
                    raise ToolExecutionError(f"Tool timeout ({tool})") from exc
            except ToolExecutionError as exc:
                last_error = exc
                approved_retry_result = await self._retry_run_command_after_policy_approval(
                    tool=tool,
                    args=args,
                    policy=policy,
                    error=exc,
                )
                if approved_retry_result is not None:
                    return approved_retry_result
                if attempt >= max_attempts:
                    raise
                if not self._is_retryable_tool_error(exc, policy.retry_class):
                    raise
            # L-1: exponential backoff between retries
            await asyncio.sleep(min(2 ** (attempt - 1), 8))

        if isinstance(last_error, ToolExecutionError):
            raise last_error
        raise ToolExecutionError(f"Tool execution failed ({tool})")

    async def _retry_run_command_after_policy_approval(
        self,
        *,
        tool: str,
        args: dict,
        policy: ToolExecutionPolicy,
        error: ToolExecutionError,
    ) -> str | None:
        if tool != "run_command":
            return None
        if (error.error_code or "") != "command_policy_unsupported":
            return None

        command = str(args.get("command") or "").strip()
        if not command:
            return None

        send_event = self._active_send_event_context.get()
        session_id = self._active_session_id_context.get()
        request_id = self._active_request_id_context.get()
        if send_event is None or not session_id or not request_id:
            return None

        leader = self.tools.extract_command_leader(command)
        if not leader:
            return None

        approved = await self._request_policy_override(
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            tool="run_command",
            resource=command,
        )
        if not approved:
            return None

        self.tools.allow_command_leader_temporarily(leader)
        invoke_tool_fn = self._invoke_tool
        remaining_timeout = policy.timeout_seconds
        if asyncio.iscoroutinefunction(invoke_tool_fn):
            return await asyncio.wait_for(
                invoke_tool_fn(tool, args),
                timeout=remaining_timeout,
            )
        phase1_start = asyncio.get_event_loop().time()
        sync_result = await asyncio.wait_for(
            asyncio.to_thread(invoke_tool_fn, tool, args),
            timeout=remaining_timeout,
        )
        if inspect.isawaitable(sync_result):
            elapsed = asyncio.get_event_loop().time() - phase1_start
            return await asyncio.wait_for(sync_result, timeout=max(0.1, remaining_timeout - elapsed))
        return sync_result

    async def _invoke_spawn_subrun_tool(
        self,
        *,
        args: dict,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None,
    ) -> str:
        if self._spawn_subrun_handler is None:
            raise ToolExecutionError("spawn_subrun is not configured for this runtime.")

        message = str(args.get("message", "")).strip()
        if not message:
            raise ToolExecutionError("spawn_subrun requires non-empty 'message'.")

        mode = str(args.get("mode") or "wait").strip().lower() or "wait"
        agent_id = str(args.get("agent_id") or "head-agent").strip() or "head-agent"
        child_model = str(args.get("model") or model or "").strip() or None
        timeout_seconds = int(args.get("timeout_seconds") or 0)
        child_policy = args.get("tool_policy")
        source_agent_id = self._source_agent_id_context.get() or self.name

        if mode == "run" and self._is_subrun_orchestration_task(message):
            mode = "wait"

        if child_policy is not None and not isinstance(child_policy, dict):
            raise ToolExecutionError("spawn_subrun 'tool_policy' must be an object.")

        # Fix 6: pass orchestration context so the subrun knows it is a delegated task
        # and does not re-plan the entire parent goal.
        current_task_type = getattr(self, "_current_task_type", None)
        orchestration_context: dict[str, Any] | None = None
        if current_task_type in ("orchestration_pending", "orchestration_active"):
            orchestration_context = {
                "parent_task_type": current_task_type,
                "delegated_task": True,
            }

        spawn_result = await self._spawn_subrun_handler(
            parent_request_id=request_id,
            parent_session_id=session_id,
            user_message=message,
            model=child_model,
            timeout_seconds=timeout_seconds,
            tool_policy=child_policy,
            send_event=send_event,
            agent_id=agent_id,
            mode=mode,
            source_agent_id=source_agent_id,
            orchestration_context=orchestration_context,
        )

        run_id = ""
        normalized_mode = mode
        normalized_agent_id = agent_id
        delegation_scope: dict[str, Any] | None = None
        handover_contract: dict = {
            "terminal_reason": "subrun-accepted",
            "confidence": 0.0,
            "result": None,
            "synthesis_valid": None,
        }

        if isinstance(spawn_result, dict):
            run_id = str(spawn_result.get("run_id") or "").strip()
            normalized_mode = str(spawn_result.get("mode") or normalized_mode).strip().lower() or normalized_mode
            normalized_agent_id = (
                str(spawn_result.get("agent_id") or normalized_agent_id).strip() or normalized_agent_id
            )
            candidate_handover = spawn_result.get("handover")
            if isinstance(candidate_handover, dict):
                handover_contract = self._sanitize_subrun_handover_contract(candidate_handover)
            candidate_scope = spawn_result.get("delegation_scope")
            if isinstance(candidate_scope, dict):
                delegation_scope = self._sanitize_subrun_delegation_scope(
                    candidate_scope,
                    source_agent_id=self.name,
                    target_agent_id=normalized_agent_id,
                )
            # Fix 5: propagate synthesis quality from subrun result
            synthesis_valid = spawn_result.get("synthesis_valid")
            if synthesis_valid is not None:
                handover_contract["synthesis_valid"] = bool(synthesis_valid)
        else:
            run_id = str(spawn_result).strip()

        if not run_id:
            raise ToolExecutionError("spawn_subrun handler returned an empty run_id.")

        # Multi-agency: evaluate confidence decision if present in handover
        confidence_decision = handover_contract.get("confidence_decision")
        if isinstance(confidence_decision, dict):
            action = str(confidence_decision.get("action", "")).strip()
            float(confidence_decision.get("confidence", 0.0))
            reason = str(confidence_decision.get("reason", "")).strip()
            handover_contract["confidence_evaluated"] = True
            handover_contract["confidence_action"] = action
            handover_contract["confidence_reason"] = reason
            # Log the confidence evaluation for observability
            if action == "redelegate":
                handover_contract["redelegate_to"] = confidence_decision.get("selected_agent_id")
            elif action == "review":
                handover_contract["review_by"] = confidence_decision.get("selected_agent_id")
        else:
            handover_contract["confidence_evaluated"] = False

        handover_json = json.dumps(handover_contract, ensure_ascii=False)
        delegation_json = (
            f" delegation_scope={json.dumps(delegation_scope, ensure_ascii=False)}"
            if delegation_scope is not None
            else ""
        )
        return (
            f"spawned_subrun_id={run_id} mode={normalized_mode} agent_id={normalized_agent_id} "
            f"handover_contract={handover_json}{delegation_json}"
        )

    @staticmethod
    def _sanitize_subrun_handover_contract(candidate: dict[str, Any]) -> dict[str, Any]:
        terminal_reason = str(candidate.get("terminal_reason") or "subrun-accepted").strip() or "subrun-accepted"
        raw_confidence = candidate.get("confidence", 0.0)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        result_value = candidate.get("result")
        result: str | None
        result = None if result_value is None else str(result_value)[:2000]

        sanitized = {
            "terminal_reason": terminal_reason,
            "confidence": confidence,
            "result": result,
        }

        raw_questions = candidate.get("follow_up_questions")
        if isinstance(raw_questions, list):
            questions = [str(item).strip() for item in raw_questions if str(item).strip()]
            if questions:
                sanitized["follow_up_questions"] = questions[:5]
        return sanitized

    @staticmethod
    def _sanitize_subrun_delegation_scope(
        candidate: dict[str, Any],
        *,
        source_agent_id: str,
        target_agent_id: str,
    ) -> dict[str, Any]:
        return {
            "source_agent_id": str(candidate.get("source_agent_id") or source_agent_id).strip().lower()
            or source_agent_id,
            "target_agent_id": str(candidate.get("target_agent_id") or target_agent_id).strip().lower()
            or target_agent_id,
            "allowed": bool(candidate.get("allowed", False)),
            "reason": str(candidate.get("reason") or "scope_match").strip().lower() or "scope_match",
        }

    def _is_retryable_tool_error(self, error: ToolExecutionError, retry_class: str) -> bool:
        decision = self._retry_strategy.decide(
            error_text=str(error),
            retry_class=retry_class,
            attempt=0,
            max_retries=1,
        )
        return decision.should_retry

    async def _invoke_tool(self, tool: str, args: dict) -> str:
        if tool == "spawn_subrun":
            raise ToolExecutionError("spawn_subrun must be handled by _invoke_spawn_subrun_tool.")

        spec = self.tool_registry.get(tool)
        if spec is None:
            raise ToolExecutionError(f"Unknown tool: {tool}")

        tool_method = self.tool_registry.get_dispatcher(tool)
        if tool_method is None:
            tool_method = getattr(self.tools, tool, None)
        if tool_method is None:
            raise ToolExecutionError(f"No AgentTooling method registered for tool: {tool}")

        kwargs: dict[str, object] = {}
        for required_name in spec.required_args:
            if required_name not in args:
                raise ToolExecutionError(f"{tool} requires '{required_name}'.")
            kwargs[required_name] = args[required_name]
        for optional_name in spec.optional_args:
            if optional_name in args:
                kwargs[optional_name] = args[optional_name]

        try:
            if asyncio.iscoroutinefunction(tool_method):
                return await tool_method(**kwargs)
            sync_result = await asyncio.to_thread(tool_method, **kwargs)
            if inspect.isawaitable(sync_result):
                return await sync_result
            return sync_result
        except TypeError as exc:
            raise ToolExecutionError(f"{tool} invocation failed: {exc}") from exc

    async def _emit_lifecycle(
        self,
        send_event: SendEvent,
        stage: str,
        request_id: str,
        session_id: str,
        details: dict | None = None,
    ) -> None:
        if stage.startswith("debug_") and not settings.debug_mode:
            return
        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage=stage,
                details=details,
                agent=self.name,
            )
        )

    async def _debug_checkpoint(
        self,
        phase: str,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
    ) -> None:
        """Cooperative pause point. Blocks only when a breakpoint is set or the user requested pause."""
        if not self._debug_mode_active:
            return
        if phase not in self._debug_breakpoints and self._debug_continue_event.is_set():
            return

        self._debug_continue_event.clear()
        # Send breakpoint hit directly (bypass debug_ gate in _emit_lifecycle)
        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage="debug_breakpoint_hit",
                details={"phase": phase, "breakpoint_id": f"bp-{phase}"},
                agent=self.name,
            )
        )
        try:
            await asyncio.wait_for(self._debug_continue_event.wait(), timeout=300.0)
        except asyncio.TimeoutError:
            # Auto-resume after timeout to prevent indefinite blocking
            self._debug_continue_event.set()

    async def _invoke_hooks(
        self,
        *,
        hook_name: str,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
        payload: dict,
    ) -> None:
        if not self._hooks:
            return

        contract = resolve_hook_execution_contract(settings=settings, hook_name=hook_name)

        for hook in list(self._hooks):
            method = getattr(hook, hook_name, None)
            if method is None:
                continue

            try:
                started_at = monotonic()
                maybe_result = method(payload)
                if asyncio.iscoroutine(maybe_result) or inspect.isawaitable(maybe_result):
                    await asyncio.wait_for(maybe_result, timeout=max(0.001, contract.timeout_ms / 1000.0))
                await self._emit_lifecycle(
                    send_event,
                    stage="hook_invoked",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "hook": type(hook).__name__,
                        "name": hook_name,
                        "status": "ok",
                        "duration_ms": int((monotonic() - started_at) * 1000),
                        **contract.as_event_details(),
                    },
                )
            except TimeoutError as exc:
                details = {
                    "hook": type(hook).__name__,
                    "name": hook_name,
                    "status": "timeout",
                    "error": f"hook timed out after {contract.timeout_ms}ms",
                    **contract.as_event_details(),
                }
                await self._emit_lifecycle(
                    send_event,
                    stage="hook_timeout",
                    request_id=request_id,
                    session_id=session_id,
                    details=details,
                )
                if contract.failure_policy == "hard_fail":
                    raise RuntimeError(f"Hook '{hook_name}' timed out for {type(hook).__name__}") from exc
                if contract.failure_policy == "skip":
                    await self._emit_lifecycle(
                        send_event,
                        stage="hook_skipped",
                        request_id=request_id,
                        session_id=session_id,
                        details=details,
                    )
            except Exception as exc:
                details = {
                    "hook": type(hook).__name__,
                    "name": hook_name,
                    "status": "error",
                    "error": str(exc),
                    **contract.as_event_details(),
                }
                await self._emit_lifecycle(
                    send_event,
                    stage="hook_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details=details,
                )
                if contract.failure_policy == "hard_fail":
                    raise RuntimeError(f"Hook '{hook_name}' failed for {type(hook).__name__}: {exc}") from exc
                if contract.failure_policy == "skip":
                    await self._emit_lifecycle(
                        send_event,
                        stage="hook_skipped",
                        request_id=request_id,
                        session_id=session_id,
                        details=details,
                    )


class CoderAgent(HeadAgent):
    def __init__(self):
        super().__init__(name=settings.coder_agent_name, role="coding-agent")


class ReviewAgent(HeadAgent):
    def __init__(self):
        super().__init__(name=settings.review_agent_name, role="review-agent")


class ResearcherAgent(HeadAgent):
    """Research specialist — breadth-first, fact-oriented, read-only."""

    def __init__(self):
        super().__init__(name=settings.researcher_agent_name, role="researcher-agent")


class ArchitectAgent(HeadAgent):
    """Architecture specialist — plan-execute, ADR-oriented, read-only."""

    def __init__(self):
        super().__init__(name=settings.architect_agent_name, role="architect-agent")


class TestAgent(HeadAgent):
    """Test specialist — verify-first, deterministic, test-runner focused."""

    def __init__(self):
        super().__init__(name=settings.test_agent_name, role="test-agent")


class SecurityAgent(HeadAgent):
    """Security reviewer — depth-first, deterministic, read-only."""

    def __init__(self):
        super().__init__(name=settings.security_agent_name, role="security-agent")


class DocAgent(HeadAgent):
    """Documentation specialist — breadth-first, creative writing, markdown-focused."""

    def __init__(self):
        super().__init__(name=settings.doc_agent_name, role="doc-agent")


class RefactorAgent(HeadAgent):
    """Refactoring specialist — plan-execute, safe-transformation focused."""

    def __init__(self):
        super().__init__(name=settings.refactor_agent_name, role="refactor-agent")


class DevOpsAgent(HeadAgent):
    """DevOps specialist — plan-execute, infrastructure and CI/CD focused."""

    def __init__(self):
        super().__init__(name=settings.devops_agent_name, role="devops-agent")


# ---------------------------------------------------------------------------
# Industry Expert Agents
# ---------------------------------------------------------------------------


class FinTechAgent(HeadAgent):
    """FinTech specialist — compliance-aware, payment-flow, audit-trail focused."""

    def __init__(self):
        super().__init__(name=settings.fintech_agent_name, role="fintech-agent")


class HealthTechAgent(HeadAgent):
    """HealthTech specialist — HIPAA/DSGVO, HL7 FHIR, clinical-workflow focused."""

    def __init__(self):
        super().__init__(name=settings.healthtech_agent_name, role="healthtech-agent")


class LegalTechAgent(HeadAgent):
    """LegalTech specialist — DSGVO/CCPA/AI-Act, license-scanning, compliance analysis."""

    def __init__(self):
        super().__init__(name=settings.legaltech_agent_name, role="legaltech-agent")


class ECommerceAgent(HeadAgent):
    """E-Commerce specialist — catalog modeling, checkout flows, order processing."""

    def __init__(self):
        super().__init__(name=settings.ecommerce_agent_name, role="ecommerce-agent")


class IndustryTechAgent(HeadAgent):
    """IndustryTech specialist — IoT protocols, predictive maintenance, digital twins."""

    def __init__(self):
        super().__init__(name=settings.industrytech_agent_name, role="industrytech-agent")
