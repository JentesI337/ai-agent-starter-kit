"""Unit tests for LearningLoop (L5.5)."""

from __future__ import annotations

import pytest

from app.memory.adaptive_selector import AdaptiveToolSelector
from app.memory.learning_loop import LearningLoop
from app.quality.execution_pattern_detector import ExecutionPatternDetector
from app.tools.discovery.knowledge_base import ToolKnowledgeBase


@pytest.fixture
def selector():
    return AdaptiveToolSelector()


@pytest.fixture
def kb():
    return ToolKnowledgeBase()


@pytest.fixture
def detector():
    return ExecutionPatternDetector()


@pytest.fixture
def loop(selector, kb, detector):
    return LearningLoop(selector=selector, kb=kb, detector=detector)


class TestOnToolOutcome:
    def test_feeds_selector(self, loop: LearningLoop, selector: AdaptiveToolSelector):
        loop.on_tool_outcome(tool="jq", success=True, duration_ms=10.0)
        assert "jq" in selector.known_tools()
        h = selector.get_history("jq")
        assert h is not None
        assert h["successes"] == 1

    def test_feeds_kb_with_capability(self, loop: LearningLoop, kb: ToolKnowledgeBase):
        loop.on_tool_outcome(
            tool="jq", success=True, duration_ms=10.0,
            capability="json_processing",
        )
        entries = kb.find_tools_for_capability("json")
        assert len(entries) == 1
        assert entries[0].tool == "jq"

    def test_skips_kb_without_capability(self, loop: LearningLoop, kb: ToolKnowledgeBase):
        loop.on_tool_outcome(tool="jq", success=True, duration_ms=10.0)
        assert kb.count() == 0

    def test_feeds_detector(self, loop: LearningLoop, detector: ExecutionPatternDetector):
        loop.on_tool_outcome(
            tool="run_command", success=True,
            args={"command": "ls -la"},
        )
        # No alert for single observation
        assert detector.check() == []

    def test_failure_records_low_confidence(self, loop: LearningLoop, kb: ToolKnowledgeBase):
        loop.on_tool_outcome(
            tool="broken", success=False, capability="something",
        )
        entries = kb.find_tools_for_capability("something", min_confidence=0.0)
        assert len(entries) == 1
        assert entries[0].confidence == 0.3  # low confidence on failure


class TestCheckPatterns:
    def test_detects_infinite_retry(self, loop: LearningLoop):
        for _ in range(5):
            loop.on_tool_outcome(
                tool="run_command", success=False,
                args={"command": "failing-command"},
            )
        alerts = loop.check_patterns()
        retry_alerts = [a for a in alerts if a.pattern == "infinite_retry"]
        assert len(retry_alerts) == 1

    def test_no_alert_clean(self, loop: LearningLoop):
        loop.on_tool_outcome(tool="ls", success=True, args={"command": "ls"})
        assert loop.check_patterns() == []


class TestAccessors:
    def test_selector_property(self, loop: LearningLoop, selector: AdaptiveToolSelector):
        assert loop.selector is selector

    def test_kb_property(self, loop: LearningLoop, kb: ToolKnowledgeBase):
        assert loop.knowledge_base is kb

    def test_detector_property(self, loop: LearningLoop, detector: ExecutionPatternDetector):
        assert loop.detector is detector


class TestDefaultInit:
    def test_default_creates_all(self):
        loop = LearningLoop()
        assert loop.selector is not None
        assert loop.knowledge_base is not None
        assert loop.detector is not None
