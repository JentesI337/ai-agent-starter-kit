from __future__ import annotations

import json

from app.agents.tool_selector_legacy import ExecuteToolsFn, LegacyRunnerBinding
from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import ToolSelectorInput, ToolSelectorOutput
from app.contracts.tool_selector_runtime import ToolSelectorRuntime
from app.tool_catalog import TOOL_NAME_SET
from app.tool_policy import ToolPolicyDict

DEFAULT_ALLOWED_TOOLS = set(TOOL_NAME_SET)


class ToolSelectorAgent(AgentContract):
    role = "tool-selector-agent"
    input_schema = ToolSelectorInput
    output_schema = ToolSelectorOutput
    constraints = AgentConstraints(
        max_context=4096,
        temperature=0.1,
        reasoning_depth=1,
        reflection_passes=0,
        combine_steps=False,
    )

    def __init__(
        self,
        execute_tools_fn: ExecuteToolsFn | None = None,
        runtime: ToolSelectorRuntime | None = None,
    ):
        self._legacy_runner_binding: LegacyRunnerBinding | None = None
        self._runtime = runtime
        if execute_tools_fn is not None:
            self.set_execute_tools_fn(execute_tools_fn)

    def set_runtime(self, runtime: ToolSelectorRuntime | None) -> None:
        self._runtime = runtime

    def set_legacy_execute_tools_fn(self, execute_tools_fn: ExecuteToolsFn) -> None:
        self._legacy_runner_binding = LegacyRunnerBinding(execute_tools_fn)

    def set_execute_tools_fn(self, execute_tools_fn: ExecuteToolsFn) -> None:
        self.set_legacy_execute_tools_fn(execute_tools_fn)

    def _resolve_configured_runner(self) -> ExecuteToolsFn | None:
        if self._legacy_runner_binding is None:
            return None
        resolved = self._legacy_runner_binding.resolve()
        if resolved is None:
            self._legacy_runner_binding = None
            return None
        return resolved

    async def _execute_with_inline_runner(
        self,
        *,
        execute_tools_fn: ExecuteToolsFn,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
    ) -> str:
        return await execute_tools_fn(
            payload.user_message,
            payload.plan_text,
            payload.reduced_context,
            session_id,
            request_id,
            send_event,
            model,
            allowed_tools,
        )

    async def _execute_with_runtime(
        self,
        *,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
    ) -> str:
        if self._runtime is None:
            raise RuntimeError("tool selector runtime is not configured")
        return await self._runtime.run_tools(
            payload=payload,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=allowed_tools,
        )

    async def _execute_with_legacy_runner(
        self,
        *,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
    ) -> str:
        runner = self._resolve_configured_runner()
        if runner is None:
            raise RuntimeError("ToolSelectorAgent.execute requires runtime or execute_tools_fn")
        return await runner(
            payload.user_message,
            payload.plan_text,
            payload.reduced_context,
            session_id,
            request_id,
            send_event,
            model,
            allowed_tools,
        )

    @staticmethod
    def _normalize_tool_name(value: str) -> str:
        return value.strip().lower().replace("-", "_")

    def _resolve_effective_allowed_tools(self, tool_policy: ToolPolicyDict | None) -> set[str]:
        allowed = set(DEFAULT_ALLOWED_TOOLS)
        if not tool_policy:
            return allowed

        allow_values = tool_policy.get("allow")
        if isinstance(allow_values, list):
            normalized_allow = {
                self._normalize_tool_name(item)
                for item in allow_values
                if isinstance(item, str) and item.strip()
            }
            known_allow = {item for item in normalized_allow if item in DEFAULT_ALLOWED_TOOLS}
            if known_allow:
                allowed &= known_allow

        deny_values = tool_policy.get("deny")
        if isinstance(deny_values, list):
            normalized_deny = {
                self._normalize_tool_name(item)
                for item in deny_values
                if isinstance(item, str) and item.strip()
            }
            allowed -= {item for item in normalized_deny if item in DEFAULT_ALLOWED_TOOLS}

        return allowed

    @property
    def name(self) -> str:
        return "tool-selector-agent"

    def configure_runtime(self, base_url: str, model: str) -> None:
        return

    async def execute(
        self,
        payload: ToolSelectorInput,
        *,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
        execute_tools_fn: ExecuteToolsFn | None = None,
    ) -> ToolSelectorOutput:
        if execute_tools_fn is not None:
            results = await self._execute_with_inline_runner(
                execute_tools_fn=execute_tools_fn,
                payload=payload,
                session_id=session_id,
                request_id=request_id,
                send_event=send_event,
                model=model,
                allowed_tools=allowed_tools,
            )
        elif self._runtime is not None:
            results = await self._execute_with_runtime(
                payload=payload,
                session_id=session_id,
                request_id=request_id,
                send_event=send_event,
                model=model,
                allowed_tools=allowed_tools,
            )
        else:
            results = await self._execute_with_legacy_runner(
                payload=payload,
                session_id=session_id,
                request_id=request_id,
                send_event=send_event,
                model=model,
                allowed_tools=allowed_tools,
            )
        return ToolSelectorOutput(tool_results=results)

    async def run(
        self,
        user_message: str,
        send_event: SendEvent,
        session_id: str,
        request_id: str,
        model: str | None = None,
        tool_policy: ToolPolicyDict | None = None,
        execute_tools_fn: ExecuteToolsFn | None = None,
    ) -> str:
        payload = ToolSelectorInput.model_validate_json(user_message)
        effective_allowed_tools = self._resolve_effective_allowed_tools(tool_policy)
        result = await self.execute(
            payload,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=effective_allowed_tools,
            execute_tools_fn=execute_tools_fn,
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)
