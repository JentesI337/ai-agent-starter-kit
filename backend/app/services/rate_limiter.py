"""SEC (OE-03): Token-bucket rate limiter for REST and WebSocket endpoints.

Provides per-IP and per-session rate limiting without external dependencies.
Uses an in-memory token-bucket algorithm with configurable burst and refill rate.
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    tokens: float
    last_refill: float
    burst: int


@dataclass
class RateLimiterConfig:
    """Configuration for the rate limiter."""
    # Requests per second (sustained rate)
    requests_per_second: float = 5.0
    # Maximum burst size (tokens in bucket at any time)
    burst: int = 20
    # How long to keep idle buckets before cleanup (seconds)
    cleanup_interval: float = 300.0
    # Whether rate limiting is enabled
    enabled: bool = True


class RateLimiter:
    """In-memory token-bucket rate limiter keyed by arbitrary string (IP, session, etc.).

    Thread-safe. No external dependencies required.
    """

    def __init__(self, config: RateLimiterConfig | None = None):
        self._config = config or RateLimiterConfig()
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def allow(self, key: str) -> bool:
        """Check if a request from *key* is allowed. Consumes one token if allowed."""
        if not self._config.enabled:
            return True

        now = time.monotonic()

        with self._lock:
            # Periodic cleanup of stale buckets
            if now - self._last_cleanup > self._config.cleanup_interval:
                self._cleanup(now)

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(
                    tokens=float(self._config.burst),
                    last_refill=now,
                    burst=self._config.burst,
                )
                self._buckets[key] = bucket

            # Refill tokens based on elapsed time
            elapsed = now - bucket.last_refill
            if elapsed > 0:
                refill = elapsed * self._config.requests_per_second
                bucket.tokens = min(float(bucket.burst), bucket.tokens + refill)
                bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True

            return False

    def remaining(self, key: str) -> int:
        """Return remaining tokens for *key* without consuming."""
        if not self._config.enabled:
            return self._config.burst

        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return self._config.burst
            elapsed = now - bucket.last_refill
            available = min(float(bucket.burst), bucket.tokens + elapsed * self._config.requests_per_second)
            return int(available)

    def _cleanup(self, now: float) -> None:
        """Remove buckets idle longer than cleanup_interval."""
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if now - bucket.last_refill > self._config.cleanup_interval
        ]
        for key in stale_keys:
            del self._buckets[key]
        self._last_cleanup = now


# ---------------------------------------------------------------------------
# Global singleton instances for REST and WebSocket rate limiting
# ---------------------------------------------------------------------------

_rest_limiter: RateLimiter | None = None
_ws_limiter: RateLimiter | None = None


def _is_test_environment() -> bool:
    """Detect if running in a test environment."""
    import os
    import sys
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
        return True
    # Check if pytest is in sys.modules (imported)
    if "pytest" in sys.modules or "_pytest" in sys.modules:
        return True
    return False


def get_rest_rate_limiter() -> RateLimiter:
    """Get (or create) the global REST rate limiter."""
    global _rest_limiter
    if _rest_limiter is None:
        import os
        enabled = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no")
        # Auto-disable in test environments
        if _is_test_environment():
            enabled = False
        rps = float(os.getenv("RATE_LIMIT_RPS", "10"))
        burst = int(os.getenv("RATE_LIMIT_BURST", "30"))
        _rest_limiter = RateLimiter(RateLimiterConfig(
            requests_per_second=rps,
            burst=burst,
            enabled=enabled,
        ))
    return _rest_limiter


def get_ws_rate_limiter() -> RateLimiter:
    """Get (or create) the global WebSocket message rate limiter."""
    global _ws_limiter
    if _ws_limiter is None:
        import os
        enabled = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in ("0", "false", "no")
        # Auto-disable in test environments
        if _is_test_environment():
            enabled = False
        rps = float(os.getenv("WS_RATE_LIMIT_RPS", "5"))
        burst = int(os.getenv("WS_RATE_LIMIT_BURST", "20"))
        _ws_limiter = RateLimiter(RateLimiterConfig(
            requests_per_second=rps,
            burst=burst,
            enabled=enabled,
        ))
    return _ws_limiter


def reset_rate_limiters() -> None:
    """Reset global singletons — intended for test isolation only."""
    global _rest_limiter, _ws_limiter
    _rest_limiter = None
    _ws_limiter = None