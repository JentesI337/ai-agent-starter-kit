"""L5.3  ExecutionPatternDetector — detect anti-patterns in tool usage.

Watches the stream of tool calls and flags problematic patterns:
  - **brute_force_install**: repeated install attempts of different versions
  - **version_roulette**: cycling through versions without converging
  - **infinite_retry**: same command retried N+ times identically
  - **sudo_escalation**: attempts to escalate privileges
  - **destructive_sequence**: rm -rf / format / del patterns

Usage::

    detector = ExecutionPatternDetector()
    detector.observe(tool="run_command", args={"command": "pip install foo==1.0"})
    detector.observe(tool="run_command", args={"command": "pip install foo==2.0"})
    detector.observe(tool="run_command", args={"command": "pip install foo==3.0"})
    alerts = detector.check()
    # → [PatternAlert(pattern="version_roulette", ...)]
"""

from __future__ import annotations

import logging
import re
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_MAX_WINDOW = 50


@dataclass(frozen=True)
class PatternAlert:
    """One detected anti-pattern."""

    pattern: str        # brute_force_install | version_roulette | infinite_retry | sudo_escalation | destructive_sequence
    severity: str       # warning | critical
    detail: str
    tool: str = ""
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "severity": self.severity,
            "detail": self.detail,
            "tool": self.tool,
            "count": self.count,
        }


@dataclass
class _Observation:
    """Internal record of one tool call."""

    tool: str
    command: str
    args_hash: str


# ── Patterns ──────────────────────────────────────────────────────────

_INSTALL_RE = re.compile(
    r"(?:pip install|npm install|brew install|choco install|apt install|apt-get install)",
    re.IGNORECASE,
)

_VERSION_RE = re.compile(
    r"==[\d.]+|@[\d.]+|--version[\s=]+[\d.]+",
    re.IGNORECASE,
)

_SUDO_RE = re.compile(r"\bsudo\b", re.IGNORECASE)

_DESTRUCTIVE_RE = re.compile(
    r"\brm\s+-rf\b|\bformat\b|\bdel\s+/[sfq]\b|\bRemove-Item\s.*-Recurse\b",
    re.IGNORECASE,
)


class ExecutionPatternDetector:
    """Sliding-window anti-pattern detector.

    Usage::

        det = ExecutionPatternDetector(window_size=30)
        det.observe(tool="run_command", args={"command": "pip install x"})
        alerts = det.check()
    """

    def __init__(self, *, window_size: int = _MAX_WINDOW) -> None:
        self._lock = threading.Lock()
        self._window: deque[_Observation] = deque(maxlen=window_size)

    # ── observe ───────────────────────────────────────────────────────

    def observe(
        self,
        *,
        tool: str,
        args: dict[str, Any] | None = None,
    ) -> None:
        """Record a tool invocation for pattern analysis."""
        command = ""
        if args:
            command = str(args.get("command", args.get("cmd", "")))
        args_hash = f"{tool}:{command}"
        with self._lock:
            self._window.append(_Observation(tool=tool, command=command, args_hash=args_hash))

    # ── check ─────────────────────────────────────────────────────────

    def check(self) -> list[PatternAlert]:
        """Scan the window and return all active alerts."""
        with self._lock:
            observations = list(self._window)

        alerts: list[PatternAlert] = []
        alerts.extend(self._detect_infinite_retry(observations))
        alerts.extend(self._detect_version_roulette(observations))
        alerts.extend(self._detect_brute_force_install(observations))
        alerts.extend(self._detect_sudo_escalation(observations))
        alerts.extend(self._detect_destructive_sequence(observations))
        return alerts

    def clear(self) -> None:
        """Reset the observation window."""
        with self._lock:
            self._window.clear()

    # ── detectors ─────────────────────────────────────────────────────

    @staticmethod
    def _detect_infinite_retry(obs: list[_Observation]) -> list[PatternAlert]:
        """Same exact command repeated 4+ times."""
        if len(obs) < 4:
            return []
        # Check last N identical commands
        last = obs[-1].args_hash
        count = 0
        for o in reversed(obs):
            if o.args_hash == last:
                count += 1
            else:
                break
        if count >= 4:
            return [
                PatternAlert(
                    pattern="infinite_retry",
                    severity="critical",
                    detail=f"Command repeated {count} times identically",
                    tool=obs[-1].tool,
                    count=count,
                )
            ]
        return []

    @staticmethod
    def _detect_version_roulette(obs: list[_Observation]) -> list[PatternAlert]:
        """Install commands with 3+ different version specifiers for same package."""
        install_cmds = [o for o in obs if _INSTALL_RE.search(o.command)]
        if len(install_cmds) < 3:
            return []

        # Group by base command (strip version)
        base_versions: dict[str, set[str]] = {}
        for o in install_cmds:
            base = _VERSION_RE.sub("", o.command).strip()
            versions = _VERSION_RE.findall(o.command)
            if versions:
                if base not in base_versions:
                    base_versions[base] = set()
                base_versions[base].update(versions)

        alerts: list[PatternAlert] = [
            PatternAlert(
                pattern="version_roulette",
                severity="warning",
                detail=f"Tried {len(versions)} different versions: {', '.join(sorted(versions))}",
                count=len(versions),
            )
            for versions in base_versions.values()
            if len(versions) >= 3
        ]
        return alerts

    @staticmethod
    def _detect_brute_force_install(obs: list[_Observation]) -> list[PatternAlert]:
        """5+ install commands in the window."""
        install_count = sum(1 for o in obs if _INSTALL_RE.search(o.command))
        if install_count >= 5:
            return [
                PatternAlert(
                    pattern="brute_force_install",
                    severity="warning",
                    detail=f"{install_count} install commands in recent window",
                    count=install_count,
                )
            ]
        return []

    @staticmethod
    def _detect_sudo_escalation(obs: list[_Observation]) -> list[PatternAlert]:
        """Any sudo usage."""
        for o in obs:
            if _SUDO_RE.search(o.command):
                return [
                    PatternAlert(
                        pattern="sudo_escalation",
                        severity="critical",
                        detail=f"Sudo detected in command: {o.command[:80]}",
                        tool=o.tool,
                        count=1,
                    )
                ]
        return []

    @staticmethod
    def _detect_destructive_sequence(obs: list[_Observation]) -> list[PatternAlert]:
        """Dangerous deletion / format commands."""
        for o in obs:
            if _DESTRUCTIVE_RE.search(o.command):
                return [
                    PatternAlert(
                        pattern="destructive_sequence",
                        severity="critical",
                        detail=f"Destructive command detected: {o.command[:80]}",
                        tool=o.tool,
                        count=1,
                    )
                ]
        return []
