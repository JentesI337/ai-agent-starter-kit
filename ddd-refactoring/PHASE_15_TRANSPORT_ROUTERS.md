# PHASE 15 — `transport/routers/` Konsolidierung

> **Session-Ziel:** Die künstliche Trennung zwischen `routers/` und `handlers/` aufheben. 16 alte Router + 12 Handler-Dateien → 16 neue Transport-Router. Dies ist die größte strukturelle Konsolidierung.
>
> **Voraussetzung:** PHASE_14 (transport/ Bootstrap) abgeschlossen
> **Folge-Phase:** PHASE_16_MAIN_SLIMDOWN.md
> **Geschätzter Aufwand:** ~5–7 Stunden (viele Merges!)
> **Betroffene Quelldateien:** 28 Dateien → 16 Zieldateien

---

## Konsolidierungs-Map

| Quelldatei(en) | Zieldatei |
|----------------|-----------|
| `routers/agents.py` + `handlers/agent_handlers.py` + `handlers/agent_config_handlers.py` + `routers/control_agent_config.py` | `transport/routers/agents.py` |
| `run_endpoints.py` + `routers/control_runs.py` + `routers/run_api.py` + `handlers/run_handlers.py` | `transport/routers/runs.py` |
| `routers/control_sessions.py` + `handlers/session_handlers.py` | `transport/routers/sessions.py` |
| `subrun_endpoints.py` + `routers/subruns.py` | `transport/routers/subruns.py` |
| `routers/control_tools.py` + `routers/control_tool_config.py` + `handlers/tools_handlers.py` + `handlers/tool_config_handlers.py` | `transport/routers/tools.py` |
| `routers/policies.py` + `routers/control_policy_approvals.py` + `handlers/policy_handlers.py` | `transport/routers/policies.py` |
| `handlers/skills_handlers.py` | `transport/routers/skills.py` |
| `routers/control_integrations.py` + `handlers/integration_handlers.py` | `transport/routers/integrations.py` |
| `routers/uploads.py` | `transport/routers/uploads.py` |
| `routers/webhooks.py` | `transport/routers/webhooks.py` |
| `workflows/router.py` | `transport/routers/workflows.py` |
| `routers/control_config.py` + `routers/control_execution_config.py` + `handlers/config_handlers.py` + `handlers/execution_config_handlers.py` | `transport/routers/config.py` |
| `handlers/audio_deps_handlers.py` | `transport/routers/audio_deps.py` |
| `runtime_debug_endpoints.py` + `routers/runtime_debug.py` | `transport/routers/debug.py` |
| `routers/ws_agent_router.py` | `transport/routers/ws_agent.py` |
| `control_router_wiring.py` + `routers/__init__.py` | `transport/routers/__init__.py` |

---

## Merge-Strategie (gilt für alle Router)

Für jede Zieldatei:

1. **Kelle lesen:** Alle Quelldateien öffnen und Inhalt verstehen
2. **FastAPI Router-Instanz:** Entweder eine neue `APIRouter(prefix=..., tags=[...])` Instanz
3. **Endpunkte zusammenführen:** Alle `@router.get/post/put/delete` Decorator-Funktionen übernehmen
4. **Handler-Funktionen:** Handler-Logik direkt in den Router integrieren (kein separates `handlers/` mehr)
5. **Imports bereinigen:** Alle alten `from app.handlers.*import` etc. auf neue Pfade

---

## 1. `transport/routers/__init__.py` (Router-Wiring)

Dies ersetzt `control_router_wiring.py`:

```python
# backend/app/transport/routers/__init__.py
"""
Router registration — replaces control_router_wiring.py.
Registers all domain routers with the FastAPI app instance.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.transport.routers import (
    agents, runs, sessions, subruns, tools, policies,
    skills, integrations, uploads, webhooks, workflows,
    config, audio_deps, debug, ws_agent,
)


def include_all_routers(app: FastAPI) -> None:
    """Register all domain routers with the FastAPI application."""
    app.include_router(agents.router)
    app.include_router(runs.router)
    app.include_router(sessions.router)
    app.include_router(subruns.router)
    app.include_router(tools.router)
    app.include_router(policies.router)
    app.include_router(skills.router)
    app.include_router(integrations.router)
    app.include_router(uploads.router)
    app.include_router(webhooks.router)
    app.include_router(workflows.router)
    app.include_router(config.router)
    app.include_router(audio_deps.router)
    app.include_router(debug.router)
    app.include_router(ws_agent.router)
```

---

## 2. Jeder Router im Detail

### 2.1 `transport/routers/agents.py`

**Quelldateien lesen:**
```powershell
Get-Content "backend/app/routers/agents.py" | Measure-Object -Line
Get-Content "backend/app/handlers/agent_handlers.py" | Measure-Object -Line
Get-Content "backend/app/handlers/agent_config_handlers.py" | Measure-Object -Line
Get-Content "backend/app/routers/control_agent_config.py" | Measure-Object -Line
```

