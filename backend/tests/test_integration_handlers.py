"""Tests for integration handlers."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from app.connectors.base import ConnectorConfig, ConnectorCredentials
from app.connectors.connector_store import ConnectorStore
from app.connectors.credential_store import CredentialStore
from app.connectors.registry import ConnectorRegistry
from app.handlers import integration_handlers


@pytest.fixture
def stores(tmp_path: Path):
    cs = ConnectorStore(persist_path=tmp_path / "connectors.json")
    cred_s = CredentialStore(persist_path=tmp_path / "credentials.json")
    reg = ConnectorRegistry()
    integration_handlers.configure(cs, cred_s, reg)
    return cs, cred_s, reg


class TestConnectorsListHandler:
    def test_empty_list(self, stores):
        result = integration_handlers.handle_connectors_list({})
        assert result["connectors"] == []

    def test_list_with_connectors(self, stores):
        cs, _, _ = stores
        cs.upsert(ConnectorConfig(
            connector_id="test-gh",
            connector_type="github",
            display_name="Test GitHub",
            base_url="https://api.github.com",
            auth_type="bearer",
        ))
        result = integration_handlers.handle_connectors_list({})
        assert len(result["connectors"]) == 1
        assert result["connectors"][0]["connector_id"] == "test-gh"


class TestConnectorsCreateHandler:
    def test_create_connector(self, stores):
        result = integration_handlers.handle_connectors_create({
            "connector_id": "my-rest",
            "connector_type": "generic_rest",
            "display_name": "My REST API",
            "base_url": "https://httpbin.org",
            "auth_type": "none",
        })
        assert "connector" in result
        assert result["connector"]["connector_id"] == "my-rest"

    def test_create_with_api_key(self, stores):
        _, cred_s, _ = stores
        result = integration_handlers.handle_connectors_create({
            "connector_id": "keyed",
            "connector_type": "generic_rest",
            "display_name": "Keyed API",
            "base_url": "https://httpbin.org",
            "auth_type": "api_key",
            "api_key": "test-key-123",
        })
        assert "connector" in result
        assert cred_s.has("keyed")

    def test_create_invalid_type(self, stores):
        result = integration_handlers.handle_connectors_create({
            "connector_id": "bad",
            "connector_type": "nonexistent",
            "display_name": "Bad",
            "base_url": "https://httpbin.org",
            "auth_type": "none",
        })
        assert "error" in result


class TestConnectorsGetHandler:
    def test_get_existing(self, stores):
        cs, _, _ = stores
        cs.upsert(ConnectorConfig(
            connector_id="test",
            connector_type="github",
            display_name="Test",
            base_url="https://api.github.com",
        ))
        result = integration_handlers.handle_connectors_get({"connector_id": "test"})
        assert "connector" in result

    def test_get_nonexistent(self, stores):
        result = integration_handlers.handle_connectors_get({"connector_id": "nope"})
        assert "error" in result


class TestConnectorsDeleteHandler:
    def test_delete(self, stores):
        cs, cred_s, _ = stores
        cs.upsert(ConnectorConfig(
            connector_id="del-me",
            connector_type="generic_rest",
            display_name="Delete Me",
            base_url="https://httpbin.org",
        ))
        cred_s.store("del-me", ConnectorCredentials(api_key="x"))
        result = integration_handlers.handle_connectors_delete({"connector_id": "del-me"})
        assert result["ok"] is True
        assert cs.get("del-me") is None
        assert not cred_s.has("del-me")


class TestConnectorsTestHandler:
    @pytest.mark.asyncio
    async def test_nonexistent_connector(self, stores):
        result = await integration_handlers.handle_connectors_test({"connector_id": "nope"})
        assert result["ok"] is False
        assert "not found" in result["error"]


class TestOAuthStartHandler:
    def test_oauth_start_no_client_id(self, stores):
        cs, _, _ = stores
        cs.upsert(ConnectorConfig(
            connector_id="gh-oauth",
            connector_type="github",
            display_name="GitHub OAuth",
            base_url="https://api.github.com",
            auth_type="oauth2_pkce",
        ))
        result = integration_handlers.handle_oauth_start({"connector_id": "gh-oauth"})
        assert "error" in result

    def test_oauth_start_with_client_id(self, stores):
        cs, _, _ = stores
        cs.upsert(ConnectorConfig(
            connector_id="gh-oauth",
            connector_type="github",
            display_name="GitHub OAuth",
            base_url="https://api.github.com",
            auth_type="oauth2_pkce",
            oauth2_client_id="test-client-id",
        ))
        result = integration_handlers.handle_oauth_start({"connector_id": "gh-oauth"})
        assert "authorization_url" in result
        assert "state" in result
        assert "test-client-id" in result["authorization_url"]


class TestOAuthStatusHandler:
    def test_not_complete(self, stores):
        result = integration_handlers.handle_oauth_status({"connector_id": "nonexistent"})
        assert result["complete"] is False
