"""T2.2: CircuitBreakerRegistry — open / half-open / closed per Modell-ID.

Rein in-memory (kein SQLite-Persist); nach Neustart alle Breaker im CLOSED-Zustand.
Async-safe via ``asyncio.Lock``.  GuardrailViolation-Fehler werden NICHT erfasst.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"           # normal operation
    OPEN = "open"               # all requests blocked
    HALF_OPEN = "half_open"     # single probe request allowed


@dataclass(frozen=True)
class CircuitStateTransition:
    """Returned by mutating methods when a state transition occurs."""
    model_id: str
    from_state: CircuitState
    to_state: CircuitState


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5          # failures within window → OPEN
    failure_window_seconds: int = 60
    recovery_timeout_seconds: int = 120  # time in OPEN before → HALF_OPEN
    success_threshold: int = 2           # successes in HALF_OPEN → CLOSED


@dataclass
class _ModelCircuit:
    """Internal mutable state for a single model's circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_timestamps: deque = None  # type: ignore[assignment]
    half_open_successes: int = 0
    opened_at_mono: float = 0.0
    # Track whether a probe request is already in-flight (HALF_OPEN allows exactly one)
    half_open_probe_in_flight: bool = False

    def __post_init__(self) -> None:
        if self.failure_timestamps is None:
            self.failure_timestamps = deque()


