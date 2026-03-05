from __future__ import annotations

from app.services.tool_call_gatekeeper import ToolCallGatekeeper
from app.services.tool_call_gatekeeper import collect_policy_override_candidates
from app.services.tool_call_gatekeeper import prepare_action_for_execution


def _identity(tool_name: str) -> str:
    return tool_name


def test_collect_policy_override_candidates_detects_and_deduplicates() -> None:
    actions = [
        {"tool": "run_command", "args": {"command": "pytest -q"}},
        {"tool": "run_command", "args": {"command": "pytest -q"}},
        {"tool": "spawn_subrun", "args": {"message": "analyze repo"}},
    ]

    candidates = collect_policy_override_candidates(
        actions=actions,
        allowed_tools=set(),
        normalize_tool_name=_identity,
    )

    assert [(candidate.tool, candidate.resource) for candidate in candidates] == [
        ("run_command", "pytest -q"),
        ("spawn_subrun", "analyze repo"),
    ]


def test_collect_policy_override_candidates_skips_allowed_and_invalid_actions() -> None:
    actions = [
        {"tool": "run_command", "args": {"command": "pytest -q"}},
        {"tool": "spawn_subrun", "args": "invalid"},
        {"tool": "read_file", "args": {"path": "README.md"}},
        {"tool": 123, "args": {}},
    ]

    candidates = collect_policy_override_candidates(
        actions=actions,
        allowed_tools={"run_command"},
        normalize_tool_name=_identity,
    )

    assert candidates == []


def test_collect_policy_override_candidates_handles_code_execute_and_custom_process_set() -> None:
    actions = [
        {"tool": "code_execute", "args": {"code": "print('x')\nprint('y')", "language": "python"}},
        {"tool": "run_command", "args": {"command": "pytest -q"}},
    ]

    candidates = collect_policy_override_candidates(
        actions=actions,
        allowed_tools=set(),
        normalize_tool_name=_identity,
        process_tools={"code_execute"},
    )

    assert len(candidates) == 1
    assert candidates[0].tool == "code_execute"
    assert candidates[0].resource.startswith("python: print('x')")


def test_prepare_action_for_execution_rejects_invalid_payload() -> None:
    result = prepare_action_for_execution(
        action={},
        allowed_tools={"read_file"},
        normalize_tool_name=_identity,
        evaluate_action=lambda tool, args, allowed: ({}, "invalid"),
    )

    assert result.tool == ""
    assert result.normalized_args == {}
    assert result.error == "invalid"


def test_prepare_action_for_execution_normalizes_tool_and_args() -> None:
    result = prepare_action_for_execution(
        action={"tool": "read_file", "args": {"path": "README.md"}},
        allowed_tools={"read_file"},
        normalize_tool_name=_identity,
        evaluate_action=lambda tool, args, allowed: (dict(args), None),
    )

    assert result.tool == "read_file"
    assert result.normalized_args == {"path": "README.md"}
    assert result.error is None


def test_prepare_action_for_execution_invalid_action_type() -> None:
    result = prepare_action_for_execution(
        action="not-a-dict",  # type: ignore[arg-type]
        allowed_tools={"read_file"},
        normalize_tool_name=_identity,
        evaluate_action=lambda tool, args, allowed: (args, None),
    )

    assert result.error == "invalid action payload"


def test_generic_repeat_warns_then_blocks() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=3,
        circuit_breaker_threshold=6,
        warning_bucket_size=10,
        generic_repeat_enabled=True,
        ping_pong_enabled=False,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=3,
    )
    signature = gatekeeper.build_signature(tool="read_file", args={"path": "README.md"})

    first = gatekeeper.before_tool_call(tool="read_file", signature=signature, index=1)
    second = gatekeeper.before_tool_call(tool="read_file", signature=signature, index=2)
    third = gatekeeper.before_tool_call(tool="read_file", signature=signature, index=3)

    assert first.blocked is False
    assert any(stage == "tool_loop_warn" for stage, _ in second.lifecycle_events)
    assert third.blocked is True
    assert any(stage == "tool_loop_blocked" for stage, _ in third.lifecycle_events)


def test_generic_repeat_warning_bucket_progression() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=50,
        circuit_breaker_threshold=60,
        warning_bucket_size=2,
        generic_repeat_enabled=True,
        ping_pong_enabled=False,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=3,
    )
    signature = gatekeeper.build_signature(tool="read_file", args={"path": "README.md"})

    events = []
    for idx in range(1, 6):
        decision = gatekeeper.before_tool_call(tool="read_file", signature=signature, index=idx)
        events.extend(decision.lifecycle_events)

    warn_events = [event for event in events if event[0] == "tool_loop_warn"]
    buckets = [int(details.get("warning_bucket_index", 0)) for _, details in warn_events]
    assert buckets == [1, 2]


