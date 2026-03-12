"""L4.5  EnvironmentSnapshot — capture pre-install state and rollback.

Captures the list of currently installed packages *before* a provisioning
action so the system can revert to the previous state on failure.

Usage::

    snap = await EnvironmentSnapshot.capture(
        scope="pip",
        run_command=my_run_fn,
    )
    # … attempt install …
    if failed:
        await snap.rollback(run_command=my_run_fn)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

RunCommandFn = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class EnvironmentSnapshot:
    """Frozen snapshot of installed packages for one scope.

    Attributes:
        scope: ``"pip"`` or ``"npm"``.
        packages: Mapping of ``{name: version}`` captured at snapshot time.
        timestamp: Epoch seconds when the snapshot was taken.
    """

    scope: str
    packages: dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0

    # ── capture ───────────────────────────────────────────────────────

    @staticmethod
    async def capture(*, scope: str, run_command: RunCommandFn) -> EnvironmentSnapshot:
        """Create a snapshot by querying the package manager."""
        if scope == "pip":
            raw = await run_command("pip freeze 2>&1")
            packages = _parse_pip_freeze(raw or "")
        elif scope == "npm":
            raw = await run_command("npm list --depth=0 --json 2>&1")
            packages = _parse_npm_list(raw or "")
        else:
            logger.warning("snapshot: unsupported scope '%s', empty snapshot", scope)
            packages = {}

        return EnvironmentSnapshot(
            scope=scope,
            packages=packages,
            timestamp=time.time(),
        )

    # ── rollback ──────────────────────────────────────────────────────

    async def rollback(
        self,
        *,
        run_command: RunCommandFn,
        current_packages: dict[str, str] | None = None,
    ) -> list[str]:
        """Uninstall packages added since the snapshot was taken.

        Returns the list of packages that were removed.
        """
        if current_packages is None:
            current_snap = await EnvironmentSnapshot.capture(
                scope=self.scope,
                run_command=run_command,
            )
            current_packages = current_snap.packages

        added = set(current_packages.keys()) - set(self.packages.keys())
        if not added:
            logger.info("rollback: nothing to remove for scope '%s'", self.scope)
            return []

        removed: list[str] = []
        for pkg in sorted(added):
            try:
                cmd = _uninstall_command(self.scope, pkg)
                await run_command(cmd)
                removed.append(pkg)
                logger.info("rollback: removed '%s' (%s)", pkg, self.scope)
            except Exception:
                logger.warning("rollback: failed to remove '%s'", pkg, exc_info=True)

        return removed

    # ── serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "packages": self.packages,
            "timestamp": self.timestamp,
            "package_count": len(self.packages),
        }


# ── helpers ───────────────────────────────────────────────────────────


def _parse_pip_freeze(raw: str) -> dict[str, str]:
    """Parse ``pip freeze`` output into ``{name: version}``."""
    packages: dict[str, str] = {}
    for raw_line in raw.strip().splitlines():
        line = raw_line.strip()
        if "==" in line:
            parts = line.split("==", 1)
            packages[parts[0].strip().lower()] = parts[1].strip()
    return packages


def _parse_npm_list(raw: str) -> dict[str, str]:
    """Parse ``npm list --json`` output into ``{name: version}``."""
    import json as _json

    try:
        data = _json.loads(raw)
    except (ValueError, TypeError):
        return {}
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        return {}
    packages: dict[str, str] = {}
    for name, info in deps.items():
        version = info.get("version", "") if isinstance(info, dict) else ""
        packages[name.lower()] = str(version)
    return packages


def _uninstall_command(scope: str, package: str) -> str:
    """Build the uninstall command for *scope*."""
    if scope == "pip":
        return f"pip uninstall -y {package}"
    if scope == "npm":
        return f"npm uninstall {package}"
    return f"echo 'unsupported scope {scope}'"