class CircuitBreakerRegistry:
    """Registry of per-model circuit breakers.  Async-safe.

    State transitions:
        CLOSED  → OPEN       when ``failure_threshold`` failures occur within ``failure_window_seconds``
        OPEN    → HALF_OPEN  when ``recovery_timeout_seconds`` elapses since opening
        HALF_OPEN → CLOSED   when ``success_threshold`` consecutive successes are recorded
        HALF_OPEN → OPEN     when any failure occurs during probing
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._lock = asyncio.Lock()
        self._circuits: dict[str, _ModelCircuit] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def allow_request(self, model_id: str) -> tuple[bool, CircuitStateTransition | None]:
        """Return (allowed, transition) — *transition* is non-None when a state change occurred.

        For HALF_OPEN: exactly **one** probe request is allowed at a time.
        """
        async with self._lock:
            circuit = self._ensure_circuit(model_id)
            if circuit.state == CircuitState.CLOSED:
                return True, None
            if circuit.state == CircuitState.OPEN:
                if self._recovery_timeout_elapsed(circuit):
                    circuit.state = CircuitState.HALF_OPEN
                    circuit.half_open_successes = 0
                    circuit.half_open_probe_in_flight = False
                    transition = CircuitStateTransition(
                        model_id=model_id,
                        from_state=CircuitState.OPEN,
                        to_state=CircuitState.HALF_OPEN,
                    )
                    logger.info(
                        "circuit_breaker_state_changed model=%s from=open to=half_open",
                        model_id,
                    )
                    # fall through to HALF_OPEN below
                else:
                    return False, None
            else:
                transition = None
            # HALF_OPEN
            if circuit.half_open_probe_in_flight:
                return False, transition  # only one concurrent probe
            circuit.half_open_probe_in_flight = True
            return True, transition

    async def record_success(self, model_id: str) -> CircuitStateTransition | None:
        """Record a successful LLM call.  Returns transition if state changed."""
        async with self._lock:
            circuit = self._ensure_circuit(model_id)
            if circuit.state == CircuitState.HALF_OPEN:
                circuit.half_open_successes += 1
                circuit.half_open_probe_in_flight = False
                if circuit.half_open_successes >= self._config.success_threshold:
                    circuit.state = CircuitState.CLOSED
                    circuit.failure_timestamps.clear()
                    circuit.half_open_successes = 0
                    transition = CircuitStateTransition(
                        model_id=model_id,
                        from_state=CircuitState.HALF_OPEN,
                        to_state=CircuitState.CLOSED,
                    )
                    logger.info(
                        "circuit_breaker_state_changed model=%s from=half_open to=closed",
                        model_id,
                    )
                    return transition
            elif circuit.state == CircuitState.CLOSED:
                pass  # nothing to do; failures are time-windowed
            return None

    async def record_failure(self, model_id: str) -> CircuitStateTransition | None:
        """Record a failed LLM call.  Does NOT accept GuardrailViolation — caller must filter.

        Returns a *CircuitStateTransition* when the state changed.
        """
        async with self._lock:
            circuit = self._ensure_circuit(model_id)
            now = time.monotonic()

            if circuit.state == CircuitState.HALF_OPEN:
                # Any failure during probing → back to OPEN
                circuit.state = CircuitState.OPEN
                circuit.opened_at_mono = now
                circuit.half_open_successes = 0
                circuit.half_open_probe_in_flight = False
                logger.info(
                    "circuit_breaker_state_changed model=%s from=half_open to=open",
                    model_id,
                )
                return CircuitStateTransition(
                    model_id=model_id,
                    from_state=CircuitState.HALF_OPEN,
                    to_state=CircuitState.OPEN,
                )

            # CLOSED → check threshold
            circuit.failure_timestamps.append(now)
            self._evict_old_failures(circuit, now)
            if len(circuit.failure_timestamps) >= self._config.failure_threshold:
                circuit.state = CircuitState.OPEN
                circuit.opened_at_mono = now
                logger.info(
                    "circuit_breaker_state_changed model=%s from=closed to=open failures=%d window=%ds",
                    model_id,
                    len(circuit.failure_timestamps),
                    self._config.failure_window_seconds,
                )
                return CircuitStateTransition(
                    model_id=model_id,
                    from_state=CircuitState.CLOSED,
                    to_state=CircuitState.OPEN,
                )
            return None

    def get_state(self, model_id: str) -> CircuitState:
        """Non-async read of current state (best-effort, no lock)."""
        circuit = self._circuits.get(model_id)
        if circuit is None:
            return CircuitState.CLOSED
        # Check for potential OPEN → HALF_OPEN transition
        if circuit.state == CircuitState.OPEN and self._recovery_timeout_elapsed(circuit):
            return CircuitState.HALF_OPEN
        return circuit.state

    def all_states(self) -> dict[str, str]:
        """Diagnostic view of all tracked models."""
        return {
            model_id: self.get_state(model_id).value
            for model_id in list(self._circuits.keys())
        }

    async def reset(self, model_id: str) -> None:
        """Force-reset a model's circuit to CLOSED (admin/debug operation)."""
        async with self._lock:
            circuit = self._ensure_circuit(model_id)
            circuit.state = CircuitState.CLOSED
            circuit.failure_timestamps.clear()
            circuit.half_open_successes = 0
            circuit.half_open_probe_in_flight = False
            logger.info("circuit_breaker_reset model=%s", model_id)

    async def release_probe(self, model_id: str) -> None:
        """Release an in-flight HALF_OPEN probe without changing circuit state.

        This is used for neutral abort paths (for example guardrail rejections)
        that must not be counted as success or failure.
        """
        async with self._lock:
            circuit = self._ensure_circuit(model_id)
            if circuit.state == CircuitState.HALF_OPEN and circuit.half_open_probe_in_flight:
                circuit.half_open_probe_in_flight = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_circuit(self, model_id: str) -> _ModelCircuit:
        if model_id not in self._circuits:
            self._circuits[model_id] = _ModelCircuit()
        return self._circuits[model_id]

    def _recovery_timeout_elapsed(self, circuit: _ModelCircuit) -> bool:
        return (time.monotonic() - circuit.opened_at_mono) >= self._config.recovery_timeout_seconds

    def _evict_old_failures(self, circuit: _ModelCircuit, now: float) -> None:
        cutoff = now - self._config.failure_window_seconds
        while circuit.failure_timestamps and circuit.failure_timestamps[0] < cutoff:
            circuit.failure_timestamps.popleft()
