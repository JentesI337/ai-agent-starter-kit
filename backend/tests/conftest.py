"""Shared pytest fixtures and configuration for backend tests."""
from __future__ import annotations

import os


def pytest_configure(config):
    """Ensure rate limiting is disabled for all tests."""
    os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
    os.environ.setdefault("TESTING", "1")
