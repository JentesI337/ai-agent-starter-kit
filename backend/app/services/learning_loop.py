"""L5.5  LearningLoop — closes the feedback circuit.

After every tool execution the loop:
  1. Records the outcome in ``AdaptiveToolSelector`` (success_rate, speed)
  2. Persists knowledge in ``ToolKnowledgeBase`` (install hints, pitfalls)
  3. Feeds observations into ``ExecutionPatternDetector``

The loop is a stateless coordinator — it does not own any data.
All state lives in the three downstream components.

Usage::

    loop = LearningLoop(
        selector=my_selector,
        kb=my_knowledge_base,
        detector=my_pattern_detector,
    )
    loop.on_tool_outcome(
        tool="jq",
        success=True,
        duration_ms=15.0,
        capability="json_processing",
        args={"command": "jq .name package.json"},
    )
    alerts = loop.check_patterns()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.adaptive_tool_selector import AdaptiveToolSelector
    from app.services.execution_pattern_detector import ExecutionPatternDetector, PatternAlert
    from app.services.tool_knowledge_base import ToolKnowledgeBase

logger = logging.getLogger(__name__)


class LearningLoop:
    """Stateless coordinator that wires outcome data to downstream services.

    Usage::

        loop = LearningLoop()
        loop.on_tool_outcome(tool="jq", success=True, duration_ms=10)
        alerts = loop.check_patterns()
    """

    def __init__(
        self,
        *,
        selector: AdaptiveToolSelector | None = None,
        kb: ToolKnowledgeBase | None = None,
        detector: ExecutionPatternDetector | None = None,
    ) -> None:
        # Lazy imports — avoids hard import chain that would break the
        # entire import graph when one downstream module fails.
        if selector is None:
            from app.services.adaptive_tool_selector import AdaptiveToolSelector
            selector = AdaptiveToolSelector()
        if kb is None:
            from app.services.tool_knowledge_base import ToolKnowledgeBase
            kb = ToolKnowledgeBase()
        if detector is None:
            from app.services.execution_pattern_detector import ExecutionPatternDetector
            detector = ExecutionPatternDetector()

        self._selector = selector
        self._kb = kb
        self._detector = detector

    # ── main entry point ──────────────────────────────────────────────

    def on_tool_outcome(
        self,
        *,
        tool: str,
        success: bool,
        duration_ms: float = 0.0,
        capability: str = "",
        pitfall: str = "",
        args: dict[str, Any] | None = None,
    ) -> None:
        """Record a tool execution outcome across all subsystems."""

        # 1. Selector — feeds success/speed scoring
        self._selector.record_outcome(
            tool, success=success, duration_ms=duration_ms,
        )

        # 2. KnowledgeBase — persist if there's a capability label
        if capability:
            effective_pitfall = pitfall if not success else ""
            if pitfall and success:
                logger.debug(
                    "learning_loop: discarding pitfall for successful tool '%s': %s",
                    tool, pitfall[:100],
                )
            self._kb.learn_from_outcome(
                tool=tool,
                capability=capability,
                install_hint="",
                pitfall=effective_pitfall,
                confidence=1.0 if success else 0.3,
                source="agent",
            )

        # 3. PatternDetector — observe for anti-pattern detection
        self._detector.observe(tool=tool, args=args)

        logger.debug(
            "learning_loop: recorded outcome for '%s' (success=%s, %.1fms)",
            tool, success, duration_ms,
        )

    # ── pattern analysis ──────────────────────────────────────────────

    def check_patterns(self) -> list[PatternAlert]:
        """Delegate pattern check to the detector."""
        return self._detector.check()

    # ── accessors ─────────────────────────────────────────────────────

    @property
    def selector(self) -> AdaptiveToolSelector:
        return self._selector

    @property
    def knowledge_base(self) -> ToolKnowledgeBase:
        return self._kb

    @property
    def detector(self) -> ExecutionPatternDetector:
        return self._detector
