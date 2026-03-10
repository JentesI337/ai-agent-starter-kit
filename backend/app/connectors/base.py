"""Data models and abstract base class for API connectors."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel

from app.url_validator import UrlValidationError, enforce_safe_url

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES_DEFAULT = 5_242_880  # 5 MB


class ConnectorConfig(BaseModel):
    connector_id: str
    connector_type: str  # github | jira | slack_webhook | google | x | generic_rest
    display_name: str
    base_url: str
    auth_type: str = "none"  # none | api_key | oauth2_pkce | bearer
    rate_limit_rps: float = 2.0
    rate_limit_burst: int = 10
    default_headers: dict[str, str] = {}
    timeout_seconds: int = 30
    max_response_bytes: int = MAX_RESPONSE_BYTES_DEFAULT
    auto_refresh_token: bool = False
    oauth2_client_id: str | None = None
    oauth2_scopes: list[str] = []


class ConnectorCredentials(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_at: float | None = None
    api_key: str | None = None
    extra: dict[str, str] = {}


class BaseConnector(ABC):
    """Abstract base class for all API connectors."""

    def __init__(self, config: ConnectorConfig, credentials: ConnectorCredentials | None = None) -> None:
        self.config = config
        self.credentials = credentials

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a logical method call to an HTTP request."""
        http_method, url, headers, body = self.build_request(method, params)
        return await self._execute_http(http_method, url, headers, body)

    @abstractmethod
    def build_request(
        self, method: str, params: dict[str, Any]
    ) -> tuple[str, str, dict[str, str], Any]:
        """Build an HTTP request from a logical method + params.

        Returns (http_method, url, headers, body).
        """

    @abstractmethod
    def available_methods(self) -> list[dict[str, Any]]:
        """Return metadata about available methods for LLM tool descriptions."""

    def _auth_headers(self) -> dict[str, str]:
        """Build authorization headers from credentials."""
        headers: dict[str, str] = {}
        if self.credentials is None:
            return headers
        if self.config.auth_type == "api_key" and self.credentials.api_key:
            headers["Authorization"] = f"Bearer {self.credentials.api_key}"
        elif self.config.auth_type in ("bearer", "oauth2_pkce") and self.credentials.access_token:
            token_type = self.credentials.token_type or "bearer"
            headers["Authorization"] = f"{token_type.capitalize()} {self.credentials.access_token}"
        return headers

    async def _execute_http(
        self,
        http_method: str,
        url: str,
        headers: dict[str, str],
        body: Any,
    ) -> dict[str, Any]:
        """Shared HTTP execution with SSRF validation and size limits."""
        try:
            enforce_safe_url(url, label=f"Connector({self.config.connector_id})")
        except UrlValidationError as exc:
            return {"error": str(exc), "status_code": 0}

        merged_headers = {**self.config.default_headers, **self._auth_headers(), **headers}
        max_bytes = self.config.max_response_bytes or MAX_RESPONSE_BYTES_DEFAULT

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                response = await client.request(
                    method=http_method.upper(),
                    url=url,
                    headers=merged_headers,
                    json=body if body is not None and http_method.upper() in ("POST", "PUT", "PATCH") else None,
                    params=body if body is not None and http_method.upper() == "GET" else None,
                )

                content_length = int(response.headers.get("content-length", 0))
                if content_length > max_bytes:
                    return {
                        "error": f"Response too large: {content_length} bytes exceeds {max_bytes} limit",
                        "status_code": response.status_code,
                    }

                raw = response.content
                if len(raw) > max_bytes:
                    return {
                        "error": f"Response too large: {len(raw)} bytes exceeds {max_bytes} limit",
                        "status_code": response.status_code,
                    }

                try:
                    data = response.json()
                except Exception:
                    data = response.text

                return {
                    "status_code": response.status_code,
                    "data": data,
                    "headers": dict(response.headers),
                }

        except httpx.TimeoutException:
            return {"error": f"Request timed out after {self.config.timeout_seconds}s", "status_code": 0}
        except httpx.HTTPError as exc:
            return {"error": f"HTTP error: {exc}", "status_code": 0}
        except Exception as exc:
            logger.warning("connector_http_error connector=%s error=%s", self.config.connector_id, exc)
            return {"error": f"Request failed: {exc}", "status_code": 0}
