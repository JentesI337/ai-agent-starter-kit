# PHASE 12 — `agent/` Domain (Kern-Domäne)

> **Session-Ziel:** Die Kern-Agenten-Domäne migrieren. Dies umfasst den HeadAgent (1769 Zeilen!), den AgentRunner (1667 Zeilen!) und das Agent-Store-System.
>
> **Voraussetzung:** PHASE_11 (tools/implementations) + PHASE_08 (reasoning/) + PHASE_07 (memory/) abgeschlossen
> **Folge-Phase:** PHASE_13_ORCHESTRATION.md
> **Geschätzter Aufwand:** ~4–5 Stunden (große Monolithen!)
> **Betroffene Quelldateien:** 7 Dateien

---

## Dateien-Übersicht

| Quelldatei | Zieldatei | Größe |
|------------|-----------|-------|
| `app/agent.py` | `app/agent/head_agent.py` | ~1769 Zeilen |
| `app/agent_runner.py` | `app/agent/runner.py` | ~1667 Zeilen |
| `app/agent_runner_types.py` | `app/agent/runner_types.py` | klein |
| `app/agents/agent_store.py` | `app/agent/store.py` | mittel |
| `app/agents/unified_agent_record.py` | `app/agent/record.py` | mittel |
| `app/agents/unified_adapter.py` | `app/agent/adapter.py` | mittel |
| `app/agents/factory_defaults.py` | `app/agent/factory_defaults.py` | mittel |
| `app/services/agent_resolution.py` | `app/agent/resolution.py` | mittel |
| `app/agents/agents_manifest.json` | `app/agent/manifest.json` | JSON |

---

## 1. Erlaubte Imports für `agent/`

```
agent/ darf nutzen:
  ✓ llm/         (LlmClient, ModelRouter)
  ✓ tools/       (ToolCatalog, ToolRegistry, AgentTooling, ToolExecutionManager)
  ✓ memory/      (MemoryStore, LongTermMemory)
  ✓ reasoning/   (ActionParser, IntentDetector, ReplyShaper, PromptKernelBuilder)
  ✓ quality/     (ReflectionService, VerificationService)
  ✓ policy/      (PolicyStore, CircuitBreaker, AgentIsolation)
  ✓ contracts/   (AgentContract, ToolProvider, OrchestratorApi)
  ✓ shared/      (Errors, ControlModels)
  ✓ config/      (Settings)

  ✗ transport/   (VERBOTEN — kein HTTP/WS-Wissen in der Agenten-Domäne)
  ✗ orchestration/ (nur via contracts)
```

---

## 2. `app/agent_runner_types.py` → `app/agent/runner_types.py`

Fange mit der kleinsten Datei an:

```powershell
Copy-Item "backend/app/agent_runner_types.py" "backend/app/agent/runner_types.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/agent/runner_types.py" -Pattern "^from app\."
```

Typ-Definitionen haben meist wenige Abhängigkeiten.

**Stub:**
```python
# backend/app/agent_runner_types.py — DEPRECATED → app.agent.runner_types
from app.agent.runner_types import *  # noqa: F401, F403
```

---

## 3. `app/agents/unified_agent_record.py` → `app/agent/record.py`

```powershell
Copy-Item "backend/app/agents/unified_agent_record.py" "backend/app/agent/record.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/agent/record.py" -Pattern "^from app\."
```

**Stub in original:**
```python
# backend/app/agents/unified_agent_record.py — DEPRECATED → app.agent.record
from app.agent.record import *  # noqa: F401, F403
```

---

## 4. `app/agents/unified_adapter.py` → `app/agent/adapter.py`

```powershell
Copy-Item "backend/app/agents/unified_adapter.py" "backend/app/agent/adapter.py"
```

**Imports prüfen:**  
Falls `from app.agents.unified_agent_record import ...` → `from app.agent.record import ...`  
Falls `from app.agents.agent_store import ...` → `from app.agent.store import ...` (nach Schritt 5)

**Stub:**
```python
# backend/app/agents/unified_adapter.py — DEPRECATED → app.agent.adapter
from app.agent.adapter import *  # noqa: F401, F403
```

---

## 5. `app/agents/agent_store.py` → `app/agent/store.py`

```powershell
Copy-Item "backend/app/agents/agent_store.py" "backend/app/agent/store.py"
```

**Imports prüfen:**
```powershell
Select-String -Path "backend/app/agent/store.py" -Pattern "^from app\."
```

Häufige Imports die gefixt werden müssen:
- `from app.agents.unified_agent_record import ...` → `from app.agent.record import ...`
- `from app.agents.unified_adapter import ...` → `from app.agent.adapter import ...`
- `from app.agents.factory_defaults import ...` → `from app.agent.factory_defaults import ...`

**Stub:**
```python
# backend/app/agents/agent_store.py — DEPRECATED → app.agent.store
from app.agent.store import *  # noqa: F401, F403
```

