"""Unit tests for AdaptiveToolSelector (L5.1)."""

from __future__ import annotations

import pytest

from app.memory.adaptive_selector import AdaptiveToolSelector, ToolScore


@pytest.fixture
def selector():
    return AdaptiveToolSelector()


class TestRecordOutcome:
    def test_record_single(self, selector: AdaptiveToolSelector):
        selector.record_outcome("jq", success=True, duration_ms=10.0)
        assert "jq" in selector.known_tools()

    def test_record_multiple(self, selector: AdaptiveToolSelector):
        selector.record_outcome("jq", success=True, duration_ms=10.0)
        selector.record_outcome("jq", success=False, duration_ms=50.0)
        h = selector.get_history("jq")
        assert h is not None
        assert h["total"] == 2
        assert h["successes"] == 1

    def test_unknown_tool_history_none(self, selector: AdaptiveToolSelector):
        assert selector.get_history("unknown") is None


class TestRank:
    def test_rank_empty(self, selector: AdaptiveToolSelector):
        ranked = selector.rank([])
        assert ranked == []

    def test_rank_unknown_tools_neutral(self, selector: AdaptiveToolSelector):
        ranked = selector.rank(["a", "b"])
        assert len(ranked) == 2
        # Unknown tools get neutral scores, so they should be roughly equal
        assert abs(ranked[0].score - ranked[1].score) < 0.01

    def test_rank_prefers_successful(self, selector: AdaptiveToolSelector):
        for _ in range(10):
            selector.record_outcome("good", success=True, duration_ms=10.0)
        for _ in range(10):
            selector.record_outcome("bad", success=False, duration_ms=10.0)
        ranked = selector.rank(["good", "bad"])
        assert ranked[0].tool == "good"
        assert ranked[0].score > ranked[1].score

    def test_rank_platform_fit(self, selector: AdaptiveToolSelector):
        selector.record_outcome("powershell", success=True, duration_ms=10.0)
        selector.record_outcome("bash", success=True, duration_ms=10.0)
        ranked = selector.rank(["powershell", "bash"], platform="windows")
        # powershell has platform_fit=1.0 on windows vs bash=0.5
        ps = next(s for s in ranked if s.tool == "powershell")
        ba = next(s for s in ranked if s.tool == "bash")
        assert ps.platform_fit > ba.platform_fit

    def test_rank_user_preference(self, selector: AdaptiveToolSelector):
        ranked = selector.rank(
            ["a", "b"],
            user_preferences={"a": 1.0, "b": 0.0},
        )
        assert ranked[0].tool == "a"

    def test_rank_speed_factor(self, selector: AdaptiveToolSelector):
        for _ in range(5):
            selector.record_outcome("fast", success=True, duration_ms=10.0)
        for _ in range(5):
            selector.record_outcome("slow", success=True, duration_ms=4000.0)
        ranked = selector.rank(["fast", "slow"])
        fast = next(s for s in ranked if s.tool == "fast")
        slow = next(s for s in ranked if s.tool == "slow")
        assert fast.speed_score > slow.speed_score


class TestToolScoreToDict:
    def test_to_dict_keys(self):
        ts = ToolScore(tool="x", score=0.75, success_rate=0.9)
        d = ts.to_dict()
        assert set(d.keys()) == {"tool", "score", "success_rate", "speed_score", "platform_fit", "user_preference", "recency"}
        assert d["tool"] == "x"
        assert d["score"] == 0.75


class TestReset:
    def test_reset_clears(self, selector: AdaptiveToolSelector):
        selector.record_outcome("jq", success=True)
        selector.reset()
        assert selector.known_tools() == []
