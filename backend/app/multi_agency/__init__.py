"""Multi-Agency subsystem: Real multi-agent coordination, not parametrised single-agent.

Domain boundary rules
─────────────────────
Allowed imports:
  • stdlib / third-party packages
  • app.multi_agency.*          (intra-package)
  • app.agent.*                 (canonical agent domain)
  • app.contracts.*             (shared value objects / DTOs)

Disallowed imports (deprecated compat shims):
  • app.agents.*                → use app.agent.*
  • app.services.*              → use app.agent.services.*
  • app.orchestrator.*          → use app.orchestration.*
  • app.model_routing.*         → use app.agent.model_routing.*
"""

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
