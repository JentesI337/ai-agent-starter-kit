# PHASE 17 — Backend-Root-Bereinigung (Daten, Scripts, Nested Dirs)

> **Session-Ziel:** `backend/`-Root aufräumen. Datendateien in `backend/data/` verschieben, verschachtelte Duplikate (`backend/backend/`, `backend/frontend/`) löschen, `scripts/` konsolidieren. Kein Python-Code wird geändert.
>
> **Voraussetzung:** PHASE_16 (main.py slim-down) abgeschlossen
> **Folge-Phase:** PHASE_18_MULTI_AGENCY.md
> **Geschätzter Aufwand:** ~1–2 Stunden
> **Betroffene Verzeichnisse:** `backend/` Root (kein `backend/app/`-Code)

---

## Ist-Zustand `backend/`

```
backend/
├── app/                        ← Python-App (bleibt)
├── tests/                      ← Tests (bleibt)
├── backend/                    ← ⚠️ DUPLIKAT — löschen
├── frontend/                   ← ⚠️ falsch verschachtelt — prüfen
├── agents/                     ← JSON-Konfigdateien
├── agent_configs/              ← agent-profile JSONs
├── custom_agents/              ← custom agent configs
├── memory_store/               ← .jsonl Dateien
├── state_store/                ← runs/ snapshots/ Dirs
├── piper_voices/               ← TTS Voice-Assets
├── generated_audio/            ← Ausgabe-Audiodateien
├── generate_speech.py          ← Utility-Script
├── generate_tone.py            ← Utility-Script
├── skills/                     ← Skill-YAML-Dateien
├── skills_synced/              ← Sync-Cache
├── scripts/                    ← bestehende Scripts
├── monitoring/                 ← Monitoring-Assets
├── policies/                   ← Policy-YAML-Dateien
└── requirements.txt etc.
```

## Ziel-Struktur `backend/`

```
backend/
├── app/                        ← Python-App (unverändert)
├── tests/                      ← Tests (unverändert)
├── data/
│   ├── agents/                 ← war: agents/ + agent_configs/ + custom_agents/
│   ├── memory/                 ← war: memory_store/
│   ├── state/                  ← war: state_store/
│   ├── skills/                 ← war: skills/ + skills_synced/
│   ├── policies/               ← war: policies/
│   ├── assets/
│   │   └── voices/             ← war: piper_voices/
│   └── output/
│       └── audio/              ← war: generated_audio/
├── scripts/
│   ├── generate_speech.py      ← war: backend/generate_speech.py
│   ├── generate_tone.py        ← war: backend/generate_tone.py
│   └── [bestehende Scripts]
└── [Requirements, pyproject.toml etc.]
```

---

## Schritt 1: Inventur machen

```powershell
cd backend

# Ist backend/backend/ ein Duplikat?
Get-ChildItem backend/ | Select-Object Name, LastWriteTime

# Ist backend/frontend/ ein Duplikat?
Get-ChildItem frontend/ | Select-Object Name

# Alle JSON-Dateien in agents/ zählen
(Get-ChildItem agents/ -Filter "*.json" -Recurse).Count

# Alle JSONL-Dateien in memory_store/ zählen
(Get-ChildItem memory_store/ -Filter "*.jsonl").Count

# State-Store-Inhalt
Get-ChildItem state_store/ -Recurse | Select-Object FullName
```

---

## Schritt 2: Verzeichnisse erstellen

```powershell
cd backend

# Daten-Verzeichnisbaum erstellen
New-Item -ItemType Directory -Force -Path data/agents
New-Item -ItemType Directory -Force -Path data/memory
New-Item -ItemType Directory -Force -Path data/state
New-Item -ItemType Directory -Force -Path data/skills
New-Item -ItemType Directory -Force -Path data/policies
New-Item -ItemType Directory -Force -Path data/assets/voices
New-Item -ItemType Directory -Force -Path data/output/audio
```