**Struktur der Zieldatei:**
```python
# backend/app/transport/routers/agents.py
"""Agent management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.shared.control_models import ...
from app.transport.app_state import ControlPlaneState
from app.agent.store import UnifiedAgentStore
# ... weitere Imports aus den Quelldateien

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# --- Aus routers/agents.py + handlers/agent_handlers.py ---
@router.get("/")
async def list_agents(...):
    # Handler-Logik direkt hier (aus agent_handlers.py)
    ...

@router.post("/")
async def create_agent(...):
    ...

# --- Aus routers/control_agent_config.py + handlers/agent_config_handlers.py ---
@router.get("/{agent_id}/config")
async def get_agent_config(...):
    ...
```

**Stubs:**
```python
# backend/app/routers/agents.py — DEPRECATED → app.transport.routers.agents
from app.transport.routers.agents import router  # noqa: F401
```
```python
# backend/app/handlers/agent_handlers.py — DEPRECATED → app.transport.routers.agents
# Handler functions moved directly into the router
```
```python
# backend/app/handlers/agent_config_handlers.py — DEPRECATED → app.transport.routers.agents
```

---

### 2.2–2.15: Alle weiteren Router

**Gleiche Vorgehensweise für jeden Router. KURZ-REFERENZ:**

#### `transport/routers/runs.py`
Quellen: `run_endpoints.py` + `routers/control_runs.py` + `routers/run_api.py` + `handlers/run_handlers.py`

#### `transport/routers/sessions.py`
Quellen: `routers/control_sessions.py` + `handlers/session_handlers.py`

#### `transport/routers/subruns.py`
Quellen: `subrun_endpoints.py` + `routers/subruns.py`

#### `transport/routers/tools.py`
Quellen: `routers/control_tools.py` + `routers/control_tool_config.py` + `handlers/tools_handlers.py` + `handlers/tool_config_handlers.py`

#### `transport/routers/policies.py`
Quellen: `routers/policies.py` + `routers/control_policy_approvals.py` + `handlers/policy_handlers.py`

#### `transport/routers/skills.py`
Quellen: `handlers/skills_handlers.py`

#### `transport/routers/integrations.py`
Quellen: `routers/control_integrations.py` + `handlers/integration_handlers.py`

#### `transport/routers/uploads.py`
Quellen: `routers/uploads.py` (direktes Kopieren + Imports fixen)

#### `transport/routers/webhooks.py`
Quellen: `routers/webhooks.py` (direktes Kopieren + Imports fixen)

#### `transport/routers/workflows.py`
Quellen: `workflows/router.py` (direktes Kopieren + Imports fixen)

#### `transport/routers/config.py`
Quellen: `routers/control_config.py` + `routers/control_execution_config.py` + `handlers/config_handlers.py` + `handlers/execution_config_handlers.py`

#### `transport/routers/audio_deps.py`
Quellen: `handlers/audio_deps_handlers.py` (direktes Kopieren + Imports fixen)

#### `transport/routers/debug.py`
Quellen: `runtime_debug_endpoints.py` + `routers/runtime_debug.py`

#### `transport/routers/ws_agent.py`
Quellen: `routers/ws_agent_router.py` (direktes Kopieren + Imports fixen)

---

## 3. Import-Rewrites in allen neuen Router-Dateien

Für alle `transport/routers/*.py` Dateien:

```powershell
# Alle falschen Imports finden
Select-String -Path "backend/app/transport/routers/*.py" -Pattern "^from app\." | Where-Object {
    $_.Line -match "from app\.(handlers|services|agents|orchestrator|model_routing|tool_modules)\."
}
```

**Standard-Rewrites (für alle Router):**

| Alt | Neu |
|-----|-----|
| `from app.handlers.*` | entfernen (Logik ist jetzt im Router selbst) |
| `from app.agents.agent_store import` | `from app.agent.store import` |
| `from app.agents.factory_defaults import` | `from app.agent.factory_defaults import` |
| `from app.app_state import ControlPlaneState` | `from app.transport.app_state import ControlPlaneState` |
| `from app.control_models import` | `from app.shared.control_models import` |
| `from app.errors import` | `from app.shared.errors import` oder `from app.policy.errors import` |
| `from app.services.policy_approval_service import` | `from app.policy.approval_service import` |
| `from app.services.session_query_service import` | `from app.session.query_service import` |
| `from app.services.tool_execution_manager import` | `from app.tools.execution.manager import` |
| `from app.services.tool_registry import` | `from app.tools.registry.registry import` |
| `from app.orchestrator.pipeline_runner import` | `from app.orchestration.pipeline_runner import` |
| `from app.state.state_store import` | `from app.state.state_store import` (unverändert) |
| `from app.models import` | `from app.transport.ws_models import` |

