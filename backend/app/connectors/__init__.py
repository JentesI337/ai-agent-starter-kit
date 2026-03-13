"""connectors — External Service Integration Domain.

Manages connections to external APIs and services.
  - BaseConnector:         Abstract base for all connectors
  - ConnectorConfig:       Connector configuration model
  - ConnectorCredentials:  Credential data model
  - ConnectorRegistry:     Discovers and instantiates connectors
  - ConnectorStore:        Persists connector configurations
  - CredentialStore:       Encrypted credential storage

HTTP routes for connector management live in app.transport.routers.connectors.

Allowed imports FROM:
  shared, contracts, config, state

NOT allowed:
  transport, agent, tools, workflows, orchestration, services (deprecated)
"""

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials
from app.connectors.connector_store import ConnectorStore
from app.connectors.credential_store import CredentialStore
from app.connectors.registry import ConnectorRegistry

__all__ = [
    "BaseConnector",
    "ConnectorConfig",
    "ConnectorCredentials",
    "ConnectorRegistry",
    "ConnectorStore",
    "CredentialStore",
]
