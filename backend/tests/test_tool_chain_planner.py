"""Unit tests for ToolChainPlanner (D-10)."""

from __future__ import annotations

import pytest

from app.services.tool_chain_planner import ChainPlan, ChainStep, ToolChainPlanner
from app.services.tool_ecosystem_map import ToolEcosystemMap


@pytest.fixture
def planner():
    return ToolChainPlanner()  # default seeded ecosystem


class TestPlanChain:
    def test_same_format_is_noop(self, planner: ToolChainPlanner):
        plan = planner.plan_chain("text/html", "text/html")
        assert plan.feasible is True
        assert len(plan.steps) == 0
        assert "identical" in plan.reason

    def test_single_step_chain(self, planner: ToolChainPlanner):
        plan = planner.plan_chain("text/markdown", "text/html")
        assert plan.feasible is True
        assert len(plan.steps) >= 1
        assert plan.steps[0].format_in == "text/markdown"
        assert plan.steps[-1].format_out == "text/html"

    def test_multi_step_chain(self, planner: ToolChainPlanner):
        # markdown → html → pdf  (marked + weasyprint/pandoc)
        plan = planner.plan_chain("text/markdown", "application/pdf")
        assert plan.feasible is True
        # Could be 1-step (pandoc) or 2-step (marked→html + weasyprint→pdf)
        assert len(plan.steps) >= 1
        assert plan.steps[0].format_in == "text/markdown"
        assert plan.steps[-1].format_out == "application/pdf"

    def test_infeasible_chain(self, planner: ToolChainPlanner):
        plan = planner.plan_chain("video/mp4", "text/markdown")
        assert plan.feasible is False
        assert "no conversion path" in plan.reason

    def test_install_hint_populated(self, planner: ToolChainPlanner):
        plan = planner.plan_chain("text/markdown", "text/html")
        assert plan.feasible is True
        # At least one step should have an install_hint
        hints = [s.install_hint for s in plan.steps if s.install_hint]
        assert len(hints) >= 1

    def test_total_cost(self, planner: ToolChainPlanner):
        plan = planner.plan_chain("image/png", "image/jpeg")
        assert plan.feasible is True
        assert plan.total_cost == sum(s.cost for s in plan.steps)


class TestSuggestAlternatives:
    def test_returns_at_least_primary(self, planner: ToolChainPlanner):
        alts = planner.suggest_alternatives("text/markdown", "application/pdf")
        assert len(alts) >= 1
        assert alts[0].feasible is True

    def test_returns_primary_for_infeasible(self, planner: ToolChainPlanner):
        alts = planner.suggest_alternatives("video/mp4", "text/markdown")
        assert len(alts) == 1
        assert alts[0].feasible is False


class TestFrozenResults:
    def test_chain_step_frozen(self):
        step = ChainStep(index=0, tool="pandoc", format_in="a", format_out="b", install_hint="", cost=1.0)
        with pytest.raises(AttributeError):
            step.tool = "other"  # type: ignore[misc]

    def test_chain_plan_frozen(self):
        plan = ChainPlan(format_in="a", format_out="b", feasible=True)
        with pytest.raises(AttributeError):
            plan.feasible = False  # type: ignore[misc]

    def test_chain_step_to_dict(self):
        step = ChainStep(index=0, tool="pandoc", format_in="text/markdown", format_out="text/html", install_hint="apt install pandoc", cost=1.0)
        d = step.to_dict()
        assert d["tool"] == "pandoc"
        assert d["format_in"] == "text/markdown"

    def test_chain_plan_to_dict(self, planner: ToolChainPlanner):
        plan = planner.plan_chain("text/markdown", "text/html")
        d = plan.to_dict()
        assert d["feasible"] is True
        assert isinstance(d["steps"], list)


class TestEcosystemAccess:
    def test_ecosystem_property(self, planner: ToolChainPlanner):
        assert isinstance(planner.ecosystem, ToolEcosystemMap)

    def test_custom_ecosystem(self):
        eco = ToolEcosystemMap(seed=False)
        planner = ToolChainPlanner(ecosystem=eco)
        plan = planner.plan_chain("a", "b")
        assert plan.feasible is False
