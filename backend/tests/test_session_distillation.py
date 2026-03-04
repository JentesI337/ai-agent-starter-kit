from __future__ import annotations

import asyncio
import sqlite3

from app.agent import HeadAgent
from app.config import settings
from app.orchestrator.step_executors import PlannerStepExecutor, SynthesizeStepExecutor, ToolStepExecutor


def test_session_distillation_persists_episodic_and_semantic(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    monkeypatch.setattr(settings, "long_term_memory_enabled", True)
    monkeypatch.setattr(settings, "session_distillation_enabled", True)
    monkeypatch.setattr(settings, "failure_journal_enabled", True)
    monkeypatch.setattr(settings, "reflection_enabled", False)
    monkeypatch.setattr(settings, "long_term_memory_db_path", str(db_path))

    agent = HeadAgent(name="session-distillation-test-agent")

    async def fake_plan_execute(payload, model=None):
        _ = (payload, model)
        return "1) inspect\n2) apply"

    async def fake_tool_execute(
        payload,
        session_id,
        request_id,
        send_event,
        model,
        allowed_tools,
        should_steer_interrupt=None,
    ):
        _ = (payload, session_id, request_id, send_event, model, allowed_tools, should_steer_interrupt)
        return "[write_file]\nupdated backend/app/example.py"

    async def fake_synthesize_execute(payload, session_id, request_id, send_event, model=None):
        _ = (payload, session_id, request_id, send_event, model)
        return "Implemented the requested change successfully."

    async def fake_complete_chat(system_prompt, user_message, model=None, temperature=0.1):
        _ = (system_prompt, user_message, model, temperature)
        return (
            '{"summary":"Implemented requested feature and validated outcome.",'
            '"key_facts":[{"key":"user.prefers.concise","value":"true"}],'
            '"tags":["feature","validation"]}'
        )

    monkeypatch.setattr(agent, "plan_step_executor", PlannerStepExecutor(execute_fn=fake_plan_execute))
    monkeypatch.setattr(agent, "tool_step_executor", ToolStepExecutor(execute_fn=fake_tool_execute))
    monkeypatch.setattr(agent, "synthesize_step_executor", SynthesizeStepExecutor(execute_fn=fake_synthesize_execute))
    monkeypatch.setattr(agent.tools, "check_toolchain", lambda: (True, {"ok": True}))
    monkeypatch.setattr(agent.client, "complete_chat", fake_complete_chat)

    async def send_event(_: dict) -> None:
        return None

    result = asyncio.run(
        agent.run(
            user_message="please implement and verify",
            send_event=send_event,
            session_id="sess-distill-1",
            request_id="req-distill-1",
        )
    )
    assert "Implemented the requested change successfully." in result

    with sqlite3.connect(str(db_path)) as connection:
        episodic_row = connection.execute(
            """
            SELECT session_id, summary, outcome, tags
            FROM episodic
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            ("sess-distill-1",),
        ).fetchone()

        semantic_row = connection.execute(
            """
            SELECT key, value, confidence, source_sessions
            FROM semantic
            WHERE key = ?
            """,
            ("user.prefers.concise",),
        ).fetchone()

    assert episodic_row is not None
    assert episodic_row[0] == "sess-distill-1"
    assert "Implemented requested feature" in str(episodic_row[1])
    assert episodic_row[2] == "success"
    assert "feature" in str(episodic_row[3])

    assert semantic_row is not None
    assert semantic_row[0] == "user.prefers.concise"
    assert semantic_row[1] == "true"
    assert float(semantic_row[2]) == 0.7
    assert "sess-distill-1" in str(semantic_row[3])
