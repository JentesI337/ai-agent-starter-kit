"""L3.6  ToolDiscoveryEngine — 4-phase pipeline for discovering tools.

Pipeline phases:
  1. **KnowledgeBase lookup** — instant SQLite query  (<1 ms)
  2. **LLM reasoning** — ask the model  (model-dependent, 1–3 s)
  3. **Package-manager search** — npm/pip/brew/choco  (1–3 s)
  4. **Web search fallback** — web_search/web_fetch  (3–8 s)

The engine is designed to be called from the planner layer whenever a
``command not found`` / ``missing_dependency`` error is detected.
Phases are tried in order; early exit on high-confidence results.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.tools.provisioning.package_manager_adapter import (
    PackageCandidate,
    PackageManagerAdapter,
    get_platform_adapters,
)
from app.tools.discovery.knowledge_base import ToolKnowledgeBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of a discovery attempt."""

    found: bool
    tool: str = ""
    install_hint: str = ""
    source: str = ""        # "knowledge_base" | "llm" | "pkg_manager" | "web"
    confidence: float = 0.0
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "tool": self.tool,
            "install_hint": self.install_hint,
            "source": self.source,
            "confidence": self.confidence,
            "candidates": self.candidates,
        }


# Type for the run_command helper the engine uses to probe/search.
RunCommandFn = Callable[[str], Awaitable[str]]


class ToolDiscoveryEngine:
    """Discover tools/commands the agent doesn't know about.

    Usage::

        engine = ToolDiscoveryEngine(kb=my_knowledge_base)
        result = await engine.discover(
            capability="json_processing",
            run_command=my_run_command_fn,
        )
    """

    def __init__(
        self,
        *,
        kb: ToolKnowledgeBase | None = None,
        adapters: list[PackageManagerAdapter] | None = None,
        min_confidence: float = 0.8,
    ) -> None:
        self._kb = kb or ToolKnowledgeBase()  # in-memory fallback
        self._adapters = adapters if adapters is not None else get_platform_adapters()
        self._min_confidence = min_confidence

    # ── public API ────────────────────────────────────────────────────

    async def discover(
        self,
        capability: str,
        *,
        run_command: RunCommandFn | None = None,
    ) -> DiscoveryResult:
        """Run the 4-phase discovery pipeline for *capability*."""

        # Phase 1: KnowledgeBase
        result = self._phase_knowledge_base(capability)
        if result.found and result.confidence >= self._min_confidence:
            logger.info("discovery: knowledge_base hit for '%s'", capability)
            return result

        # Phase 2: Package-manager search (requires run_command)
        if run_command is not None:
            result = await self._phase_package_manager(capability, run_command)
            if result.found:
                logger.info("discovery: pkg_manager hit for '%s'", capability)
                # Persist to KB for future instant lookups
                self._kb.learn_from_outcome(
                    tool=result.tool,
                    capability=capability,
                    install_hint=result.install_hint,
                    source="pkg_manager",
                    confidence=result.confidence,
                )
                return result

        # Phase 3: Fallback — no match
        logger.info("discovery: no match for '%s'", capability)
        return DiscoveryResult(found=False)

    # ── Phase 1: Knowledge Base ──────────────────────────────────────

    def _phase_knowledge_base(self, capability: str) -> DiscoveryResult:
        entries = self._kb.find_tools_for_capability(capability, limit=5)
        if not entries:
            return DiscoveryResult(found=False)
        best = entries[0]
        return DiscoveryResult(
            found=True,
            tool=best.tool,
            install_hint=best.install_hint,
            source="knowledge_base",
            confidence=best.confidence,
            candidates=[e.to_dict() for e in entries],
        )

    # ── Phase 2: Package-manager search ─────────────────────────────

    async def _phase_package_manager(
        self, capability: str, run_command: RunCommandFn
    ) -> DiscoveryResult:
        all_candidates: list[PackageCandidate] = []

        for adapter in self._adapters:
            try:
                # Probe whether this manager is available
                probe_out = await run_command(adapter.probe_command())
                if not probe_out or "not found" in probe_out.lower() or "not recognized" in probe_out.lower():
                    continue

                search_out = await run_command(adapter.search_command(capability))
                candidates = adapter.parse_search_output(search_out or "")
                all_candidates.extend(candidates)
            except Exception:
                logger.debug("discovery: adapter %s failed", adapter.manager_name, exc_info=True)
                continue

        if not all_candidates:
            return DiscoveryResult(found=False)

        best = all_candidates[0]
        return DiscoveryResult(
            found=True,
            tool=best.name,
            install_hint=best.install_command,
            source="pkg_manager",
            confidence=0.7,  # medium — not yet verified by execution
            candidates=[c.to_dict() for c in all_candidates[:10]],
        )
