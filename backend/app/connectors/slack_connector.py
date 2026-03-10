"""Slack webhook connector."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials


class SlackConnector(BaseConnector):

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        super().__init__(config, credentials)

    def _auth_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        if method != "message.send":
            raise ValueError(f"Unknown Slack method '{method}'. Available: ['message.send']")

        url = self.config.base_url  # webhook URL
        body = {"text": params.get("text", "")}
        if "blocks" in params:
            body["blocks"] = params["blocks"]
        if "channel" in params:
            body["channel"] = params["channel"]
        return "POST", url, {}, body

    def available_methods(self) -> list[dict[str, Any]]:
        return [
            {"name": "message.send", "description": "Send a message via webhook", "params": ["text", "blocks", "channel"]},
        ]
