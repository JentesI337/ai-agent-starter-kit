from __future__ import annotations

from app.errors import ToolExecutionError
from app.services.intent_detector import IntentDetector


def test_detect_intent_gate_extracts_command() -> None:
    detector = IntentDetector()

    decision = detector.detect_intent_gate('run "pytest -q"')

    assert decision.intent == "execute_command"
    assert decision.extracted_command == "pytest -q"


def test_detect_intent_gate_returns_missing_slot_when_no_command() -> None:
    detector = IntentDetector()

    decision = detector.detect_intent_gate("run command")

    assert decision.intent == "execute_command"
    assert decision.missing_slots == ("command",)


def test_file_creation_task_requires_explicit_phrase() -> None:
    detector = IntentDetector()

    assert detector.is_file_creation_task("Please explain JavaScript closures") is False
    assert detector.is_file_creation_task("create a file with hello") is True


def test_web_fetch_success_detection() -> None:
    detector = IntentDetector()

    assert detector.has_successful_web_fetch("[web_fetch]\ncontent") is True
    assert detector.has_successful_web_fetch("[web_fetch] ERROR: no") is False


def test_should_retry_web_fetch_on_404() -> None:
    detector = IntentDetector()

    assert detector.should_retry_web_fetch_on_404(ToolExecutionError("HTTP error 404")) is True
    assert detector.should_retry_web_fetch_on_404(ToolExecutionError("HTTP error 500")) is False
