# PHASE 19 — `workflows/` + `skills/` — Import-Bereinigung & DDD-Einordnung

> **Session-Ziel:** `workflows/` (10 Dateien) und `skills/` (9 Dateien) DDD-konform machen. Imports auf neue Pfade aktualisieren, `router.py` aus beiden Domains in `transport/routers/` verlinken (oder bereits erledigt in Phase 15), und `__init__.py` sauber dokumentieren.
>
> **Voraussetzung:** PHASE_15 (Transport-Router), PHASE_13 (Orchestration), PHASE_09–11 (Tools)
> **Folge-Phase:** PHASE_20_CONNECTORS.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Dateien:** `backend/app/workflows/` (10), `backend/app/skills/` (9)

---

## Ist-Zustand

### `backend/app/workflows/`
```
chain_resolver.py    — löst Workflow-Ketten auf
contracts.py         — Workflow-spezifische Contracts
engine.py            — Workflow-Ausführungs-Engine
handlers.py          — HTTP Handler-Logik (war in handlers/)
models.py            — Datenmodelle (Pydantic)
router.py            — FastAPI Router (WIRD nach transport/routers/ verlagert)
scheduler.py         — Zeitgesteuerter Workflow-Start
store.py             — Persistenz-Layer
tools.py             — Workflow-spezifische Tools
transforms.py        — Daten-Transformationen
__init__.py
```

### `backend/app/skills/`
```
discovery.py         — Skill-Erkennung
eligibility.py       — Skill-Berechtigung
models.py            — Datenmodelle (Pydantic)
parser.py            — Skill-Definition-Parser
prompt.py            — Skill-zu-Prompt-Generierung
retrieval.py         — Skill-Abruf aus Store
service.py           — Haupt-Service (Fassade)
snapshot.py          — Skill-Snapshot-Persistenz
validation.py        — Skill-Validierungslogik
__init__.py
```

---

## Domain-Grenzen

### `workflows/` DARF importieren:
```
✅ app.shared.*
✅ app.contracts.*
✅ app.config.*
✅ app.state.state_store
✅ app.orchestration.*
✅ app.tools.registry  (Tool-Lookup, nicht Execution)
✅ app.skills.*        (Skill-Lookup für Workflows)
✅ app.memory.*        (Workflow-Kontext)
```

### `workflows/` DARF NICHT importieren:
```
❌ app.transport.*     — Transport ist external to domain
❌ app.agent.*         — Agent läuft Workflows, nicht umgekehrt
❌ app.services.*      — Alter Monolith — weg damit
❌ app.routers.*       — Transport-Layer
❌ app.handlers.*      — Transport-Layer
```

### `skills/` DARF importieren:
```
✅ app.shared.*
✅ app.contracts.*
✅ app.config.*
✅ app.state.state_store
✅ app.memory.*        (Skill-Erfahrungen speichern)
```

### `skills/` DARF NICHT importieren:
```
❌ app.transport.*
❌ app.agent.*         (Verhindert Circular)
❌ app.tools.*         (Skills sind keine Tools)
❌ app.workflows.*     (Circular-Import vermeiden)
❌ app.services.*
```

---

## TEIL A: `workflows/`

### Schritt A1: Import-Audit

```powershell
cd backend

Select-String -Path "app/workflows/*.py" -Pattern "^from|^import" |
    Select-Object Filename, LineNumber, Line |
    Format-Table -AutoSize
```

### Schritt A2: `router.py` — Transport-Verlagerung

In Phase 15 sollte `workflows/router.py` bereits nach `transport/routers/workflows.py` verschoben worden sein.

**Prüfen:**
```powershell
Test-Path "backend/app/transport/routers/workflows.py"
```

Falls `True`: `workflows/router.py` kann jetzt auf einen Import-Shim reduziert werden:
```python
# backend/app/workflows/router.py
# DEPRECATED — Router moved to transport/routers/workflows.py
# This file kept for backwards-compatibility during migration.
# TODO: Remove after all imports are updated.
from app.transport.routers.workflows import router

__all__ = ["router"]
```

