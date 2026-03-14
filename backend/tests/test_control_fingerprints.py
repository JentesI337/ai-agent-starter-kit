from __future__ import annotations

from app.shared.control_fingerprints import (
    build_run_start_fingerprint,
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
