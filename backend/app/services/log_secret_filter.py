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

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _SECRET_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args:
            sanitized_args: list[object] = []
            for arg in (record.args if isinstance(record.args, tuple) else (record.args,)):
                sanitized_arg = arg
                if isinstance(sanitized_arg, str):
                    for pattern, replacement in _SECRET_PATTERNS:
                        sanitized_arg = pattern.sub(replacement, sanitized_arg)
                sanitized_args.append(sanitized_arg)
            record.args = tuple(sanitized_args)
        return True


def install_secret_filter() -> None:
    """Install the secret filter on the root logger."""
    root_logger = logging.getLogger()
    root_logger.addFilter(SecretFilter())
