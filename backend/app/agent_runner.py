"""AgentRunner — Continuous Streaming Tool Loop.

Replaces the 3-phase pipeline (Planner → ToolSelector → Synthesizer) with a
single continuous loop where the LLM decides when to use tools and when to
answer.  Activated via ``USE_CONTINUOUS_LOOP=true`` feature flag.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent_runner_types import LoopState, StreamResult, ToolCall, ToolResult
from app.config import settings
from app.llm_client import LlmClient
from app.memory import MemoryStore
from app.services.tool_execution_manager import ToolExecutionManager
from app.services.tool_registry import ToolRegistry
from app.state.context_reducer import ContextReducer
from app.tool_policy import ToolPolicyDict

logger = logging.getLogger("app.agent_runner")

SendEvent = Callable[[dict], Awaitable[None]]


# ──────────────────────────────────────────────────────────────────────
# Unified System Prompt Builder
# ──────────────────────────────────────────────────────────────────────


def build_unified_system_prompt(
    *,
    role: str,
    plan_prompt: str,
    tool_hints: str,
    final_instructions: str,
    guardrails: str = "",
    skills_prompt: str = "",
    platform_summary: str = "",
) -> str:
    """Merge the 3 phase-specific prompts into a single unified system prompt.

    The resulting prompt gives the LLM full autonomy to decide *when* to plan,
    *which* tools to use, and *how* to formulate the final answer — without
    artificial phase boundaries.
    """
    sections: list[str] = []

    # 1. Identity & role (extracted from plan_prompt preamble)
    sections.append(f"You are {role}, an autonomous AI assistant with access to tools.\n")

    # 2. Working style — let LLM decide naturally
    sections.append(
        "## How you work\n"
        "- Analyse the user's request carefully.\n"
        "- If you already know the answer: respond directly — no tool use needed.\n"
        "- If you need information or must perform an action: use the available tools.\n"
        "- You may use multiple tools in sequence; after each tool result decide "
        "whether you need more tools or can answer.\n"
        "- Think step-by-step but do NOT announce your plan to the user unless asked.\n"
    )

    # 3. Tool hints (from tool_selector_prompt, trimmed)
    if tool_hints and tool_hints.strip():
        sections.append(f"## Tool guidelines\n{tool_hints.strip()}\n")

    # 4. Answer guidelines (from final_prompt)
    if final_instructions and final_instructions.strip():
        sections.append(f"## Answer guidelines\n{final_instructions.strip()}\n")

    # 5. Platform info
    if platform_summary and platform_summary.strip():
        sections.append(f"## Environment\n{platform_summary.strip()}\n")

    # 6. Skills
    if skills_prompt and skills_prompt.strip():
        sections.append(f"## Active skills\n{skills_prompt.strip()}\n")

    # 7. Guardrails & safety
    if guardrails and guardrails.strip():
        sections.append(f"## Safety rules\n{guardrails.strip()}\n")

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
        context_reducer: ContextReducer,
        system_prompt: str,
        execute_tool_fn: Callable[..., Awaitable[str]],
        allowed_tools_resolver: Callable[[ToolPolicyDict | None], set[str]],
        guardrail_validator: Callable[..., None] | None = None,
        mcp_initializer: Callable[..., Awaitable[None]] | None = None,
        ambiguity_detector: Any | None = None,
        reflection_service: Any | None = None,
        emit_lifecycle_fn: Callable[..., Awaitable[None]] | None = None,
    ):
        self.client = client
        self.memory = memory
        self.tool_registry = tool_registry
        self._tool_execution_manager = tool_execution_manager
        self.context_reducer = context_reducer
        self.system_prompt = system_prompt
        self._execute_tool_fn = execute_tool_fn
        self._allowed_tools_resolver = allowed_tools_resolver
        self._guardrail_validator = guardrail_validator
        self._mcp_initializer = mcp_initializer
        self._ambiguity_detector = ambiguity_detector
        self._reflection_service = reflection_service
        self._emit_lifecycle = emit_lifecycle_fn

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

        # Guardrails
        if self._guardrail_validator:
            self._guardrail_validator(user_message, session_id, model)

        # MCP init
        if self._mcp_initializer:
            await self._mcp_initializer(
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
            )

        # Resolve allowed tools
        effective_allowed_tools = self._allowed_tools_resolver(tool_policy)

        # Memory
        self.memory.add(session_id, "user", user_message)
        self.memory.repair_orphaned_tool_calls(session_id)

        # Context reduction (single budget, not 3-way split)
        memory_items = self.memory.get_items(session_id)

        # Ambiguity detection → early return
        if self._ambiguity_detector and settings.clarification_protocol_enabled:
            try:
                ambiguity = self._ambiguity_detector.assess(user_message)
                if (
                    hasattr(ambiguity, "is_ambiguous")
                    and ambiguity.is_ambiguous
                    and hasattr(ambiguity, "confidence")
                    and ambiguity.confidence < settings.clarification_confidence_threshold
                ):
                    clarification = getattr(ambiguity, "clarification_question", "")
                    if clarification:
                        await send_event({"type": "final", "message": clarification})
                        self.memory.add(session_id, "assistant", clarification)
                        return clarification
            except Exception:
                logger.debug("Ambiguity detection skipped due to error", exc_info=True)

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

            # ── LLM CALL ──
            if self._emit_lifecycle:
                await self._emit_lifecycle(
                    send_event,
                    stage="loop_iteration_started",
                    request_id=request_id,
                    session_id=session_id,
                    details={"iteration": loop_state.iteration},
                )

            stream_result = await self.client.stream_chat_with_tools(
                messages=messages,
                tools=tool_definitions if not loop_state.budget_exhausted else None,
                model=model,
                on_text_chunk=lambda chunk: send_event({"type": "stream", "content": chunk}),
            )

            # ── FINISH REASON: STOP → done ──
            if stream_result.finish_reason == "stop":
                final_text = stream_result.text
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

                # CONTINUE → next LLM call with tool results
                continue

            # ── FINISH REASON: LENGTH → context overflow ──
            if stream_result.finish_reason == "length":
                if self._compaction_enabled:
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
                    on_text_chunk=lambda chunk: send_event({"type": "stream", "content": chunk}),
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

        # Evidence gates (stub — full migration in Sprint 2, Phase C)
        final_text = self._apply_evidence_gates(final_text, all_tool_results, user_message)

        # Reply shaping (stub — full migration in Sprint 2, Phase C)
        final_text = self._shape_final_response(final_text, all_tool_results)

        # Final event
        await send_event({"type": "final", "message": final_text})

        # Memory persistence
        self.memory.add(session_id, "assistant", final_text)

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

        # 1. System message
        messages.append({"role": "system", "content": self.system_prompt})

        # 2. Conversation history from memory (last N turns)
        for item in memory_items:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # 3. Current user message (skip if it was already the last item added)
        if not messages or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    # ──────────────────────────────────────────────────────────────────
    # Tool execution
    # ──────────────────────────────────────────────────────────────────

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

            # Policy check
            if tool_name not in effective_allowed_tools:
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
            except Exception as exc:
                result_text = f"Error executing {tool_name}: {exc}"
                is_error = True
                logger.warning("Tool execution failed: %s %s", tool_name, exc, exc_info=True)

            duration_ms = int((time.monotonic() - start) * 1000)

            # Truncate large results
            if len(result_text) > self._tool_result_max_chars:
                half = self._tool_result_max_chars // 2
                result_text = (
                    result_text[:half]
                    + "\n\n... (truncated) ...\n\n"
                    + result_text[-half:]
                )

            # Result event
            await send_event({
                "type": "tool_end",
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
    # Evidence gates & reply shaping (stubs — Phase C migration)
    # ──────────────────────────────────────────────────────────────────

    def _apply_evidence_gates(
        self,
        final_text: str,
        tool_results: list[ToolResult],
        user_message: str,
    ) -> str:
        """Stub — full evidence gate migration happens in Sprint 2 (Phase C)."""
        return final_text

    def _shape_final_response(
        self,
        final_text: str,
        tool_results: list[ToolResult],
    ) -> str:
        """Stub — full reply shaping migration happens in Sprint 2 (Phase C)."""
        return final_text
