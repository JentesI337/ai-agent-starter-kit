from __future__ import annotations

import sqlite3

from app.services.long_term_memory import FailureEntry, LongTermMemoryStore, SemanticEntry


def test_long_term_memory_add_failure_persists_row(tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    store = LongTermMemoryStore(str(db_path))

    store.add_failure(
        FailureEntry(
            failure_id="req-123",
            task_description="run tests",
            error_type="RuntimeError",
            root_cause="tool timeout",
            solution="",
            prevention="",
            tags=["tests", "timeout"],
        )
    )

    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            """
            SELECT id, task_description, error_type, root_cause, solution, prevention, tags
            FROM failure_journal
            WHERE id = ?
            """,
            ("req-123",),
        ).fetchone()

    assert row is not None
    assert row[0] == "req-123"
    assert row[1] == "run tests"
    assert row[2] == "RuntimeError"
    assert row[3] == "tool timeout"
    assert row[4] == ""
    assert row[5] == ""
    assert row[6] == "tests,timeout"


def test_long_term_memory_search_failures_and_semantic_retrieval(tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    store = LongTermMemoryStore(str(db_path))

    store.add_failure(
        FailureEntry(
            failure_id="req-1",
            task_description="deploy preview environment",
            error_type="RuntimeError",
            root_cause="missing env var",
            solution="set PREVIEW_TOKEN",
            prevention="validate env before deploy",
            tags=["deploy", "preview"],
        )
    )
    store.add_failure(
        FailureEntry(
            failure_id="req-2",
            task_description="run lint job",
            error_type="RuntimeError",
            root_cause="node modules missing",
            solution="install dependencies",
            prevention="cache node_modules",
            tags=["ci"],
        )
    )
    store.add_semantic(
        SemanticEntry(
            key="user.preferred_language",
            value="Python",
            confidence=0.8,
            source_sessions=["sess-a", "sess-b"],
        )
    )

    failures = store.search_failures("deploy", limit=2)
    semantic = store.get_all_semantic()

    assert len(failures) == 1
    assert failures[0].failure_id == "req-1"
    assert failures[0].solution == "set PREVIEW_TOKEN"
    assert failures[0].tags == ["deploy", "preview"]

    assert len(semantic) == 1
    assert semantic[0].key == "user.preferred_language"
    assert semantic[0].value == "Python"
    assert semantic[0].source_sessions == ["sess-a", "sess-b"]


def test_long_term_memory_get_semantic_by_key(tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    store = LongTermMemoryStore(str(db_path))

    store.add_semantic(
        key="user.editor",
        value="vscode",
        confidence=0.9,
        source_sessions=["sess-1"],
    )

    entry = store.get_semantic("user.editor")
    missing = store.get_semantic("unknown.key")

    assert entry is not None
    assert entry.key == "user.editor"
    assert entry.value == "vscode"
    assert entry.source_sessions == ["sess-1"]
    assert missing is None


def test_long_term_memory_search_episodic(tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    store = LongTermMemoryStore(str(db_path))

    store.add_episodic(
        session_id="sess-episodic-1",
        summary="Implemented deployment workflow and validated smoke tests.",
        key_actions=["deploy", "verify"],
        outcome="success",
        tags=["deployment", "smoke"],
    )
    store.add_episodic(
        session_id="sess-episodic-2",
        summary="Refactored cache layer.",
        key_actions=["refactor"],
        outcome="success",
        tags=["cache"],
    )

    deploy_hits = store.search_episodic("deployment verify", limit=5)
    all_hits = store.search_episodic("", limit=5)

    assert len(deploy_hits) == 1
    assert deploy_hits[0].session_id == "sess-episodic-1"
    assert "deploy" in deploy_hits[0].key_actions
    assert "deployment" in deploy_hits[0].tags

    assert len(all_hits) == 2
