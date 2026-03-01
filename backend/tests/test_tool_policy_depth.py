from __future__ import annotations

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