def test_ping_pong_blocks_with_no_progress_evidence() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=3,
        circuit_breaker_threshold=6,
        warning_bucket_size=10,
        generic_repeat_enabled=False,
        ping_pong_enabled=True,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=3,
    )
    signature_a = gatekeeper.build_signature(tool="read_file", args={"path": "a.txt"})
    signature_b = gatekeeper.build_signature(tool="read_file", args={"path": "b.txt"})

    gatekeeper.after_tool_success(tool="read_file", signature=signature_a, index=1, result="A")
    gatekeeper.after_tool_success(tool="read_file", signature=signature_b, index=2, result="B")
    gatekeeper.after_tool_success(tool="read_file", signature=signature_a, index=3, result="A")

    decision = gatekeeper.before_tool_call(tool="read_file", signature=signature_b, index=4)

    assert decision.blocked is True
    assert any(stage == "tool_loop_ping_pong_blocked" for stage, _ in decision.lifecycle_events)


def test_ping_pong_not_blocked_without_no_progress_evidence() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=3,
        circuit_breaker_threshold=6,
        warning_bucket_size=10,
        generic_repeat_enabled=False,
        ping_pong_enabled=True,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=3,
    )
    signature_a = gatekeeper.build_signature(tool="read_file", args={"path": "a.txt"})
    signature_b = gatekeeper.build_signature(tool="read_file", args={"path": "b.txt"})

    gatekeeper.after_tool_success(tool="read_file", signature=signature_a, index=1, result="A-1")
    gatekeeper.after_tool_success(tool="read_file", signature=signature_b, index=2, result="B-1")
    gatekeeper.after_tool_success(tool="read_file", signature=signature_a, index=3, result="A-2")

    decision = gatekeeper.before_tool_call(tool="read_file", signature=signature_b, index=4)

    assert decision.blocked is False


def test_poll_no_progress_blocks_after_threshold() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=5,
        circuit_breaker_threshold=8,
        warning_bucket_size=10,
        generic_repeat_enabled=False,
        ping_pong_enabled=False,
        poll_no_progress_enabled=True,
        poll_no_progress_threshold=3,
    )
    signature = gatekeeper.build_signature(tool="web_fetch", args={"url": "https://example.com"})

    first = gatekeeper.after_tool_success(tool="web_fetch", signature=signature, index=1, result="same")
    second = gatekeeper.after_tool_success(tool="web_fetch", signature=signature, index=2, result="same")
    third = gatekeeper.after_tool_success(tool="web_fetch", signature=signature, index=3, result="same")

    assert first.blocked is False
    assert second.blocked is False
    assert third.blocked is True
    assert third.break_run is True
    assert any(stage == "tool_loop_poll_no_progress_blocked" for stage, _ in third.lifecycle_events)


def test_summary_payload_contains_reason_counts() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=3,
        circuit_breaker_threshold=6,
        warning_bucket_size=10,
        generic_repeat_enabled=True,
        ping_pong_enabled=False,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=3,
    )
    signature = gatekeeper.build_signature(tool="read_file", args={"path": "README.md"})
    gatekeeper.before_tool_call(tool="read_file", signature=signature, index=1)
    gatekeeper.before_tool_call(tool="read_file", signature=signature, index=2)
    gatekeeper.before_tool_call(tool="read_file", signature=signature, index=3)

    payload = gatekeeper.summary_payload()

    assert payload["loop_blocked"] == 1
    assert payload["loop_reason_counts"]["generic_repeat"] == 1
    assert payload["loop_detector_ping_pong_enabled"] is False


def test_summary_payload_reason_counts_never_negative() -> None:
    gatekeeper = ToolCallGatekeeper(
        warn_threshold=2,
        critical_threshold=3,
        circuit_breaker_threshold=6,
        warning_bucket_size=10,
        generic_repeat_enabled=False,
        ping_pong_enabled=True,
        poll_no_progress_enabled=False,
        poll_no_progress_threshold=3,
    )
    signature_a = gatekeeper.build_signature(tool="read_file", args={"path": "a.txt"})
    signature_b = gatekeeper.build_signature(tool="read_file", args={"path": "b.txt"})
    gatekeeper.after_tool_success(tool="read_file", signature=signature_a, index=1, result="A")
    gatekeeper.after_tool_success(tool="read_file", signature=signature_b, index=2, result="B")
    gatekeeper.after_tool_success(tool="read_file", signature=signature_a, index=3, result="A")
    gatekeeper.before_tool_call(tool="read_file", signature=signature_b, index=4)

    payload = gatekeeper.summary_payload()

    assert payload["loop_blocked"] == 1
    assert payload["loop_reason_counts"]["generic_repeat"] == 0
