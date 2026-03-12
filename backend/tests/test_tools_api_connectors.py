"""Tests for API connector tool mixin."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.connectors.base import ConnectorConfig, ConnectorCredentials
from app.connectors.connector_store import ConnectorStore
from app.connectors.credential_store import CredentialStore
from app.connectors.registry import ConnectorRegistry
from app.tools.implementations.api_connectors import ApiConnectorToolMixin


class MockTooling(ApiConnectorToolMixin):
    """Test harness for the mixin."""
    pass


@pytest.fixture
def mixin(tmp_path: Path):
    cs = ConnectorStore(persist_path=tmp_path / "connectors.json")
    cred_s = CredentialStore(persist_path=tmp_path / "credentials.json")
    reg = ConnectorRegistry()
    m = MockTooling()
    m.set_connector_services(cs, cred_s, reg)
    return m, cs, cred_s


class TestApiCall:
    @pytest.mark.asyncio
    async def test_missing_connector(self, mixin):
        m, _, _ = mixin
        result = await m.api_call("nonexistent", "get", None)
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_invalid_json_params(self, mixin):
        m, cs, _ = mixin
        cs.upsert(ConnectorConfig(
            connector_id="test",
            connector_type="generic_rest",
            display_name="Test",
            base_url="https://httpbin.org",
        ))
        result = await m.api_call("test", "get", "{invalid json")
        assert "invalid json" in result.lower()

    @pytest.mark.asyncio
    async def test_services_not_initialized(self):
        m = MockTooling()
        result = await m.api_call("test", "get", None)
        assert "not initialized" in result.lower()

    @pytest.mark.asyncio
    async def test_rate_limiting(self, mixin):
        m, cs, _ = mixin
        cs.upsert(ConnectorConfig(
            connector_id="rate-test",
            connector_type="generic_rest",
            display_name="Rate Test",
            base_url="https://httpbin.org",
            rate_limit_rps=0.001,  # Very low rate
            rate_limit_burst=1,
        ))

        # First call should succeed (or fail for other reasons)
        with patch.object(type(m), '_get_connector_rate_limiter') as mock_limiter:
            from app.services.rate_limiter import RateLimiter, RateLimiterConfig
            limiter = RateLimiter(RateLimiterConfig(requests_per_second=0.001, burst=1))
            # Consume the only token
            limiter.allow("rate-test")
            mock_limiter.return_value = limiter

            result = await m.api_call("rate-test", "get", None)
            assert "rate limit" in result.lower()


class TestApiListConnectors:
    @pytest.mark.asyncio
    async def test_empty_list(self, mixin):
        m, _, _ = mixin
        result = await m.api_list_connectors()
        assert "No connectors" in result

    @pytest.mark.asyncio
    async def test_list_with_connectors(self, mixin):
        m, cs, cred_s = mixin
        cs.upsert(ConnectorConfig(
            connector_id="gh",
            connector_type="github",
            display_name="GitHub",
            base_url="https://api.github.com",
            auth_type="bearer",
        ))
        cred_s.store("gh", ConnectorCredentials(api_key="test"))

        result = await m.api_list_connectors()
        data = json.loads(result)
        assert len(data["connectors"]) == 1
        assert data["connectors"][0]["id"] == "gh"
        assert data["connectors"][0]["has_credentials"] is True

    @pytest.mark.asyncio
    async def test_services_not_initialized(self):
        m = MockTooling()
        result = await m.api_list_connectors()
        assert "not initialized" in result.lower()


class TestApiAuth:
    @pytest.mark.asyncio
    async def test_returns_ui_message(self, mixin):
        m, _, _ = mixin
        result = await m.api_auth("any-connector")
        assert "Integrations page" in result
        assert "cannot" in result.lower()
