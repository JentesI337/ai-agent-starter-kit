from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AmbiguityAssessment:
    is_ambiguous: bool
    confidence: float
    ambiguity_type: str | None
    clarification_question: str | None
    default_interpretation: str | None


class AmbiguityDetector:
    # NOTE: This detector is intentionally minimal.
    #
    # Heuristic checks for "conflicting actions", "missing parameters",
    # "multi-intent", and "short message" have all been removed because they
    # are anti-patterns for this pipeline:
    #
    # - Multi-intent / multi-role orchestration requests are the core use-case.
    #   The PlanGraph + spawn_subrun + Synthesizer pipeline is purpose-built to
    #   decompose and execute them. A regex gate here fires false positives and
    #   breaks the flow (see CRITICALBUG.md).
    #
    # - "Conflicting pair" keyword matching (create/delete, start/stop, …) hits
    #   on compound orchestration messages that contain both verbs in different
    #   roles/workstreams — exactly the worst case to interrupt.
    #
    # - Short message length is meaningless once memory_context exists.
    #
    # Only two genuinely unresolvable cases warrant a clarification interrupt:
    #   1. Completely empty input — the pipeline cannot proceed at all.
    #   2. A bare pronoun reference with no context — referent is unknowable.
    #
    # Everything else should reach the planner.

    _PRONOUNS = {"it", "this", "that", "those", "them", "es", "das", "dies", "diese", "dieses"}

    def assess(self, user_message: str, memory_context: str | None = None) -> AmbiguityAssessment:
        text = (user_message or "").strip()

        if not text:
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.2,
                ambiguity_type="vague",
                clarification_question="Could you share what you want me to do?",
                default_interpretation=None,
            )

        if self._has_unresolved_pronouns(text, memory_context):
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.4,
                ambiguity_type="incomplete",
                clarification_question="What specifically are you referring to?",
                default_interpretation=None,
            )

        return AmbiguityAssessment(
            is_ambiguous=False,
            confidence=0.9,
            ambiguity_type=None,
            clarification_question=None,
            default_interpretation=None,
        )

    def _has_unresolved_pronouns(self, text: str, context: str | None) -> bool:
        words = set(self._tokenize_words(text))
        has_pronoun = bool(words & self._PRONOUNS)
        has_context = bool((context or "").strip()) and len((context or "").strip()) > 50
        return has_pronoun and not has_context

    @staticmethod
    def _tokenize_words(text: str) -> list[str]:
        return [token for token in re.findall(r"[\w-]+", (text or "").lower()) if token]
