from __future__ import annotations

from app.errors import ToolExecutionError
from app.services.intent_detector import IntentDetector


def test_detect_extracts_command_and_forces_tool() -> None:
    detector = IntentDetector()

    decision = detector.detect('run "pytest -q"')

    assert decision.detected_intent == "execute_command"
    assert decision.gate_action == "force_tool"
    assert decision.confidence >= 0.9
    assert decision.extracted_command == "pytest -q"


def test_detect_returns_missing_slot_when_no_command() -> None:
    detector = IntentDetector()

    decision = detector.detect("run command")

    assert decision.detected_intent == "execute_command"
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

    assert detector.should_retry_fetch(ToolExecutionError("HTTP error 404")) is True
    assert detector.should_retry_fetch(ToolExecutionError("HTTP error 500")) is False


def test_web_research_task_positive_and_negative() -> None:
    detector = IntentDetector()

    assert detector.is_web_research_task("search on the web for latest llm benchmarks") is True
    assert detector.is_web_research_task("explain async await in python") is False


def test_orchestration_task_positive_and_negative() -> None:
    detector = IntentDetector()

    assert detector.is_subrun_orchestration_task("orchestrate a multi-agent analysis") is True
    assert detector.is_subrun_orchestration_task("summarize this text") is False


def test_weather_task_positive_and_negative() -> None:
    detector = IntentDetector()

    assert detector.is_weather_lookup_task("what is the weather in berlin?") is True
    assert detector.is_weather_lookup_task("what is the capital of germany?") is False