Falls `False`: `workflows/router.py` nach `transport/routers/workflows.py` kopieren (folge Phase 15 Anweisungen für diesen Router).

### Schritt A3: `handlers.py` — Transport-Verlagerung

Gleiche Prüfung:
```powershell
Select-String -Path "app/transport/routers/workflows.py" -Pattern "def " | Select-Object LineNumber, Line
```

Falls alle Handler bereits im Transport-Router sind: `workflows/handlers.py` auf Shim reduzieren oder als pure Business-Logik-Helfer belassen.

Falls Handler-Logik fehlt: Ins `transport/routers/workflows.py` migrieren.

### Schritt A4: Import-Reparaturen für `engine.py`

```python
# ALT
from app.orchestrator.pipeline_runner import PipelineRunner
# NEU
from app.orchestration.pipeline_runner import PipelineRunner

# ALT
from app.services.workflow_service import WorkflowService
# NEU — lokale Domain-Klassen verwenden
from app.workflows.store import WorkflowStore

# ALT
from app.interfaces.orchestrator_api import OrchestratorAPI
# NEU
from app.contracts.orchestrator_contract import OrchestratorContract
```

### Schritt A5: Import-Reparaturen für `scheduler.py`

```python
# ALT
from app.services.scheduler_service import SchedulerService
# NEU — direkt aus engine
from app.workflows.engine import WorkflowEngine
```

### Schritt A6: Import-Reparaturen für `tools.py`

```python
# ALT
from app.tools import run_tool
# NEU
from app.tools.execution.executor import ToolExecutor
```

### Schritt A7: `__init__.py` für `workflows/`

```python
# backend/app/workflows/__init__.py
"""
workflows — Workflow Execution Domain.

Handles definition, execution, scheduling, and persistence of workflows.
  - WorkflowEngine:      Executes workflow chains step-by-step
  - WorkflowStore:       Persists workflow state and history
  - WorkflowScheduler:   Triggers workflows on schedule
  - ChainResolver:       Resolves multi-step workflow chains
  - WorkflowTransforms:  Pre/post transform data between steps

Transport layer (HTTP routes) lives in app.transport.routers.workflows.

Allowed imports FROM:
  shared, contracts, config, state, orchestration, tools.registry, skills, memory

NOT allowed:
  transport, agent, services (deprecated)
"""

from app.workflows.engine import WorkflowEngine
from app.workflows.store import WorkflowStore
from app.workflows.scheduler import WorkflowScheduler
from app.workflows.models import WorkflowDefinition, WorkflowRun, WorkflowStatus
from app.workflows.contracts import WorkflowContract

__all__ = [
    "WorkflowEngine",
    "WorkflowStore",
    "WorkflowScheduler",
    "WorkflowDefinition",
    "WorkflowRun",
    "WorkflowStatus",
    "WorkflowContract",
]
```

---

## TEIL B: `skills/`

### Schritt B1: Import-Audit

```powershell
cd backend

Select-String -Path "app/skills/*.py" -Pattern "^from|^import" |
    Select-Object Filename, LineNumber, Line |
    Format-Table -AutoSize
```

### Schritt B2: Import-Reparaturen für `service.py`

```python
# ALT
from app.services.skills_service import SkillsService
# NEU — direkt lokale Klassen
from app.skills.discovery import SkillDiscovery
from app.skills.retrieval import SkillRetrieval

# ALT
from app.services.agent_service import AgentService
# NEU — Skills sollen NICHT Agent importieren (Circular-Vermeidung)
# An die Skills übergeben was gebraucht wird, nicht den ganzen Agent importieren
```

### Schritt B3: Import-Reparaturen für `retrieval.py`

```python
# ALT
from app.services.memory_service import MemoryService
# NEU
from app.memory.memory_service import MemoryService

# ALT
from app.state.state_store import StateStore
# NEU — bleibt gleich (state/ wurde in Phase 04 schon richtig gesetzt)
from app.state.state_store import StateStore
```

### Schritt B4: Import-Reparaturen für `discovery.py`

