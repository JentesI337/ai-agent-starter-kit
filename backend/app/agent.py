from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import logging
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from time import monotonic
from typing import Any, Callable, Awaitable

from app.agents.planner_agent import PlannerAgent
from app.agents.synthesizer_agent import SynthesizerAgent
from app.agents.tool_selector_agent import ToolSelectorAgent
from app.contracts.tool_selector_runtime import ToolSelectorRuntime
from app.config import settings
from app.contracts.tool_protocol import ToolProvider
from app.contracts.schemas import PlannerInput, SynthesizerInput, ToolSelectorInput
from app.errors import GuardrailViolation, PolicyApprovalCancelledError, ToolExecutionError
from app.llm_client import LlmClient
from app.memory import MemoryStore
from app.model_routing import ModelRegistry
from app.orchestrator.events import build_lifecycle_event
from app.orchestrator.step_executors import (
    PlannerStepExecutor,
    SynthesizeStepExecutor,
    ToolStepExecutor,
)
from app.services.tool_call_gatekeeper import (
    collect_policy_override_candidates,
)
from app.services.action_parser import ActionParser
from app.services.action_augmenter import ActionAugmenter
from app.services.ambiguity_detector import AmbiguityDetector
from app.services.intent_detector import IntentDetector
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.reflection_service import ReflectionService
from app.services.reflection_feedback_store import ReflectionFeedbackStore, ReflectionRecord
from app.services.reply_shaper import ReplyShaper
from app.services.request_normalization import normalize_prompt_mode
from app.services.dynamic_temperature import DynamicTemperatureResolver
from app.services.prompt_ab_registry import PromptAbRegistry
from app.services.long_term_memory import FailureEntry, LongTermMemoryStore
from app.services.failure_retriever import FailureRetriever
from app.services.mcp_bridge import McpBridge
from app.services.tool_retry_strategy import ToolRetryStrategy
from app.services.platform_info import detect_platform
from app.services.verification_service import VerificationService
from app.services.hook_contract import resolve_hook_execution_contract
from app.services.tool_arg_validator import ToolArgValidator
from app.services.tool_execution_manager import ToolExecutionManager
from app.services.tool_registry import ToolExecutionPolicy, ToolRegistry, ToolRegistryFactory
from app.services.tool_result_context_guard import enforce_tool_result_context_budget
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
STEER_INTERRUPTED_MARKER = "__STEER_INTERRUPTED__"
_IMPLEMENTATION_RE = re.compile(
    r"\b(?:implement|fix|refactor|test(?:s|ing)?|coding|bugfix|bug\s*fix|feature)\b", re.IGNORECASE
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


class _HeadToolSelectorRuntime(ToolSelectorRuntime):
    def __init__(self, owner: HeadAgent):
        self._owner_ref: weakref.ReferenceType[HeadAgent] = weakref.ref(owner)

    async def run_tools(
        self,
        *,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        owner = self._owner_ref()
        if owner is None:
            raise RuntimeError("HeadAgent is no longer available for tool selection runtime.")
        return await owner._execute_tools(
            user_message=payload.user_message,
            plan_text=payload.plan_text,
            memory_context=payload.reduced_context,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=allowed_tools,
            prompt_mode=payload.prompt_mode,
            should_steer_interrupt=should_steer_interrupt,
        )


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
        self._ambiguity_detector = AmbiguityDetector()
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
        self._reconfiguring = False
        self._active_run_count = 0  # H-6: tracks concurrently executing run() calls
        if settings.mcp_enabled and settings.mcp_servers:
            self._mcp_bridge = McpBridge(settings.mcp_servers)
        # Registry muss vor ToolExecutionManager gebaut werden, damit
        # filter_tools_by_capabilities verfügbar ist und capability preselection
        # nicht mit "registry_missing_filter" abbricht.
        self.tool_registry = self._build_tool_registry()
        self._tool_execution_manager = ToolExecutionManager(registry=self.tool_registry)
        self._retry_strategy = ToolRetryStrategy()
        self._platform = detect_platform()
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

    def set_source_agent_context(self, source_agent_id: str | None):
        normalized = (source_agent_id or "").strip().lower() or None
        return self._source_agent_id_context.set(normalized)

    def reset_source_agent_context(self, token) -> None:
        self._source_agent_id_context.reset(token)

    def register_hook(self, hook: object) -> None:
        if hook not in self._hooks:
            self._hooks.append(hook)

    def _build_sub_agents(self) -> None:
        temperature_resolver = DynamicTemperatureResolver(
            base_temperature=SynthesizerAgent.constraints.temperature,
            overrides=settings.dynamic_temperature_overrides,
        )
        prompt_ab_registry = PromptAbRegistry(settings.prompt_ab_registry_path)

        self.planner_agent = PlannerAgent(
            client=self.client,
            system_prompt=self.prompt_profile.plan_prompt,
            failure_retriever=self._failure_retriever,
        )
        self.tool_selector_agent = ToolSelectorAgent(runtime=_HeadToolSelectorRuntime(self))
        self.synthesizer_agent = SynthesizerAgent(
            client=self.client,
            agent_name=self.name,
            emit_lifecycle_fn=self._emit_lifecycle,
            system_prompt=self.prompt_profile.final_prompt,
            temperature_resolver=temperature_resolver,
            prompt_ab_registry=prompt_ab_registry,
        )
        self.plan_step_executor = PlannerStepExecutor(execute_fn=self._execute_planner_step)
        self.tool_step_executor = ToolStepExecutor(execute_fn=self._execute_tool_step)
        self.synthesize_step_executor = SynthesizeStepExecutor(execute_fn=self._execute_synthesize_step)

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
            self.planner_agent.configure_runtime(base_url=base_url, model=model)
            self.synthesizer_agent.configure_runtime(base_url=base_url, model=model)
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
            # CB-2: planner_agent muss in ALLEN clear-Pfaden zurückgesetzt werden,
            # nicht nur im Exception-Catch-Pfad.
            if hasattr(self, "planner_agent"):
                self.planner_agent._failure_retriever = None

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
            if hasattr(self, "planner_agent"):
                self.planner_agent._failure_retriever = self._failure_retriever
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to initialise long-term memory store", exc_info=True,
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
            failure_lines: list[str] = []
            for failure in similar_failures:
                failure_lines.append(
                    (
                        f"- Task: {failure.task_description[:100]} "
                        f"→ Error: {failure.root_cause[:100]} "
                        f"→ Fix: {failure.solution[:100]}"
                    )
                )
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
        if self._reconfiguring:
            raise RuntimeError(
                "run() abgewiesen: Agent wird gerade rekonfiguriert. Bitte erneut versuchen."
            )
        self._active_run_count += 1
        status = "failed"
        error_text: str | None = None
        final_text = ""
        plan_text = ""
        tool_results = ""
        send_event_token = self._active_send_event_context.set(send_event)
        session_id_token = self._active_session_id_context.set(session_id)
        request_id_token = self._active_request_id_context.set(request_id)

        await self._emit_lifecycle(
            send_event,
            stage="run_started",
            request_id=request_id,
            session_id=session_id,
            details={"model": model or self.client.model},
        )

        try:
            self._validate_guardrails(user_message=user_message, session_id=session_id, model=model)
            self._validate_tool_policy(tool_policy)
            await self._emit_lifecycle(
                send_event,
                stage="guardrails_passed",
                request_id=request_id,
                session_id=session_id,
            )

            await self._ensure_mcp_tools_registered(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
            )

            effective_allowed_tools = self._resolve_effective_allowed_tools(tool_policy)
            policy_details = self._build_tool_policy_resolution_details(
                tool_policy=tool_policy,
                effective_allowed_tools=effective_allowed_tools,
            )
            await self._emit_lifecycle(
                send_event,
                stage="tool_policy_resolved",
                request_id=request_id,
                session_id=session_id,
                details=policy_details,
            )

            toolchain_ok, toolchain_details = self.tools.check_toolchain()
            await self._emit_lifecycle(
                send_event,
                stage="toolchain_checked",
                request_id=request_id,
                session_id=session_id,
                details=toolchain_details,
            )
            if not toolchain_ok:
                raise ToolExecutionError("Toolchain unavailable. Check workspace path or shell configuration.")

            self.memory.add(session_id, "user", user_message)
            repaired_orphans = self.memory.repair_orphaned_tool_calls(session_id)
            if repaired_orphans > 0:
                await self._emit_lifecycle(
                    send_event,
                    stage="orphaned_tool_calls_repaired",
                    request_id=request_id,
                    session_id=session_id,
                    details={"count": repaired_orphans},
                )
            sanitized_items = self.memory.sanitize_session_history(session_id)
            if sanitized_items > 0:
                await self._emit_lifecycle(
                    send_event,
                    stage="session_history_sanitized",
                    request_id=request_id,
                    session_id=session_id,
                    details={"removed_items": sanitized_items},
                )
            await self._invoke_hooks(
                hook_name="before_model_resolve",
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload={
                    "requested_model": model,
                    "default_model": self.client.model,
                    "agent": self.name,
                },
            )
            model_id = model or self.client.model
            effective_prompt_mode = normalize_prompt_mode(prompt_mode, default=settings.prompt_mode_default)
            profile = self.model_registry.resolve(model_id)
            budgets = self._step_budgets(profile.max_context)
            memory_items = self.memory.get_items(session_id)
            memory_lines = [f"{item.role}: {item.content}" for item in memory_items]
            ltm_context = self._build_long_term_memory_context(user_message)
            planning_snapshot_lines = [ltm_context] if ltm_context else None

            plan_context = self.context_reducer.reduce(
                budget_tokens=budgets["plan"],
                user_message=user_message,
                memory_lines=memory_lines,
                tool_outputs=[],
                snapshot_lines=planning_snapshot_lines,
            )
            await self._emit_lifecycle(
                send_event,
                stage="memory_updated",
                request_id=request_id,
                session_id=session_id,
                details={"memory_items": len(memory_items), "memory_chars": len(plan_context.rendered)},
            )
            await self._emit_lifecycle(
                send_event,
                stage="context_reduced",
                request_id=request_id,
                session_id=session_id,
                details={
                    "model": model_id,
                    "prompt_mode": effective_prompt_mode,
                    "max_context": profile.max_context,
                    "plan_budget": budgets["plan"],
                    "tool_budget": budgets["tool"],
                    "final_budget": budgets["final"],
                    "plan_used": plan_context.used_tokens,
                },
            )
            await self._emit_lifecycle(
                send_event,
                stage="context_segmented",
                request_id=request_id,
                session_id=session_id,
                details=self._build_context_segments(
                    phase="planning",
                    prompt_mode=effective_prompt_mode,
                    prompt_type="planning",
                    budget_tokens=budgets["plan"],
                    rendered_text=plan_context.rendered,
                    used_tokens=plan_context.used_tokens,
                    user_message=user_message,
                    memory_lines=memory_lines,
                    tool_outputs=[],
                    snapshot_lines=planning_snapshot_lines,
                    system_prompt=self.prompt_profile.plan_prompt,
                ),
            )

            if settings.clarification_protocol_enabled and effective_prompt_mode != "subagent":
                ambiguity = self._ambiguity_detector.assess(user_message, plan_context.rendered)
                threshold = max(0.0, min(1.0, float(settings.clarification_confidence_threshold)))
                if ambiguity.is_ambiguous and ambiguity.confidence < threshold:
                    if ambiguity.default_interpretation:
                        await self._emit_lifecycle(
                            send_event,
                            stage="clarification_auto_resolved",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "ambiguity_type": ambiguity.ambiguity_type,
                                "confidence": ambiguity.confidence,
                                "threshold": threshold,
                                "action": "proceed_with_default",
                                "default_interpretation": ambiguity.default_interpretation[:200],
                            },
                        )
                    else:
                        await self._emit_lifecycle(
                            send_event,
                            stage="clarification_needed",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "ambiguity_type": ambiguity.ambiguity_type,
                                "confidence": ambiguity.confidence,
                                "question": ambiguity.clarification_question,
                                "threshold": threshold,
                            },
                        )
                        await send_event(
                            {
                                "type": "clarification_needed",
                                "agent": self.name,
                                "request_id": request_id,
                                "session_id": session_id,
                                "message": ambiguity.clarification_question or "Could you clarify your request?",
                                "default_interpretation": ambiguity.default_interpretation,
                                "ambiguity_type": ambiguity.ambiguity_type,
                                "confidence": ambiguity.confidence,
                            }
                        )
                        status = "completed"
                        clarification_text = ambiguity.clarification_question or "Could you clarify your request?"
                        self.memory.add(session_id, "assistant", clarification_text)
                        return clarification_text

            await self._invoke_hooks(
                hook_name="before_prompt_build",
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload={
                    "prompt_type": "planning",
                    "model": model,
                    "prompt_mode": effective_prompt_mode,
                    "context_chars": len(plan_context.rendered),
                    "budget_tokens": budgets["plan"],
                },
            )

            await send_event(
                {
                    "type": "status",
                    "agent": self.name,
                    "message": "Analyzing your request and planning execution.",
                }
            )

            await self._emit_lifecycle(
                send_event,
                stage="planning_started",
                request_id=request_id,
                session_id=session_id,
            )
            plan_text = await self.plan_step_executor.execute(
                PlannerInput(
                    user_message=user_message,
                    reduced_context=plan_context.rendered,
                    prompt_mode=effective_prompt_mode,
                ),
                model,
            )
            await self._emit_lifecycle(
                send_event,
                stage="planning_completed",
                request_id=request_id,
                session_id=session_id,
                details={"plan_chars": len(plan_text), "iteration": 0},
            )
            plan_verification = self._verification.verify_plan(user_message=user_message, plan_text=plan_text)
            await self._emit_lifecycle(
                send_event,
                stage="verification_plan",
                request_id=request_id,
                session_id=session_id,
                details={
                    "status": plan_verification.status,
                    "reason": plan_verification.reason,
                    **plan_verification.details,
                },
            )
            semantic_plan_verification = self._verification.verify_plan_semantically(
                user_message=user_message,
                plan_text=plan_text,
            )
            await self._emit_lifecycle(
                send_event,
                stage="verification_plan_semantic",
                request_id=request_id,
                session_id=session_id,
                details={
                    "status": semantic_plan_verification.status,
                    "reason": semantic_plan_verification.reason,
                    **semantic_plan_verification.details,
                },
            )
            self.memory.add(session_id, "plan", plan_text)
            await send_event(
                {
                    "type": "agent_step",
                    "agent": self.name,
                    "step": f"Plan ready: {plan_text[:220]}",
                }
            )

            max_replan_iterations = max(1, int(settings.run_max_replan_iterations))
            max_empty_tool_replan_attempts = max(0, int(settings.run_empty_tool_replan_max_attempts))
            max_error_tool_replan_attempts = max(0, int(settings.run_error_tool_replan_max_attempts))
            empty_tool_replan_attempts_used = 0
            error_tool_replan_attempts_used = 0
            regular_replan_attempts_used = 0
            total_replan_cycles = max_replan_iterations + max_empty_tool_replan_attempts + max_error_tool_replan_attempts
            await self._emit_lifecycle(
                send_event,
                stage="terminal_wait_started",
                request_id=request_id,
                session_id=session_id,
                details={
                    "scope": "tool_phase",
                    "reason": "await_tool_terminal_state",
                },
            )
            for iteration in range(total_replan_cycles):
                tool_context_outputs = [plan_text]
                if tool_results:
                    tool_context_outputs.append(tool_results)
                tool_context = self.context_reducer.reduce(
                    budget_tokens=budgets["tool"],
                    user_message=user_message,
                    memory_lines=memory_lines,
                    tool_outputs=tool_context_outputs,
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="context_segmented",
                    request_id=request_id,
                    session_id=session_id,
                    details=self._build_context_segments(
                        phase="tool_loop",
                        prompt_mode="minimal" if effective_prompt_mode == "full" else effective_prompt_mode,
                        prompt_type="tool_selection",
                        budget_tokens=budgets["tool"],
                        rendered_text=tool_context.rendered,
                        used_tokens=tool_context.used_tokens,
                        user_message=user_message,
                        memory_lines=memory_lines,
                        tool_outputs=tool_context_outputs,
                        snapshot_lines=None,
                        system_prompt=self.prompt_profile.tool_selector_prompt,
                    ),
                )

                tool_results = await self.tool_step_executor.execute(
                    ToolSelectorInput(
                        user_message=user_message,
                        plan_text=plan_text,
                        reduced_context=tool_context.rendered,
                        prompt_mode="minimal" if effective_prompt_mode == "full" else effective_prompt_mode,
                    ),
                    session_id,
                    request_id,
                    send_event,
                    model,
                    effective_allowed_tools,
                    should_steer_interrupt,
                )

                tool_results_state = self._classify_tool_results_state(tool_results)
                if tool_results_state in {"blocked", "usable", "steer_interrupted"}:
                    break

                replan_reason = self._resolve_replan_reason(
                    tool_results_state=tool_results_state,
                    iteration=regular_replan_attempts_used,
                    max_replan_iterations=max_replan_iterations,
                    empty_tool_replan_attempts_used=empty_tool_replan_attempts_used,
                    max_empty_tool_replan_attempts=max_empty_tool_replan_attempts,
                    error_tool_replan_attempts_used=error_tool_replan_attempts_used,
                    max_error_tool_replan_attempts=max_error_tool_replan_attempts,
                )
                if replan_reason is None:
                    await self._emit_lifecycle(
                        send_event,
                        stage="replanning_exhausted",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "iteration": iteration + 1,
                            "tool_results_state": tool_results_state,
                            "empty_tool_replan_attempts_used": empty_tool_replan_attempts_used,
                            "max_empty_tool_replan_attempts": max_empty_tool_replan_attempts,
                            "error_tool_replan_attempts_used": error_tool_replan_attempts_used,
                            "max_error_tool_replan_attempts": max_error_tool_replan_attempts,
                        },
                    )
                    break
                if replan_reason == "tool_selection_empty_replan":
                    empty_tool_replan_attempts_used += 1
                if replan_reason == "tool_selection_error_replan":
                    error_tool_replan_attempts_used += 1
                if replan_reason == "tool_results_invalidated_plan":
                    regular_replan_attempts_used += 1

                await self._emit_lifecycle(
                    send_event,
                    stage="replanning_started",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "iteration": iteration + 1,
                        "reason": replan_reason,
                        "tool_results_state": tool_results_state,
                        "empty_tool_replan_attempts_used": empty_tool_replan_attempts_used,
                        "max_empty_tool_replan_attempts": max_empty_tool_replan_attempts,
                        "error_tool_replan_attempts_used": error_tool_replan_attempts_used,
                        "max_error_tool_replan_attempts": max_error_tool_replan_attempts,
                    },
                )
                replan_context = self.context_reducer.reduce(
                    budget_tokens=budgets["plan"],
                    user_message=user_message,
                    memory_lines=memory_lines,
                    tool_outputs=[plan_text, tool_results] if tool_results else [plan_text],
                )
                replan_user_message = user_message
                if settings.plan_root_cause_replan_enabled:
                    replan_user_message = self._build_root_cause_replan_prompt(
                        user_message=user_message,
                        previous_plan=plan_text,
                        tool_results=tool_results,
                    )
                plan_text = await self.plan_step_executor.execute(
                    PlannerInput(
                        user_message=replan_user_message,
                        reduced_context=replan_context.rendered,
                        prompt_mode="minimal" if effective_prompt_mode == "full" else effective_prompt_mode,
                    ),
                    model,
                )
                self.memory.add(session_id, "plan", plan_text)
                await self._emit_lifecycle(
                    send_event,
                    stage="replanning_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "iteration": iteration + 1,
                        "plan_chars": len(plan_text),
                        "reason": replan_reason,
                        "root_cause_replan": bool(settings.plan_root_cause_replan_enabled),
                    },
                )

            await self._emit_lifecycle(
                send_event,
                stage="terminal_wait_completed",
                request_id=request_id,
                session_id=session_id,
                details={
                    "scope": "tool_phase",
                    "terminal_stage": "tool_audit_summary",
                    "replan_cycles": total_replan_cycles,
                    "empty_tool_replan_attempts_used": empty_tool_replan_attempts_used,
                    "max_empty_tool_replan_attempts": max_empty_tool_replan_attempts,
                    "error_tool_replan_attempts_used": error_tool_replan_attempts_used,
                    "max_error_tool_replan_attempts": max_error_tool_replan_attempts,
                },
            )
            tool_result_verification = self._verification.verify_tool_result(
                plan_text=plan_text,
                tool_results=tool_results,
            )
            await self._emit_lifecycle(
                send_event,
                stage="verification_tool_result",
                request_id=request_id,
                session_id=session_id,
                details={
                    "status": tool_result_verification.status,
                    "reason": tool_result_verification.reason,
                    **tool_result_verification.details,
                },
            )

            blocked_payload = self._parse_blocked_tool_result(tool_results)
            if blocked_payload is not None:
                final_text = blocked_payload.get("message") or "I need one required detail before I can continue."
                final_verification = self._verification.verify_final(user_message=user_message, final_text=final_text)
                await self._emit_lifecycle(
                    send_event,
                    stage="verification_final",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "status": final_verification.status,
                        "reason": final_verification.reason,
                        **final_verification.details,
                    },
                )
                await send_event(
                    {
                        "type": "final",
                        "agent": self.name,
                        "message": final_text,
                    }
                )
                self.memory.add(session_id, "assistant", final_text)
                await self._emit_lifecycle(
                    send_event,
                    stage="run_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "response_chars": len(final_text),
                        "fallback": "blocked_with_reason",
                        "blocked_with_reason": blocked_payload.get("blocked_with_reason", "blocked"),
                    },
                )
                status = "completed"
                return final_text

            if self._is_steer_interrupted(tool_results):
                interrupted_message = "Run interrupted due to newer input (steer). Processing latest message now."
                final_verification = self._verification.verify_final(
                    user_message=user_message,
                    final_text=interrupted_message,
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="verification_final",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "status": final_verification.status,
                        "reason": final_verification.reason,
                        **final_verification.details,
                    },
                )
                self.memory.add(session_id, "assistant", interrupted_message)
                await send_event(
                    {
                        "type": "status",
                        "agent": self.name,
                        "message": interrupted_message,
                    }
                )
                await send_event(
                    {
                        "type": "final",
                        "agent": self.name,
                        "message": interrupted_message,
                        "interrupted": True,
                    }
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="response_emitted",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "response_chars": len(interrupted_message),
                        "interrupted": True,
                        "reason": "steer",
                    },
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="run_interrupted",
                    request_id=request_id,
                    session_id=session_id,
                    details={"reason": "steer"},
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="run_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "steer_interrupt": True,
                        "superseded_by_new_input": True,
                        "response_chars": len(interrupted_message),
                    },
                )
                status = "completed"
                return interrupted_message

            if self._is_web_research_task(user_message) and not self._has_successful_web_fetch(tool_results or ""):
                web_errors = self._extract_tool_errors(tool_results or "", tool_name="web_search")
                web_errors.extend(self._extract_tool_errors(tool_results or "", tool_name="web_fetch"))
                await self._emit_lifecycle(
                    send_event,
                    stage="web_research_sources_unavailable",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error_count": len(web_errors)},
                )
                final_text = self._build_web_fetch_unavailable_reply(web_errors)
                final_verification = self._verification.verify_final(user_message=user_message, final_text=final_text)
                await self._emit_lifecycle(
                    send_event,
                    stage="verification_final",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "status": final_verification.status,
                        "reason": final_verification.reason,
                        **final_verification.details,
                    },
                )
                await send_event(
                    {
                        "type": "final",
                        "agent": self.name,
                        "message": final_text,
                    }
                )
                self.memory.add(session_id, "assistant", final_text)
                await self._emit_lifecycle(
                    send_event,
                    stage="run_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"response_chars": len(final_text), "fallback": "web_search_unavailable"},
                )
                status = "completed"
                return final_text

            await send_event(
                {
                    "type": "agent_step",
                    "agent": self.name,
                    "step": "Reviewing results and building final response",
                }
            )

            if settings.tool_result_context_guard_enabled and tool_results:
                guarded_tool_results, guard_result = enforce_tool_result_context_budget(
                    tool_results=tool_results,
                    context_window_tokens=profile.max_context,
                    context_input_headroom_ratio=settings.tool_result_context_headroom_ratio,
                    single_tool_result_share=settings.tool_result_single_share,
                )
                if guard_result.modified:
                    tool_results = guarded_tool_results
                    await self._emit_lifecycle(
                        send_event,
                        stage="tool_result_context_guard_applied",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "original_chars": guard_result.original_chars,
                            "reduced_chars": guard_result.reduced_chars,
                            "reason": guard_result.reason,
                        },
                    )

            final_context = self.context_reducer.reduce(
                budget_tokens=budgets["final"],
                user_message=user_message,
                memory_lines=memory_lines,
                tool_outputs=[tool_results] if tool_results else [],
                snapshot_lines=[f"plan: {plan_text[:500]}"] if plan_text else None,
            )
            final_snapshot_lines = [f"plan: {plan_text[:500]}"] if plan_text else None
            await self._emit_lifecycle(
                send_event,
                stage="context_segmented",
                request_id=request_id,
                session_id=session_id,
                details=self._build_context_segments(
                    phase="synthesis",
                    prompt_mode=effective_prompt_mode,
                    prompt_type="synthesis",
                    budget_tokens=budgets["final"],
                    rendered_text=final_context.rendered,
                    used_tokens=final_context.used_tokens,
                    user_message=user_message,
                    memory_lines=memory_lines,
                    tool_outputs=[tool_results] if tool_results else [],
                    snapshot_lines=final_snapshot_lines,
                    system_prompt=self.prompt_profile.final_prompt,
                ),
            )
            synthesis_task_type = self._resolve_synthesis_task_type(
                user_message=user_message,
                tool_results=tool_results or "",
            )

            await self._invoke_hooks(
                hook_name="before_prompt_build",
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload={
                    "prompt_type": "synthesize",
                    "model": model,
                    "prompt_mode": effective_prompt_mode,
                    "context_chars": len(final_context.rendered),
                    "budget_tokens": budgets["final"],
                    "task_type": synthesis_task_type,
                },
            )

            final_text = await self.synthesize_step_executor.execute(
                SynthesizerInput(
                    user_message=user_message,
                    plan_text=plan_text,
                    tool_results=tool_results or "",
                    reduced_context=final_context.rendered,
                    prompt_mode=effective_prompt_mode,
                    task_type=synthesis_task_type,
                ),
                session_id,
                request_id,
                send_event,
                model,
            )
            reflection_passes = max(0, int(self.synthesizer_agent.constraints.reflection_passes))
            if reflection_passes > 0 and self._reflection_service is not None and len((final_text or "").strip()) >= 8:
                for reflection_pass in range(reflection_passes):
                    try:
                        try:
                            verdict = await self._reflection_service.reflect(
                                user_message=user_message,
                                plan_text=plan_text,
                                tool_results=tool_results or "",
                                final_answer=final_text,
                                model=model,
                                task_type=synthesis_task_type,
                            )
                        except TypeError as inner_exc:
                            message = str(inner_exc)
                            if "task_type" not in message:
                                raise
                            verdict = await self._reflection_service.reflect(
                                user_message=user_message,
                                plan_text=plan_text,
                                tool_results=tool_results or "",
                                final_answer=final_text,
                                model=model,
                            )
                    except Exception as exc:
                        await self._emit_lifecycle(
                            send_event,
                            stage="reflection_failed",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "pass": reflection_pass + 1,
                                "error": str(exc),
                            },
                        )
                        break
                    await self._emit_lifecycle(
                        send_event,
                        stage="reflection_completed",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "pass": reflection_pass + 1,
                            "score": verdict.score,
                            "goal_alignment": verdict.goal_alignment,
                            "completeness": verdict.completeness,
                            "factual_grounding": verdict.factual_grounding,
                            "issues": verdict.issues[:3],
                            "should_retry": verdict.should_retry,
                            "hard_factual_fail": verdict.hard_factual_fail,
                        },
                    )
                    if self._reflection_feedback_store is not None:
                        self._reflection_feedback_store.store(
                            ReflectionRecord(
                                record_id=f"{request_id}-reflection-{reflection_pass + 1}",
                                session_id=session_id,
                                request_id=request_id,
                                task_type=synthesis_task_type,
                                score=verdict.score,
                                goal_alignment=verdict.goal_alignment,
                                completeness=verdict.completeness,
                                factual_grounding=verdict.factual_grounding,
                                issues=list(verdict.issues),
                                suggested_fix=verdict.suggested_fix,
                                model_id=(model or settings.llm_model),
                                prompt_variant=self.synthesizer_agent.last_prompt_variant_id,
                                retry_triggered=verdict.should_retry,
                                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                            )
                        )
                    if not verdict.should_retry:
                        break

                    feedback_lines = [issue for issue in verdict.issues if issue]
                    if verdict.suggested_fix:
                        feedback_lines.append(f"Suggested fix: {verdict.suggested_fix}")
                    reflection_feedback = "\n".join(feedback_lines).strip() or "No specific issues provided."

                    final_text = await self.synthesize_step_executor.execute(
                        SynthesizerInput(
                            user_message=user_message,
                            plan_text=plan_text,
                            tool_results=(tool_results or "") + f"\n\n[REFLECTION FEEDBACK]\n{reflection_feedback}",
                            reduced_context=final_context.rendered,
                            prompt_mode=effective_prompt_mode,
                            task_type=synthesis_task_type,
                        ),
                        session_id,
                        request_id,
                        send_event,
                        model,
                    )
            elif reflection_passes > 0 and len((final_text or "").strip()) < 8:
                await self._emit_lifecycle(
                    send_event,
                    stage="reflection_skipped",
                    request_id=request_id,
                    session_id=session_id,
                    details={"reason": "final_too_short", "final_chars": len((final_text or "").strip())},
                )
            # L-5: run evidence gates BEFORE shaping to avoid wasted shaping work
            if self._requires_implementation_evidence(
                user_message=user_message,
                synthesis_task_type=synthesis_task_type,
            ) and not self._has_implementation_evidence(tool_results):
                await self._emit_lifecycle(
                    send_event,
                    stage="implementation_evidence_missing",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "task_type": synthesis_task_type,
                        "required_evidence_tools": ["write_file", "apply_patch", "run_command", "code_execute"],
                    },
                )
                final_text = (
                    "I could not complete the implementation in this run because no code-edit or command-execution "
                    "step succeeded. Please allow the required tools (for example `write_file`, `apply_patch`, "
                    "`run_command`, or `code_execute`) and retry."
                )

            await self._emit_lifecycle(
                send_event,
                stage="reply_shaping_started",
                request_id=request_id,
                session_id=session_id,
                details={"input_chars": len(final_text)},
            )
            shape_result = self._shape_final_response(final_text, tool_results)
            if (
                shape_result.removed_tokens
                or shape_result.deduped_lines > 0
                or shape_result.text != final_text
                or shape_result.suppressed
            ):
                await self._emit_lifecycle(
                    send_event,
                    stage="reply_shaping_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "original_chars": len(final_text),
                        "shaped_chars": len(shape_result.text),
                        "suppressed": shape_result.suppressed,
                        "reason": shape_result.reason,
                        "removed_tokens": shape_result.removed_tokens,
                        "deduped_lines": shape_result.deduped_lines,
                    },
                )
            final_text = shape_result.text

            # Orchestration Evidence Gate: verhindert, dass fabrizierte Erfolgsmeldungen
            # den Nutzer täuschen, wenn ein Subrun nie erfolgreich abgeschlossen wurde.
            # Analoges Muster zum implementation_evidence_missing Gate.
            if synthesis_task_type == "orchestration" and not self._has_orchestration_evidence(tool_results):
                attempted = self._has_orchestration_attempted(tool_results)
                await self._emit_lifecycle(
                    send_event,
                    stage="orchestration_evidence_missing",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "task_type": synthesis_task_type,
                        "subrun_attempted": attempted,
                        "expected_terminal_reason": "subrun-complete",
                    },
                )
                if attempted:
                    final_text = (
                        "The delegated subrun did not complete successfully. "
                        "No confirmed delegation outcome is available. "
                        "Check the subrun status and retry with `mode=\"wait\"` for synchronous delegation."
                    )
                else:
                    final_text = (
                        "No subrun was executed for this orchestration request. "
                        "The plan did not result in a `spawn_subrun` tool call. "
                        "Please verify the orchestration intent and retry."
                    )
            final_verification = self._verification.verify_final(user_message=user_message, final_text=final_text)
            await self._emit_lifecycle(
                send_event,
                stage="verification_final",
                request_id=request_id,
                session_id=session_id,
                details={
                    "status": final_verification.status,
                    "reason": final_verification.reason,
                    **final_verification.details,
                },
            )
            if not final_verification.ok:
                final_text = "No output generated."

            if shape_result.suppressed:
                suppressed_text = final_text or f"Reply suppressed: {shape_result.reason or 'suppressed'}"
                await self._emit_lifecycle(
                    send_event,
                    stage="reply_suppressed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"reason": shape_result.reason or "suppressed"},
                )
                self.memory.add(session_id, "assistant", suppressed_text)
                await send_event(
                    {
                        "type": "final",
                        "agent": self.name,
                        "message": suppressed_text,
                        "suppressed": True,
                    }
                )
            else:
                await self._invoke_hooks(
                    hook_name="before_transcript_append",
                    send_event=send_event,
                    request_id=request_id,
                    session_id=session_id,
                    payload={
                        "role": "assistant",
                        "content_chars": len(final_text or ""),
                        "status": status,
                    },
                )
                self.memory.add(session_id, "assistant", final_text or "No output generated.")
                await send_event(
                    {
                        "type": "final",
                        "agent": self.name,
                        "message": final_text or "No output generated.",
                    }
                )
            await self._emit_lifecycle(
                send_event,
                stage="run_completed",
                request_id=request_id,
                session_id=session_id,
            )
            status = "completed"
            return final_text
        except Exception as exc:
            error_text = str(exc)
            if settings.failure_journal_enabled and self._long_term_memory is not None:
                try:
                    self._long_term_memory.add_failure(
                        FailureEntry(
                            failure_id=request_id,
                            task_description=user_message[:500],
                            error_type=type(exc).__name__,
                            root_cause=error_text[:500],
                            solution=f"Review {type(exc).__name__} handling in agent run",
                            prevention=f"Add guard for {type(exc).__name__} before reaching this code path",
                            tags=[type(exc).__name__],
                        )
                    )
                except Exception:
                    pass
            raise
        finally:
            if (
                status == "completed"
                and settings.session_distillation_enabled
                and self._long_term_memory is not None
            ):
                try:
                    await self._distill_session_knowledge(
                        session_id=session_id,
                        user_message=user_message,
                        plan_text=plan_text,
                        tool_results=tool_results,
                        final_text=final_text,
                        model=model,
                    )
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Session distillation failed for session %s", session_id, exc_info=True,
                    )
            try:
                await self._invoke_hooks(
                    hook_name="agent_end",
                    send_event=send_event,
                    request_id=request_id,
                    session_id=session_id,
                    payload={
                        "status": status,
                        "error": error_text,
                        "final_chars": len(final_text),
                        "model": model or self.client.model,
                    },
                )
            except Exception:
                pass
            self._active_request_id_context.reset(request_id_token)
            self._active_session_id_context.reset(session_id_token)
            self._active_send_event_context.reset(send_event_token)
            self._active_run_count -= 1  # H-6: release run slot

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
            "Return JSON: {\"summary\": \"...\", \"key_facts\": [{\"key\": \"...\", \"value\": \"...\"}], \"tags\": [\"...\"]}\n\n"
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

    async def _execute_planner_step(self, payload: PlannerInput, model: str | None) -> str:
        if settings.structured_planning_enabled:
            plan_graph = await self.planner_agent.execute_structured(payload, model=model)
            return plan_graph.as_plan_text()
        planner_output = await self.planner_agent.execute(payload, model=model)
        return planner_output.plan_text

    async def _execute_tool_step(
        self,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
        should_steer_interrupt: Callable[[], bool] | None,
    ) -> str:
        return await self._execute_tools(
            user_message=payload.user_message,
            plan_text=payload.plan_text,
            memory_context=payload.reduced_context,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=allowed_tools,
            prompt_mode=payload.prompt_mode,
            should_steer_interrupt=should_steer_interrupt,
        )

    async def _execute_synthesize_step(
        self,
        payload: SynthesizerInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
    ) -> str:
        synthesize_output = await self.synthesizer_agent.execute(
            payload,
            send_event=send_event,
            session_id=session_id,
            request_id=request_id,
            model=model,
        )
        return synthesize_output.final_text

    def _step_budgets(self, max_context: int) -> dict[str, int]:
        budget = max(1024, max_context)
        plan_budget = max(256, int(budget * 0.25))
        tool_budget = max(256, int(budget * 0.30))
        final_budget = max(512, int(budget * 0.45))
        total = plan_budget + tool_budget + final_budget
        if total > budget:
            scale = budget / total
            plan_budget = int(plan_budget * scale)
            tool_budget = int(tool_budget * scale)
            final_budget = budget - plan_budget - tool_budget
        return {
            "plan": plan_budget,
            "tool": tool_budget,
            "final": final_budget,
        }

    def _build_context_segments(
        self,
        *,
        phase: str,
        prompt_mode: str,
        prompt_type: str,
        budget_tokens: int,
        rendered_text: str,
        used_tokens: int,
        user_message: str,
        memory_lines: list[str],
        tool_outputs: list[str],
        snapshot_lines: list[str] | None,
        system_prompt: str,
    ) -> dict[str, object]:
        estimate = self.context_reducer.estimate_tokens
        user_tokens = estimate(user_message or "")
        memory_text = "\n".join(memory_lines or [])
        memory_tokens = estimate(memory_text)
        tool_text = "\n\n".join(tool_outputs or [])
        tool_tokens = estimate(tool_text)
        snapshot_text = "\n".join(snapshot_lines or [])
        snapshot_tokens = estimate(snapshot_text)
        system_tokens = estimate(system_prompt or "")

        segments: dict[str, dict[str, int | float]] = {
            "system_prompt": {"tokens_est": system_tokens, "chars": len(system_prompt or "")},
            "user_payload": {"tokens_est": user_tokens, "chars": len(user_message or "")},
            "memory": {"tokens_est": memory_tokens, "chars": len(memory_text)},
            "tool_results": {"tokens_est": tool_tokens, "chars": len(tool_text)},
            "snapshot": {"tokens_est": snapshot_tokens, "chars": len(snapshot_text)},
            "rendered_prompt": {"tokens_est": used_tokens, "chars": len(rendered_text or "")},
        }

        total = max(1, sum(int(item["tokens_est"]) for item in segments.values()))
        for value in segments.values():
            value["share_pct"] = round((int(value["tokens_est"]) / total) * 100.0, 2)

        kernel = self.prompt_kernel_builder.build(
            prompt_type=prompt_type,
            prompt_mode=normalize_prompt_mode(prompt_mode, default=settings.prompt_mode_default),
            sections={
                "system": system_prompt or "",
                "platform": self._platform.summary(),
                "context": rendered_text or "",
                "task": user_message or "",
                "tool_results": tool_text,
                "snapshot": snapshot_text,
            },
        )

        return {
            "phase": phase,
            "prompt_mode": kernel.prompt_mode,
            "kernel_version": kernel.kernel_version,
            "prompt_hash": kernel.prompt_hash,
            "section_fingerprints": kernel.section_fingerprints,
            "budget_tokens": int(budget_tokens),
            "used_tokens": int(used_tokens),
            "segments": segments,
        }

    def _validate_guardrails(self, user_message: str, session_id: str, model: str | None) -> None:
        if not user_message.strip():
            raise GuardrailViolation("Message must not be empty.")
        if len(user_message) > settings.max_user_message_length:
            raise GuardrailViolation(
                f"Message exceeds max length ({settings.max_user_message_length})."
            )
        if len(session_id) > 120:
            raise GuardrailViolation("session_id too long.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise GuardrailViolation("session_id contains unsupported characters.")
        if model and len(model) > 120:
            raise GuardrailViolation("model name too long.")

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
            item
            for item in ((tool_policy or {}).get("allow") or [])
            if isinstance(item, str) and item.strip()
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
            item
            for item in ((tool_policy or {}).get("allow") or [])
            if isinstance(item, str) and item.strip()
        ]
        requested_allow = self._normalize_tool_set((tool_policy or {}).get("allow"))
        if requested_allow is not None:
            if requested_allow:
                base_allowed &= requested_allow
            elif not requested_allow_values:
                base_allowed &= requested_allow

        deny_set = set()
        deny_set |= self._normalize_tool_set(settings.agent_tools_deny) or set()
        deny_set |= self._normalize_tool_set((tool_policy or {}).get("deny")) or set()

        base_allowed -= deny_set

        also_allow_set = self._normalize_tool_set((tool_policy or {}).get("also_allow")) or set()
        base_allowed |= (also_allow_set - deny_set)

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
                    base_allowed |= (agent_also_allow - deny_set)

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

        async def _approve_blocked_process_tools_if_needed_proxy(*, actions: list[dict], allowed_tools: set[str]) -> set[str]:
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
            detect_intent_gate=self._detect_intent_gate,
            resolve_skills_enabled_for_request=self._resolve_skills_enabled_for_request,
            build_skills_snapshot=self.skills_service.build_snapshot,
            empty_skills_snapshot=self._empty_skills_snapshot,
            request_policy_override=_request_policy_override_proxy,
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

    def _plan_still_valid(self, plan_text: str, tool_results: str | None) -> bool:
        state = self._classify_tool_results_state(tool_results)
        if state not in {"blocked", "usable"}:
            return False
        # L-2: check plan_text for explicit completion/done markers
        if plan_text and any(marker in plan_text.lower() for marker in ("[done]", "[completed]", "[aborted]")):
            return False
        return True

    def _classify_tool_results_state(self, tool_results: str | None) -> str:
        if self._is_steer_interrupted(tool_results):
            return "steer_interrupted"

        if self._parse_blocked_tool_result(tool_results) is not None:
            return "blocked"

        normalized_results = (tool_results or "").strip()
        if not normalized_results:
            return "empty"

        lowered = normalized_results.lower()
        has_ok = "] ok" in lowered or "[ok]" in lowered
        has_error = "[error]" in lowered or "] error" in lowered
        # D-11: detect suspicious patterns (empty body, placeholder output)
        suspicious_patterns = (
            "no output", "n/a", "not available", "null", "undefined",
            "placeholder", "{}", "[]",
        )
        has_suspicious = any(p in lowered for p in suspicious_patterns)

        if has_error and has_ok:
            # D-11   BREAKING: was "usable" before D-11.
            # Mixed OK + ERROR now triggers partial_error to enable
            # targeted replanning of only the failed tools.
            return "partial_error"
        if has_error and not has_ok:
            if "tool timeout" in lowered or "timed out" in lowered:
                return "timeout_error"
            return "error_only"
        if has_suspicious and not has_ok:
            # D-11   BREAKING: was "usable" before D-11.
            return "all_suspicious"
        return "usable"

    def _is_steer_interrupted(self, tool_results: str | None) -> bool:
        return (tool_results or "").startswith(STEER_INTERRUPTED_MARKER)

    def _resolve_replan_reason(
        self,
        *,
        tool_results_state: str,
        iteration: int,
        max_replan_iterations: int,
        empty_tool_replan_attempts_used: int,
        max_empty_tool_replan_attempts: int,
        error_tool_replan_attempts_used: int,
        max_error_tool_replan_attempts: int,
    ) -> str | None:
        # A timed-out tool call will time out again with the same arguments.
        # Do not waste replan budget — break the loop immediately.
        if tool_results_state == "timeout_error":
            return None

        if tool_results_state == "error_only":
            if error_tool_replan_attempts_used < max_error_tool_replan_attempts:
                return "tool_selection_error_replan"
            return None

        # D-11: partial_error — some tools worked, some failed. Re-plan only
        # the failed portion while keeping successful results.
        if tool_results_state == "partial_error":
            if error_tool_replan_attempts_used < max_error_tool_replan_attempts:
                return "tool_selection_partial_error_replan"
            return None

        # D-11: all_suspicious — every result looks like empty/placeholder output.
        # Treat similarly to empty results but with a specific reason tag.
        if tool_results_state == "all_suspicious":
            if empty_tool_replan_attempts_used < max_empty_tool_replan_attempts:
                return "tool_selection_suspicious_replan"
            return None

        if (
            tool_results_state == "empty"
            and empty_tool_replan_attempts_used < max_empty_tool_replan_attempts
        ):
            return "tool_selection_empty_replan"

        regular_replan_budget_remaining = iteration < max_replan_iterations
        if regular_replan_budget_remaining:
            return "tool_results_invalidated_plan"

        return None

    def _build_root_cause_replan_prompt(
        self,
        *,
        user_message: str,
        previous_plan: str,
        tool_results: str,
    ) -> str:
        return (
            "The previous plan failed. Analyze WHY and create a better plan.\n\n"
            f"Original user request: {user_message[:2000]}\n"
            f"Previous plan: {previous_plan[:2000]}\n"
            f"Tool results (including errors): {(tool_results or '')[:3000]}\n\n"
            "Your analysis must include:\n"
            "1. ROOT CAUSE: Why did the previous plan fail? (wrong tool? wrong arguments? missing info?)\n"
            "2. LESSON LEARNED: What should we avoid in the new plan?\n"
            "3. NEW PLAN: A revised plan that addresses the root cause."
        )

    def _detect_intent_gate(self, user_message: str) -> IntentGateDecision:
        decision = self._intent.detect(user_message)
        confidence_label = "high" if decision.confidence >= 0.8 else ("medium" if decision.confidence >= 0.45 else "low")
        return IntentGateDecision(
            intent=decision.intent,
            confidence=confidence_label,
            extracted_command=decision.extracted_command,
            missing_slots=decision.missing_slots,
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

    def _resolve_synthesis_task_type(self, *, user_message: str, tool_results: str) -> str:
        message = (user_message or "").strip()
        if self.synthesizer_agent._requires_hard_research_structure(message):
            return "hard_research"

        # Evidence-first: Tool-Ergebnisse haben absoluten Vorrang vor Keyword-Match.
        # "spawned_subrun_id=" im Tool-Result belegt, dass spawn_subrun ausgeführt wurde.
        # Der terminal_reason entscheidet über den konkreten Orchestrierungs-Typ.
        if "spawned_subrun_id=" in (tool_results or ""):
            tr = tool_results or ""
            terminal_statuses = [
                (m.start(), m.group(1))
                for m in re.finditer(
                    r"terminal_reason=(subrun-complete|subrun-error|subrun-timeout|subrun-cancelled|subrun-running|subrun-accepted)",
                    tr,
                )
            ]
            if terminal_statuses:
                _, last_status = max(terminal_statuses, key=lambda item: item[0])
                if last_status == "subrun-complete":
                    return "orchestration"
                if last_status in ("subrun-error", "subrun-timeout", "subrun-cancelled"):
                    return "orchestration_failed"
                return "orchestration_pending"

            # Backward-compatible fallback wenn terminal_reason nicht explizit serialisiert ist.
            if "subrun-complete" in tr:
                return "orchestration"
            if any(s in tr for s in ("subrun-error", "subrun-timeout", "subrun-cancelled")):
                return "orchestration_failed"
            return "orchestration_pending"

        # Keyword-Scan nur wenn KEIN Subrun-Ergebnis vorliegt.
        if self._is_subrun_orchestration_task(message):
            return "orchestration"

        if self._is_file_creation_task(message) or _IMPLEMENTATION_RE.search(message):
            return "implementation"
        if self._is_web_research_task(message) or "source_url" in (tool_results or ""):
            return "research"
        return "general"

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
        if "subrun_announce" in tr and "subrun-complete" in tr:
            return True
        return False

    def _has_orchestration_attempted(self, tool_results: str | None) -> bool:
        """Gibt True zurück, wenn spawn_subrun aufgerufen wurde (egal ob erfolgreich)."""
        return "spawned_subrun_id=" in (tool_results or "")

    def _has_successful_tool_output(self, tool_results: str | None, tool_name: str) -> bool:
        if not tool_results:
            return False
        pattern = re.compile(rf"\[{re.escape(tool_name)}\]\s*\n?(?!\s*ERROR:)", re.IGNORECASE)
        return bool(pattern.search(tool_results))

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
            if tool_name != "spawn_subrun"
            and not tool_name.startswith("mcp_")
            and not hasattr(self.tools, tool_name)
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
                "Tool registry contains tools without argument validator: "
                + ", ".join(sorted(missing_arg_validators))
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
            except asyncio.TimeoutError as exc:
                last_error = exc
                if attempt >= max_attempts:
                    raise ToolExecutionError(
                        f"Tool timeout ({tool}) after {policy.timeout_seconds:.1f}s"
                    ) from exc
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

        mode = str(args.get("mode") or "run").strip().lower() or "run"
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
            normalized_agent_id = str(spawn_result.get("agent_id") or normalized_agent_id).strip() or normalized_agent_id
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
        if result_value is None:
            result = None
        else:
            result = str(result_value)[:2000]

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
            "source_agent_id": str(candidate.get("source_agent_id") or source_agent_id).strip().lower() or source_agent_id,
            "target_agent_id": str(candidate.get("target_agent_id") or target_agent_id).strip().lower() or target_agent_id,
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
        await send_event(
            build_lifecycle_event(
                request_id=request_id,
                session_id=session_id,
                stage=stage,
                details=details,
                agent=self.name,
            )
        )

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
            except asyncio.TimeoutError as exc:
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
                    raise RuntimeError(
                        f"Hook '{hook_name}' timed out for {type(hook).__name__}"
                    ) from exc
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
                    raise RuntimeError(
                        f"Hook '{hook_name}' failed for {type(hook).__name__}: {exc}"
                    ) from exc
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
