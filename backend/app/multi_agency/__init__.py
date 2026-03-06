"""Multi-Agency subsystem: Real multi-agent coordination, not parametrised single-agent."""

from app.multi_agency.agent_identity import AgentCapabilityProfile, AgentIdentityCard
from app.multi_agency.agent_message_bus import AgentMessage, AgentMessageBus
from app.multi_agency.blackboard import Blackboard, BlackboardEntry
from app.multi_agency.confidence_router import ConfidenceRouteDecision, ConfidenceRouter
from app.multi_agency.consensus import ConsensusEngine, ConsensusResult, VotingStrategy
from app.multi_agency.parallel_executor import FanOutResult, ParallelFanOutExecutor
from app.multi_agency.supervisor import SupervisorCoordinator, SupervisorDecision

__all__ = [
    "AgentCapabilityProfile",
    "AgentIdentityCard",
    "AgentMessage",
    "AgentMessageBus",
    "Blackboard",
    "BlackboardEntry",
    "ConfidenceRouteDecision",
    "ConfidenceRouter",
    "ConsensusEngine",
    "ConsensusResult",
    "FanOutResult",
    "ParallelFanOutExecutor",
    "SupervisorCoordinator",
    "SupervisorDecision",
    "VotingStrategy",
]
