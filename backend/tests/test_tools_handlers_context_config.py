from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.transport.routers import tools as tools_handlers


class _StateStore:
    def __init__(self) -> None:
        self._runs = {
            "run-1": {
                "run_id": "run-1",
                "session_id": "s1",
                "status": "completed",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:01Z",
                "input": {"user_message": "hello"},
                "events": [
                    {"type": "lifecycle", "stage": "memory_updated", "details": {"memory_chars": 120}},
                    {"type": "lifecycle", "stage": "planning_completed", "details": {"plan_chars": 80}},
                    {"type": "lifecycle", "stage": "tool_completed", "details": {"result_chars": 40}},
                    {"type": "lifecycle", "stage": "run_completed", "details": {"response_chars": 60}},
                ],
            },
            "run-2": {
                "run_id": "run-2",
                "session_id": "s2",
                "status": "completed",
                "created_at": "2026-01-01T00:01:00Z",
                "updated_at": "2026-01-01T00:01:01Z",
                "input": {"user_message": "build feature"},
                "events": [
                    {
                        "type": "lifecycle",
                        "stage": "context_segmented",
                        "details": {
                            "phase": "planning",
                            "used_tokens": 120,
                            "segments": {
                                "user_payload": {"tokens_est": 10, "chars": 40, "share_pct": 8.33},
                                "memory": {"tokens_est": 30, "chars": 120, "share_pct": 25.0},
                                "rendered_prompt": {"tokens_est": 120, "chars": 480, "share_pct": 100.0},
                            },
                        },
                    },
                    {
                        "type": "lifecycle",
                        "stage": "context_segmented",
                        "details": {
                            "phase": "synthesis",
                            "used_tokens": 200,
                            "segments": {
                                "user_payload": {"tokens_est": 12, "chars": 50, "share_pct": 6.0},
                                "memory": {"tokens_est": 50, "chars": 200, "share_pct": 25.0},
                                "tool_results": {"tokens_est": 70, "chars": 280, "share_pct": 35.0},
                                "rendered_prompt": {"tokens_est": 200, "chars": 800, "share_pct": 100.0},
                            },
                        },
                    },
                ],
            },
        }

    def list_runs(self, limit: int = 50):
        _ = limit
        return list(self._runs.values())

    def get_run(self, run_id: str):
        return self._runs.get(run_id)


def _configure() -> None:
    tools_handlers.configure(
        tools_handlers.ToolsHandlerDependencies(
            sync_custom_agents=lambda: None,
            normalize_agent_id=lambda value: (value or "head-agent"),
            resolve_agent=lambda value: (value or "head-agent", SimpleNamespace(role="head-agent"), object()),
            effective_orchestrator_agent_ids=lambda: {"head-agent"},
            agent_registry={"head-agent": SimpleNamespace(role="head-agent")},
            state_store=_StateStore(),
        )
    )


def test_api_control_context_list_returns_items() -> None:
    _configure()
    payload = tools_handlers.api_control_context_list({"limit": 10})
    assert payload["schema"] == "context.list.v1"
    assert payload["count"] == 2
    assert payload["items"][0]["run_id"] == "run-1"
    assert "segment_source" in payload["items"][0]
    assert "degraded_estimation" in payload["items"][0]
    assert "phase_breakdown" in payload["items"][0]


def test_api_control_context_detail_returns_segments() -> None:
    _configure()
    payload = tools_handlers.api_control_context_detail({"run_id": "run-1"})
    assert payload["schema"] == "context.detail.v1"
    assert payload["run_id"] == "run-1"
    assert payload["segments"]["memory"]["tokens_est"] > 0
    assert payload["segment_source"] == "fallback"
    assert payload["degraded_estimation"] is True


def test_api_control_context_detail_prefers_segmented_events() -> None:
    _configure()
    payload = tools_handlers.api_control_context_detail({"run_id": "run-2"})
    assert payload["segment_source"] == "event"
    assert payload["degraded_estimation"] is False
    assert payload["segments"]["tool_results"]["tokens_est"] == 70
    assert payload["phase_breakdown"]["planning"]["tokens_est"] == 120
    assert payload["phase_breakdown"]["synthesis"]["tokens_est"] == 200


