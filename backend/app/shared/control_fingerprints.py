from __future__ import annotations

import json

from app.tools.policy import ToolPolicyDict


def build_run_start_fingerprint(
    *,
    message: str,
    session_id: str | None,
    model: str | None,
    preset: str | None,
    queue_mode: str | None,
    prompt_mode: str | None,
    tool_policy: ToolPolicyDict | None,
    runtime: str,
) -> str:
    payload = {
        "message": message,
        "session_id": session_id,
        "model": model,
        "preset": preset,
        "queue_mode": queue_mode,
        "prompt_mode": prompt_mode,
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
