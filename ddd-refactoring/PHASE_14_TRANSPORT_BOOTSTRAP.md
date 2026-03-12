# PHASE 14 — `transport/` Bootstrap + WebSocket

> **Session-Ziel:** Die App-Bootstrap-Dateien und den WebSocket-Handler in `transport/` migrieren (ohne die Router — die kommen in Phase 15).
>
> **Voraussetzung:** PHASE_12 (agent/) + PHASE_13 (orchestration/) abgeschlossen
> **Folge-Phase:** PHASE_15_TRANSPORT_ROUTERS.md
> **Geschätzter Aufwand:** ~3–4 Stunden
> **Betroffene Quelldateien:** 6 Dateien (darunter `ws_handler.py` mit 1658 Zeilen!)

---

## Dateien-Übersicht

| Quelldatei | Zieldatei | Größe |
|------------|-----------|-------|
| `app/app_setup.py` | `app/transport/app_factory.py` | mittel |
| `app/app_state.py` | `app/transport/app_state.py` | mittel |
| `app/startup_tasks.py` | `app/transport/startup.py` | mittel |
| `app/runtime_manager.py` | `app/transport/runtime_manager.py` | mittel |
| `app/ws_handler.py` | `app/transport/ws_handler.py` | ~1658 Zeilen! |
| `app/models.py` | `app/transport/ws_models.py` | mittel |

---

## 1. Erlaubte Imports für `transport/`

```
transport/ darf nutzen:
  ✓ agent/           (HeadAgent, AgentRunner, UnifiedAgentStore)
  ✓ orchestration/   (PipelineRunner, SessionLaneManager)
  ✓ workflows/       (WorkflowEngine)
  ✓ shared/          (ControlModels, Errors)
  ✓ policy/          (PolicyStore, RateLimiter, CircuitBreaker)
  ✓ contracts/       (AgentContract)
  ✓ config/          (Settings)
  ✓ session/         (SessionInboxService)
  ✓ state/           (StateStore)
  ✓ memory/          (MemoryStore)

  ✗ llm/             (kein direkter LLM-Zugriff aus Transport!)
  ✗ tools/           (kein direkter Tool-Zugriff aus Transport!)
  ✗ reasoning/       (kein direkter Reasoning-Zugriff aus Transport!)
```

---

## 2. `app/models.py` → `app/transport/ws_models.py`

Fange mit der kleinsten Datei an (Modelle haben wenige Abhängigkeiten):

```powershell
Copy-Item "backend/app/models.py" "backend/app/transport/ws_models.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/transport/ws_models.py" -Pattern "^from app\."
```

Pydantic-Modelle sollten nur `shared/`, `contracts/` oder externen Bibliotheken importieren.  
Falls `from app.control_models import ...` → `from app.shared.control_models import ...`

**Stub in original:**
```python
# backend/app/models.py — DEPRECATED → app.transport.ws_models
from app.transport.ws_models import *  # noqa: F401, F403
```

---

## 3. `app/app_state.py` → `app/transport/app_state.py`

```powershell
Copy-Item "backend/app/app_state.py" "backend/app/transport/app_state.py"
```

**app_state.py enthält `ControlPlaneState`, `LazyRuntimeRegistry` etc.**  
Diese Datei ist _der_ zentrale Zustandshalter des Systems.

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/transport/app_state.py" -Pattern "^from app\."
```

Häufige Imports die gefixt werden müssen:

| Alt | Neu |
|-----|-----|
| `from app.agent import HeadAgent` | `from app.agent.head_agent import HeadAgent` |
| `from app.agents.agent_store import UnifiedAgentStore` | `from app.agent.store import UnifiedAgentStore` |
| `from app.llm_client import LlmClient` | `from app.llm.client import LlmClient` |
| `from app.errors import` | `from app.shared.errors import` |
| `from app.config import settings` | `from app.config.settings import settings` |

**Stub in original:**
```python
# backend/app/app_state.py — DEPRECATED → app.transport.app_state
from app.transport.app_state import *  # noqa: F401, F403
from app.transport.app_state import ControlPlaneState, LazyMappingProxy, LazyObjectProxy, LazyRuntimeRegistry, RuntimeComponents
```

---

## 4. `app/runtime_manager.py` → `app/transport/runtime_manager.py`

```powershell
Copy-Item "backend/app/runtime_manager.py" "backend/app/transport/runtime_manager.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/transport/runtime_manager.py" -Pattern "^from app\."
```

Häufige Rewrites:

| Alt | Neu |
|-----|-----|
| `from app.app_state import ControlPlaneState` | `from app.transport.app_state import ControlPlaneState` |
| `from app.llm_client import` | `from app.llm.client import` |

**Stub:**
```python
# backend/app/runtime_manager.py — DEPRECATED → app.transport.runtime_manager
from app.transport.runtime_manager import *  # noqa: F401, F403
```

---

## 5. `app/startup_tasks.py` → `app/transport/startup.py`

```powershell
Copy-Item "backend/app/startup_tasks.py" "backend/app/transport/startup.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/transport/startup.py" -Pattern "^from app\."
```

Häufige Rewrites:

| Alt | Neu |
|-----|-----|
| `from app.app_state import ControlPlaneState` | `from app.transport.app_state import ControlPlaneState` |
| `from app.agents.agent_store import` | `from app.agent.store import` |
| `from app.agents.factory_defaults import` | `from app.agent.factory_defaults import` |
| `from app.config_service import init_config_service` | `from app.config.service import init_config_service` |
| `from app.memory import MemoryStore` | `from app.memory import MemoryStore` (via package, OK) |
| `from app.state.state_store import` | `from app.state.state_store import` (unverändert) |

**Stub:**
```python
# backend/app/startup_tasks.py — DEPRECATED → app.transport.startup
from app.transport.startup import *  # noqa: F401, F403
```

---

## 6. `app/app_setup.py` → `app/transport/app_factory.py`

```powershell
Copy-Item "backend/app/app_setup.py" "backend/app/transport/app_factory.py"
```

> **Namensänderung:** `app_setup.py` → `app_factory.py`. Der Haupteinstiegspunkt heißt `build_fastapi_app()`.

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/transport/app_factory.py" -Pattern "^from app\."
```

