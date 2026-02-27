from pydantic import BaseModel


class WsInboundMessage(BaseModel):
    type: str
    content: str = ""
    agent_id: str | None = None
    model: str | None = None
    session_id: str | None = None
    runtime_target: str | None = None
    api_key: str | None = None


class AgentDescriptor(BaseModel):
    id: str
    name: str
    role: str
    status: str