---

## Schritt 3: Dateien verschieben

> ⚠️ **WICHTIG:** Nach jedem Verschiebevorgang die App testen!
> Die App muss so konfiguriert werden, dass sie die neuen Pfade kennt. Prüfe `config/` auf Pfad-Einstellungen.

```powershell
cd backend

# -- Agent-Konfigurationen ---------------------------------------
# agents/ → data/agents/
Move-Item -Path agents/* -Destination data/agents/ -Force

# agent_configs/ → data/agents/configs/
New-Item -ItemType Directory -Force -Path data/agents/configs
Move-Item -Path agent_configs/* -Destination data/agents/configs/ -Force

# custom_agents/ → data/agents/custom/
New-Item -ItemType Directory -Force -Path data/agents/custom
Move-Item -Path custom_agents/* -Destination data/agents/custom/ -Force

# -- Memory Store ------------------------------------------------
Move-Item -Path memory_store/* -Destination data/memory/ -Force

# -- State Store -------------------------------------------------
Move-Item -Path state_store/* -Destination data/state/ -Force

# -- Skills ------------------------------------------------------
Move-Item -Path skills/* -Destination data/skills/ -Force
# skills_synced nur wenn leer oder Cache (kann gelöscht werden)
# Falls skills_synced/ nur Cache: leer + löschen
# Falls Dateien drin → auch verschieben:
# Move-Item -Path skills_synced/* -Destination data/skills/synced/ -Force

# -- Policies ----------------------------------------------------
Move-Item -Path policies/* -Destination data/policies/ -Force

# -- TTS Voices --------------------------------------------------
Move-Item -Path piper_voices/* -Destination data/assets/voices/ -Force

# -- Audio Output ------------------------------------------------
Move-Item -Path generated_audio/* -Destination data/output/audio/ -Force

# -- Scripts -----------------------------------------------------
# Nur wenn noch nicht in scripts/ vorhanden
Move-Item -Path generate_speech.py -Destination scripts/generate_speech.py -ErrorAction SilentlyContinue
Move-Item -Path generate_tone.py -Destination scripts/generate_tone.py -ErrorAction SilentlyContinue
```

---

## Schritt 4: Leere Verzeichnisse entfernen

```powershell
cd backend

# Nur entfernen wenn LEER (Safe-Remove)
foreach ($dir in @("agents", "agent_configs", "custom_agents", "memory_store", "state_store", "skills", "skills_synced", "policies", "piper_voices", "generated_audio")) {
    if ((Get-ChildItem $dir -Recurse).Count -eq 0) {
        Remove-Item $dir -Recurse -Force
        Write-Host "Removed: $dir"
    } else {
        Write-Host "NOT EMPTY — skipping: $dir"
        Get-ChildItem $dir
    }
}
```

---

## Schritt 5: `backend/backend/` und `backend/frontend/` prüfen

```powershell
cd backend

# backend/backend/ — ist es ein echtes Duplikat?
if (Test-Path "backend") {
    Write-Host "=== backend/backend/ contents ==="
    Get-ChildItem "backend" -Recurse | Select-Object FullName
}

# frontend/ — gehört es hierher?
if (Test-Path "frontend") {
    Write-Host "=== backend/frontend/ contents ==="
    Get-ChildItem "frontend" -Recurse | Select-Object FullName
}
```

**Entscheidungsbaum:**

| Verzeichnis | Aktion |
|---|---|
| `backend/backend/` ist leer | `Remove-Item backend/backend/ -Recurse -Force` |
| `backend/backend/` hat Duplikat-Dateien | Manuell vergleichen, dann löschen |
| `backend/backend/` hat einzigartige Dateien | Dateien retten, dann löschen |
| `backend/frontend/` ist ein Sym-Link | Link entfernen |
| `backend/frontend/` hat Dateien | Nach `c:\Users\wisni\code\git\ai-agent-starter-kit\frontend\` verschieben wenn nötig |

---

## Schritt 6: Config-Pfade aktualisieren

Die App-Config muss die neuen Datenpfade kennen. Prüfe:

```powershell
cd backend

