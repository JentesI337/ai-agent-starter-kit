# PHASE 03 — `policy/` Domain

> **Session-Ziel:** Alle Policy-, Security- und Guardrail-Dateien in `app/policy/` konsolidieren. `policy/` importiert nur aus `shared/` — keine anderen Domänen.
>
> **Voraussetzung:** PHASE_01 + PHASE_02 abgeschlossen
> **Folge-Phase:** PHASE_04_STATE.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Quelldateien:** 10 Dateien

---

## Quelldateien → Zieldateien

| Quelldatei | Zieldatei |
|------------|-----------|
| `app/policy_store.py` | `app/policy/store.py` |
| `app/errors.py` (policy-spez. Teile) | `app/policy/errors.py` |
| `app/services/policy_approval_service.py` | `app/policy/approval_service.py` |
| `app/services/circuit_breaker.py` | `app/policy/circuit_breaker.py` |
| `app/services/agent_isolation.py` | `app/policy/agent_isolation.py` |
| `app/services/rate_limiter.py` | `app/policy/rate_limiter.py` |
| `app/services/provisioning_policy.py` | `app/policy/provisioning_policy.py` |
| `app/services/log_secret_filter.py` | `app/policy/log_secret_filter.py` |
| `app/services/error_taxonomy.py` | `app/policy/error_taxonomy.py` |

---

## 1. `app/policy/errors.py` — Fehler-Split aus `errors.py`

**Schritt 1:** Öffne `backend/app/errors.py` und identifiziere policy-spezifische Fehler.  
Typischerweise gehören diese nach `policy/errors.py`:
- `GuardrailViolationError` / `GuardrailViolation`
- `PolicyApprovalCancelledError`
- `RateLimitExceededError`
- `CircuitBreakerOpenError`
- `AgentIsolationError`

Allgemeine Fehler (z.B. `AgentError`, `ToolExecutionError`, `BaseAppError`) bleiben in `shared/errors.py`.

**Schritt 2:** Erstelle `backend/app/policy/errors.py` mit den policy-spezifischen Fehlern:
```python
# backend/app/policy/errors.py
"""Policy and security error types."""
from __future__ import annotations

from app.shared.errors import BaseAppError  # Basis-Import aus shared


class GuardrailViolationError(BaseAppError):
    """Raised when a guardrail policy is violated."""


class PolicyApprovalCancelledError(BaseAppError):
    """Raised when a policy approval request is cancelled."""


# ... weitere policy-spezifische Fehler aus errors.py hier einfügen
```

**Schritt 3:** `shared/errors.py` ergänzen mit Re-Export für Abwärtskompatibilität:
```python
# Am Ende von backend/app/shared/errors.py hinzufügen:
# Policy-specific errors — re-exported for backwards compatibility
# These will be removed from here in PHASE_18 cleanup
from app.policy.errors import GuardrailViolationError, PolicyApprovalCancelledError
```

> **ACHTUNG:** Zirkulären Import prüfen! Wenn `policy/errors.py` aus `shared/errors.py` importiert und `shared/errors.py` von `policy/errors.py` re-exportiert, gibt es einen Zirkel.  
> Lösung: `shared/errors.py` re-exportiert NICHT aus policy/errors. Der Re-Export passiert in Phase 18 durch direkte Umbenennung in allen Konsumenten.

---

## 2. `app/policy_store.py` → `app/policy/store.py`

```powershell
Copy-Item "backend/app/policy_store.py" "backend/app/policy/store.py"
```

**Imports in `store.py` prüfen:**
```powershell
Select-String -Path "backend/app/policy/store.py" -Pattern "^from app\."
```

Erlaubte Imports: `shared/`, `config/` (nur Settings lesen)  
Falls `from app.errors import ...` → ändern zu `from app.shared.errors import ...` oder `from app.policy.errors import ...`

**Stub in original:**
```python
# backend/app/policy_store.py
# DEPRECATED: moved to app.policy.store
from app.policy.store import *  # noqa: F401, F403
```

---

## 3. Services-Dateien kopieren

Für jede der folgenden Dateien: Kopieren, Imports prüfen, Stub erstellen.

### 3.1 `services/policy_approval_service.py` → `policy/approval_service.py`

```powershell
Copy-Item "backend/app/services/policy_approval_service.py" "backend/app/policy/approval_service.py"
```

**Erlaubte Imports:** `shared/`, `config/`, `policy/` (interne Querverweise)  
**VERBOTEN:** Imports aus `agent/`, `tools/`, `transport/` o.ä.

```powershell
Select-String -Path "backend/app/policy/approval_service.py" -Pattern "^from app\."
```

Zu fixende Imports:
- `from app.errors import ...` → `from app.policy.errors import ...`
- `from app.services.policy_approval_service import ...` (intern) → nicht nötig

**Stub:**
```python
# backend/app/services/policy_approval_service.py — DEPRECATED → app.policy.approval_service
from app.policy.approval_service import *  # noqa: F401, F403
```

---

### 3.2 `services/circuit_breaker.py` → `policy/circuit_breaker.py`

```powershell
Copy-Item "backend/app/services/circuit_breaker.py" "backend/app/policy/circuit_breaker.py"
```

**Imports prüfen:** Nur `shared/`, `config/` erlaubt.

**Stub:**
```python
# backend/app/services/circuit_breaker.py — DEPRECATED → app.policy.circuit_breaker
from app.policy.circuit_breaker import *  # noqa: F401, F403
```

---

### 3.3 `services/agent_isolation.py` → `policy/agent_isolation.py`

