# PHASE 21 — Alte Verzeichnisse entfernen (`services/`, `routers/`, `handlers/`, `orchestrator/`, etc.)

> **Session-Ziel:** Die alten vorDDD-Verzeichnisse endgültig entfernen. Alle Referenzen darauf sind in den vorherigen Phasen auf neue DDD-Pfade umgestellt worden. Diese Session stellt sicher dass nichts mehr davon abhängt, und löscht dann sauber.
>
> **Voraussetzung:** ALLE vorherigen Phasen (01–20) abgeschlossen
> **Folge-Phase:** PHASE_22_IMPORT_VERIFICATION.md
> **Geschätzter Aufwand:** ~2–3 Stunden (hauptsächlich Verifikation)
> **Betroffene Verzeichnisse:** `services/`, `routers/`, `handlers/`, `orchestrator/`, `interfaces/`, `model_routing/`, `tool_modules/`, `agents/`

---

## Zu löschende Verzeichnisse

| Verzeichnis | Inhalt migriert nach | Phase |
|---|---|---|
| `app/services/` | Diverse DDD-Domains | 03–15 |
| `app/routers/` | `app/transport/routers/` | 15 |
| `app/handlers/` | `app/transport/routers/` | 15 |
| `app/orchestrator/` | `app/orchestration/` | 13 |
| `app/interfaces/` | `app/contracts/` | 13 |
| `app/model_routing/` | `app/llm/routing/` | 05 |
| `app/tool_modules/` | `app/tools/` (registry, policy) | 09 |
| `app/agents/` | `app/agent/` | 12 |

---

## Schritt 1: Abhängigkeits-Check vor dem Löschen

```powershell
cd backend

# Für jedes zu löschende Verzeichnis: Hat noch irgendjemand darauf?
$old_dirs = @(
    "app.services",
    "app.routers",
    "app.handlers",
    "app.orchestrator",
    "app.interfaces",
    "app.model_routing",
    "app.tool_modules"
)

foreach ($import_path in $old_dirs) {
    Write-Host "`n=== Checking: $import_path ==="
    $results = Select-String -Path "app/**/*.py" -Pattern "from $import_path|import $import_path" -Recurse
    if ($results) {
        Write-Host "⚠️  STILL REFERENCED in:"
        $results | Select-Object Filename, LineNumber, Line | Format-Table
    } else {
        Write-Host "✅ No references found — safe to delete"
    }
}
```

> **STOPP:** Wenn irgendein `⚠️ STILL REFERENCED` erscheint, diesen Import ZUERST reparieren bevor weiter gemacht wird!

---

## Schritt 2: `app/agents/` vs `app/agent/` — Namens-Kollision auflösen

```powershell
# Achtung: app/agents/ (plural) = alt, app/agent/ (singular) = neu
Test-Path "backend/app/agents"
Test-Path "backend/app/agent"

# Welche Imports noch auf app.agents zeigen?
Select-String -Path "backend/app/**/*.py" -Pattern "from app\.agents\." -Recurse |
    Select-Object Filename, LineNumber, Line
```

Alle `from app.agents.` → `from app.agent.` Ersetzungen durchführen.

---

## Schritt 3: `services/` — Schrittweises Löschen

`services/` ist das grösste Verzeichnis (~70 Dateien). Nicht alles auf einmal löschen.

```powershell
cd backend

# Wie viele Dateien noch in services?
(Get-ChildItem app/services/ -Filter "*.py").Count

# Welche services/*.py haben noch externe Referenzen?
Get-ChildItem app/services/ -Filter "*.py" | ForEach-Object {
    $module = "app.services." + $_.BaseName
    $refs = Select-String -Path "app/**/*.py" -Pattern "from $module|import $module" -Recurse -ErrorAction SilentlyContinue
    if ($refs) {
        Write-Host "=== STILL NEEDED: $($_.Name) ==="
        $refs | Select-Object Filename, Line
    }
}
```

Für jede noch referenzierte `services/*.py`-Datei: Zurück zur zugehörigen Phase und den Import reparieren.

---

## Schritt 4: Test-Imports prüfen

```powershell
cd backend

# Tests referenzieren alte Paths?
Select-String -Path "tests/**/*.py" -Pattern "from app\.services\.|from app\.routers\.|from app\.handlers\.|from app\.orchestrator\." -Recurse |
    Select-Object Filename, LineNumber, Line
```

Tests die alte Pfade importieren, müssen aktualisiert werden.

---

## Schritt 5: Backup vor dem Löschen

```powershell
cd backend

# Backup der alten Verzeichnisse
$backup_path = "../_old_pre_ddd_backup"
New-Item -ItemType Directory -Force -Path $backup_path

