from __future__ import annotations

from pydantic import BaseModel, Field

from app.tools.policy import ToolPolicyDict


class AgentInput(BaseModel):
    user_message: str = Field(min_length=1)
    session_id: str = Field(min_length=1, max_length=120)
    request_id: str = Field(min_length=1)
    model: str | None = Field(default=None, max_length=120)
    tool_policy: ToolPolicyDict | None = None


HeadAgentInput = AgentInput


class HeadAgentOutput(BaseModel):
    final_text: str


CoderAgentInput = AgentInput


class CoderAgentOutput(BaseModel):
    final_text: str


HeadCoderInput = AgentInput
HeadCoderOutput = HeadAgentOutput
