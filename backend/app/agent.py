from __future__ import annotations

import asyncio
import inspect
import json
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Callable, Awaitable

from app.agents.planner_agent import PlannerAgent
from app.agents.synthesizer_agent import SynthesizerAgent
from app.agents.tool_selector_agent import ToolSelectorAgent
from app.contracts.tool_selector_runtime import ToolSelectorRuntime
from app.config import settings
from app.contracts.tool_protocol import ToolProvider
from app.contracts.schemas import PlannerInput, SynthesizerInput, ToolSelectorInput
from app.errors import GuardrailViolation, ToolExecutionError
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
from app.services.intent_detector import IntentDetector
from app.services.prompt_kernel_builder import PromptKernelBuilder
from app.services.reply_shaper import ReplyShaper
from app.services.request_normalization import normalize_prompt_mode
from app.services.tool_arg_validator import ToolArgValidator
from app.services.tool_execution_manager import ToolExecutionManager
from app.services.tool_registry import ToolExecutionPolicy, ToolRegistry, ToolRegistryFactory
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
            payload.user_message,
            payload.plan_text,
            payload.reduced_context,
            payload.prompt_mode,
            session_id,
            request_id,
            send_event,
            model,
            allowed_tools,
            should_steer_interrupt,
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
            )
        )
        self._intent = IntentDetector()
        self._intent_detector = self._intent
        self._action_parser = ActionParser()
        self._action_augmenter = ActionAugmenter(intent_detector=self._intent)
        self._reply_shaper = ReplyShaper()
        self._tool_execution_manager = ToolExecutionManager()
        self.tool_registry = self._build_tool_registry()
        self._arg_validator = ToolArgValidator(violates_command_policy=self._violates_command_policy)
        self._validate_tool_registry_dispatch()
        self._hooks: list[object] = []
        self._build_sub_agents()

    def register_hook(self, hook: object) -> None:
        self._hooks.append(hook)

    def _build_sub_agents(self) -> None:
        self.planner_agent = PlannerAgent(client=self.client, system_prompt=self.prompt_profile.plan_prompt)
        self.tool_selector_agent = ToolSelectorAgent(runtime=_HeadToolSelectorRuntime(self))
        self.synthesizer_agent = SynthesizerAgent(
            client=self.client,
            agent_name=self.name,
            emit_lifecycle_fn=self._emit_lifecycle,
            system_prompt=self.prompt_profile.final_prompt,
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
        self.client = LlmClient(
            base_url=base_url,
            model=model,
        )
        self.planner_agent.configure_runtime(base_url=base_url, model=model)
        self.synthesizer_agent.configure_runtime(base_url=base_url, model=model)

    def set_spawn_subrun_handler(self, handler: SpawnSubrunHandler | None) -> None:
        self._spawn_subrun_handler = handler

    def set_policy_approval_handler(self, handler: PolicyApprovalHandler | None) -> None:
        self._policy_approval_handler = handler

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
        status = "failed"
        error_text: str | None = None
        final_text = ""

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
            model_id = model or self.client.model
            effective_prompt_mode = normalize_prompt_mode(prompt_mode, default=settings.prompt_mode_default)
            profile = self.model_registry.resolve(model_id)
            budgets = self._step_budgets(profile.max_context)
            memory_items = self.memory.get_items(session_id)
            memory_lines = [f"{item.role}: {item.content}" for item in memory_items]

            plan_context = self.context_reducer.reduce(
                budget_tokens=budgets["plan"],
                user_message=user_message,
                memory_lines=memory_lines,
                tool_outputs=[],
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
                    budget_tokens=budgets["plan"],
                    rendered_text=plan_context.rendered,
                    used_tokens=plan_context.used_tokens,
                    user_message=user_message,
                    memory_lines=memory_lines,
                    tool_outputs=[],
                    snapshot_lines=None,
                    system_prompt=self.prompt_profile.plan_prompt,
                ),
            )

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
            total_replan_cycles = max_replan_iterations + max_empty_tool_replan_attempts + max_error_tool_replan_attempts
            tool_results = ""
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
                    iteration=iteration,
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
                plan_text = await self.plan_step_executor.execute(
                    PlannerInput(
                        user_message=user_message,
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

            blocked_payload = self._parse_blocked_tool_result(tool_results)
            if blocked_payload is not None:
                final_text = blocked_payload.get("message") or "I need one required detail before I can continue."
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
                web_errors = self._extract_tool_errors(tool_results or "", tool_name="web_fetch")
                await self._emit_lifecycle(
                    send_event,
                    stage="web_research_sources_unavailable",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error_count": len(web_errors)},
                )
                final_text = self._build_web_fetch_unavailable_reply(web_errors)
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
                    details={"response_chars": len(final_text), "fallback": "web_fetch_unavailable"},
                )
                return final_text

            await send_event(
                {
                    "type": "agent_step",
                    "agent": self.name,
                    "step": "Reviewing results and building final response",
                }
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

            if shape_result.suppressed:
                await self._emit_lifecycle(
                    send_event,
                    stage="reply_suppressed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"reason": shape_result.reason or "suppressed"},
                )
                await send_event(
                    {
                        "type": "status",
                        "agent": self.name,
                        "message": f"Reply suppressed by shaping: {shape_result.reason or 'suppressed'}",
                    }
                )
            else:
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
            raise
        finally:
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

    async def _execute_planner_step(self, payload: PlannerInput, model: str | None) -> str:
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
        tool_selector_output = await self.tool_selector_agent.execute(
            payload,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=allowed_tools,
            should_steer_interrupt=should_steer_interrupt,
        )
        return tool_selector_output.tool_results

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
        return {
            "plan": plan_budget,
            "tool": tool_budget,
            "final": final_budget,
        }

    def _build_context_segments(
        self,
        *,
        phase: str,
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

        return {
            "phase": phase,
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
        normalized: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            candidate = self._normalize_tool_name(value)
            if candidate in ALLOWED_TOOLS:
                normalized.add(candidate)
        return normalized

    def _unknown_tool_names(self, values: list[str] | None) -> list[str]:
        if values is None:
            return []
        unknown: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            candidate = self._normalize_tool_name(value)
            if candidate and candidate not in ALLOWED_TOOLS:
                unknown.add(candidate)
        return sorted(unknown)

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
        base_allowed = set(ALLOWED_TOOLS)

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
        return base_allowed

    async def _execute_tools(
        self,
        user_message: str,
        plan_text: str,
        memory_context: str,
        prompt_mode: str,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
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

    def _plan_still_valid(self, plan_text: str, tool_results: str | None) -> bool:
        _ = plan_text
        state = self._classify_tool_results_state(tool_results)
        return state in {"blocked", "usable"}

    def _classify_tool_results_state(self, tool_results: str | None) -> str:
        if self._is_steer_interrupted(tool_results):
            return "steer_interrupted"

        if self._parse_blocked_tool_result(tool_results):
            return "blocked"

        normalized_results = (tool_results or "").strip()
        if not normalized_results:
            return "empty"

        lowered = normalized_results.lower()
        has_ok = "[ok]" in lowered or re.search(r"\bok\b", lowered) is not None
        has_error = "[error]" in lowered or " error:" in lowered
        if has_error and not has_ok:
            return "error_only"
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
        if (
            tool_results_state == "error_only"
            and error_tool_replan_attempts_used < max_error_tool_replan_attempts
        ):
            return "tool_selection_error_replan"

        regular_replan_budget_remaining = iteration < max_replan_iterations - 1
        if regular_replan_budget_remaining:
            return "tool_results_invalidated_plan"

        if (
            tool_results_state == "empty"
            and empty_tool_replan_attempts_used < max_empty_tool_replan_attempts
        ):
            return "tool_selection_empty_replan"

        return None

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
        if self._is_subrun_orchestration_task(message) or "spawned_subrun_id=" in (tool_results or ""):
            return "orchestration"
        if self._is_web_research_task(message) or "source_url" in (tool_results or ""):
            return "research"
        implementation_markers = (
            "implement",
            "fix",
            "refactor",
            "test",
            "code",
            "bug",
            "feature",
        )
        lowered = message.lower()
        if any(marker in lowered for marker in implementation_markers):
            return "implementation"
        return "general"

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
        return self._action_parser.parse(raw)

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
        )

    def _validate_tool_registry_dispatch(self) -> None:
        missing_tooling_methods = [
            tool_name
            for tool_name in self.tool_registry
            if tool_name != "spawn_subrun" and not hasattr(self.tools, tool_name)
        ]
        missing_arg_validators = [
            tool_name
            for tool_name in self.tool_registry
            if not self._arg_validator.has_validator(tool_name)
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

    def _normalize_tool_name(self, tool_name: str) -> str:
        normalized = tool_name.strip()
        if not normalized:
            return normalized
        lowered = normalized.lower()
        if lowered in TOOL_NAME_ALIASES:
            return TOOL_NAME_ALIASES[lowered]
        return normalized

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
                sync_result = await asyncio.wait_for(
                    asyncio.to_thread(invoke_tool_fn, tool, args),
                    timeout=policy.timeout_seconds,
                )
                if inspect.isawaitable(sync_result):
                    return await asyncio.wait_for(sync_result, timeout=policy.timeout_seconds)
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
                if attempt >= max_attempts:
                    raise
                if not self._is_retryable_tool_error(exc, policy.retry_class):
                    raise

        if isinstance(last_error, ToolExecutionError):
            raise last_error
        raise ToolExecutionError(f"Tool execution failed ({tool})")

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

        if child_policy is not None and not isinstance(child_policy, dict):
            raise ToolExecutionError("spawn_subrun 'tool_policy' must be an object.")

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
        )

        run_id = ""
        normalized_mode = mode
        normalized_agent_id = agent_id
        handover_contract: dict = {
            "terminal_reason": "subrun-accepted",
            "confidence": 0.0,
            "result": None,
        }

        if isinstance(spawn_result, dict):
            run_id = str(spawn_result.get("run_id") or "").strip()
            normalized_mode = str(spawn_result.get("mode") or normalized_mode).strip().lower() or normalized_mode
            normalized_agent_id = str(spawn_result.get("agent_id") or normalized_agent_id).strip() or normalized_agent_id
            candidate_handover = spawn_result.get("handover")
            if isinstance(candidate_handover, dict):
                handover_contract = candidate_handover
        else:
            run_id = str(spawn_result).strip()

        if not run_id:
            raise ToolExecutionError("spawn_subrun handler returned an empty run_id.")

        handover_json = json.dumps(handover_contract, ensure_ascii=False)
        return (
            f"spawned_subrun_id={run_id} mode={normalized_mode} agent_id={normalized_agent_id} "
            f"handover_contract={handover_json}"
        )

    def _is_retryable_tool_error(self, error: ToolExecutionError, retry_class: str) -> bool:
        if retry_class == "none":
            return False
        text = str(error).lower()
        transient_markers = ("timeout", "tempor", "busy", "try again", "connection")
        if retry_class == "timeout":
            return "timeout" in text
        return any(marker in text for marker in transient_markers)

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

        for hook in list(self._hooks):
            method = getattr(hook, hook_name, None)
            if method is None:
                continue

            try:
                maybe_result = method(payload)
                if asyncio.iscoroutine(maybe_result):
                    await maybe_result
                await self._emit_lifecycle(
                    send_event,
                    stage="hook_invoked",
                    request_id=request_id,
                    session_id=session_id,
                    details={"hook": type(hook).__name__, "name": hook_name},
                )
            except Exception as exc:
                await self._emit_lifecycle(
                    send_event,
                    stage="hook_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"hook": type(hook).__name__, "name": hook_name, "error": str(exc)},
                )


class CoderAgent(HeadAgent):
    def __init__(self):
        super().__init__(name=settings.coder_agent_name, role="coding-agent")


class ReviewAgent(HeadAgent):
    def __init__(self):
        super().__init__(name=settings.review_agent_name, role="review-agent")


HeadCodingAgent = HeadAgent
