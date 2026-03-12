# PHASE 13 — `orchestration/` + `contracts/` (Abschluss)

> **Session-Ziel:** `orchestrator/` nach `orchestration/` migrieren und `interfaces/` in `contracts/` zusammenführen (wurde in Phase 01 begonnen).
>
> **Voraussetzung:** PHASE_12 (agent/) abgeschlossen
> **Folge-Phase:** PHASE_14_TRANSPORT_BOOTSTRAP.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Quelldateien:** 10 Dateien

---

## Dateien-Übersicht

### `orchestrator/` → `orchestration/`

| Quelldatei | Zieldatei |
|------------|-----------|
| `orchestrator/pipeline_runner.py` | `orchestration/pipeline_runner.py` |
| `orchestrator/fallback_state_machine.py` | `orchestration/fallback_state_machine.py` |
| `orchestrator/run_state_machine.py` | `orchestration/run_state_machine.py` |
| `orchestrator/session_lane_manager.py` | `orchestration/session_lane_manager.py` |
| `orchestrator/subrun_lane.py` | `orchestration/subrun_lane.py` |
| `orchestrator/events.py` | `orchestration/events.py` |
| `orchestrator/step_types.py` | `orchestration/step_types.py` |
| `orchestrator/recovery_strategy.py` | `orchestration/recovery_strategy.py` |

### `interfaces/` → `contracts/` (Rest aus Phase 01)

| Quelldatei | Zieldatei | Status |
|------------|-----------|--------|
| `interfaces/orchestrator_api.py` | `contracts/orchestrator_api.py` | In Phase 01 erledigt |
| `interfaces/request_context.py` | `contracts/orchestrator_api.py` | In Phase 01 erledigt (merge) |

---

## 1. Erlaubte Imports für `orchestration/`

```
orchestration/ darf nutzen:
  ✓ agent/       (via contracts — HeadAgent Protokoll, nicht direkte Klasse)
  ✓ session/     (SessionInboxService)
  ✓ state/       (StateStore, Snapshots)
  ✓ memory/      (MemoryStore)
  ✓ policy/      (CircuitBreaker, RateLimiter)
  ✓ shared/      (Errors)
  ✓ contracts/   (OrchestratorApi, AgentContract)
  ✓ config/

  ✗ transport/   (VERBOTEN)
  ✗ tools/       (VERBOTEN — Orchestration kennt keine Tool-Details)
```

---

## 2. Alle 8 `orchestrator/` Dateien kopieren

```powershell
$orchFiles = @(
    "pipeline_runner",
    "fallback_state_machine",
    "run_state_machine",
    "session_lane_manager",
    "subrun_lane",
    "events",
    "step_types",
    "recovery_strategy"
)

foreach ($f in $orchFiles) {
    Copy-Item "backend/app/orchestrator/$f.py" "backend/app/orchestration/$f.py"
    Write-Host "Copied: $f.py → orchestration/$f.py"
}
```

---

## 3. Imports in allen `orchestration/` Dateien prüfen und fixen

```powershell
Select-String -Path "backend/app/orchestration/*.py" -Pattern "^from app\." | Select-Object Filename, LineNumber, Line
```

**Import-Rewrites die notwendig sein werden:**

| Alt | Neu |
|-----|-----|
| `from app.orchestrator.pipeline_runner import` | `from app.orchestration.pipeline_runner import` |
| `from app.orchestrator.fallback_state_machine import` | `from app.orchestration.fallback_state_machine import` |
| `from app.orchestrator.run_state_machine import` | `from app.orchestration.run_state_machine import` |
| `from app.orchestrator.session_lane_manager import` | `from app.orchestration.session_lane_manager import` |
| `from app.orchestrator.subrun_lane import` | `from app.orchestration.subrun_lane import` |
| `from app.orchestrator.events import` | `from app.orchestration.events import` |
| `from app.orchestrator.step_types import` | `from app.orchestration.step_types import` |
| `from app.orchestrator.recovery_strategy import` | `from app.orchestration.recovery_strategy import` |
| `from app.interfaces.orchestrator_api import` | `from app.contracts.orchestrator_api import` |
| `from app.interfaces.request_context import` | `from app.contracts.orchestrator_api import` |
| `from app.agent import HeadAgent` | `from app.contracts.agent_contract import AgentContract` (via Protocol!) |
| `from app.services.session_inbox_service import` | `from app.session.inbox_service import` |
| `from app.state.state_store import` | `from app.state.state_store import` (unverändert) |
| `from app.errors import` | `from app.shared.errors import` |

> **WICHTIG:** `orchestration/pipeline_runner.py` kommuniziert mit dem Agent via das`AgentContract`-Protokoll aus `contracts/`, NICHT durch direkten Import von `HeadAgent`. Das ist der DDD-Kern: Orchestrierung kennt nur das Protokoll, nicht die Implementierung.

