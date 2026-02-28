from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Callable, Awaitable, ClassVar

from app.config import settings
from app.errors import GuardrailViolation, LlmClientError, ToolExecutionError
from app.llm_client import LlmClient
from app.memory import MemoryStore
from app.tools import AgentTooling

logger = logging.getLogger(__name__)

SendEvent = Callable[[dict], Awaitable[None]]
ALLOWED_TOOLS = {"list_dir", "read_file", "write_file", "run_command"}
TOOL_NAME_ALIASES = {
    "createfile": "write_file",
    "writefile": "write_file",
    "readfile": "read_file",
    "listdir": "list_dir",
    "runcommand": "run_command",
}

# Pre-compiled patterns & tuneable constants (override via settings where applicable)
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
TOOL_RESULT_CLIP_CHARS: int = 6_000
PLAN_PREVIEW_CHARS: int = 220
JSON_CANDIDATE_MAX_CHARS: int = 3_000
MAX_TOOL_CALLS: int = 3
ACTION_REJECTION_PREVIEW_MAX: int = 5
EXPLORATION_TOOLS: frozenset[str] = frozenset({"list_dir", "read_file"})
IMPLEMENTATION_CREATE_TOOLS: frozenset[str] = frozenset({"read_file", "write_file", "run_command"})
MAX_EXPLORATION_PASSES: int = 2
# Frozenset of allowed model names.  Empty = allow all (backward-compatible default).
_ALLOWED_MODELS: frozenset[str] = frozenset(
    m.strip() for m in settings.allowed_models_csv.split(",") if m.strip()
)
_TOOL_EXECUTION_MODES = {"parallel", "sequential"}


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
class ToolSelectionResult:
    actions: list[dict]
    mode: str
    parse_error: str | None


@dataclass(frozen=True)
class TaskTriage:
    needs_exploration: bool
    needs_evidence_gate: bool
    create_intent: bool
    reason: str
    required_evidence_types: tuple[str, ...]
    confidence: float
    risk_level: str


