"""Tests for connector framework."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials
from app.connectors.generic_rest_connector import GenericRestConnector
from app.connectors.github_connector import GitHubConnector
from app.connectors.registry import ConnectorRegistry


def _make_config(**overrides) -> ConnectorConfig:
    defaults = {
        "connector_id": "test",
        "connector_type": "generic_rest",
        "display_name": "Test",
        "base_url": "https://httpbin.org",
        "auth_type": "none",
    }
    defaults.update(overrides)
    return ConnectorConfig(**defaults)


class TestConnectorConfig:
    def test_default_values(self):
        cfg = _make_config()
        assert cfg.rate_limit_rps == 2.0
        assert cfg.rate_limit_burst == 10
        assert cfg.timeout_seconds == 30
        assert cfg.max_response_bytes == 5_242_880

    def test_custom_values(self):
        cfg = _make_config(rate_limit_rps=10.0, timeout_seconds=60)
        assert cfg.rate_limit_rps == 10.0
        assert cfg.timeout_seconds == 60


class TestConnectorCredentials:
    def test_defaults(self):
        creds = ConnectorCredentials()
        assert creds.access_token is None
        assert creds.token_type == "bearer"
        assert creds.extra == {}

    def test_api_key(self):
        creds = ConnectorCredentials(api_key="test-key-123")
        assert creds.api_key == "test-key-123"


class TestGenericRestConnector:
    def test_build_request_get(self):
        cfg = _make_config(base_url="https://api.example.com")
        conn = GenericRestConnector(cfg)
        method, url, headers, body = conn.build_request("get", {"path": "/users"})
        assert method == "GET"
        assert url == "https://api.example.com/users"

    def test_build_request_post(self):
        cfg = _make_config(base_url="https://api.example.com")
        conn = GenericRestConnector(cfg)
        method, url, headers, body = conn.build_request("post", {"path": "/users", "body": {"name": "test"}})
        assert method == "POST"
        assert url == "https://api.example.com/users"
        assert body == {"name": "test"}

    def test_build_request_invalid_method(self):
        cfg = _make_config()
        conn = GenericRestConnector(cfg)
        with pytest.raises(ValueError, match="Unknown method"):
            conn.build_request("invalid", {})

    def test_available_methods(self):
        cfg = _make_config()
        conn = GenericRestConnector(cfg)
        methods = conn.available_methods()
        names = [m["name"] for m in methods]
        assert "get" in names
        assert "post" in names
        assert "delete" in names


class TestGitHubConnector:
    def test_build_request_repos_list(self):
        cfg = _make_config(connector_type="github", base_url="https://api.github.com")
        conn = GitHubConnector(cfg)
        method, url, headers, body = conn.build_request("repos.list", {})
        assert method == "GET"
        assert url == "https://api.github.com/user/repos"

    def test_build_request_issues_list(self):
        cfg = _make_config(connector_type="github", base_url="https://api.github.com")
        conn = GitHubConnector(cfg)
        method, url, headers, body = conn.build_request("issues.list", {"owner": "octocat", "repo": "hello"})
        assert method == "GET"
        assert url == "https://api.github.com/repos/octocat/hello/issues"

    def test_default_base_url(self):
        cfg = _make_config(connector_type="github", base_url="")
        conn = GitHubConnector(cfg)
        assert conn.config.base_url == "https://api.github.com"

    def test_auth_headers_with_api_key(self):
        cfg = _make_config(connector_type="github", base_url="https://api.github.com")
        creds = ConnectorCredentials(api_key="ghp_test123")
        conn = GitHubConnector(cfg, creds)
        headers = conn._auth_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer ghp_test123"

    def test_invalid_method(self):
        cfg = _make_config(connector_type="github", base_url="https://api.github.com")
        conn = GitHubConnector(cfg)
        with pytest.raises(ValueError, match="Unknown GitHub method"):
            conn.build_request("invalid.method", {})


class TestBaseConnectorExecuteHttp:
    @pytest.mark.asyncio
    async def test_blocks_private_ips(self):
        cfg = _make_config(base_url="http://192.168.1.1")
        conn = GenericRestConnector(cfg)
        result = await conn._execute_http("GET", "http://192.168.1.1/test", {}, None)
        assert "error" in result
        assert result["status_code"] == 0

    @pytest.mark.asyncio
    async def test_blocks_localhost(self):
        cfg = _make_config(base_url="http://localhost")
        conn = GenericRestConnector(cfg)
        result = await conn._execute_http("GET", "http://localhost/test", {}, None)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_enforces_size_limit(self):
        cfg = _make_config(max_response_bytes=100)
        conn = GenericRestConnector(cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "1000"}
        mock_response.content = b"x" * 1000

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            with patch("app.connectors.base.enforce_safe_url", return_value=None):
                result = await conn._execute_http("GET", "https://example.com/large", {}, None)
                assert "error" in result
                assert "too large" in result["error"].lower()


class TestConnectorRegistry:
    def test_supported_types(self):
        reg = ConnectorRegistry()
        types = reg.supported_types()
        assert "github" in types
        assert "jira" in types
        assert "slack_webhook" in types
        assert "google" in types
        assert "x" in types
        assert "generic_rest" in types

    def test_create_connector(self):
        reg = ConnectorRegistry()
        cfg = _make_config(connector_type="github", base_url="https://api.github.com")
        conn = reg.create_connector(cfg)
        assert isinstance(conn, GitHubConnector)

    def test_create_unknown_type(self):
        reg = ConnectorRegistry()
        cfg = _make_config(connector_type="unknown")
        with pytest.raises(ValueError, match="Unknown connector type"):
            reg.create_connector(cfg)

    def test_register_custom_type(self):
        reg = ConnectorRegistry()
        reg.register_type("custom", GenericRestConnector)
        assert "custom" in reg.supported_types()
