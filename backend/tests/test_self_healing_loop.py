"""Unit tests for L6.2 SelfHealingLoop."""

from __future__ import annotations

import asyncio

import pytest

from app.services.self_healing_loop import (
    HealingResult,
    RecoveryPlan,
    SelfHealingLoop,
)

# ── RecoveryPlan ──────────────────────────────────────────────────────


class TestRecoveryPlan:
    def test_to_dict(self):
        p = RecoveryPlan(
            name="fix_pip",
            description="Install via pip",
            error_pattern="ModuleNotFoundError",
            recovery_commands=["pip install foo"],
            category="missing_dependency",
        )
        d = p.to_dict()
        assert d["name"] == "fix_pip"
        assert d["recovery_commands"] == ["pip install foo"]
        assert d["category"] == "missing_dependency"

    def test_frozen(self):
        p = RecoveryPlan(name="x", description="", error_pattern="")
        with pytest.raises(AttributeError):
            p.name = "y"  # type: ignore[misc]


# ── HealingResult ────────────────────────────────────────────────────


class TestHealingResult:
    def test_to_dict(self):
        r = HealingResult(healed=True, plan_used="fix_pip", attempts=1)
        d = r.to_dict()
        assert d["healed"] is True
        assert d["plan_used"] == "fix_pip"
        assert d["attempts"] == 1

    def test_frozen(self):
        r = HealingResult(healed=False)
        with pytest.raises(AttributeError):
            r.healed = True  # type: ignore[misc]


# ── match_plan ────────────────────────────────────────────────────────


class TestMatchPlan:
    def test_matches_module_not_found(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("ModuleNotFoundError: No module named 'pandas'")
        assert plan is not None
        assert plan.name == "pip_missing_module"

    def test_matches_npm_not_found(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("Cannot find module 'express'")
        assert plan is not None
        assert plan.name == "npm_missing_package"

    def test_matches_command_not_found(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("pandoc: command not found")
        assert plan is not None
        assert plan.name == "command_not_found"

    def test_matches_permission_denied(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("Permission denied: /etc/shadow")
        assert plan is not None
        assert plan.name == "permission_denied"

    def test_matches_path_not_found(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("No such file or directory: /missing/path")
        assert plan is not None
        assert plan.name == "path_not_found"

    def test_matches_port_in_use(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("Error: address already in use :8080")
        assert plan is not None
        assert plan.name == "port_in_use"

    def test_matches_disk_full(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("ENOSPC: no space left on device")
        assert plan is not None
        assert plan.name == "disk_full"

    def test_no_match(self):
        healer = SelfHealingLoop()
        plan = healer.match_plan("some totally unknown error xyz123")
        assert plan is None

    def test_custom_plan_matches(self):
        custom = RecoveryPlan(
            name="fix_custom",
            description="Fix custom error",
            error_pattern="CUSTOM_ERROR_42",
            category="custom",
        )
        healer = SelfHealingLoop(plans=[custom])
        plan = healer.match_plan("CUSTOM_ERROR_42 occurred")
        assert plan is not None
        assert plan.name == "fix_custom"


# ── heal_and_retry ───────────────────────────────────────────────────


class TestHealAndRetry:
    def test_successful_healing(self):
        plan = RecoveryPlan(
            name="install_tool",
            description="Install missing tool",
            error_pattern="command not found",
            recovery_commands=["pip install mytool"],
            category="missing_dependency",
        )
        healer = SelfHealingLoop(plans=[plan])

        async def fake_run(cmd: str) -> str:
            if "pip install" in cmd:
                return "installed"
            return "mytool 1.0"

        result = asyncio.run(
            healer.heal_and_retry(
                tool="run_command",
                args={"command": "mytool --version"},
                error_text="mytool: command not found",
                run_command=fake_run,
            )
        )
        assert result.healed
        assert result.plan_used == "install_tool"
        assert result.attempts == 1

    def test_no_matching_plan(self):
        healer = SelfHealingLoop(plans=[])

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(
            healer.heal_and_retry(
                tool="x",
                args={"command": "x"},
                error_text="weird unknown error",
                run_command=fake_run,
            )
        )
        assert not result.healed
        assert "No recovery plan" in result.error

    def test_recovery_executed_but_retry_fails(self):
        plan = RecoveryPlan(
            name="fix_perm",
            description="Fix permissions",
            error_pattern="Permission denied",
            recovery_commands=["chmod 755 /tmp/x"],
            category="permission",
        )
        healer = SelfHealingLoop(plans=[plan])

        async def fake_run(cmd: str) -> str:
            if "chmod" in cmd:
                return "ok"
            # Retry still has "error" in output
            return "error: still denied"

        result = asyncio.run(
            healer.heal_and_retry(
                tool="run_command",
                args={"command": "cat /tmp/x"},
                error_text="Permission denied: /tmp/x",
                run_command=fake_run,
            )
        )
        assert not result.healed
        assert result.plan_used == "fix_perm"

    def test_no_command_to_retry(self):
        plan = RecoveryPlan(
            name="fix",
            description="Fix",
            error_pattern="broken",
            recovery_commands=["fix-it"],
            category="environment",
        )
        healer = SelfHealingLoop(plans=[plan])

        async def fake_run(cmd: str) -> str:
            return "ok"

        result = asyncio.run(
            healer.heal_and_retry(
                tool="x",
                args={},
                error_text="broken state",
                run_command=fake_run,
            )
        )
        assert not result.healed
        assert "No command to retry" in result.error

    def test_retry_exception_caught(self):
        plan = RecoveryPlan(
            name="fix",
            description="Fix",
            error_pattern="broken",
            recovery_commands=["pip install fix-pkg"],
            category="environment",
        )
        healer = SelfHealingLoop(plans=[plan])

        call_count = 0

        async def fake_run(cmd: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "recovery ok"
            raise RuntimeError("still broken")

        result = asyncio.run(
            healer.heal_and_retry(
                tool="x",
                args={"command": "do-thing"},
                error_text="broken state",
                run_command=fake_run,
            )
        )
        assert not result.healed
        assert "still broken" in result.error

    def test_recovery_command_failure_continues(self):
        """Recovery command exception doesn't abort the whole flow."""
        plan = RecoveryPlan(
            name="multi_fix",
            description="Multiple steps",
            error_pattern="broken",
            recovery_commands=["pip install step1", "npm install step2"],
            category="environment",
        )
        healer = SelfHealingLoop(plans=[plan])

        async def fake_run(cmd: str) -> str:
            if cmd == "pip install step1":
                raise RuntimeError("step1 failed")
            return "all good"

        result = asyncio.run(
            healer.heal_and_retry(
                tool="x",
                args={"command": "check"},
                error_text="broken state",
                run_command=fake_run,
            )
        )
        # step1 fails but step2 + retry succeed
        assert result.healed
        assert "[error]" in result.recovery_output


# ── plan management ──────────────────────────────────────────────────


class TestPlanManagement:
    def test_add_plan(self):
        healer = SelfHealingLoop(plans=[])
        assert len(healer.list_plans()) == 0

        healer.add_plan(
            RecoveryPlan(
                name="new",
                description="New plan",
                error_pattern="NEW_ERR",
            )
        )
        plans = healer.list_plans()
        assert len(plans) == 1
        assert plans[0]["name"] == "new"

    def test_default_plans_loaded(self):
        healer = SelfHealingLoop()
        plans = healer.list_plans()
        assert len(plans) == 7
        names = {p["name"] for p in plans}
        assert "pip_missing_module" in names
        assert "command_not_found" in names
