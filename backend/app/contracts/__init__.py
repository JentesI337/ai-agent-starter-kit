from app.contracts.agent_contract import AgentConstraints, AgentContract, SendEvent
from app.contracts.hook_contract import HookExecutionContract, resolve_hook_execution_contract
from app.contracts.request_context import RequestContext
from app.contracts.schemas import (
    AgentInput,
    CoderAgentInput,
    CoderAgentOutput,
    HeadAgentInput,
    HeadAgentOutput,
    HeadCoderInput,
    HeadCoderOutput,
)
from app.contracts.tool_protocol import ToolProvider

# NOTE: OrchestratorApi deliberately NOT imported here to avoid circular import
# (orchestrator_api → orchestration.pipeline_runner → contracts.agent_contract → contracts/__init__)
# Import directly: from app.contracts.orchestrator_api import OrchestratorApi

__all__ = [
    "AgentConstraints",
    "AgentContract",
    "AgentInput",
    "CoderAgentInput",
    "CoderAgentOutput",
    "HeadAgentInput",
    "HeadAgentOutput",
    "HeadCoderInput",
    "HeadCoderOutput",
    "HookExecutionContract",
    "OrchestratorApi",
    "RequestContext",
    "SendEvent",
    "ToolProvider",
    "resolve_hook_execution_contract",
]


def __getattr__(name: str):
    if name == "OrchestratorApi":
        from app.contracts.orchestrator_api import OrchestratorApi
        return OrchestratorApi
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
