# PHASE 05 — `llm/` Domain + `llm/routing/`

> **Session-Ziel:** LLM-Client und Model-Routing in eine eigene `llm/` Domäne zusammenführen. `llm/` importiert nur aus `shared/` und `config/`.
>
> **Voraussetzung:** PHASE_04 abgeschlossen
> **Folge-Phase:** PHASE_06_INFRASTRUCTURE.md
> **Geschätzter Aufwand:** ~2 Stunden
> **Betroffene Quelldateien:**
> - `app/llm_client.py`
> - `app/services/model_health_tracker.py`
> - `app/model_routing/router.py`
> - `app/model_routing/model_registry.py`
> - `app/model_routing/capability_profile.py`
> - `app/model_routing/context_window_guard.py`

---

## 1. `app/llm_client.py` → `app/llm/client.py`

```powershell
Copy-Item "backend/app/llm_client.py" "backend/app/llm/client.py"
```

**Imports in `client.py` prüfen:**
```powershell
Select-String -Path "backend/app/llm/client.py" -Pattern "^from app\."
```

`llm/client.py` darf NUR aus `shared/` und `config/` importieren.  
VERBOTEN: Imports aus `agent/`, `tools/`, `transport/` etc.

Falls Typen aus anderen Domänen genutzt werden → `TYPE_CHECKING`:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.agent.head_agent import HeadAgent  # nur für Typcheck
```

**Stub in original:**
```python
# backend/app/llm_client.py
# DEPRECATED: moved to app.llm.client
from app.llm.client import *  # noqa: F401, F403
from app.llm.client import LlmClient  # explicit
```

---

## 2. `services/model_health_tracker.py` → `llm/health_tracker.py`

```powershell
Copy-Item "backend/app/services/model_health_tracker.py" "backend/app/llm/health_tracker.py"
```

**Imports prüfen:** Nur `shared/`, `config/` erlaubt.

**Stub:**
```python
# backend/app/services/model_health_tracker.py — DEPRECATED → app.llm.health_tracker
from app.llm.health_tracker import *  # noqa: F401, F403
```

---

## 3. `model_routing/` → `llm/routing/`

Das gesamte `model_routing/`-Verzeichnis wird nach `llm/routing/` verschoben.

### 3.1 `model_routing/router.py` → `llm/routing/router.py`

```powershell
Copy-Item "backend/app/model_routing/router.py" "backend/app/llm/routing/router.py"
```

**Imports in router.py prüfen:**
```powershell
Select-String -Path "backend/app/llm/routing/router.py" -Pattern "^from app\."
```

Intern darf auf `llm/routing/registry.py`, `llm/routing/capability_profile.py` etc. verweisen.  
Zu fixende Imports:
- `from app.model_routing.model_registry import ...` → `from app.llm.routing.registry import ...`
- `from app.model_routing.capability_profile import ...` → `from app.llm.routing.capability_profile import ...`
- `from app.model_routing.context_window_guard import ...` → `from app.llm.routing.context_window_guard import ...`

**Stub in original:**
```python
# backend/app/model_routing/router.py — DEPRECATED → app.llm.routing.router
from app.llm.routing.router import *  # noqa: F401, F403
```

---

### 3.2 `model_routing/model_registry.py` → `llm/routing/registry.py`

> **WICHTIG:** Der Dateiname ändert sich! `model_registry.py` → `registry.py`

```powershell
Copy-Item "backend/app/model_routing/model_registry.py" "backend/app/llm/routing/registry.py"
```

**Imports prüfen und fixieren.**

**Stub in original:**
```python
# backend/app/model_routing/model_registry.py — DEPRECATED → app.llm.routing.registry
from app.llm.routing.registry import *  # noqa: F401, F403
```

---

### 3.3 `model_routing/capability_profile.py` → `llm/routing/capability_profile.py`

```powershell
Copy-Item "backend/app/model_routing/capability_profile.py" "backend/app/llm/routing/capability_profile.py"
```

**Stub:**
```python
# backend/app/model_routing/capability_profile.py — DEPRECATED → app.llm.routing.capability_profile
from app.llm.routing.capability_profile import *  # noqa: F401, F403
```

---

### 3.4 `model_routing/context_window_guard.py` → `llm/routing/context_window_guard.py`

```powershell
Copy-Item "backend/app/model_routing/context_window_guard.py" "backend/app/llm/routing/context_window_guard.py"
```

**Stub:**
```python
# backend/app/model_routing/context_window_guard.py — DEPRECATED → app.llm.routing.context_window_guard
from app.llm.routing.context_window_guard import *  # noqa: F401, F403
```

---

### 3.5 `model_routing/__init__.py` als Stub anlegen

```python
# backend/app/model_routing/__init__.py
# DEPRECATED: moved to app.llm.routing
from app.llm.routing import *  # noqa: F401, F403
```

---

## 4. `__init__.py` Dateien befüllen

### `llm/routing/__init__.py`

```python
# backend/app/llm/routing/__init__.py
from app.llm.routing.router import ModelRouter
from app.llm.routing.registry import ModelRegistry
from app.llm.routing.capability_profile import CapabilityProfile
from app.llm.routing.context_window_guard import ContextWindowGuard

