# PHASE 00 — Pre-flight Assessment & Verzeichnis-Skelett

> **Session-Ziel:** Nichts verschieben. Nur analysieren, sichern und das komplette Verzeichnis-Skelett anlegen (leere `__init__.py`-Dateien). Nach dieser Phase ist jedes Ziel-Verzeichnis vorhanden, aber noch leer.
>
> **Voraussetzung:** Keine (erster Schritt)
> **Folge-Phase:** PHASE_01_SHARED_CONTRACTS.md

---

## 0. Checkliste vor dem Start

- [ ] Git-Branch erstellen: `git checkout -b refactor/ddd-structure`
- [ ] Aktuellen Stand committen: `git add -A && git commit -m "chore: pre-refactor snapshot"`
- [ ] Tests laufen durch: `cd backend && python -m pytest tests/ -x -q` (Baseline dokumentieren)
- [ ] Baseline-Fehleranzahl notieren: _____ Tests bestanden, _____ fehlgeschlagen

---

## 1. Aktuelle Ist-Struktur verifizieren

Führe folgende Befehle aus und prüfe ob die Ausgabe mit dem DDD_STRUCTURE_PLAN übereinstimmt:

```powershell
# Python-Dateien zählen (Soll: ~214)
Get-ChildItem "backend/app" -Recurse -Name "*.py" | Where-Object { $_ -notmatch "__pycache__" } | Measure-Object

# Root-Level-Dateien im app/ auflisten
Get-ChildItem "backend/app" -MaxDepth 1 -Name

# services/ Dateien zählen (Soll: ~75 inkl. __init__.py)
Get-ChildItem "backend/app/services" -Name | Measure-Object

# handlers/ Dateien zählen
Get-ChildItem "backend/app/handlers" -Name

# routers/ Dateien zählen
Get-ChildItem "backend/app/routers" -Name
```

---

## 2. Neue Verzeichnisse anlegen (Skelett)

Führe dieses PowerShell-Script aus. Es erstellt alle fehlenden Zielverzeichnisse mit `__init__.py`.

```powershell
$base = "backend/app"

$newDirs = @(
    # shared/ (Querschnitt)
    "$base/shared",
    "$base/shared/idempotency",

    # config/ (neu)
    "$base/config",

    # policy/  (neu – war: policy_store.py + services/policy_*)
    "$base/policy",

    # llm/ (neu – war: llm_client.py + model_routing/)
    "$base/llm",
    "$base/llm/routing",

    # mcp/ (neu – war: mcp_types.py + services/mcp_bridge.py)
    "$base/mcp",

    # media/ (neu – war: services/audio_* etc.)
    "$base/media",

    # sandbox/ (neu – war: services/code_sandbox.py etc.)
    "$base/sandbox",

    # browser/ (neu – war: services/browser_pool.py)
    "$base/browser",

    # monitoring/ (neu – war: services/visualization.py etc.)
    "$base/monitoring",

    # memory/ (neu – war: memory.py + services/long_term_memory.py etc.)
    "$base/memory",

    # session/ (neu – war: services/session_*)
    "$base/session",

    # reasoning/ (neu – war: services/action_parser.py etc.)
    "$base/reasoning",
    "$base/reasoning/prompt",
    "$base/reasoning/prompt/templates",
    "$base/reasoning/prompt/templates/cognitive",

    # quality/ (neu – war: services/reflection_service.py etc.)
    "$base/quality",

    # tools/ (erweitert – war: tool_catalog.py etc. + services/tool_*)
    "$base/tools",
    "$base/tools/implementations",
    "$base/tools/registry",
    "$base/tools/execution",
    "$base/tools/discovery",
    "$base/tools/provisioning",

    # agent/ (neu – war: agent.py + agents/)
    "$base/agent",

    # orchestration/ (neu – war: orchestrator/)
    "$base/orchestration",

    # transport/ (neu – war: app_setup.py + ws_handler.py etc.)
    "$base/transport",
    "$base/transport/routers",

    # contracts/ (ergänzen – war: contracts/ + interfaces/)
    # → existiert bereits, nur ergänzen
)

foreach ($dir in $newDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        New-Item -ItemType File -Path "$dir/__init__.py" -Force | Out-Null
        Write-Host "CREATED: $dir"
    } else {
        Write-Host "EXISTS:  $dir"
        # Sicherstellen dass __init__.py existiert
        if (-not (Test-Path "$dir/__init__.py")) {
            New-Item -ItemType File -Path "$dir/__init__.py" -Force | Out-Null
            Write-Host "  + added __init__.py"
        }
    }
}

Write-Host "`nDone. Verify with: Get-ChildItem backend/app -Directory -Recurse | Select-Object Name"
```

### Erwartete neue Verzeichnisse nach dem Script:

```
backend/app/
├── shared/               ← NEU
│   └── idempotency/      ← NEU
├── config/               ← NEU
├── policy/               ← NEU
├── llm/                  ← NEU
│   └── routing/          ← NEU
├── mcp/                  ← NEU
├── media/                ← NEU
├── sandbox/              ← NEU
├── browser/              ← NEU
├── monitoring/           ← NEU
├── memory/               ← NEU
├── session/              ← NEU
├── reasoning/            ← NEU
│   └── prompt/           ← NEU
│       └── templates/    ← NEU
│           └── cognitive/ ← NEU
├── quality/              ← NEU
├── tools/                ← NEU (existiert evtl. noch nicht)
│   ├── implementations/  ← NEU
│   ├── registry/         ← NEU
│   ├── execution/        ← NEU
│   ├── discovery/        ← NEU
│   └── provisioning/     ← NEU
├── agent/                ← NEU (nicht zu verwechseln mit agents/)
├── orchestration/        ← NEU (nicht zu verwechseln mit orchestrator/)
└── transport/            ← NEU
    └── routers/          ← NEU
