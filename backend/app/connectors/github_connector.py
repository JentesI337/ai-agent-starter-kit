"""GitHub API connector."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials

_DEFAULT_BASE = "https://api.github.com"

_METHOD_MAP: dict[str, tuple[str, str]] = {
    "repos.list": ("GET", "/user/repos"),
    "repos.get": ("GET", "/repos/{owner}/{repo}"),
    "issues.list": ("GET", "/repos/{owner}/{repo}/issues"),
    "issues.create": ("POST", "/repos/{owner}/{repo}/issues"),
    "pulls.list": ("GET", "/repos/{owner}/{repo}/pulls"),
    "search.code": ("GET", "/search/code"),
}


class GitHubConnector(BaseConnector):

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        if not config.base_url:
            config = config.model_copy(update={"base_url": _DEFAULT_BASE})
        super().__init__(config, credentials)

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self.credentials:
            if self.credentials.api_key:
                headers["Authorization"] = f"Bearer {self.credentials.api_key}"
            elif self.credentials.access_token:
                headers["Authorization"] = f"Bearer {self.credentials.access_token}"
        return headers

    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        spec = _METHOD_MAP.get(method)
        if spec is None:
            raise ValueError(f"Unknown GitHub method '{method}'. Available: {list(_METHOD_MAP)}")

        http_method, path_template = spec
        # Substitute path params
        owner = params.pop("owner", None) or ""
        repo = params.pop("repo", None) or ""
        path = path_template.replace("{owner}", owner).replace("{repo}", repo)

        base = self.config.base_url.rstrip("/")
        url = f"{base}{path}"
        body = params if http_method == "POST" else None
        query = params if http_method == "GET" else None
        return http_method, url, {}, body or query

    def available_methods(self) -> list[dict[str, Any]]:
        return [
            {"name": "repos.list", "description": "List authenticated user's repositories"},
            {"name": "repos.get", "description": "Get a repository", "params": ["owner", "repo"]},
            {"name": "issues.list", "description": "List issues", "params": ["owner", "repo"]},
            {"name": "issues.create", "description": "Create an issue", "params": ["owner", "repo", "title", "body"]},
            {"name": "pulls.list", "description": "List pull requests", "params": ["owner", "repo"]},
            {"name": "search.code", "description": "Search code", "params": ["q"]},
        ]
