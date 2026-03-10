"""X (Twitter) API v2 connector."""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorConfig, ConnectorCredentials

_DEFAULT_BASE = "https://api.x.com/2"

_METHOD_MAP: dict[str, tuple[str, str]] = {
    "tweets.search": ("GET", "/tweets/search/recent"),
    "tweets.post": ("POST", "/tweets"),
    "users.lookup": ("GET", "/users/by/username/{username}"),
}


class XConnector(BaseConnector):

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        if not config.base_url:
            config = config.model_copy(update={"base_url": _DEFAULT_BASE})
        super().__init__(config, credentials)

    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        spec = _METHOD_MAP.get(method)
        if spec is None:
            raise ValueError(f"Unknown X method '{method}'. Available: {list(_METHOD_MAP)}")

        http_method, path_template = spec
        username = params.pop("username", None) or ""
        path = path_template.replace("{username}", username)

        base = self.config.base_url.rstrip("/")
        url = f"{base}{path}"
        body = params if http_method == "POST" else None
        query = params if http_method == "GET" else None
        return http_method, url, {}, body or query

    def available_methods(self) -> list[dict[str, Any]]:
        return [
            {"name": "tweets.search", "description": "Search recent tweets", "params": ["query", "max_results"]},
            {"name": "tweets.post", "description": "Post a tweet", "params": ["text"]},
            {"name": "users.lookup", "description": "Lookup user by username", "params": ["username"]},
        ]