class HeadCodingAgent:
    # Built once at class load time – settings is a module-level singleton so values are stable.
    _TOOL_REGISTRY: ClassVar[dict[str, ToolSpec]] = {
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
    }
    # Shared executor with a bounded pool to avoid exhausting the default thread pool
    # under high concurrency. Max workers = 3 tools × N concurrent requests.
    _executor: ClassVar[ThreadPoolExecutor] = ThreadPoolExecutor(
        max_workers=12, thread_name_prefix="agent-tool"
    )

    def __init__(self):
        self.name = settings.agent_name
        self.role = "coding-head-agent"
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
        self._client_lock = threading.Lock()

    def configure_runtime(self, base_url: str, model: str) -> None:
        with self._client_lock:
            self.client = LlmClient(
                base_url=base_url,
                model=model,
            )

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
    ) -> str:
        run_started_at = time.perf_counter()
        # Snapshot the client at request start so a concurrent configure_runtime call
        # does not affect an in-flight request.
        with self._client_lock:
            client = self.client

        logger.info(
            "run started",
            extra={"request_id": request_id, "session_id": session_id, "model": model or client.model},
        )
        await self._emit_lifecycle(
            send_event,
            stage="run_started",
            request_id=request_id,
            session_id=session_id,
            details={"model": model or client.model},
        )

        self._validate_guardrails(user_message=user_message, session_id=session_id, model=model)
        await self._emit_lifecycle(
            send_event,
            stage="guardrails_passed",
            request_id=request_id,
            session_id=session_id,
        )

        memory_context = await self._prepare_context(
            user_message=user_message,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
        )

        triage = self._triage_task(user_message)
        await self._emit_lifecycle(
            send_event,
            stage="task_triage_completed",
            request_id=request_id,
            session_id=session_id,
            details={
                "needs_exploration": triage.needs_exploration,
                "needs_evidence_gate": triage.needs_evidence_gate,
                "create_intent": triage.create_intent,
                "reason": triage.reason,
                "required_evidence_types": list(triage.required_evidence_types),
                "confidence": triage.confidence,
                "risk_level": triage.risk_level,
            },
        )

        exploration_plan_text = ""

        exploration_results = ""
        exploration_metrics: dict = {
            "parse_failed": False,
            "repaired": False,
            "requested_actions": 0,
            "accepted_actions": 0,
            "rejected_actions": 0,
            "tool_errors": 0,
            "execution_mode": "parallel",
        }
        missing_evidence: list[str] = list(triage.required_evidence_types)
        if triage.needs_exploration:
            await send_event(
                {
                    "type": "status",
                    "agent": self.name,
                    "message": "Building exploration plan (V1) before implementation planning (V2).",
                }
            )

            exploration_plan_text = await self._create_plan(
                user_message=user_message,
                memory_context=memory_context,
                evidence_context="",
                client=client,
                model=model,
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                phase="exploration",
                compact=False,
                triage=triage,
            )
            self.memory.add(session_id, "plan:exploration", exploration_plan_text)
            await send_event(
                {
                    "type": "agent_step",
                    "agent": self.name,
                    "step": f"Exploration plan (V1): {exploration_plan_text[:PLAN_PREVIEW_CHARS]}",
                }
            )

        if triage.needs_exploration:
            exploration_results, exploration_metrics = await self._execute_tools(
                user_message=user_message,
                plan_text=exploration_plan_text,
                memory_context=memory_context,
                client=client,
                session_id=session_id,
                request_id=request_id,
                send_event=send_event,
                model=model,
                allowed_tools=EXPLORATION_TOOLS,
                phase="exploration",
            )

            coverage = self._assess_evidence_coverage(
                tool_results=exploration_results,
                required_evidence_types=triage.required_evidence_types,
            )
            missing_evidence = coverage["missing"]
            await self._emit_lifecycle(
                send_event,
                stage="evidence_coverage_checked",
                request_id=request_id,
                session_id=session_id,
                details=coverage,
            )

            exploration_pass = 1
            while missing_evidence and exploration_pass < MAX_EXPLORATION_PASSES:
                exploration_pass += 1
                await send_event(
                    {
                        "type": "status",
                        "agent": self.name,
                        "message": "Evidence incomplete; running focused exploration reads.",
                    }
                )
                focused_plan_text = self._build_focused_exploration_plan(
                    user_message=user_message,
                    triage=triage,
                    missing_evidence=missing_evidence,
                )
                focused_results, focused_metrics = await self._execute_tools(
                    user_message=user_message,
                    plan_text=focused_plan_text,
                    memory_context=memory_context,
                    client=client,
                    session_id=session_id,
                    request_id=request_id,
                    send_event=send_event,
                    model=model,
                    allowed_tools=EXPLORATION_TOOLS,
                    phase="exploration_followup",
                )
                exploration_results = "\n\n".join(
                    section for section in (exploration_results, focused_results) if section
                )
                exploration_metrics = self._merge_tool_metrics(exploration_metrics, focused_metrics)
                coverage = self._assess_evidence_coverage(
                    tool_results=exploration_results,
                    required_evidence_types=triage.required_evidence_types,
                )
                missing_evidence = coverage["missing"]
                await self._emit_lifecycle(
                    send_event,
                    stage="evidence_coverage_checked",
                    request_id=request_id,
                    session_id=session_id,
                    details=coverage,
                )
        else:
            await send_event(
                {
                    "type": "status",
                    "agent": self.name,
                    "message": "Exploration skipped; using compact implementation plan (V2).",
                }
            )
            if triage.create_intent:
                await send_event(
                    {
                        "type": "status",
                        "agent": self.name,
                        "message": "Create-intent detected; running a minimal exploration pass.",
                    }
                )
                exploration_results, exploration_metrics = await self._execute_tools(
                    user_message=user_message,
                    plan_text="Minimal exploration: run list_dir to discover candidate target paths.",
                    memory_context=memory_context,
                    client=client,
                    session_id=session_id,
                    request_id=request_id,
                    send_event=send_event,
                    model=model,
                    allowed_tools=EXPLORATION_TOOLS,
                    phase="exploration_bootstrap",
                )
            missing_evidence = []

        await send_event(
            {
                "type": "status",
                "agent": self.name,
                "message": "Building implementation plan (V2) grounded in exploration outputs.",
            }
        )

        implementation_plan_text = await self._create_plan(
            user_message=user_message,
            memory_context=memory_context,
            evidence_context=exploration_results,
            client=client,
            model=model,
            send_event=send_event,
            request_id=request_id,
            session_id=session_id,
            phase="implementation",
            compact=not triage.needs_exploration,
            triage=triage,
        )
        self.memory.add(session_id, "plan", implementation_plan_text)
        await send_event(
            {
                "type": "agent_step",
                "agent": self.name,
                "step": f"Implementation plan (V2): {implementation_plan_text[:PLAN_PREVIEW_CHARS]}",
            }
        )

        implementation_allowed_tools = (
            IMPLEMENTATION_CREATE_TOOLS if triage.create_intent else None
        )
        implementation_results, implementation_metrics = await self._execute_tools(
            user_message=user_message,
            plan_text=implementation_plan_text,
            memory_context=memory_context,
            client=client,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=implementation_allowed_tools,
            phase="implementation",
        )

        if triage.create_intent and not self._has_successful_tool_result(implementation_results, "write_file"):
            fallback_action = self._build_bootstrap_action(user_message)
            if fallback_action is not None:
                await send_event(
                    {
                        "type": "status",
                        "agent": self.name,
                        "message": "No implementation actions selected; applying deterministic bootstrap write.",
                    }
                )
                fallback_result, fallback_error = await self._run_single_action(
                    idx=1,
                    action=fallback_action,
                    session_id=session_id,
                    request_id=request_id,
                    send_event=send_event,
                )
                implementation_results = "\n\n".join(
                    section for section in (implementation_results, fallback_result) if section
                )
                implementation_metrics["requested_actions"] = int(implementation_metrics.get("requested_actions", 0)) + 1
                implementation_metrics["accepted_actions"] = int(implementation_metrics.get("accepted_actions", 0)) + 1
                if fallback_error:
                    implementation_metrics["tool_errors"] = int(implementation_metrics.get("tool_errors", 0)) + 1

        if int(implementation_metrics.get("tool_errors", 0)) > 0:
            await send_event(
                {
                    "type": "status",
                    "agent": self.name,
                    "message": "Tool errors detected; performing one implementation re-plan.",
                }
            )
            replan_context = "\n\n".join(
                section
                for section in (
                    exploration_results,
                    implementation_results,
                    f"Missing evidence (if any): {', '.join(missing_evidence) if missing_evidence else '(none)'}",
                )
                if section
            )
            implementation_plan_text = await self._create_plan(
                user_message=user_message,
                memory_context=memory_context,
                evidence_context=replan_context,
                client=client,
                model=model,
                send_event=send_event,
                request_id=request_id,
                session_id=session_id,
                phase="implementation_replan",
                compact=True,
                triage=triage,
            )
            retry_results, retry_metrics = await self._execute_tools(
                user_message=user_message,
                plan_text=implementation_plan_text,
                memory_context=memory_context,
                client=client,
                session_id=session_id,
                request_id=request_id,
                send_event=send_event,
                model=model,
                allowed_tools=None,
                phase="implementation_replan",
            )
            implementation_results = "\n\n".join(
                section for section in (implementation_results, retry_results) if section
            )
            implementation_metrics = self._merge_tool_metrics(implementation_metrics, retry_metrics)

        combined_tool_results = "\n\n".join(
            section
            for section in (
                f"[phase:exploration]\n{exploration_results}" if exploration_results else "",
                f"[phase:implementation]\n{implementation_results}" if implementation_results else "",
            )
            if section
        )

        tool_metrics = {
            "exploration": exploration_metrics,
            "implementation": implementation_metrics,
        }

        await send_event(
            {
                "type": "agent_step",
                "agent": self.name,
                "step": "Reviewing results and building final response",
            }
        )

        final_text = await self._stream_final_response(
            user_message=user_message,
            plan_text=implementation_plan_text,
            tool_results=combined_tool_results,
            memory_context=memory_context,
            client=client,
            model=model,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            evidence_required=triage.needs_evidence_gate,
            create_intent=triage.create_intent,
        )

        await self._emit_lifecycle(
            send_event,
            stage="run_completed",
            request_id=request_id,
            session_id=session_id,
            details={
                "elapsed_ms": int((time.perf_counter() - run_started_at) * 1000),
                "tool_metrics": tool_metrics,
            },
        )
        return final_text

    async def _prepare_context(
        self,
        user_message: str,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
    ) -> str:
        """Check toolchain availability, update memory, and return the rendered memory context."""
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
        memory_context = self.memory.render_context(session_id)
        await self._emit_lifecycle(
            send_event,
            stage="memory_updated",
            request_id=request_id,
            session_id=session_id,
            details={"memory_chars": len(memory_context)},
        )
        return memory_context

    async def _stream_final_response(
        self,
        user_message: str,
        plan_text: str,
        tool_results: str,
        memory_context: str,
        client: LlmClient,
        model: str | None,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        evidence_required: bool,
        create_intent: bool,
    ) -> str:
        """Build the final prompt, stream tokens, persist the response, and return the full text."""
        if evidence_required and not self._has_verified_evidence(
            tool_results,
            allow_write_only=create_intent,
        ):
            blocked_message = (
                "INSUFFICIENT_EVIDENCE: No verified repository evidence was collected. "
                "I will not guess code or file contents. "
                "Please allow exploratory reads (list_dir/read_file) or provide exact file paths to continue."
            )
            await self._emit_lifecycle(
                send_event,
                stage="final_response_blocked_insufficient_evidence",
                request_id=request_id,
                session_id=session_id,
            )
            self.memory.add(session_id, "assistant", blocked_message)
            await send_event(
                {
                    "type": "final",
                    "agent": self.name,
                    "message": blocked_message,
                }
            )
            return blocked_message

        evidence_block = self._build_evidence_block(tool_results)
        final_prompt = (
            "User request:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}\n\n"
            "Tool outputs:\n"
            f"{tool_results or '(no tool outputs)'}\n\n"
            "Evidence summary:\n"
            f"{evidence_block}\n\n"
            "Relevant memory:\n"
            f"{memory_context}\n\n"
            "Return a concise implementation summary grounded only in tool outputs. "
            "Every concrete claim about files, code, commands, or outputs must be supported by the evidence summary. "
            "If evidence is insufficient, respond with 'INSUFFICIENT_EVIDENCE' and list exactly what to read/run next. "
            "Do not output full source files unless explicitly requested by the user. "
            "If files were written, list their paths and short next validation steps."
        )

        await self._emit_lifecycle(
            send_event,
            stage="streaming_started",
            request_id=request_id,
            session_id=session_id,
        )

        output_parts: list[str] = []
        async for token in client.stream_chat_completion(
            settings.agent_final_prompt,
            final_prompt,
            model=model,
        ):
            output_parts.append(token)
            await send_event({"type": "token", "agent": self.name, "token": token})

        final_text = "".join(output_parts).strip()
        await self._emit_lifecycle(
            send_event,
            stage="streaming_completed",
            request_id=request_id,
            session_id=session_id,
            details={"output_chars": len(final_text)},
        )
        self.memory.add(session_id, "assistant", final_text or "No output generated.")
        await send_event(
            {
                "type": "final",
                "agent": self.name,
                "message": final_text or "No output generated.",
            }
        )
        return final_text

    def _validate_guardrails(self, user_message: str, session_id: str, model: str | None) -> None:
        if not user_message.strip():
            logger.warning("guardrail violation: empty message", extra={"session_id": session_id})
            raise GuardrailViolation("Message must not be empty.")
        if len(user_message) > settings.max_user_message_length:
            logger.warning("guardrail violation: message too long", extra={"session_id": session_id})
            raise GuardrailViolation(
                f"Message exceeds max length ({settings.max_user_message_length})."
            )
        if len(session_id) > 120:
            logger.warning("guardrail violation: session_id too long")
            raise GuardrailViolation("session_id too long.")
        if not _SESSION_ID_RE.fullmatch(session_id):
            logger.warning("guardrail violation: session_id invalid chars", extra={"session_id": session_id})
            raise GuardrailViolation("session_id contains unsupported characters.")
        if model and len(model) > 120:
            logger.warning("guardrail violation: model name too long", extra={"model": model})
            raise GuardrailViolation("model name too long.")
        if model and _ALLOWED_MODELS and model not in _ALLOWED_MODELS:
            logger.warning("guardrail violation: model not allowed", extra={"model": model})
            raise GuardrailViolation(f"Model '{model}' is not in the allowed list.")

    async def _create_plan(
        self,
        user_message: str,
        memory_context: str,
        evidence_context: str,
        client: LlmClient,
        model: str | None,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
        phase: str,
        compact: bool,
        triage: TaskTriage,
    ) -> str:
        await self._emit_lifecycle(
            send_event,
            stage=f"planning_{phase}_started",
            request_id=request_id,
            session_id=session_id,
        )
        if phase == "exploration":
            exploration_targets = self._build_exploration_targets(user_message=user_message, triage=triage)
            planner_prompt = (
                "Create Plan V1 (Exploration) with 3-6 bullets for a coding agent task.\n"
                "Goal: gather evidence before implementation.\n"
                "Use only exploration actions like list_dir/read_file in this phase.\n"
                "No code guessing.\n\n"
                "Triage:\n"
                f"- reason: {triage.reason}\n"
                f"- required_evidence_types: {', '.join(triage.required_evidence_types) or '(none)'}\n"
                f"- confidence: {triage.confidence:.2f}\n\n"
                "Exploration targets:\n"
                f"{exploration_targets}\n\n"
                "Conversation memory:\n"
                f"{memory_context}\n\n"
                "Current task:\n"
                f"{user_message}"
            )
        else:
            bullets_range = "2-4" if compact else "3-6"
            planner_prompt = (
                f"Create Plan V2 (Implementation) with {bullets_range} bullets for a coding agent task.\n"
                "Use exploration evidence when deciding edits/commands.\n"
                "Avoid assumptions not backed by evidence.\n\n"
                "Required evidence types (must be satisfied when relevant):\n"
                f"{', '.join(triage.required_evidence_types) or '(none)'}\n\n"
                "Exploration evidence:\n"
                f"{evidence_context or '(none)'}\n\n"
                "Conversation memory:\n"
                f"{memory_context}\n\n"
                "Current task:\n"
                f"{user_message}"
            )
        plan = await client.complete_chat(
            settings.agent_plan_prompt,
            planner_prompt,
            model=model,
        )
        await self._emit_lifecycle(
            send_event,
            stage=f"planning_{phase}_completed",
            request_id=request_id,
            session_id=session_id,
            details={"plan_chars": len(plan), "phase": phase},
        )
        return plan

    async def _execute_tools(
        self,
        user_message: str,
        plan_text: str,
        memory_context: str,
        client: LlmClient,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str] | frozenset[str] | None,
        phase: str,
    ) -> tuple[str, dict]:
        metrics: dict[str, int | str | bool] = {
            "parse_failed": False,
            "repaired": False,
            "requested_actions": 0,
            "accepted_actions": 0,
            "rejected_actions": 0,
            "tool_errors": 0,
            "execution_mode": "parallel",
            "phase": phase,
        }

        await self._emit_lifecycle(
            send_event,
            stage=f"tool_selection_{phase}_started",
            request_id=request_id,
            session_id=session_id,
        )
        allowed_tool_list = sorted(allowed_tools) if allowed_tools is not None else sorted(ALLOWED_TOOLS)
        tool_selector_prompt = (
            "Choose up to 3 tool calls to support this coding task.\n"
            "Return strict JSON only in this schema:\n"
            "{\"mode\":\"parallel|sequential\",\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command\",\"args\":{}}]}\n"
            "The 'mode' field is optional and defaults to 'parallel'.\n"
            "If no tool is needed return {\"actions\":[]}.\n"
            "For write_file include args path and content.\n"
            "For run_command include args command and optional cwd.\n\n"
            "Do not output markdown, explanations, [TOOL_CALL] wrappers, or any text outside the JSON object.\n"
            f"Allowed tool names for this phase are exactly: {', '.join(allowed_tool_list)}.\n\n"
            "Memory:\n"
            f"{memory_context}\n\n"
            "Phase:\n"
            f"{phase}\n\n"
            "Task:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}"
        )

        try:
            raw = await client.complete_chat(
                settings.agent_tool_selector_prompt,
                tool_selector_prompt,
                model=model,
            )
        except LlmClientError as exc:
            logger.warning(
                "tool selection llm failed; continuing without tools",
                extra={"request_id": request_id, "session_id": session_id, "error": str(exc)},
            )
            await send_event(
                {
                    "type": "status",
                    "agent": self.name,
                    "message": "Tool selection timed out; continuing without tool calls.",
                }
            )
            await self._emit_lifecycle(
                send_event,
                stage=f"tool_selection_{phase}_failed",
                request_id=request_id,
                session_id=session_id,
                details={"error": str(exc)},
            )
            return "", metrics
        selection = self._extract_actions(raw)
        actions, mode, parse_error = selection.actions, selection.mode, selection.parse_error
        metrics["requested_actions"] = len(actions)
        metrics["execution_mode"] = mode
        repaired = False

        if parse_error:
            metrics["parse_failed"] = True
            await self._emit_lifecycle(
                send_event,
                stage=f"tool_selection_{phase}_repair_started",
                request_id=request_id,
                session_id=session_id,
                details={"error": parse_error},
            )
            try:
                repaired_raw = await self._repair_tool_selection_json(raw=raw, client=client, model=model)
            except LlmClientError as exc:
                logger.warning(
                    "tool selection repair llm failed; continuing without tools",
                    extra={"request_id": request_id, "session_id": session_id, "error": str(exc)},
                )
                await send_event(
                    {
                        "type": "status",
                        "agent": self.name,
                        "message": "Tool-selection repair timed out; continuing without tool calls.",
                    }
                )
                await self._emit_lifecycle(
                    send_event,
                    stage=f"tool_selection_{phase}_repair_failed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"error": str(exc)},
                )
                return "", metrics
            repaired_selection = self._extract_actions(repaired_raw)
            repaired_actions, repaired_mode, repaired_error = (
                repaired_selection.actions,
                repaired_selection.mode,
                repaired_selection.parse_error,
            )
            if repaired_error is None:
                actions = repaired_actions
                mode = repaired_mode
                parse_error = None
                repaired = True
                metrics["repaired"] = True
                metrics["requested_actions"] = len(actions)
                metrics["execution_mode"] = mode
                await self._emit_lifecycle(
                    send_event,
                    stage=f"tool_selection_{phase}_repair_completed",
                    request_id=request_id,
                    session_id=session_id,
                )
            else:
                parse_error = f"{parse_error} | repair_failed: {repaired_error}"
                await self._emit_lifecycle(
                    send_event,
                    stage=f"tool_selection_{phase}_repair_failed",
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
                stage=f"tool_selection_{phase}_parse_failed",
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

        actions, rejected_count, rejection_reasons = self._validate_actions(actions, allowed_tools=allowed_tools)
        metrics["accepted_actions"] = len(actions)
        metrics["rejected_actions"] = rejected_count
        if rejected_count > 0:
            await self._emit_lifecycle(
                send_event,
                stage=f"tool_selection_{phase}_actions_rejected",
                request_id=request_id,
                session_id=session_id,
                details={
                    "rejected": rejected_count,
                    "reasons": rejection_reasons[:ACTION_REJECTION_PREVIEW_MAX],
                },
            )
        await self._emit_lifecycle(
            send_event,
            stage=f"tool_selection_{phase}_completed",
            request_id=request_id,
            session_id=session_id,
            details={
                "actions": len(actions),
                "mode": mode,
                "phase": phase,
                "metrics": metrics,
            },
        )
        if not actions:
            return "", metrics

        selected_actions = actions[:MAX_TOOL_CALLS]
        if mode == "sequential":
            results: list[str] = []
            for idx, action in enumerate(selected_actions, start=1):
                single_result, has_error = await self._run_single_action(
                    idx=idx,
                    action=action,
                    session_id=session_id,
                    request_id=request_id,
                    send_event=send_event,
                )
                if has_error:
                    metrics["tool_errors"] = int(metrics["tool_errors"]) + 1
                results.append(single_result)
        else:
            tasks = [
                self._run_single_action(
                    idx=idx,
                    action=action,
                    session_id=session_id,
                    request_id=request_id,
                    send_event=send_event,
                )
                for idx, action in enumerate(selected_actions, start=1)
            ]
            execution_results = await asyncio.gather(*tasks)
            results = []
            for single_result, has_error in execution_results:
                if has_error:
                    metrics["tool_errors"] = int(metrics["tool_errors"]) + 1
                results.append(single_result)
        return "\n\n".join(r for r in results if r), metrics

    async def _run_single_action(
        self,
        idx: int,
        action: dict,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
    ) -> tuple[str, bool]:
        tool = str(action.get("tool", "")).strip()
        args = action.get("args", {})
        if not isinstance(args, dict):
            args = {}

        evaluated_args, eval_error = self._evaluate_action(tool, args)
        if eval_error:
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
            return f"[{tool}] REJECTED: {eval_error}", True

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

        try:
            result = await self._run_tool_with_policy(tool=tool, args=evaluated_args, policy=policy)
            clipped = result[:TOOL_RESULT_CLIP_CHARS]
            self.memory.add(session_id, f"tool:{tool}", clipped)
            logger.debug("tool completed", extra={"tool": tool, "result_chars": len(clipped)})
            await self._emit_lifecycle(
                send_event,
                stage="tool_completed",
                request_id=request_id,
                session_id=session_id,
                details={"tool": tool, "index": idx, "result_chars": len(clipped)},
            )
            return f"[{tool}]\n{clipped}", False
        except ToolExecutionError as exc:
            logger.warning("tool failed", extra={"tool": tool, "error": str(exc)})
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
            return f"[{tool}] ERROR: {exc}", True

    def _extract_actions(self, raw: str) -> ToolSelectionResult:
        text = raw.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ToolSelectionResult(actions=[], mode="parallel", parse_error="LLM JSON could not be decoded.")
        if not isinstance(parsed, dict):
            return ToolSelectionResult(actions=[], mode="parallel", parse_error="LLM JSON root is not an object.")
        unsupported_fields = set(parsed.keys()) - {"actions", "mode"}
        if unsupported_fields:
            return ToolSelectionResult(actions=[], mode="parallel", parse_error="LLM JSON root contains unsupported fields.")

        mode = parsed.get("mode", "parallel")
        if not isinstance(mode, str) or mode not in _TOOL_EXECUTION_MODES:
            return ToolSelectionResult(actions=[], mode="parallel", parse_error="LLM JSON field 'mode' must be 'parallel' or 'sequential'.")

        actions = parsed.get("actions", [])
        if not isinstance(actions, list):
            return ToolSelectionResult(actions=[], mode=mode, parse_error="LLM JSON field 'actions' is not a list.")

        validated_actions: list[dict] = []
        for action in actions:
            if not isinstance(action, dict):
                return ToolSelectionResult(actions=[], mode=mode, parse_error="Each action must be an object.")
            if set(action.keys()) - {"tool", "args"}:
                return ToolSelectionResult(actions=[], mode=mode, parse_error="Each action supports only 'tool' and 'args'.")
            if not isinstance(action.get("tool"), str):
                return ToolSelectionResult(actions=[], mode=mode, parse_error="Each action requires string field 'tool'.")
            if "args" in action and not isinstance(action.get("args"), dict):
                return ToolSelectionResult(actions=[], mode=mode, parse_error="Each action field 'args' must be an object when provided.")
            validated_actions.append({"tool": action["tool"], "args": action.get("args", {})})
        return ToolSelectionResult(actions=validated_actions, mode=mode, parse_error=None)

    async def _repair_tool_selection_json(self, raw: str, client: LlmClient, model: str | None) -> str:
        raw_block = self._extract_json_candidate(raw)
        repair_prompt = (
            "Convert the following tool-selection output into strict JSON only.\n"
            "Output schema:\n"
            "{\"mode\":\"parallel|sequential\",\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command\",\"args\":{}}]}\n"
            "Rules:\n"
            "- Output only one JSON object.\n"
            "- No markdown and no explanations.\n"
            "- Keep mode when available, otherwise omit it.\n"
            "- Map legacy tool names to allowed names if obvious (e.g. CreateFile -> write_file).\n"
            "- If uncertain, return {\"actions\":[]}.\n\n"
            "Broken output block (do not add reasoning):\n"
            f"{raw_block}"
        )
        return await client.complete_chat(
            settings.agent_tool_repair_prompt,
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
            return text[:JSON_CANDIDATE_MAX_CHARS]
        return text[start : end + 1][:JSON_CANDIDATE_MAX_CHARS]

    def _validate_actions(
        self,
        actions: list[dict],
        allowed_tools: set[str] | frozenset[str] | None = None,
    ) -> tuple[list[dict], int, list[str]]:
        valid_actions: list[dict] = []
        rejected = 0
        reasons: list[str] = []
        effective_allowed_tools = allowed_tools if allowed_tools is not None else ALLOWED_TOOLS

        for idx, action in enumerate(actions, start=1):
            validated, reason = self._validate_single_action(action, allowed_tools=effective_allowed_tools)
            if reason is not None:
                rejected += 1
                reasons.append(f"action_{idx}: {reason}")
                continue
            valid_actions.append(validated)

        return valid_actions, rejected, reasons

    def _validate_single_action(
        self,
        action: dict,
        allowed_tools: set[str] | frozenset[str],
    ) -> tuple[dict, str | None]:
        if not isinstance(action, dict):
            return {}, "action is not an object"
        tool = action.get("tool")
        args = action.get("args", {})
        if not isinstance(tool, str):
            return {}, "field 'tool' is missing or not a string"
        normalized_tool = self._normalize_tool_name(tool)
        if normalized_tool not in ALLOWED_TOOLS:
            return {}, f"tool '{normalized_tool}' is not allowed"
        if normalized_tool not in allowed_tools:
            return {}, f"tool '{normalized_tool}' is not allowed in this phase"
        if not isinstance(args, dict):
            return {}, "field 'args' is not an object"
        return {"tool": normalized_tool, "args": args}, None

    def _triage_task(self, user_message: str) -> TaskTriage:
        text = user_message.lower()
        evidence_markers = ("file", "code", "repo", "test", "bug", "fix", "implement", "refactor")
        dependency_markers = ("multiple", "across", "integration", "dependency", "related", "pipeline")
        concrete_change_markers = ("change", "replace", "rename", "update", "add", "remove", "set")
        create_markers = ("make", "build", "create", "generate")
        web_markers = ("html", "css", "javascript", "js", "index.html", "app")
        explicit_path_pattern = re.compile(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+")
        risky_markers = ("delete", "drop", "remove all", "format", "production", "deploy")
        mentions_code_or_repo = any(marker in text for marker in evidence_markers)
        create_intent = any(marker in text for marker in create_markers) and any(
            marker in text for marker in web_markers
        )
        has_explicit_path = bool(explicit_path_pattern.search(user_message))
        has_concrete_change = any(marker in text for marker in concrete_change_markers)
        has_dependencies = any(marker in text for marker in dependency_markers)

        required_evidence_types: list[str] = []
        if mentions_code_or_repo or create_intent:
            required_evidence_types.append("code_context")
        if "test" in text:
            required_evidence_types.append("test_context")
        if not has_explicit_path and (mentions_code_or_repo or create_intent):
            required_evidence_types.append("repo_map")
        if any(marker in text for marker in ("api", "endpoint", "route")):
            required_evidence_types.append("api_surface")

        needs_exploration = mentions_code_or_repo or create_intent
        reason = "Code/repo task requires evidence before implementation."
        confidence = 0.72

        if has_explicit_path and has_concrete_change and not has_dependencies:
            needs_exploration = False
            reason = "Exact file path and concrete change detected without dependency hints."
            confidence = 0.9
        elif not mentions_code_or_repo and not create_intent:
            needs_exploration = False
            reason = "No strong code/repo indicators in request."
            confidence = 0.88
            required_evidence_types = []
        elif create_intent:
            needs_exploration = True
            reason = "Greenfield create-intent detected; minimal exploration required."
            confidence = 0.86
        elif has_dependencies:
            needs_exploration = True
            reason = "Cross-file/dependency hints detected; exploration required."
            confidence = 0.82

        if confidence < 0.65 and (mentions_code_or_repo or create_intent):
            needs_exploration = True
            reason = "Low triage confidence for code task; exploration enforced."

        risk_level = "high" if any(marker in text for marker in risky_markers) else "normal"
        return TaskTriage(
            needs_exploration=needs_exploration,
            needs_evidence_gate=bool(required_evidence_types),
            create_intent=create_intent,
            reason=reason,
            required_evidence_types=tuple(dict.fromkeys(required_evidence_types)),
            confidence=confidence,
            risk_level=risk_level,
        )

    def _has_verified_evidence(self, tool_results: str, allow_write_only: bool = False) -> bool:
        if not tool_results.strip():
            return False
        if " ERROR:" in tool_results or " REJECTED:" in tool_results:
            return False
        if "[read_file]" in tool_results:
            return True
        if allow_write_only and "[write_file]" in tool_results:
            return True
        return False

    def _build_bootstrap_action(self, user_message: str) -> dict | None:
        text = user_message.lower()
        is_calculator = "calculator" in text and all(marker in text for marker in ("html", "css", "javascript"))
        if not is_calculator:
            return None
        content = """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Calculator</title>
    <style>
        :root { --bg:#111827; --panel:#1f2937; --btn:#374151; --txt:#f9fafb; --acc:#2563eb; }
        body { margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--txt); font-family:system-ui,sans-serif; }
        .calc { width:min(360px,92vw); background:var(--panel); padding:16px; border-radius:12px; }
        #display { width:100%; box-sizing:border-box; margin-bottom:12px; padding:12px; font-size:1.5rem; text-align:right; background:#0b1220; color:var(--txt); border:0; border-radius:8px; }
        .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
        button { padding:12px; font-size:1rem; border:0; border-radius:8px; background:var(--btn); color:var(--txt); cursor:pointer; }
        .op,.eq { background:var(--acc); }
        .wide { grid-column:span 2; }
    </style>
</head>
<body>
    <div class=\"calc\">
        <input id=\"display\" value=\"0\" readonly />
        <div class=\"grid\" id=\"keys\">
            <button data-act=\"ac\" class=\"wide\">AC</button><button data-act=\"del\">⌫</button><button data-op=\"/\" class=\"op\">÷</button>
            <button data-num=\"7\">7</button><button data-num=\"8\">8</button><button data-num=\"9\">9</button><button data-op=\"*\" class=\"op\">×</button>
            <button data-num=\"4\">4</button><button data-num=\"5\">5</button><button data-num=\"6\">6</button><button data-op=\"-\" class=\"op\">−</button>
            <button data-num=\"1\">1</button><button data-num=\"2\">2</button><button data-num=\"3\">3</button><button data-op=\"+\" class=\"op\">+</button>
            <button data-num=\"0\" class=\"wide\">0</button><button data-num=\".\">.</button><button data-act=\"eq\" class=\"eq\">=</button>
        </div>
    </div>
    <script>
        const d = document.getElementById('display');
        const prec = o => (o === '+' || o === '-') ? 1 : 2;
        const apply = (a,b,o) => o==='+'?a+b:o==='-'?a-b:o==='*'?a*b:(b===0?NaN:a/b);
        function evalExpr(expr){
            const t = expr.match(/\\d*\\.?\\d+|[+\\-*/]/g) || []; const out=[]; const ops=[];
            for(const x of t){
                if(!Number.isNaN(Number(x))) out.push(Number(x));
                else { while(ops.length && prec(ops.at(-1))>=prec(x)) out.push(ops.pop()); ops.push(x); }
            }
            while(ops.length) out.push(ops.pop());
            const st=[]; for(const x of out){ if(typeof x==='number') st.push(x); else { const b=st.pop(),a=st.pop(); st.push(apply(a,b,x)); }}
            const r = st.pop(); if(!Number.isFinite(r)) throw new Error('bad'); return Number(r.toFixed(10)).toString();
        }
        function add(v){ if(d.value==='Error' || d.value==='0') d.value=''; d.value += v; }
        function del(){ d.value = d.value.length>1 ? d.value.slice(0,-1) : '0'; }
        function ac(){ d.value='0'; }
        function eq(){ try{ d.value = evalExpr(d.value); } catch { d.value='Error'; } }
        document.getElementById('keys').addEventListener('click', e => {
            const b = e.target.closest('button'); if(!b) return;
            if(b.dataset.num) add(b.dataset.num); else if(b.dataset.op) add(b.dataset.op); else if(b.dataset.act==='del') del(); else if(b.dataset.act==='ac') ac(); else eq();
        });
        window.addEventListener('keydown', e => {
            if(/^[0-9]$/.test(e.key) || ['+','-','*','/','.'].includes(e.key)) add(e.key);
            else if(e.key==='Enter') eq(); else if(e.key==='Backspace') del(); else if(e.key==='Escape') ac();
        });
    </script>
</body>
</html>
"""
        return {
            "tool": "write_file",
            "args": {
                "path": "index.html",
                "content": content,
            },
        }

    def _has_successful_tool_result(self, tool_results: str, tool_name: str) -> bool:
        marker = f"[{tool_name}]"
        if marker not in tool_results:
            return False
        for block in tool_results.split("\n\n"):
            block = block.strip()
            if not block.startswith(marker):
                continue
            if " ERROR:" in block or " REJECTED:" in block:
                continue
            return True
        return False

    def _build_exploration_targets(self, user_message: str, triage: TaskTriage) -> str:
        explicit_paths = re.findall(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+", user_message)
        targets: list[str] = []
        if explicit_paths:
            targets.append(f"- Verify these paths first: {', '.join(explicit_paths[:4])}")
        if "repo_map" in triage.required_evidence_types:
            targets.append("- Build a quick repo map around likely source/test folders.")
        if "code_context" in triage.required_evidence_types:
            targets.append("- Read the most relevant implementation files before edits.")
        if "test_context" in triage.required_evidence_types:
            targets.append("- Read nearby tests to infer expected behavior.")
        if "api_surface" in triage.required_evidence_types:
            targets.append("- Read route/controller definitions to confirm API contracts.")
        if not targets:
            targets.append("- Minimal exploration only; gather just enough evidence for implementation.")
        return "\n".join(targets)

    def _build_focused_exploration_plan(
        self,
        user_message: str,
        triage: TaskTriage,
        missing_evidence: list[str],
    ) -> str:
        targets = self._build_exploration_targets(user_message=user_message, triage=triage)
        return (
            "Focused exploration follow-up plan.\n"
            f"Missing evidence types: {', '.join(missing_evidence)}\n"
            "Use only list_dir/read_file and prioritize files directly related to missing evidence.\n"
            f"Targets:\n{targets}"
        )

    def _assess_evidence_coverage(
        self,
        tool_results: str,
        required_evidence_types: tuple[str, ...],
    ) -> dict[str, object]:
        lower = tool_results.lower()
        has_list_dir = "[list_dir]" in lower and "[list_dir] error:" not in lower
        has_read_file = "[read_file]" in lower and "[read_file] error:" not in lower

        coverage_checks = {
            "repo_map": has_list_dir,
            "code_context": has_read_file,
            "test_context": has_read_file and ("test" in lower or "spec" in lower),
            "api_surface": has_read_file and ("api" in lower or "route" in lower or "endpoint" in lower),
        }

        missing = [kind for kind in required_evidence_types if not coverage_checks.get(kind, False)]
        matched = [kind for kind in required_evidence_types if kind not in missing]
        quality_score = 1.0 if not required_evidence_types else len(matched) / max(1, len(required_evidence_types))
        return {
            "required": list(required_evidence_types),
            "matched": matched,
            "missing": missing,
            "quality_score": round(quality_score, 3),
        }

    def _merge_tool_metrics(self, base: dict, extra: dict) -> dict:
        merged = dict(base)
        for key in ("requested_actions", "accepted_actions", "rejected_actions", "tool_errors"):
            merged[key] = int(merged.get(key, 0)) + int(extra.get(key, 0))
        merged["parse_failed"] = bool(merged.get("parse_failed") or extra.get("parse_failed"))
        merged["repaired"] = bool(merged.get("repaired") or extra.get("repaired"))
        merged["execution_mode"] = merged.get("execution_mode", "parallel")
        merged["phase"] = merged.get("phase", extra.get("phase", "unknown"))
        return merged

    def _build_evidence_block(self, tool_results: str) -> str:
        if not tool_results.strip():
            return "(none)"
        evidence_lines: list[str] = []
        for block in tool_results.split("\n\n"):
            block = block.strip()
            if not block or " ERROR:" in block or " REJECTED:" in block:
                continue
            if not block.startswith("["):
                continue
            header, _, body = block.partition("\n")
            preview = body.strip()[:240] if body else ""
            evidence_lines.append(f"- {header} => {preview}")
        return "\n".join(evidence_lines) if evidence_lines else "(none)"

    def _normalize_tool_name(self, tool_name: str) -> str:
        normalized = tool_name.strip()
        if not normalized:
            return normalized
        lowered = normalized.lower()
        if lowered in TOOL_NAME_ALIASES:
            return TOOL_NAME_ALIASES[lowered]
        return normalized

    def _evaluate_action(self, tool: str, args: dict) -> tuple[dict, str | None]:
        spec = self._TOOL_REGISTRY.get(tool)
        if spec is None:
            return {}, "tool is not in registry"

        normalized_args: dict[str, str] = {}
        allowed_keys = set(spec.required_args) | set(spec.optional_args)
        if set(args.keys()) - allowed_keys:
            return {}, "arguments contain unsupported fields"

        for required_name in spec.required_args:
            value = args.get(required_name)
            if not isinstance(value, str) or not value.strip():
                return {}, f"missing required argument '{required_name}'"
            normalized_args[required_name] = value

        for optional_name in spec.optional_args:
            value = args.get(optional_name)
            if value is None:
                continue
            if not isinstance(value, str):
                return {}, f"optional argument '{optional_name}' must be a string"
            normalized_args[optional_name] = value

        path_value = normalized_args.get("path")
        if path_value is not None and (len(path_value) > 400 or "\x00" in path_value):
            return {}, "path is not plausible"

        if tool == "run_command":
            command = normalized_args.get("command", "")
            if self._violates_command_policy(command):
                return {}, "command blocked by policy"

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
        spec = self._TOOL_REGISTRY[tool]
        retry_class = "none"
        if tool == "run_command":
            retry_class = "transient"
        return ToolExecutionPolicy(
            retry_class=retry_class,
            timeout_seconds=spec.timeout_seconds,
            max_retries=spec.max_retries,
        )

    async def _run_tool_with_policy(self, tool: str, args: dict, policy: ToolExecutionPolicy) -> str:
        max_attempts = policy.max_retries + 1
        last_error: Exception | None = None
        loop = asyncio.get_running_loop()

        for attempt in range(1, max_attempts + 1):
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(self._executor, self._invoke_tool, tool, args),
                    timeout=policy.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning("tool timeout (attempt %d/%d)", attempt, max_attempts, extra={"tool": tool})
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
        raise ToolExecutionError(f"Tool execution failed ({tool})") from last_error

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
            {
                "type": "lifecycle",
                "agent": self.name,
                "stage": stage,
                "request_id": request_id,
                "session_id": session_id,
                "ts": datetime.now(timezone.utc).isoformat(),
                "details": details or {},
            }
        )
