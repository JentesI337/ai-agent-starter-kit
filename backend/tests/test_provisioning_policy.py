"""Unit tests for ProvisioningPolicy (L4.2)."""

from __future__ import annotations

import pytest

from app.services.provisioning_policy import ProvisioningPolicy, _DEFAULT_BLOCKED


@pytest.fixture
def policy():
    return ProvisioningPolicy()


class TestDefaults:
    def test_default_mode(self, policy: ProvisioningPolicy):
        assert policy.mode == "ask_user"

    def test_default_scopes(self, policy: ProvisioningPolicy):
        assert "venv" in policy.allowed_scopes
        assert "node_modules" in policy.allowed_scopes
        assert "user" in policy.allowed_scopes

    def test_default_size_limit(self, policy: ProvisioningPolicy):
        assert policy.size_limit_mb == 500

    def test_default_no_sudo(self, policy: ProvisioningPolicy):
        assert policy.allow_sudo is False

    def test_default_blocked_nonempty(self, policy: ProvisioningPolicy):
        assert len(policy.blocked_packages) > 0


class TestPackageAllowed:
    def test_normal_package_allowed(self, policy: ProvisioningPolicy):
        assert policy.is_package_allowed("lodash") is True

    def test_blocked_package_denied(self, policy: ProvisioningPolicy):
        assert policy.is_package_allowed("event-stream") is False

    def test_blocked_case_insensitive(self, policy: ProvisioningPolicy):
        assert policy.is_package_allowed("Event-Stream") is False

    def test_blocked_strips_whitespace(self, policy: ProvisioningPolicy):
        assert policy.is_package_allowed("  event-stream  ") is False

    def test_custom_blocked_list(self):
        p = ProvisioningPolicy(blocked_packages=frozenset({"badpkg"}))
        assert p.is_package_allowed("badpkg") is False
        assert p.is_package_allowed("goodpkg") is True

    def test_empty_blocked_allows_all(self):
        p = ProvisioningPolicy(blocked_packages=frozenset())
        assert p.is_package_allowed("anything") is True


class TestScopeAllowed:
    def test_venv_allowed(self, policy: ProvisioningPolicy):
        assert policy.is_scope_allowed("venv") is True

    def test_system_not_allowed(self, policy: ProvisioningPolicy):
        assert policy.is_scope_allowed("system") is False

    def test_custom_scopes(self):
        p = ProvisioningPolicy(allowed_scopes=frozenset({"system"}))
        assert p.is_scope_allowed("system") is True
        assert p.is_scope_allowed("venv") is False


class TestConvenienceProperties:
    def test_auto_install(self):
        p = ProvisioningPolicy(mode="auto")
        assert p.auto_install is True
        assert p.deny_all is False

    def test_deny_all(self):
        p = ProvisioningPolicy(mode="deny")
        assert p.deny_all is True
        assert p.auto_install is False

    def test_ask_user_neither(self, policy: ProvisioningPolicy):
        assert policy.auto_install is False
        assert policy.deny_all is False


class TestToDict:
    def test_to_dict_keys(self, policy: ProvisioningPolicy):
        d = policy.to_dict()
        assert set(d.keys()) == {"mode", "allowed_scopes", "size_limit_mb", "blocked_packages", "allow_sudo"}

    def test_to_dict_scopes_sorted(self, policy: ProvisioningPolicy):
        d = policy.to_dict()
        assert d["allowed_scopes"] == sorted(d["allowed_scopes"])

    def test_to_dict_blocked_sorted(self, policy: ProvisioningPolicy):
        d = policy.to_dict()
        assert d["blocked_packages"] == sorted(d["blocked_packages"])


class TestFrozen:
    def test_immutable(self, policy: ProvisioningPolicy):
        with pytest.raises(AttributeError):
            policy.mode = "auto"  # type: ignore[misc]