Häufige Rewrites:

| Alt | Neu |
|-----|-----|
| `from app.app_state import` | `from app.transport.app_state import` |
| `from app.startup_tasks import` | `from app.transport.startup import` |
| `from app.runtime_manager import` | `from app.transport.runtime_manager import` |
| `from app.control_router_wiring import` | `from app.transport.routers import include_all_routers` (Phase 15!) |
| `from app.config import settings` | `from app.config.settings import settings` |
| `from app.policy.log_secret_filter import LogSecretFilter` | unverändert (korrekt) |

> **ACHTUNG:** `control_router_wiring` ist noch nicht migriert (Phase 15). Nutze einen Platzhalter:
> ```python
> # TODO Phase 15: from app.transport.routers import include_all_routers
> from app.control_router_wiring import include_all_routers  # DEPRECATED, Phase 15 fix
> ```

**Stub:**
```python
# backend/app/app_setup.py — DEPRECATED → app.transport.app_factory
from app.transport.app_factory import build_fastapi_app, build_lifespan_context  # noqa: F401
```

---

## 7. `app/ws_handler.py` → `app/transport/ws_handler.py` (~1658 Zeilen)

```powershell
Copy-Item "backend/app/ws_handler.py" "backend/app/transport/ws_handler.py"
```

**Imports VOLLSTÄNDIG prüfen:**
```powershell
Select-String -Path "backend/app/transport/ws_handler.py" -Pattern "^from app\." | Select-Object LineNumber, Line
```

**Systematische Rewrites:**

| Alt | Neu |
|-----|-----|
| `from app.agent import HeadAgent` | `from app.agent.head_agent import HeadAgent` |
| `from app.agent_runner import AgentRunner` | `from app.agent.runner import AgentRunner` |
| `from app.models import WsInboundEnvelope` | `from app.transport.ws_models import WsInboundEnvelope` |
| `from app.app_state import ControlPlaneState` | `from app.transport.app_state import ControlPlaneState` |
| `from app.errors import` | `from app.shared.errors import` oder `from app.policy.errors import` |
| `from app.services.session_inbox_service import` | `from app.session.inbox_service import` |
| `from app.services.session_security import` | `from app.session.security import` |
| `from app.services.rate_limiter import` | `from app.policy.rate_limiter import` |
| `from app.services.circuit_breaker import` | `from app.policy.circuit_breaker import` |
| `from app.memory import MemoryStore` | `from app.memory import MemoryStore` (via package, OK) |
| `from app.control_models import` | `from app.shared.control_models import` |

**Stub:**
```python
# backend/app/ws_handler.py — DEPRECATED → app.transport.ws_handler
from app.transport.ws_handler import WebSocketHandler, handle_websocket  # noqa: F401
```

---

## 8. `transport/__init__.py` befüllen

```python
# backend/app/transport/__init__.py
"""
HTTP/WebSocket transport layer.
Imports allowed from: agent/, orchestration/, workflows/, shared/, policy/, contracts/, config/, session/, state/, memory/
"""
from app.transport.app_factory import build_fastapi_app, build_lifespan_context
from app.transport.app_state import ControlPlaneState

__all__ = ["build_fastapi_app", "build_lifespan_context", "ControlPlaneState"]
```

---

## 9. Verifikation

```powershell
$checks = @(
    "backend/app/transport/__init__.py",
    "backend/app/transport/app_factory.py",
    "backend/app/transport/app_state.py",
    "backend/app/transport/startup.py",
    "backend/app/transport/runtime_manager.py",
    "backend/app/transport/ws_handler.py",
    "backend/app/transport/ws_models.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
python -c "
from app.transport.ws_models import *
from app.transport.app_state import ControlPlaneState
print('transport/ bootstrap OK')
"

# Stubs prüfen
python -c "
from app.app_state import ControlPlaneState
from app.models import *
from app.app_setup import build_fastapi_app
print('Stubs OK')
"
```

---

## 10. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate transport/ bootstrap + ws_handler — Phase 14"
```

---

## Status-Checkliste

- [ ] `transport/ws_models.py` erstellt (aus models.py), Stub
- [ ] `transport/app_state.py` erstellt, Imports gefixt (HeadAgent, LlmClient etc.), Stub
- [ ] `transport/runtime_manager.py` erstellt, Imports gefixt, Stub
- [ ] `transport/startup.py` erstellt, Imports gefixt, Stub
- [ ] `transport/app_factory.py` erstellt (aus app_setup.py), Namensänderung!, control_router_wiring TODO markiert, Stub
- [ ] `transport/ws_handler.py` erstellt (1658 Zeilen!), ALLE Imports systematisch gefixt, Stub
- [ ] `transport/__init__.py` befüllt
- [ ] Smoke-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_15_TRANSPORT_ROUTERS.md](./PHASE_15_TRANSPORT_ROUTERS.md)
