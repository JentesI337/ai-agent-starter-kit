"""Tests for ToolBudgetManager (Sprint R4)."""

from app.tools.provisioning.budget_manager import BudgetConfig, ToolBudgetManager


class TestBudgetManager:
    def test_initial_state(self):
        mgr = ToolBudgetManager(BudgetConfig(call_cap=5))
        mgr.start()
        assert mgr.calls_remaining == 5
        assert not mgr.is_exhausted

    def test_call_cap(self):
        mgr = ToolBudgetManager(BudgetConfig(call_cap=2))
        mgr.start()
        mgr.record_call()
        mgr.record_call()
        assert mgr.is_exhausted
        assert "call_cap" in (mgr.exhaustion_reason() or "")

    def test_elapsed_time(self):
        mgr = ToolBudgetManager(BudgetConfig(time_cap_seconds=0.01))
        mgr.start()
        import time
        time.sleep(0.02)
        assert mgr.is_exhausted
