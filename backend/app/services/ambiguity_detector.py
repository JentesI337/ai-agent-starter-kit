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
    _SIMPLE_COMMANDS = {
        "ls",
        "dir",
        "pwd",
        "help",
        "status",
        "continue",
        "stop",
        "retry",
        "run",
        "execute",
        "start",
        "launch",
    }
    _PRONOUNS = {"it", "this", "that", "those", "them", "es", "das", "dies", "diese", "dieses"}
    _CONFLICTING_PAIRS = (
        ("create", "delete"),
        ("add", "remove"),
        ("enable", "disable"),
        ("start", "stop"),
        ("install", "uninstall"),
        ("erstelle", "lösche"),
        ("anlegen", "löschen"),
        ("aktivieren", "deaktivieren"),
        ("starten", "stoppen"),
    )
    _PARAMETER_REQUIRED_VERBS = {
        "deploy",
        "release",
        "rollback",
        "migrate",
        "connect",
        "open",
        "download",
        "upload",
    }

    def assess(self, user_message: str, memory_context: str | None = None) -> AmbiguityAssessment:
        text = (user_message or "").strip()
        has_context = bool((memory_context or "").strip()) and len((memory_context or "").strip()) > 50
        if not text:
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.2,
                ambiguity_type="vague",
                clarification_question="Could you share what you want me to do?",
                default_interpretation=None,
            )

        words = self._tokenize_words(text)
        word_count = len(words)

        if self._has_unresolved_pronouns(text, memory_context):
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.4,
                ambiguity_type="incomplete",
                clarification_question="What specifically are you referring to?",
                default_interpretation=None,
            )

        if word_count < 3 and not self._is_simple_command(text) and not has_context:
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.3,
                ambiguity_type="vague",
                clarification_question=(
                    f'Your request "{text}" is quite short. Could you provide more details about what you need?'
                ),
                default_interpretation=None,
            )

        if self._has_missing_parameters(words):
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.35,
                ambiguity_type="incomplete",
                clarification_question="I can do that. Which target or parameters should I use?",
                default_interpretation=None,
            )

        if self._has_conflicting_requests(words):
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.45,
                ambiguity_type="conflicting",
                clarification_question="Your request includes conflicting actions. Which action should I do first?",
                default_interpretation=None,
            )

        # NOTE: multi_intent detection removed by design.
        # The planner pipeline (PlanGraph with dependency-aware steps,
        # replan loop, and synthesizer) is purpose-built to decompose
        # and execute multi-intent requests. A naive regex gate here
        # would block the pipeline's core competency.

        return AmbiguityAssessment(
            is_ambiguous=False,
            confidence=0.8,
            ambiguity_type=None,
            clarification_question=None,
            default_interpretation=None,
        )

    def _is_simple_command(self, text: str) -> bool:
        normalized = (text or "").strip().lower()
        return normalized in self._SIMPLE_COMMANDS

    def _has_unresolved_pronouns(self, text: str, context: str | None) -> bool:
        words = set(self._tokenize_words(text))
        has_pronoun = bool(words & self._PRONOUNS)
        has_context = bool((context or "").strip()) and len((context or "").strip()) > 50
        return has_pronoun and not has_context

    def _has_missing_parameters(self, words: list[str]) -> bool:
        if not words:
            return False
        first = words[0]
        return first in self._PARAMETER_REQUIRED_VERBS and len(words) <= 2

    def _has_conflicting_requests(self, words: list[str]) -> bool:
        word_set = set(words)
        for left, right in self._CONFLICTING_PAIRS:
            if left in word_set and right in word_set:
                return True
        return False

    @staticmethod
    def _tokenize_words(text: str) -> list[str]:
        return [token for token in re.findall(r"[\w-]+", (text or "").lower()) if token]
