"""L4.2  ProvisioningPolicy — governance rules for tool provisioning.

Controls *how* the agent is allowed to install tools:
  - ``mode``: auto / ask_user / deny
  - ``allowed_scopes``: where installations may land (venv, node_modules, user)
  - ``size_limit_mb``: per-install disk budget
  - ``blocked_packages``: refuse-list (known malware, unsafe packages)

Usage::

    policy = ProvisioningPolicy()                   # sensible defaults
    policy = ProvisioningPolicy(mode="deny")        # lock-down
    policy.is_package_allowed("evil-pkg")           # → False
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Default blocked packages ──────────────────────────────────────────

_DEFAULT_BLOCKED: frozenset[str] = frozenset(
    {
        # Python — known malicious / typo-squat
        "colourama",
        "python-binance",
        "openai-whisperx",
        # npm — known malicious
        "event-stream",
        "flatmap-stream",
        "ua-parser-js",
        # Generic patterns that should never be installed blindly
        "rm-rf",
        "ransomware",
    }
)


@dataclass(frozen=True)
class ProvisioningPolicy:
    """Frozen governance config for tool provisioning.

    Attributes:
        mode: ``"auto"`` — install without asking (sandboxed).
              ``"ask_user"`` — prompt the user before installing.
              ``"deny"`` — never install, only report what is missing.
        allowed_scopes: Installation scopes the agent may use.
        size_limit_mb: Maximum disk usage per single install, in MB.
        blocked_packages: Package names that must be refused.
        allow_sudo: Whether ``sudo`` / admin-elevation is permitted.
    """

    mode: str = "ask_user"
    allowed_scopes: frozenset[str] = frozenset({"venv", "node_modules", "user"})
    size_limit_mb: int = 500
    blocked_packages: frozenset[str] = field(default_factory=lambda: _DEFAULT_BLOCKED)
    allow_sudo: bool = False

    # ── query helpers ─────────────────────────────────────────────────

    def is_package_allowed(self, package: str) -> bool:
        """Return ``False`` if *package* is on the blocked list."""
        return package.strip().lower() not in {b.lower() for b in self.blocked_packages}

    def is_scope_allowed(self, scope: str) -> bool:
        """Return ``True`` if *scope* is in ``allowed_scopes``."""
        return scope in self.allowed_scopes

    @property
    def auto_install(self) -> bool:
        """Convenience: ``True`` when mode is ``auto``."""
        return self.mode == "auto"

    @property
    def deny_all(self) -> bool:
        """Convenience: ``True`` when mode is ``deny``."""
        return self.mode == "deny"

    # ── serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allowed_scopes": sorted(self.allowed_scopes),
            "size_limit_mb": self.size_limit_mb,
            "blocked_packages": sorted(self.blocked_packages),
            "allow_sudo": self.allow_sudo,
        }
