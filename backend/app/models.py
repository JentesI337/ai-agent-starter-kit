import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter
from app.tool_policy import ToolPolicyPayload


class WsInboundEnvelope(BaseModel):
    type: str
    content: str = ""
    agent_id: str | None = None
    mode: str | None = None
    preset: str | None = None
    model: str | None = None
    session_id: str | None = None
    runtime_target: str | None = None
    queue_mode: str | None = None
    prompt_mode: str | None = None
    tool_policy: ToolPolicyPayload | None = None


class WsUserMessage(WsInboundEnvelope):
    type: Literal["user_message"]


class WsSubrunSpawnMessage(WsInboundEnvelope):
    type: Literal["subrun_spawn"]


class WsRuntimeSwitchRequestMessage(WsInboundEnvelope):
    type: Literal["runtime_switch_request"]


class WsClarificationResponseMessage(WsInboundEnvelope):
    type: Literal["clarification_response"]


class WsPolicyDecisionMessage(WsInboundEnvelope):
    type: Literal["policy_decision"]
    approval_id: str
    decision: Literal["allow_once", "allow_session", "cancel"]


WsInboundMessage = Annotated[
    WsUserMessage
    | WsSubrunSpawnMessage
    | WsRuntimeSwitchRequestMessage
    | WsClarificationResponseMessage
    | WsPolicyDecisionMessage,
    Field(discriminator="type"),
]

SUPPORTED_WS_INBOUND_TYPES = frozenset(
    {
        "user_message",
        "subrun_spawn",
        "runtime_switch_request",
        "clarification_response",
        "policy_decision",
    }
)

_WS_INBOUND_MESSAGE_ADAPTER = TypeAdapter(WsInboundMessage)


def parse_ws_inbound_message(raw: str) -> WsInboundMessage:
    return _WS_INBOUND_MESSAGE_ADAPTER.validate_json(raw)


def peek_ws_inbound_type(raw: str) -> str | None:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return None
    msg_type = payload.get("type")
    return msg_type if isinstance(msg_type, str) else None


class AgentDescriptor(BaseModel):
    id: str
    name: str
    role: str
    status: str
