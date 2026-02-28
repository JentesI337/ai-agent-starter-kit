from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Callable, Awaitable

from app.config import settings
from app.errors import GuardrailViolation, ToolExecutionError
from app.llm_client import LlmClient
from app.memory import MemoryStore
from app.tools import AgentTooling

SendEvent = Callable[[dict], Awaitable[None]]
ALLOWED_TOOLS = {"list_dir", "read_file", "write_file", "run_command"}
TOOL_NAME_ALIASES = {
    "createfile": "write_file",
    "writefile": "write_file",
    "readfile": "read_file",
    "listdir": "list_dir",
    "runcommand": "run_command",
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


class HeadCodingAgent:
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
        self.tool_registry = self._build_tool_registry()

    def configure_runtime(self, base_url: str, model: str) -> None:
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
        await self._emit_lifecycle(
            send_event,
            stage="run_started",
            request_id=request_id,
            session_id=session_id,
            details={"model": model or self.client.model},
        )

        self._validate_guardrails(user_message=user_message, session_id=session_id, model=model)
        await self._emit_lifecycle(
            send_event,
            stage="guardrails_passed",
            request_id=request_id,
            session_id=session_id,
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
        memory_context = self.memory.render_context(session_id)
        await self._emit_lifecycle(
            send_event,
            stage="memory_updated",
            request_id=request_id,
            session_id=session_id,
            details={"memory_chars": len(memory_context)},
        )

        await send_event(
            {
                "type": "status",
                "agent": self.name,
                "message": "Analyzing your request and planning execution.",
            }
        )

        plan_text = await self._create_plan(
            user_message=user_message,
            memory_context=memory_context,
            model=model,
            send_event=send_event,
            request_id=request_id,
            session_id=session_id,
        )
        self.memory.add(session_id, "plan", plan_text)
        await send_event(
            {
                "type": "agent_step",
                "agent": self.name,
                "step": f"Plan ready: {plan_text[:220]}",
            }
        )

        tool_results = await self._execute_tools(
            user_message=user_message,
            plan_text=plan_text,
            memory_context=memory_context,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
        )

        await send_event(
            {
                "type": "agent_step",
                "agent": self.name,
                "step": "Reviewing results and building final response",
            }
        )

        final_prompt = (
            "User request:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}\n\n"
            "Tool outputs:\n"
            f"{tool_results or '(no tool outputs)'}\n\n"
            "Relevant memory:\n"
            f"{memory_context}\n\n"
            "Generate a concise final answer with concrete next implementation steps."
        )

        await self._emit_lifecycle(
            send_event,
            stage="streaming_started",
            request_id=request_id,
            session_id=session_id,
        )

        output_parts: list[str] = []
        async for token in self.client.stream_chat_completion(
            settings.agent_system_prompt,
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
        await self._emit_lifecycle(
            send_event,
            stage="run_completed",
            request_id=request_id,
            session_id=session_id,
        )
        return final_text

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

    async def _create_plan(
        self,
        user_message: str,
        memory_context: str,
        model: str | None,
        send_event: SendEvent,
        request_id: str,
        session_id: str,
    ) -> str:
        await self._emit_lifecycle(
            send_event,
            stage="planning_started",
            request_id=request_id,
            session_id=session_id,
        )
        planner_prompt = (
            "Create a short implementation plan (3-6 bullets) for a coding agent task.\n"
            "Focus on actionable steps only.\n\n"
            "Conversation memory:\n"
            f"{memory_context}\n\n"
            "Current task:\n"
            f"{user_message}"
        )
        plan = await self.client.complete_chat(
            settings.agent_system_prompt,
            planner_prompt,
            model=model,
        )
        await self._emit_lifecycle(
            send_event,
            stage="planning_completed",
            request_id=request_id,
            session_id=session_id,
            details={"plan_chars": len(plan)},
        )
        return plan

    async def _execute_tools(
        self,
        user_message: str,
        plan_text: str,
        memory_context: str,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
    ) -> str:
        await self._emit_lifecycle(
            send_event,
            stage="tool_selection_started",
            request_id=request_id,
            session_id=session_id,
        )
        tool_selector_prompt = (
            "Choose up to 3 tool calls to support this coding task.\n"
            "Return strict JSON only in this schema:\n"
            "{\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command\",\"args\":{}}]}\n"
            "If no tool is needed return {\"actions\":[]}.\n"
            "For write_file include args path and content.\n"
            "For run_command include args command and optional cwd.\n\n"
            "Do not output markdown, explanations, [TOOL_CALL] wrappers, or any text outside the JSON object.\n"
            "Allowed tool names are exactly: list_dir, read_file, write_file, run_command.\n\n"
            "Memory:\n"
            f"{memory_context}\n\n"
            "Task:\n"
            f"{user_message}\n\n"
            "Plan:\n"
            f"{plan_text}"
        )

        raw = await self.client.complete_chat(
            settings.agent_system_prompt,
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

        actions, rejected_count = self._validate_actions(actions)
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
            return ""

        results: list[str] = []
        for idx, action in enumerate(actions[:3], start=1):
            tool = str(action.get("tool", "")).strip()
            args = action.get("args", {})
            if not isinstance(args, dict):
                args = {}

            evaluated_args, eval_error = self._evaluate_action(tool, args)
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
                clipped = result[:6000]
                self.memory.add(session_id, f"tool:{tool}", clipped)
                results.append(f"[{tool}]\n{clipped}")
                await self._emit_lifecycle(
                    send_event,
                    stage="tool_completed",
                    request_id=request_id,
                    session_id=session_id,
                    details={"tool": tool, "index": idx, "result_chars": len(clipped)},
                )
            except ToolExecutionError as exc:
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

        return "\n\n".join(results)

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
            "{\"actions\":[{\"tool\":\"list_dir|read_file|write_file|run_command\",\"args\":{}}]}\n"
            "Rules:\n"
            "- Output only one JSON object.\n"
            "- No markdown and no explanations.\n"
            "- Map legacy tool names to allowed names if obvious (e.g. CreateFile -> write_file).\n"
            "- If uncertain, return {\"actions\":[]}.\n\n"
            "Broken output block (do not add reasoning):\n"
            f"{raw_block}"
        )
        return await self.client.complete_chat(
            settings.agent_system_prompt,
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

    def _validate_actions(self, actions: list[dict]) -> tuple[list[dict], int]:
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
            if normalized_tool not in ALLOWED_TOOLS:
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
        }

    def _normalize_tool_name(self, tool_name: str) -> str:
        normalized = tool_name.strip()
        if not normalized:
            return normalized
        lowered = normalized.lower()
        if lowered in TOOL_NAME_ALIASES:
            return TOOL_NAME_ALIASES[lowered]
        return normalized

    def _evaluate_action(self, tool: str, args: dict) -> tuple[dict, str | None]:
        spec = self.tool_registry.get(tool)
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
        spec = self.tool_registry[tool]
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
