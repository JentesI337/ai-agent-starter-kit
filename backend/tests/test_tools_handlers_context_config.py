from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.handlers import tools_handlers


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
            }
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
    assert payload["count"] == 1
    assert payload["items"][0]["run_id"] == "run-1"


def test_api_control_context_detail_returns_segments() -> None:
    _configure()
    payload = tools_handlers.api_control_context_detail({"run_id": "run-1"})
    assert payload["schema"] == "context.detail.v1"
    assert payload["run_id"] == "run-1"
    assert payload["segments"]["memory"]["tokens_est"] > 0


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
