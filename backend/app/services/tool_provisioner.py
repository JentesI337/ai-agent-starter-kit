"""L4.1 / L4.4 / L4.6  ToolProvisioner — install + verify pipeline with audit.

Orchestrates the full provisioning lifecycle:
  1. Check policy (auto / ask_user / deny)
  2. Capture pre-install ``EnvironmentSnapshot``
  3. Run sandboxed install command (venv, node_modules, --user)
  4. Verify the tool is now available (probe)
  5. On failure → automatic rollback via snapshot
  6. Record every action to the audit log

Usage::

    provisioner = ToolProvisioner(policy=my_policy)
    result = await provisioner.ensure_available(
        package="lodash",
        manager="npm",
        install_command="npm install lodash",
        run_command=my_run_fn,
    )
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services.environment_snapshot import EnvironmentSnapshot
from app.services.provisioning_policy import ProvisioningPolicy

logger = logging.getLogger(__name__)

RunCommandFn = Callable[[str], Awaitable[str]]


# ── Result types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProvisionResult:
    """Outcome of an ``ensure_available`` call."""

    success: bool
    package: str
    manager: str
    action: str = ""        # "installed" | "already_available" | "denied" | "blocked" | "failed" | "rolled_back"
    detail: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "package": self.package,
            "manager": self.manager,
            "action": self.action,
            "detail": self.detail,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass(frozen=True)
class AuditEntry:
    """One entry in the install audit log (L4.6)."""

    timestamp: float
    package: str
    manager: str
    action: str
    install_command: str
    success: bool
    detail: str = ""
    rolled_back: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "package": self.package,
            "manager": self.manager,
            "action": self.action,
            "install_command": self.install_command,
            "success": self.success,
            "detail": self.detail,
            "rolled_back": self.rolled_back,
        }


# ── Sandbox helpers ──────────────────────────────────────────────────

_SCOPE_FOR_MANAGER: dict[str, str] = {
    "pip": "venv",
    "npm": "node_modules",
    "brew": "user",
    "choco": "user",
}


def _sandbox_command(install_command: str, manager: str, *, allow_sudo: bool) -> str:
    """Rewrite *install_command* to enforce sandbox rules (L4.4).

    - pip  → always use ``--user`` if not already in venv
    - npm  → always local (no ``-g``)
    - Strips ``sudo`` unless explicitly allowed
    """
    cmd = install_command

    # Strip sudo unless allowed
    if not allow_sudo:
        cmd = cmd.replace("sudo ", "")

    if manager == "pip":
        # Ensure --user for safety outside venv
        if "--user" not in cmd and "-e" not in cmd:
            cmd = cmd.replace("pip install", "pip install --user", 1)
    elif manager == "npm":
        # Force local (strip -g / --global)
        cmd = cmd.replace(" -g ", " ").replace(" --global ", " ")

    return cmd


# ── Main class ───────────────────────────────────────────────────────


class ToolProvisioner:
    """Install + Verify + Rollback pipeline for tool provisioning.

    Usage::

        prov = ToolProvisioner()
        result = await prov.ensure_available(
            package="jq",
            manager="pip",
            install_command="pip install jq",
            run_command=run_fn,
        )
    """

    def __init__(
        self,
        *,
        policy: ProvisioningPolicy | None = None,
    ) -> None:
        self._policy = policy or ProvisioningPolicy()
        self._lock = threading.Lock()
        self._audit_log: list[AuditEntry] = []

    # ── public API ────────────────────────────────────────────────────

    async def ensure_available(
        self,
        *,
        package: str,
        manager: str,
        install_command: str,
        run_command: RunCommandFn,
        probe_command: str | None = None,
    ) -> ProvisionResult:
        """Full provisioning pipeline for *package*.

        Args:
            package: Package name (e.g. ``"lodash"``).
            manager: Package manager id (``"npm"`` / ``"pip"`` / …).
            install_command: Raw install command from the adapter.
            run_command: Async callable to execute shell commands.
            probe_command: Optional command to verify availability after install.
        """
        start_ns = time.monotonic_ns()

        # ── 1. Policy gate ────────────────────────────────────────────
        if self._policy.deny_all:
            return self._finish(
                package=package, manager=manager, install_command=install_command,
                action="denied", success=False,
                detail="Provisioning policy mode is 'deny'",
                start_ns=start_ns,
            )

        if not self._policy.is_package_allowed(package):
            return self._finish(
                package=package, manager=manager, install_command=install_command,
                action="blocked", success=False,
                detail=f"Package '{package}' is on the blocked list",
                start_ns=start_ns,
            )

        scope = _SCOPE_FOR_MANAGER.get(manager, manager)
        if not self._policy.is_scope_allowed(scope):
            return self._finish(
                package=package, manager=manager, install_command=install_command,
                action="denied", success=False,
                detail=f"Scope '{scope}' is not allowed by policy",
                start_ns=start_ns,
            )

        # ── 1b. Auto vs ask_user gate ────────────────────────────────
        if not self._policy.auto_install:
            # In ask_user mode we return a "needs_approval" result.
            # The caller (ws_handler / agent) is responsible for
            # obtaining user consent before calling again with
            # a policy overridden to auto.
            return self._finish(
                package=package, manager=manager, install_command=install_command,
                action="needs_approval", success=False,
                detail=f"User approval required to install '{package}' via {manager}",
                start_ns=start_ns,
            )

        # ── 2. Snapshot ───────────────────────────────────────────────
        snapshot: EnvironmentSnapshot | None = None
        if scope in ("pip", "npm"):
            try:
                snapshot = await EnvironmentSnapshot.capture(
                    scope=scope, run_command=run_command,
                )
            except Exception:
                logger.warning("provisioner: snapshot capture failed", exc_info=True)

        # ── 3. Sandboxed install ──────────────────────────────────────
        safe_cmd = _sandbox_command(
            install_command, manager, allow_sudo=self._policy.allow_sudo,
        )
        try:
            output = await run_command(safe_cmd)
        except Exception as exc:
            return self._finish(
                package=package, manager=manager, install_command=safe_cmd,
                action="failed", success=False,
                detail=f"Install command raised: {exc}",
                start_ns=start_ns,
            )

        # ── 4. Verify ────────────────────────────────────────────────
        verified = await self._verify(
            package=package, manager=manager,
            probe_command=probe_command, run_command=run_command,
        )

        if verified:
            return self._finish(
                package=package, manager=manager, install_command=safe_cmd,
                action="installed", success=True,
                detail=f"Installed and verified via {manager}",
                start_ns=start_ns,
            )

        # ── 5. Rollback on verify failure ────────────────────────────
        rolled_back = False
        if snapshot is not None:
            try:
                removed = await snapshot.rollback(run_command=run_command)
                rolled_back = len(removed) > 0
                logger.info("provisioner: rolled back %d packages", len(removed))
            except Exception:
                logger.warning("provisioner: rollback failed", exc_info=True)

        return self._finish(
            package=package, manager=manager, install_command=safe_cmd,
            action="rolled_back" if rolled_back else "failed",
            success=False,
            detail="Verification failed after install" + (
                "; rolled back" if rolled_back else ""
            ),
            start_ns=start_ns,
            rolled_back=rolled_back,
        )

    # ── Audit log queries (L4.6) ──────────────────────────────────────

    def get_audit_log(self, *, last_n: int | None = None) -> list[dict[str, Any]]:
        """Return recent audit entries."""
        with self._lock:
            entries = self._audit_log if last_n is None else self._audit_log[-last_n:]
            return [e.to_dict() for e in entries]

    def audit_count(self) -> int:
        with self._lock:
            return len(self._audit_log)

    # ── internals ─────────────────────────────────────────────────────

    async def _verify(
        self,
        *,
        package: str,
        manager: str,
        probe_command: str | None,
        run_command: RunCommandFn,
    ) -> bool:
        """Try to verify the package is now available."""
        cmd = probe_command
        if not cmd:
            # Default probe: ask the manager
            if manager == "pip":
                cmd = f"pip show {package}"
            elif manager == "npm":
                cmd = f"npm list {package} --depth=0"
            else:
                cmd = f"{package} --version"

        try:
            out = await run_command(cmd)
            if out and "not found" not in out.lower() and "ERR" not in out:
                return True
        except Exception:
            pass
        return False

    def _finish(
        self,
        *,
        package: str,
        manager: str,
        install_command: str,
        action: str,
        success: bool,
        detail: str,
        start_ns: int,
        rolled_back: bool = False,
    ) -> ProvisionResult:
        """Build result, record audit entry, return."""
        elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000

        entry = AuditEntry(
            timestamp=time.time(),
            package=package,
            manager=manager,
            action=action,
            install_command=install_command,
            success=success,
            detail=detail,
            rolled_back=rolled_back,
        )
        with self._lock:
            self._audit_log.append(entry)

        logger.info(
            "provisioner: %s %s via %s — %s (%.1fms)",
            action, package, manager, detail, elapsed_ms,
        )

        return ProvisionResult(
            success=success,
            package=package,
            manager=manager,
            action=action,
            detail=detail,
            elapsed_ms=elapsed_ms,
        )
