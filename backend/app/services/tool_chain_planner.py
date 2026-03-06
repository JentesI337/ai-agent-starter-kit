"""D-10  ToolChainPlanner — high-level multi-step tool-chain planning.

Wraps :class:`ToolEcosystemMap` to provide a planning API that the agent
can use to figure out *which sequence of tools* will convert input-A to
output-B, install missing tools along the way, and verify each step.

Usage::

    planner = ToolChainPlanner()          # uses default seeded ecosystem map
    plan = planner.plan_chain("text/markdown", "application/pdf")
    if plan.feasible:
        for step in plan.steps:
            print(step)

Design rules (from ROADTOTOOLGOLD):
  - Frozen dataclasses for all result types.
  - No ``additionalProperties`` / extra dict blobs.
  - Pure logic — no I/O, no network calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services.tool_ecosystem_map import ConversionEdge, ToolEcosystemMap

logger = logging.getLogger(__name__)


# ── Result types (frozen) ────────────────────────────────────────────


@dataclass(frozen=True)
class ChainStep:
    """One step in a conversion chain plan."""

    index: int
    tool: str
    format_in: str
    format_out: str
    install_hint: str
    cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tool": self.tool,
            "format_in": self.format_in,
            "format_out": self.format_out,
            "install_hint": self.install_hint,
            "cost": self.cost,
        }


@dataclass(frozen=True)
class ChainPlan:
    """The result of a chain-planning request."""

    format_in: str
    format_out: str
    feasible: bool
    steps: tuple[ChainStep, ...] = ()
    total_cost: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_in": self.format_in,
            "format_out": self.format_out,
            "feasible": self.feasible,
            "steps": [s.to_dict() for s in self.steps],
            "total_cost": self.total_cost,
            "reason": self.reason,
        }


# ── Planner ──────────────────────────────────────────────────────────


class ToolChainPlanner:
    """Plan multi-step tool chains using the ecosystem graph.

    This sits one layer above :class:`ToolEcosystemMap` and provides:

    * ``plan_chain(format_in, format_out)`` — returns a :class:`ChainPlan`
      with ordered :class:`ChainStep` objects.
    * ``suggest_alternatives(format_in, format_out)`` — returns up to *k*
      alternative chain plans (different tool choices).
    """

    def __init__(self, ecosystem: ToolEcosystemMap | None = None) -> None:
        self._eco = ecosystem or ToolEcosystemMap()

    # ── public API ────────────────────────────────────────────────────

    def plan_chain(self, format_in: str, format_out: str) -> ChainPlan:
        """Compute the cheapest conversion chain.

        Returns a :class:`ChainPlan` with ``feasible=True`` and populated
        steps when a path exists, or ``feasible=False`` with a reason.
        """
        if format_in == format_out:
            return ChainPlan(
                format_in=format_in,
                format_out=format_out,
                feasible=True,
                reason="no conversion needed — formats are identical",
            )

        edges = self._eco.conversion_chain(format_in, format_out)
        if not edges:
            return ChainPlan(
                format_in=format_in,
                format_out=format_out,
                feasible=False,
                reason=f"no conversion path from {format_in!r} to {format_out!r}",
            )

        steps = tuple(self._edge_to_step(i, e) for i, e in enumerate(edges))
        total_cost = sum(s.cost for s in steps)
        return ChainPlan(
            format_in=format_in,
            format_out=format_out,
            feasible=True,
            steps=steps,
            total_cost=total_cost,
        )

    def suggest_alternatives(
        self,
        format_in: str,
        format_out: str,
        *,
        max_alternatives: int = 3,
    ) -> list[ChainPlan]:
        """Return up to *max_alternatives* distinct chain plans.

        The first entry is the cheapest (primary plan).  Subsequent entries
        use different tools where possible.  If only one path exists the
        list contains a single element.
        """
        primary = self.plan_chain(format_in, format_out)
        if not primary.feasible:
            return [primary]

        # Collect alternative paths by temporarily removing edges used in
        # the primary plan and re-searching.
        alternatives: list[ChainPlan] = [primary]
        used_tool_sets: set[frozenset[str]] = {
            frozenset(s.tool for s in primary.steps)
        }

        # Simple heuristic: remove each primary-plan edge in turn and ask the
        # ecosystem map for an alternative path.
        original_adj = {k: list(v) for k, v in self._eco._adj.items()}
        for step in primary.steps:
            # Temporarily remove the edge
            adj_list = self._eco._adj.get(step.format_in, [])
            filtered = [
                entry for entry in adj_list
                if not (entry[0] == step.format_out and entry[1] == step.tool)
            ]
            self._eco._adj[step.format_in] = filtered

            alt_edges = self._eco.conversion_chain(format_in, format_out)
            if alt_edges:
                tool_set = frozenset(e.tool for e in alt_edges)
                if tool_set not in used_tool_sets:
                    alt_steps = tuple(
                        self._edge_to_step(i, e)
                        for i, e in enumerate(alt_edges)
                    )
                    alternatives.append(
                        ChainPlan(
                            format_in=format_in,
                            format_out=format_out,
                            feasible=True,
                            steps=alt_steps,
                            total_cost=sum(s.cost for s in alt_steps),
                        )
                    )
                    used_tool_sets.add(tool_set)

            # Restore
            self._eco._adj[step.format_in] = original_adj.get(step.format_in, [])

            if len(alternatives) >= max_alternatives:
                break

        return alternatives

    @property
    def ecosystem(self) -> ToolEcosystemMap:
        """Access the underlying ecosystem map (read-only intent)."""
        return self._eco

    # ── internals ─────────────────────────────────────────────────────

    def _edge_to_step(self, index: int, edge: ConversionEdge) -> ChainStep:
        tool_node = self._eco.get_tool(edge.tool)
        install_hint = tool_node.install_hint if tool_node else ""
        return ChainStep(
            index=index,
            tool=edge.tool,
            format_in=edge.format_in,
            format_out=edge.format_out,
            install_hint=install_hint,
            cost=edge.cost,
        )
