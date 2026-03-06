"""SEC (CFG-07): Logging filter that redacts sensitive data from log messages.

Prevents accidental leakage of API keys, tokens, and other secrets in log output.
"""

from __future__ import annotations

import logging
import re

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api[_\-]?key\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(password\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(secret\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(Authorization\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
]


class SecretFilter(logging.Filter):
    """Redact sensitive patterns from log messages before they are emitted."""

    @staticmethod
    def _sanitize_value(value: object) -> object:
        if isinstance(value, str):
            for pattern, replacement in _SECRET_PATTERNS:
                value = pattern.sub(replacement, value)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _SECRET_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._sanitize_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._sanitize_value(a) for a in record.args)
            else:
                record.args = (self._sanitize_value(record.args),)
        return True


def install_secret_filter() -> None:
    """Install the secret filter on the root logger."""
    root_logger = logging.getLogger()
    root_logger.addFilter(SecretFilter())
