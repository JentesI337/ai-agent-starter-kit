"""Connector type registry — factory for creating connector instances."""
from __future__ import annotations

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials


class ConnectorRegistry:
    """Registry of connector types with a factory method."""

    def __init__(self) -> None:
        self._types: dict[str, type[BaseConnector]] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        from app.connectors.generic_rest_connector import GenericRestConnector
        from app.connectors.github_connector import GitHubConnector
        from app.connectors.google_connector import GoogleConnector
        from app.connectors.jira_connector import JiraConnector
        from app.connectors.slack_connector import SlackConnector
        from app.connectors.x_connector import XConnector

        self._types["github"] = GitHubConnector
        self._types["jira"] = JiraConnector
        self._types["slack_webhook"] = SlackConnector
        self._types["google"] = GoogleConnector
        self._types["x"] = XConnector
        self._types["generic_rest"] = GenericRestConnector

    def register_type(self, name: str, cls: type[BaseConnector]) -> None:
        self._types[name] = cls

    def create_connector(
        self,
        config: ConnectorConfig,
        credentials: ConnectorCredentials | None = None,
    ) -> BaseConnector:
        cls = self._types.get(config.connector_type)
        if cls is None:
            raise ValueError(f"Unknown connector type: {config.connector_type}")
        return cls(config, credentials)

    def supported_types(self) -> list[str]:
        return sorted(self._types.keys())