```

### Bereits vorhandene Verzeichnisse (NICHT anfassen):
```
backend/app/agents/         ← bleibt bis Phase 12
backend/app/connectors/     ← bleibt bereits in Zielposition
backend/app/contracts/      ← bleibt, wird in Phase 01 ergänzt
backend/app/handlers/       ← bleibt bis Phase 15
backend/app/interfaces/     ← bleibt bis Phase 13
backend/app/model_routing/  ← bleibt bis Phase 05
backend/app/multi_agency/   ← bleibt (schon korrekt benannt, Inhalt prüfen in Phase 17)
backend/app/orchestrator/   ← bleibt bis Phase 13
backend/app/routers/        ← bleibt bis Phase 15
backend/app/services/       ← bleibt bis Phase 18
backend/app/skills/         ← bleibt (schon korrekt, kein Move nötig)
backend/app/state/          ← bleibt (schon korrekt, wird in Phase 04 ergänzt)
backend/app/tool_modules/   ← bleibt bis Phase 09/10
backend/app/workflows/      ← bleibt (schon korrekt, Router wird in Phase 15 bewegt)
```

---

## 3. Backend-Root-Verzeichnis für Datenmigration vorbereiten

```powershell
$dataBase = "backend/data"

$dataDirs = @(
    "$dataBase/agents",
    "$dataBase/memory",
    "$dataBase/state",
    "$dataBase/assets/voices",
    "$dataBase/output/audio"
)

foreach ($dir in $dataDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "CREATED: $dir"
    }
}
```

> **ACHTUNG:** Die Daten werden erst in **PHASE_17** verschoben. Jetzt nur Verzeichnisse anlegen.

---

## 4. Verifikation

```powershell
# Alle neuen app/-Verzeichnisse wurden angelegt
$expected = @("shared","config","policy","llm","mcp","media","sandbox","browser",
              "monitoring","memory","session","reasoning","quality","tools","agent",
              "orchestration","transport")

foreach ($d in $expected) {
    if (Test-Path "backend/app/$d") {
        Write-Host "OK: backend/app/$d"
    } else {
        Write-Host "MISSING: backend/app/$d"
    }
}

# data/ Verzeichnisse
$dataExpected = @("agents","memory","state","assets/voices","output/audio")
foreach ($d in $dataExpected) {
    if (Test-Path "backend/data/$d") {
        Write-Host "OK: backend/data/$d"
    } else {
        Write-Host "MISSING: backend/data/$d"
    }
}
```

---

## 5. Commit

```bash
git add -A
git commit -m "chore(ddd): scaffold new directory structure (empty __init__.py only)"
```

---

## Status-Checkliste

- [ ] Git-Branch angelegt
- [ ] Baseline-Tests dokumentiert
- [ ] Alle 17 neuen app/-Verzeichnisse vorhanden
- [ ] backend/data/ Struktur angelegt
- [ ] Commit gemacht
- [ ] **Keine einzige Produktionsdatei wurde verschoben oder verändert**

---

> **Nächste Session:** [PHASE_01_SHARED_CONTRACTS.md](./PHASE_01_SHARED_CONTRACTS.md)
