"""AgentRunner — Continuous Streaming Tool Loop.

Replaces the 3-phase pipeline (Planner → ToolSelector → Synthesizer) with a
single continuous loop where the LLM decides when to use tools and when to
answer.  Activated via ``USE_CONTINUOUS_LOOP=true`` feature flag.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import os
from typing import Any

from app.agent_runner_types import LoopState, PlanStep, PlanTracker, StreamResult, ToolCall, ToolResult
from app.services.visualization import build_plan_progress_event, build_visualization_event, sanitize_mermaid_labels, validate_mermaid_node_count
from app.config import settings
from app.errors import PolicyApprovalCancelledError
from app.llm_client import LlmClient
from app.memory import MemoryStore
from app.services.compaction_service import CompactionService
from app.services.tool_execution_manager import ToolExecutionManager
from app.services.tool_registry import ToolRegistry
from app.tool_policy import ToolPolicyDict

_IMPLEMENTATION_RE = re.compile(
    r"\b(?:implement|fix|refactor|coding|bugfix|bug\s*fix|feature)\b", re.IGNORECASE
)

logger = logging.getLogger("app.agent_runner")

SendEvent = Callable[[dict], Awaitable[None]]


# ──────────────────────────────────────────────────────────────────────
# Unified System Prompt Builder
# ──────────────────────────────────────────────────────────────────────


def _format_current_datetime() -> str:
    """Return the current date/time formatted for the system prompt."""
    import zoneinfo as _zi

    tz_name = (os.environ.get("USER_TIMEZONE") or "").strip()
    try:
        tz = _zi.ZoneInfo(tz_name) if tz_name else None
    except (KeyError, Exception):
        tz = None
    now = datetime.now(tz=tz or UTC)
    tz_label = tz_name or "UTC"
    return now.strftime(f"%A, %d %B %Y, %H:%M {tz_label}")


_REASONING_STRATEGY_HINTS: dict[str, str] = {
    "depth_first": "Explore one path deeply before considering alternatives.",
    "breadth_first": "Survey multiple options before committing to a path.",
    "plan_execute": "Create a plan first, then execute step by step.",
    "verify_first": "Verify assumptions and evidence before drawing conclusions.",
    "analytical": "Apply structured analytical frameworks to decompose the problem.",
}


def build_capability_section(
    *,
    specialization: str = "",
    capabilities: list[str] | None = None,
    preferred_tools: list[str] | None = None,
    forbidden_tools: list[str] | None = None,
    mandatory_deny: list[str] | None = None,
    read_only: bool = False,
    reasoning_strategy: str = "",
) -> str:
    """Build a concise '## Your capabilities and tools' section for an agent's system prompt."""
    lines: list[str] = ["## Your capabilities and tools\n"]

    if read_only:
        lines.append("**Access mode: READ-ONLY** — you cannot modify files or execute commands.\n")

    if specialization and specialization.strip():
        lines.append(f"**Specialization:** {specialization.strip()}")

    if capabilities:
        lines.append(f"**Capabilities:** {', '.join(capabilities)}")

    if preferred_tools:
        lines.append(f"**Preferred tools:** {', '.join(preferred_tools)}")

    unavailable = sorted(set((forbidden_tools or []) + (mandatory_deny or [])))
    if unavailable:
        lines.append(f"**Unavailable tools:** {', '.join(unavailable)}")

    if reasoning_strategy and reasoning_strategy.strip():
        hint = _REASONING_STRATEGY_HINTS.get(reasoning_strategy, "")
        hint_suffix = f" — {hint}" if hint else ""
        lines.append(f"**Reasoning approach:** {reasoning_strategy}{hint_suffix}")

    # Only return content if we added something beyond the header
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def build_unified_system_prompt(
    *,
    role: str,
    tool_hints: str,
    final_instructions: str,
    guardrails: str = "",
    platform_summary: str = "",
    current_datetime: str = "",
    reasoning_hint: str = "",
    agent_roster: str = "",
    capability_section: str = "",
    domain_reasoning: str = "",
) -> str:
    """Merge the 3 phase-specific prompts into a single unified system prompt.

    The resulting prompt gives the LLM full autonomy to decide *when* to plan,
    *which* tools to use, and *how* to formulate the final answer — without
    artificial phase boundaries.
    """
    sections: list[str] = []

    # 1. Identity & role
    sections.append(f"You are {role}, an autonomous AI assistant with access to tools.\n")

    # 2. Current date & time
    dt_str = current_datetime or _format_current_datetime()
    sections.append(f"## Current date & time\n{dt_str}\n")

    # 3. Working style — let LLM decide naturally
    sections.append(
        "## How you work\n"
        "- Analyse the user's request carefully.\n"
        "- If you already know the answer: respond directly — no tool use needed.\n"
        "- If you need information or must perform an action: use the available tools.\n"
        "- You may use multiple tools in sequence; after each tool result decide "
        "whether you need more tools or can answer.\n"
        "- Think step-by-step but do NOT announce your plan to the user unless asked.\n"
        "- For complex multi-step tasks, begin with an internal plan block:\n"
        "  <plan>\n"
        "  1. [Step description] -> [expected tool(s)]\n"
        "  2. [Step description] -> [expected tool(s)]\n"
        "  </plan>\n"
        "- The <plan> block is for system tracking only — omit it from your final answer.\n"
        "- For simple questions, skip the plan entirely.\n"
        "- If a step fails, reconsider your approach before continuing.\n"
        "- When asked to visualize, diagram, or chart something, use the `emit_visualization` tool "
        "with Mermaid syntax. This renders the diagram live in the user's UI. "
        "The mermaid source code is returned — you can embed it in markdown files "
        "using fenced code blocks (```mermaid ... ```) for persistent documents. "
        "Do NOT output raw Mermaid in chat — use the tool for rendering, write_file for saving.\n"
    )

    # 3.5 Agent-specific capabilities and tools
    if capability_section and capability_section.strip():
        sections.append(capability_section.strip() + "\n")

    # 3.6 Domain-specific reasoning framework
    if domain_reasoning and domain_reasoning.strip():
        sections.append(f"## Domain reasoning\n{domain_reasoning.strip()}\n")

    # 4. Available specialist agents (delegation roster)
    if agent_roster and agent_roster.strip():
        sections.append(f"## Available specialist agents\n{agent_roster.strip()}\n")

    # 5. When to search the web
    sections.append(
        "## When to search the web\n"
        "Use `web_search` BEFORE answering when the user's question involves:\n"
        "- Current events, news, recent developments (anything after your knowledge cutoff)\n"
        "- Software versions, release dates, changelogs\n"
        "- Prices, availability, stock, or any live data\n"
        "- People's current roles, recent actions, or latest statements\n"
        "- Any question containing 'latest', 'newest', 'current', 'today', 'recently'\n\n"
        "You MAY answer from model knowledge when:\n"
        "- The question is about well-established facts (math, physics, history)\n"
        "- The question is about code syntax, language features, or algorithms\n"
        "- The user explicitly says 'from what you know' or 'without searching'\n"
        "- The question is about the current project/workspace (use file tools instead)\n\n"
        "When in doubt: **search first, then verify against your knowledge.**\n"
        "State explicitly when your answer is based on model knowledge vs. search results.\n"
    )

    # 5. Tool hints (from tool_selector_prompt, trimmed)
    if tool_hints and tool_hints.strip():
        sections.append(f"## Tool guidelines\n{tool_hints.strip()}\n")

    # 6. Answer guidelines (from final_prompt)
    if final_instructions and final_instructions.strip():
        sections.append(f"## Answer guidelines\n{final_instructions.strip()}\n")

    # 7. Platform info
    if platform_summary and platform_summary.strip():
        sections.append(f"## Environment\n{platform_summary.strip()}\n")

    # 8. Guardrails & safety
    if guardrails and guardrails.strip():
        sections.append(f"## Safety rules\n{guardrails.strip()}\n")

    # 10. Reasoning hint (adaptive)
    if reasoning_hint and reasoning_hint.strip():
        sections.append(f"## Reasoning approach\n{reasoning_hint.strip()}\n")

    return "\n".join(sections)


