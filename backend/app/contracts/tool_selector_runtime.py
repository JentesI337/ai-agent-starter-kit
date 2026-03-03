from __future__ import annotations

from typing import Protocol

from app.contracts.agent_contract import SendEvent
from app.contracts.schemas import ToolSelectorInput


class ToolSelectorRuntime(Protocol):
    async def run_tools(
        self,
        *,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event: SendEvent,
        model: str | None,
        allowed_tools: set[str],
    ) -> str: ...
