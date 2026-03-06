"""Unit tests for L6.3 ToolEcosystemMap."""

from __future__ import annotations

import pytest

from app.services.tool_ecosystem_map import (
    ConversionEdge,
    EcoTool,
    ToolEcosystemMap,
)

# ── EcoTool ──────────────────────────────────────────────────────────


class TestEcoTool:
    def test_to_dict(self):
        t = EcoTool(
            name="jq", ecosystem="system",
            capabilities=frozenset({"json_processing"}),
            install_hint="brew install jq",
        )
        d = t.to_dict()
        assert d["name"] == "jq"
        assert d["ecosystem"] == "system"
        assert "json_processing" in d["capabilities"]

    def test_frozen(self):
        t = EcoTool(name="x", ecosystem="system")
        with pytest.raises(AttributeError):
            t.name = "y"  # type: ignore[misc]


# ── ConversionEdge ───────────────────────────────────────────────────


class TestConversionEdge:
    def test_to_dict(self):
        e = ConversionEdge(tool="pandoc", format_in="text/markdown", format_out="application/pdf")
        d = e.to_dict()
        assert d["tool"] == "pandoc"
        assert d["format_in"] == "text/markdown"
        assert d["format_out"] == "application/pdf"
        assert d["cost"] == 1.0

    def test_frozen(self):
        e = ConversionEdge(tool="x", format_in="a", format_out="b")
        with pytest.raises(AttributeError):
            e.tool = "y"  # type: ignore[misc]


# ── ToolEcosystemMap — seeded state ─────────────────────────────────


class TestSeededMap:
    def test_ecosystems_at_least_three(self):
        """AC-39: ≥ 3 ecosystems."""
        eco = ToolEcosystemMap()
        ecosystems = eco.ecosystems()
        assert len(ecosystems) >= 3
        assert "python" in ecosystems
        assert "node" in ecosystems
        assert "system" in ecosystems

    def test_tool_count(self):
        eco = ToolEcosystemMap()
        assert eco.tool_count() >= 18

    def test_edge_count(self):
        eco = ToolEcosystemMap()
        assert eco.edge_count() >= 13


# ── tools_for_capability ────────────────────────────────────────────


class TestToolsForCapability:
    def test_json_processing(self):
        eco = ToolEcosystemMap()
        tools = eco.tools_for_capability("json_processing")
        names = {t.name for t in tools}
        assert "python" in names
        assert "jq" in names

    def test_pdf_generation(self):
        eco = ToolEcosystemMap()
        tools = eco.tools_for_capability("pdf_generation")
        names = {t.name for t in tools}
        assert "pandoc" in names
        assert "weasyprint" in names

    def test_unknown_capability_empty(self):
        eco = ToolEcosystemMap()
        tools = eco.tools_for_capability("quantum_computing")
        assert tools == []


# ── tools_for_ecosystem ─────────────────────────────────────────────


class TestToolsForEcosystem:
    def test_python_tools(self):
        eco = ToolEcosystemMap()
        tools = eco.tools_for_ecosystem("python")
        names = {t.name for t in tools}
        assert "pip" in names
        assert "python" in names

    def test_node_tools(self):
        eco = ToolEcosystemMap()
        tools = eco.tools_for_ecosystem("node")
        names = {t.name for t in tools}
        assert "npm" in names
        assert "node" in names

    def test_system_tools(self):
        eco = ToolEcosystemMap()
        tools = eco.tools_for_ecosystem("system")
        names = {t.name for t in tools}
        assert "pandoc" in names
        assert "git" in names


# ── conversion_chain BFS ─────────────────────────────────────────────


class TestConversionChain:
    def test_direct_md_to_pdf(self):
        """Pandoc can do md → pdf in one step."""
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("text/markdown", "application/pdf")
        assert len(chain) >= 1
        assert chain[-1].format_out == "application/pdf"

    def test_md_to_docx(self):
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("text/markdown", "application/docx")
        assert len(chain) == 1
        assert chain[0].tool == "pandoc"

    def test_png_to_jpeg(self):
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("image/png", "image/jpeg")
        assert len(chain) == 1
        assert chain[0].tool == "imagemagick"

    def test_no_path_returns_empty(self):
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("application/pdf", "video/mp4")
        assert chain == []

    def test_same_format_returns_empty(self):
        eco = ToolEcosystemMap()
        chain = eco.conversion_chain("text/html", "text/html")
        assert chain == []

    def test_multi_step_chain(self):
        """Build a custom 2-step chain: A → B → C."""
        eco = ToolEcosystemMap(seed=False)
        eco.add_edge(ConversionEdge("tool1", "A", "B", 1.0))
        eco.add_edge(ConversionEdge("tool2", "B", "C", 1.0))
        chain = eco.conversion_chain("A", "C")
        assert len(chain) == 2
        assert chain[0].format_in == "A"
        assert chain[0].format_out == "B"
        assert chain[1].format_in == "B"
        assert chain[1].format_out == "C"


# ── mutation ─────────────────────────────────────────────────────────


class TestMutation:
    def test_add_tool(self):
        eco = ToolEcosystemMap(seed=False)
        assert eco.tool_count() == 0
        eco.add_tool(EcoTool(name="newtool", ecosystem="custom"))
        assert eco.tool_count() == 1
        assert eco.get_tool("newtool") is not None

    def test_add_edge(self):
        eco = ToolEcosystemMap(seed=False)
        assert eco.edge_count() == 0
        eco.add_edge(ConversionEdge("x", "A", "B"))
        assert eco.edge_count() == 1
        chain = eco.conversion_chain("A", "B")
        assert len(chain) == 1

    def test_get_tool_missing(self):
        eco = ToolEcosystemMap(seed=False)
        assert eco.get_tool("nonexistent") is None

    def test_all_tools_sorted(self):
        eco = ToolEcosystemMap(seed=False)
        eco.add_tool(EcoTool(name="z_tool", ecosystem="system"))
        eco.add_tool(EcoTool(name="a_tool", ecosystem="python"))
        tools = eco.all_tools()
        assert tools[0].name == "a_tool"
        assert tools[1].name == "z_tool"
