"""Multi-Agency subsystem: Real multi-agent coordination, not parametrised single-agent."""

from app.multi_agency.blackboard import Blackboard, BlackboardEntry
from app.multi_agency.agent_message_bus import AgentMessageBus, AgentMessage
from app.multi_agency.supervisor import SupervisorCoordinator, SupervisorDecision
from app.multi_agency.confidence_router import ConfidenceRouter, ConfidenceRouteDecision
from app.multi_agency.parallel_executor import ParallelFanOutExecutor, FanOutResult
from app.multi_agency.consensus import ConsensusEngine, ConsensusResult, VotingStrategy
from app.multi_agency.agent_identity import AgentIdentityCard, AgentCapabilityProfile

__all__ = [
    "Blackboard",
    "BlackboardEntry",
    "AgentMessageBus",
    "AgentMessage",
    "SupervisorCoordinator",
    "SupervisorDecision",
    "ConfidenceRouter",
    "ConfidenceRouteDecision",
    "ParallelFanOutExecutor",
    "FanOutResult",
    "ConsensusEngine",
    "ConsensusResult",
    "VotingStrategy",
    "AgentIdentityCard",
    "AgentCapabilityProfile",
]
