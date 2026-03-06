from __future__ import annotations

from app.services.control_fingerprints import (
    build_run_start_fingerprint,
    build_workflow_execute_fingerprint,
)


def test_build_run_start_fingerprint_includes_queue_mode() -> None:
    base = {
        "message": "hello",
        "session_id": "s1",
        "model": "m1",
        "preset": "default",
        "prompt_mode": "full",
        "tool_policy": {"allow": ["read_file"]},
        "runtime": "api",
    }

    fingerprint_wait = build_run_start_fingerprint(queue_mode="wait", **base)
    fingerprint_steer = build_run_start_fingerprint(queue_mode="steer", **base)

    assert fingerprint_wait != fingerprint_steer


def test_build_workflow_execute_fingerprint_includes_queue_mode() -> None:
    base = {
        "workflow_id": "wf-1",
        "message": "run workflow",
        "session_id": "s1",
        "model": "m1",
        "preset": "default",
        "prompt_mode": "minimal",
        "tool_policy": {"allow": ["read_file"]},
        "allow_subrun_delegation": False,
        "runtime": "api",
    }

    fingerprint_wait = build_workflow_execute_fingerprint(queue_mode="wait", **base)
    fingerprint_follow_up = build_workflow_execute_fingerprint(queue_mode="follow_up", **base)

    assert fingerprint_wait != fingerprint_follow_up