foreach ($dir in @("app/services", "app/routers", "app/handlers", "app/orchestrator", "app/interfaces", "app/model_routing", "app/tool_modules", "app/agents")) {
    if (Test-Path $dir) {
        $dest = Join-Path $backup_path (Split-Path $dir -Leaf)
        Copy-Item -Path $dir -Destination $dest -Recurse -Force
        Write-Host "Backed up: $dir → $dest"
    }
}
```

---

## Schritt 6: Verzeichnisse löschen

> ⚠️ **NUR WENN SCHRITT 1 keine `⚠️ STILL REFERENCED` mehr zeigt!**

```powershell
cd backend

# Einzeln löschen, jeweils prüfen
foreach ($dir in @(
    "app/orchestrator",
    "app/interfaces",
    "app/model_routing",
    "app/tool_modules"
)) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force
        Write-Host "DELETED: $dir"
    } else {
        Write-Host "ALREADY GONE: $dir"
    }
}

# handlers/ und routers/ nach Transport-Migration
foreach ($dir in @("app/handlers", "app/routers")) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force
        Write-Host "DELETED: $dir"
    }
}

# agents/ (alt) nur wenn app/agent/ (neu) vollständig ist
if ((Test-Path "app/agent") -and (Test-Path "app/agents")) {
    Remove-Item "app/agents" -Recurse -Force
    Write-Host "DELETED: app/agents (old plural form)"
}

# services/ — ERST ZULETZT! Nach intensiver Verifikation
# $confirm = Read-Host "Delete app/services/ ? Type YES to confirm"
# if ($confirm -eq "YES") {
#     Remove-Item "app/services" -Recurse -Force
#     Write-Host "DELETED: app/services"
# }
```

---

## Schritt 7: `__init__.py` in der App-Root prüfen

```powershell
cd backend

# app/__init__.py — exportiert es noch alte Modules?
Get-Content "app/__init__.py"
```

Alle Exporte auf alte Pfade entfernen oder durch neue ersetzen.

---

## Schritt 8: Full Import Test

```powershell
cd backend

python -c "
import sys
sys.path.insert(0, '.')

# Alle DDD-Domains importieren
imports = [
    'app.shared',
    'app.contracts',
    'app.config',
    'app.policy',
    'app.state',
    'app.llm',
    'app.memory',
    'app.session',
    'app.reasoning',
    'app.quality',
    'app.tools',
    'app.agent',
    'app.orchestration',
    'app.transport',
    'app.multi_agency',
    'app.workflows',
    'app.skills',
    'app.connectors',
]

for imp in imports:
    try:
        __import__(imp)
        print(f'  ✅ {imp}')
    except ImportError as e:
        print(f'  ❌ {imp}: {e}')
"
```

---

## Schritt 9: Full Test-Suite

```powershell
cd backend

python -m pytest tests/ -v --tb=short 2>&1 | Tee-Object -FilePath "../test_results_phase21.txt"

# Zusammenfassung
Select-String -Path "../test_results_phase21.txt" -Pattern "passed|failed|error" | Select-Object -Last 5
```

---

## Commit

```bash
git add -A
git commit -m "refactor(ddd): remove old pre-DDD directories — Phase 21

Deleted:
- app/orchestrator/ → app/orchestration/
- app/interfaces/   → app/contracts/
- app/model_routing/ → app/llm/routing/
- app/tool_modules/ → app/tools/
- app/handlers/     → app/transport/routers/
- app/routers/      → app/transport/routers/
- app/agents/       → app/agent/
- app/services/     → distributed across DDD domains
"
```

---

## Status-Checkliste

- [ ] Abhängigkeits-Check: Keine Referenzen auf alte Pfade mehr
- [ ] `app/agents/` vs `app/agent/` Namens-Kollision aufgelöst
- [ ] Test-Imports geprüft und aktualisiert
- [ ] Backup erstellt
- [ ] `app/orchestrator/` gelöscht
- [ ] `app/interfaces/` gelöscht
- [ ] `app/model_routing/` gelöscht
- [ ] `app/tool_modules/` gelöscht
- [ ] `app/handlers/` gelöscht
- [ ] `app/routers/` gelöscht
- [ ] `app/agents/` (alt, plural) gelöscht
- [ ] `app/services/` gelöscht (LETZTER SCHRITT)
- [ ] `app/__init__.py` aufgeräumt
- [ ] Full Import Test bestanden (alle ✅)
- [ ] Full Test-Suite läuft durch
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_22_IMPORT_VERIFICATION.md](./PHASE_22_IMPORT_VERIFICATION.md)
