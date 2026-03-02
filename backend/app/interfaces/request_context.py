from __future__ import annotations

from dataclasses import dataclass

from app.tool_policy import ToolPolicyDict


@dataclass(frozen=True)
class RequestContext:
    session_id: str
    request_id: str
    runtime: str
    model: str
    tool_policy: ToolPolicyDict | None = None
    also_allow: list[str] | None = None
    agent_id: str | None = None
    depth: int | None = None
    preset: str | None = None
    orchestrator_agent_ids: list[str] | None = None
