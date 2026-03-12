# PHASE 20 — `connectors/` — Import-Bereinigung & DDD-Einordnung

> **Session-Ziel:** Das `connectors/`-Verzeichnis (11 Dateien) DDD-konform machen. Imports auf neue Pfade aktualisieren, Credential-Store mit `policy/` absichern, OAuth2-Flow isolieren, und `__init__.py` mit einer sauberen öffentlichen API ausstatten.
>
> **Voraussetzung:** PHASE_03 (policy/), PHASE_04 (state/), PHASE_01 (shared/)
> **Folge-Phase:** PHASE_21_OLD_DIRS_REMOVAL.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Dateien:** `backend/app/connectors/` (11 Dateien)

---

## Ist-Zustand

```
backend/app/connectors/
├── __init__.py
├── base.py                — Basis-Klasse für alle Connectors
├── registry.py            — Connector-Registry
├── connector_store.py     — Persistenz von Connector-Konfigurationen
├── credential_store.py    — Sichere Credential-Verwaltung
├── generic_rest_connector.py  — Generischer REST-Connector
├── oauth2_flow.py         — OAuth2-Authentifizierungs-Flow
├── github_connector.py    — GitHub-Integration
├── google_connector.py    — Google-Integration
├── jira_connector.py      — Jira-Integration
├── slack_connector.py     — Slack-Integration
└── x_connector.py         — X (Twitter)-Integration
```

---

## Domain-Grenzen für `connectors/`

```
connectors/ DARF importieren:
  ✅ app.shared.*                — Utilities, IDGen, EventBus
  ✅ app.contracts.*             — BaseContract, ConnectorContract
  ✅ app.config.*                — API-Keys, Base-URLs
  ✅ app.policy.*                — Credential-Zugriff prüfen
  ✅ app.state.state_store       — Connector-State speichern

connectors/ DARF NICHT importieren:
  ❌ app.transport.*             — HTTP-Transport ist extern
  ❌ app.agent.*                 — Connector kennt keinen Agent
  ❌ app.tools.*                 — Tools nutzen Connectors, nicht umgekehrt
  ❌ app.services.*              — Alter Monolith
  ❌ app.workflows.*             — Workflows nutzen Connectors, nicht umgekehrt
  ❌ app.orchestration.*         — Orchestration ist extern
```

---

## Schritt 1: Import-Audit

```powershell
cd backend

Select-String -Path "app/connectors/*.py" -Pattern "^from|^import" |
    Select-Object Filename, LineNumber, Line |
    Format-Table -AutoSize
```

---

## Schritt 2: `base.py` — Basis-Connector-Klasse

Ziel-Struktur für `base.py`:

```python
# backend/app/connectors/base.py
"""Base class for all external connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.contracts.connector_contract import ConnectorContract  # falls existiert
from app.shared.logging import get_logger

log = get_logger(__name__)


class BaseConnector(ABC):
    """Abstract base for all external service connectors."""

    connector_id: str
    display_name: str

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

**Reparaturen:**
```python
# ALT
from app.services.connector_service import BaseConnector
# NEU — Klasse ist hier definitiv in base.py
class BaseConnector(ABC): ...

# ALT
from app.interfaces.request_context import RequestContext
# NEU
from app.contracts.request_context import RequestContext
```

---

## Schritt 3: `credential_store.py` — Sicherheits-Audit

⚠️ **SICHERHEITSKRITISCH:** Credentials müssen verschlüsselt gespeichert werden.

```powershell
# Prüfen ob Verschlüsselung bereits vorhanden
Select-String -Path "app/connectors/credential_store.py" -Pattern "encrypt|decrypt|fernet|cryptography|secrets"
```

**Falls keine Verschlüsselung vorhanden:**
```python
# backend/app/connectors/credential_store.py — Sicherheits-Erweiterung
from cryptography.fernet import Fernet
from app.config.settings import get_settings

class CredentialStore:
    def __init__(self):
        settings = get_settings()
        # Key MUSS aus Config kommen, nie hardcoded!
        self._fernet = Fernet(settings.credential_encryption_key.encode())

    def store(self, connector_id: str, credentials: dict) -> None:
        import json
        raw = json.dumps(credentials).encode()
        encrypted = self._fernet.encrypt(raw)
        # Persistenz via state_store oder separater DB
        ...

    def retrieve(self, connector_id: str) -> dict:
        encrypted = ...  # aus Persistenz
        raw = self._fernet.decrypt(encrypted)
        import json
        return json.loads(raw)
```

**Import-Reparaturen für `credential_store.py`:**
```python
# ALT
from app.services.credential_service import CredentialService
# NEU
from app.policy.access_control import check_credential_access
from app.config.settings import get_settings
from app.state.state_store import StateStore
```

---

## Schritt 4: `registry.py` — Connector-Registry

```python
# ALT
from app.services.connector_registry import ConnectorRegistry
# NEU — selbst Registry sein

# ALT
from app.services.plugin_service import PluginRegistry
# NEU
from app.shared.registry import BaseRegistry  # falls shared/registry.py existiert
```

---

## Schritt 5: `oauth2_flow.py` — OAuth2 Isolation

OAuth2 darf keine HTTP-Routen kennen. Es empfängt Callback-Daten als Parameter:

```python
# ALT (falsch — importiert Transport-Layer direkt)
from fastapi import Request
from app.routers.oauth_router import oauth_callback_url
# NEU — callback URL als Parameter
class OAuth2Flow:
    def __init__(self, callback_url: str, client_id: str, client_secret: str): ...
    
    async def get_authorization_url(self) -> str: ...
    
    async def exchange_code(self, code: str, state: str) -> dict: ...
