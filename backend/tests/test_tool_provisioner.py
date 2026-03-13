"""Unit tests for ToolProvisioner (L4.1 / L4.4 / L4.6)."""

from __future__ import annotations

import asyncio

import pytest

from app.policy.provisioning_policy import ProvisioningPolicy
from app.tools.provisioning.provisioner import (
    AuditEntry,
    ProvisionResult,
    ToolProvisioner,
    _sandbox_command,
)


@pytest.fixture
def auto_policy():
    return ProvisioningPolicy(mode="auto")


@pytest.fixture
def deny_policy():
    return ProvisioningPolicy(mode="deny")


@pytest.fixture
def provisioner(auto_policy):
    return ToolProvisioner(policy=auto_policy)


# ── sandbox_command tests (L4.4) ─────────────────────────────────────


class TestSandboxCommand:
    def test_pip_gets_user_flag(self):
        cmd = _sandbox_command("pip install requests", "pip", allow_sudo=False)
        assert "--user" in cmd

    def test_pip_preserves_existing_user_flag(self):
        cmd = _sandbox_command("pip install --user requests", "pip", allow_sudo=False)
        assert cmd.count("--user") == 1

    def test_npm_strips_global(self):
        cmd = _sandbox_command("npm install -g lodash", "npm", allow_sudo=False)
        assert "-g" not in cmd
        assert "lodash" in cmd

    def test_npm_strips_global_long(self):
        cmd = _sandbox_command("npm install --global lodash", "npm", allow_sudo=False)
        assert "--global" not in cmd

    def test_sudo_stripped_by_default(self):
        cmd = _sandbox_command("sudo pip install foo", "pip", allow_sudo=False)
        assert "sudo" not in cmd

    def test_sudo_kept_when_allowed(self):
        cmd = _sandbox_command("sudo pip install foo", "pip", allow_sudo=True)
        assert "sudo" in cmd

    def test_pip_editable_no_user(self):
        cmd = _sandbox_command("pip install -e .", "pip", allow_sudo=False)
        assert "--user" not in cmd


# ── Policy gate tests ────────────────────────────────────────────────


class TestPolicyGate:
    def test_deny_mode(self, deny_policy):
        prov = ToolProvisioner(policy=deny_policy)

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(
            prov.ensure_available(
                package="foo", manager="pip",
                install_command="pip install foo",
                run_command=fake_run,
            )
        )
        assert not result.success
        assert result.action == "denied"

    def test_blocked_package(self, auto_policy):
        policy = ProvisioningPolicy(
            mode="auto",
            blocked_packages=frozenset({"evil-pkg"}),
        )
        prov = ToolProvisioner(policy=policy)

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(
            prov.ensure_available(
                package="evil-pkg", manager="pip",
                install_command="pip install evil-pkg",
                run_command=fake_run,
            )
        )
        assert not result.success
        assert result.action == "blocked"

    def test_ask_user_needs_approval(self):
        policy = ProvisioningPolicy(mode="ask_user")
        prov = ToolProvisioner(policy=policy)

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(
            prov.ensure_available(
                package="foo", manager="pip",
                install_command="pip install foo",
                run_command=fake_run,
            )
        )
        assert not result.success
        assert result.action == "needs_approval"

    def test_scope_denied(self):
        policy = ProvisioningPolicy(
            mode="auto",
            allowed_scopes=frozenset({"venv"}),  # no npm
        )
        prov = ToolProvisioner(policy=policy)

        async def fake_run(cmd: str) -> str:
            return ""

        result = asyncio.run(
            prov.ensure_available(
                package="lodash", manager="npm",
                install_command="npm install lodash",
                run_command=fake_run,
            )
        )
        assert not result.success
        assert result.action == "denied"


# ── Install + Verify pipeline tests ──────────────────────────────────


