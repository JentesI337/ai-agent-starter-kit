from __future__ import annotations

from app.services.ambiguity_detector import AmbiguityDetector


def test_assess_short_message_is_not_ambiguous_because_planner_handles_it() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("help me")

    # Short messages are no longer intercepted: the planner is better placed
    # to decide whether it needs more information. Only truly empty input blocks.
    assert verdict.is_ambiguous is False
    assert verdict.clarification_question is None


def test_assess_unresolved_pronoun_without_context_requires_clarification() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("fix it")

    assert verdict.is_ambiguous is True
    assert verdict.ambiguity_type == "incomplete"


def test_assess_unresolved_pronoun_with_context_is_not_ambiguous() -> None:
    detector = AmbiguityDetector()
    context = "Previous issue: test_websocket_flow is failing because the payload serializer drops request_id in nested events."

    verdict = detector.assess("fix it", context)

    assert verdict.is_ambiguous is False


def test_assess_conflicting_keyword_pair_is_not_ambiguous_because_planner_handles_it() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("create and delete the same file")

    # "Conflicting pair" keyword matching was removed: the same heuristic that
    # correctly catches create+delete also fires on legitimate orchestration
    # messages that contain both verbs in different roles (see CRITICALBUG.md).
    # The planner resolves ordering and intent; the detector must not block it.
    assert verdict.is_ambiguous is False
    assert verdict.ambiguity_type is None


def test_assess_clear_request_is_not_ambiguous() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("Please run pytest for backend tests and show the failing test names")

    assert verdict.is_ambiguous is False
    assert verdict.clarification_question is None


def test_assess_multi_intent_is_not_ambiguous_because_planner_handles_it() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("check logs and deploy and restart and verify")

    # Multi-intent is NOT ambiguous by design: the planner pipeline
    # (PlanGraph, replan loop, synthesizer) decomposes multi-intent
    # requests into executable steps.
    assert verdict.is_ambiguous is False
    assert verdict.ambiguity_type is None
