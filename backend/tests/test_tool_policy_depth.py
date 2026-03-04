from __future__ import annotations

from app.config import settings
from app.services.tool_policy_service import resolve_tool_policy


def test_agent_depth_policy_blocks_spawn_subrun_for_deep_runs() -> None:
    resolved = resolve_tool_policy(
        request_policy={"allow": ["spawn_subrun", "read_file"]},
        agent_id="head-agent",
        depth=2,
    )

    merged = resolved.get("merged_policy") or {}
    deny_values = set(merged.get("deny") or [])
    assert "spawn_subrun" in deny_values


def test_agent_depth_policy_blocks_spawn_subrun_for_non_orchestrator_agent() -> None:
    resolved = resolve_tool_policy(
        request_policy={"allow": ["spawn_subrun", "read_file"]},
        agent_id="coder-agent",
        depth=1,
    )

    merged = resolved.get("merged_policy") or {}
    deny_values = set(merged.get("deny") or [])
    assert "spawn_subrun" in deny_values


def test_agent_depth_policy_keeps_spawn_subrun_available_for_head_agent_depth_zero() -> None:
    resolved = resolve_tool_policy(
        request_policy={"allow": ["spawn_subrun", "read_file"]},
        agent_id="head-agent",
        depth=0,
    )

    merged = resolved.get("merged_policy") or {}
    deny_values = set(merged.get("deny") or [])
    assert "spawn_subrun" not in deny_values


def test_global_policy_layer_is_included_in_merged_policy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "agent_tools_allow", ["read_file"])
    monkeypatch.setattr(settings, "agent_tools_deny", ["run_command"])

    resolved = resolve_tool_policy(request_policy=None)
    merged = resolved.get("merged_policy") or {}

    assert "read_file" in set(merged.get("allow") or [])
    assert "run_command" in set(merged.get("deny") or [])


def test_review_preset_blocks_http_request_by_default() -> None:
    resolved = resolve_tool_policy(preset="review")

    merged = resolved.get("merged_policy") or {}
    deny_values = set(merged.get("deny") or [])
    assert "http_request" in deny_values


def test_research_preset_allows_web_search() -> None:
    resolved = resolve_tool_policy(preset="research")

    merged = resolved.get("merged_policy") or {}
    allow_values = set(merged.get("allow") or [])
    assert "web_search" in allow_values


def test_minimal_profile_allows_web_search() -> None:
    resolved = resolve_tool_policy(profile="minimal")

    merged = resolved.get("merged_policy") or {}
    allow_values = set(merged.get("allow") or [])
    assert "web_search" in allow_values