```

**Transport-Layer-Trennung:**
- `oauth2_flow.py` — Pure OAuth2-Logik, keine FastAPI-Imports
- `transport/routers/connectors.py` — HTTP-Routen die `OAuth2Flow` aufrufen

---

## Schritt 6: Einzelne Connector-Reparaturen

### `github_connector.py`
```python
# ALT
from app.services.github_service import GithubService
# NEU — direkt requests/httpx
import httpx
from app.connectors.credential_store import CredentialStore
from app.connectors.base import BaseConnector
```

### `google_connector.py`
```python
# ALT
from app.services.google_service import GoogleService
# NEU
import httpx
from app.connectors.credential_store import CredentialStore
from app.connectors.base import BaseConnector
```

### `slack_connector.py`
```python
# ALT
from app.services.slack_service import SlackService
# NEU
import httpx
from app.connectors.credential_store import CredentialStore
from app.connectors.base import BaseConnector
```

### Gleiches Muster für `jira_connector.py` und `x_connector.py`.

---

## Schritt 7: `__init__.py` aktualisieren

```python
# backend/app/connectors/__init__.py
"""
connectors — External Service Integration Domain.

Manages connections to external APIs and services.
  - BaseConnector:           Abstract base for all connectors
  - ConnectorRegistry:       Discovers and instantiates connectors
  - ConnectorStore:          Persists connector configurations
  - CredentialStore:         Encrypted credential storage
  - OAuth2Flow:              OAuth2 authentication flow (transport-agnostic)
  - GenericRESTConnector:    Configurable REST API connector
  - GitHubConnector:         GitHub API integration
  - GoogleConnector:         Google API integration
  - JiraConnector:           Jira API integration
  - SlackConnector:          Slack API integration
  - XConnector:              X (Twitter) API integration

HTTP routes for connector management live in:
  app.transport.routers.connectors

Allowed imports FROM:
  shared, contracts, config, policy, state

NOT allowed:
  transport, agent, tools, workflows, orchestration, services (deprecated)
"""

from app.connectors.base import BaseConnector
from app.connectors.registry import ConnectorRegistry
from app.connectors.connector_store import ConnectorStore
from app.connectors.credential_store import CredentialStore
from app.connectors.oauth2_flow import OAuth2Flow
from app.connectors.generic_rest_connector import GenericRESTConnector
from app.connectors.github_connector import GitHubConnector
from app.connectors.google_connector import GoogleConnector
from app.connectors.jira_connector import JiraConnector
from app.connectors.slack_connector import SlackConnector
from app.connectors.x_connector import XConnector

__all__ = [
    "BaseConnector",
    "ConnectorRegistry",
    "ConnectorStore",
    "CredentialStore",
    "OAuth2Flow",
    "GenericRESTConnector",
    "GitHubConnector",
    "GoogleConnector",
    "JiraConnector",
    "SlackConnector",
    "XConnector",
]
```

---

## Verifikation

```powershell
cd backend

# 1. Imports OK
python -c "
from app.connectors import (
    BaseConnector, ConnectorRegistry, CredentialStore, OAuth2Flow,
    GenericRESTConnector, GitHubConnector
)
print('connectors imports OK')
"

# 2. Keine alten Imports
Select-String -Path "app/connectors/*.py" -Pattern "from app\.services\.|from app\.routers\.|from app\.handlers\." |
    Select-Object Filename, LineNumber, Line

# 3. Sicherheits-Check: Keine hardcodierten Secrets
Select-String -Path "app/connectors/*.py" -Pattern "password\s*=\s*['\"]|secret\s*=\s*['\"]|api_key\s*=\s*['\"]" |
    Select-Object Filename, LineNumber, Line

# 4. Tests
python -m pytest tests/ -k "connector" -q --tb=short 2>&1 | Select-Object -First 40
```

---

## Commit

```bash
git add -A
git commit -m "refactor(ddd): update connectors imports, secure credentials — Phase 20"
```

---

## Status-Checkliste

- [ ] Import-Audit für alle 11 Dateien
- [ ] `base.py` aufgeräumt
- [ ] `credential_store.py` verwendet Verschlüsselung
- [ ] `registry.py` imports aktualisiert
- [ ] `connector_store.py` imports aktualisiert
- [ ] `oauth2_flow.py` hat keine FastAPI/Transport-Imports
- [ ] `generic_rest_connector.py` imports aktualisiert
- [ ] `github_connector.py` imports aktualisiert
- [ ] `google_connector.py` imports aktualisiert
- [ ] `jira_connector.py` imports aktualisiert
- [ ] `slack_connector.py` imports aktualisiert
- [ ] `x_connector.py` imports aktualisiert
- [ ] `__init__.py` clean public API
- [ ] Kein Import aus `app.services.*` mehr
- [ ] Keine hardcodierten Credentials
- [ ] Tests laufen durch
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_21_OLD_DIRS_REMOVAL.md](./PHASE_21_OLD_DIRS_REMOVAL.md)
