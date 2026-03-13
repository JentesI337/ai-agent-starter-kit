"""Tests for credential store."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.connectors.base import ConnectorCredentials
from app.connectors.credential_store import CredentialStore


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "test_creds.json"


@pytest.fixture
def store(store_path: Path) -> CredentialStore:
    return CredentialStore(persist_path=store_path)


class TestCredentialStore:
    def test_store_and_retrieve(self, store: CredentialStore):
        creds = ConnectorCredentials(api_key="test-key-123")
        store.store("my-connector", creds)

        retrieved = store.retrieve("my-connector")
        assert retrieved is not None
        assert retrieved.api_key == "test-key-123"

    def test_retrieve_nonexistent(self, store: CredentialStore):
        assert store.retrieve("nonexistent") is None

    def test_delete(self, store: CredentialStore):
        creds = ConnectorCredentials(api_key="test-key")
        store.store("my-connector", creds)
        store.delete("my-connector")
        assert store.retrieve("my-connector") is None

    def test_list_ids(self, store: CredentialStore):
        store.store("conn-a", ConnectorCredentials(api_key="a"))
        store.store("conn-b", ConnectorCredentials(api_key="b"))
        ids = store.list_ids()
        assert "conn-a" in ids
        assert "conn-b" in ids

    def test_has(self, store: CredentialStore):
        assert not store.has("test")
        store.store("test", ConnectorCredentials(api_key="x"))
        assert store.has("test")

    def test_encryption_on_disk(self, store: CredentialStore, store_path: Path):
        creds = ConnectorCredentials(api_key="secret-api-key-12345")
        store.store("encrypted-test", creds)

        # Read raw file — should NOT contain plaintext
        raw = store_path.read_text(encoding="utf-8")
        assert "secret-api-key-12345" not in raw

    def test_list_ids_contains_no_secrets(self, store: CredentialStore):
        creds = ConnectorCredentials(api_key="super-secret")
        store.store("my-conn", creds)
        ids = store.list_ids()
        for id_val in ids:
            assert "super-secret" not in id_val

    def test_persistence_across_instances(self, store_path: Path):
        store1 = CredentialStore(persist_path=store_path)
        store1.store("persist-test", ConnectorCredentials(api_key="persisted"))

        store2 = CredentialStore(persist_path=store_path)
        retrieved = store2.retrieve("persist-test")
        assert retrieved is not None
        assert retrieved.api_key == "persisted"

    def test_overwrite_credentials(self, store: CredentialStore):
        store.store("conn", ConnectorCredentials(api_key="old"))
        store.store("conn", ConnectorCredentials(api_key="new"))
        retrieved = store.retrieve("conn")
        assert retrieved is not None
        assert retrieved.api_key == "new"
