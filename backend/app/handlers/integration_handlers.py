"""Handlers for integration/connector management endpoints."""
from __future__ import annotations

import logging
import time
from typing import Any

from app.connectors.base import ConnectorConfig, ConnectorCredentials
from app.connectors.connector_store import ConnectorStore
from app.connectors.credential_store import CredentialStore
from app.connectors.oauth2_flow import (
    OAuth2Config,
    OAUTH2_PRESETS,
    complete_flow,
    exchange_code_for_tokens,
    get_pending_flow,
    start_oauth_flow,
)
from app.connectors.registry import ConnectorRegistry
from app.url_validator import UrlValidationError, enforce_safe_url

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]

# Module-level dependencies
_connector_store: ConnectorStore | None = None
_credential_store: CredentialStore | None = None
_connector_registry: ConnectorRegistry | None = None

# Track completed OAuth flows
_completed_oauth: dict[str, bool] = {}


def configure(
    connector_store: ConnectorStore,
    credential_store: CredentialStore,
    connector_registry: ConnectorRegistry,
) -> None:
    global _connector_store, _credential_store, _connector_registry
    _connector_store = connector_store
    _credential_store = credential_store
    _connector_registry = connector_registry


def _require_stores() -> tuple[ConnectorStore, CredentialStore, ConnectorRegistry]:
    if _connector_store is None or _credential_store is None or _connector_registry is None:
        raise RuntimeError("Integration handlers not configured")
    return _connector_store, _credential_store, _connector_registry


def handle_connectors_list(request: JsonDict) -> JsonDict:
    cs, cred_s, reg = _require_stores()
    configs = cs.get_all()
    connectors = []
    for cid, cfg in configs.items():
        has_creds = cred_s.has(cid)
        try:
            conn = reg.create_connector(cfg)
            methods = conn.available_methods()
        except Exception:
            methods = []
        connectors.append({
            "connector_id": cid,
            "connector_type": cfg.connector_type,
            "display_name": cfg.display_name,
            "base_url": cfg.base_url,
            "auth_type": cfg.auth_type,
            "has_credentials": has_creds,
            "available_methods": methods,
            "rate_limit_rps": cfg.rate_limit_rps,
            "rate_limit_burst": cfg.rate_limit_burst,
            "auto_refresh_token": cfg.auto_refresh_token,
        })
    return {"connectors": connectors}


def handle_connectors_get(request: JsonDict) -> JsonDict:
    cs, cred_s, reg = _require_stores()
    cid = request.get("connector_id", "")
    cfg = cs.get(cid)
    if cfg is None:
        return {"error": f"Connector '{cid}' not found"}
    has_creds = cred_s.has(cid)
    try:
        conn = reg.create_connector(cfg)
        methods = conn.available_methods()
    except Exception:
        methods = []
    return {
        "connector": {
            **cfg.model_dump(),
            "has_credentials": has_creds,
            "available_methods": methods,
        }
    }


def handle_connectors_create(request: JsonDict) -> JsonDict:
    cs, cred_s, reg = _require_stores()
    try:
        config = ConnectorConfig.model_validate(request)
    except Exception as exc:
        return {"error": f"Invalid connector config: {exc}"}

    # Validate base URL
    try:
        enforce_safe_url(config.base_url, label="Connector base_url")
    except UrlValidationError as exc:
        return {"error": f"Invalid base_url: {exc}"}

    # Check type is valid
    if config.connector_type not in reg.supported_types():
        return {"error": f"Unknown connector type: {config.connector_type}. Supported: {reg.supported_types()}"}

    # Store API key if provided
    api_key = request.get("api_key")
    if api_key:
        creds = ConnectorCredentials(api_key=api_key)
        extra = request.get("credentials_extra", {})
        if extra and isinstance(extra, dict):
            creds.extra = extra
        cred_s.store(config.connector_id, creds)

    cs.upsert(config)
    return {"connector": config.model_dump()}


