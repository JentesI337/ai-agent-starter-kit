from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from time import monotonic
from typing import Callable, Awaitable
from urllib.parse import quote_plus

from app.agents.planner_agent import PlannerAgent
from app.agents.synthesizer_agent import SynthesizerAgent
from app.agents.tool_selector_agent import ToolSelectorAgent
from app.config import settings
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
from app.state.context_reducer import ContextReducer
from app.tools import AgentTooling

SendEvent = Callable[[dict], Awaitable[None]]
ALLOWED_TOOLS = {
    "list_dir",
    "read_file",
    "write_file",
    "run_command",
    "apply_patch",
    "file_search",
    "grep_search",
    "list_code_usages",
    "get_changed_files",
    "start_background_command",
    "get_background_output",
    "kill_background_process",
    "web_fetch",
}
TOOL_NAME_ALIASES = {
    "createfile": "write_file",
    "writefile": "write_file",
    "readfile": "read_file",
    "listdir": "list_dir",
    "runcommand": "run_command",
    "applypatch": "apply_patch",
    "filesearch": "file_search",
    "grepsearch": "grep_search",
    "listcodeusages": "list_code_usages",
    "getchangedfiles": "get_changed_files",
    "startbackgroundcommand": "start_background_command",
    "getbackgroundoutput": "get_background_output",
    "killbackgroundprocess": "kill_background_process",
    "webfetch": "web_fetch",
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    required_args: tuple[str, ...]
    optional_args: tuple[str, ...]
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class ToolExecutionPolicy:
    retry_class: str
    timeout_seconds: float
    max_retries: int


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
    def __init__(self, name: str | None = None, role: str = "head-agent"):
        self.name = name or settings.agent_name
        self.role = role
        self.prompt_profile = self._resolve_prompt_profile(role)
        self.client = LlmClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        persist_dir = Path(settings.memory_persist_dir)
        if not persist_dir.is_absolute():
            persist_dir = (Path(settings.workspace_root) / persist_dir).resolve()
        self.memory = MemoryStore(
            max_items_per_session=settings.memory_max_items,
            persist_dir=str(persist_dir),
        )
        self.tools = AgentTooling(
            workspace_root=settings.workspace_root,
            command_timeout_seconds=settings.command_timeout_seconds,
        )
        self.model_registry = ModelRegistry()
        self.context_reducer = ContextReducer()
        self.tool_registry = self._build_tool_registry()
        self._hooks: list[object] = []
        self._build_sub_agents()

    def register_hook(self, hook: object) -> None:
        self._hooks.append(hook)

    def _build_sub_agents(self) -> None:
        self.planner_agent = PlannerAgent(client=self.client, system_prompt=self.prompt_profile.plan_prompt)
        self.tool_selector_agent = ToolSelectorAgent(execute_tools_fn=self._execute_tools)
        self.synthesizer_agent = SynthesizerAgent(
            client=self.client,
            agent_name=self.name,
            emit_lifecycle_fn=self._emit_lifecycle,
            system_prompt=self.prompt_profile.final_prompt,
        )
        self.plan_step_executor = PlannerStepExecutor(execute_fn=self._execute_planner_step)
        self.tool_step_executor = ToolStepExecutor(execute_fn=self._execute_tool_step)
        self.synthesize_step_executor = SynthesizeStepExecutor(execute_fn=self._execute_synthesize_step)

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
        self._build_sub_agents()

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: dict[str, list[str]] | None = None,
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
            await self._emit_lifecycle(
                send_event,
                stage="tool_policy_resolved",
                request_id=request_id,
                session_id=session_id,
                details={
                    "allowed": sorted(effective_allowed_tools),
                    "requested_allow": sorted((tool_policy or {}).get("allow", [])),
                    "requested_deny": sorted((tool_policy or {}).get("deny", [])),
                },
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
                    "max_context": profile.max_context,
                    "plan_budget": budgets["plan"],
                    "tool_budget": budgets["tool"],
                    "final_budget": budgets["final"],
                    "plan_used": plan_context.used_tokens,
                },
            )

            await self._invoke_hooks(
                hook_name="before_prompt_build",
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload={
                    "prompt_type": "planning",
                    "model": model,
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
                ),
                model,
            )
            await self._emit_lifecycle(
                send_event,
                stage="planning_completed",
                request_id=request_id,
                session_id=session_id,
                details={"plan_chars": len(plan_text)},
            )
            self.memory.add(session_id, "plan", plan_text)
            await send_event(
                {
                    "type": "agent_step",
                    "agent": self.name,
                    "step": f"Plan ready: {plan_text[:220]}",
                }
            )

            tool_context = self.context_reducer.reduce(
                budget_tokens=budgets["tool"],
                user_message=user_message,
                memory_lines=memory_lines,
                tool_outputs=[plan_text],
            )

            tool_results = await self.tool_step_executor.execute(
                ToolSelectorInput(
                    user_message=user_message,
                    plan_text=plan_text,
                    reduced_context=tool_context.rendered,
                ),
                session_id,
                request_id,
                send_event,
                model,
                effective_allowed_tools,
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

            await self._invoke_hooks(
                hook_name="before_prompt_build",
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload={
                    "prompt_type": "synthesize",
                    "model": model,
                    "context_chars": len(final_context.rendered),
                    "budget_tokens": budgets["final"],
                },
            )

            final_text = await self.synthesize_step_executor.execute(
                SynthesizerInput(
                    user_message=user_message,
                    plan_text=plan_text,
                    tool_results=tool_results or "",
                    reduced_context=final_context.rendered,
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
    ) -> str:
        tool_output = await self.tool_selector_agent.execute(
            payload,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=allowed_tools,
        )
        return tool_output.tool_results

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

    def _validate_tool_policy(self, tool_policy: dict[str, list[str]] | None) -> None:
        if tool_policy is None:
            return
        for key in ("allow", "deny"):
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

    def _resolve_effective_allowed_tools(self, tool_policy: dict[str, list[str]] | None) -> set[str]:
        base_allowed = set(ALLOWED_TOOLS)

        config_allow = self._normalize_tool_set(settings.agent_tools_allow)
        if config_allow is not None:
            base_allowed &= config_allow

        requested_allow = self._normalize_tool_set((tool_policy or {}).get("allow"))
        if requested_allow is not None:
            base_allowed &= requested_allow

        deny_set = set()
        deny_set |= self._normalize_tool_set(settings.agent_tools_deny) or set()
        deny_set |= self._normalize_tool_set((tool_policy or {}).get("deny")) or set()

        base_allowed -= deny_set
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
    ) -> str:
        allowed_text = "|".join(sorted(allowed_tools)) if allowed_tools else "(none)"
        await self._emit_lifecycle(
            send_event,
            stage="tool_selection_started",
            request_id=request_id,
            session_id=session_id,
        )
        if not allowed_tools:
            await self._emit_tool_selection_empty(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                reason="policy_block",
                details={"blocked_with_reason": "no_tools_allowed"},
            )
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_skipped",
                request_id=request_id,
                session_id=session_id,
                details={"reason": "no_tools_allowed"},
            )
            return ""

        intent_decision = self._detect_intent_gate(user_message)
        if intent_decision.intent == "execute_command" and "run_command" not in allowed_tools:
            blocked_message = (
                "I can execute commands for you, but command execution is currently blocked by the active tool policy. "
                "Please allow `run_command` (or switch to a coding-capable profile) and retry."
            )
            await self._emit_tool_selection_empty(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                reason="policy_block",
                details={
                    "intent": intent_decision.intent,
                    "confidence": intent_decision.confidence,
                    "blocked_with_reason": "run_command_not_allowed",
                },
            )
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_completed",
                request_id=request_id,
                session_id=session_id,
                details={"actions": 0, "blocked_with_reason": "run_command_not_allowed"},
            )
            return self._encode_blocked_tool_result(
                blocked_with_reason="run_command_not_allowed",
                message=blocked_message,
            )

        if intent_decision.intent == "execute_command" and intent_decision.missing_slots:
            blocked_message = (
                "Ich kann den Command ausführen, brauche aber den exakten Befehl. "
                "Bitte nenne genau den auszuführenden Command (z. B. `pytest -q` oder `npm test`)."
            )
            await self._emit_tool_selection_empty(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                reason="missing_slots",
                details={
                    "intent": intent_decision.intent,
                    "confidence": intent_decision.confidence,
                    "missing_slots": list(intent_decision.missing_slots),
                    "blocked_with_reason": "missing_command",
                },
            )
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_completed",
                request_id=request_id,
                session_id=session_id,
                details={"actions": 0, "blocked_with_reason": "missing_command"},
            )
            return self._encode_blocked_tool_result(
                blocked_with_reason="missing_command",
                message=blocked_message,
            )

        await self._invoke_hooks(
            hook_name="before_prompt_build",
            send_event=send_event,
            request_id=request_id,
            session_id=session_id,
            payload={
                "prompt_type": "tool_selection",
                "model": model,
                "context_chars": len(memory_context),
                "allowed_tools": sorted(allowed_tools),
            },
        )

        tool_selector_prompt = (
            "Choose up to 3 tool calls to support this task.\n"
            "Return strict JSON only in this schema:\n"
            f"{{\"actions\":[{{\"tool\":\"{allowed_text}\",\"args\":{{}}}}]}}\n"
            "If no tool is needed return {\"actions\":[]}.\n"
            "If the user explicitly asks to search/browse/check the web, include at least one web_fetch action whenever allowed.\n"
            "Key args by tool:\n"
            "- write_file: path, content\n"
            "- apply_patch: path, search, replace, optional replace_all\n"
            "- run_command/start_background_command: command, optional cwd\n"
            "- file_search: pattern, optional max_results\n"
            "- grep_search: query, optional include_pattern, optional is_regexp, optional max_results\n"
            "- list_code_usages: symbol, optional include_pattern, optional max_results\n"
            "- get_background_output/kill_background_process: job_id\n"
            "- web_fetch: url, optional max_chars\n\n"
            "Do not output markdown, explanations, [TOOL_CALL] wrappers, or any text outside the JSON object.\n"
            f"Allowed tool names are exactly: {', '.join(sorted(allowed_tools)) or 'none'}.\n\n"
            "Memory:\n"
            f"{memory_context}\n\n"
            "Task:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}"
        )

        raw = await self.client.complete_chat(
            self.prompt_profile.tool_selector_prompt,
            tool_selector_prompt,
            model=model,
        )
        actions, parse_error = self._extract_actions(raw)
        repaired = False

        if parse_error:
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_repair_started",
                request_id=request_id,
                session_id=session_id,
                details={"error": parse_error},
            )
            repaired_raw = await self._repair_tool_selection_json(raw=raw, model=model)
            repaired_actions, repaired_error = self._extract_actions(repaired_raw)
            if repaired_error is None:
                actions = repaired_actions
                parse_error = None
                repaired = True
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_selection_repair_completed",
                    request_id=request_id,
                    session_id=session_id,
                )
            else:
                parse_error = f"{parse_error} | repair_failed: {repaired_error}"
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_selection_repair_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": repaired_error},
                )

        if parse_error:
            await send_event(
                {
                    "type": "error",
                    "agent": self.name,
                    "message": f"Tool-selection parse issue: {parse_error}",
                }
            )
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_parse_failed",
                request_id=request_id,
                session_id=session_id,
                details={"error": parse_error, "raw_preview": raw[:300]},
            )

        if repaired:
            await send_event(
                {
                    "type": "status",
                    "agent": self.name,
                    "message": "Tool-selection output recovered from malformed format.",
                }
            )

        actions, rejected_count = self._validate_actions(actions, allowed_tools)

        actions = await self._augment_actions_if_needed(
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

        if not actions and intent_decision.intent == "execute_command" and intent_decision.confidence == "high":
            if intent_decision.extracted_command:
                actions = [
                    {
                        "tool": "run_command",
                        "args": {"command": intent_decision.extracted_command},
                    }
                ]
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_selection_followup_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "reason": "intent_execute_command_forced_action",
                        "added_tool": "run_command",
                    },
                )
            else:
                blocked_message = (
                    "Ich kann den Command ausführen, brauche aber den exakten Befehl. "
                    "Bitte nenne genau den auszuführenden Command (z. B. `pytest -q` oder `npm test`)."
                )
                await self._emit_tool_selection_empty(
                    send_event=send_event,
                    request_id=request_id,
                    session_id=session_id,
                    reason="missing_slots",
                    details={
                        "intent": intent_decision.intent,
                        "confidence": intent_decision.confidence,
                        "missing_slots": ["command"],
                        "blocked_with_reason": "missing_command",
                    },
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_selection_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"actions": 0, "blocked_with_reason": "missing_command"},
                )
                return self._encode_blocked_tool_result(
                    blocked_with_reason="missing_command",
                    message=blocked_message,
                )

        if rejected_count > 0:
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_actions_rejected",
                request_id=request_id,
                session_id=session_id,
                details={"rejected": rejected_count},
            )
        await self._emit_lifecycle(
            send_event,
            stage="tool_selection_completed",
            request_id=request_id,
            session_id=session_id,
            details={"actions": len(actions)},
        )
        if not actions:
            empty_reason = "ambiguous_input"
            if intent_decision.intent is not None and intent_decision.confidence == "low":
                empty_reason = "low_confidence"
            await self._emit_tool_selection_empty(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                reason=empty_reason,
                details={
                    "intent": intent_decision.intent,
                    "confidence": intent_decision.confidence,
                    "rejected_actions": rejected_count,
                },
            )
            return ""

        results: list[str] = []
        tool_call_cap = max(1, int(getattr(settings, "run_tool_call_cap", 8)))
        tool_time_cap_seconds = max(1.0, float(getattr(settings, "run_tool_time_cap_seconds", 90)))
        loop_warn_threshold = max(1, int(getattr(settings, "tool_loop_warn_threshold", 2)))
        loop_critical_threshold = max(loop_warn_threshold + 1, int(getattr(settings, "tool_loop_critical_threshold", 3)))
        tool_call_count = 0
        loop_blocked_count = 0
        budget_blocked_count = 0
        tool_error_count = 0
        signature_counts: dict[str, int] = {}
        started_at = monotonic()

        for idx, action in enumerate(actions[:3], start=1):
            tool = str(action.get("tool", "")).strip()
            args = action.get("args", {})
            if not isinstance(args, dict):
                args = {}

            elapsed = monotonic() - started_at
            if elapsed >= tool_time_cap_seconds:
                budget_blocked_count += 1
                message = f"tool time budget exceeded ({tool_time_cap_seconds:.1f}s)"
                results.append(f"[{tool}] REJECTED: {message}")
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_budget_exceeded",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "tool": tool,
                        "index": idx,
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
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_budget_exceeded",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "tool": tool,
                        "index": idx,
                        "budget_type": "call_count",
                        "used_calls": tool_call_count,
                        "limit_calls": tool_call_cap,
                    },
                )
                break

            evaluated_args, eval_error = self._evaluate_action(tool, args, allowed_tools)
            if eval_error:
                results.append(f"[{tool}] REJECTED: {eval_error}")
                await send_event(
                    {
                        "type": "error",
                        "agent": self.name,
                        "message": f"Tool blocked ({tool}): {eval_error}",
                    }
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_blocked",
                    request_id=request_id,
                    session_id=session_id,
                    details={"tool": tool, "index": idx, "error": eval_error},
                )
                continue

            signature = json.dumps({"tool": tool, "args": evaluated_args}, ensure_ascii=False, sort_keys=True)
            current_count = signature_counts.get(signature, 0) + 1
            signature_counts[signature] = current_count
            if current_count == loop_warn_threshold:
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_loop_warn",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "tool": tool,
                        "index": idx,
                        "signature_hits": current_count,
                        "warn_threshold": loop_warn_threshold,
                    },
                )
            if current_count >= loop_critical_threshold:
                loop_blocked_count += 1
                message = (
                    "tool loop blocked "
                    f"(signature repeated {current_count}x, threshold {loop_critical_threshold})"
                )
                results.append(f"[{tool}] REJECTED: {message}")
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_loop_blocked",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "tool": tool,
                        "index": idx,
                        "signature_hits": current_count,
                        "critical_threshold": loop_critical_threshold,
                    },
                )
                continue

            policy = self._build_execution_policy(tool)

            await send_event(
                {
                    "type": "agent_step",
                    "agent": self.name,
                    "step": f"Tool {idx}: {tool}",
                }
            )
            await self._emit_lifecycle(
                send_event,
                stage="tool_started",
                request_id=request_id,
                session_id=session_id,
                details={"tool": tool, "index": idx},
            )

            await self._invoke_hooks(
                hook_name="before_tool_call",
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                payload={
                    "tool": tool,
                    "args": dict(evaluated_args),
                    "index": idx,
                },
            )

            try:
                tool_started = monotonic()
                result = await self._run_tool_with_policy(tool=tool, args=evaluated_args, policy=policy)
                tool_call_count += 1
                tool_elapsed_ms = int((monotonic() - tool_started) * 1000)
                clipped = result[:6000]
                self.memory.add(session_id, f"tool:{tool}", clipped)
                results.append(f"[{tool}]\n{clipped}")
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"tool": tool, "index": idx, "result_chars": len(clipped), "elapsed_ms": tool_elapsed_ms},
                )
                await self._invoke_hooks(
                    hook_name="after_tool_call",
                    send_event=send_event,
                    request_id=request_id,
                    session_id=session_id,
                    payload={
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "index": idx,
                        "status": "ok",
                        "result_chars": len(clipped),
                    },
                )
            except ToolExecutionError as exc:
                attempt_calls = 1
                retried_successfully = False
                if (
                    tool == "web_fetch"
                    and self._should_retry_web_fetch_on_404(exc)
                    and (self._is_web_research_task(user_message) or self._is_weather_lookup_task(user_message))
                ):
                    fallback_url = self._build_web_research_url(user_message)
                    primary_url = str(evaluated_args.get("url", "")).strip()
                    if fallback_url and fallback_url != primary_url:
                        await send_event(
                            {
                                "type": "agent_step",
                                "agent": self.name,
                                "step": f"Tool {idx}: web_fetch retry with fallback source",
                            }
                        )
                        await self._emit_lifecycle(
                            send_event,
                            stage="tool_retry_started",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "tool": tool,
                                "index": idx,
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
                            retry_result = await self._run_tool_with_policy(tool=tool, args=retry_args, policy=policy)
                            retry_elapsed_ms = int((monotonic() - retry_started) * 1000)
                            clipped = retry_result[:6000]
                            self.memory.add(session_id, f"tool:{tool}", clipped)
                            results.append(f"[{tool}]\n{clipped}")
                            await self._emit_lifecycle(
                                send_event,
                                stage="tool_completed",
                                request_id=request_id,
                                session_id=session_id,
                                details={
                                    "tool": tool,
                                    "index": idx,
                                    "result_chars": len(clipped),
                                    "elapsed_ms": retry_elapsed_ms,
                                    "retried": True,
                                },
                            )
                            await self._emit_lifecycle(
                                send_event,
                                stage="tool_retry_completed",
                                request_id=request_id,
                                session_id=session_id,
                                details={
                                    "tool": tool,
                                    "index": idx,
                                    "reason": "http_404",
                                    "from_url": primary_url,
                                    "to_url": fallback_url,
                                },
                            )
                            await self._invoke_hooks(
                                hook_name="after_tool_call",
                                send_event=send_event,
                                request_id=request_id,
                                session_id=session_id,
                                payload={
                                    "tool": tool,
                                    "args": dict(retry_args),
                                    "index": idx,
                                    "status": "ok",
                                    "result_chars": len(clipped),
                                    "retried": True,
                                },
                            )
                            retried_successfully = True
                        except ToolExecutionError as retry_exc:
                            exc = ToolExecutionError(f"{exc} | retry_failed: {retry_exc}")
                            await self._emit_lifecycle(
                                send_event,
                                stage="tool_retry_failed",
                                request_id=request_id,
                                session_id=session_id,
                                details={
                                    "tool": tool,
                                    "index": idx,
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
                await send_event(
                    {
                        "type": "error",
                        "agent": self.name,
                        "message": f"Tool error ({tool}): {exc}",
                    }
                )
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"tool": tool, "index": idx, "error": str(exc)},
                )
                await self._invoke_hooks(
                    hook_name="after_tool_call",
                    send_event=send_event,
                    request_id=request_id,
                    session_id=session_id,
                    payload={
                        "tool": tool,
                        "args": dict(evaluated_args),
                        "index": idx,
                        "status": "error",
                        "error": str(exc),
                    },
                )

        total_elapsed_ms = int((monotonic() - started_at) * 1000)
        await self._emit_lifecycle(
            send_event,
            stage="tool_audit_summary",
            request_id=request_id,
            session_id=session_id,
            details={
                "tool_calls": tool_call_count,
                "tool_errors": tool_error_count,
                "loop_blocked": loop_blocked_count,
                "budget_blocked": budget_blocked_count,
                "elapsed_ms": total_elapsed_ms,
                "call_cap": tool_call_cap,
                "time_cap_seconds": tool_time_cap_seconds,
                "loop_warn_threshold": loop_warn_threshold,
                "loop_critical_threshold": loop_critical_threshold,
            },
        )

        return "\n\n".join(results)

    def _detect_intent_gate(self, user_message: str) -> IntentGateDecision:
        text = (user_message or "").strip()
        lowered = text.lower()
        if not text:
            return IntentGateDecision(intent=None, confidence="low", extracted_command=None, missing_slots=())

        command_markers = (
            "run",
            "execute",
            "start",
            "launch",
            "build",
            "test",
            "compile",
            "führe",
            "starte",
            "baue",
            "teste",
        )
        has_command_intent = bool(re.match(r"^\s*(please\s+)?(run|execute|start|launch|build|test|compile)\b", lowered))
        has_command_intent = has_command_intent or "run command" in lowered or "execute command" in lowered
        has_command_intent = has_command_intent or any(lowered.startswith(f"{marker} ") for marker in command_markers)
        if not has_command_intent:
            return IntentGateDecision(intent=None, confidence="low", extracted_command=None, missing_slots=())

        extracted_command = self._extract_explicit_command(text)
        if extracted_command:
            return IntentGateDecision(
                intent="execute_command",
                confidence="high",
                extracted_command=extracted_command,
                missing_slots=(),
            )

        return IntentGateDecision(
            intent="execute_command",
            confidence="high",
            extracted_command=None,
            missing_slots=("command",),
        )

    def _extract_explicit_command(self, user_message: str) -> str | None:
        text = (user_message or "").strip()
        if not text:
            return None

        fenced_match = re.search(r"`([^`\n]{1,400})`", text)
        if fenced_match:
            candidate = fenced_match.group(1).strip()
            if candidate:
                return candidate

        quoted_match = re.search(r"\"([^\"\n]{1,400})\"", text)
        if quoted_match:
            candidate = quoted_match.group(1).strip()
            if candidate:
                return candidate

        lowered = text.lower()
        prefixes = (
            "run ",
            "execute ",
            "start ",
            "launch ",
            "build ",
            "test ",
            "compile ",
            "please run ",
            "please execute ",
            "führe ",
            "starte ",
            "baue ",
            "teste ",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                candidate = text[len(prefix) :].strip()
                if not candidate:
                    return None
                if candidate.lower() in {"it", "this", "that", "command", "den command", "befehl"}:
                    return None
                return candidate

        command_after_colon = re.search(r"(?:command|befehl)\s*:\s*(.+)$", text, flags=re.IGNORECASE)
        if command_after_colon:
            candidate = command_after_colon.group(1).strip()
            if candidate:
                return candidate
        return None

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
        augmented_actions = list(actions)

        if self._is_web_research_task(user_message) and "web_fetch" in allowed_tools:
            has_web_fetch = any(str(action.get("tool", "")).strip() == "web_fetch" for action in augmented_actions)
            if not has_web_fetch:
                fallback_url = self._build_web_research_url(user_message)
                if fallback_url:
                    augmented_actions.append({"tool": "web_fetch", "args": {"url": fallback_url, "max_chars": 24000}})
                    await self._emit_lifecycle(
                        send_event,
                        stage="tool_selection_followup_completed",
                        request_id=request_id,
                        session_id=session_id,
                        details={
                            "reason": "web_research_without_web_fetch",
                            "added_tool": "web_fetch",
                            "url": fallback_url,
                        },
                    )

        if not self._is_file_creation_task(user_message):
            return augmented_actions

        has_write_action = any(str(action.get("tool", "")).strip() == "write_file" for action in augmented_actions)
        if has_write_action:
            return augmented_actions

        await self._emit_lifecycle(
            send_event,
            stage="tool_selection_followup_started",
            request_id=request_id,
            session_id=session_id,
            details={"reason": "file_task_without_write_file"},
        )

        followup_prompt = (
            "You previously selected tools for a task.\n"
            "The user intent likely requires creating or updating files, but no write_file action was selected.\n"
            "Return strict JSON only:\n"
            "{\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command|apply_patch|file_search|grep_search|list_code_usages|get_changed_files|start_background_command|get_background_output|kill_background_process|web_fetch\",\"args\":{}}]}\n"
            "Choose up to 2 additional actions. Include write_file when enough content is available.\n"
            "If still insufficient context, return {\"actions\":[]}\n\n"
            "Memory:\n"
            f"{memory_context}\n\n"
            "Task:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}"
        )

        followup_raw = await self.client.complete_chat(
            settings.agent_tool_selector_prompt,
            followup_prompt,
            model=model,
        )
        followup_actions, followup_error = self._extract_actions(followup_raw)
        if followup_error:
            await self._emit_lifecycle(
                send_event,
                stage="tool_selection_followup_failed",
                request_id=request_id,
                session_id=session_id,
                details={"error": followup_error},
            )
            return augmented_actions

        validated_followups, _ = self._validate_actions(followup_actions, allowed_tools)
        merged = augmented_actions + validated_followups
        deduped: list[dict] = []
        seen_keys: set[str] = set()
        for action in merged:
            key = json.dumps(action, sort_keys=True)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(action)

        await self._emit_lifecycle(
            send_event,
            stage="tool_selection_followup_completed",
            request_id=request_id,
            session_id=session_id,
            details={"base_actions": len(actions), "merged_actions": len(deduped)},
        )
        return deduped

    def _is_web_research_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        markers = (
            "search on the web",
            "search the web",
            "browse the web",
            "look up",
            "latest",
            "current",
            "news",
            "google",
            "bing",
            "duckduckgo",
            "find online",
            "web search",
            "internet",
        )
        return any(marker in text for marker in markers)

    def _is_weather_lookup_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        markers = (
            "weather",
            "forecast",
            "temperature",
            "humidity",
            "wind",
            "precipitation",
            "wetter",
            "temperatur",
            "niederschlag",
        )
        return any(marker in text for marker in markers)

    def _should_retry_web_fetch_on_404(self, error: ToolExecutionError) -> bool:
        text = str(error).lower()
        return "http error 404" in text or " 404" in text

    def _has_successful_web_fetch(self, tool_results: str) -> bool:
        if not tool_results:
            return False
        success_pattern = re.compile(r"\[web_fetch\]\s*\n(?!ERROR:)", re.IGNORECASE)
        return bool(success_pattern.search(tool_results))

    def _extract_tool_errors(self, tool_results: str, *, tool_name: str) -> list[str]:
        if not tool_results:
            return []
        pattern = re.compile(rf"\[{re.escape(tool_name)}\]\s+ERROR:\s*(.+)", re.IGNORECASE)
        errors = [match.group(1).strip() for match in pattern.finditer(tool_results)]
        return [item for item in errors if item]

    def _build_web_fetch_unavailable_reply(self, web_errors: list[str]) -> str:
        lines = [
            "I couldn't reliably fetch web sources for this request, so I can't provide a grounded deep-research answer yet.",
            "",
            "What failed:",
        ]
        if web_errors:
            for item in web_errors[:3]:
                lines.append(f"- {item}")
        else:
            lines.append("- No successful web_fetch result was returned.")

        lines.extend(
            [
                "",
                "How to proceed:",
                "- Retry the request once (temporary upstream issues can resolve on retry).",
                "- Provide 3-5 direct source URLs and I will analyze them deeply.",
                "- If you want, I can first build a reliable source list, then run a second pass with comparative analysis.",
            ]
        )
        return "\n".join(lines).strip()

    def _build_web_research_url(self, user_message: str) -> str:
        text = (user_message or "").strip()
        if not text:
            return ""

        explicit_url = re.search(r"https?://\S+", text)
        if explicit_url:
            return explicit_url.group(0).rstrip(").,;:!?")

        query = text
        for prefix in (
            "can you",
            "please",
            "could you",
            "search on the web for",
            "search the web for",
            "look up",
            "find",
        ):
            if query.lower().startswith(prefix):
                query = query[len(prefix) :].strip()

        if not query:
            query = text
        return f"https://duckduckgo.com/html/?q={quote_plus(query)}"

    def _is_file_creation_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        markers = (
            "create",
            "build",
            "make",
            "save",
            "file",
            "html",
            "css",
            "javascript",
            "js",
        )
        return any(marker in text for marker in markers)

    def _sanitize_final_response(self, final_text: str) -> str:
        text = (final_text or "").strip()
        if not text:
            return text

        sanitized = re.sub(r"\[TOOL_CALL\].*?\[/TOOL_CALL\]", "", text, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r"\{\s*tool\s*=>.*?\}", "", sanitized, flags=re.IGNORECASE | re.DOTALL)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        return sanitized

    def _shape_final_response(self, final_text: str, tool_results: str | None) -> ReplyShapeResult:
        text = (final_text or "").strip()
        removed_tokens: list[str] = []

        for token in ("NO_REPLY", "ANNOUNCE_SKIP"):
            if token in text:
                removed_tokens.append(token)
                text = text.replace(token, "")

        text = self._sanitize_final_response(text)

        deduped_lines = 0
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if lines:
            seen_tool_confirmation: set[str] = set()
            shaped_lines: list[str] = []
            tool_markers = tuple(sorted(self.tool_registry.keys()))
            for line in lines:
                lowered = line.lower()
                is_tool_confirmation = (
                    any(marker in lowered for marker in tool_markers)
                    and any(keyword in lowered for keyword in ("done", "completed", "finished", "erfolgreich"))
                )
                if is_tool_confirmation:
                    if lowered in seen_tool_confirmation:
                        deduped_lines += 1
                        continue
                    seen_tool_confirmation.add(lowered)
                shaped_lines.append(line)
            text = "\n".join(shaped_lines).strip()

        if tool_results:
            compact = re.sub(r"\s+", " ", text.lower()).strip()
            if compact in {
                "done",
                "done.",
                "completed",
                "completed.",
                "ok",
                "ok.",
                "fertig",
                "fertig.",
            }:
                return ReplyShapeResult(
                    text="",
                    suppressed=True,
                    reason="irrelevant_ack_after_tools",
                    removed_tokens=removed_tokens,
                    deduped_lines=deduped_lines,
                )

        if not text:
            reason = "empty_after_shaping"
            if "NO_REPLY" in removed_tokens:
                reason = "no_reply_token"
            elif "ANNOUNCE_SKIP" in removed_tokens:
                reason = "announce_skip_token"
            return ReplyShapeResult(
                text="",
                suppressed=True,
                reason=reason,
                removed_tokens=removed_tokens,
                deduped_lines=deduped_lines,
            )

        return ReplyShapeResult(
            text=text,
            suppressed=False,
            reason=None,
            removed_tokens=removed_tokens,
            deduped_lines=deduped_lines,
        )

    def _extract_actions(self, raw: str) -> tuple[list[dict], str | None]:
        text = raw.strip()
        try:
            parsed = json.loads(text)
        except Exception:
            return [], "LLM JSON could not be decoded."
        if not isinstance(parsed, dict):
            return [], "LLM JSON root is not an object."
        if set(parsed.keys()) - {"actions"}:
            return [], "LLM JSON root contains unsupported fields."
        actions = parsed.get("actions", [])
        if not isinstance(actions, list):
            return [], "LLM JSON field 'actions' is not a list."
        return actions, None

    async def _repair_tool_selection_json(self, raw: str, model: str | None) -> str:
        raw_block = self._extract_json_candidate(raw)
        repair_prompt = (
            "Convert the following tool-selection output into strict JSON only.\n"
            "Output schema:\n"
            "{\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command|apply_patch|file_search|grep_search|list_code_usages|get_changed_files|start_background_command|get_background_output|kill_background_process|web_fetch\",\"args\":{}}]}\n"
            "Rules:\n"
            "- Output only one JSON object.\n"
            "- No markdown and no explanations.\n"
            "- Map legacy tool names to allowed names if obvious (e.g. CreateFile -> write_file).\n"
            "- If uncertain, return {\"actions\":[]}.\n\n"
            "Broken output block (do not add reasoning):\n"
            f"{raw_block}"
        )
        return await self.client.complete_chat(
            self.prompt_profile.tool_repair_prompt,
            repair_prompt,
            model=model,
        )

    def _extract_json_candidate(self, raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return "{}"
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return text[:3000]
        return text[start : end + 1][:3000]

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

    def _build_tool_registry(self) -> dict[str, ToolSpec]:
        return {
            "list_dir": ToolSpec(
                name="list_dir",
                required_args=(),
                optional_args=("path",),
                timeout_seconds=6.0,
                max_retries=0,
            ),
            "read_file": ToolSpec(
                name="read_file",
                required_args=("path",),
                optional_args=(),
                timeout_seconds=8.0,
                max_retries=0,
            ),
            "write_file": ToolSpec(
                name="write_file",
                required_args=("path", "content"),
                optional_args=(),
                timeout_seconds=10.0,
                max_retries=0,
            ),
            "run_command": ToolSpec(
                name="run_command",
                required_args=("command",),
                optional_args=("cwd",),
                timeout_seconds=float(max(3, settings.command_timeout_seconds)),
                max_retries=1,
            ),
            "apply_patch": ToolSpec(
                name="apply_patch",
                required_args=("path", "search", "replace"),
                optional_args=("replace_all",),
                timeout_seconds=10.0,
                max_retries=0,
            ),
            "file_search": ToolSpec(
                name="file_search",
                required_args=("pattern",),
                optional_args=("max_results",),
                timeout_seconds=6.0,
                max_retries=0,
            ),
            "grep_search": ToolSpec(
                name="grep_search",
                required_args=("query",),
                optional_args=("include_pattern", "is_regexp", "max_results"),
                timeout_seconds=8.0,
                max_retries=0,
            ),
            "list_code_usages": ToolSpec(
                name="list_code_usages",
                required_args=("symbol",),
                optional_args=("include_pattern", "max_results"),
                timeout_seconds=8.0,
                max_retries=0,
            ),
            "get_changed_files": ToolSpec(
                name="get_changed_files",
                required_args=(),
                optional_args=(),
                timeout_seconds=8.0,
                max_retries=0,
            ),
            "start_background_command": ToolSpec(
                name="start_background_command",
                required_args=("command",),
                optional_args=("cwd",),
                timeout_seconds=6.0,
                max_retries=0,
            ),
            "get_background_output": ToolSpec(
                name="get_background_output",
                required_args=("job_id",),
                optional_args=("tail_lines",),
                timeout_seconds=5.0,
                max_retries=0,
            ),
            "kill_background_process": ToolSpec(
                name="kill_background_process",
                required_args=("job_id",),
                optional_args=(),
                timeout_seconds=5.0,
                max_retries=0,
            ),
            "web_fetch": ToolSpec(
                name="web_fetch",
                required_args=("url",),
                optional_args=("max_chars",),
                timeout_seconds=20.0,
                max_retries=1,
            ),
        }

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

        def _require_str(name: str, *, non_empty: bool = True, max_len: int = 4000) -> tuple[str | None, str | None]:
            value = normalized_args.get(name)
            if not isinstance(value, str):
                return None, f"argument '{name}' must be a string"
            if non_empty and not value.strip():
                return None, f"argument '{name}' must not be empty"
            if len(value) > max_len:
                return None, f"argument '{name}' too long"
            return value, None

        def _require_bool(name: str, default: bool = False) -> tuple[bool, str | None]:
            if name not in normalized_args:
                return default, None
            value = normalized_args[name]
            if not isinstance(value, bool):
                return default, f"argument '{name}' must be a boolean"
            return value, None

        def _optional_int(name: str, default: int, min_value: int, max_value: int) -> tuple[int, str | None]:
            if name not in normalized_args:
                return default, None
            value = normalized_args[name]
            if not isinstance(value, int):
                return default, f"argument '{name}' must be an integer"
            if value < min_value or value > max_value:
                return default, f"argument '{name}' out of range"
            return value, None

        if tool in {"list_dir", "read_file", "write_file", "apply_patch"}:
            if "path" in normalized_args:
                path_value, err = _require_str("path", max_len=400)
                if err:
                    return {}, err
                if path_value is not None and "\x00" in path_value:
                    return {}, "path is not plausible"

        if tool == "write_file":
            content, err = _require_str("content", non_empty=False, max_len=350000)
            if err:
                return {}, err
            normalized_args["content"] = content

        if tool == "run_command" or tool == "start_background_command":
            command, err = _require_str("command", max_len=1000)
            if err:
                return {}, err
            if command is not None and self._violates_command_policy(command):
                return {}, "command blocked by policy"
            normalized_args["command"] = command
            if "cwd" in normalized_args:
                cwd, err = _require_str("cwd", max_len=400)
                if err:
                    return {}, err
                normalized_args["cwd"] = cwd

        if tool == "apply_patch":
            search, err = _require_str("search", max_len=50000)
            if err:
                return {}, err
            replace, err = _require_str("replace", non_empty=False, max_len=50000)
            if err:
                return {}, err
            replace_all, err = _require_bool("replace_all", default=False)
            if err:
                return {}, err
            normalized_args["search"] = search
            normalized_args["replace"] = replace
            normalized_args["replace_all"] = replace_all

        if tool == "file_search":
            pattern, err = _require_str("pattern", max_len=300)
            if err:
                return {}, err
            max_results, err = _optional_int("max_results", default=100, min_value=1, max_value=500)
            if err:
                return {}, err
            normalized_args["pattern"] = pattern
            normalized_args["max_results"] = max_results

        if tool == "grep_search":
            query, err = _require_str("query", max_len=500)
            if err:
                return {}, err
            if "include_pattern" in normalized_args:
                include_pattern, err = _require_str("include_pattern", max_len=300)
                if err:
                    return {}, err
                normalized_args["include_pattern"] = include_pattern
            is_regexp, err = _require_bool("is_regexp", default=False)
            if err:
                return {}, err
            max_results, err = _optional_int("max_results", default=100, min_value=1, max_value=500)
            if err:
                return {}, err
            normalized_args["query"] = query
            normalized_args["is_regexp"] = is_regexp
            normalized_args["max_results"] = max_results

        if tool == "list_code_usages":
            symbol, err = _require_str("symbol", max_len=160)
            if err:
                return {}, err
            if "include_pattern" in normalized_args:
                include_pattern, err = _require_str("include_pattern", max_len=300)
                if err:
                    return {}, err
                normalized_args["include_pattern"] = include_pattern
            max_results, err = _optional_int("max_results", default=100, min_value=1, max_value=500)
            if err:
                return {}, err
            normalized_args["symbol"] = symbol
            normalized_args["max_results"] = max_results

        if tool == "get_background_output":
            job_id, err = _require_str("job_id", max_len=80)
            if err:
                return {}, err
            tail_lines, err = _optional_int("tail_lines", default=200, min_value=1, max_value=1000)
            if err:
                return {}, err
            normalized_args["job_id"] = job_id
            normalized_args["tail_lines"] = tail_lines

        if tool == "kill_background_process":
            job_id, err = _require_str("job_id", max_len=80)
            if err:
                return {}, err
            normalized_args["job_id"] = job_id

        if tool == "web_fetch":
            url, err = _require_str("url", max_len=1000)
            if err:
                return {}, err
            max_chars, err = _optional_int("max_chars", default=12000, min_value=1000, max_value=100000)
            if err:
                return {}, err
            normalized_args["url"] = url
            normalized_args["max_chars"] = max_chars

        return normalized_args, None

    def _violates_command_policy(self, command: str) -> bool:
        lowered = command.lower()
        blocked_patterns = [
            r"\brm\s+-rf\s+/",
            r"\bdel\s+/[a-z]*\s*[a-z]:\\",
            r"\bformat\s+[a-z]:",
            r"\bshutdown\b",
            r"\breboot\b",
        ]
        return any(re.search(pattern, lowered) for pattern in blocked_patterns)

    def _build_execution_policy(self, tool: str) -> ToolExecutionPolicy:
        spec = self.tool_registry[tool]
        retry_class = "none"
        if tool in {"run_command", "web_fetch"}:
            retry_class = "transient"
        return ToolExecutionPolicy(
            retry_class=retry_class,
            timeout_seconds=spec.timeout_seconds,
            max_retries=spec.max_retries,
        )

    async def _run_tool_with_policy(self, tool: str, args: dict, policy: ToolExecutionPolicy) -> str:
        max_attempts = policy.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._invoke_tool, tool, args),
                    timeout=policy.timeout_seconds,
                )
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

    def _is_retryable_tool_error(self, error: ToolExecutionError, retry_class: str) -> bool:
        if retry_class == "none":
            return False
        text = str(error).lower()
        transient_markers = ("timeout", "tempor", "busy", "try again", "connection")
        if retry_class == "timeout":
            return "timeout" in text
        return any(marker in text for marker in transient_markers)

    def _invoke_tool(self, tool: str, args: dict) -> str:
        if tool == "list_dir":
            return self.tools.list_dir(path=args.get("path"))
        if tool == "read_file":
            path = args.get("path")
            if not isinstance(path, str):
                raise ToolExecutionError("read_file requires 'path'.")
            return self.tools.read_file(path=path)
        if tool == "write_file":
            path = args.get("path")
            content = args.get("content")
            if not isinstance(path, str) or not isinstance(content, str):
                raise ToolExecutionError("write_file requires 'path' and 'content'.")
            return self.tools.write_file(path=path, content=content)
        if tool == "run_command":
            command = args.get("command")
            cwd = args.get("cwd")
            if not isinstance(command, str):
                raise ToolExecutionError("run_command requires 'command'.")
            if cwd is not None and not isinstance(cwd, str):
                raise ToolExecutionError("run_command 'cwd' must be string if provided.")
            return self.tools.run_command(command=command, cwd=cwd)
        if tool == "apply_patch":
            path = args.get("path")
            search = args.get("search")
            replace = args.get("replace")
            replace_all = args.get("replace_all", False)
            if not isinstance(path, str) or not isinstance(search, str) or not isinstance(replace, str):
                raise ToolExecutionError("apply_patch requires 'path', 'search' and 'replace'.")
            if not isinstance(replace_all, bool):
                raise ToolExecutionError("apply_patch 'replace_all' must be boolean if provided.")
            return self.tools.apply_patch(path=path, search=search, replace=replace, replace_all=replace_all)
        if tool == "file_search":
            pattern = args.get("pattern")
            max_results = args.get("max_results", 100)
            if not isinstance(pattern, str):
                raise ToolExecutionError("file_search requires 'pattern'.")
            if not isinstance(max_results, int):
                raise ToolExecutionError("file_search 'max_results' must be int if provided.")
            return self.tools.file_search(pattern=pattern, max_results=max_results)
        if tool == "grep_search":
            query = args.get("query")
            include_pattern = args.get("include_pattern")
            is_regexp = args.get("is_regexp", False)
            max_results = args.get("max_results", 100)
            if not isinstance(query, str):
                raise ToolExecutionError("grep_search requires 'query'.")
            if include_pattern is not None and not isinstance(include_pattern, str):
                raise ToolExecutionError("grep_search 'include_pattern' must be string if provided.")
            if not isinstance(is_regexp, bool):
                raise ToolExecutionError("grep_search 'is_regexp' must be boolean if provided.")
            if not isinstance(max_results, int):
                raise ToolExecutionError("grep_search 'max_results' must be int if provided.")
            return self.tools.grep_search(
                query=query,
                include_pattern=include_pattern,
                is_regexp=is_regexp,
                max_results=max_results,
            )
        if tool == "list_code_usages":
            symbol = args.get("symbol")
            include_pattern = args.get("include_pattern")
            max_results = args.get("max_results", 100)
            if not isinstance(symbol, str):
                raise ToolExecutionError("list_code_usages requires 'symbol'.")
            if include_pattern is not None and not isinstance(include_pattern, str):
                raise ToolExecutionError("list_code_usages 'include_pattern' must be string if provided.")
            if not isinstance(max_results, int):
                raise ToolExecutionError("list_code_usages 'max_results' must be int if provided.")
            return self.tools.list_code_usages(
                symbol=symbol,
                include_pattern=include_pattern,
                max_results=max_results,
            )
        if tool == "get_changed_files":
            return self.tools.get_changed_files()
        if tool == "start_background_command":
            command = args.get("command")
            cwd = args.get("cwd")
            if not isinstance(command, str):
                raise ToolExecutionError("start_background_command requires 'command'.")
            if cwd is not None and not isinstance(cwd, str):
                raise ToolExecutionError("start_background_command 'cwd' must be string if provided.")
            return self.tools.start_background_command(command=command, cwd=cwd)
        if tool == "get_background_output":
            job_id = args.get("job_id")
            tail_lines = args.get("tail_lines", 200)
            if not isinstance(job_id, str):
                raise ToolExecutionError("get_background_output requires 'job_id'.")
            if not isinstance(tail_lines, int):
                raise ToolExecutionError("get_background_output 'tail_lines' must be int if provided.")
            return self.tools.get_background_output(job_id=job_id, tail_lines=tail_lines)
        if tool == "kill_background_process":
            job_id = args.get("job_id")
            if not isinstance(job_id, str):
                raise ToolExecutionError("kill_background_process requires 'job_id'.")
            return self.tools.kill_background_process(job_id=job_id)
        if tool == "web_fetch":
            url = args.get("url")
            max_chars = args.get("max_chars", 12000)
            if not isinstance(url, str):
                raise ToolExecutionError("web_fetch requires 'url'.")
            if not isinstance(max_chars, int):
                raise ToolExecutionError("web_fetch 'max_chars' must be int if provided.")
            return self.tools.web_fetch(url=url, max_chars=max_chars)
        raise ToolExecutionError(f"Unknown tool: {tool}")

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
