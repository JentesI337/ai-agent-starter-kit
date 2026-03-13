"""Comprehensive tests for T2.2: CircuitBreakerRegistry."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from app.policy.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitStateTransition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry(
    *,
    failure_threshold: int = 3,
    failure_window_seconds: int = 60,
    recovery_timeout_seconds: int = 10,
    success_threshold: int = 2,
) -> CircuitBreakerRegistry:
    return CircuitBreakerRegistry(
        config=CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            failure_window_seconds=failure_window_seconds,
            recovery_timeout_seconds=recovery_timeout_seconds,
            success_threshold=success_threshold,
        )
    )


async def _trip_breaker(reg: CircuitBreakerRegistry, model: str, failures: int = 3) -> None:
    for _ in range(failures):
        await reg.record_failure(model)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_unknown_model_defaults_to_closed() -> None:
    reg = _registry()
    assert reg.get_state("new-model") == CircuitState.CLOSED


def test_allow_request_for_new_model() -> None:
    allowed, transition = asyncio.run(_registry().allow_request("new-model"))
    assert allowed is True
    assert transition is None


# ---------------------------------------------------------------------------
# CLOSED → OPEN transition
# ---------------------------------------------------------------------------

def test_trips_after_threshold_failures() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=3)
        for _i in range(2):
            await reg.record_failure("m1")
            assert reg.get_state("m1") == CircuitState.CLOSED
        await reg.record_failure("m1")
        assert reg.get_state("m1") == CircuitState.OPEN
    asyncio.run(_run())


def test_blocks_requests_when_open() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2)
        await _trip_breaker(reg, "m1", 2)
        allowed, transition = await reg.allow_request("m1")
        assert allowed is False
        assert transition is None
    asyncio.run(_run())


def test_failures_outside_window_do_not_trip() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=3, failure_window_seconds=5)
        now = time.monotonic()
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=now - 10):
            await reg.record_failure("m1")
            await reg.record_failure("m1")
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=now):
            await reg.record_failure("m1")  # evicts old ones
            await reg.record_failure("m1")  # 2 within window, < 3
        assert reg.get_state("m1") == CircuitState.CLOSED
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN transition
# ---------------------------------------------------------------------------

def test_transitions_after_recovery_timeout() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=5)
        await _trip_breaker(reg, "m1", 2)
        assert reg.get_state("m1") == CircuitState.OPEN
        real_mono = time.monotonic
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=real_mono() + 10):
            assert reg.get_state("m1") == CircuitState.HALF_OPEN
            allowed, transition = await reg.allow_request("m1")
            assert allowed is True
            assert transition is not None
            assert transition.from_state == CircuitState.OPEN
            assert transition.to_state == CircuitState.HALF_OPEN
    asyncio.run(_run())


def test_stays_open_before_recovery_timeout() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=999)
        await _trip_breaker(reg, "m1", 2)
        assert reg.get_state("m1") == CircuitState.OPEN
        allowed, transition = await reg.allow_request("m1")
        assert allowed is False
        assert transition is None
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# HALF_OPEN → CLOSED transition
# ---------------------------------------------------------------------------

def test_closes_after_success_threshold() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=0, success_threshold=2)
        await _trip_breaker(reg, "m1", 2)
        allowed, _ = await reg.allow_request("m1")  # probe
        assert allowed is True
        tx = await reg.record_success("m1")
        assert tx is None  # not yet at threshold
        allowed2, _ = await reg.allow_request("m1")
        assert allowed2 is True
        tx2 = await reg.record_success("m1")
        assert tx2 is not None
        assert tx2.from_state == CircuitState.HALF_OPEN
        assert tx2.to_state == CircuitState.CLOSED
        assert reg.get_state("m1") == CircuitState.CLOSED
    asyncio.run(_run())


def test_requests_allowed_after_close() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=0, success_threshold=1)
        await _trip_breaker(reg, "m1", 2)
        allowed, _ = await reg.allow_request("m1")
        assert allowed is True
        await reg.record_success("m1")
        assert reg.get_state("m1") == CircuitState.CLOSED
        allowed2, _ = await reg.allow_request("m1")
        assert allowed2 is True
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# HALF_OPEN → OPEN transition (failure during probing)
# ---------------------------------------------------------------------------

def test_failure_during_probe_reopens() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=999, success_threshold=3)
        await _trip_breaker(reg, "m1", 2)
        assert reg.get_state("m1") == CircuitState.OPEN
        # Fast-forward past recovery timeout to get into HALF_OPEN
        real_mono = time.monotonic
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=real_mono() + 1000):
            allowed, _ = await reg.allow_request("m1")  # probe
            assert allowed is True
            tx = await reg.record_failure("m1")  # any failure → OPEN
            assert tx is not None
            assert tx.from_state == CircuitState.HALF_OPEN
            assert tx.to_state == CircuitState.OPEN
            assert reg.get_state("m1") == CircuitState.OPEN
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# HALF_OPEN: only one probe at a time
# ---------------------------------------------------------------------------

def test_blocks_second_concurrent_probe() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=0)
        await _trip_breaker(reg, "m1", 2)
        allowed1, _ = await reg.allow_request("m1")
        assert allowed1 is True
        allowed2, _ = await reg.allow_request("m1")
        assert allowed2 is False
    asyncio.run(_run())


def test_probe_released_after_success() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=0, success_threshold=3)
        await _trip_breaker(reg, "m1", 2)
        allowed1, _ = await reg.allow_request("m1")
        assert allowed1 is True
        await reg.record_success("m1")
        allowed2, _ = await reg.allow_request("m1")
        assert allowed2 is True
    asyncio.run(_run())


def test_probe_released_after_failure() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=999)
        await _trip_breaker(reg, "m1", 2)
        real_mono = time.monotonic
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=real_mono() + 1000):
            allowed, _ = await reg.allow_request("m1")  # half-open probe
            assert allowed is True
            await reg.record_failure("m1")  # → OPEN
            assert reg.get_state("m1") == CircuitState.OPEN
    asyncio.run(_run())


def test_release_probe_frees_half_open_slot_without_state_change() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=0, success_threshold=3)
        await _trip_breaker(reg, "m1", 2)
        allowed1, _ = await reg.allow_request("m1")
        assert allowed1 is True
        assert reg.get_state("m1") == CircuitState.HALF_OPEN

        await reg.release_probe("m1")

        assert reg.get_state("m1") == CircuitState.HALF_OPEN
        allowed2, transition2 = await reg.allow_request("m1")
        assert allowed2 is True
        assert transition2 is None
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Failure window eviction
# ---------------------------------------------------------------------------

def test_old_failures_evicted_beyond_window() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=3, failure_window_seconds=10)
        now = time.monotonic()
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=now - 20):
            await reg.record_failure("m1")
            await reg.record_failure("m1")
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=now):
            await reg.record_failure("m1")
            await reg.record_failure("m1")
        assert reg.get_state("m1") == CircuitState.CLOSED
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Reset (admin/debug operation)
# ---------------------------------------------------------------------------

def test_reset_closes_open_circuit() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2)
        await _trip_breaker(reg, "m1", 2)
        assert reg.get_state("m1") == CircuitState.OPEN
        await reg.reset("m1")
        assert reg.get_state("m1") == CircuitState.CLOSED
        allowed, _ = await reg.allow_request("m1")
        assert allowed is True
    asyncio.run(_run())


def test_reset_on_unknown_model_doesnt_error() -> None:
    async def _run() -> None:
        reg = _registry()
        await reg.reset("unknown-model")
        assert reg.get_state("unknown-model") == CircuitState.CLOSED
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# all_states diagnostic
# ---------------------------------------------------------------------------

def test_lists_all_tracked_models() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2)
        await reg.allow_request("m1")
        await _trip_breaker(reg, "m2", 2)
        states = reg.all_states()
        assert "m1" in states
        assert "m2" in states
        assert states["m1"] == "closed"
        assert states["m2"] == "open"
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Model isolation
# ---------------------------------------------------------------------------

def test_tripping_one_model_does_not_affect_another() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=2)
        await _trip_breaker(reg, "m1", 2)
        assert reg.get_state("m1") == CircuitState.OPEN
        assert reg.get_state("m2") == CircuitState.CLOSED
        allowed, _ = await reg.allow_request("m2")
        assert allowed is True
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Async safety
# ---------------------------------------------------------------------------

def test_concurrent_operations_do_not_corrupt() -> None:
    async def _run() -> None:
        reg = _registry(failure_threshold=100, failure_window_seconds=600)

        async def _writer(model: str, n: int) -> None:
            for _ in range(n):
                await reg.record_failure(model)
                await reg.record_success(model)

        await asyncio.gather(
            _writer("m1", 50),
            _writer("m2", 50),
            _writer("m1", 50),
        )
        states = reg.all_states()
        assert isinstance(states, dict)
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_default_config_values() -> None:
    cfg = CircuitBreakerConfig()
    assert cfg.failure_threshold == 5
    assert cfg.failure_window_seconds == 60
    assert cfg.recovery_timeout_seconds == 120
    assert cfg.success_threshold == 2


def test_config_is_frozen() -> None:
    cfg = CircuitBreakerConfig()
    with pytest.raises(AttributeError):
        cfg.failure_threshold = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Success in CLOSED is a no-op
# ---------------------------------------------------------------------------

def test_success_in_closed_does_not_change_state() -> None:
    async def _run() -> None:
        reg = _registry()
        tx = await reg.record_success("m1")
        assert tx is None
        assert reg.get_state("m1") == CircuitState.CLOSED
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Transition return values
# ---------------------------------------------------------------------------

def test_record_failure_returns_transition_on_trip() -> None:
    """record_failure returns CircuitStateTransition when CLOSED → OPEN."""
    async def _run() -> None:
        reg = _registry(failure_threshold=2)
        tx1 = await reg.record_failure("m1")
        assert tx1 is None  # not yet tripped
        tx2 = await reg.record_failure("m1")
        assert tx2 is not None
        assert tx2 == CircuitStateTransition(
            model_id="m1",
            from_state=CircuitState.CLOSED,
            to_state=CircuitState.OPEN,
        )
    asyncio.run(_run())


def test_record_failure_returns_none_within_threshold() -> None:
    """record_failure returns None when failures stay below threshold."""
    async def _run() -> None:
        reg = _registry(failure_threshold=5)
        for _ in range(4):
            tx = await reg.record_failure("m1")
            assert tx is None
    asyncio.run(_run())


def test_allow_request_returns_transition_on_open_to_half_open() -> None:
    """allow_request returns transition when OPEN → HALF_OPEN."""
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=1)
        await _trip_breaker(reg, "m1", 2)
        real_mono = time.monotonic
        with patch("app.policy.circuit_breaker.time.monotonic", return_value=real_mono() + 10):
            allowed, tx = await reg.allow_request("m1")
            assert allowed is True
            assert tx is not None
            assert tx == CircuitStateTransition(
                model_id="m1",
                from_state=CircuitState.OPEN,
                to_state=CircuitState.HALF_OPEN,
            )
    asyncio.run(_run())


def test_record_success_returns_transition_on_close() -> None:
    """record_success returns transition when HALF_OPEN → CLOSED."""
    async def _run() -> None:
        reg = _registry(failure_threshold=2, recovery_timeout_seconds=0, success_threshold=1)
        await _trip_breaker(reg, "m1", 2)
        await reg.allow_request("m1")  # probe
        tx = await reg.record_success("m1")
        assert tx is not None
        assert tx == CircuitStateTransition(
            model_id="m1",
            from_state=CircuitState.HALF_OPEN,
            to_state=CircuitState.CLOSED,
        )
    asyncio.run(_run())
