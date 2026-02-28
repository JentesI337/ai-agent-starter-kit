"""
Context Reducer — trims and prioritizes context per token budget.

Models receive only what fits within their context window.
The reducer selects the most relevant information and discards the rest.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ≈ 4 characters for English text.
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ContextChunk:
    """A labelled piece of context with a priority score."""
    label: str
    content: str
    priority: float = 1.0  # Higher = more important, kept first
    token_estimate: int = 0  # 0 = auto-estimate from content length

    def estimated_tokens(self) -> int:
        if self.token_estimate > 0:
            return self.token_estimate
        return max(1, len(self.content) // CHARS_PER_TOKEN)


@dataclass
class ReducedContext:
    """Result of context reduction."""
    chunks: list[ContextChunk] = field(default_factory=list)
    total_tokens: int = 0
    dropped_chunks: int = 0
    dropped_labels: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Render all kept chunks into a single string."""
        parts: list[str] = []
        for chunk in self.chunks:
            parts.append(f"[{chunk.label}]\n{chunk.content}")
        return "\n\n".join(parts)


class ContextReducer:
    """
    Trims and prioritizes context to fit within a token budget.

    Strategy:
    1. Sort chunks by priority (descending)
    2. Greedily add chunks until budget is exhausted
    3. If a chunk is too large, truncate it to fill remaining budget
    4. Log what was dropped for debugging
    """

    def __init__(self, default_budget: int = 4000):
        self.default_budget = default_budget

    def reduce(
        self,
        chunks: list[ContextChunk],
        token_budget: int | None = None,
        reserve_tokens: int = 0,
    ) -> ReducedContext:
        """
        Reduce a list of context chunks to fit within *token_budget*.

        Args:
            chunks: Unordered list of context chunks.
            token_budget: Max tokens for the reduced context. Uses default if None.
            reserve_tokens: Tokens to reserve for system prompt / output.
        """
        budget = (token_budget or self.default_budget) - reserve_tokens
        if budget <= 0:
            logger.warning("context_reducer budget_exhausted budget=%d reserve=%d", budget, reserve_tokens)
            return ReducedContext(dropped_chunks=len(chunks), dropped_labels=[c.label for c in chunks])

        # Sort by priority descending, then by label for determinism
        sorted_chunks = sorted(chunks, key=lambda c: (-c.priority, c.label))

        result = ReducedContext()
        remaining = budget

        for chunk in sorted_chunks:
            tokens = chunk.estimated_tokens()
            if tokens <= remaining:
                # Fits entirely
                result.chunks.append(chunk)
                result.total_tokens += tokens
                remaining -= tokens
            elif remaining >= 8:
                # Truncate to fill remaining budget
                max_chars = remaining * CHARS_PER_TOKEN
                truncated_content = chunk.content[:max_chars]
                if len(truncated_content) < len(chunk.content):
                    truncated_content += "\n... [truncated]"
                truncated_chunk = ContextChunk(
                    label=chunk.label,
                    content=truncated_content,
                    priority=chunk.priority,
                    token_estimate=remaining,
                )
                result.chunks.append(truncated_chunk)
                result.total_tokens += remaining
                remaining = 0
            else:
                # Drop entirely
                result.dropped_chunks += 1
                result.dropped_labels.append(chunk.label)

        if result.dropped_chunks > 0:
            logger.info(
                "context_reducer dropped_chunks=%d labels=%s budget=%d used=%d",
                result.dropped_chunks,
                result.dropped_labels,
                budget,
                result.total_tokens,
            )

        return result

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate from character count."""
        return max(1, len(text) // CHARS_PER_TOKEN)

    def build_agent_context(
        self,
        task_slice: dict[str, Any],
        session_summary: dict[str, Any] | None = None,
        evidence: str = "",
        history_summary: str = "",
        token_budget: int | None = None,
    ) -> ReducedContext:
        """
        Convenience method: build and reduce context for an agent call.
        Assigns default priorities to standard context types.
        """
        import json

        chunks: list[ContextChunk] = []

        # Task input — highest priority
        task_json = json.dumps(task_slice, indent=2, ensure_ascii=False, default=str)
        chunks.append(ContextChunk(label="task", content=task_json, priority=10.0))

        # Evidence — high priority
        if evidence:
            chunks.append(ContextChunk(label="evidence", content=evidence, priority=8.0))

        # Session summary — medium priority
        if session_summary:
            summary_json = json.dumps(session_summary, indent=2, ensure_ascii=False, default=str)
            chunks.append(ContextChunk(label="session_summary", content=summary_json, priority=5.0))

        # History — low priority
        if history_summary:
            chunks.append(ContextChunk(label="history", content=history_summary, priority=3.0))

        return self.reduce(chunks, token_budget=token_budget)
