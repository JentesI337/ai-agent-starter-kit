# PHASE 01 — `shared/` + `contracts/` (Foundation)

> **Session-Ziel:** Die Fundament-Module verschieben. `shared/` und `contracts/` haben **keine Imports aus anderen App-Domänen** — sie sind sicher als erstes zu migrieren. Nach dieser Phase funktionieren alle Importe aus `shared/` und `contracts/` am neuen Ort.
>
> **Voraussetzung:** PHASE_00 abgeschlossen (Verzeichnisse existieren)
> **Folge-Phase:** PHASE_02_CONFIG.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Dateien:** 9 Quelldateien → 9 Zieldateien

---

## Goldene Regel für diese Phase

`shared/` und `contracts/` dürfen **NIEMALS** aus Domänen-Modulen importieren.  
Erlaubte Importe: `typing`, `pydantic`, `datetime`, `uuid`, externe Bibliotheken, Standard-Library.

---

## 1. `app/shared/` — Aufbau

### 1.1 `app/control_models.py` → `app/shared/control_models.py`

**Aktion:** Datei kopieren (nicht löschen – die alte bleibt als Stub), Imports in der Datei selbst prüfen.

```powershell
Copy-Item "backend/app/control_models.py" "backend/app/shared/control_models.py"
```

**Nach dem Kopieren:** Öffne `backend/app/shared/control_models.py` und prüfe alle `from app.` Imports.  
Erlaubt: nur `from app.shared.` oder externe Bibliotheken.  
Falls `from app.errors import ...` → ändern zu `from app.shared.errors import ...` (aber erst wenn Phase 01 Schritt 1.2 fertig ist).

**Stub in original erstellen** (damit alte Importe noch funktionieren bis zum Cleanup in Phase 18):
```python
# backend/app/control_models.py
# DEPRECATED: moved to app.shared.control_models
# Remove this file in PHASE_18
from app.shared.control_models import *  # noqa: F401, F403
```

---

### 1.2 `app/errors.py` → `app/shared/errors.py`

**Aktion:** Kopieren.

```powershell
Copy-Item "backend/app/errors.py" "backend/app/shared/errors.py"
```

> **ACHTUNG:** `app/errors.py` enthält sowohl allgemeine Basis-Fehler ALS AUCH bereits policy-spezifische Fehler (GuardrailViolation, PolicyApprovalCancelledError). Diese policy-spezifischen Fehler werden in **Phase 03** nach `app/policy/errors.py` wandern. Für jetzt: alles in `shared/errors.py` belassen. In Phase 03 wird `policy/errors.py` diese re-exportieren oder ein refactoring vornehmen.

**Stub in original:**
```python
# backend/app/errors.py
# DEPRECATED: moved to app.shared.errors (base errors) and app.policy.errors (policy errors)
# Remove this file in PHASE_18
from app.shared.errors import *  # noqa: F401, F403
```

---

### 1.3 `app/services/idempotency_manager.py` → `app/shared/idempotency/manager.py`

```powershell
Copy-Item "backend/app/services/idempotency_manager.py" "backend/app/shared/idempotency/manager.py"
```

**Imports in `idempotency_manager.py` prüfen:** Suche nach `from app.` und stelle sicher, dass nur `shared/`-konforme Imports vorhanden sind.

```powershell
Select-String -Path "backend/app/shared/idempotency/manager.py" -Pattern "^from app\."
```

**Stub in original:**
```python
# backend/app/services/idempotency_manager.py — DEPRECATED → app.shared.idempotency.manager
from app.shared.idempotency.manager import *  # noqa: F401, F403
```

---

### 1.4 `app/services/idempotency_service.py` → `app/shared/idempotency/service.py`

```powershell
Copy-Item "backend/app/services/idempotency_service.py" "backend/app/shared/idempotency/service.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/shared/idempotency/service.py" -Pattern "^from app\."
```

Wenn `from app.services.idempotency_manager import ...` → ersetzen durch `from app.shared.idempotency.manager import ...`

**Stub in original:**
```python
# backend/app/services/idempotency_service.py — DEPRECATED → app.shared.idempotency.service
from app.shared.idempotency.service import *  # noqa: F401, F403
```

---

### 1.5 `app/shared/__init__.py` befüllen

```python
# backend/app/shared/__init__.py
"""
Shared cross-cutting types and utilities.
NO domain imports allowed here.
"""
```

### 1.6 `app/shared/idempotency/__init__.py` befüllen

```python
# backend/app/shared/idempotency/__init__.py
from app.shared.idempotency.manager import IdempotencyManager
from app.shared.idempotency.service import IdempotencyService

__all__ = ["IdempotencyManager", "IdempotencyService"]
```

---

## 2. `app/contracts/` — Ergänzungen

