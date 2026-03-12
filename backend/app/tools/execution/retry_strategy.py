"""Reason-aware retry strategy for tool calls.

Classifies errors via the shared :mod:`error_taxonomy` and decides
optimal retry strategy: backoff, escalate, or let replan handle it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.services.error_taxonomy import ErrorCategory, classify_error

# ── Typed enums for strategy / retry-class ────────────────────────────

class RetryStrategy(StrEnum):
    BACKOFF = "backoff"
    ESCALATE = "escalate"
    REPLAN = "replan"
    SKIP = "skip"


RetryClass = Literal["transient", "timeout", "none"]


@dataclass(frozen=True)
class RetryDecision:
    """Outcome of a retry strategy evaluation."""

    should_retry: bool
    strategy: RetryStrategy
    delay_seconds: float
    reason: str
    error_category: ErrorCategory


class ToolRetryStrategy:
    """Analyzes tool errors and decides whether/how to retry.

    Error taxonomy (from ``error_taxonomy.ErrorCategory``):
        transient          → retry with exponential backoff
        missing_dependency → don't retry, signal to LLM for replan
        invalid_args       → don't retry, replan with error context
        permission         → don't retry, escalate to user
        resource_exhaustion→ retry once after wait
        crash              → don't retry, replan
        unknown            → retry if retry_class allows
    """

    # Strategy mapping: category → (should_retry, strategy)
    _STRATEGY_MAP: dict[ErrorCategory, tuple[bool, RetryStrategy]] = {
        ErrorCategory.TRANSIENT: (True, RetryStrategy.BACKOFF),
        ErrorCategory.MISSING_DEPENDENCY: (False, RetryStrategy.REPLAN),
        ErrorCategory.INVALID_ARGS: (False, RetryStrategy.REPLAN),
        ErrorCategory.PERMISSION: (False, RetryStrategy.ESCALATE),
        ErrorCategory.RESOURCE_EXHAUSTION: (True, RetryStrategy.BACKOFF),
        ErrorCategory.CRASH: (False, RetryStrategy.REPLAN),
        ErrorCategory.UNKNOWN: (False, RetryStrategy.SKIP),
    }

    @staticmethod
    def classify_error(error_text: str) -> ErrorCategory:
        """Classify an error via the shared taxonomy."""
        return classify_error(error_text)

    def decide(
        self,
        *,
        error_text: str,
        retry_class: RetryClass,
        attempt: int,
        max_retries: int,
    ) -> RetryDecision:
        """Decide whether to retry and with what strategy.

        Args:
            error_text: The error message from the tool.
            retry_class: Policy retry class ("transient", "timeout", "none").
            attempt: Current attempt number (1-based).
            max_retries: Maximum retries configured.

        Returns:
            RetryDecision with strategy details.
        """
        category = self.classify_error(error_text)

        # No retries allowed by policy
        if retry_class == "none":
            _should, strategy = self._STRATEGY_MAP.get(
                category, (False, RetryStrategy.SKIP),
            )
            return RetryDecision(
                should_retry=False,
                strategy=strategy,
                delay_seconds=0.0,
                reason=f"Retry disabled by policy (category={category})",
                error_category=category,
            )

        # Budget exhausted
        if attempt >= max_retries + 1:
            _should, strategy = self._STRATEGY_MAP.get(
                category, (False, RetryStrategy.SKIP),
            )
            return RetryDecision(
                should_retry=False,
                strategy=strategy,
                delay_seconds=0.0,
                reason=f"Retry budget exhausted ({attempt}/{max_retries + 1})",
                error_category=category,
            )

        _should_retry, strategy = self._STRATEGY_MAP.get(
            category, (False, RetryStrategy.SKIP),
        )

        # Transient: always retry if policy allows
        if category == ErrorCategory.TRANSIENT and retry_class in {"transient", "timeout"}:
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.BACKOFF,
                delay_seconds=self.backoff_delay(attempt),
                reason=f"Transient error, retrying (attempt {attempt})",
                error_category=category,
            )

        # Resource exhaustion: retry once with longer wait
        if category == ErrorCategory.RESOURCE_EXHAUSTION and retry_class == "transient":
            return RetryDecision(
                should_retry=attempt <= 1,
                strategy=RetryStrategy.BACKOFF,
                delay_seconds=self.backoff_delay(attempt, base=3.0),
                reason="Resource exhaustion, waiting before retry",
                error_category=category,
            )

        # Timeout-only class: match actual timeouts
        if retry_class == "timeout" and "timeout" in error_text.lower():
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.BACKOFF,
                delay_seconds=self.backoff_delay(attempt),
                reason="Timeout error, retrying",
                error_category=ErrorCategory.TRANSIENT,
            )

        # Everything else: don't retry
        return RetryDecision(
            should_retry=False,
            strategy=strategy,
            delay_seconds=0.0,
            reason=f"Non-retryable error category: {category}",
            error_category=category,
        )

    @staticmethod
    def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
        """Exponential backoff: base * 2^(attempt-1), capped."""
        return min(base * (2 ** (attempt - 1)), cap)
