"""Tests for ToolLoopDetector (Sprint R4)."""
from app.services.tool_loop_detector import LoopDetectionConfig, LoopDetectionState, ToolLoopDetector
import pytest


@pytest.fixture()
def detector():
    return ToolLoopDetector(LoopDetectionConfig())


class TestGenericRepeat:
    def test_no_repeat(self, detector):
        state = LoopDetectionState()
        assert detector.check(state, "read_file", "fp1") is None
        assert detector.check(state, "write_file", "fp2") is None

    def test_repeat_detected(self, detector):
        state = LoopDetectionState()
        detector.check(state, "read_file", "fp1")
        detector.check(state, "read_file", "fp1")
        result = detector.check(state, "read_file", "fp1")
        assert result is not None
        assert "generic_repeat" in result


class TestPingPong:
    def test_ping_pong_detected(self, detector):
        state = LoopDetectionState()
        detector.check(state, "read_file", "fp1")
        detector.check(state, "write_file", "fp2")
        detector.check(state, "read_file", "fp1")
        result = detector.check(state, "write_file", "fp2")
        assert result is not None
        assert "ping_pong" in result


class TestCircuitBreaker:
    def test_circuit_breaks_after_threshold(self, detector):
        state = LoopDetectionState()
        for i in range(20):
            detector.check(state, "read_file", "fp1")
        assert state.circuit_broken
