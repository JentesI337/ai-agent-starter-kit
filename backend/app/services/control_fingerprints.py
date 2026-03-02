from __future__ import annotations

import json

from app.tool_policy import ToolPolicyDict


def build_run_start_fingerprint(
    *,
    message: str,
    session_id: str | None,
    model: str | None,
    preset: str | None,
    tool_policy: ToolPolicyDict | None,
    runtime: str,
) -> str:
    payload = {
        "message": message,
        "session_id": session_id,
        "model": model,
        "preset": preset,
        "tool_policy": tool_policy,
        "runtime": runtime,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_session_patch_fingerprint(*, session_id: str, meta: dict[str, object]) -> str:
    payload = {
        "session_id": session_id,
        "meta": meta,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_session_reset_fingerprint(*, session_id: str) -> str:
    payload = {
        "session_id": session_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_workflow_create_fingerprint(
    *,
    operation: str,
    workflow_id: str | None,
    name: str,
    description: str,
    base_agent_id: str,
    steps: list[str],
    tool_policy: ToolPolicyDict | None,
    allow_subrun_delegation: bool,
) -> str:
    payload = {
        "operation": operation,
        "id": workflow_id,
        "name": name,
        "description": description,
        "base_agent_id": base_agent_id,
        "steps": steps,
        "tool_policy": tool_policy,
        "allow_subrun_delegation": allow_subrun_delegation,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_workflow_execute_fingerprint(
    *,
    workflow_id: str,
    message: str,
    session_id: str | None,
    model: str | None,
    preset: str | None,
    tool_policy: ToolPolicyDict | None,
    allow_subrun_delegation: bool,
    runtime: str,
) -> str:
    payload = {
        "operation": "execute",
        "workflow_id": workflow_id,
        "message": message,
        "session_id": session_id,
        "model": model,
        "preset": preset,
        "tool_policy": tool_policy,
        "allow_subrun_delegation": allow_subrun_delegation,
        "runtime": runtime,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_workflow_delete_fingerprint(*, workflow_id: str) -> str:
    payload = {
        "operation": "delete",
        "workflow_id": workflow_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
