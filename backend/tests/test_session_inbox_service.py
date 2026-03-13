from __future__ import annotations

import time

import pytest

from app.errors import GuardrailViolation
from app.reasoning.request_normalization import normalize_prompt_mode, normalize_queue_mode
from app.session.inbox_service import SessionInboxService


def test_session_inbox_enqueue_dequeue_fifo() -> None:
    inbox = SessionInboxService(max_queue_length=5, ttl_seconds=60)
    inbox.enqueue("s1", "r1", "first")
    inbox.enqueue("s1", "r2", "second")

    first = inbox.dequeue("s1")
    second = inbox.dequeue("s1")

    assert first is not None
    assert second is not None
    assert first.run_id == "r1"
    assert second.run_id == "r2"
    assert inbox.dequeue("s1") is None


def test_session_inbox_overflow_raises() -> None:
    inbox = SessionInboxService(max_queue_length=1, ttl_seconds=60)
    inbox.enqueue("s1", "r1", "only")

    with pytest.raises(OverflowError):
        inbox.enqueue("s1", "r2", "overflow")


def test_session_inbox_peek_newer_than_filters_run() -> None:
    inbox = SessionInboxService(max_queue_length=5, ttl_seconds=60)
    inbox.enqueue("s1", "r1", "one")
    inbox.enqueue("s1", "r2", "two")

    newer = inbox.peek_newer_than("s1", "r1")
    assert len(newer) == 1
    assert newer[0].run_id == "r2"


def test_session_inbox_ttl_purges_expired() -> None:
    inbox = SessionInboxService(max_queue_length=5, ttl_seconds=1)
    inbox.enqueue("s1", "r1", "old")
    time.sleep(1.05)

    assert inbox.size("s1") == 0
    assert inbox.dequeue("s1") is None


def test_session_inbox_dequeue_prioritized_defers_follow_up() -> None:
    inbox = SessionInboxService(max_queue_length=5, ttl_seconds=60)
    inbox.enqueue("s1", "r-follow", "follow", meta={"queue_mode": "follow_up"})
    inbox.enqueue("s1", "r-wait", "wait", meta={"queue_mode": "wait"})

    first, deferred = inbox.dequeue_prioritized("s1", force_follow_up=False)
    assert first is not None
    assert first.run_id == "r-wait"
    assert deferred is True

    second, deferred_second = inbox.dequeue_prioritized("s1", force_follow_up=True)
    assert second is not None
    assert second.run_id == "r-follow"
    assert deferred_second is False


def test_normalize_queue_mode_accepts_supported_values() -> None:
    assert normalize_queue_mode("wait") == "wait"
    assert normalize_queue_mode("follow_up") == "follow_up"
    assert normalize_queue_mode("steer") == "steer"


def test_normalize_queue_mode_uses_default_when_empty() -> None:
    assert normalize_queue_mode(None, default="follow_up") == "follow_up"


def test_normalize_queue_mode_rejects_unknown_value() -> None:
    with pytest.raises(GuardrailViolation):
        normalize_queue_mode("invalid-mode")


def test_normalize_prompt_mode_accepts_supported_values() -> None:
    assert normalize_prompt_mode("full") == "full"
    assert normalize_prompt_mode("minimal") == "minimal"
    assert normalize_prompt_mode("subagent") == "subagent"


def test_normalize_prompt_mode_uses_default_when_empty() -> None:
    assert normalize_prompt_mode(None, default="minimal") == "minimal"


def test_normalize_prompt_mode_rejects_unknown_value() -> None:
    with pytest.raises(GuardrailViolation):
        normalize_prompt_mode("invalid-mode")
