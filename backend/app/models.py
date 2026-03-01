from pydantic import BaseModel


class ToolPolicyPayload(BaseModel):
    allow: list[str] | None = None
    deny: list[str] | None = None


class WsInboundMessage(BaseModel):
    type: str
    content: str = ""
    agent_id: str | None = None
    model: str | None = None
    session_id: str | None = None
    runtime_target: str | None = None
    tool_policy: ToolPolicyPayload | None = None


class AgentDescriptor(BaseModel):
    id: str
    name: str
    role: str
    status: str
