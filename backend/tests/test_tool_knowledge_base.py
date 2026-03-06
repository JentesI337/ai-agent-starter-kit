"""Unit tests for ToolKnowledgeBase."""

from __future__ import annotations

import time

import pytest

from app.services.tool_knowledge_base import ToolKnowledgeBase


@pytest.fixture
def kb():
    return ToolKnowledgeBase()  # in-memory


class TestLearnAndQuery:
    def test_learn_basic(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json_processing", install_hint="apt install jq")
        assert kb.count() == 1

    def test_find_capability(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json_processing")
        kb.learn_from_outcome(tool="prettier", capability="code_formatting")
        results = kb.find_tools_for_capability("json")
        assert len(results) == 1
        assert results[0].tool == "jq"

    def test_find_empty(self, kb: ToolKnowledgeBase):
        assert kb.find_tools_for_capability("nonexistent") == []

    def test_upsert_updates_confidence(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json", confidence=0.5)
        kb.learn_from_outcome(tool="jq", capability="json", confidence=0.9)
        entries = kb.get_tool_hints("jq")
        assert len(entries) == 1
        assert entries[0].confidence == 0.9  # MAX of old and new

    def test_upsert_preserves_install_hint(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json", install_hint="apt install jq")
        kb.learn_from_outcome(tool="jq", capability="json")  # empty hint
        entries = kb.get_tool_hints("jq")
        assert entries[0].install_hint == "apt install jq"  # preserved

    def test_upsert_overwrites_install_hint(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json", install_hint="old")
        kb.learn_from_outcome(tool="jq", capability="json", install_hint="new")
        entries = kb.get_tool_hints("jq")
        assert entries[0].install_hint == "new"

    def test_get_tool_hints_multiple_capabilities(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="python", capability="scripting")
        kb.learn_from_outcome(tool="python", capability="data_processing")
        hints = kb.get_tool_hints("python")
        assert len(hints) == 2

    def test_min_confidence_filter(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json", confidence=0.2)
        results = kb.find_tools_for_capability("json", min_confidence=0.5)
        assert len(results) == 0

    def test_limit(self, kb: ToolKnowledgeBase):
        for i in range(20):
            kb.learn_from_outcome(tool=f"tool_{i}", capability="generic")
        results = kb.find_tools_for_capability("generic", limit=5)
        assert len(results) == 5

    def test_all_entries(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="a", capability="x")
        kb.learn_from_outcome(tool="b", capability="y")
        all_e = kb.all_entries()
        assert len(all_e) == 2

    def test_to_dict(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json", source="pkg_manager")
        entry = kb.get_tool_hints("jq")[0]
        d = entry.to_dict()
        assert d["tool"] == "jq"
        assert d["source"] == "pkg_manager"

    def test_pitfall_stored(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="rm", capability="file_delete", pitfall="recursive delete is dangerous")
        entry = kb.get_tool_hints("rm")[0]
        assert "dangerous" in entry.pitfall

    def test_source_field(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="x", capability="y", source="web")
        assert kb.get_tool_hints("x")[0].source == "web"


class TestConfidenceDecay:
    """X-10: confidence must decay with exp(-0.01 * days_since_last_seen)."""

    def test_fresh_entry_full_confidence(self, kb: ToolKnowledgeBase):
        kb.learn_from_outcome(tool="jq", capability="json", confidence=1.0)
        results = kb.find_tools_for_capability("json")
        assert len(results) == 1
        # Just inserted → effectively 0 days old → confidence ≈ 1.0
        assert results[0].confidence > 0.99

    def test_old_entry_decayed(self, kb: ToolKnowledgeBase):
        # Manually insert an entry with last_seen 90 days ago
        ninety_days_ago = time.time() - 90 * 86400
        with kb._lock, kb._conn:
            kb._conn.execute(
                """INSERT INTO tool_knowledge
                   (tool, capability, confidence, source, last_seen)
                   VALUES (?, ?, ?, ?, ?)""",
                ("ancient", "json", 1.0, "agent", ninety_days_ago),
            )
        results = kb.find_tools_for_capability("json", min_confidence=0.0)
        ancient = [r for r in results if r.tool == "ancient"]
        assert len(ancient) == 1
        # exp(-0.01 * 90) ≈ 0.4066
        assert ancient[0].confidence < 0.5

    def test_decay_filters_below_threshold(self, kb: ToolKnowledgeBase):
        # Entry 200 days old with confidence=0.5 → exp(-0.01*200)*0.5 ≈ 0.0677
        old_time = time.time() - 200 * 86400
        with kb._lock, kb._conn:
            kb._conn.execute(
                """INSERT INTO tool_knowledge
                   (tool, capability, confidence, source, last_seen)
                   VALUES (?, ?, ?, ?, ?)""",
                ("stale", "json", 0.5, "agent", old_time),
            )
        # Default min_confidence=0.3 → stale entry should be filtered out
        results = kb.find_tools_for_capability("json")
        stale = [r for r in results if r.tool == "stale"]
        assert len(stale) == 0
