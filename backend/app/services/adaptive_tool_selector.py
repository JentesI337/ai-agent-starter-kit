"""L5.1  AdaptiveToolSelector — weighted scoring for tool selection.

Ranks alternative tools for the same capability using a multi-factor
scoring formula:

    score = (success_rate × 0.40)
          + (speed_score  × 0.20)
          + (platform_fit × 0.15)
          + (user_pref    × 0.15)
          + (recency      × 0.10)

Data sources:
  - ``ToolTelemetry``  → success_rate, speed_score
  - ``PlatformInfo``   → platform_fit
  - Caller-supplied    → user_preference, recency

Usage::

    selector = AdaptiveToolSelector(telemetry=my_telemetry)
    ranked = selector.rank(
        candidates=["jq", "python -m json.tool", "node -e"],
        platform="windows",
    )
    best = ranked[0]  # highest score
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Weights ───────────────────────────────────────────────────────────

_W_SUCCESS  = 0.40
_W_SPEED    = 0.20
_W_PLATFORM = 0.15
_W_USER     = 0.15
_W_RECENCY  = 0.10


@dataclass(frozen=True)
class ToolScore:
    """Scored candidate produced by ``AdaptiveToolSelector.rank()``."""

    tool: str
    score: float
    success_rate: float = 0.0
    speed_score: float = 0.0
    platform_fit: float = 0.0
    user_preference: float = 0.0
    recency: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "score": round(self.score, 4),
            "success_rate": round(self.success_rate, 4),
            "speed_score": round(self.speed_score, 4),
            "platform_fit": round(self.platform_fit, 4),
            "user_preference": round(self.user_preference, 4),
            "recency": round(self.recency, 4),
        }


# ── Platform affinity lookup ─────────────────────────────────────────

_PLATFORM_AFFINITY: dict[str, set[str]] = {
    "windows": {"powershell", "cmd", "choco", "winget", "wsl", "node", "python", "npx"},
    "linux":   {"bash", "sh", "apt", "yum", "dnf", "snap", "brew", "node", "python", "npx"},
    "darwin":  {"bash", "sh", "brew", "node", "python", "npx"},
}


def _platform_fit(tool: str, platform: str) -> float:
    """Return 1.0 if tool is known-good on platform, 0.5 otherwise."""
    affinity = _PLATFORM_AFFINITY.get(platform.lower(), set())
    tool_base = tool.split()[0].lower().split("/")[-1]
    return 1.0 if tool_base in affinity else 0.5


class AdaptiveToolSelector:
    """Weighted multi-factor tool selector.

    Usage::

        sel = AdaptiveToolSelector()
        sel.record_outcome("jq", success=True, duration_ms=12.0)
        sel.record_outcome("jq", success=True, duration_ms=8.0)
        ranked = sel.rank(["jq", "python -m json.tool"], platform="linux")
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: dict[str, _ToolHistory] = {}

    # ── record outcomes ───────────────────────────────────────────────

    def record_outcome(
        self,
        tool: str,
        *,
        success: bool,
        duration_ms: float = 0.0,
    ) -> None:
        """Feed an execution outcome for future scoring."""
        with self._lock:
            if tool not in self._history:
                self._history[tool] = _ToolHistory()
            h = self._history[tool]
            h.total += 1
            if success:
                h.successes += 1
            h.total_ms += duration_ms
            h.last_call_seq += 1
            h.last_seq = h.last_call_seq

    # ── ranking ───────────────────────────────────────────────────────

    def rank(
        self,
        candidates: list[str],
        *,
        platform: str = "",
        user_preferences: dict[str, float] | None = None,
    ) -> list[ToolScore]:
        """Score and rank *candidates* descending by composite score.

        Args:
            candidates: List of tool names / commands to rank.
            platform: OS name for platform-fit factor.
            user_preferences: Optional ``{tool: 0.0–1.0}`` overrides.
        """
        prefs = user_preferences or {}
        scores: list[ToolScore] = []

        with self._lock:
            max_seq = max(
                (h.last_seq for h in self._history.values()), default=1
            ) or 1

            for tool in candidates:
                h = self._history.get(tool)
                sr = h.success_rate if h else 0.5   # neutral default
                sp = h.speed_score if h else 0.5
                pf = _platform_fit(tool, platform) if platform else 0.5
                up = prefs.get(tool, 0.5)
                rc = (h.last_seq / max_seq) if h else 0.0

                composite = (
                    sr * _W_SUCCESS
                    + sp * _W_SPEED
                    + pf * _W_PLATFORM
                    + up * _W_USER
                    + rc * _W_RECENCY
                )

                scores.append(
                    ToolScore(
                        tool=tool,
                        score=composite,
                        success_rate=sr,
                        speed_score=sp,
                        platform_fit=pf,
                        user_preference=up,
                        recency=rc,
                    )
                )

        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    # ── queries ───────────────────────────────────────────────────────

    def known_tools(self) -> list[str]:
        """Return tool names that have recorded history."""
        with self._lock:
            return sorted(self._history.keys())

    def get_history(self, tool: str) -> dict[str, Any] | None:
        """Return raw history for a single tool."""
        with self._lock:
            h = self._history.get(tool)
            return h.to_dict() if h else None

    def reset(self) -> None:
        with self._lock:
            self._history.clear()


@dataclass
class _ToolHistory:
    """Mutable accumulator for one tool's outcomes."""

    total: int = 0
    successes: int = 0
    total_ms: float = 0.0
    last_seq: int = 0
    last_call_seq: int = 0  # class-level counter tracked in parent

    @property
    def success_rate(self) -> float:
        return self.successes / self.total if self.total else 0.0

    @property
    def speed_score(self) -> float:
        """Normalised speed: faster → higher score (0.0–1.0).

        Uses a simple heuristic: avg < 100ms → 1.0, avg > 5000ms → 0.0.
        """
        if self.total == 0:
            return 0.5
        avg = self.total_ms / self.total
        if avg <= 100:
            return 1.0
        if avg >= 5000:
            return 0.0
        return 1.0 - (avg - 100) / 4900

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "successes": self.successes,
            "success_rate": round(self.success_rate, 4),
            "speed_score": round(self.speed_score, 4),
            "avg_ms": round(self.total_ms / self.total, 2) if self.total else 0.0,
        }
