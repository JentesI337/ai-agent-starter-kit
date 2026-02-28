from __future__ import annotations

import json
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
                result = self._run_tool(tool, args)
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
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return [], "LLM did not return valid JSON object."
            try:
                parsed = json.loads(text[start : end + 1])
            except Exception:
                return [], "LLM JSON could not be decoded."
        if not isinstance(parsed, dict):
            return [], "LLM JSON root is not an object."
        actions = parsed.get("actions", [])
        if not isinstance(actions, list):
            return [], "LLM JSON field 'actions' is not a list."
        return actions, None

    def _validate_actions(self, actions: list[dict]) -> tuple[list[dict], int]:
        valid_actions: list[dict] = []
        rejected = 0

        for action in actions:
            if not isinstance(action, dict):
                rejected += 1
                continue
            tool = action.get("tool")
            args = action.get("args", {})
            if not isinstance(tool, str) or tool.strip() not in ALLOWED_TOOLS:
                rejected += 1
                continue
            if not isinstance(args, dict):
                rejected += 1
                continue
            valid_actions.append({"tool": tool.strip(), "args": args})

        return valid_actions, rejected

    def _run_tool(self, tool: str, args: dict) -> str:
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
