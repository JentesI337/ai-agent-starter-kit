"""Jira API connector."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials

_METHOD_MAP: dict[str, tuple[str, str]] = {
    "issues.search": ("POST", "/rest/api/3/search"),
    "issues.get": ("GET", "/rest/api/3/issue/{issue_key}"),
    "issues.create": ("POST", "/rest/api/3/issue"),
    "issues.transition": ("POST", "/rest/api/3/issue/{issue_key}/transitions"),
    "projects.list": ("GET", "/rest/api/3/project"),
}


class JiraConnector(BaseConnector):

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        super().__init__(config, credentials)

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.credentials:
            if self.credentials.api_key and self.credentials.extra.get("email"):
                import base64
                raw = f"{self.credentials.extra['email']}:{self.credentials.api_key}"
                encoded = base64.b64encode(raw.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
            elif self.credentials.access_token:
                headers["Authorization"] = f"Bearer {self.credentials.access_token}"
        return headers

    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        spec = _METHOD_MAP.get(method)
        if spec is None:
            raise ValueError(f"Unknown Jira method '{method}'. Available: {list(_METHOD_MAP)}")

        http_method, path_template = spec
        issue_key = params.pop("issue_key", None) or ""
        path = path_template.replace("{issue_key}", issue_key)

        base = self.config.base_url.rstrip("/")
        url = f"{base}{path}"
        body = params if http_method == "POST" else None
        query = params if http_method == "GET" else None
        return http_method, url, {}, body or query

    def available_methods(self) -> list[dict[str, Any]]:
        return [
            {"name": "issues.search", "description": "Search issues with JQL", "params": ["jql", "maxResults"]},
            {"name": "issues.get", "description": "Get an issue", "params": ["issue_key"]},
            {"name": "issues.create", "description": "Create an issue", "params": ["fields"]},
            {"name": "issues.transition", "description": "Transition an issue", "params": ["issue_key", "transition"]},
            {"name": "projects.list", "description": "List projects"},
        ]
