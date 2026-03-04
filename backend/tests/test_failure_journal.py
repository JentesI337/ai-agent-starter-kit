from __future__ import annotations

import asyncio
import sqlite3

import pytest

from app.agent import HeadAgent
from app.config import settings
from app.orchestrator.step_executors import PlannerStepExecutor
from app.services.long_term_memory import FailureEntry, SemanticEntry


def test_failure_journal_logs_entry_when_run_raises(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    monkeypatch.setattr(settings, "long_term_memory_enabled", True)
    monkeypatch.setattr(settings, "failure_journal_enabled", True)
    monkeypatch.setattr(settings, "long_term_memory_db_path", str(db_path))

    agent = HeadAgent(name="failure-journal-test-agent")

    async def fake_plan_execute(payload, model=None):
        _ = (payload, model)
        raise RuntimeError("simulated planner failure")

    monkeypatch.setattr(agent, "plan_step_executor", PlannerStepExecutor(execute_fn=fake_plan_execute))
    monkeypatch.setattr(agent.tools, "check_toolchain", lambda: (True, {"ok": True}))

    events: list[dict] = []

    async def send_event(event: dict) -> None:
        events.append(event)

    with pytest.raises(RuntimeError, match="simulated planner failure"):
        asyncio.run(
            agent.run(
                user_message="please plan this task",
                send_event=send_event,
                session_id="sess1",
                request_id="req-failure-1",
            )
        )

    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            """
            SELECT id, task_description, error_type, root_cause, solution, prevention, tags
            FROM failure_journal
            WHERE id = ?
            """,
            ("req-failure-1",),
        ).fetchone()

    assert row is not None
    assert row[0] == "req-failure-1"
    assert row[1] == "please plan this task"
    assert row[2] == "RuntimeError"
    assert "simulated planner failure" in row[3]
    assert row[4] == ""
    assert row[5] == ""
    assert row[6] == ""
    assert any(event.get("stage") == "run_started" for event in events)


def test_planning_context_includes_long_term_memory_snapshot(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    monkeypatch.setattr(settings, "long_term_memory_enabled", True)
    monkeypatch.setattr(settings, "failure_journal_enabled", True)
    monkeypatch.setattr(settings, "long_term_memory_db_path", str(db_path))

    agent = HeadAgent(name="ltm-snapshot-test-agent")
    assert agent._long_term_memory is not None

    agent._long_term_memory.add_failure(
        FailureEntry(
            failure_id="f-1",
            task_description="deploy preview to cloud",
            error_type="RuntimeError",
            root_cause="missing token",
            solution="export token",
            prevention="precheck env",
            tags=["deploy"],
        )
    )
    agent._long_term_memory.add_semantic(
        SemanticEntry(
            key="user.preferred_runtime",
            value="python",
            confidence=0.9,
            source_sessions=["sess1"],
        )
    )

    ltm_context = agent._build_long_term_memory_context("deploy preview env")
    assert "[Past failures with similar tasks]" in ltm_context
    assert "missing token" in ltm_context
    assert "[Known user preferences]" in ltm_context
    assert "user.preferred_runtime: python" in ltm_context

    async def fake_plan_execute(payload, model=None):
        _ = model
        assert "Snapshot:" in payload.reduced_context
        assert "user.preferred_runtime: python" in payload.reduced_context
        raise RuntimeError("stop after planning context check")

    monkeypatch.setattr(agent, "plan_step_executor", PlannerStepExecutor(execute_fn=fake_plan_execute))
    monkeypatch.setattr(agent.tools, "check_toolchain", lambda: (True, {"ok": True}))

    async def send_event(_: dict) -> None:
        return None

    with pytest.raises(RuntimeError, match="stop after planning context check"):
        asyncio.run(
            agent.run(
                user_message="deploy preview env",
                send_event=send_event,
                session_id="sess1",
                request_id="req-ltm-ctx-1",
            )
        )