```python
# ALT
from app.services.skill_discovery import SkillDiscoveryService
# NEU — lokale Klasse ist selbst der Service
from app.skills.models import SkillDefinition

# ALT
from app.skills_synced import ...
# NEU — skills_synced ist kein Python-Paket mehr (nach Phase 17 ist es data/)
# Config-Pfad für das skills-Verzeichnis aus config holen:
from app.config.paths import SKILLS_DIR
```

### Schritt B5: `__init__.py` für `skills/`

```python
# backend/app/skills/__init__.py
"""
skills — Skill Management Domain.

Handles skill discovery, retrieval, validation, and injection into agent prompts.
  - SkillService:        Main facade for skill operations
  - SkillDiscovery:      Finds available skills from config/data
  - SkillRetrieval:      Retrieves skills relevant to current context
  - SkillEligibility:    Checks if agent is eligible to use a skill
  - SkillValidator:      Validates skill definitions
  - SkillSnapshot:       Persists and restores skill state

Skills are loaded from: data/skills/ (see config/paths.py)

Allowed imports FROM:
  shared, contracts, config, state, memory

NOT allowed:
  transport, agent (prevents circular), tools, workflows, services (deprecated)
"""

from app.skills.service import SkillService
from app.skills.models import SkillDefinition, SkillSnapshot as SkillSnapshotModel
from app.skills.discovery import SkillDiscovery
from app.skills.eligibility import SkillEligibility
from app.skills.validation import SkillValidator

__all__ = [
    "SkillService",
    "SkillDefinition",
    "SkillSnapshotModel",
    "SkillDiscovery",
    "SkillEligibility",
    "SkillValidator",
]
```

---

## Verifikation

```powershell
cd backend

# 1. workflows imports OK
python -c "
from app.workflows import WorkflowEngine, WorkflowStore, WorkflowScheduler
print('workflows imports OK')
"

# 2. skills imports OK
python -c "
from app.skills import SkillService, SkillDefinition, SkillDiscovery
print('skills imports OK')
"

# 3. Keine alten Imports mehr
foreach ($domain in @("workflows", "skills")) {
    Write-Host "=== $domain old imports ==="
    Select-String -Path "app/$domain/*.py" -Pattern "from app\.services\.|from app\.orchestrator\.|from app\.handlers\.|from app\.routers\." |
        Select-Object Filename, LineNumber, Line
}

# 4. Tests
python -m pytest tests/ -k "workflow or skill" -q --tb=short 2>&1 | Select-Object -First 50
```

---

## Commit

```bash
git add -A
git commit -m "refactor(ddd): update workflows + skills imports to DDD paths — Phase 19"
```

---

## Status-Checkliste

### workflows/
- [ ] Import-Audit durchgeführt
- [ ] `router.py` → Transport-Shim oder bereits nach `transport/routers/workflows.py` verschoben
- [ ] `handlers.py` → Handler-Logik in Transport-Router (oder als Business-Logik behalten)
- [ ] `engine.py` imports aktualisiert
- [ ] `scheduler.py` imports aktualisiert
- [ ] `store.py` imports aktualisiert
- [ ] `chain_resolver.py` imports aktualisiert
- [ ] `tools.py` imports aktualisiert
- [ ] `transforms.py` imports aktualisiert
- [ ] `contracts.py` imports aktualisiert
- [ ] `__init__.py` clean public API

### skills/
- [ ] Import-Audit durchgeführt
- [ ] `service.py` imports aktualisiert
- [ ] `retrieval.py` imports aktualisiert
- [ ] `discovery.py` imports aktualisiert (SKILLS_DIR aus config/paths)
- [ ] `eligibility.py` imports aktualisiert
- [ ] `parser.py` imports aktualisiert
- [ ] `prompt.py` imports aktualisiert
- [ ] `snapshot.py` imports aktualisiert
- [ ] `validation.py` imports aktualisiert
- [ ] `__init__.py` clean public API

### Integration
- [ ] `workflows` imports OK
- [ ] `skills` imports OK
- [ ] Keine `app.services.*` Imports mehr in beiden Domains
- [ ] Tests laufen durch
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_20_CONNECTORS.md](./PHASE_20_CONNECTORS.md)