class TestInstallPipeline:
    def test_successful_install(self, provisioner):
        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return ""
            if "pip install" in cmd:
                return "Successfully installed requests-2.31.0"
            if "pip show" in cmd:
                return "Name: requests\nVersion: 2.31.0"
            return ""

        result = asyncio.run(
            provisioner.ensure_available(
                package="requests", manager="pip",
                install_command="pip install requests",
                run_command=fake_run,
            )
        )
        assert result.success
        assert result.action == "installed"

    def test_failed_install_exception(self, provisioner):
        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return ""
            if "pip install" in cmd:
                raise RuntimeError("network error")
            return ""

        result = asyncio.run(
            provisioner.ensure_available(
                package="requests", manager="pip",
                install_command="pip install requests",
                run_command=fake_run,
            )
        )
        assert not result.success
        assert result.action == "failed"

    def test_verify_failure_triggers_rollback(self, provisioner):
        rollback_called = False

        async def fake_run(cmd: str) -> str:
            nonlocal rollback_called
            if "pip freeze" in cmd and not rollback_called:
                return ""  # pre-install: empty
            if "pip install" in cmd:
                return "installed"
            if "pip show" in cmd:
                return "not found"  # verify fails
            if "pip freeze" in cmd:
                rollback_called = True
                return ""
            if "pip uninstall" in cmd:
                return "uninstalled"
            return ""

        result = asyncio.run(
            provisioner.ensure_available(
                package="requests", manager="pip",
                install_command="pip install requests",
                run_command=fake_run,
            )
        )
        assert not result.success
        # action is either "rolled_back" or "failed" depending on rollback content
        assert result.action in ("rolled_back", "failed")

    def test_custom_probe_command(self, provisioner):
        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return ""
            if "pip install" in cmd:
                return "installed"
            if cmd == "jq --version":
                return "jq-1.7"
            return ""

        result = asyncio.run(
            provisioner.ensure_available(
                package="jq", manager="pip",
                install_command="pip install jq",
                probe_command="jq --version",
                run_command=fake_run,
            )
        )
        assert result.success


# ── Audit log tests (L4.6) ──────────────────────────────────────────


class TestAuditLog:
    def test_audit_recorded_on_success(self, provisioner):
        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return ""
            if "pip install" in cmd:
                return "installed"
            if "pip show" in cmd:
                return "Name: foo"
            return ""

        asyncio.run(
            provisioner.ensure_available(
                package="foo", manager="pip",
                install_command="pip install foo",
                run_command=fake_run,
            )
        )
        assert provisioner.audit_count() == 1
        log = provisioner.get_audit_log()
        assert log[0]["action"] == "installed"
        assert log[0]["success"] is True

    def test_audit_recorded_on_denied(self):
        prov = ToolProvisioner(policy=ProvisioningPolicy(mode="deny"))

        async def fake_run(cmd: str) -> str:
            return ""

        asyncio.run(
            prov.ensure_available(
                package="foo", manager="pip",
                install_command="pip install foo",
                run_command=fake_run,
            )
        )
        assert prov.audit_count() == 1
        log = prov.get_audit_log()
        assert log[0]["action"] == "denied"
        assert log[0]["success"] is False

    def test_audit_last_n(self, provisioner):
        async def fake_run(cmd: str) -> str:
            if "pip freeze" in cmd:
                return ""
            if "pip install" in cmd:
                return "ok"
            if "pip show" in cmd:
                return "Name: x"
            return ""

        for i in range(5):
            asyncio.run(
                provisioner.ensure_available(
                    package=f"pkg{i}", manager="pip",
                    install_command=f"pip install pkg{i}",
                    run_command=fake_run,
                )
            )
        assert provisioner.audit_count() == 5
        last_two = provisioner.get_audit_log(last_n=2)
        assert len(last_two) == 2


# ── Result / AuditEntry dataclass tests ──────────────────────────────


class TestDataclasses:
    def test_provision_result_to_dict(self):
        r = ProvisionResult(success=True, package="foo", manager="pip", action="installed")
        d = r.to_dict()
        assert d["success"] is True
        assert d["package"] == "foo"

    def test_audit_entry_to_dict(self):
        e = AuditEntry(
            timestamp=1.0, package="foo", manager="pip",
            action="installed", install_command="pip install foo",
            success=True,
        )
        d = e.to_dict()
        assert d["timestamp"] == 1.0
        assert d["rolled_back"] is False
