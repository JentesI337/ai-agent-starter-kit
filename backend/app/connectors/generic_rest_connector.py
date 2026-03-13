"""Generic REST API connector — supports arbitrary HTTP methods."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials


class GenericRestConnector(BaseConnector):
    """Pass-through connector for arbitrary REST APIs."""

    _METHODS = {
        "get": "GET",
        "post": "POST",
        "put": "PUT",
        "patch": "PATCH",
        "delete": "DELETE",
    }

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        super().__init__(config, credentials)

    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        http_method = self._METHODS.get(method)
        if http_method is None:
            raise ValueError(f"Unknown method '{method}'. Available: {list(self._METHODS)}")

        path = params.pop("path", "") or ""
        base = self.config.base_url.rstrip("/")
        url = f"{base}/{path.lstrip('/')}" if path else base
        headers = params.pop("headers", {}) or {}
        body = params.pop("body", None)
        # Remaining params become query params for GET, body for others
        if http_method == "GET" and not body:
            body = params or None
        elif body is None and params:
            body = params
        return http_method, url, headers, body

    def available_methods(self) -> list[dict[str, Any]]:
        return [
            {"name": "get", "description": "HTTP GET request", "params": ["path", "headers"]},
            {"name": "post", "description": "HTTP POST request", "params": ["path", "headers", "body"]},
            {"name": "put", "description": "HTTP PUT request", "params": ["path", "headers", "body"]},
            {"name": "patch", "description": "HTTP PATCH request", "params": ["path", "headers", "body"]},
            {"name": "delete", "description": "HTTP DELETE request", "params": ["path", "headers"]},
        ]