Die Basisdateien existieren bereits (`agent_contract.py`, `schemas.py`, `tool_protocol.py`).  
Wir fügen zwei neue hinzu:

### 2.1 `app/interfaces/orchestrator_api.py` + `app/interfaces/request_context.py` → `app/contracts/orchestrator_api.py` (MERGE)

**Schritt 1:** Inhalt beider Interface-Dateien lesen:
```powershell
Get-Content "backend/app/interfaces/orchestrator_api.py"
Get-Content "backend/app/interfaces/request_context.py"
```

**Schritt 2:** Neue Datei `backend/app/contracts/orchestrator_api.py` erstellen, die beide Inhalte zusammenführt:
- Alle Klassen/Protokolle aus `orchestrator_api.py` übernehmen
- Alle Klassen/Protokolle aus `request_context.py` übernehmen
- Duplikate entfernen
- Imports bereinigen: nur typing / shared

**Schritt 3:** Stubs in den Originalen:
```python
# backend/app/interfaces/orchestrator_api.py — DEPRECATED → app.contracts.orchestrator_api
from app.contracts.orchestrator_api import *  # noqa: F401, F403
```
```python
# backend/app/interfaces/request_context.py — DEPRECATED → app.contracts.orchestrator_api
from app.contracts.orchestrator_api import *  # noqa: F401, F403
```

---

### 2.2 `app/services/hook_contract.py` → `app/contracts/hook_contract.py`

```powershell
Copy-Item "backend/app/services/hook_contract.py" "backend/app/contracts/hook_contract.py"
```

**Imports prüfen:** Nur typing/shared erlaubt.

**Stub:**
```python
# backend/app/services/hook_contract.py — DEPRECATED → app.contracts.hook_contract
from app.contracts.hook_contract import *  # noqa: F401, F403
```

---

### 2.3 `app/contracts/__init__.py` befüllen

```python
# backend/app/contracts/__init__.py
"""
Protocol interfaces and ABCs.
No domain imports — only typing and shared.
"""
from app.contracts.agent_contract import AgentContract  # bereits vorhanden
from app.contracts.schemas import *  # bereits vorhanden
from app.contracts.tool_protocol import ToolProvider  # bereits vorhanden
from app.contracts.orchestrator_api import *  # neu
from app.contracts.hook_contract import *  # neu
```

> Passe die konkreten Klassen-/Protokoll-Namen nach Lektüre der Dateien an.

---

## 3. Import-Rewrites für Konsumenten

Finde alle Dateien, die die alten Pfade importieren:

```powershell
# Konsumenten von errors.py finden
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.errors import" -Recurse | Select-Object Filename, LineNumber, Line

# Konsumenten von control_models.py finden
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.control_models import" -Recurse | Select-Object Filename, LineNumber, Line

# Konsumenten von interfaces/ finden
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.interfaces\." -Recurse | Select-Object Filename, LineNumber, Line

# Konsumenten von idempotency finden
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.services\.(idempotency)" -Recurse | Select-Object Filename, LineNumber, Line
```

> **Strategie:** Da wir Stubs belassen, müssen Konsumenten in Phase 01 NICHT sofort geändert werden.  
> Der endgültige Import-Rewrite aller Konsumenten erfolgt in **Phase 18** (Final Cleanup).  
> **Ausnahme:** Wenn eine Datei in einer späteren Phase verschoben wird, werden ihre Imports dann aktualisiert.

---

## 4. Verifikation

```powershell
# 1. Neue Dateien existieren
$checks = @(
    "backend/app/shared/control_models.py",
    "backend/app/shared/errors.py",
    "backend/app/shared/idempotency/manager.py",
    "backend/app/shared/idempotency/service.py",
    "backend/app/contracts/orchestrator_api.py",
    "backend/app/contracts/hook_contract.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

# 2. Stubs in den Originalen vorhanden
Select-String -Path "backend/app/errors.py" -Pattern "DEPRECATED"
Select-String -Path "backend/app/control_models.py" -Pattern "DEPRECATED"

# 3. Smoke-Test: Python kann importieren
cd backend
python -c "from app.shared.errors import *; from app.shared.control_models import *; from app.contracts.orchestrator_api import *; print('OK')"
```

---

## 5. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate shared/ and contracts/ — Phase 01"
```

---

## Status-Checkliste

- [ ] `shared/control_models.py` erstellt, Stub in Original
- [ ] `shared/errors.py` erstellt, Stub in Original
- [ ] `shared/idempotency/manager.py` erstellt, Imports bereinigt, Stub in Original
- [ ] `shared/idempotency/service.py` erstellt, Imports bereinigt, Stub in Original
- [ ] `contracts/orchestrator_api.py` — Merge aus interfaces/ completed
- [ ] `contracts/hook_contract.py` erstellt, Stub in Original
- [ ] `contracts/__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_02_CONFIG.md](./PHASE_02_CONFIG.md)
