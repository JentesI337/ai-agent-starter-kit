# PHASE 22 — Import-Verifikation & Linter-Cleanup

> **Session-Ziel:** Nach dem Löschen aller alten Verzeichnisse eine vollständige Import-Verifikation durchführen. Alle Linter-Fehler (unresolved imports, unused imports, circular imports) beheben. Eine saubere `isort` + `ruff`/`flake8`-Baseline herstellen.
>
> **Voraussetzung:** PHASE_21 (alte Verzeichnisse gelöscht) abgeschlossen
> **Folge-Phase:** PHASE_23_TESTS_UPDATE.md
> **Geschätzter Aufwand:** ~3–4 Stunden
> **Betroffene Dateien:** Gesamte `backend/app/` (~200 Python-Dateien)

---

## Schritt 1: Ruff-Basis-Scan (schnellster Einstieg)

```powershell
cd backend

# Falls ruff noch nicht installiert:
pip install ruff

# Scan aller Python-Dateien
ruff check app/ --select E,F,I --output-format concise 2>&1 | Tee-Object -FilePath "../ruff_phase22.txt"

# Zusammenfassung
Select-String -Path "../ruff_phase22.txt" -Pattern "^app.*\.py" | 
    Group-Object { $_.Line -replace ":.*", "" } | 
    Sort-Object Count -Descending | 
    Select-Object Count, Name | 
    Select-Object -First 20
```

**Wichtige Ruff-Codes:**
| Code | Bedeutung |
|---|---|
| `F401` | Ungenutzte Imports |
| `F811` | Redefinition (import shadowing) |
| `E402` | Module level import not at top of file |
| `I001` | Import-Sortierung falsch (isort) |

---

## Schritt 2: Unresolved Imports finden

```powershell
cd backend

# mypy für Import-Check (zeigt unresolved modules)
pip install mypy

mypy app/ --ignore-missing-imports --no-error-summary 2>&1 | 
    Select-String -Pattern "Cannot find implementation|Module .* has no attribute|error:" |
    Tee-Object -FilePath "../mypy_phase22.txt"

# Top-Fehler zeigen
Get-Content "../mypy_phase22.txt" | Select-Object -First 50
```

---

## Schritt 3: Circular-Import-Detection

```powershell
cd backend

pip install pydeps importlab

# Einfacher Circular-Import-Check via Python
python -c "
import sys, importlib
sys.path.insert(0, '.')

domains = [
    'app.shared',      # Tier 0 — no deps
    'app.contracts',   # Tier 0 — no deps
    'app.config',      # Tier 1 — imports shared only
    'app.policy',      # Tier 2 — imports config
    'app.state',       # Tier 2 — imports config, shared
    'app.llm',         # Tier 3 — imports config, shared, contracts
    'app.memory',      # Tier 3
    'app.session',     # Tier 3
    'app.reasoning',   # Tier 4
    'app.quality',     # Tier 4
    'app.tools',       # Tier 4 — imports llm, memory
    'app.agent',       # Tier 5 — imports tools, reasoning, quality
    'app.orchestration', # Tier 5
    'app.multi_agency',  # Tier 6
    'app.workflows',   # Tier 6
    'app.skills',      # Tier 6
    'app.connectors',  # Tier 6
    'app.transport',   # Tier 7 — imports everything
]

for domain in domains:
    try:
        importlib.import_module(domain)
        print(f'OK: {domain}')
    except ImportError as e:
        print(f'FAIL: {domain} — {e}')
    except Exception as e:
        print(f'ERROR: {domain} — {e.__class__.__name__}: {e}')
"
```

---

## Schritt 4: Häufige Import-Muster reparieren

### Pattern A: `from app.services.X import Y`

```powershell
cd backend

# Alle verbliebenen app.services Imports finden
Select-String -Path "app/**/*.py" -Pattern "from app\.services\." -Recurse |
    Select-Object Filename, LineNumber, Line |
    Format-Table -AutoSize | 
    Tee-Object -FilePath "../leftover_services_imports.txt"
```

Für jeden Fund: Manuell auf den neuen DDD-Pfad umstellen.