---

## 4. Stubs für alle alten Router + Handler

```powershell
# Alle routers/ als Stubs
Get-ChildItem "backend/app/routers" -Name "*.py" | Where-Object { $_ -ne "__init__.py" } | ForEach-Object {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($_)
    $content = "# DEPRECATED: moved to app.transport.routers`n# This file is kept for backwards compatibility only"
    Set-Content "backend/app/routers/$_" $content
    Write-Host "Stub: routers/$_"
}

# Alle handlers/ als Stubs
Get-ChildItem "backend/app/handlers" -Name "*.py" | Where-Object { $_ -ne "__init__.py" } | ForEach-Object {
    $content = "# DEPRECATED: handler functions moved into app.transport.routers`n# This file is kept for backwards compatibility only"
    Set-Content "backend/app/handlers/$_" $content
    Write-Host "Stub: handlers/$_"
}

# routers/__init__.py
Set-Content "backend/app/routers/__init__.py" "# DEPRECATED → app.transport.routers"

# handlers/__init__.py
Set-Content "backend/app/handlers/__init__.py" "# DEPRECATED → app.transport.routers"
```

---

## 5. `control_router_wiring.py` Stub

```python
# backend/app/control_router_wiring.py
# DEPRECATED: moved to app.transport.routers
from app.transport.routers import include_all_routers  # noqa: F401
```

**Und in `transport/app_factory.py`**: Den TODO von Phase 14 auflösen:
```python
# ALT (Phase 14 Placeholder):
from app.control_router_wiring import include_all_routers

# NEU:
from app.transport.routers import include_all_routers
```

---

## 6. Verifikation

```powershell
$checks = @(
    "backend/app/transport/routers/__init__.py",
    "backend/app/transport/routers/agents.py",
    "backend/app/transport/routers/runs.py",
    "backend/app/transport/routers/sessions.py",
    "backend/app/transport/routers/subruns.py",
    "backend/app/transport/routers/tools.py",
    "backend/app/transport/routers/policies.py",
    "backend/app/transport/routers/skills.py",
    "backend/app/transport/routers/integrations.py",
    "backend/app/transport/routers/uploads.py",
    "backend/app/transport/routers/webhooks.py",
    "backend/app/transport/routers/workflows.py",
    "backend/app/transport/routers/config.py",
    "backend/app/transport/routers/audio_deps.py",
    "backend/app/transport/routers/debug.py",
    "backend/app/transport/routers/ws_agent.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
# Alle 15 Router importierbar?
python -c "
from app.transport.routers import include_all_routers
from app.transport.routers.agents import router as agents_router
from app.transport.routers.runs import router as runs_router
from app.transport.routers.tools import router as tools_router
print('All routers importable')
"

# App startbar? (schneller Check)
python -c "
from app.transport.app_factory import build_fastapi_app
app = build_fastapi_app()
print('App created OK, routes:', len(app.routes))
"
```

---

## 7. Commit

```bash
git add -A
git commit -m "refactor(ddd): consolidate routers/ + handlers/ into transport/routers/ — Phase 15"
```

---

## Status-Checkliste

- [ ] `transport/routers/__init__.py` mit `include_all_routers()` erstellt
- [ ] `transport/routers/agents.py` (4 Quellen gemergt)
- [ ] `transport/routers/runs.py` (4 Quellen gemergt)
- [ ] `transport/routers/sessions.py` (2 Quellen gemergt)
- [ ] `transport/routers/subruns.py` (2 Quellen gemergt)
- [ ] `transport/routers/tools.py` (4 Quellen gemergt)
- [ ] `transport/routers/policies.py` (3 Quellen gemergt)
- [ ] `transport/routers/skills.py` (1 Quelle)
- [ ] `transport/routers/integrations.py` (2 Quellen gemergt)
- [ ] `transport/routers/uploads.py` (1 Quelle)
- [ ] `transport/routers/webhooks.py` (1 Quelle)
- [ ] `transport/routers/workflows.py` (aus workflows/router.py)
- [ ] `transport/routers/config.py` (4 Quellen gemergt)
- [ ] `transport/routers/audio_deps.py` (1 Quelle)
- [ ] `transport/routers/debug.py` (2 Quellen gemergt)
- [ ] `transport/routers/ws_agent.py` (1 Quelle)
- [ ] `control_router_wiring.py` Stub erstellt
- [ ] `transport/app_factory.py` Phase-14-TODO aufgelöst
- [ ] Alle routers/ + handlers/ Files zu Stubs gemacht
- [ ] Alle Import-Rewrites in neuen Routern durchgeführt
- [ ] App startet ohne Fehler
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_16_MAIN_SLIMDOWN.md](./PHASE_16_MAIN_SLIMDOWN.md)
