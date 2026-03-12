# PHASE 04 — `state/` Domain (Ergänzung)

> **Session-Ziel:** `app/state/` existiert bereits mit 3 Dateien. Diese Phase fügt `state/encryption.py` hinzu und bereinigt die `__init__.py`.
>
> **Voraussetzung:** PHASE_03 abgeschlossen
> **Folge-Phase:** PHASE_05_LLM.md
> **Geschätzter Aufwand:** ~1 Stunde
> **Betroffene Quelldateien:** 1 neue Datei + __init__.py-Bereinigung

---

## Ist-Zustand `app/state/`

```
backend/app/state/
├── snapshots.py      ← bereits vorhanden ✓
├── state_store.py    ← bereits vorhanden ✓
├── task_graph.py     ← bereits vorhanden ✓
└── __init__.py       ← prüfen und befüllen
```

Fehlend:
- `encryption.py` ← aus `services/state_encryption.py`

---

## 1. `services/state_encryption.py` → `state/encryption.py`

```powershell
Copy-Item "backend/app/services/state_encryption.py" "backend/app/state/encryption.py"
```

**Imports in `encryption.py` prüfen:**
```powershell
Select-String -Path "backend/app/state/encryption.py" -Pattern "^from app\."
```

`state/` darf nur aus `shared/` importieren — keine anderen App-Domänen.  
Falls `from app.config import settings` → erlaubt (config ist Leaf-Domain).

**Stub in original:**
```python
# backend/app/services/state_encryption.py — DEPRECATED → app.state.encryption
from app.state.encryption import *  # noqa: F401, F403
```

---

## 2. Bestehende `state/` Dateien prüfen

Prüfe die bestehenden Dateien auf falsche Imports:

```powershell
# Imports in state/ prüfen — dürfen nur shared/ und config/ nutzen
Select-String -Path "backend/app/state/*.py" -Pattern "^from app\." | Where-Object { $_.Line -notmatch "app\.shared|app\.config" }
```

**Erwartet:** Keine verbotenen Imports. Falls doch welche gefunden werden, dokumentieren und in Phase 18 fixen.

---

## 3. `app/state/__init__.py` befüllen

```python
# backend/app/state/__init__.py
"""
State persistence domain.
Only imports from shared/ and config/ — no other domain imports.
"""
from app.state.state_store import StateStore
from app.state.snapshots import SnapshotManager
from app.state.task_graph import TaskGraph
from app.state.encryption import StateEncryption

__all__ = ["StateStore", "SnapshotManager", "TaskGraph", "StateEncryption"]
```

> Passe Klassen-Namen nach Lektüre der Dateien an.

---

## 4. Verifikation

```powershell
$checks = @(
    "backend/app/state/__init__.py",
    "backend/app/state/state_store.py",
    "backend/app/state/snapshots.py",
    "backend/app/state/task_graph.py",
    "backend/app/state/encryption.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

# Import-Test
cd backend
python -c "
from app.state import StateStore, SnapshotManager, TaskGraph, StateEncryption
print('state/ OK')
"
```

---

## 5. Commit

```bash
git add -A
git commit -m "refactor(ddd): complete state/ domain with encryption — Phase 04"
```

---

## Status-Checkliste

- [ ] `state/encryption.py` erstellt, Stub in Original
- [ ] Bestehende state/-Dateien auf verbotene Imports geprüft
- [ ] `state/__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_05_LLM.md](./PHASE_05_LLM.md)
