"""Unit tests for ExecutionPatternDetector (L5.3)."""

from __future__ import annotations

import pytest

from app.quality.execution_pattern_detector import ExecutionPatternDetector, PatternAlert


@pytest.fixture
def detector():
    return ExecutionPatternDetector()


class TestInfiniteRetry:
    def test_no_alert_below_threshold(self, detector: ExecutionPatternDetector):
        for _ in range(3):
            detector.observe(tool="run_command", args={"command": "ls"})
        assert not any(a.pattern == "infinite_retry" for a in detector.check())

    def test_alert_at_threshold(self, detector: ExecutionPatternDetector):
        for _ in range(4):
            detector.observe(tool="run_command", args={"command": "ls"})
        alerts = detector.check()
        retry_alerts = [a for a in alerts if a.pattern == "infinite_retry"]
        assert len(retry_alerts) == 1
        assert retry_alerts[0].count >= 4

    def test_different_commands_no_alert(self, detector: ExecutionPatternDetector):
        for i in range(10):
            detector.observe(tool="run_command", args={"command": f"cmd_{i}"})
        assert not any(a.pattern == "infinite_retry" for a in detector.check())


class TestVersionRoulette:
    def test_roulette_detected(self, detector: ExecutionPatternDetector):
        detector.observe(tool="run_command", args={"command": "pip install foo==1.0"})
        detector.observe(tool="run_command", args={"command": "pip install foo==2.0"})
        detector.observe(tool="run_command", args={"command": "pip install foo==3.0"})
        alerts = [a for a in detector.check() if a.pattern == "version_roulette"]
        assert len(alerts) == 1

    def test_no_roulette_same_version(self, detector: ExecutionPatternDetector):
        for _ in range(3):
            detector.observe(tool="run_command", args={"command": "pip install foo==1.0"})
        alerts = [a for a in detector.check() if a.pattern == "version_roulette"]
        assert len(alerts) == 0


class TestBruteForceInstall:
    def test_brute_force_detected(self, detector: ExecutionPatternDetector):
        for i in range(5):
            detector.observe(tool="run_command", args={"command": f"pip install pkg{i}"})
        alerts = [a for a in detector.check() if a.pattern == "brute_force_install"]
        assert len(alerts) == 1
        assert alerts[0].count == 5

    def test_below_threshold_no_alert(self, detector: ExecutionPatternDetector):
        for i in range(4):
            detector.observe(tool="run_command", args={"command": f"pip install pkg{i}"})
        alerts = [a for a in detector.check() if a.pattern == "brute_force_install"]
        assert len(alerts) == 0


class TestSudoEscalation:
    def test_sudo_detected(self, detector: ExecutionPatternDetector):
        detector.observe(tool="run_command", args={"command": "sudo rm -rf /"})
        alerts = [a for a in detector.check() if a.pattern == "sudo_escalation"]
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"

    def test_no_sudo_clean(self, detector: ExecutionPatternDetector):
        detector.observe(tool="run_command", args={"command": "ls -la"})
        alerts = [a for a in detector.check() if a.pattern == "sudo_escalation"]
        assert len(alerts) == 0


class TestDestructiveSequence:
    def test_rm_rf_detected(self, detector: ExecutionPatternDetector):
        detector.observe(tool="run_command", args={"command": "rm -rf /tmp/stuff"})
        alerts = [a for a in detector.check() if a.pattern == "destructive_sequence"]
        assert len(alerts) == 1

    def test_safe_rm_no_alert(self, detector: ExecutionPatternDetector):
        detector.observe(tool="run_command", args={"command": "rm file.txt"})
        alerts = [a for a in detector.check() if a.pattern == "destructive_sequence"]
        assert len(alerts) == 0


class TestClear:
    def test_clear_resets(self, detector: ExecutionPatternDetector):
        for _ in range(5):
            detector.observe(tool="run_command", args={"command": "sudo pip install x"})
        detector.clear()
        assert detector.check() == []


class TestPatternAlertToDict:
    def test_to_dict(self):
        a = PatternAlert(pattern="sudo_escalation", severity="critical", detail="bad", tool="run_command", count=1)
        d = a.to_dict()
        assert d["pattern"] == "sudo_escalation"
        assert d["severity"] == "critical"