---

## 6. `app/agents/factory_defaults.py` → `app/agent/factory_defaults.py`

```powershell
Copy-Item "backend/app/agents/factory_defaults.py" "backend/app/agent/factory_defaults.py"
```

**Imports prüfen:**  
`factory_defaults.py` enthält die 15 eingebauten Agenten-Definitionen.  
Muss `record.py` und `adapter.py` kennen.

**Stub:**
```python
# backend/app/agents/factory_defaults.py — DEPRECATED → app.agent.factory_defaults
from app.agent.factory_defaults import *  # noqa: F401, F403
```

---

## 7. `app/agents/agents_manifest.json` → `app/agent/manifest.json`

```powershell
Copy-Item "backend/app/agents/agents_manifest.json" "backend/app/agent/manifest.json"
```

**Dann prüfen ob factory_defaults.py oder store.py auf diesen Pfad referenziert:**
```powershell
Select-String -Path "backend/app/agent/*.py" -Pattern "agents_manifest|manifest\.json"
```

Falls gefunden → Pfad anpassen auf `Path(__file__).parent / "manifest.json"` (relativ zum `agent/`-Verzeichnis).

---

## 8. `services/agent_resolution.py` → `agent/resolution.py`

```powershell
Copy-Item "backend/app/services/agent_resolution.py" "backend/app/agent/resolution.py"
```

**Imports prüfen:** Darf `agent/store.py`, `agent/record.py`, `shared/` nutzen.

**Stub:**
```python
# backend/app/services/agent_resolution.py — DEPRECATED → app.agent.resolution
from app.agent.resolution import *  # noqa: F401, F403
```

---

## 9. `app/agent_runner.py` → `app/agent/runner.py` (~1667 Zeilen)

```powershell
Copy-Item "backend/app/agent_runner.py" "backend/app/agent/runner.py"
```

**Imports in `runner.py` prüfen — SEHR VIELE IMPORTS ERWARTET:**
```powershell
Select-String -Path "backend/app/agent/runner.py" -Pattern "^from app\." | Select-Object LineNumber, Line
```

**Systematische Import-Rewrites:**

| Alt | Neu |
|-----|-----|
| `from app.agent_runner_types import` | `from app.agent.runner_types import` |
| `from app.tools import AgentTooling` | `from app.tools.implementations import AgentTooling` |
| `from app.tool_catalog import` | `from app.tools.catalog import` |
| `from app.services.tool_execution_manager import` | `from app.tools.execution.manager import` |
| `from app.services.tool_call_gatekeeper import` | `from app.tools.execution.gatekeeper import` |
| `from app.services.tool_loop_detector import` | `from app.tools.execution.loop_detector import` |
| `from app.services.action_parser import` | `from app.reasoning.action_parser import` |
| `from app.services.reply_shaper import` | `from app.reasoning.reply_shaper import` |
| `from app.services.intent_detector import` | `from app.reasoning.intent_detector import` |
| `from app.services.output_parsers import` | `from app.reasoning.output_parsers import` |
| `from app.services.reflection_service import` | `from app.quality.reflection_service import` |
| `from app.memory import MemoryStore` | `from app.memory.session_memory import MemoryStore` |
| `from app.services.long_term_memory import` | `from app.memory.long_term import` |
| `from app.errors import` | `from app.shared.errors import` oder `from app.policy.errors import` |
| `from app.llm_client import` | `from app.llm.client import` |
| `from app.contracts.agent_contract import` | `from app.contracts.agent_contract import` (unverändert) |
| `from app.policy_store import` | `from app.policy.store import` |
| `from app.services.circuit_breaker import` | `from app.policy.circuit_breaker import` |

**Stub in original:**
```python
# backend/app/agent_runner.py — DEPRECATED → app.agent.runner
from app.agent.runner import AgentRunner  # noqa: F401
```

---

## 10. `app/agent.py` → `app/agent/head_agent.py` (~1769 Zeilen)

Dies ist die größte und kritischste Datei.

```powershell
Copy-Item "backend/app/agent.py" "backend/app/agent/head_agent.py"
```

**Imports prüfen — VOLLSTÄNDIGE LISTE:**
```powershell
Select-String -Path "backend/app/agent/head_agent.py" -Pattern "^from app\." | Select-Object LineNumber, Line
Select-String -Path "backend/app/agent/head_agent.py" -Pattern "^import " | Select-Object LineNumber, Line
```

**Systematische Import-Rewrites (zusätzlich zu denen aus Schritt 9):**

| Alt | Neu |
|-----|-----|
| `from app.agent_runner import AgentRunner` | `from app.agent.runner import AgentRunner` |
| `from app.agents.agent_store import` | `from app.agent.store import` |
| `from app.agents.factory_defaults import` | `from app.agent.factory_defaults import` |
| `from app.agents.unified_adapter import` | `from app.agent.adapter import` |
| `from app.services.agent_resolution import` | `from app.agent.resolution import` |
| `from app.models import` | `from app.transport.ws_models import` (Phase 14 — stub needed) |
| `from app.control_models import` | `from app.shared.control_models import` |
| `from app.app_state import` | `from app.transport.app_state import` (Phase 14 — stub needed) |

