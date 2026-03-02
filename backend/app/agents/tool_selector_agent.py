from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.schemas import ToolSelectorInput, ToolSelectorOutput
from app.tool_catalog import TOOL_NAME_SET
from app.tool_policy import ToolPolicyDict

ExecuteToolsFn = Callable[[str, str, str, str, str, SendEvent, str | None, set[str]], Awaitable[str]]
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

    def __init__(self, execute_tools_fn: ExecuteToolsFn):
        self._execute_tools_fn = execute_tools_fn

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
    ) -> ToolSelectorOutput:
        results = await self._execute_tools_fn(
            payload.user_message,
            payload.plan_text,
            payload.reduced_context,
            session_id,
            request_id,
            send_event,
            model,
            allowed_tools,
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
    ) -> str:
        payload = ToolSelectorInput.model_validate_json(user_message)
        result = await self.execute(
            payload,
            session_id=session_id,
            request_id=request_id,
            send_event=send_event,
            model=model,
            allowed_tools=set(DEFAULT_ALLOWED_TOOLS),
        )
        return json.dumps(result.model_dump(), ensure_ascii=False)
