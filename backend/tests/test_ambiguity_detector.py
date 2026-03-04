from __future__ import annotations

from app.services.ambiguity_detector import AmbiguityDetector


def test_assess_short_vague_message_requires_clarification() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("help me")

    assert verdict.is_ambiguous is True
    assert verdict.ambiguity_type == "vague"
    assert verdict.clarification_question is not None


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


def test_assess_conflicting_actions_requires_clarification() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("create and delete the same file")

    assert verdict.is_ambiguous is True
    assert verdict.ambiguity_type == "conflicting"


def test_assess_clear_request_is_not_ambiguous() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("Please run pytest for backend tests and show the failing test names")

    assert verdict.is_ambiguous is False
    assert verdict.clarification_question is None


def test_assess_multi_intent_is_flagged_at_boundary_confidence() -> None:
    detector = AmbiguityDetector()

    verdict = detector.assess("check logs and deploy and restart")

    assert verdict.is_ambiguous is True
    assert verdict.ambiguity_type == "multi_intent"
    assert verdict.confidence == 0.5
