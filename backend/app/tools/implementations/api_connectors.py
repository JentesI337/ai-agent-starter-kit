"""API Connector tool mixin — provides api_call, api_list_connectors, api_auth tools."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.connectors.base import ConnectorConfig
from app.connectors.connector_store import ConnectorStore
from app.connectors.credential_store import CredentialStore
from app.connectors.oauth2_flow import OAUTH2_PRESETS, OAuth2Config, refresh_oauth2_token
from app.connectors.registry import ConnectorRegistry
from app.tools.content_security import wrap_external_content
from app.policy.rate_limiter import RateLimiter, RateLimiterConfig

logger = logging.getLogger(__name__)

# Default rate limits per connector type
_DEFAULT_RATES: dict[str, tuple[float, int]] = {
    "github": (5.0, 15),
    "jira": (2.0, 10),
    "slack_webhook": (1.0, 5),
    "google": (5.0, 15),
    "x": (1.0, 5),
    "generic_rest": (5.0, 20),
}

_MAX_RESPONSE_CHARS = 100_000

# Pattern to detect accidentally leaked tokens/keys
_CREDENTIAL_PATTERNS = [
    re.compile(r"(ghp_[A-Za-z0-9_]{36,})"),
    re.compile(r"(gho_[A-Za-z0-9_]{36,})"),
    re.compile(r"(xox[bpsar]-[A-Za-z0-9-]+)"),
    re.compile(r"(sk-[A-Za-z0-9]{20,})"),
    re.compile(r"(ya29\.[A-Za-z0-9_-]+)"),
]


def _redact_credentials(text: str) -> str:
    """Redact known credential patterns from text."""
    for pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class ApiConnectorToolMixin:
    """Mixin providing API connector tools for AgentTooling."""

    _connector_store: ConnectorStore | None = None
    _credential_store: CredentialStore | None = None
    _connector_registry: ConnectorRegistry | None = None
    _connector_rate_limiters: dict[str, RateLimiter] = {}

    def set_connector_services(
        self,
        connector_store: ConnectorStore,
        credential_store: CredentialStore,
        connector_registry: ConnectorRegistry,
    ) -> None:
        self._connector_store = connector_store
        self._credential_store = credential_store
        self._connector_registry = connector_registry

    def _get_connector_rate_limiter(self, config: ConnectorConfig) -> RateLimiter:
        """Get or create a rate limiter for the given connector."""
        cid = config.connector_id
        if cid not in self._connector_rate_limiters:
            defaults = _DEFAULT_RATES.get(config.connector_type, (2.0, 10))
            rps = config.rate_limit_rps or defaults[0]
            burst = config.rate_limit_burst or defaults[1]
            self._connector_rate_limiters[cid] = RateLimiter(
                RateLimiterConfig(requests_per_second=rps, burst=burst)
            )
        return self._connector_rate_limiters[cid]

    async def api_call(
        self, connector: str, method: str, params: str | None = None
    ) -> str:
        """Call an external API through a configured connector.

        Args:
            connector: Connector ID (e.g. "my-github")
            method: Logical method name (e.g. "repos.list")
            params: JSON string of parameters, or null
        """
        if not self._connector_store or not self._credential_store or not self._connector_registry:
            return "Error: API connector services not initialized. Enable api_connectors in settings."

        config = self._connector_store.get(connector)
        if config is None:
            return f"Error: Connector '{connector}' not found. Use api_list_connectors to see available connectors."

        # Rate limiting
        limiter = self._get_connector_rate_limiter(config)
        if not limiter.allow(connector):
            return f"Error: Rate limit exceeded for connector '{connector}'. Try again shortly."

        # Parse params
        parsed_params: dict[str, Any] = {}
        if params:
            try:
                parsed_params = json.loads(params) if isinstance(params, str) else params
            except json.JSONDecodeError:
                return "Error: Invalid JSON in params."

        # Get credentials (never expose in output)
        credentials = self._credential_store.retrieve(connector)

        # Check token expiry
        if credentials and credentials.expires_at and time.time() > credentials.expires_at:
            if config.auto_refresh_token and credentials.refresh_token:
                try:
                    preset = OAUTH2_PRESETS.get(config.connector_type, {})
                    if preset and config.oauth2_client_id:
                        oauth_cfg = OAuth2Config(
                            client_id=config.oauth2_client_id,
                            scopes=config.oauth2_scopes,
                            **preset,
                        )
                        credentials = await refresh_oauth2_token(oauth_cfg, credentials)
                        self._credential_store.store(connector, credentials)
                except Exception as exc:
                    return f"Error: Token refresh failed: {exc}"
            else:
                return "Error: Access token has expired. Re-authenticate from the Integrations page."

        # Create and call connector
        try:
            conn = self._connector_registry.create_connector(config, credentials)
            result = await conn.call(method, parsed_params)
        except ValueError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.warning("api_call_error connector=%s method=%s error=%s", connector, method, exc)
            return f"Error: API call failed: {exc}"

        # Format and sanitize response
        response_text = json.dumps(result, indent=2, default=str)
        response_text = _redact_credentials(response_text)
        if len(response_text) > _MAX_RESPONSE_CHARS:
            response_text = response_text[:_MAX_RESPONSE_CHARS] + "\n... [truncated]"

        return wrap_external_content(response_text, source=f"api_connector:{connector}")

    async def api_list_connectors(self) -> str:
        """List all configured API connectors with their status."""
        if not self._connector_store or not self._credential_store or not self._connector_registry:
            return "Error: API connector services not initialized."

        configs = self._connector_store.get_all()
        if not configs:
            return "No connectors configured. Add connectors from the Integrations page."

        items = []
        for cid, config in configs.items():
            has_creds = self._credential_store.has(cid)
            try:
                conn = self._connector_registry.create_connector(config)
                methods = conn.available_methods()
            except Exception:
                methods = []

            items.append({
                "id": cid,
                "type": config.connector_type,
                "display_name": config.display_name,
                "base_url": config.base_url,
                "auth_type": config.auth_type,
                "has_credentials": has_creds,
                "available_methods": [m["name"] for m in methods],
            })

        return json.dumps({"connectors": items}, indent=2)

    async def api_auth(self, connector: str) -> str:
        """Authenticate a connector — must be done from the Integrations UI page.

        Args:
            connector: Connector ID to authenticate
        """
        return (
            f"OAuth flow for connector '{connector}' must be initiated from the Integrations page in the UI. "
            "Agents cannot perform interactive authentication. "
            "Please ask the user to visit the Integrations page and connect the service there."
        )