# Welche Dateien referenzieren alte Pfade?
Select-String -Path "app/**/*.py" -Pattern "memory_store|state_store|piper_voices|generated_audio|agent_configs|custom_agents" -Recurse | Select-Object Filename, LineNumber, Line
```

Für jeden gefundenen Pfad:
1. Öffne die Datei
2. Ersetze `"memory_store"` → `"data/memory"`
3. Ersetze `"state_store"` → `"data/state"`
4. Ersetze `"piper_voices"` → `"data/assets/voices"`
5. Ersetze `"generated_audio"` → `"data/output/audio"`
6. Ersetze `"agent_configs"` → `"data/agents/configs"`

**Bevorzugter Ansatz:** In `config/` eine zentrale `paths.py` oder `settings.py` haben, die alle Datenpfade definiert:

```python
# app/config/paths.py (falls noch nicht existiert)
from pathlib import Path

# Basis-Pfad: wo liegen die Datendaten relativ zur App?
DATA_ROOT = Path(__file__).parent.parent.parent / "data"  # backend/data/

AGENTS_DIR = DATA_ROOT / "agents"
MEMORY_DIR = DATA_ROOT / "memory"
STATE_DIR  = DATA_ROOT / "state"
SKILLS_DIR = DATA_ROOT / "skills"
VOICES_DIR = DATA_ROOT / "assets" / "voices"
AUDIO_DIR  = DATA_ROOT / "output" / "audio"
```

Dann in der App überall `from app.config.paths import MEMORY_DIR` statt Hardcoded-Strings.

---

## Verifikation

```powershell
cd backend

# 1. App startet noch?
python -c "from app.main import app; print('Import OK')"

# 2. Datenverzeichnisse vorhanden?
Get-ChildItem data/ | Select-Object Name

# 3. Alte Verzeichnisse weg?
foreach ($dir in @("agents", "agent_configs", "custom_agents", "memory_store", "state_store")) {
    if (Test-Path $dir) { Write-Host "STILL EXISTS: $dir" } else { Write-Host "REMOVED OK: $dir" }
}

# 4. Tests
python -m pytest tests/ -k "memory or state or agent" -q --tb=short 2>&1 | Select-Object -First 40
```

---

## `.gitignore` aktualisieren

```powershell
cd backend
```

Füge zu `backend/.gitignore` hinzu (oder erstelle es):
```
# Data outputs (generated, not committed)
data/output/
data/memory/
data/state/

# Voices (large binary assets)
data/assets/voices/

# Audio cache
generated_audio/
```

---

## Commit

```bash
git add -A
git commit -m "chore(structure): move data dirs under backend/data/ — Phase 17"
```

---

## Status-Checkliste

- [ ] Verzeichnis-Inventur gemacht
- [ ] `backend/data/` Struktur erstellt
- [ ] `agents/`, `agent_configs/`, `custom_agents/` → `data/agents/`
- [ ] `memory_store/` → `data/memory/`
- [ ] `state_store/` → `data/state/`
- [ ] `skills/` → `data/skills/`
- [ ] `policies/` → `data/policies/`
- [ ] `piper_voices/` → `data/assets/voices/`
- [ ] `generated_audio/` → `data/output/audio/`
- [ ] Utility-Scripts nach `scripts/` verschoben
- [ ] Leere alte Dirs entfernt
- [ ] `backend/backend/` und `backend/frontend/` geprüft + bereinigt
- [ ] Config-Pfade in `app/` aktualisiert
- [ ] `.gitignore` aktualisiert
- [ ] App startet noch (`from app.main import app`)
- [ ] Tests laufen durch
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_18_MULTI_AGENCY.md](./PHASE_18_MULTI_AGENCY.md)