def test_api_control_context_detail_missing_run_raises_404() -> None:
    _configure()
    with pytest.raises(HTTPException) as exc:
        tools_handlers.api_control_context_detail({"run_id": "missing"})
    assert exc.value.status_code == 404


def test_api_control_config_health_includes_schema_and_risks() -> None:
    _configure()
    payload = tools_handlers.api_control_config_health({"include_effective_values": False})
    assert payload["schema"] == "config.health.v1"
    assert "risk_flags" in payload
    assert "validation_status" in payload
    assert "strict_unknown_keys_enabled" in payload
    assert "unknown_key_count" in payload
    assert isinstance(payload["invalid_or_unknown"], list)
    assert "isolation_allowlist_wildcard" in payload["risk_flags"]
    assert "isolation_allowlist_excessive" in payload["risk_flags"]
    assert "isolation_allowlist_pair_count" in payload["risk_flags"]


def test_api_control_memory_overview_includes_long_term_sections(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure()

    memory_dir = tmp_path / "memory_store"
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_file = memory_dir / "sess-a.jsonl"
    memory_file.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "build memory view"}),
                json.dumps({"role": "plan", "content": "add api and frontend page"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "long_term.db"
    connection = sqlite3.connect(str(db_path))
    with connection:
        connection.execute(
            "CREATE TABLE episodic (id TEXT PRIMARY KEY, session_id TEXT, timestamp TEXT, summary TEXT, key_actions TEXT, outcome TEXT, tags TEXT)"
        )
        connection.execute(
            "CREATE TABLE semantic (key TEXT PRIMARY KEY, value TEXT, confidence REAL, source_sessions TEXT, last_updated TEXT)"
        )
        connection.execute(
            "CREATE TABLE failure_journal (id TEXT PRIMARY KEY, timestamp TEXT, task_description TEXT, error_type TEXT, root_cause TEXT, solution TEXT, prevention TEXT, tags TEXT)"
        )
        connection.execute(
            "INSERT INTO episodic (id, session_id, timestamp, summary, key_actions, outcome, tags) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("e1", "sess-a", "2026-03-04T00:00:00Z", "Built memory page", "api,ui", "success", "memory,ui"),
        )
        connection.execute(
            "INSERT INTO semantic (key, value, confidence, source_sessions, last_updated) VALUES (?, ?, ?, ?, ?)",
            ("user.pref.stack", "python+angular", 0.8, "sess-a", "2026-03-04T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO failure_journal (id, timestamp, task_description, error_type, root_cause, solution, prevention, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "f1",
                "2026-03-04T00:01:00Z",
                "memory api failed",
                "tool_error",
                "missing route",
                "add router wiring",
                "add unit test",
                "memory,backend",
            ),
        )
    connection.close()

    monkeypatch.setattr(tools_handlers.settings, "memory_persist_dir", str(memory_dir))
    monkeypatch.setattr(tools_handlers.settings, "long_term_memory_db_path", str(db_path))

    payload = tools_handlers.api_control_memory_overview({"include_content": True})

    assert payload["schema"] == "memory.overview.v1"
    assert payload["session_count"] == 1
    assert payload["total_entries"] == 2
    assert payload["long_term_db"]["exists"] is True
    assert payload["long_term_memory"]["available"] is True
    assert payload["long_term_memory"]["counts"]["episodic"] == 1
    assert payload["long_term_memory"]["counts"]["semantic"] == 1
    assert payload["long_term_memory"]["counts"]["failure_journal"] == 1
    assert payload["long_term_memory"]["episodic"][0]["summary"] == "Built memory page"
    assert payload["long_term_memory"]["semantic"][0]["key"] == "user.pref.stack"
    assert payload["long_term_memory"]["failure_journal"][0]["id"] == "f1"

    filtered = tools_handlers.api_control_memory_overview({"include_content": True, "search_query": "python+angular"})
    assert filtered["search_query"] == "python+angular"
    assert filtered["long_term_memory"]["counts"]["semantic"] == 1
    assert len(filtered["long_term_memory"]["semantic"]) == 1
    assert filtered["long_term_memory"]["semantic"][0]["key"] == "user.pref.stack"
    assert len(filtered["long_term_memory"]["episodic"]) == 0
    assert len(filtered["long_term_memory"]["failure_journal"]) == 0
