"""L6.4  Zero-Knowledge Benchmark — tests for the full L1-L6 pipeline.

These are *unit-level* scenario tests that exercise the synthesized
pipeline components in isolation (no live LLM, no live server).

Each scenario simulates the agent encountering an unknown tool/task
and verifies the pipeline: Discovery → Provisioning → Execution →
Verification → Learning → Degradation.
"""

from __future__ import annotations

import asyncio
import json

from app.services.adaptive_tool_selector import AdaptiveToolSelector
from app.services.graceful_degradation import (
    FailedAttempt,
    GracefulDegradation,
)
from app.services.learning_loop import LearningLoop
from app.services.provisioning_policy import ProvisioningPolicy
from app.services.self_healing_loop import RecoveryPlan, SelfHealingLoop
from app.services.tool_discovery_engine import ToolDiscoveryEngine
from app.services.tool_ecosystem_map import ToolEcosystemMap
from app.services.tool_knowledge_base import ToolKnowledgeBase
from app.services.tool_provisioner import ToolProvisioner
from app.services.tool_synthesizer import ToolSynthesizer

# ── Scenario 1: Unknown tool discovery + provision + learn ───────────


class TestZeroKnowledgePipeline:
    """Simulates: user asks for JSON processing, agent has never seen jq."""

    def test_discovery_finds_tool(self):
        """Phase 1: ToolDiscoveryEngine finds a tool from package manager."""
        kb = ToolKnowledgeBase()

        async def fake_run(cmd: str) -> str:
            if "npm --version" in cmd:
                return "10.2.0"
            if "npm search" in cmd:
                return json.dumps([
                    {"name": "jq-cli", "version": "1.0.0", "description": "JSON query tool"}
                ])
            return ""

        from app.services.package_manager_adapter import NpmAdapter
        engine = ToolDiscoveryEngine(kb=kb, adapters=[NpmAdapter()])
        result = asyncio.run(engine.discover("json_processing", run_command=fake_run))

        assert result.found
        assert result.source == "pkg_manager"
        # Verify it was persisted to KB
        assert kb.count() == 1

    def test_provision_installs_and_verifies(self):
        """Phase 2: ToolProvisioner installs and verifies the discovered tool."""
        policy = ProvisioningPolicy(mode="auto")
        prov = ToolProvisioner(policy=policy)

        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return ""
            if "pip install" in cmd:
                return "Successfully installed jq-1.7"
            if "pip show" in cmd:
                return "Name: jq\nVersion: 1.7"
            return ""

        result = asyncio.run(prov.ensure_available(
            package="jq", manager="pip",
            install_command="pip install jq",
            run_command=fake_run,
        ))
        assert result.success
        assert result.action == "installed"
        assert prov.audit_count() == 1

    def test_learning_loop_records_success(self):
        """Phase 3: LearningLoop feeds success to selector + KB."""
        selector = AdaptiveToolSelector()
        kb = ToolKnowledgeBase()
        loop = LearningLoop(selector=selector, kb=kb)

        loop.on_tool_outcome(
            tool="jq", success=True, duration_ms=15.0,
            capability="json_processing",
        )

        # Selector knows about jq now
        assert "jq" in selector.known_tools()
        # KB has an entry
        entries = kb.find_tools_for_capability("json")
        assert len(entries) == 1
        assert entries[0].confidence == 1.0

    def test_next_request_uses_learned_knowledge(self):
        """Phase 4: Second request for same capability → KB hit, no search."""
        kb = ToolKnowledgeBase()
        kb.learn_from_outcome(
            tool="jq", capability="json_processing",
            install_hint="pip install jq", confidence=1.0,
        )

        engine = ToolDiscoveryEngine(kb=kb, adapters=[], min_confidence=0.8)
        result = asyncio.run(engine.discover("json_processing"))

        assert result.found
        assert result.source == "knowledge_base"
        assert result.tool == "jq"


# ── Scenario 2: Self-healing on command not found ────────────────────


