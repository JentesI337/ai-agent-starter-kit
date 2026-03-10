from __future__ import annotations

import asyncio
import sqlite3

from app.agent import HeadAgent
from app.config import settings


def test_session_distillation_persists_episodic_and_semantic(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "long_term.db"
    monkeypatch.setattr(settings, "long_term_memory_enabled", True)
    monkeypatch.setattr(settings, "session_distillation_enabled", True)
    monkeypatch.setattr(settings, "failure_journal_enabled", True)
    monkeypatch.setattr(settings, "reflection_enabled", False)
    monkeypatch.setattr(settings, "long_term_memory_db_path", str(db_path))

    agent = HeadAgent(name="session-distillation-test-agent")

    final_text = "Implemented the requested change successfully."

    async def fake_runner_run(**kwargs):
        # Trigger distillation like AgentRunner would
        await agent._distill_session_knowledge(
            session_id=kwargs["session_id"],
            user_message=kwargs["user_message"],
            plan_text="1) Use read_file to inspect the current code\n2) Use write_file to apply the requested changes",
            tool_results="[write_file]\nupdated backend/app/example.py",
            final_text=final_text,
            model=kwargs.get("model"),
        )
        return final_text

    async def fake_complete_chat(system_prompt, user_message, model=None, temperature=0.1):
        _ = (system_prompt, user_message, model, temperature)
        return (
            '{"summary":"Implemented requested feature and validated outcome.",'
            '"key_facts":[{"key":"user.prefers.concise","value":"true"}],'
            '"tags":["feature","validation"]}'
        )

    monkeypatch.setattr(agent._agent_runner, "run", fake_runner_run)
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
    # Confidence is now dynamic based on tool success rate (0.5-0.9 range)
    assert 0.5 <= float(semantic_row[2]) <= 0.9
    assert "sess-distill-1" in str(semantic_row[3])