```powershell
Copy-Item "backend/app/services/agent_isolation.py" "backend/app/policy/agent_isolation.py"
```

> **HINWEIS:** `agent_isolation.py` könnte Typen aus `agent/` importieren. Falls ja:  
> - Diese Typen müssen in `contracts/` oder `shared/` extrahiert werden  
> - ODER der Import bleibt als `TYPE_CHECKING`-only Import:
> ```python
> from __future__ import annotations
> from typing import TYPE_CHECKING
> if TYPE_CHECKING:
>     from app.agent.record import AgentRecord  # nur für Typcheck, kein Runtime-Import
> ```

**Stub:**
```python
# backend/app/services/agent_isolation.py — DEPRECATED → app.policy.agent_isolation
from app.policy.agent_isolation import *  # noqa: F401, F403
```

---

### 3.4 `services/rate_limiter.py` → `policy/rate_limiter.py`

```powershell
Copy-Item "backend/app/services/rate_limiter.py" "backend/app/policy/rate_limiter.py"
```

**Stub:**
```python
# backend/app/services/rate_limiter.py — DEPRECATED → app.policy.rate_limiter
from app.policy.rate_limiter import *  # noqa: F401, F403
```

---

### 3.5 `services/provisioning_policy.py` → `policy/provisioning_policy.py`

```powershell
Copy-Item "backend/app/services/provisioning_policy.py" "backend/app/policy/provisioning_policy.py"
```

**Stub:**
```python
# backend/app/services/provisioning_policy.py — DEPRECATED → app.policy.provisioning_policy
from app.policy.provisioning_policy import *  # noqa: F401, F403
```

---

### 3.6 `services/log_secret_filter.py` → `policy/log_secret_filter.py`

```powershell
Copy-Item "backend/app/services/log_secret_filter.py" "backend/app/policy/log_secret_filter.py"
```

**Stub:**
```python
# backend/app/services/log_secret_filter.py — DEPRECATED → app.policy.log_secret_filter
from app.policy.log_secret_filter import *  # noqa: F401, F403
```

---

### 3.7 `services/error_taxonomy.py` → `policy/error_taxonomy.py`

```powershell
Copy-Item "backend/app/services/error_taxonomy.py" "backend/app/policy/error_taxonomy.py"
```

**Imports prüfen:** Soll `shared/errors` oder `policy/errors` importieren — nicht `services/`.

**Stub:**
```python
# backend/app/services/error_taxonomy.py — DEPRECATED → app.policy.error_taxonomy
from app.policy.error_taxonomy import *  # noqa: F401, F403
```

---

## 4. `app/policy/__init__.py` befüllen

```python
# backend/app/policy/__init__.py
"""
Policy, Security and Guardrails domain.
Only imports from shared/ and config/ — no other domain imports.
"""
from app.policy.errors import GuardrailViolationError, PolicyApprovalCancelledError
from app.policy.store import PolicyStore
from app.policy.circuit_breaker import CircuitBreaker
from app.policy.rate_limiter import RateLimiter
from app.policy.log_secret_filter import LogSecretFilter

__all__ = [
    "GuardrailViolationError",
    "PolicyApprovalCancelledError",
    "PolicyStore",
    "CircuitBreaker",
    "RateLimiter",
    "LogSecretFilter",
]
```

> Passe Klassen-Namen nach Lektüre der Dateien an.

---

## 5. Zirkular-Import-Check

```powershell
cd backend
python -c "
import sys
# check no circular imports
from app.policy import (
    GuardrailViolationError, PolicyApprovalCancelledError,
    PolicyStore, CircuitBreaker, RateLimiter, LogSecretFilter
)
from app.policy.approval_service import *
from app.policy.agent_isolation import *
from app.policy.provisioning_policy import *
from app.policy.error_taxonomy import *
print('policy/ imports OK')
"
```

---

## 6. Verifikation

```powershell
$checks = @(
    "backend/app/policy/__init__.py",
    "backend/app/policy/errors.py",
    "backend/app/policy/store.py",
    "backend/app/policy/approval_service.py",
    "backend/app/policy/circuit_breaker.py",
    "backend/app/policy/agent_isolation.py",
    "backend/app/policy/rate_limiter.py",
    "backend/app/policy/provisioning_policy.py",
    "backend/app/policy/log_secret_filter.py",
    "backend/app/policy/error_taxonomy.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

# Stubs in Originalen
Select-String "backend/app/policy_store.py" -Pattern "DEPRECATED"
```

---

## 7. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate policy/ domain — Phase 03"
```

---

## Status-Checkliste

- [ ] `policy/errors.py` erstellt (policy-spezifische Fehler aus `errors.py` extrahiert)
- [ ] `policy/store.py` erstellt, Stub in Original
- [ ] `policy/approval_service.py` erstellt, Imports bereinigt, Stub in Original
- [ ] `policy/circuit_breaker.py` erstellt, Stub in Original
- [ ] `policy/agent_isolation.py` erstellt, TYPE_CHECKING-Workaround falls nötig, Stub in Original
- [ ] `policy/rate_limiter.py` erstellt, Stub in Original
- [ ] `policy/provisioning_policy.py` erstellt, Stub in Original
- [ ] `policy/log_secret_filter.py` erstellt, Stub in Original
- [ ] `policy/error_taxonomy.py` erstellt, Stub in Original
- [ ] `policy/__init__.py` befüllt
- [ ] Kein Zirkular-Import
- [ ] Smoke-Test `python -c "from app.policy import ..."` erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_04_STATE.md](./PHASE_04_STATE.md)
