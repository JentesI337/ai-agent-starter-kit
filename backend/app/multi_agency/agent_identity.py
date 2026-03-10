"""Agent Identity: Real differentiation between agents.

This replaces the current "same code, different prompt" model with:
- Distinct capability profiles per agent
- Distinct tool sets per agent
- Distinct reasoning strategies per agent
- Distinct model preferences per agent
- Runtime-discoverable agent registry
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReasoningStrategy(StrEnum):
    """How an agent approaches problems — NOT just a prompt difference."""
    BREADTH_FIRST = "breadth_first"   # Explore many options, then narrow
    DEPTH_FIRST = "depth_first"       # Go deep on first solution
    ITERATIVE = "iterative"           # Refine through multiple passes
    ANALYTICAL = "analytical"         # Break down, analyze components
    CREATIVE = "creative"             # Generate novel approaches
    VERIFY_FIRST = "verify_first"     # Check assumptions before acting
    PLAN_EXECUTE = "plan_execute"     # Structured planning then execution


class AgentRole(StrEnum):
    """Semantic roles that agents can fill in a multi-agent system."""
    COORDINATOR = "coordinator"     # Distributes work, doesn't do it
    SPECIALIST = "specialist"       # Deep expertise in a domain
    GENERALIST = "generalist"       # Broad knowledge, fallback
    REVIEWER = "reviewer"           # Validates others' work
    RESEARCHER = "researcher"       # Gathers information
    EXECUTOR = "executor"           # Performs actions/commands
    SYNTHESIZER = "synthesizer"     # Combines results from multiple agents


@dataclass(frozen=True)
class AgentCapabilityProfile:
    """What an agent can do — used for routing decisions."""
    capabilities: tuple[str, ...]
    preferred_tools: tuple[str, ...]       # tools this agent is best at using
    forbidden_tools: tuple[str, ...]       # tools this agent must never use
    preferred_models: tuple[str, ...]      # LLM models this agent works best with
    max_concurrent_tasks: int = 1
    supports_parallel: bool = False
    supports_delegation: bool = False
    can_be_delegated_to: bool = True
    cost_tier: str = "standard"            # "cheap", "standard", "expensive"
    latency_tier: str = "standard"         # "fast", "standard", "slow"
    quality_tier: str = "standard"         # "draft", "standard", "high"


@dataclass(frozen=True)
class AgentIdentityCard:
    """Complete identity and capability description for an agent.

    This is what makes each agent truly different — not just a prompt.
    """
    agent_id: str
    display_name: str
    role: str                             # AgentRole value
    reasoning_strategy: str               # ReasoningStrategy value
    capability_profile: AgentCapabilityProfile
    system_prompt_key: str                # key into settings for prompt
    description: str = ""                 # human-readable description
    specialization: str = ""              # domain specialization
    autonomy_level: int = 5               # 1-10, how much freedom
    confidence_threshold: float = 0.7     # min confidence to act
    delegation_preference: str = "selective"  # "eager", "selective", "reluctant"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def can_delegate(self) -> bool:
        return self.capability_profile.supports_delegation

    @property
    def can_receive_delegation(self) -> bool:
        return self.capability_profile.can_be_delegated_to

    def matches_capabilities(self, required: set[str]) -> tuple[str, ...]:
        """Return the capabilities that match the required set."""
        return tuple(cap for cap in self.capability_profile.capabilities if cap in required)

    def capability_score(self, required: set[str]) -> float:
        """Score from 0-1 how well this agent matches required capabilities."""
        if not required:
            return 0.0
        matched = self.matches_capabilities(required)
        return len(matched) / len(required)


# --- Default agent identity cards (derived from canonical definitions) ---


def _build_default_identities() -> dict[str, AgentIdentityCard]:
    """Build identity cards from the factory default definitions."""
    from app.agents.factory_defaults import FACTORY_DEFAULTS

    result: dict[str, AgentIdentityCard] = {}
    for agent_id, defn in FACTORY_DEFAULTS.items():
        result[agent_id] = AgentIdentityCard(
            agent_id=agent_id,
            display_name=defn.display_name,
            role=defn.role,
            reasoning_strategy=defn.reasoning_strategy,
            capability_profile=AgentCapabilityProfile(
                capabilities=tuple(defn.capabilities),
                preferred_tools=tuple(defn.tool_policy.preferred_tools),
                forbidden_tools=tuple(defn.tool_policy.forbidden_tools),
                preferred_models=("gpt-4o", "claude-sonnet-4-20250514"),
                max_concurrent_tasks=defn.delegation.max_concurrent_tasks,
                supports_parallel=defn.delegation.supports_parallel,
                supports_delegation=defn.delegation.supports_delegation,
                can_be_delegated_to=True,
                cost_tier=defn.cost_tier,
                latency_tier=defn.latency_tier,
                quality_tier=defn.quality_tier,
            ),
            system_prompt_key=defn.prompts.fallback_system_key,
            description=defn.description,
            specialization=defn.specialization,
            autonomy_level=defn.delegation.autonomy_level,
            confidence_threshold=defn.delegation.confidence_threshold,
            delegation_preference=defn.delegation.delegation_preference,
        )
    return result


DEFAULT_AGENT_IDENTITIES: dict[str, AgentIdentityCard] = _build_default_identities()


class AgentRegistry:
    """Runtime registry for agent identity discovery and lookup."""

    def __init__(self) -> None:
        self._identities: dict[str, AgentIdentityCard] = dict(DEFAULT_AGENT_IDENTITIES)

    def register(self, identity: AgentIdentityCard) -> None:
        """Register or update an agent identity."""
        self._identities[identity.agent_id] = identity

    def get(self, agent_id: str) -> AgentIdentityCard | None:
        """Look up an agent's identity card."""
        return self._identities.get((agent_id or "").strip().lower())

    def list_all(self) -> list[AgentIdentityCard]:
        """List all registered agent identities."""
        return list(self._identities.values())

    def find_by_role(self, role: str) -> list[AgentIdentityCard]:
        """Find agents by their role."""
        normalized = (role or "").strip().lower()
        return [card for card in self._identities.values() if card.role == normalized]

    def find_by_capability(self, capability: str) -> list[AgentIdentityCard]:
        """Find agents that have a specific capability."""
        normalized = (capability or "").strip().lower()
        return [
            card for card in self._identities.values()
            if normalized in card.capability_profile.capabilities
        ]

    def find_best_match(self, required_capabilities: set[str]) -> AgentIdentityCard | None:
        """Find the agent that best matches a set of required capabilities."""
        if not required_capabilities:
            return self._identities.get("head-agent")

        candidates = [
            (card, card.capability_score(required_capabilities))
            for card in self._identities.values()
            if card.can_receive_delegation
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0] if candidates and candidates[0][1] > 0 else None

    def find_delegatable(self) -> list[AgentIdentityCard]:
        """Find agents that can receive delegated work."""
        return [card for card in self._identities.values() if card.can_receive_delegation]

    def find_coordinators(self) -> list[AgentIdentityCard]:
        """Find agents with coordinator role."""
        return self.find_by_role(AgentRole.COORDINATOR)
