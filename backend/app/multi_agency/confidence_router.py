"""Confidence Router: Uses confidence scores for real routing decisions.

Replaces the current system where confidence is serialized but never evaluated.

Architecture:
- Evaluates handover contract confidence for routing decisions
- Routes to different agents based on confidence level
- Triggers re-delegation when confidence drops below threshold
- Maintains confidence history for learning
- Provides confidence-weighted agent selection
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.multi_agency.agent_identity import AgentIdentityCard, AgentRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfidenceRouteDecision:
    """The result of confidence-based routing."""
    action: str                    # "accept", "redelegate", "review", "reject", "escalate"
    selected_agent_id: str | None
    confidence: float
    reason: str
    alternatives: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfidenceHistoryEntry:
    """Tracks confidence over time for an agent."""
    agent_id: str
    task_description: str
    confidence: float
    outcome: str         # "success", "failure", "partial"
    timestamp: str
    capabilities_used: tuple[str, ...]


class ConfidenceRouter:
    """Routes tasks based on confidence scores — not just capability matching.
    
    Key improvements over current agent_resolution.py:
    1. Evaluates handover contract confidence (currently ignored)
    2. Tracks per-agent confidence history (learning)
    3. Adjusts routing based on historical performance
    4. Implements quality gates: low confidence → redelegate or review
    5. Provides confidence-weighted scoring for agent selection
    """

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry,
        accept_threshold: float = 0.7,
        review_threshold: float = 0.5,
        reject_threshold: float = 0.3,
        history_weight: float = 0.3,      # how much history affects scoring
        max_history_per_agent: int = 100,
    ):
        self._registry = agent_registry
        self._accept_threshold = max(0.0, min(1.0, accept_threshold))
        self._review_threshold = max(0.0, min(1.0, review_threshold))
        self._reject_threshold = max(0.0, min(1.0, reject_threshold))
        self._history_weight = max(0.0, min(1.0, history_weight))
        self._max_history = max(1, max_history_per_agent)
        # agent_id -> list of confidence history entries
        self._history: dict[str, list[ConfidenceHistoryEntry]] = defaultdict(list)
        # agent_id -> running average confidence
        self._avg_confidence: dict[str, float] = {}

    def evaluate_handover(
        self,
        *,
        handover_contract: dict[str, Any],
        source_agent_id: str,
        task_description: str = "",
    ) -> ConfidenceRouteDecision:
        """Evaluate a handover contract and decide what to do with the result.
        
        This is the KEY function that the current system is missing.
        The handover contract has a confidence field that is serialized but never evaluated.
        """
        confidence = self._extract_confidence(handover_contract)
        terminal_reason = str(handover_contract.get("terminal_reason", "")).strip()
        result = handover_contract.get("result")
        synthesis_valid = handover_contract.get("synthesis_valid")

        # Factor 1: Raw confidence from the handover
        raw_score = confidence

        # Factor 2: Historical performance of this agent
        historical_score = self._get_historical_confidence(source_agent_id)
        if historical_score is not None:
            adjusted_score = (
                raw_score * (1 - self._history_weight)
                + historical_score * self._history_weight
            )
        else:
            adjusted_score = raw_score

        # Factor 3: Terminal reason signals
        if terminal_reason in ("subrun-error", "subrun-timeout"):
            adjusted_score *= 0.3  # Heavily penalize errors/timeouts
        elif terminal_reason == "subrun-complete" and synthesis_valid is False:
            adjusted_score *= 0.5  # Penalize invalid synthesis

        # Decision logic
        if adjusted_score >= self._accept_threshold:
            return ConfidenceRouteDecision(
                action="accept",
                selected_agent_id=source_agent_id,
                confidence=adjusted_score,
                reason=f"Confidence {adjusted_score:.2f} >= accept threshold {self._accept_threshold:.2f}",
                metadata={
                    "raw_confidence": raw_score,
                    "historical_confidence": historical_score,
                    "adjusted_confidence": adjusted_score,
                    "terminal_reason": terminal_reason,
                },
            )

        if adjusted_score >= self._review_threshold:
            # Find a reviewer agent
            reviewer = self._find_reviewer(exclude=source_agent_id)
            return ConfidenceRouteDecision(
                action="review",
                selected_agent_id=reviewer.agent_id if reviewer else None,
                confidence=adjusted_score,
                reason=f"Confidence {adjusted_score:.2f} in review range [{self._review_threshold:.2f}, {self._accept_threshold:.2f})",
                alternatives=[reviewer.agent_id] if reviewer else [],
                metadata={
                    "raw_confidence": raw_score,
                    "needs_review_by": reviewer.agent_id if reviewer else "none",
                },
            )

        if adjusted_score >= self._reject_threshold:
            # Redelegate to a different agent
            alternative = self._find_alternative(
                exclude=source_agent_id,
                task_description=task_description,
            )
            return ConfidenceRouteDecision(
                action="redelegate",
                selected_agent_id=alternative.agent_id if alternative else None,
                confidence=adjusted_score,
                reason=f"Confidence {adjusted_score:.2f} below review threshold, redelegating",
                alternatives=[alternative.agent_id] if alternative else [],
                metadata={
                    "raw_confidence": raw_score,
                    "redelegate_to": alternative.agent_id if alternative else "none",
                },
            )

        return ConfidenceRouteDecision(
            action="reject",
            selected_agent_id=None,
            confidence=adjusted_score,
            reason=f"Confidence {adjusted_score:.2f} below reject threshold {self._reject_threshold:.2f}",
            metadata={"raw_confidence": raw_score},
        )

    def route_by_confidence(
        self,
        *,
        required_capabilities: set[str],
        preferred_quality: str = "standard",  # "draft", "standard", "high"
    ) -> ConfidenceRouteDecision:
        """Select the best agent based on capability match AND historical confidence.
        
        This replaces the current capability_route_agent() which only considers
        raw capability matching without any confidence history.
        """
        candidates: list[tuple[AgentIdentityCard, float]] = []

        for identity in self._registry.list_all():
            if not identity.can_receive_delegation:
                continue

            # Capability score
            capability_score = identity.capability_score(required_capabilities)
            if capability_score <= 0:
                continue

            # Historical confidence adjustment
            hist = self._get_historical_confidence(identity.agent_id)
            if hist is not None:
                combined_score = (
                    capability_score * (1 - self._history_weight)
                    + hist * self._history_weight
                )
            else:
                combined_score = capability_score

            # Quality tier adjustment
            if preferred_quality == "high" and identity.capability_profile.quality_tier == "high":
                combined_score *= 1.2
            elif preferred_quality == "draft" and identity.capability_profile.quality_tier == "draft":
                combined_score *= 1.1

            # Confidence threshold check
            if combined_score >= identity.confidence_threshold or hist is None:
                candidates.append((identity, combined_score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        if not candidates:
            return ConfidenceRouteDecision(
                action="reject",
                selected_agent_id=None,
                confidence=0.0,
                reason=f"No agent matches capabilities: {required_capabilities}",
            )

        best, score = candidates[0]
        alternatives = [c[0].agent_id for c in candidates[1:4]]

        return ConfidenceRouteDecision(
            action="accept",
            selected_agent_id=best.agent_id,
            confidence=score,
            reason=f"Best match: {best.agent_id} (score={score:.2f})",
            alternatives=alternatives,
            metadata={
                "capability_score": best.capability_score(required_capabilities),
                "historical_confidence": self._get_historical_confidence(best.agent_id),
            },
        )

    def record_outcome(
        self,
        *,
        agent_id: str,
        task_description: str,
        confidence: float,
        outcome: str,
        capabilities_used: tuple[str, ...] = (),
    ) -> None:
        """Record the outcome of a task for confidence learning.
        
        This builds the historical knowledge that improves routing over time.
        """
        normalized = (agent_id or "").strip().lower()
        entry = ConfidenceHistoryEntry(
            agent_id=normalized,
            task_description=task_description[:200],
            confidence=max(0.0, min(1.0, float(confidence))),
            outcome=outcome,
            timestamp=datetime.now(timezone.utc).isoformat(),
            capabilities_used=capabilities_used,
        )

        history = self._history[normalized]
        history.append(entry)
        if len(history) > self._max_history:
            self._history[normalized] = history[-self._max_history:]

        # Update running average
        self._avg_confidence[normalized] = sum(
            e.confidence for e in self._history[normalized]
        ) / len(self._history[normalized])

    def _get_historical_confidence(self, agent_id: str) -> float | None:
        """Get the historical average confidence for an agent."""
        normalized = (agent_id or "").strip().lower()
        return self._avg_confidence.get(normalized)

    def _find_reviewer(self, exclude: str) -> AgentIdentityCard | None:
        """Find a reviewer agent."""
        reviewers = self._registry.find_by_role("reviewer")
        for r in reviewers:
            if r.agent_id != exclude:
                return r
        # Fallback: any agent that isn't the excluded one
        for card in self._registry.list_all():
            if card.agent_id != exclude and card.can_receive_delegation:
                return card
        return None

    def _find_alternative(self, exclude: str, task_description: str = "") -> AgentIdentityCard | None:
        """Find an alternative agent for redelegation."""
        for card in self._registry.find_delegatable():
            if card.agent_id != exclude:
                return card
        return None

    @staticmethod
    def _extract_confidence(handover: dict[str, Any]) -> float:
        """Extract confidence from a handover contract, handling all edge cases."""
        raw = handover.get("confidence", 0.0)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            if isinstance(raw, str):
                mapping = {"high": 0.9, "medium": 0.6, "low": 0.3}
                return mapping.get(raw.strip().lower(), 0.0)
            return 0.0
        return max(0.0, min(1.0, val))

    def get_confidence_report(self) -> dict[str, Any]:
        """Get a summary of confidence data for all agents."""
        report: dict[str, Any] = {}
        for agent_id, history in self._history.items():
            if not history:
                continue
            avg = self._avg_confidence.get(agent_id, 0.0)
            successes = sum(1 for e in history if e.outcome == "success")
            failures = sum(1 for e in history if e.outcome == "failure")
            report[agent_id] = {
                "avg_confidence": round(avg, 3),
                "total_tasks": len(history),
                "successes": successes,
                "failures": failures,
                "success_rate": round(successes / len(history), 3) if history else 0.0,
                "latest_confidence": history[-1].confidence if history else None,
            }
        return report
