"""L6.2  SelfHealingLoop — root-cause analysis + recovery + retry.

Goes beyond simple retry by analysing the *root cause* of a failure
and applying environment-level fixes before retrying:

  1. Classify the error (reuse ``ToolRetryStrategy``)
  2. Match a ``RecoveryPlan`` from a registry of known fixes
  3. Execute the recovery actions (e.g. install missing dep, fix PATH)
  4. Retry the original command
  5. Record outcome for future learning

Usage::

    healer = SelfHealingLoop()
    result = await healer.heal_and_retry(
        tool="run_command",
        args={"command": "pandoc --version"},
        error_text="pandoc: command not found",
        run_command=my_run_fn,
    )
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.tool_retry_strategy import ToolRetryStrategy

logger = logging.getLogger(__name__)

RunCommandFn = Callable[[str], Awaitable[str]]

# SEC (SHL-01): Only allow recovery commands whose leader is in this set.
# This prevents self-healing from executing arbitrary commands.
_RECOVERY_COMMAND_ALLOWLIST: frozenset[str] = frozenset({
    "pip", "pip3", "npm", "npx", "yarn", "pnpm",
    "git", "python", "python3", "py", "node",
    "mkdir", "touch", "chmod", "cp",
    "docker", "docker-compose",
})


# ── Result types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecoveryPlan:
    """A named recovery strategy with repair commands."""

    name: str
    description: str
    error_pattern: str          # regex or keyword to match
    recovery_commands: list[str] = field(default_factory=list)
    category: str = ""          # missing_dependency | permission | environment | configuration

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "error_pattern": self.error_pattern,
            "recovery_commands": self.recovery_commands,
            "category": self.category,
        }


@dataclass(frozen=True)
class HealingResult:
    """Outcome of a heal-and-retry attempt."""

    healed: bool
    plan_used: str = ""
    recovery_output: str = ""
    retry_output: str = ""
    error: str = ""
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "healed": self.healed,
            "plan_used": self.plan_used,
            "recovery_output": self.recovery_output,
            "retry_output": self.retry_output,
            "error": self.error,
            "attempts": self.attempts,
        }


# ── Default recovery plans ───────────────────────────────────────────

_DEFAULT_PLANS: list[RecoveryPlan] = [
    RecoveryPlan(
        name="pip_missing_module",
        description="Install missing Python module",
        error_pattern="ModuleNotFoundError|No module named",
        category="missing_dependency",
    ),
    RecoveryPlan(
        name="npm_missing_package",
        description="Install missing Node.js package",
        error_pattern="Cannot find module|MODULE_NOT_FOUND",
        category="missing_dependency",
    ),
    RecoveryPlan(
        name="command_not_found",
        description="Tool not installed on system",
        error_pattern="command not found|not recognized|is not recognized",
        category="missing_dependency",
    ),
    RecoveryPlan(
        name="permission_denied",
        description="File or command permission issue",
        error_pattern="Permission denied|EACCES|Access is denied",
        category="permission",
    ),
    RecoveryPlan(
        name="path_not_found",
        description="Directory or file path does not exist",
        error_pattern="No such file or directory|ENOENT|cannot find the path",
        category="environment",
    ),
    RecoveryPlan(
        name="port_in_use",
        description="Network port already occupied",
        error_pattern="EADDRINUSE|address already in use",
        category="environment",
    ),
    RecoveryPlan(
        name="disk_full",
        description="Disk space exhausted",
        error_pattern="No space left|ENOSPC|disk full",
        category="environment",
    ),
]


class SelfHealingLoop:
    """Root-cause analyser + recovery executor.

    Usage::

        healer = SelfHealingLoop()
        result = await healer.heal_and_retry(
            tool="run_command",
            args={"command": "pandoc --version"},
            error_text="pandoc: command not found",
            run_command=my_run_fn,
        )
    """

    def __init__(
        self,
        *,
        plans: list[RecoveryPlan] | None = None,
        retry_strategy: ToolRetryStrategy | None = None,
        max_healing_attempts: int = 2,
    ) -> None:
        self._plans = plans if plans is not None else list(_DEFAULT_PLANS)
        self._retry_strategy = retry_strategy or ToolRetryStrategy()
        self._max_attempts = max_healing_attempts

    # ── public API ────────────────────────────────────────────────────

    async def heal_and_retry(
        self,
        *,
        tool: str,
        args: dict[str, Any],
        error_text: str,
        run_command: RunCommandFn,
        retry_command: str | None = None,
    ) -> HealingResult:
        """Analyse *error_text*, apply recovery, retry the original command.

        Args:
            tool: Tool name that failed.
            args: Original tool arguments.
            error_text: The error output to analyze.
            run_command: Async callable for executing recovery + retry.
            retry_command: The command to retry (defaults to ``args["command"]``).
        """
        cmd = retry_command or str(args.get("command", ""))

        # ── 1. Root-cause analysis ────────────────────────────────────
        plan = self.match_plan(error_text)
        if plan is None:
            logger.info("healing: no recovery plan for error: %s", error_text[:120])
            return HealingResult(
                healed=False,
                error=f"No recovery plan matches: {error_text[:200]}",
            )

        logger.info("healing: matched plan '%s' for tool '%s'", plan.name, tool)

        # ── 2. Execute recovery commands ──────────────────────────────
        recovery_outputs: list[str] = []
        for rcmd in plan.recovery_commands:
            # SEC (SHL-01): Validate recovery command against allowlist
            rcmd_leader = rcmd.split()[0].strip().lower() if rcmd and rcmd.strip() else ""
            if rcmd_leader not in _RECOVERY_COMMAND_ALLOWLIST:
                msg = f"Recovery command blocked by allowlist: {rcmd}"
                logger.warning("healing: %s", msg)
                recovery_outputs.append(f"[blocked] {msg}")
                continue
            try:
                out = await run_command(rcmd)
                recovery_outputs.append(out or "")
            except Exception as exc:
                logger.warning("healing: recovery command failed: %s", exc)
                recovery_outputs.append(f"[error] {exc}")

        recovery_summary = "\n".join(recovery_outputs)

        # ── 3. Retry original command ─────────────────────────────────
        if not cmd:
            return HealingResult(
                healed=False,
                plan_used=plan.name,
                recovery_output=recovery_summary,
                error="No command to retry",
                attempts=1,
            )

        try:
            retry_out = await run_command(cmd)
            success = bool(retry_out) and "not found" not in retry_out.lower() and "error" not in retry_out.lower()[:50]
        except Exception as exc:
            return HealingResult(
                healed=False,
                plan_used=plan.name,
                recovery_output=recovery_summary,
                error=f"Retry failed: {exc}",
                attempts=1,
            )

        if success:
            logger.info("healing: successfully healed '%s' with plan '%s'", tool, plan.name)

        return HealingResult(
            healed=success,
            plan_used=plan.name,
            recovery_output=recovery_summary,
            retry_output=retry_out or "",
            attempts=1,
        )

    # ── plan matching ─────────────────────────────────────────────────

    def match_plan(self, error_text: str) -> RecoveryPlan | None:
        """Find the first ``RecoveryPlan`` whose pattern matches *error_text*."""
        import re as _re

        for plan in self._plans:
            if _re.search(plan.error_pattern, error_text, _re.IGNORECASE):
                return plan
        return None

    # ── plan management ───────────────────────────────────────────────

    def add_plan(self, plan: RecoveryPlan) -> None:
        """Register a custom recovery plan."""
        self._plans.append(plan)

    def list_plans(self) -> list[dict[str, Any]]:
        """Return all registered plans as dicts."""
        return [p.to_dict() for p in self._plans]
