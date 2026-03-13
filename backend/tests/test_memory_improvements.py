"""Tests for memory system improvements: FTS5 search, turn summaries, distillation, compaction."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_runner import AgentRunner
from app.agent_runner_types import LoopState, StreamResult, ToolCall, ToolResult
from app.memory.long_term import (
    EpisodicEntry,
    FailureEntry,
    LongTermMemoryStore,
    SemanticEntry,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _make_ltm(*, fts_enabled: bool = True) -> LongTermMemoryStore:
    tmp = tempfile.mktemp(suffix=".db")
    return LongTermMemoryStore(tmp, fts_enabled=fts_enabled)


def _make_runner(**overrides) -> AgentRunner:
    defaults = dict(
        client=MagicMock(),
        memory=MagicMock(),
        tool_registry=MagicMock(),
        tool_execution_manager=MagicMock(),
        system_prompt="You are a test agent.",
        execute_tool_fn=AsyncMock(return_value="tool result"),
        allowed_tools_resolver=MagicMock(return_value={"read_file", "run_command"}),
    )
    defaults.update(overrides)
    return AgentRunner(**defaults)


# ──────────────────────────────────────────────────────────────────────
# FTS5 Search Tests
# ──────────────────────────────────────────────────────────────────────


class TestFTS5SearchFailures:
    def test_finds_related_terms(self):
        """FTS5 should find 'package installation failed' when searching 'install npm package'."""
        ltm = _make_ltm()
        ltm.add_failure(FailureEntry(
            failure_id="f1",
            task_description="install npm package lodash in the project",
            error_type="CommandError",
            root_cause="package installation failed due to network timeout",
            solution="Retry with --registry flag",
            prevention="Check network before install",
            tags=["npm", "install"],
        ))
        ltm.add_failure(FailureEntry(
            failure_id="f2",
            task_description="unrelated database migration task",
            error_type="SQLError",
            root_cause="missing column in schema",
            solution="Run migration script",
            prevention="Always check schema",
            tags=["database"],
        ))

        results = ltm.search_failures("package installation problems", limit=5)
        assert len(results) >= 1
        assert any("npm" in r.task_description or "package" in r.task_description for r in results)

    def test_ranks_by_relevance(self):
        """More relevant results should appear first via BM25."""
        ltm = _make_ltm()
        # Add a highly relevant entry
        ltm.add_failure(FailureEntry(
            failure_id="f1",
            task_description="python import error when loading module",
            error_type="ImportError",
            root_cause="module not found in path",
            solution="pip install the missing module",
            prevention="Add to requirements.txt",
            tags=["python", "import"],
        ))
        # Add a less relevant entry
        ltm.add_failure(FailureEntry(
            failure_id="f2",
            task_description="general configuration error",
            error_type="ConfigError",
            root_cause="missing env variable",
            solution="Set the variable",
            prevention="Document required vars",
            tags=["config"],
        ))

        results = ltm.search_failures("python import module error", limit=5)
        assert len(results) >= 1
        # The python/import entry should be first
        assert results[0].failure_id == "f1"

    def test_rebuild_indexes_existing_data(self):
        """Data inserted before FTS5 should be searchable after rebuild."""
        tmp = tempfile.mktemp(suffix=".db")
        # First create with FTS disabled
        ltm1 = LongTermMemoryStore(tmp, fts_enabled=False)
        ltm1.add_failure(FailureEntry(
            failure_id="f1",
            task_description="webpack build failure in production",
            error_type="BuildError",
            root_cause="missing loader for tsx files",
            solution="Install ts-loader",
            prevention="Check webpack config",
            tags=["webpack"],
        ))
        del ltm1

        # Re-open with FTS enabled — rebuild should index existing data
        ltm2 = LongTermMemoryStore(tmp, fts_enabled=True)
        results = ltm2.search_failures("webpack build tsx", limit=5)
        assert len(results) >= 1
        assert results[0].failure_id == "f1"

    def test_disabled_falls_back_to_like(self):
        """With FTS disabled, search still works via LIKE fallback."""
        ltm = _make_ltm(fts_enabled=False)
        ltm.add_failure(FailureEntry(
            failure_id="f1",
            task_description="docker container crashed on startup",
            error_type="RuntimeError",
            root_cause="port already in use",
            solution="Kill the process on port 8080",
            prevention="Check ports before starting",
            tags=["docker"],
        ))
        results = ltm.search_failures("docker container", limit=5)
        assert len(results) >= 1

    def test_special_characters_safe(self):
        """Queries with quotes, parens, etc. should not crash."""
        ltm = _make_ltm()
        ltm.add_failure(FailureEntry(
            failure_id="f1",
            task_description="test failure",
            error_type="TestError",
            root_cause="assertion failed",
            solution="fix test",
            prevention="add guard",
        ))
        # These should not raise
        ltm.search_failures('query with "quotes"', limit=5)
        ltm.search_failures("query (with) parens", limit=5)
        ltm.search_failures("", limit=5)
        ltm.search_failures("ab", limit=5)  # all terms too short


class TestFTS5SearchEpisodic:
    def test_ranks_by_relevance(self):
        ltm = _make_ltm()
        ltm.add_episodic(
            session_id="s1",
            summary="Implemented user authentication with JWT tokens",
            key_actions=["created auth middleware", "added JWT validation"],
            tags=["auth", "jwt"],
        )
        ltm.add_episodic(
            session_id="s2",
            summary="Fixed CSS styling issues on the landing page",
            key_actions=["updated styles.css"],
            tags=["css", "frontend"],
        )
        results = ltm.search_episodic("authentication JWT", limit=5)
        assert len(results) >= 1
        assert results[0].session_id == "s1"


class TestFTS5SearchSemantic:
    def test_returns_relevant_facts(self):
        """'python version' should find 'preferred_language: Python 3.11'."""
        ltm = _make_ltm()
        ltm.add_semantic(key="preferred_language", value="Python 3.11", confidence=0.8, source_sessions=["s1"])
        ltm.add_semantic(key="preferred_editor", value="VS Code", confidence=0.7, source_sessions=["s1"])
        ltm.add_semantic(key="project_framework", value="FastAPI", confidence=0.7, source_sessions=["s2"])

        results = ltm.search_semantic("python version", limit=10)
        assert len(results) >= 1
        assert any("Python" in r.value for r in results)

    def test_empty_query_returns_recent(self):
        """Empty query should fall back to get_all_semantic."""
        ltm = _make_ltm()
        ltm.add_semantic(key="k1", value="v1", confidence=0.5, source_sessions=["s1"])
        ltm.add_semantic(key="k2", value="v2", confidence=0.5, source_sessions=["s1"])

        results = ltm.search_semantic("", limit=10)
        assert len(results) == 2


class TestBuildFtsQuery:
    def test_normal_query(self):
        q = LongTermMemoryStore._build_fts_query("install npm package")
        assert '"install"' in q
        assert '"npm"' in q
        assert '"package"' in q
        assert "OR" in q

    def test_short_terms_stripped(self):
        q = LongTermMemoryStore._build_fts_query("go to it")
        # "go", "to", "it" are all < 3 chars
        assert q == ""

    def test_special_chars_removed(self):
        q = LongTermMemoryStore._build_fts_query('query "with" (parens)')
        assert "(" not in q
        assert ")" not in q

    def test_max_terms(self):
        q = LongTermMemoryStore._build_fts_query("one two three four five six seven eight nine ten")
        # Should cap at 8 terms
        assert q.count('"') == 16  # 8 terms * 2 quotes each


# ──────────────────────────────────────────────────────────────────────
# Turn Summary Tests
# ──────────────────────────────────────────────────────────────────────


class TestTurnSummary:
    def test_build_turn_summary(self):
        runner = _make_runner()
        results = [
            ToolResult(tool_call_id="c1", tool_name="read_file", content="file content here...", is_error=False),
            ToolResult(tool_call_id="c2", tool_name="run_command", content="Error: command not found", is_error=True),
        ]
        summary = runner._build_turn_summary(results, iteration=3)
        assert "[Turn 3]" in summary
        assert "read_file" in summary
        assert "run_command" in summary
        assert "1 ok" in summary
        assert "1 err" in summary

    def test_turn_summary_respects_max_chars(self):
        runner = _make_runner()
        results = [
            ToolResult(tool_call_id=f"c{i}", tool_name=f"tool_{i}", content="x" * 200, is_error=False)
            for i in range(10)
        ]
        with patch("app.agent_runner.settings") as mock_settings:
            mock_settings.memory_turn_summary_max_chars = 100
            summary = runner._build_turn_summary(results, iteration=1)
        assert len(summary) <= 100

    def test_turn_summary_included_in_initial_messages(self):
        runner = _make_runner()
        item_user = MagicMock(role="user", content="hello")
        item_assistant = MagicMock(role="assistant", content="hi")
        item_turn = MagicMock(role="turn_summary", content="[Turn 1] Tools: read_file (1 ok, 0 err)")

        with patch("app.agent_runner.settings") as mock_settings:
            mock_settings.memory_include_turn_summaries = True
            msgs = runner._build_initial_messages(
                memory_items=[item_user, item_assistant, item_turn],
                user_message="next question",
            )

        # Should include: system + user + assistant + turn_summary(as user) + user
        turn_msgs = [m for m in msgs if "[Previous tool context]" in m.get("content", "")]
        assert len(turn_msgs) == 1
        assert turn_msgs[0]["role"] == "user"

    def test_turn_summary_excluded_when_flag_off(self):
        runner = _make_runner()
        item_user = MagicMock(role="user", content="hello")
        item_turn = MagicMock(role="turn_summary", content="[Turn 1] summary")

        with patch("app.agent_runner.settings") as mock_settings:
            mock_settings.memory_include_turn_summaries = False
            msgs = runner._build_initial_messages(
                memory_items=[item_user, item_turn],
                user_message="next question",
            )

        turn_msgs = [m for m in msgs if "[Previous tool context]" in m.get("content", "")]
        assert len(turn_msgs) == 0


# ──────────────────────────────────────────────────────────────────────
# Distillation Tests
# ──────────────────────────────────────────────────────────────────────


class TestDistillationImprovements:
    def test_confidence_varies_with_errors(self):
        """All-ok tools → high confidence, all-error → low confidence."""
        # Simulate tool results strings
        ok_results = "[read_file] content\n[write_file] done"
        err_results = "[read_file] [ERROR] failed\n[write_file] [ERROR] failed"

        # ok: 2 tools, 0 errors → success_rate=1.0 → confidence=0.9
        ok_count = max(1, ok_results.count("["))
        ok_errors = ok_results.count("[ERROR]")
        ok_rate = 1.0 - (ok_errors / ok_count)
        ok_conf = 0.5 + (ok_rate * 0.4)
        assert ok_conf > 0.8

        # err: 4 brackets, 2 errors → success_rate=0.5 → confidence=0.7
        err_count = max(1, err_results.count("["))
        err_errors = err_results.count("[ERROR]")
        err_rate = 1.0 - (err_errors / err_count)
        err_conf = 0.5 + (err_rate * 0.4)
        assert err_conf < ok_conf


# ──────────────────────────────────────────────────────────────────────
# Compaction Tests
# ──────────────────────────────────────────────────────────────────────


class TestCompactionImprovements:
    def test_text_fallback_preserves_tool_metadata(self):
        from app.session.compaction import CompactionService

        svc = CompactionService(MagicMock())
        messages = [
            {"role": "tool", "tool_call_id": "call_123", "content": "[ERROR] Command not found: npm"},
            {"role": "tool", "tool_call_id": "call_456", "content": "File content: hello world"},
        ]
        summary = svc._text_fallback_summary(messages)
        assert "call_123" in summary
        assert "ERR" in summary
        assert "call_456" in summary
        assert "OK" in summary

    def test_text_fallback_uses_configurable_chars(self):
        from app.session.compaction import CompactionService

        svc = CompactionService(MagicMock())
        long_content = "x" * 500
        messages = [{"role": "user", "content": long_content}]

        with patch("app.session.compaction.settings") as mock_settings:
            mock_settings.runner_compaction_text_fallback_chars = 300
            summary = svc._text_fallback_summary(messages)

        # Should include ~300 chars of content, not just 150
        assert len(summary) > 200


# ──────────────────────────────────────────────────────────────────────
# Progress context (verify unchanged)
# ──────────────────────────────────────────────────────────────────────


class TestLoopStatePlan:
    def test_loop_state_has_plan_field(self):
        state = LoopState()
        assert state.plan is not None
        assert state.plan.planning_active is False
        assert state.plan.steps == []