__all__ = ["ModelRouter", "ModelRegistry", "CapabilityProfile", "ContextWindowGuard"]
```

### `llm/__init__.py`

```python
# backend/app/llm/__init__.py
"""
LLM Client and Model Routing domain.
Only imports from shared/ and config/ — no other domain imports.
"""
from app.llm.client import LlmClient
from app.llm.health_tracker import ModelHealthTracker
from app.llm.routing import ModelRouter, ModelRegistry

__all__ = ["LlmClient", "ModelHealthTracker", "ModelRouter", "ModelRegistry"]
```

---

## 5. Konsumenten-Übersicht (Info für spätere Phasen)

```powershell
# Wer importiert llm_client?
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.llm_client import|from app\.model_routing\." -Recurse | Group-Object Filename | Select-Object Name, Count | Sort-Object Count -Descending
```

> Die Stubs sorgen für Abwärtskompatibilität. Konsumenten werden in Phase 18 aktualisiert.

---

## 6. Verifikation

```powershell
$checks = @(
    "backend/app/llm/__init__.py",
    "backend/app/llm/client.py",
    "backend/app/llm/health_tracker.py",
    "backend/app/llm/routing/__init__.py",
    "backend/app/llm/routing/router.py",
    "backend/app/llm/routing/registry.py",
    "backend/app/llm/routing/capability_profile.py",
    "backend/app/llm/routing/context_window_guard.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.llm import LlmClient, ModelHealthTracker, ModelRouter
from app.llm.routing import ModelRegistry, CapabilityProfile
print('llm/ OK')
"

# Stubs funktionieren noch
python -c "
from app.llm_client import LlmClient
from app.model_routing.router import ModelRouter
print('Stubs OK')
"
```

---

## 7. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate llm/ domain + routing — Phase 05"
```

---

## Status-Checkliste

- [ ] `llm/client.py` erstellt, Imports bereinigt, Stub in `llm_client.py`
- [ ] `llm/health_tracker.py` erstellt, Stub in Original
- [ ] `llm/routing/router.py` erstellt, interne Imports auf neue Pfade geändert, Stub
- [ ] `llm/routing/registry.py` erstellt (Namensänderung von `model_registry.py`!), Stub
- [ ] `llm/routing/capability_profile.py` erstellt, Stub
- [ ] `llm/routing/context_window_guard.py` erstellt, Stub
- [ ] `model_routing/__init__.py` als Stub angelegt
- [ ] `llm/routing/__init__.py` befüllt
- [ ] `llm/__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Stubs für alte Pfade funktionieren
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_06_INFRASTRUCTURE.md](./PHASE_06_INFRASTRUCTURE.md)