---

## 4. Stubs für `orchestrator/` Originale

```powershell
$orchStubs = @{
    "pipeline_runner" = "app.orchestration.pipeline_runner"
    "fallback_state_machine" = "app.orchestration.fallback_state_machine"
    "run_state_machine" = "app.orchestration.run_state_machine"
    "session_lane_manager" = "app.orchestration.session_lane_manager"
    "subrun_lane" = "app.orchestration.subrun_lane"
    "events" = "app.orchestration.events"
    "step_types" = "app.orchestration.step_types"
    "recovery_strategy" = "app.orchestration.recovery_strategy"
}

foreach ($orig in $orchStubs.Keys) {
    $new = $orchStubs[$orig]
    $content = "# DEPRECATED: moved to $new`nfrom $new import *  # noqa: F401, F403"
    Set-Content "backend/app/orchestrator/$orig.py" $content
    Write-Host "Stub: $orig.py"
}
```

**`orchestrator/__init__.py` als Stub:**
```python
# backend/app/orchestrator/__init__.py
# DEPRECATED: module moved to app.orchestration.*
from app.orchestration import *  # noqa: F401, F403
```

---

## 5. `orchestration/__init__.py` befüllen

```python
# backend/app/orchestration/__init__.py
"""
Orchestration pipeline domain.
Communicates with agent/ only via contracts.AgentContract (Protocol).
Imports allowed from: agent/ (via contracts), session/, state/, memory/, policy/, shared/, contracts/, config/
"""
from app.orchestration.events import *  # OrchestratorEvent, RunEvent etc.
from app.orchestration.step_types import *  # StepType etc.
from app.orchestration.pipeline_runner import PipelineRunner
from app.orchestration.run_state_machine import RunStateMachine
from app.orchestration.fallback_state_machine import FallbackStateMachine
from app.orchestration.session_lane_manager import SessionLaneManager
from app.orchestration.subrun_lane import SubrunLane
from app.orchestration.recovery_strategy import RecoveryStrategy

__all__ = [
    "PipelineRunner", "RunStateMachine", "FallbackStateMachine",
    "SessionLaneManager", "SubrunLane", "RecoveryStrategy",
]
```

---

## 6. `interfaces/` Cleanup

Phase 01 hat `orchestrator_api.py` und `request_context.py` bereits nach `contracts/` migriert.  
Jetzt `interfaces/` komplett als Stub:

```python
# backend/app/interfaces/__init__.py
# DEPRECATED: interfaces/ merged into app.contracts
from app.contracts import *  # noqa: F401, F403
```

```python
# backend/app/interfaces/orchestrator_api.py (falls noch nicht stub)
# DEPRECATED → app.contracts.orchestrator_api
from app.contracts.orchestrator_api import *  # noqa: F401, F403
```

```python
# backend/app/interfaces/request_context.py (falls noch nicht stub)
# DEPRECATED → app.contracts.orchestrator_api
from app.contracts.orchestrator_api import *  # noqa: F401, F403
```

---

## 7. Verifikation

```powershell
$checks = @(
    "backend/app/orchestration/pipeline_runner.py",
    "backend/app/orchestration/fallback_state_machine.py",
    "backend/app/orchestration/run_state_machine.py",
    "backend/app/orchestration/session_lane_manager.py",
    "backend/app/orchestration/subrun_lane.py",
    "backend/app/orchestration/events.py",
    "backend/app/orchestration/step_types.py",
    "backend/app/orchestration/recovery_strategy.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.orchestration.events import *
from app.orchestration.step_types import *
from app.orchestration import PipelineRunner, SessionLaneManager
print('orchestration/ OK')
"

# Stubs prüfen
python -c "
from app.orchestrator.pipeline_runner import PipelineRunner
from app.interfaces.orchestrator_api import *
print('Stubs OK')
"
```

---

## 8. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate orchestration/ domain and complete contracts/ — Phase 13"
```

---

## Status-Checkliste

- [ ] `orchestration/` alle 8 Dateien kopiert
- [ ] Alle interne `orchestrator/`-Querverweise auf `orchestration/` geändert
- [ ] Agent-Kommunikation via `contracts.AgentContract` statt direktem `HeadAgent`-Import
- [ ] `interfaces/`-Imports auf `contracts/` aktualisiert
- [ ] Stubs für alle 8 `orchestrator/` Originale
- [ ] `orchestrator/__init__.py` als Stub
- [ ] `interfaces/__init__.py` + einzelne files als Stubs
- [ ] `orchestration/__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_14_TRANSPORT_BOOTSTRAP.md](./PHASE_14_TRANSPORT_BOOTSTRAP.md)