# ──────────────────────────────────────────────────────────────────────
# AgentRunner
# ──────────────────────────────────────────────────────────────────────


class AgentRunner:
    """Continuous streaming tool loop — replaces HeadAgent.run()."""

    def __init__(
        self,
        *,
        client: LlmClient,
        memory: MemoryStore,
        tool_registry: ToolRegistry,
        tool_execution_manager: ToolExecutionManager,
        system_prompt: str,
        execute_tool_fn: Callable[..., Awaitable[str]],
        allowed_tools_resolver: Callable[[ToolPolicyDict | None], set[str]],
        guardrail_validator: Callable[..., None] | None = None,
        mcp_initializer: Callable[..., Awaitable[None]] | None = None,
        reflection_service: Any | None = None,
        emit_lifecycle_fn: Callable[..., Awaitable[None]] | None = None,
        intent_detector: Any | None = None,
        reply_shaper: Any | None = None,
        verification_service: Any | None = None,
        reflection_feedback_store: Any | None = None,
        agent_name: str = "agent",
        distill_fn: Callable[..., Awaitable[None]] | None = None,
        long_term_context_fn: Callable[[str], str] | None = None,
        policy_approval_fn: Callable[..., Awaitable[bool]] | None = None,
        debug_checkpoint_fn: Callable[..., Awaitable[None]] | None = None,
        max_reflections: int | None = None,
    ):
        self.client = client
        self.memory = memory
        self.tool_registry = tool_registry
        self._tool_execution_manager = tool_execution_manager
        self.system_prompt = system_prompt
        self._execute_tool_fn = execute_tool_fn
        self._allowed_tools_resolver = allowed_tools_resolver
        self._guardrail_validator = guardrail_validator
        self._mcp_initializer = mcp_initializer
        self._reflection_service = reflection_service
        self._emit_lifecycle = emit_lifecycle_fn
        self._intent_detector = intent_detector
        self._reply_shaper = reply_shaper
        self._verification_service = verification_service
        self._reflection_feedback_store = reflection_feedback_store
        self._agent_name = agent_name
        self._distill_fn = distill_fn
        self._long_term_context_fn = long_term_context_fn
        self._policy_approval_fn = policy_approval_fn
        self._debug_checkpoint_fn = debug_checkpoint_fn
        self._max_reflections = max_reflections
        self._compaction_service = CompactionService(client)

        # Loop limits from settings
        self._max_iterations = settings.runner_max_iterations
        self._max_tool_calls = settings.runner_max_tool_calls
        self._time_budget_seconds = settings.runner_time_budget_seconds
        self._loop_detection_threshold = settings.runner_loop_detection_threshold
        self._loop_detection_enabled = settings.runner_loop_detection_enabled
        self._compaction_enabled = settings.runner_compaction_enabled
        self._compaction_tail_keep = settings.runner_compaction_tail_keep
        self._tool_result_max_chars = settings.runner_tool_result_max_chars

    # ──────────────────────────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────────────────────────

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        should_steer_interrupt: Callable[[], bool] | None = None,
    ) -> str:
        # ═══════════════════════════════════════════
        # PRE-LOOP: Setup
        # ═══════════════════════════════════════════

        if self._emit_lifecycle:
            await self._emit_lifecycle(
                send_event,
                stage="runner_started",
                request_id=request_id,
                session_id=session_id,
                details={"model": model or self.client.model},
            )

        # Debug checkpoint: guardrails
        if self._debug_checkpoint_fn:
            await self._debug_checkpoint_fn("guardrails", send_event, request_id, session_id)

        # Guardrails
        if self._guardrail_validator:
            self._guardrail_validator(user_message, session_id, model)

        if self._emit_lifecycle:
            await self._emit_lifecycle(
                send_event,
                stage="guardrails_passed",
                request_id=request_id,
                session_id=session_id,
            )

        # MCP init
        if self._mcp_initializer:
            await self._mcp_initializer(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
            )

        # Debug checkpoint: context
        if self._debug_checkpoint_fn:
            await self._debug_checkpoint_fn("context", send_event, request_id, session_id)

        # Resolve allowed tools
        effective_allowed_tools = self._allowed_tools_resolver(tool_policy)

        # Memory
        self.memory.add(session_id, "user", user_message)
        self.memory.repair_orphaned_tool_calls(session_id)

        # Context reduction (single budget, not 3-way split)
        memory_items = self.memory.get_items(session_id)

        if self._emit_lifecycle:
            await self._emit_lifecycle(
                send_event,
                stage="memory_updated",
                request_id=request_id,
                session_id=session_id,
                details={"memory_items": len(memory_items)},
            )

        # ═══════════════════════════════════════════
        # BUILD MESSAGES
        # ═══════════════════════════════════════════

        messages = self._build_initial_messages(
            memory_items=memory_items,
            user_message=user_message,
        )

        # ═══════════════════════════════════════════
        # BUILD TOOL DEFINITIONS
        # ═══════════════════════════════════════════

        tool_definitions: list[dict] | None = self.tool_registry.build_function_calling_tools(
            allowed_tools=effective_allowed_tools,
        )
        if not tool_definitions:
            tool_definitions = None

        # ═══════════════════════════════════════════
        # PLANNING HINT (Point A)
        # ═══════════════════════════════════════════

        _planning_requested = False
        if settings.runner_planning_enabled and self._needs_planning(user_message):
            messages[-1]["content"] += "\n\n[SYSTEM HINT: This is a complex task. Start with a <plan> block.]"
            _planning_requested = True

        # ═══════════════════════════════════════════
        # CONTINUOUS LOOP
        # ═══════════════════════════════════════════

        loop_state = LoopState()
        start_time = time.monotonic()
        final_text = ""
        all_tool_results: list[ToolResult] = []

        while not loop_state.budget_exhausted:
            loop_state.iteration += 1

            # Safety: Max iterations
            if loop_state.iteration > self._max_iterations:
                loop_state.budget_exhausted = True
                break

            # Safety: Time budget
            loop_state.elapsed_seconds = time.monotonic() - start_time
            if loop_state.elapsed_seconds > self._time_budget_seconds:
                loop_state.budget_exhausted = True
                break

            # Safety: Steer interrupt
            if should_steer_interrupt and should_steer_interrupt():
                loop_state.steer_interrupted = True
                break

            # Debug checkpoint: agent_loop (before each LLM call)
            if self._debug_checkpoint_fn:
                await self._debug_checkpoint_fn("agent_loop", send_event, request_id, session_id)

            # ── LLM CALL ──
            # Proactive compaction: summarise before hitting context limit
            if self._compaction_enabled and self._compaction_service.needs_compaction(messages):
                try:
                    messages = await self._compaction_service.compact(messages)
                except Exception:
                    logger.debug("Proactive compaction failed", exc_info=True)

            if self._emit_lifecycle:
                await self._emit_lifecycle(
                    send_event,
                    stage="loop_iteration_started",
                    request_id=request_id,
                    session_id=session_id,
                    details={"iteration": loop_state.iteration},
                )

            _llm_t0 = time.monotonic()
            stream_result = await self.client.stream_chat_with_tools(
                messages=messages,
                tools=tool_definitions if not loop_state.budget_exhausted else None,
                model=model,
                on_text_chunk=lambda chunk: send_event({"type": "token", "agent": self._agent_name, "token": chunk}),
            )
            _llm_latency_ms = int((time.monotonic() - _llm_t0) * 1000)

            # Emit LLM telemetry with conversation content (always, not debug-gated)
            if self._emit_lifecycle:
                _usage = stream_result.usage or {}

                # Extract the last user/system message sent to the LLM
                _last_user_msg = ""
                _system_msg = ""
                for _m in reversed(messages):
                    if _m.get("role") == "user" and not _last_user_msg:
                        _last_user_msg = str(_m.get("content", ""))[:2000]
                    if _m.get("role") == "system" and not _system_msg:
                        _system_msg = str(_m.get("content", ""))[:2000]
                    if _last_user_msg and _system_msg:
                        break

                # Tool call names
                _tool_names = [tc.name for tc in stream_result.tool_calls] if stream_result.tool_calls else []

                await self._emit_lifecycle(
                    send_event,
                    stage="llm_call_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "model": model,
                        "iteration": loop_state.iteration,
                        "finish_reason": stream_result.finish_reason,
                        "latency_ms": _llm_latency_ms,
                        "input_tokens": _usage.get("prompt_tokens", _usage.get("input_tokens", 0)),
                        "output_tokens": _usage.get("completion_tokens", _usage.get("output_tokens", 0)),
                        "tool_calls_count": len(stream_result.tool_calls),
                        "tool_names": _tool_names,
                        "response_chars": len(stream_result.text or ""),
                        "response_text": (stream_result.text or "")[:3000],
                        "prompt_preview": _last_user_msg[:500],
                        "system_prompt_preview": _system_msg[:500],
                    },
                )

            # ── PLAN EXTRACTION (Point B) ──
            if _planning_requested and loop_state.iteration == 1 and stream_result.text:
                extracted_plan = self._extract_plan(stream_result.text)
                if extracted_plan.planning_active:
                    loop_state.plan = extracted_plan
                    if self._emit_lifecycle:
                        await self._emit_lifecycle(
                            send_event,
                            stage="plan_extracted",
                            request_id=request_id,
                            session_id=session_id,
                            details={
                                "steps": len(extracted_plan.steps),
                                "step_descriptions": [s.description for s in extracted_plan.steps],
                            },
                        )
                    # Emit plan progress as lightweight JSON (frontend renders CSS stepper)
                    if extracted_plan.planning_active and len(extracted_plan.steps) >= 2:
                        await send_event(build_plan_progress_event(
                            extracted_plan, request_id, session_id, self._agent_name,
                        ))

            # ── FINISH REASON: STOP → done ──
            if stream_result.finish_reason == "stop":
                final_text = stream_result.text
                # Strip plan block from final output
                if loop_state.plan.planning_active:
                    final_text = self._strip_plan_from_text(final_text)
                    # Mark remaining steps as completed and emit final progress
                    for step in loop_state.plan.steps:
                        if step.status in ("pending", "in_progress"):
                            step.status = "completed"
                    if len(loop_state.plan.steps) >= 2:
                        await send_event(build_plan_progress_event(
                            loop_state.plan, request_id, session_id, self._agent_name,
                        ))
                break

            # ── FINISH REASON: TOOL_CALLS → execute tools ──
            if stream_result.finish_reason == "tool_calls" and stream_result.tool_calls:
                # 1. Assistant message with tool_calls → history
                messages.append({
                    "role": "assistant",
                    "content": stream_result.text or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in stream_result.tool_calls
                    ],
                })

                # 2. Execute tools
                tool_results = await self._execute_tool_calls(
                    tool_calls=stream_result.tool_calls,
                    effective_allowed_tools=effective_allowed_tools,
                    send_event=send_event,
                    session_id=session_id,
                    request_id=request_id,
                )

                # 3. Tool results → history
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "content": result.content,
                    })
                    all_tool_results.append(result)

                # 3b. Store turn summary in memory for cross-session context
                if settings.memory_include_turn_summaries:
                    turn_summary = self._build_turn_summary(tool_results, loop_state.iteration)
                    self.memory.add(session_id, "turn_summary", turn_summary)

                # 4. Update loop state
                loop_state.total_tool_calls += len(tool_results)

                # 5. Budget check: max tool calls
                if loop_state.total_tool_calls > self._max_tool_calls:
                    loop_state.budget_exhausted = True
                    messages.append({
                        "role": "user",
                        "content": (
                            "[SYSTEM] Tool call budget exhausted. "
                            "Please provide your final answer now based on "
                            "what you have accomplished so far."
                        ),
                    })
                    tool_definitions = None
                    continue

                # 6. Loop detection
                if self._loop_detection_enabled and self._detect_tool_loop(
                    loop_state, stream_result.tool_calls
                ):
                    loop_state.loop_detected = True
                    messages.append({
                        "role": "user",
                        "content": (
                            "[SYSTEM] Loop detected — you are repeating "
                            "the same tool calls. Please try a different "
                            "approach or provide your answer."
                        ),
                    })
                    continue

                # 7. Plan progress tracking (Point C)
                if loop_state.plan.planning_active:
                    failed = [r for r in tool_results if r.is_error]
                    if failed and loop_state.plan.replan_count < settings.runner_planning_max_replans:
                        loop_state.plan.fail_current()
                        loop_state.plan.replan_count += 1
                        messages.append({
                            "role": "user",
                            "content": self._build_replan_message(loop_state.plan, failed),
                        })
                    else:
                        _prev_step_idx = loop_state.plan.current_step_index
                        self._update_plan_progress(loop_state.plan, tool_results)
                        # Re-emit plan progress when step advanced
                        if loop_state.plan.current_step_index != _prev_step_idx and len(loop_state.plan.steps) >= 2:
                            await send_event(build_plan_progress_event(
                                loop_state.plan, request_id, session_id, self._agent_name,
                            ))

                    # Periodic progress injection
                    if loop_state.iteration % settings.runner_planning_progress_interval == 0:
                        messages.append({
                            "role": "user",
                            "content": self._build_progress_context(loop_state.plan),
                        })

                # CONTINUE → next LLM call with tool results
                continue

            # ── FINISH REASON: LENGTH → context overflow ──
            if stream_result.finish_reason == "length":
                if self._compaction_enabled:
                    try:
                        messages = await self._compaction_service.compact(messages)
                    except Exception:
                        logger.debug("LLM compaction on overflow failed, using text fallback", exc_info=True)
                        messages = self._compact_messages(messages)
                    continue
                else:
                    loop_state.budget_exhausted = True
                    break

            # Unknown finish_reason → break safely
            if stream_result.text:
                final_text = stream_result.text
            break

        # ═══════════════════════════════════════════
        # POST-LOOP
        # ═══════════════════════════════════════════

        # Budget exhaustion fallback: force final answer without tools
        if loop_state.budget_exhausted and not final_text:
            try:
                stream_result = await self.client.stream_chat_with_tools(
                    messages=messages + [
                        {
                            "role": "user",
                            "content": (
                                "[SYSTEM] Please provide your final answer based on "
                                "what you have accomplished so far."
                            ),
                        }
                    ],
                    tools=None,
                    model=model,
                    on_text_chunk=lambda chunk: send_event({"type": "token", "agent": self._agent_name, "token": chunk}),
                )
                final_text = stream_result.text
            except Exception:
                logger.warning("Budget exhaustion fallback LLM call failed", exc_info=True)
                final_text = (
                    "I was unable to complete the request within the allowed budget. "
                    "Please try again or simplify your request."
                )

        # Steer interrupted fallback
        if loop_state.steer_interrupted and not final_text:
            final_text = "The request was interrupted by a new message."

        # Guard: ensure we have some text
        if not final_text:
            final_text = "I was unable to generate a response. Please try again."

        # ── POST-LOOP: Evidence Gates → Reflection → Reply Shaping → Verification ──

        # 1. Evidence gates
        final_text = self._apply_evidence_gates(
            final_text, all_tool_results, user_message, send_event, request_id, session_id,
        )

        # Debug checkpoint: reflection
        if self._debug_checkpoint_fn:
            await self._debug_checkpoint_fn("reflection", send_event, request_id, session_id)

        # 2. Reflection (before shaping — reflection sees unshaped text)
        if (
            self._reflection_service
            and settings.runner_reflection_enabled
            and len((final_text or "").strip()) >= 8
        ):
            final_text = await self._run_reflection(
                final_text=final_text,
                user_message=user_message,
                tool_results=all_tool_results,
                task_type=self._resolve_task_type(user_message, all_tool_results),
                model=model,
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                messages=messages,
                tool_definitions=tool_definitions,
                effective_allowed_tools=effective_allowed_tools,
            )
        elif self._reflection_service and settings.runner_reflection_enabled:
            if self._emit_lifecycle:
                await self._emit_lifecycle(
                    send_event,
                    stage="reflection_skipped",
                    request_id=request_id,
                    session_id=session_id,
                    details={"reason": "final_too_short", "final_chars": len((final_text or "").strip())},
                )

        # Debug checkpoint: reply_shaping
        if self._debug_checkpoint_fn:
            await self._debug_checkpoint_fn("reply_shaping", send_event, request_id, session_id)

        # 3. Reply shaping
        final_text = await self._shape_final_response(
            final_text, all_tool_results, send_event, request_id, session_id,
        )

        # 4. Verification (last check)
        if self._verification_service:
            final_check = self._verification_service.verify_final(
                user_message=user_message,
                final_text=final_text,
            )
            if self._emit_lifecycle:
                await self._emit_lifecycle(
                    send_event,
                    stage="verification_final",
                    request_id=request_id,
                    session_id=session_id,
                    details={
                        "status": final_check.status,
                        "reason": final_check.reason,
                        **final_check.details,
                    },
                )
            if not final_check.ok:
                final_text = "No output generated."

        # Final event
        await send_event({"type": "final", "agent": self._agent_name, "message": final_text})

        # Memory persistence
        self.memory.add(session_id, "assistant", final_text)

        # Session distillation (fire-and-forget, like legacy pipeline)
        if self._distill_fn is not None:
            import asyncio as _asyncio

            _user = user_message
            _tool_str = self._tool_results_to_string(all_tool_results)
            _final = final_text
            _model = model
            _sid = session_id

            # Build plan text from PlanTracker if available
            _plan_text = ""
            if loop_state.plan.planning_active and loop_state.plan.steps:
                step_lines = [f"{s.index}. {s.description} [{s.status}]" for s in loop_state.plan.steps]
                _plan_text = "\n".join(step_lines)

            async def _distill_bg() -> None:
                try:
                    await self._distill_fn(
                        session_id=_sid,
                        user_message=_user,
                        plan_text=_plan_text,
                        tool_results=_tool_str,
                        final_text=_final,
                        model=_model,
                    )
                except Exception:
                    logger.debug("Session distillation failed", exc_info=True)

            _asyncio.create_task(_distill_bg())

        if self._emit_lifecycle:
            await self._emit_lifecycle(
                send_event,
                stage="runner_completed",
                request_id=request_id,
                session_id=session_id,
                details={
                    "iterations": loop_state.iteration,
                    "total_tool_calls": loop_state.total_tool_calls,
                    "elapsed_seconds": round(time.monotonic() - start_time, 2),
                    "loop_detected": loop_state.loop_detected,
                    "budget_exhausted": loop_state.budget_exhausted,
                    "steer_interrupted": loop_state.steer_interrupted,
                    "plan_steps": len(loop_state.plan.steps),
                    "plan_completed": sum(1 for s in loop_state.plan.steps if s.status == "completed"),
                    "replan_count": loop_state.plan.replan_count,
                },
            )

        return final_text

    # ──────────────────────────────────────────────────────────────────
    # Initial messages builder
    # ──────────────────────────────────────────────────────────────────

    def _build_initial_messages(
        self,
        memory_items: list,
        user_message: str,
    ) -> list[dict]:
        messages: list[dict] = []

        # 1. System message (with optional LTM context)
        #    Refresh the date/time line on every request so the LLM always
        #    sees the current timestamp, not the one from server startup.
        system_content = re.sub(
            r"(?m)^## Current date & time\n.*\n",
            f"## Current date & time\n{_format_current_datetime()}\n",
            self.system_prompt,
        )
        if self._long_term_context_fn:
            try:
                ltm = self._long_term_context_fn(user_message)
                if ltm:
                    system_content += f"\n\n## Long-term context\n{ltm}"
            except Exception:
                logger.debug("LTM context retrieval failed", exc_info=True)
        messages.append({"role": "system", "content": system_content})

        # 2. Conversation history from memory (last N turns)
        for item in memory_items:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
            elif role == "turn_summary" and content and settings.memory_include_turn_summaries:
                messages.append({"role": "user", "content": f"[Previous tool context] {content}"})

        # 3. Current user message (skip if it was already the last item added)
        if not messages or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    # ──────────────────────────────────────────────────────────────────
    # Turn summary builder
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_turn_summary(tool_results: list[ToolResult], iteration: int) -> str:
        """Build a compact summary of a tool execution batch for memory persistence."""
        max_chars = settings.memory_turn_summary_max_chars
        tool_names = [tr.tool_name for tr in tool_results]
        ok = sum(1 for tr in tool_results if not tr.is_error)
        err = sum(1 for tr in tool_results if tr.is_error)
        snippets: list[str] = []
        for tr in tool_results:
            prefix = "[ERR] " if tr.is_error else ""
            snippets.append(f"{prefix}{tr.tool_name}: {tr.content[:80]}")
        snippet_text = "; ".join(snippets)
        summary = f"[Turn {iteration}] Tools: {', '.join(tool_names)} ({ok} ok, {err} err). {snippet_text}"
        return summary[:max_chars]

    # ──────────────────────────────────────────────────────────────────
    # Tool execution
    # ──────────────────────────────────────────────────────────────────

    _APPROVABLE_PROCESS_TOOLS = frozenset({"run_command", "code_execute", "spawn_subrun"})

    @staticmethod
    def _extract_resource_for_approval(tool_name: str, args: dict) -> str:
        """Extract a human-readable resource description from tool arguments."""
        if tool_name == "run_command":
            candidate = args.get("command")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        elif tool_name == "code_execute":
            code = args.get("code")
            lang = args.get("language")
            if isinstance(code, str) and code.strip():
                snippet = code.strip().splitlines()[0][:160]
                language = str(lang).strip() if isinstance(lang, str) else "python"
                return f"{language}: {snippet}"
        elif tool_name == "spawn_subrun":
            candidate = args.get("message")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return tool_name

    async def _execute_tool_calls(
        self,
        tool_calls: tuple[ToolCall, ...],
        effective_allowed_tools: set[str],
        send_event: SendEvent,
        session_id: str,
        request_id: str,
    ) -> list[ToolResult]:
        results: list[ToolResult] = []

        for tc in tool_calls:
            tool_name = tc.name.strip()

            # Policy check — prompt user for approvable process tools
            if tool_name not in effective_allowed_tools:
                if (
                    tool_name in self._APPROVABLE_PROCESS_TOOLS
                    and self._policy_approval_fn is not None
                ):
                    resource = self._extract_resource_for_approval(tool_name, tc.arguments)
                    try:
                        approved = await self._policy_approval_fn(
                            send_event=send_event,
                            session_id=session_id,
                            request_id=request_id,
                            tool=tool_name,
                            resource=resource,
                        )
                    except PolicyApprovalCancelledError:
                        raise
                    except Exception:
                        approved = False
                    if approved:
                        effective_allowed_tools.add(tool_name)
                    else:
                        results.append(ToolResult(
                            tool_call_id=tc.id,
                            tool_name=tool_name,
                            content=f"Error: Tool '{tool_name}' is blocked by policy. The user denied the approval request.",
                            is_error=True,
                        ))
                        continue
                else:
                    results.append(ToolResult(
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        content=f"Error: Tool '{tool_name}' is not in the allowed tools list.",
                        is_error=True,
                    ))
                    continue

            # Status event
            await send_event({
                "type": "tool_start",
                "agent": self._agent_name,
                "tool": tool_name,
                "tool_call_id": tc.id,
            })

            # Execute tool via the injected function
            start = time.monotonic()
            try:
                result_text = await self._execute_tool_fn(
                    tool_name=tool_name,
                    tool_args=tc.arguments,
                    session_id=session_id,
                    request_id=request_id,
                )
                is_error = False
            except PolicyApprovalCancelledError:
                raise
            except Exception as exc:
                result_text = f"Error executing {tool_name}: {exc}"
                is_error = True
                logger.warning("Tool execution failed: %s %s", tool_name, exc, exc_info=True)

            duration_ms = int((time.monotonic() - start) * 1000)

            # Emit emit_visualization result to frontend
            if tool_name == "emit_visualization" and not is_error:
                try:
                    viz_payload = json.loads(result_text)
                    if viz_payload.get("type") == "visualization":
                        viz_type = viz_payload.get("viz_type", "mermaid")
                        viz_code = viz_payload.get("code", "")
                        if viz_code:
                            if viz_type == "mermaid":
                                validate_mermaid_node_count(viz_code)
                                viz_code = sanitize_mermaid_labels(viz_code)
                            await send_event(build_visualization_event(
                                viz_type,
                                viz_code,
                                request_id,
                                session_id,
                                self._agent_name,
                            ))
                            title = viz_payload.get("title") or ""
                            result_text = (
                                f"Visualization ({viz_type}) rendered in the user's UI."
                            )
                            if title:
                                result_text += f" Title: {title}"
                            result_text += (
                                f"\n\nSource (for embedding in markdown files):\n```{viz_type}\n{viz_code}\n```"
                            )
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    result_text = f"Visualization failed: {exc}"
                    is_error = True

            # Emit screenshot visualization BEFORE truncation (base64 is huge)
            if tool_name == "browser_screenshot" and not is_error:
                try:
                    img_payload = json.loads(result_text)
                    if img_payload.get("type") == "image":
                        b64 = img_payload["data"]
                        fmt = img_payload.get("format", "png")
                        await send_event(build_visualization_event(
                            "image",
                            f"data:image/{fmt};base64,{b64}",
                            request_id,
                            session_id,
                            self._agent_name,
                        ))
                        # Replace with compact placeholder — LLM doesn't need raw base64
                        result_text = json.dumps({
                            "type": "image",
                            "format": fmt,
                            "status": "screenshot_captured",
                            "note": "Screenshot taken and displayed to user. Base64 data omitted from context.",
                        })
                except (json.JSONDecodeError, KeyError):
                    pass

            # Emit generated image visualization and auto-save to workspace
            if tool_name == "generate_image" and not is_error:
                try:
                    img_payload = json.loads(result_text)
                    if img_payload.get("type") == "image":
                        b64_data = img_payload["data"]
                        fmt = img_payload.get("format", "png")
                        # Display in frontend
                        await send_event(build_visualization_event(
                            "image",
                            f"data:image/{fmt};base64,{b64_data}",
                            request_id, session_id, self._agent_name,
                        ))
                        # Auto-save to workspace
                        import base64 as b64_mod
                        import uuid as _uuid
                        from pathlib import Path as _Path
                        img_dir = _Path(settings.workspace_root) / "generated_images"
                        img_dir.mkdir(parents=True, exist_ok=True)
                        filename = f"{_uuid.uuid4().hex[:12]}.{fmt}"
                        img_path = img_dir / filename
                        img_path.write_bytes(b64_mod.b64decode(b64_data))
                        result_text = json.dumps({
                            "type": "image",
                            "format": fmt,
                            "status": "generated_and_saved",
                            "saved_path": str(img_path),
                            "relative_path": f"generated_images/{filename}",
                            "note": "Image displayed to user and saved to disk.",
                        })
                except (json.JSONDecodeError, KeyError):
                    pass

            # Emit generated audio and auto-save to workspace
            if tool_name == "generate_audio" and not is_error:
                try:
                    audio_payload = json.loads(result_text)
                    if audio_payload.get("type") == "audio":
                        b64_data = audio_payload["data"]
                        fmt = audio_payload.get("format", "mp3")
                        # Display in frontend
                        await send_event(build_visualization_event(
                            "audio",
                            f"data:audio/{fmt};base64,{b64_data}",
                            request_id, session_id, self._agent_name,
                        ))
                        # Auto-save to workspace
                        import base64 as b64_mod
                        import uuid as _uuid
                        from pathlib import Path as _Path
                        audio_dir = _Path(settings.workspace_root) / "generated_audio"
                        audio_dir.mkdir(parents=True, exist_ok=True)
                        filename = f"{_uuid.uuid4().hex[:12]}.{fmt}"
                        audio_path = audio_dir / filename
                        audio_path.write_bytes(b64_mod.b64decode(b64_data))
                        result_text = json.dumps({
                            "type": "audio",
                            "format": fmt,
                            "status": "generated_and_saved",
                            "saved_path": str(audio_path),
                            "relative_path": f"generated_audio/{filename}",
                            "note": "Audio generated and saved to disk.",
                        })
                except (json.JSONDecodeError, KeyError):
                    pass

            # Truncate large results
            if len(result_text) > self._tool_result_max_chars:
                if settings.runner_smart_summarization_enabled:
                    result_text = self._smart_summarize_tool_result(tool_name, result_text)
                else:
                    half = self._tool_result_max_chars // 2
                    result_text = (
                        result_text[:half]
                        + "\n\n... (truncated) ...\n\n"
                        + result_text[-half:]
                    )

            # Result event
            await send_event({
                "type": "tool_end",
                "agent": self._agent_name,
                "tool": tool_name,
                "tool_call_id": tc.id,
                "duration_ms": duration_ms,
                "is_error": is_error,
            })

            results.append(ToolResult(
                tool_call_id=tc.id,
                tool_name=tool_name,
                content=result_text,
                is_error=is_error,
                duration_ms=duration_ms,
            ))

        return results

    # ──────────────────────────────────────────────────────────────────
    # Smart tool result summarization
    # ──────────────────────────────────────────────────────────────────

    def _smart_summarize_tool_result(self, tool_name: str, result_text: str) -> str:
        """Summarize a large tool result using per-tool-type strategies.

        Preserves the most useful parts of the output depending on the tool type,
        rather than blindly cutting at the midpoint.
        """
        lines = result_text.splitlines()
        total_lines = len(lines)
        budget = self._tool_result_max_chars

        if tool_name in ("read_file", "read_file_content"):
            # File reads: head lines (declarations/imports) + tail lines (recent context)
            head_n, tail_n = 40, 20
            head = "\n".join(lines[:head_n])
            tail = "\n".join(lines[-tail_n:])
            summary = (
                f"{head}\n\n... ({total_lines} total lines, showing first {head_n} + last {tail_n}) ...\n\n{tail}"
            )
        elif tool_name in ("run_command", "code_execute"):
            # Command output: errors typically at end, so tail-heavy
            head_n, tail_n = 10, 40
            head = "\n".join(lines[:head_n])
            tail = "\n".join(lines[-tail_n:])
            summary = (
                f"{head}\n\n... ({total_lines} total lines, showing first {head_n} + last {tail_n}) ...\n\n{tail}"
            )
        elif tool_name in ("web_search", "web_fetch"):
            # Web results: keep URLs, headings, and numbered items
            important_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if any(marker in stripped for marker in ("http://", "https://", "://", "##", "#")):
                    important_lines.append(line)
                elif re.match(r"^\d+[\.\)]\s", stripped):
                    important_lines.append(line)
                elif stripped.startswith(("-", "*")) and len(stripped) > 3:
                    important_lines.append(line)
            if important_lines:
                extracted = "\n".join(important_lines)
                if len(extracted) <= budget:
                    summary = f"(Extracted {len(important_lines)} key lines from {total_lines} total)\n{extracted}"
                else:
                    summary = f"(Extracted key lines, truncated from {total_lines} total)\n{extracted[:budget]}"
            else:
                # Fallback to head/tail
                half = budget // 2
                summary = result_text[:half] + f"\n\n... ({total_lines} lines truncated) ...\n\n" + result_text[-half:]
        elif tool_name in ("list_directory", "list_files"):
            # Directory listings: head + tail
            head_n, tail_n = 50, 20
            head = "\n".join(lines[:head_n])
            tail = "\n".join(lines[-tail_n:])
            summary = (
                f"{head}\n\n... ({total_lines} total entries, showing first {head_n} + last {tail_n}) ...\n\n{tail}"
            )
        else:
            # Default strategy: extract lines with identifiers/errors + head/tail
            priority_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                lowered = stripped.lower()
                if any(kw in lowered for kw in ("error", "exception", "warning", "fail", "traceback")):
                    priority_lines.append(line)
                elif re.match(r"^(def |class |function |import |from |export )", stripped):
                    priority_lines.append(line)
            head_n = 15
            tail_n = 15
            head = "\n".join(lines[:head_n])
            tail = "\n".join(lines[-tail_n:])
            priority_section = ""
            if priority_lines:
                priority_text = "\n".join(priority_lines[:20])
                priority_section = f"\n\n[Key lines]\n{priority_text}"
            summary = (
                f"{head}\n\n... ({total_lines} total lines) ...{priority_section}\n\n{tail}"
            )

        # Final budget enforcement
        if len(summary) > budget:
            half = budget // 2
            summary = summary[:half] + "\n\n... (truncated) ...\n\n" + summary[-half:]
        return summary

    # ──────────────────────────────────────────────────────────────────
    # Loop detection
    # ──────────────────────────────────────────────────────────────────

    def _detect_tool_loop(
        self,
        state: LoopState,
        tool_calls: tuple[ToolCall, ...],
    ) -> bool:
        """Detect if the agent is stuck in a loop.

        Three detectors:
        1. Identical Repeat — same tool call signature N times in a row
        2. Ping-Pong — alternating between 2 different call signatures (A→B→A→B)
        3. (No-Progress detector deferred to Sprint 2)
        """
        # Build current call signature
        current_sig = tuple(
            (tc.name, json.dumps(tc.arguments, sort_keys=True))
            for tc in tool_calls
        )
        state.tool_call_history.append({"sig": current_sig, "iteration": state.iteration})
        history = state.tool_call_history
        threshold = self._loop_detection_threshold

        # 1. Identical Repeat
        if len(history) >= threshold:
            recent = [h["sig"] for h in history[-threshold:]]
            if all(s == recent[0] for s in recent):
                logger.warning(
                    "Loop detected: identical tool calls repeated %d times", threshold
                )
                return True

        # 2. Ping-Pong (A→B→A→B)
        if len(history) >= 4:
            last4 = [h["sig"] for h in history[-4:]]
            if (
                last4[0] == last4[2]
                and last4[1] == last4[3]
                and last4[0] != last4[1]
            ):
                logger.warning("Loop detected: ping-pong pattern")
                return True

        return False

    # ──────────────────────────────────────────────────────────────────
    # Planning helpers
    # ──────────────────────────────────────────────────────────────────

    _COMPLEXITY_KEYWORDS = frozenset({
        "implement", "refactor", "debug", "configure", "migrate", "deploy",
        "optimize", "investigate", "analyse", "analyze", "integrate", "build",
        "create", "design", "restructure", "convert", "upgrade",
    })

    _PLAN_BLOCK_RE = re.compile(r"<plan>\s*(.*?)\s*</plan>", re.DOTALL | re.IGNORECASE)
    _PLAN_STEP_RE = re.compile(r"(\d+)\.\s*(.+?)(?:\s*->\s*(.+))?$", re.MULTILINE)

    def _needs_planning(self, user_message: str) -> bool:
        """Fast heuristic: does this message warrant a structured plan?

        Returns True when 2+ complexity signals are present.
        """
        msg = (user_message or "").strip()
        if not msg:
            return False

        signals = 0

        # Signal 1: 3+ sentences
        sentence_count = len(re.findall(r"[.!?]\s", msg)) + (1 if msg else 0)
        if sentence_count >= 3:
            signals += 1

        # Signal 2: Numbered/bulleted list
        if re.search(r"^\s*(?:\d+[.)]|-|\*)\s+", msg, re.MULTILINE):
            signals += 1

        # Signal 3: 2+ complexity keywords
        lowered = msg.lower()
        keyword_hits = sum(1 for kw in self._COMPLEXITY_KEYWORDS if kw in lowered)
        if keyword_hits >= 2:
            signals += 1

        # Signal 4: Long message
        if len(msg) > 200:
            signals += 1

        return signals >= 2

    @classmethod
    def _extract_plan(cls, text: str) -> PlanTracker:
        """Extract a <plan> block from LLM text into a PlanTracker."""
        match = cls._PLAN_BLOCK_RE.search(text)
        if not match:
            return PlanTracker(planning_active=False)

        raw = match.group(1)
        steps: list[PlanStep] = []
        for step_match in cls._PLAN_STEP_RE.finditer(raw):
            idx = int(step_match.group(1))
            desc = step_match.group(2).strip()
            tools_raw = (step_match.group(3) or "").strip()
            expected_tools = [t.strip() for t in tools_raw.split(",") if t.strip()] if tools_raw else []
            steps.append(PlanStep(index=idx, description=desc, expected_tools=expected_tools))

        if steps:
            steps[0].status = "in_progress"

        return PlanTracker(raw_plan_text=raw, steps=steps, planning_active=bool(steps))

    @staticmethod
    def _strip_plan_from_text(text: str) -> str:
        """Remove <plan>...</plan> blocks from text."""
        return re.sub(r"<plan>.*?</plan>\s*", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    @staticmethod
    def _update_plan_progress(plan: PlanTracker, tool_results: list[ToolResult]) -> None:
        """Advance the plan when expected tools completed successfully."""
        if not plan.planning_active or not plan.current_step:
            return
        step = plan.current_step
        successful_tools = {tr.tool_name for tr in tool_results if not tr.is_error}
        step.tool_calls_used.extend(successful_tools)
        if step.expected_tools:
            if any(t in successful_tools for t in step.expected_tools):
                plan.advance()
        elif successful_tools:
            plan.advance()

    @staticmethod
    def _build_replan_message(plan: PlanTracker, failed_results: list[ToolResult]) -> str:
        """Build a system message asking the LLM to reassess after failure."""
        failed_tools = ", ".join(f"{tr.tool_name}: {tr.content[:100]}" for tr in failed_results)
        current_desc = plan.current_step.description if plan.current_step else "unknown"
        return (
            f"[SYSTEM] Plan step failed: \"{current_desc}\"\n"
            f"Failed tools: {failed_tools}\n"
            "Reassess your approach. You may adjust the remaining plan or try an alternative."
        )

    @staticmethod
    def _build_progress_context(plan: PlanTracker) -> str:
        """Build a progress summary for injection into the conversation."""
        lines = ["[PLAN PROGRESS]"]
        for step in plan.steps:
            marker = {"completed": "[x]", "in_progress": "[>]", "failed": "[!]"}.get(step.status, "[ ]")
            lines.append(f"  {marker} {step.index}. {step.description}")
        completed = sum(1 for s in plan.steps if s.status == "completed")
        lines.append(f"  ({completed}/{len(plan.steps)} completed)")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────
    # Message compaction
    # ──────────────────────────────────────────────────────────────────

    def _compact_messages(self, messages: list[dict]) -> list[dict]:
        """Compact older messages when context overflows.

        Strategy:
        1. System message → always keep (index 0)
        2. Last N messages → always keep (tail_keep)
        3. Older tool results → truncate to head+tail snippet
        4. Older assistant messages → truncate
        5. User messages → keep as-is
        """
        tail_keep = self._compaction_tail_keep
        if len(messages) <= tail_keep + 2:
            return messages

        system = messages[0]
        rest = messages[1:]

        keep_tail = rest[-tail_keep:]
        to_compact = rest[:-tail_keep]

        compacted: list[dict] = []
        for msg in to_compact:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if len(content) > 500:
                    compacted.append({
                        **msg,
                        "content": content[:200] + "\n... (truncated) ...\n" + content[-100:],
                    })
                else:
                    compacted.append(msg)
            elif msg.get("role") == "assistant" and msg.get("content"):
                content = msg["content"]
                if len(content) > 300:
                    compacted.append({
                        **msg,
                        "content": content[:200] + "...",
                    })
                else:
                    compacted.append(msg)
            else:
                compacted.append(msg)

        return [system] + compacted + keep_tail

    # ──────────────────────────────────────────────────────────────────
    # Tool-result conversion
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _tool_results_to_string(tool_results: list[ToolResult]) -> str:
        """Convert ``list[ToolResult]`` to the legacy string format.

        Format per result::

            [tool_name] content          (success)
            [tool_name] [ERROR] content  (error)
        """
        if not tool_results:
            return ""
        lines: list[str] = []
        for tr in tool_results:
            prefix = f"[{tr.tool_name}]"
            if tr.is_error:
                lines.append(f"{prefix} [ERROR] {tr.content}")
            else:
                lines.append(f"{prefix} {tr.content}")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────
    # Task-type resolution
    # ──────────────────────────────────────────────────────────────────

    def _resolve_task_type(self, user_message: str, tool_results: list[ToolResult]) -> str:
        """Determine the synthesis task type from user intent + tool results.

        Returns one of: ``"hard_research"``, ``"research"``, ``"implementation"``,
        ``"orchestration"``, ``"orchestration_failed"``, ``"orchestration_pending"``,
        ``"general"``.
        """
        tool_results_str = self._tool_results_to_string(tool_results)
        message = (user_message or "").strip()

        # Evidence-first: spawned_subrun_id in tool results has absolute priority
        if "spawned_subrun_id=" in tool_results_str:
            terminal_statuses = [
                (m.start(), m.group(1))
                for m in re.finditer(
                    r"terminal_reason=(subrun-complete|subrun-error|subrun-timeout|subrun-cancelled|subrun-running|subrun-accepted)",
                    tool_results_str,
                )
            ]
            if terminal_statuses:
                _, last_status = max(terminal_statuses, key=lambda item: item[0])
                if last_status == "subrun-complete":
                    return "orchestration"
                if last_status in ("subrun-error", "subrun-timeout", "subrun-cancelled"):
                    return "orchestration_failed"
                return "orchestration_pending"

            if "subrun-complete" in tool_results_str:
                return "orchestration"
            if any(s in tool_results_str for s in ("subrun-error", "subrun-timeout", "subrun-cancelled")):
                return "orchestration_failed"
            return "orchestration_pending"

        # Intent-based classification (via IntentDetector when available)
        # NOTE: orchestration is classified purely by evidence (spawned_subrun_id
        # in tool results above), never by keyword matching.  The LLM decides
        # whether to delegate via spawn_subrun based on its system prompt.
        if self._intent_detector:
            if hasattr(self._intent_detector, "is_file_creation_task"):
                if self._intent_detector.is_file_creation_task(message):
                    return "implementation"
            if hasattr(self._intent_detector, "is_web_research_task"):
                if self._intent_detector.is_web_research_task(message):
                    return "research"

        # Regex fallback
        if _IMPLEMENTATION_RE.search(message):
            return "implementation"

        return "general"

    # ──────────────────────────────────────────────────────────────────
    # Evidence gates
    # ──────────────────────────────────────────────────────────────────

    def _apply_evidence_gates(
        self,
        final_text: str,
        tool_results: list[ToolResult],
        user_message: str,
        send_event: SendEvent | None = None,
        request_id: str = "",
        session_id: str = "",
    ) -> str:
        """Run evidence gates to prevent hallucinated success responses.

        Gates (in order):
        1. Implementation Evidence — blocks success claims when no code-edit tool succeeded
        2. All-Tools-Failed — blocks optimistic text when every tool errored
        3. Orchestration Evidence — blocks success claims when subrun did not complete
        """
        task_type = self._resolve_task_type(user_message, tool_results)

        # Gate 1: Implementation Evidence
        if self._requires_implementation_evidence(user_message, task_type):
            if not self._has_implementation_evidence(tool_results):
                if self._emit_lifecycle and send_event:
                    # fire-and-forget lifecycle event from sync context is not possible;
                    # lifecycle is emitted from the caller (run()) when needed.
                    pass
                final_text = (
                    "I could not complete the implementation in this run because no code-edit or command-execution "
                    "step succeeded. Please allow the required tools (for example `write_file`, `apply_patch`, "
                    "`run_command`, or `code_execute`) and retry."
                )

        # Gate 2: All-Tools-Failed
        if self._all_tools_failed(tool_results) and not self._response_acknowledges_failures(final_text):
            final_text = (
                "I was unable to complete this task. All tool calls encountered errors and no work "
                "was successfully performed in this run.\n\n"
                "Please check the tool error details above, resolve any permission or policy issues "
                "(for example, approve the requested commands via the policy dialog), and retry."
            )

        # Gate 3: Orchestration Evidence
        if task_type in ("orchestration", "orchestration_failed", "orchestration_pending"):
            if not self._has_orchestration_evidence(tool_results):
                attempted = self._has_orchestration_attempted(tool_results)
                if attempted:
                    final_text = (
                        "The delegated subrun did not complete successfully. "
                        "Most likely cause: a tool call inside the subrun timed out (e.g. a CLI scaffolding "
                        "command such as `npm`, `ng`, or `npx` exceeded COMMAND_TIMEOUT_SECONDS) or was "
                        "blocked by the command allowlist. "
                        "Check the subrun lifecycle events for `tool_timeout` or `command_policy_unsupported` "
                        "errors. If commands are blocked, set COMMAND_ALLOWLIST_EXTRA in the environment or "
                        "approve the command via the policy dialog. "
                        "If the subrun succeeded but this message still appears, the subrun returned before "
                        "the parent could read its result — this is now fixed in the current build."
                    )
                # else: LLM chose not to delegate — keep its response as-is

        return final_text

    # ── Evidence gate helpers ──

    def _requires_implementation_evidence(self, user_message: str, task_type: str) -> bool:
        if task_type == "implementation":
            return True
        if self._intent_detector and hasattr(self._intent_detector, "is_file_creation_task"):
            return self._intent_detector.is_file_creation_task(user_message)
        return False

    def _has_implementation_evidence(self, tool_results: list[ToolResult]) -> bool:
        evidence_tools = ("write_file", "apply_patch", "run_command", "code_execute")
        return any(
            tr.tool_name in evidence_tools and not tr.is_error
            for tr in tool_results
        )

    @staticmethod
    def _all_tools_failed(tool_results: list[ToolResult]) -> bool:
        if not tool_results:
            return False
        return all(tr.is_error for tr in tool_results)

    @staticmethod
    def _response_acknowledges_failures(final_text: str) -> bool:
        lowered = (final_text or "").lower()
        acknowledgement_phrases = (
            "error", "fail", "unable", "could not", "cannot", "can't",
            "couldn't", "not able", "not allowed", "blocked", "policy",
            "permission", "denied", "unsuccessful", "not complete",
            "unfortunately", "did not succeed", "did not complete", "was not",
        )
        return any(phrase in lowered for phrase in acknowledgement_phrases)

    def _has_orchestration_evidence(self, tool_results: list[ToolResult]) -> bool:
        combined = self._tool_results_to_string(tool_results)
        if "spawned_subrun_id=" in combined and "subrun-complete" in combined:
            return True
        return bool("subrun_announce" in combined and "subrun-complete" in combined)

    def _has_orchestration_attempted(self, tool_results: list[ToolResult]) -> bool:
        combined = self._tool_results_to_string(tool_results)
        return "spawned_subrun_id=" in combined

    # ──────────────────────────────────────────────────────────────────
    # Reply shaping
    # ──────────────────────────────────────────────────────────────────

    async def _shape_final_response(
        self,
        final_text: str,
        tool_results: list[ToolResult],
        send_event: SendEvent | None = None,
        request_id: str = "",
        session_id: str = "",
    ) -> str:
        """Shape the final response using ReplyShaper (sanitize + deduplicate)."""
        if not self._reply_shaper:
            if self._emit_lifecycle and send_event:
                await self._emit_lifecycle(
                    send_event, stage="reply_shaping_skipped",
                    request_id=request_id, session_id=session_id,
                    details={"reason": "no_reply_shaper"},
                )
            return final_text

        if self._emit_lifecycle and send_event:
            await self._emit_lifecycle(
                send_event, stage="reply_shaping_started",
                request_id=request_id, session_id=session_id,
            )

        tool_results_str = self._tool_results_to_string(tool_results)
        tool_markers: set[str] = set()
        if hasattr(self.tool_registry, "keys"):
            tool_markers = set(self.tool_registry.keys())

        shape_result = self._reply_shaper.shape(
            final_text=final_text,
            tool_results=tool_results_str,
            tool_markers=tool_markers,
        )

        shaped_text = shape_result.text
        if shape_result.was_suppressed:
            shaped_text = shape_result.text or f"Reply suppressed: {shape_result.suppression_reason or 'suppressed'}"

        if self._emit_lifecycle and send_event:
            await self._emit_lifecycle(
                send_event, stage="reply_shaping_completed",
                request_id=request_id, session_id=session_id,
                details={
                    "was_suppressed": shape_result.was_suppressed,
                    "input_chars": len(final_text),
                    "output_chars": len(shaped_text),
                },
            )

        return shaped_text

    # ──────────────────────────────────────────────────────────────────
    # Reflection loop
    # ──────────────────────────────────────────────────────────────────

    async def _run_reflection(
        self,
        final_text: str,
        user_message: str,
        tool_results: list[ToolResult],
        task_type: str,
        model: str | None,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
        messages: list[dict],
        tool_definitions: list[dict] | None = None,
        effective_allowed_tools: set[str] | None = None,
    ) -> str:
        """Run post-loop reflection passes.

        The ReflectionService evaluates the answer on goal_alignment, completeness
        and factual_grounding.  When ``should_retry`` is True a follow-up LLM call
        with reflection feedback is made (without tools).
        """
        tool_results_str = self._tool_results_to_string(tool_results)
        max_passes = max(0, self._max_reflections if self._max_reflections is not None else settings.runner_reflection_max_passes)

        for reflection_pass in range(max_passes):
            try:
                try:
                    verdict = await self._reflection_service.reflect(
                        user_message=user_message,
                        plan_text="",
                        tool_results=tool_results_str,
                        final_answer=final_text,
                        model=model,
                        task_type=task_type,
                    )
                except TypeError:
                    # Fallback for older ReflectionService without task_type param
                    verdict = await self._reflection_service.reflect(
                        user_message=user_message,
                        plan_text="",
                        tool_results=tool_results_str,
                        final_answer=final_text,
                        model=model,
                    )
            except Exception as exc:
                logger.warning("Reflection pass %d failed: %s", reflection_pass + 1, exc, exc_info=True)
                if self._emit_lifecycle:
                    await self._emit_lifecycle(
                        send_event,
                        stage="reflection_failed",
                        request_id=request_id,
                        session_id=session_id,
                        details={"pass": reflection_pass + 1, "error": str(exc)},
                    )
                break

            if self._emit_lifecycle:
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

            # Store reflection record
            if self._reflection_feedback_store is not None:
                try:
                    from app.services.reflection_feedback_store import ReflectionRecord

                    self._reflection_feedback_store.store(
                        ReflectionRecord(
                            record_id=f"{request_id}-reflection-{reflection_pass + 1}",
                            session_id=session_id,
                            request_id=request_id,
                            task_type=task_type,
                            score=verdict.score,
                            goal_alignment=verdict.goal_alignment,
                            completeness=verdict.completeness,
                            factual_grounding=verdict.factual_grounding,
                            issues=list(verdict.issues),
                            suggested_fix=verdict.suggested_fix,
                            model_id=model or settings.llm_model,
                            prompt_variant="unified",
                            retry_triggered=verdict.should_retry,
                            timestamp_utc=datetime.now(UTC).isoformat(),
                        )
                    )
                except Exception:
                    logger.debug("Failed to store reflection record", exc_info=True)

            if not verdict.should_retry:
                break

            # Build feedback and retry via LLM
            feedback_lines = [issue for issue in verdict.issues if issue]
            if verdict.suggested_fix:
                feedback_lines.append(f"Suggested fix: {verdict.suggested_fix}")
            feedback = "\n".join(feedback_lines).strip() or "No specific issues provided."

            # Decide: tool-enabled retry vs text-only retry
            use_tool_retry = (
                settings.runner_reflection_tool_retry_enabled
                and verdict.completeness < 0.5
                and tool_definitions is not None
            )

            if use_tool_retry:
                # Tool-enabled retry: let the LLM gather missing information
                messages.append({
                    "role": "user",
                    "content": (
                        f"[REFLECTION FEEDBACK]\n{feedback}\n\n"
                        "Your answer is incomplete. Use the available tools to gather "
                        "the missing information, then provide a revised answer."
                    ),
                })
                try:
                    # Mini tool loop (max 3 iterations)
                    for _retry_iter in range(3):
                        stream_result = await self.client.stream_chat_with_tools(
                            messages=messages,
                            tools=tool_definitions,
                            model=model,
                            on_text_chunk=lambda chunk: send_event({"type": "token", "agent": self._agent_name, "token": chunk}),
                        )
                        if stream_result.finish_reason == "stop":
                            final_text = stream_result.text
                            break
                        if stream_result.finish_reason == "tool_calls" and stream_result.tool_calls:
                            messages.append({
                                "role": "assistant",
                                "content": stream_result.text or None,
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": tc.name,
                                            "arguments": json.dumps(tc.arguments),
                                        },
                                    }
                                    for tc in stream_result.tool_calls
                                ],
                            })
                            retry_tool_results = await self._execute_tool_calls(
                                tool_calls=stream_result.tool_calls,
                                effective_allowed_tools=effective_allowed_tools or set(),
                                send_event=send_event,
                                session_id=session_id,
                                request_id=request_id,
                            )
                            for rtr in retry_tool_results:
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": rtr.tool_call_id,
                                    "content": rtr.content,
                                })
                            continue
                        # Unknown finish reason
                        if stream_result.text:
                            final_text = stream_result.text
                        break
                except Exception:
                    logger.warning("Reflection tool-enabled retry failed", exc_info=True)
                    break
            else:
                # Text-only retry (original behavior)
                messages.append({
                    "role": "user",
                    "content": f"[REFLECTION FEEDBACK]\n{feedback}\n\nPlease revise your answer.",
                })
                try:
                    stream_result = await self.client.stream_chat_with_tools(
                        messages=messages,
                        tools=None,
                        model=model,
                        on_text_chunk=lambda chunk: send_event({"type": "token", "agent": self._agent_name, "token": chunk}),
                    )
                    final_text = stream_result.text
                except Exception:
                    logger.warning("Reflection retry LLM call failed", exc_info=True)
                    break

        return final_text
