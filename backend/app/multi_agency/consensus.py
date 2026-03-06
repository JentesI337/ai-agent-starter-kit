"""Consensus Engine: Multi-agent conflict resolution and voting.

When multiple agents produce results, we need mechanisms to:
- Vote on the best result
- Detect and resolve conflicts
- Merge complementary results
- Weight votes by agent confidence and expertise
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.multi_agency.agent_identity import AgentRegistry

logger = logging.getLogger(__name__)


class VotingStrategy(StrEnum):
    MAJORITY = "majority"                 # Simple majority wins
    WEIGHTED_CONFIDENCE = "weighted_confidence"  # Votes weighted by confidence
    WEIGHTED_EXPERTISE = "weighted_expertise"    # Votes weighted by capability match
    UNANIMOUS = "unanimous"               # All agents must agree
    BEST_OF_N = "best_of_n"               # Highest confidence wins


@dataclass(frozen=True)
class Vote:
    """A single vote from an agent."""
    agent_id: str
    result: Any
    confidence: float
    reasoning: str
    timestamp: str
    weight: float = 1.0          # derived from strategy
    capabilities_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConsensusResult:
    """The outcome of a consensus process."""
    consensus_reached: bool
    winning_result: Any
    winning_agent_id: str | None
    winning_confidence: float
    vote_count: int
    agreement_ratio: float         # 0-1, how many agents agree
    strategy_used: str
    votes: list[Vote]
    conflicts: list[dict[str, Any]]  # detected conflicts between votes
    metadata: dict[str, Any] = field(default_factory=dict)


class ConsensusEngine:
    """Engine for multi-agent voting and conflict resolution.

    Supports multiple voting strategies:
    - Majority: Simple majority wins
    - Weighted by confidence: Higher confidence votes count more
    - Weighted by expertise: Agents with better capability match vote stronger
    - Unanimous: All agents must agree
    - Best of N: Just pick the highest confidence result
    """

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry,
        default_strategy: str = VotingStrategy.WEIGHTED_CONFIDENCE,
        quorum: int = 2,
        conflict_similarity_threshold: float = 0.8,
    ):
        self._registry = agent_registry
        self._default_strategy = default_strategy
        self._quorum = max(1, quorum)
        self._conflict_threshold = max(0.0, min(1.0, conflict_similarity_threshold))

    def vote(
        self,
        *,
        votes: list[dict[str, Any]],
        strategy: str | None = None,
        required_capabilities: set[str] | None = None,
    ) -> ConsensusResult:
        """Run a consensus vote on a set of agent results.

        Each vote dict should have:
        - "agent_id": str
        - "result": Any
        - "confidence": float
        - "reasoning": str (optional)
        - "capabilities_used": list[str] (optional)
        """
        active_strategy = strategy or self._default_strategy
        now = datetime.now(UTC).isoformat()

        # Build Vote objects with weights
        processed_votes: list[Vote] = []
        for v in votes:
            agent_id = str(v.get("agent_id", "")).strip().lower()
            confidence = max(0.0, min(1.0, float(v.get("confidence", 0.0))))
            weight = self._compute_weight(
                agent_id=agent_id,
                confidence=confidence,
                strategy=active_strategy,
                required_capabilities=required_capabilities,
            )
            processed_votes.append(Vote(
                agent_id=agent_id,
                result=v.get("result"),
                confidence=confidence,
                reasoning=str(v.get("reasoning", "")),
                timestamp=now,
                weight=weight,
                capabilities_used=tuple(v.get("capabilities_used", ())),
            ))

        if not processed_votes:
            return ConsensusResult(
                consensus_reached=False,
                winning_result=None,
                winning_agent_id=None,
                winning_confidence=0.0,
                vote_count=0,
                agreement_ratio=0.0,
                strategy_used=active_strategy,
                votes=[],
                conflicts=[],
            )

        # Detect conflicts
        conflicts = self._detect_conflicts(processed_votes)

        # Apply voting strategy
        if active_strategy == VotingStrategy.MAJORITY:
            return self._majority_vote(processed_votes, conflicts, active_strategy)
        if active_strategy == VotingStrategy.WEIGHTED_CONFIDENCE:
            return self._weighted_confidence_vote(processed_votes, conflicts, active_strategy)
        if active_strategy == VotingStrategy.WEIGHTED_EXPERTISE:
            return self._weighted_expertise_vote(processed_votes, conflicts, active_strategy, required_capabilities)
        if active_strategy == VotingStrategy.UNANIMOUS:
            return self._unanimous_vote(processed_votes, conflicts, active_strategy)
        if active_strategy == VotingStrategy.BEST_OF_N:
            return self._best_of_n_vote(processed_votes, conflicts, active_strategy)
        return self._weighted_confidence_vote(processed_votes, conflicts, active_strategy)

    def merge_results(
        self,
        *,
        results: list[dict[str, Any]],
        merge_strategy: str = "concatenate",
    ) -> dict[str, Any]:
        """Merge complementary results from multiple agents.

        Strategies:
        - "concatenate": Combine all results
        - "deduplicate": Remove duplicate content
        - "best_sections": Take best section from each agent
        """
        if not results:
            return {"merged": None, "sources": []}

        if merge_strategy == "best_sections":
            return self._merge_best_sections(results)
        if merge_strategy == "deduplicate":
            return self._merge_deduplicate(results)
        return self._merge_concatenate(results)

    def _compute_weight(
        self,
        *,
        agent_id: str,
        confidence: float,
        strategy: str,
        required_capabilities: set[str] | None,
    ) -> float:
        """Compute vote weight based on strategy."""
        if strategy == VotingStrategy.MAJORITY:
            return 1.0
        if strategy == VotingStrategy.WEIGHTED_CONFIDENCE:
            return confidence
        if strategy == VotingStrategy.WEIGHTED_EXPERTISE:
            identity = self._registry.get(agent_id)
            if identity and required_capabilities:
                return identity.capability_score(required_capabilities)
            return confidence
        if strategy == VotingStrategy.UNANIMOUS:
            return 1.0
        if strategy == VotingStrategy.BEST_OF_N:
            return confidence
        return 1.0

    def _detect_conflicts(self, votes: list[Vote]) -> list[dict[str, Any]]:
        """Detect conflicts between agent results."""
        conflicts: list[dict[str, Any]] = []
        for i, v1 in enumerate(votes):
            for v2 in votes[i + 1:]:
                similarity = self._result_similarity(v1.result, v2.result)
                if similarity < self._conflict_threshold:
                    conflicts.append({
                        "agent_a": v1.agent_id,
                        "agent_b": v2.agent_id,
                        "similarity": similarity,
                        "confidence_a": v1.confidence,
                        "confidence_b": v2.confidence,
                    })
        return conflicts

    @staticmethod
    def _result_similarity(a: Any, b: Any) -> float:
        """Simple similarity metric between two results."""
        str_a = str(a or "").strip().lower()
        str_b = str(b or "").strip().lower()
        if not str_a or not str_b:
            return 0.0
        if str_a == str_b:
            return 1.0
        # Jaccard similarity on words
        words_a = set(str_a.split())
        words_b = set(str_b.split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    def _majority_vote(
        self,
        votes: list[Vote],
        conflicts: list[dict[str, Any]],
        strategy: str,
    ) -> ConsensusResult:
        """Simple majority voting."""
        result_groups: dict[str, list[Vote]] = defaultdict(list)
        for v in votes:
            key = str(v.result)[:200]
            result_groups[key].append(v)

        best_group = max(result_groups.values(), key=len)
        best_vote = max(best_group, key=lambda v: v.confidence)
        agreement = len(best_group) / len(votes)

        return ConsensusResult(
            consensus_reached=len(best_group) > len(votes) / 2,
            winning_result=best_vote.result,
            winning_agent_id=best_vote.agent_id,
            winning_confidence=best_vote.confidence,
            vote_count=len(votes),
            agreement_ratio=agreement,
            strategy_used=strategy,
            votes=votes,
            conflicts=conflicts,
        )

    def _weighted_confidence_vote(
        self,
        votes: list[Vote],
        conflicts: list[dict[str, Any]],
        strategy: str,
    ) -> ConsensusResult:
        """Votes weighted by confidence score."""
        result_scores: dict[str, float] = defaultdict(float)
        result_votes: dict[str, list[Vote]] = defaultdict(list)
        for v in votes:
            key = str(v.result)[:200]
            result_scores[key] += v.weight
            result_votes[key].append(v)

        best_key = max(result_scores, key=result_scores.get)  # type: ignore
        best_group = result_votes[best_key]
        best_vote = max(best_group, key=lambda v: v.confidence)
        total_weight = sum(result_scores.values())
        agreement = result_scores[best_key] / total_weight if total_weight > 0 else 0

        return ConsensusResult(
            consensus_reached=agreement > 0.5,
            winning_result=best_vote.result,
            winning_agent_id=best_vote.agent_id,
            winning_confidence=best_vote.confidence,
            vote_count=len(votes),
            agreement_ratio=agreement,
            strategy_used=strategy,
            votes=votes,
            conflicts=conflicts,
            metadata={"weighted_scores": dict(result_scores)},
        )

    def _weighted_expertise_vote(
        self,
        votes: list[Vote],
        conflicts: list[dict[str, Any]],
        strategy: str,
        required_capabilities: set[str] | None,
    ) -> ConsensusResult:
        """Votes weighted by capability match."""
        # Create a copy with recalculated weights using expertise (Vote is frozen)
        updated_votes: list[Vote] = []
        for v in votes:
            identity = self._registry.get(v.agent_id)
            if identity and required_capabilities:
                expertise_weight = identity.capability_score(required_capabilities)
            else:
                expertise_weight = v.confidence
            updated_votes.append(Vote(
                agent_id=v.agent_id,
                result=v.result,
                confidence=v.confidence,
                reasoning=v.reasoning,
                timestamp=v.timestamp,
                weight=expertise_weight,
                capabilities_used=v.capabilities_used,
            ))

        return self._weighted_confidence_vote(updated_votes, conflicts, strategy)

    def _unanimous_vote(
        self,
        votes: list[Vote],
        conflicts: list[dict[str, Any]],
        strategy: str,
    ) -> ConsensusResult:
        """All agents must agree."""
        if len(votes) < self._quorum:
            return ConsensusResult(
                consensus_reached=False,
                winning_result=None,
                winning_agent_id=None,
                winning_confidence=0.0,
                vote_count=len(votes),
                agreement_ratio=0.0,
                strategy_used=strategy,
                votes=votes,
                conflicts=conflicts,
            )

        first_result = str(votes[0].result)[:200]
        all_agree = all(str(v.result)[:200] == first_result for v in votes)
        best_vote = max(votes, key=lambda v: v.confidence)

        return ConsensusResult(
            consensus_reached=all_agree,
            winning_result=best_vote.result if all_agree else None,
            winning_agent_id=best_vote.agent_id if all_agree else None,
            winning_confidence=best_vote.confidence if all_agree else 0.0,
            vote_count=len(votes),
            agreement_ratio=1.0 if all_agree else 0.0,
            strategy_used=strategy,
            votes=votes,
            conflicts=conflicts,
        )

    def _best_of_n_vote(
        self,
        votes: list[Vote],
        conflicts: list[dict[str, Any]],
        strategy: str,
    ) -> ConsensusResult:
        """Simply pick the highest confidence result."""
        best = max(votes, key=lambda v: v.confidence)
        return ConsensusResult(
            consensus_reached=True,
            winning_result=best.result,
            winning_agent_id=best.agent_id,
            winning_confidence=best.confidence,
            vote_count=len(votes),
            agreement_ratio=1.0 / len(votes),
            strategy_used=strategy,
            votes=votes,
            conflicts=conflicts,
        )

    @staticmethod
    def _merge_concatenate(results: list[dict[str, Any]]) -> dict[str, Any]:
        """Concatenate all results."""
        merged_parts = []
        sources = []
        for r in results:
            merged_parts.append(str(r.get("result", "")))
            sources.append(r.get("agent_id", "unknown"))
        return {
            "merged": "\n\n---\n\n".join(merged_parts),
            "sources": sources,
            "strategy": "concatenate",
        }

    @staticmethod
    def _merge_deduplicate(results: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge with deduplication of similar content."""
        seen_hashes: set[str] = set()
        unique_parts = []
        sources = []
        for r in results:
            text = str(r.get("result", "")).strip()
            text_hash = text[:200].lower()
            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                unique_parts.append(text)
                sources.append(r.get("agent_id", "unknown"))
        return {
            "merged": "\n\n---\n\n".join(unique_parts),
            "sources": sources,
            "strategy": "deduplicate",
            "original_count": len(results),
            "unique_count": len(unique_parts),
        }

    @staticmethod
    def _merge_best_sections(results: list[dict[str, Any]]) -> dict[str, Any]:
        """Take the best section from each agent based on confidence."""
        # Group by confidence and take highest
        sorted_results = sorted(
            results,
            key=lambda r: float(r.get("confidence", 0.0)),
            reverse=True,
        )
        if sorted_results:
            best = sorted_results[0]
            return {
                "merged": str(best.get("result", "")),
                "sources": [best.get("agent_id", "unknown")],
                "strategy": "best_sections",
                "selected_confidence": float(best.get("confidence", 0.0)),
            }
        return {"merged": None, "sources": [], "strategy": "best_sections"}