def handle_connectors_update(request: JsonDict) -> JsonDict:
    cs, cred_s, _ = _require_stores()
    cid = request.get("connector_id", "")
    existing = cs.get(cid)
    if existing is None:
        return {"error": f"Connector '{cid}' not found"}

    updates = {k: v for k, v in request.items() if k != "connector_id" and k != "api_key" and k != "credentials_extra"}
    merged = existing.model_dump()
    merged.update(updates)
    try:
        config = ConnectorConfig.model_validate(merged)
    except Exception as exc:
        return {"error": f"Invalid update: {exc}"}

    # Update API key if provided
    api_key = request.get("api_key")
    if api_key:
        creds = ConnectorCredentials(api_key=api_key)
        extra = request.get("credentials_extra", {})
        if extra and isinstance(extra, dict):
            creds.extra = extra
        cred_s.store(cid, creds)

    cs.upsert(config)
    return {"connector": config.model_dump()}


def handle_connectors_delete(request: JsonDict) -> JsonDict:
    cs, cred_s, _ = _require_stores()
    cid = request.get("connector_id", "")
    cs.delete(cid)
    cred_s.delete(cid)
    return {"ok": True}


async def handle_connectors_test(request: JsonDict) -> JsonDict:
    cs, cred_s, reg = _require_stores()
    cid = request.get("connector_id", "")
    config = cs.get(cid)
    if config is None:
        return {"ok": False, "error": f"Connector '{cid}' not found", "latency_ms": 0}

    credentials = cred_s.retrieve(cid)
    try:
        conn = reg.create_connector(config, credentials)
        methods = conn.available_methods()
        if not methods:
            return {"ok": False, "error": "No methods available", "latency_ms": 0}

        # Use first read-only method for testing
        test_method = methods[0]["name"]
        start = time.monotonic()
        result = await conn.call(test_method, {})
        elapsed_ms = round((time.monotonic() - start) * 1000)

        status = result.get("status_code", 0)
        if status == 0:
            return {"ok": False, "error": result.get("error", "Unknown error"), "latency_ms": elapsed_ms}
        if 200 <= status < 400:
            return {"ok": True, "latency_ms": elapsed_ms}
        return {"ok": False, "error": f"HTTP {status}", "latency_ms": elapsed_ms}

    except Exception as exc:
        return {"ok": False, "error": str(exc), "latency_ms": 0}


def handle_oauth_start(request: JsonDict) -> JsonDict:
    cs, _, _ = _require_stores()
    cid = request.get("connector_id", "")
    config = cs.get(cid)
    if config is None:
        return {"error": f"Connector '{cid}' not found"}

    client_id = config.oauth2_client_id or request.get("client_id", "")
    if not client_id:
        return {"error": "No OAuth2 client_id configured for this connector"}

    preset = OAUTH2_PRESETS.get(config.connector_type, {})
    if not preset:
        return {"error": f"No OAuth2 preset for connector type '{config.connector_type}'"}

    oauth_config = OAuth2Config(
        client_id=client_id,
        scopes=config.oauth2_scopes,
        **preset,
    )

    auth_url, state = start_oauth_flow(cid, oauth_config)
    return {"authorization_url": auth_url, "state": state}


async def handle_oauth_callback(code: str, state: str) -> str:
    """Handle the OAuth callback redirect. Returns HTML response."""
    _, cred_s, _ = _require_stores()

    flow = get_pending_flow(state)
    if flow is None:
        return "<html><body><h2>Error: Invalid or expired OAuth state.</h2></body></html>"

    credentials = await exchange_code_for_tokens(code, state)
    if credentials is None:
        return "<html><body><h2>Error: Failed to exchange code for tokens.</h2></body></html>"

    connector_id = flow["connector_id"]
    cred_s.store(connector_id, credentials)
    complete_flow(state)
    _completed_oauth[connector_id] = True

    return (
        "<html><body>"
        "<h2>Authentication successful!</h2>"
        "<p>You can close this tab and return to the application.</p>"
        "<script>window.close();</script>"
        "</body></html>"
    )


def handle_oauth_status(request: JsonDict) -> JsonDict:
    cid = request.get("connector_id", "")
    complete = _completed_oauth.pop(cid, False)
    if not complete:
        _, cred_s, _ = _require_stores()
        complete = cred_s.has(cid)
    return {"complete": complete}