> **ACHTUNG bei `app_state` und `models` Importen:** Diese Dateien wurden noch nicht migriert (kommen in Phase 14). Nutze `TYPE_CHECKING` guards:
> ```python
> from typing import TYPE_CHECKING
> if TYPE_CHECKING:
>     from app.transport.app_state import ControlPlaneState
> ```

**Stub in original:**
```python
# backend/app/agent.py — DEPRECATED → app.agent.head_agent
from app.agent.head_agent import HeadAgent  # noqa: F401
```

---

## 11. `agents/__init__.py` als Stub

```python
# backend/app/agents/__init__.py
# DEPRECATED: agent code moved to app.agent.*
# Stubs for backwards compatibility:
from app.agent.store import UnifiedAgentStore
from app.agent.record import UnifiedAgentRecord
from app.agent.adapter import UnifiedAgentAdapter
from app.agent.factory_defaults import CODER_AGENT_ID, PRIMARY_AGENT_ID, REVIEW_AGENT_ID
```

---

## 12. `agent/__init__.py` befüllen

```python
# backend/app/agent/__init__.py
"""
Agent domain — core agent execution.
Imports allowed from: llm/, tools/, memory/, reasoning/, quality/, policy/, contracts/, shared/, config/
"""
from app.agent.head_agent import HeadAgent
from app.agent.runner import AgentRunner
from app.agent.runner_types import *  # RunnerContext etc.
from app.agent.store import UnifiedAgentStore
from app.agent.record import UnifiedAgentRecord
from app.agent.adapter import UnifiedAgentAdapter
from app.agent.factory_defaults import CODER_AGENT_ID, PRIMARY_AGENT_ID, REVIEW_AGENT_ID
from app.agent.resolution import AgentResolution

__all__ = [
    "HeadAgent", "AgentRunner", "UnifiedAgentStore", "UnifiedAgentRecord",
    "UnifiedAgentAdapter", "AgentResolution",
    "CODER_AGENT_ID", "PRIMARY_AGENT_ID", "REVIEW_AGENT_ID",
]
```

---

## 13. Verifikation

```powershell
$checks = @(
    "backend/app/agent/head_agent.py",
    "backend/app/agent/runner.py",
    "backend/app/agent/runner_types.py",
    "backend/app/agent/store.py",
    "backend/app/agent/record.py",
    "backend/app/agent/adapter.py",
    "backend/app/agent/factory_defaults.py",
    "backend/app/agent/manifest.json",
    "backend/app/agent/resolution.py"
)
foreach ($f in $checks) {
    if (Test-Path $f) { Write-Host "OK: $f" } else { Write-Host "MISSING: $f" }
}

cd backend
# Import-Test (kein vollständiger Start, nur Import-Check)
python -c "
import sys
sys.dont_write_bytecode = True  # kein pyc spam
from app.agent.runner_types import *
from app.agent.record import UnifiedAgentRecord
from app.agent.factory_defaults import PRIMARY_AGENT_ID
print('agent/ types OK:', PRIMARY_AGENT_ID)
"

# Stubs prüfen
python -c "
from app.agent import HeadAgent  # via __init__
from app.agents.agent_store import UnifiedAgentStore  # via stub
print('Stubs OK')
"
```

---

## 14. Commit

```bash
git add -A
git commit -m "refactor(ddd): migrate agent/ core domain (HeadAgent, AgentRunner, Store) — Phase 12"
```

---

## Status-Checkliste

- [ ] `agent/runner_types.py` erstellt, Stub in Original
- [ ] `agent/record.py` erstellt, Stub in agents/
- [ ] `agent/adapter.py` erstellt, Imports gefixt, Stub in agents/
- [ ] `agent/store.py` erstellt, interne Imports gefixt, Stub in agents/
- [ ] `agent/factory_defaults.py` erstellt, Stub in agents/
- [ ] `agent/manifest.json` kopiert, Pfadreferenzen gefixt
- [ ] `agent/resolution.py` erstellt, Stub in services/
- [ ] `agent/runner.py` erstellt (1667 Zeilen!), ALLE Imports systematisch gefixt, Stub
- [ ] `agent/head_agent.py` erstellt (1769 Zeilen!), ALLE Imports systematisch gefixt, TYPE_CHECKING für noch nicht migrierte Module, Stub
- [ ] `agents/__init__.py` als Stub für Abwärtskompatibilität
- [ ] `agent/__init__.py` befüllt
- [ ] Smoke-Import-Test erfolgreich
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_13_ORCHESTRATION.md](./PHASE_13_ORCHESTRATION.md)