### Pattern B: Router/Handler-Imports

```powershell
Select-String -Path "app/**/*.py" -Pattern "from app\.(routers|handlers)\." -Recurse |
    Select-Object Filename, LineNumber, Line
```

### Pattern C: Orchestrator/Interface-Imports

```powershell
Select-String -Path "app/**/*.py" -Pattern "from app\.(orchestrator|interfaces|model_routing|tool_modules)\." -Recurse |
    Select-Object Filename, LineNumber, Line
```

---

## Schritt 5: Unbenutzte Imports entfernen (automatisch)

```powershell
cd backend

# Ruff kann ungenutzte Imports automatisch entfernen
ruff check app/ --select F401 --fix

# Nachher prüfen was sich geändert hat
git diff --stat
```

---

## Schritt 6: Import-Sortierung fixieren (isort)

```powershell
cd backend

pip install isort

# Imports in allen Python-Dateien sortieren
isort app/ --profile black --line-length 100

# Überprüfen
isort app/ --check --profile black --line-length 100
```

**isort-Profil in `pyproject.toml` eintragen:**
```toml
[tool.isort]
profile = "black"
line_length = 100
known_first_party = ["app"]
sections = ["FUTURE", "STDLIB", "THIRDPARTY", "FIRSTPARTY", "LOCALFOLDER"]
```

---

## Schritt 7: `__all__`-Exports in allen `__init__.py` prüfen

```powershell
cd backend

# Welche __init__.py haben kein __all__?
Get-ChildItem app/**/__init__.py -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName
    if (-not ($content | Select-String -Pattern "__all__")) {
        Write-Host "MISSING __all__: $($_.FullName)"
    }
}
```

---

## Schritt 8: Type-Hint-Import-Fixes

Wenn Type-Hints ausschließlich im TYPE_CHECKING-Block benötigt werden:

```python
# Statt (verursacht circular imports):
from app.agent.head_agent import HeadAgent  # type-only use case

# Besser:
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.head_agent import HeadAgent
```

---

## Schritt 9: Final Full-App Import Test

```powershell
cd backend

python -c "
from app.main import app
routes = [(r.methods, r.path) for r in app.routes if hasattr(r, 'path')]
print(f'App loaded OK with {len(routes)} routes')
for method, path in sorted(routes, key=lambda x: x[1]):
    print(f'  {method} {path}')
" 2>&1 | Tee-Object -FilePath "../routes_inventory_phase22.txt"
```

---

## Schritt 10: Ruff Final-Check

```powershell
cd backend

ruff check app/ --select E,F,I
```

**Ziel:** 0 Fehler

---

## Commit

```bash
git add -A
git commit -m "refactor(ddd): fix all imports, remove unused, sort — Phase 22

- All app.services.* imports replaced with DDD paths
- All app.orchestrator.* → app.orchestration.*
- All app.model_routing.* → app.llm.routing.*
- Unused imports removed (ruff F401)
- Imports sorted (isort black profile)
- All __init__.py have __all__ defined
"
```

---

## Status-Checkliste

- [ ] Ruff-Scan durchgeführt, Ergebnisse gespeichert
- [ ] mypy Import-Check durchgeführt
- [ ] Circular-Import-Check bestanden
- [ ] Alle `from app.services.*` Imports eliminiert
- [ ] Alle `from app.routers.*` Imports eliminiert
- [ ] Alle `from app.handlers.*` Imports eliminiert
- [ ] Alle `from app.orchestrator.*` Imports eliminiert
- [ ] Alle `from app.interfaces.*` Imports eliminiert
- [ ] Alle `from app.model_routing.*` Imports eliminiert
- [ ] Ruff F401 (ungenutzte Imports) gefixt
- [ ] isort Sortierung angewandt
- [ ] Alle `__init__.py` haben `__all__`
- [ ] `TYPE_CHECKING`-Block für type-only circular imports
- [ ] Full App loads: `from app.main import app` ✅
- [ ] Route-Inventory erstellt
- [ ] Ruff: 0 Fehler
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_23_TESTS_UPDATE.md](./PHASE_23_TESTS_UPDATE.md)
