"""L6.3  ToolEcosystemMap — graph of tool ecosystems.

Models the relationship between tools, package managers, capabilities,
and format conversions as an in-memory directed graph.  Provides
queries like "which tools can do X?", "what converts A→B?", and
shortest-path chains for multi-step conversions.

The graph is pre-seeded with the three core ecosystems (Python, Node.js,
System-Tools) and can be extended at runtime via ``add_tool`` / ``add_edge``.

Usage::

    eco = ToolEcosystemMap()
    tools = eco.tools_for_capability("json_processing")
    chain = eco.conversion_chain("text/markdown", "application/pdf")
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EcoTool:
    """A tool node in the ecosystem graph."""

    name: str
    ecosystem: str              # "python" | "node" | "system" | "custom"
    capabilities: frozenset[str] = frozenset()
    install_hint: str = ""
    formats_in: frozenset[str] = frozenset()   # MIME types or short labels
    formats_out: frozenset[str] = frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ecosystem": self.ecosystem,
            "capabilities": sorted(self.capabilities),
            "install_hint": self.install_hint,
            "formats_in": sorted(self.formats_in),
            "formats_out": sorted(self.formats_out),
        }


@dataclass(frozen=True)
class ConversionEdge:
    """A directed edge: tool converts *format_in* → *format_out*."""

    tool: str
    format_in: str
    format_out: str
    cost: float = 1.0   # lower = preferred

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "format_in": self.format_in,
            "format_out": self.format_out,
            "cost": self.cost,
        }


# ── Pre-seeded data ──────────────────────────────────────────────────

_SEED_TOOLS: list[EcoTool] = [
    # Python ecosystem
    EcoTool("python", "python", frozenset({"scripting", "data_processing", "json_processing", "csv_processing"}), "pre-installed"),
    EcoTool("pip", "python", frozenset({"package_management"}), "pre-installed"),
    EcoTool("black", "python", frozenset({"code_formatting"}), "pip install black"),
    EcoTool("pytest", "python", frozenset({"testing"}), "pip install pytest"),
    EcoTool("pandas", "python", frozenset({"data_processing", "csv_processing"}), "pip install pandas"),
    EcoTool("weasyprint", "python", frozenset({"pdf_generation"}), "pip install weasyprint",
            frozenset({"text/html"}), frozenset({"application/pdf"})),

    # Node.js ecosystem
    EcoTool("node", "node", frozenset({"scripting", "json_processing"}), "pre-installed"),
    EcoTool("npm", "node", frozenset({"package_management"}), "pre-installed"),
    EcoTool("prettier", "node", frozenset({"code_formatting"}), "npm install prettier"),
    EcoTool("typescript", "node", frozenset({"transpilation"}), "npm install typescript"),
    EcoTool("eslint", "node", frozenset({"linting"}), "npm install eslint"),
    EcoTool("marked", "node", frozenset({"markdown_rendering"}), "npm install marked",
            frozenset({"text/markdown"}), frozenset({"text/html"})),

    # System tools
    EcoTool("pandoc", "system", frozenset({"document_conversion", "pdf_generation", "markdown_rendering"}),
            "choco install pandoc / brew install pandoc",
            frozenset({"text/markdown", "text/html", "application/docx"}),
            frozenset({"application/pdf", "text/html", "application/docx"})),
    EcoTool("ffmpeg", "system", frozenset({"video_processing", "audio_processing", "image_processing"}),
            "choco install ffmpeg / brew install ffmpeg",
            frozenset({"video/*", "audio/*", "image/*"}),
            frozenset({"video/*", "audio/*", "image/*"})),
    EcoTool("imagemagick", "system", frozenset({"image_processing", "image_conversion"}),
            "choco install imagemagick / brew install imagemagick",
            frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"}),
            frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})),
    EcoTool("jq", "system", frozenset({"json_processing"}), "choco install jq / brew install jq"),
    EcoTool("curl", "system", frozenset({"http_client"}), "pre-installed"),
    EcoTool("git", "system", frozenset({"version_control"}), "pre-installed"),
]

_SEED_EDGES: list[ConversionEdge] = [
    ConversionEdge("pandoc", "text/markdown", "application/pdf", 1.0),
    ConversionEdge("pandoc", "text/markdown", "text/html", 1.0),
    ConversionEdge("pandoc", "text/html", "application/pdf", 1.0),
    ConversionEdge("pandoc", "application/docx", "text/markdown", 1.0),
    ConversionEdge("pandoc", "text/markdown", "application/docx", 1.0),
    ConversionEdge("weasyprint", "text/html", "application/pdf", 1.5),
    ConversionEdge("marked", "text/markdown", "text/html", 0.5),
    ConversionEdge("imagemagick", "image/png", "image/jpeg", 1.0),
    ConversionEdge("imagemagick", "image/jpeg", "image/png", 1.0),
    ConversionEdge("imagemagick", "image/png", "image/webp", 1.0),
    ConversionEdge("ffmpeg", "video/mp4", "video/webm", 1.0),
    ConversionEdge("ffmpeg", "audio/wav", "audio/mp3", 1.0),
    ConversionEdge("ffmpeg", "video/mp4", "audio/mp3", 1.5),
]


# ── Main class ────────────────────────────────────────────────────────


class ToolEcosystemMap:
    """In-memory graph of tool ecosystems.

    Usage::

        eco = ToolEcosystemMap()
        tools = eco.tools_for_capability("pdf_generation")
        chain = eco.conversion_chain("text/markdown", "application/pdf")
    """

    def __init__(self, *, seed: bool = True) -> None:
        self._tools: dict[str, EcoTool] = {}
        self._edges: list[ConversionEdge] = []
        # Adjacency: format_in → [(format_out, tool, cost)]
        self._adj: dict[str, list[tuple[str, str, float]]] = {}

        if seed:
            for t in _SEED_TOOLS:
                self._tools[t.name] = t
            for e in _SEED_EDGES:
                self._edges.append(e)
                self._adj.setdefault(e.format_in, []).append(
                    (e.format_out, e.tool, e.cost)
                )

    # ── queries ───────────────────────────────────────────────────────

    def tools_for_capability(self, capability: str) -> list[EcoTool]:
        """Return tools that declare *capability*."""
        cap_lower = capability.lower()
        return [
            t for t in self._tools.values()
            if any(cap_lower in c.lower() for c in t.capabilities)
        ]

    def tools_for_ecosystem(self, ecosystem: str) -> list[EcoTool]:
        """Return all tools in *ecosystem* (``python``, ``node``, ``system``)."""
        return [t for t in self._tools.values() if t.ecosystem == ecosystem]

    def ecosystems(self) -> list[str]:
        """Return distinct ecosystem names."""
        return sorted({t.ecosystem for t in self._tools.values()})

    def get_tool(self, name: str) -> EcoTool | None:
        return self._tools.get(name)

    def all_tools(self) -> list[EcoTool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    # ── conversion chain (BFS shortest path) ─────────────────────────

    def conversion_chain(
        self, format_in: str, format_out: str,
    ) -> list[ConversionEdge]:
        """Find the cheapest conversion chain from *format_in* to *format_out*.

        Returns an ordered list of edges, or ``[]`` if no path exists.
        Uses BFS on the format graph for simplicity (edges have ~uniform cost).
        """
        if format_in == format_out:
            return []

        visited: set[str] = {format_in}
        queue: deque[tuple[str, list[ConversionEdge]]] = deque()
        queue.append((format_in, []))

        while queue:
            current, path = queue.popleft()
            for fmt_out, tool, cost in self._adj.get(current, []):
                if fmt_out in visited:
                    continue
                edge = ConversionEdge(tool=tool, format_in=current, format_out=fmt_out, cost=cost)
                new_path = [*path, edge]
                if fmt_out == format_out:
                    return new_path
                visited.add(fmt_out)
                queue.append((fmt_out, new_path))

        return []

    # ── mutation ──────────────────────────────────────────────────────

    def add_tool(self, tool: EcoTool) -> None:
        """Register a new tool node."""
        self._tools[tool.name] = tool

    def add_edge(self, edge: ConversionEdge) -> None:
        """Register a new conversion edge."""
        self._edges.append(edge)
        self._adj.setdefault(edge.format_in, []).append(
            (edge.format_out, edge.tool, edge.cost)
        )

    def tool_count(self) -> int:
        return len(self._tools)

    def edge_count(self) -> int:
        return len(self._edges)
