# PHASE 02 — `config/` Domain

> **Session-Ziel:** Das Konfigurations-Subsystem in ein dediziertes `config/`-Paket migrieren. `config/` wird von ALLEN Modulen genutzt, importiert aber selbst NICHTS aus den Domänen.
>
> **Voraussetzung:** PHASE_01 abgeschlossen
> **Folge-Phase:** PHASE_03_POLICY.md
> **Geschätzter Aufwand:** ~1–2 Stunden
> **Betroffene Quelldateien:**
> - `backend/app/config.py`
> - `backend/app/config_sections.py`
> - `backend/app/config_service.py`

---

## 1. Dateien kopieren

### 1.1 `app/config.py` → `app/config/settings.py`

```powershell
Copy-Item "backend/app/config.py" "backend/app/config/settings.py"
```

**Imports in `settings.py` prüfen:**
```powershell
Select-String -Path "backend/app/config/settings.py" -Pattern "^from app\.|^import app\."
```

`config/settings.py` darf NUR aus extern / typing / Standard-Library importieren.  
Falls `from app.config_sections import ...` → ändern zu `from app.config.sections import ...`

**Stub in original:**
```python
# backend/app/config.py
# DEPRECATED: moved to app.config.settings
# Remove in PHASE_18
from app.config.settings import *  # noqa: F401, F403
# Re-export commonly used symbols explicitly (für typsicheren Zugriff)
from app.config.settings import settings, resolved_prompt_settings, validate_environment_config
```

---

### 1.2 `app/config_sections.py` → `app/config/sections.py`

```powershell
Copy-Item "backend/app/config_sections.py" "backend/app/config/sections.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/config/sections.py" -Pattern "^from app\."
```

Kein App-Domain-Import erlaubt.

**Stub in original:**
```python
# backend/app/config_sections.py
# DEPRECATED: moved to app.config.sections
from app.config.sections import *  # noqa: F401, F403
```

---

### 1.3 `app/config_service.py` → `app/config/service.py`

```powershell
Copy-Item "backend/app/config_service.py" "backend/app/config/service.py"
```

**Imports prüfen — Config-Service darf importieren:**
- `from app.config.settings import settings` (nicht `from app.config import settings`)
- `from app.config.sections import ...`

```powershell
Select-String -Path "backend/app/config/service.py" -Pattern "^from app\."
```

Wenn `from app.config import settings` → prüfen ob das nach dem Stub noch funktioniert (es sollte, da config.py als Stub re-exportiert).

**Stub in original:**
```python
# backend/app/config_service.py
# DEPRECATED: moved to app.config.service
from app.config.service import *  # noqa: F401, F403
from app.config.service import init_config_service  # explicit re-export
```

---

### 1.4 `app/config/overrides.py` — NEU erstellen

Prüfe ob es eine Runtime-Config-Override-Logik gibt (z.B. aus `backend/config_overrides.json`):
```powershell
Get-Content "backend/config_overrides.json" | Select-Object -First 20
```

Falls die Override-Logik in `config_service.py` eingebettet ist, extrahiere sie:
```python
# backend/app/config/overrides.py
"""Runtime config overrides — loaded from config_overrides.json."""
from __future__ import annotations

import json
from pathlib import Path

_OVERRIDES_PATH = Path(__file__).parents[3] / "config_overrides.json"


def load_overrides() -> dict:
    """Load runtime config overrides from JSON file if it exists."""
    if _OVERRIDES_PATH.exists():
        return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {}
```

Falls keine Override-Logik existiert, leere Datei mit Docstring:
```python
# backend/app/config/overrides.py
"""Placeholder for runtime config overrides."""
```

---

### 1.5 `app/config/__init__.py` befüllen

```python
# backend/app/config/__init__.py
"""
Configuration domain — loaded by all modules, imports nothing from domains.
"""
from app.config.settings import settings, resolved_prompt_settings, validate_environment_config
from app.config.service import init_config_service

__all__ = [
    "settings",
    "resolved_prompt_settings",
    "validate_environment_config",
    "init_config_service",
]
```

> Passe die exportierten Symbole nach Lektüre der Dateien an (exakte Klassen-/Funktionsnamen).

---

## 2. Konsumenten finden (Info, kein sofortiger Rewrite)

```powershell
# Wer importiert aus app.config?
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.config import|from app\.config_sections import|from app\.config_service import" -Recurse | Group-Object Filename | Select-Object Name, Count | Sort-Object Count -Descending
```

> **Strategie:** Die Stubs sorgen dafür, dass alte Importe weiter funktionieren.  
> Grober Überblick: `main.py` ist der Haupt-Konsument. Wird in **Phase 16** bereinigt.  
> Alle anderen Konsumenten werden in **Phase 18** mit einem Batch-Rewrite aktualisiert.

---

## 3. Interne Referenzen in config/settings.py fixieren

Wenn `settings.py` auf `config_sections` zeigt:
```python
# ALT (wenn vorhanden in settings.py)
from app.config_sections import SomeSection

# NEU
from app.config.sections import SomeSection
```

Da `config_sections.py` zum Stub wurde, würde der alte Import via Stub noch funktionieren.  
Für Sauberkeit: direkt zu `app.config.sections` updaten.

---

## 4. Verifikation

```powershell
# Dateien existieren
$checks = @(
    "backend/app/config/__init__.py",
    "backend/app/config/settings.py",
    "backend/app/config/sections.py",
    "backend/app/config/service.py",
    "backend/app/config/overrides.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

# Stubs vorhanden
Select-String "backend/app/config.py" -Pattern "DEPRECATED"
Select-String "backend/app/config_sections.py" -Pattern "DEPRECATED"
Select-String "backend/app/config_service.py" -Pattern "DEPRECATED"

# Import-Test
cd backend
python -c "
from app.config import settings, init_config_service
from app.config.settings import settings as s2
from app.config.sections import *
print('config/ OK')
"

# Smoke-Test via alte Pfade (Stubs müssen noch funktionieren)
python -c "
from app.config import settings
from app.config_service import init_config_service
print('Stubs OK')
"
```

---

## 5. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate config/ domain — Phase 02"
```

---

## Status-Checkliste

- [ ] `config/settings.py` erstellt (aus `config.py`)
- [ ] `config/sections.py` erstellt (aus `config_sections.py`)
- [ ] `config/service.py` erstellt (aus `config_service.py`)
- [ ] `config/overrides.py` erstellt
- [ ] `config/__init__.py` befüllt mit sauberen Exports
- [ ] Stubs in allen 3 originalen Dateien
- [ ] Interne Querverweise in settings.py auf neue Pfade umgestellt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_03_POLICY.md](./PHASE_03_POLICY.md)