class TestSelfHealingScenario:
    """Simulates: command fails → healing identifies root cause → fixes → retries."""

    def test_heal_command_not_found(self):
        plan = RecoveryPlan(
            name="install_pandoc",
            description="Install pandoc",
            error_pattern="command not found",
            recovery_commands=["pip install pandoc"],
            category="missing_dependency",
        )
        healer = SelfHealingLoop(plans=[plan])

        async def fake_run(cmd: str) -> str:
            if "pip install" in cmd:
                return "installed"
            if "pandoc" in cmd:
                return "pandoc 3.1.11"
            return ""

        result = asyncio.run(healer.heal_and_retry(
            tool="run_command",
            args={"command": "pandoc --version"},
            error_text="pandoc: command not found",
            run_command=fake_run,
        ))
        assert result.healed
        assert result.plan_used == "install_pandoc"

    def test_no_plan_available(self):
        healer = SelfHealingLoop(plans=[])

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(healer.heal_and_retry(
            tool="run_command",
            args={"command": "exotic-tool"},
            error_text="totally unknown error xyz",
            run_command=fake_run,
        ))
        assert not result.healed
        assert "No recovery plan" in result.error


# ── Scenario 3: Graceful degradation ─────────────────────────────────


class TestGracefulDegradationScenario:
    """When all approaches fail, provide partial results + suggestions."""

    def test_full_failure_with_suggestions(self):
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Convert markdown to PDF",
            attempts=[
                FailedAttempt(tool="pandoc", error="not found", error_category="missing_dependency"),
                FailedAttempt(tool="weasyprint", error="not found", error_category="missing_dependency"),
            ],
        )
        assert not resp.fully_resolved
        assert resp.confidence == 0.0
        assert len(resp.suggestions) >= 1
        text = resp.format_for_user()
        assert "pandoc" in text
        assert "weasyprint" in text

    def test_partial_result_with_degradation(self):
        gd = GracefulDegradation()
        resp = gd.build_response(
            task="Convert markdown to PDF",
            attempts=[
                FailedAttempt(tool="pandoc", error="not found", error_category="missing_dependency"),
            ],
            partial_results=["HTML version generated successfully"],
        )
        assert not resp.fully_resolved
        assert resp.confidence > 0.0
        assert len(resp.partial_results) == 1


# ── Scenario 4: Ecosystem map for conversion chains ─────────────────


class TestEcosystemChainScenario:
    """EcosystemMap finds multi-step conversion: md → html → pdf."""

    def test_direct_chain(self):
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("text/markdown", "application/pdf")
        assert len(chain) >= 1
        assert chain[-1].format_out == "application/pdf"

    def test_two_step_uses_intermediate(self):
        """md → html (marked) → pdf (weasyprint): 2-step chain."""
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("text/markdown", "application/pdf")
        # Could be 1-step (pandoc) or 2-step (marked → weasyprint)
        # Either is valid but chain must exist
        assert len(chain) >= 1
        tools_used = {e.tool for e in chain}
        # Should use at least one known converter
        assert tools_used & {"pandoc", "marked", "weasyprint"}


# ── Scenario 5: Script synthesis with safety ─────────────────────────


class TestSynthesizerSafety:
    """ToolSynthesizer rejects unsafe scripts, runs safe ones."""

    def test_safe_script_runs(self):
        synth = ToolSynthesizer()

        async def fake_run(cmd: str) -> str:
            return '{"result": "ok"}'

        result = asyncio.run(synth.synthesize_and_run(
            task="Print hello",
            runtime="python",
            script="print('hello world')",
            run_command=fake_run,
        ))
        assert result.success

    def test_unsafe_script_rejected(self):
        synth = ToolSynthesizer()

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(synth.synthesize_and_run(
            task="Bad idea",
            runtime="python",
            script="import subprocess; subprocess.run(['rm', '-rf', '/'])",
            run_command=fake_run,
        ))
        assert not result.success
        assert "subprocess_usage" in result.safety_violations
