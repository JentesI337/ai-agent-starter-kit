"""Tests for ToolRetryStrategy."""

import pytest
from app.services.tool_retry_strategy import ToolRetryStrategy, RetryDecision


@pytest.fixture
def strategy():
    return ToolRetryStrategy()


class TestClassifyError:
    def test_transient_timeout(self, strategy):
        assert strategy.classify_error("Connection timeout after 30s") == "transient"

    def test_transient_rate_limit(self, strategy):
        assert strategy.classify_error("429 too many requests") == "transient"

    def test_transient_connection_refused(self, strategy):
        assert strategy.classify_error("ECONNREFUSED 127.0.0.1:3000") == "transient"

    def test_transient_503(self, strategy):
        assert strategy.classify_error("503 Service Unavailable") == "transient"

    def test_missing_dependency_command_not_found(self, strategy):
        assert strategy.classify_error("bash: ffmpeg: command not found") == "missing_dependency"

    def test_missing_dependency_module_not_found(self, strategy):
        assert strategy.classify_error("ModuleNotFoundError: No module named 'pandas'") == "missing_dependency"

    def test_missing_dependency_not_recognized(self, strategy):
        assert strategy.classify_error("'cargo' is not recognized as an internal command") == "missing_dependency"

    def test_invalid_args(self, strategy):
        assert strategy.classify_error("error: unknown flag --verbose-extra") == "invalid_args"

    def test_invalid_args_no_such_option(self, strategy):
        assert strategy.classify_error("no such option: --foobar") == "invalid_args"

    def test_permission_denied(self, strategy):
        assert strategy.classify_error("PermissionError: [Errno 13] Permission denied") == "permission"

    def test_permission_requires_admin(self, strategy):
        assert strategy.classify_error("This operation requires admin privileges") == "permission"

    def test_resource_exhaustion_disk(self, strategy):
        assert strategy.classify_error("OSError: [Errno 28] No space left on device") == "resource_exhaustion"

    def test_resource_exhaustion_port(self, strategy):
        assert strategy.classify_error("Error: port 8080 in use") == "resource_exhaustion"

    def test_crash_traceback(self, strategy):
        assert strategy.classify_error("Traceback (most recent call last):\n  File ...") == "crash"

    def test_crash_segfault(self, strategy):
        assert strategy.classify_error("Segmentation fault (core dumped)") == "crash"

    def test_unknown(self, strategy):
        assert strategy.classify_error("Something went wrong with the frobnicator") == "unknown"


class TestDecide:
    def test_transient_error_with_transient_class_retries(self, strategy):
        decision = strategy.decide(
            error_text="Connection timeout",
            retry_class="transient",
            attempt=1,
            max_retries=2,
        )
        assert decision.should_retry is True
        assert decision.strategy == "backoff"
        assert decision.error_category == "transient"
        assert decision.delay_seconds > 0

    def test_transient_error_with_timeout_class_retries(self, strategy):
        decision = strategy.decide(
            error_text="timeout waiting for response",
            retry_class="timeout",
            attempt=1,
            max_retries=2,
        )
        assert decision.should_retry is True
        assert decision.strategy == "backoff"

    def test_permission_error_never_retries(self, strategy):
        decision = strategy.decide(
            error_text="Permission denied: /etc/shadow",
            retry_class="transient",
            attempt=1,
            max_retries=3,
        )
        assert decision.should_retry is False
        assert decision.strategy == "escalate"
        assert decision.error_category == "permission"

    def test_missing_dependency_does_not_retry(self, strategy):
        decision = strategy.decide(
            error_text="command not found: docker",
            retry_class="transient",
            attempt=1,
            max_retries=3,
        )
        assert decision.should_retry is False
        assert decision.strategy == "replan"
        assert decision.error_category == "missing_dependency"

    def test_resource_exhaustion_retries_once(self, strategy):
        decision = strategy.decide(
            error_text="No space left on device",
            retry_class="transient",
            attempt=1,
            max_retries=3,
        )
        assert decision.should_retry is True
        assert decision.strategy == "backoff"
        assert decision.error_category == "resource_exhaustion"

    def test_resource_exhaustion_no_retry_after_first(self, strategy):
        decision = strategy.decide(
            error_text="No space left on device",
            retry_class="transient",
            attempt=2,
            max_retries=3,
        )
        assert decision.should_retry is False

    def test_retry_class_none_never_retries(self, strategy):
        decision = strategy.decide(
            error_text="Connection timeout",
            retry_class="none",
            attempt=1,
            max_retries=3,
        )
        assert decision.should_retry is False

    def test_budget_exhausted(self, strategy):
        decision = strategy.decide(
            error_text="Connection timeout",
            retry_class="transient",
            attempt=3,
            max_retries=2,
        )
        assert decision.should_retry is False
        assert "exhausted" in decision.reason.lower()

    def test_crash_does_not_retry(self, strategy):
        decision = strategy.decide(
            error_text="Traceback (most recent call last):\n  File 'x.py'",
            retry_class="transient",
            attempt=1,
            max_retries=3,
        )
        assert decision.should_retry is False
        assert decision.strategy == "replan"
        assert decision.error_category == "crash"


class TestBackoffDelay:
    def test_first_attempt(self):
        assert ToolRetryStrategy.backoff_delay(1) == 1.0

    def test_second_attempt(self):
        assert ToolRetryStrategy.backoff_delay(2) == 2.0

    def test_third_attempt(self):
        assert ToolRetryStrategy.backoff_delay(3) == 4.0

    def test_cap(self):
        assert ToolRetryStrategy.backoff_delay(10, cap=30.0) == 30.0

    def test_custom_base(self):
        assert ToolRetryStrategy.backoff_delay(1, base=3.0) == 3.0
        assert ToolRetryStrategy.backoff_delay(2, base=3.0) == 6.0
