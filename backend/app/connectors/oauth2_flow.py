"""OAuth2 PKCE flow for connector authentication."""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.connectors.base import ConnectorCredentials

logger = logging.getLogger(__name__)


class OAuth2Config(BaseModel):
    authorization_url: str
    token_url: str
    client_id: str
    scopes: list[str] = []
    redirect_uri: str = "http://localhost:8000/api/integrations/oauth/callback"


OAUTH2_PRESETS: dict[str, dict[str, str]] = {
    "github": {
        "authorization_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
    },
    "google": {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
    },
    "x": {
        "authorization_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.twitter.com/2/oauth2/token",
    },
}


# In-memory PKCE state storage (state -> flow data)
_pending_flows: dict[str, dict[str, Any]] = {}


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def start_oauth_flow(
    connector_id: str,
    oauth_config: OAuth2Config,
) -> tuple[str, str]:
    """Start an OAuth2 PKCE flow. Returns (authorization_url, state)."""
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    _pending_flows[state] = {
        "connector_id": connector_id,
        "code_verifier": code_verifier,
        "oauth_config": oauth_config,
        "created_at": time.time(),
    }

    params = {
        "client_id": oauth_config.client_id,
        "redirect_uri": oauth_config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(oauth_config.scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items() if v)
    auth_url = f"{oauth_config.authorization_url}?{query}"
    return auth_url, state


def get_pending_flow(state: str) -> dict[str, Any] | None:
    """Retrieve a pending flow by state token."""
    return _pending_flows.get(state)


def complete_flow(state: str) -> None:
    """Remove a completed flow from pending storage."""
    _pending_flows.pop(state, None)


async def exchange_code_for_tokens(
    code: str,
    state: str,
) -> ConnectorCredentials | None:
    """Exchange authorization code for tokens."""
    flow = _pending_flows.get(state)
    if flow is None:
        return None

    oauth_config: OAuth2Config = flow["oauth_config"]
    code_verifier: str = flow["code_verifier"]

    payload = {
        "grant_type": "authorization_code",
        "client_id": oauth_config.client_id,
        "code": code,
        "redirect_uri": oauth_config.redirect_uri,
        "code_verifier": code_verifier,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                oauth_config.token_url,
                data=payload,
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                logger.warning("oauth_token_exchange_failed status=%d body=%s", response.status_code, response.text[:200])
                return None

            data = response.json()
            expires_in = data.get("expires_in")
            expires_at = (time.time() + expires_in) if expires_in else None

            return ConnectorCredentials(
                access_token=data.get("access_token"),
                refresh_token=data.get("refresh_token"),
                token_type=data.get("token_type", "bearer"),
                expires_at=expires_at,
            )
    except Exception:
        logger.warning("oauth_token_exchange_error", exc_info=True)
        return None


async def refresh_oauth2_token(
    oauth_config: OAuth2Config,
    current_creds: ConnectorCredentials,
) -> ConnectorCredentials:
    """Refresh an OAuth2 token using the refresh_token."""
    if not current_creds.refresh_token:
        raise ValueError("No refresh_token available")

    payload = {
        "grant_type": "refresh_token",
        "client_id": oauth_config.client_id,
        "refresh_token": current_creds.refresh_token,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            oauth_config.token_url,
            data=payload,
            headers={"Accept": "application/json"},
        )
        if response.status_code != 200:
            raise ValueError(f"Token refresh failed: {response.status_code}")

        data = response.json()
        expires_in = data.get("expires_in")
        expires_at = (time.time() + expires_in) if expires_in else None

        return ConnectorCredentials(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token") or current_creds.refresh_token,
            token_type=data.get("token_type", "bearer"),
            expires_at=expires_at,
        )
