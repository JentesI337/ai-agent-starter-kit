from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.tool_policy import ToolPolicyDict

QueueMode = Literal["wait", "follow_up", "steer"]
PromptMode = Literal["full", "minimal", "subagent"]
ReasoningLevel = Literal["low", "medium", "high", "ultrathink", "adaptive"]
ReasoningVisibility = Literal["off", "summary", "stream"]


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
    queue_mode: QueueMode = "wait"
    prompt_mode: PromptMode = "full"
    reasoning_level: ReasoningLevel = "medium"
    reasoning_visibility: ReasoningVisibility = "off"
    should_steer_interrupt: Callable[[], bool] | None = None
