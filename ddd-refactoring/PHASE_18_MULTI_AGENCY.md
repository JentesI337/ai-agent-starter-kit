# PHASE 18 — `multi_agency/` — Import-Bereinigung & DDD-Einordnung

> **Session-Ziel:** Das `multi_agency/`-Verzeichnis DDD-konform machen. Die 8 existierenden Dateien bleiben erhalten, aber ihre Imports werden auf die neuen DDD-Pfade aktualisiert. Ausserdem wird `__init__.py` sauber dokumentiert und die Domain-Grenzen werden protokolliert.
>
> **Voraussetzung:** PHASE_15 (transport/routers/), PHASE_12 (agent/), PHASE_13 (orchestration/) abgeschlossen
> **Folge-Phase:** PHASE_19_WORKFLOWS_SKILLS.md
> **Geschätzter Aufwand:** ~2–3 Stunden
> **Betroffene Dateien:** `backend/app/multi_agency/` (8 Dateien)

---

## Ist-Zustand

```
backend/app/multi_agency/
├── __init__.py
├── agent_identity.py
├── agent_message_bus.py
├── blackboard.py
├── confidence_router.py
├── consensus.py
├── coordination_bridge.py
├── parallel_executor.py
└── supervisor.py
```

---

## Domain-Grenzen für `multi_agency/`

**Erlaubte Imports (von außen nach innen):**
```
multi_agency/ DARF importieren:
  ✅ app.shared.*          — Utilities, EventBus, IDGen
  ✅ app.contracts.*       — Domain-Contracts (AgentContract etc.)
  ✅ app.agent.*           — HeadAgent, Runner (nur via Contracts!)
  ✅ app.orchestration.*   — Pipeline, Events
  ✅ app.config.*          — Settings

multi_agency/ DARF NICHT importieren:
  ❌ app.transport.*       — Keine HTTP/WS-Layer!
  ❌ app.tools.*           — Tools sind Agenten-intern
  ❌ app.services.*        — Alter Monolith — nicht mehr referenzieren
  ❌ app.routers.*         — Transport-Layer
  ❌ app.handlers.*        — Transport-Layer
```

---

## Schritt 1: Import-Audit für jede Datei

```powershell
cd backend

# Alle aktuellen Imports in multi_agency/ auflisten
Select-String -Path "app/multi_agency/*.py" -Pattern "^from|^import" | 
    Select-Object Filename, LineNumber, Line | 
    Format-Table -AutoSize
```

Erwartetes Ausgaben-Template (tatsächliche Werte werden beim Audit sichtbar):

```
agent_identity.py     → from dataclasses import ...
                       → from app.contracts.agent_contract import AgentContract
agent_message_bus.py  → from app.shared.events import EventBus
                       → from app.contracts... import ...
blackboard.py         → from app.shared... import ...
confidence_router.py  → from app.agent... import ...
                       → from app.contracts... import ...
consensus.py          → from app.multi_agency.blackboard import Blackboard
coordination_bridge.py→ from app.orchestration... import ...
parallel_executor.py  → from app.agent.runner import AgentRunner
supervisor.py         → from app.multi_agency... import ...
```

---

## Schritt 2: Import-Reparaturen

### `agent_identity.py`
Prüfen ob es `from app.agents.` (alt) oder `from app.agent.` (neu) importiert.

**Alt → Neu:**
```python
# ALT
from app.agents.unified_agent_record import UnifiedAgentRecord
# NEU
from app.agent.agent_record import AgentRecord

# ALT
from app.services.agent_service import ...
# NEU
from app.agent.head_agent import HeadAgent
```

### `agent_message_bus.py`
Prüfen ob es `from app.services.` importiert.

**Typische Reparatur:**
```python
# ALT
from app.services.event_service import EventBus
# NEU
from app.shared.events import EventBus
```

### `blackboard.py`
Prüfen ob State-Imports korrekt auf `app.state` zeigen:

```python
# ALT
from app.services.state_service import StateStore
# NEU
from app.state.state_store import StateStore
```

### `confidence_router.py`
LLM-Routing wird jetzt über `app.llm.routing`:

```python
# ALT
from app.model_routing.router import ModelRouter
# NEU
from app.llm.routing.router import ModelRouter
```

### `consensus.py`
Prüfen auf ältere Imports aus `app.services.`:

```python
# ALT
from app.services.consensus_service import ...
# NEU — alles aus blackboard/coordination_bridge
from app.multi_agency.blackboard import Blackboard
```

### `coordination_bridge.py`
Orchestration-Imports auf neue Pfade:

```python
# ALT
from app.orchestrator.pipeline_runner import PipelineRunner
# NEU
from app.orchestration.pipeline_runner import PipelineRunner

# ALT
from app.interfaces.orchestrator_api import OrchestratorAPI
# NEU
from app.contracts.orchestrator_contract import OrchestratorContract
```

### `parallel_executor.py`
Agent-Runner-Import:

```python
# ALT
from app.agent_runner import AgentRunner
# NEU
from app.agent.runner import AgentRunner
```

### `supervisor.py`
Alle internen multi_agency Imports + contracts:

```python
# ALT
from app.services.multi_agency_service import ...
# NEU
from app.multi_agency.coordination_bridge import CoordinationBridge
from app.multi_agency.consensus import ConsensusCoordinator
```

---

## Schritt 3: `__init__.py` aktualisieren

```python
# backend/app/multi_agency/__init__.py
"""
multi_agency — Multi-Agent Coordination Domain.

Handles coordination between multiple agents:
  - AgentIdentity:        Identity and capability declaration per agent
  - AgentMessageBus:      Message passing between agents
  - Blackboard:           Shared knowledge space for agent coordination
  - ConfidenceRouter:     Routes tasks to most-capable agent
  - ConsensusCoordinator: Quorum-based decision making
  - CoordinationBridge:   Bridge to orchestration pipeline
  - ParallelExecutor:     Runs multiple agents in parallel
  - Supervisor:           Orchestrates the multi-agent workflow

Allowed imports FROM:
  shared, contracts, agent (via contracts only), orchestration, config

NOT allowed:
  transport, tools, services (deprecated)
"""

from app.multi_agency.agent_identity import AgentIdentity
from app.multi_agency.agent_message_bus import AgentMessageBus
from app.multi_agency.blackboard import Blackboard
from app.multi_agency.confidence_router import ConfidenceRouter
from app.multi_agency.consensus import ConsensusCoordinator
from app.multi_agency.coordination_bridge import CoordinationBridge
from app.multi_agency.parallel_executor import ParallelExecutor
from app.multi_agency.supervisor import MultiAgentSupervisor

__all__ = [
    "AgentIdentity",
    "AgentMessageBus",
    "Blackboard",
    "ConfidenceRouter",
    "ConsensusCoordinator",
    "CoordinationBridge",
    "ParallelExecutor",
    "MultiAgentSupervisor",
]
```

---

## Schritt 4: Circular-Import-Prüfung

```powershell
cd backend

python -c "
import sys
sys.path.insert(0, '.')
from app.multi_agency import (
    AgentIdentity,
    AgentMessageBus,
    Blackboard,
    ConfidenceRouter,
    ConsensusCoordinator,
    CoordinationBridge,
    ParallelExecutor,
    MultiAgentSupervisor,
)
print('All multi_agency imports OK')
"
```

Falls Circular Import Fehler: Mit `__init__.py` als letzte Ebene arbeiten, nicht direkt innerhalb der Module.

---

## Verifikation

```powershell
cd backend

# 1. Alle Imports valide
python -c "from app.multi_agency import MultiAgentSupervisor; print('MultiAgentSupervisor OK')"

# 2. Keine alten Imports mehr
Select-String -Path "app/multi_agency/*.py" -Pattern "from app\.services\.|from app\.orchestrator\.|from app\.model_routing\.|from app\.agents\." |
    Select-Object Filename, LineNumber, Line

# 3. Tests
python -m pytest tests/ -k "multi_agency or supervisor or consensus" -q --tb=short 2>&1 | Select-Object -First 40
```

---

## Commit

```bash
git add -A
git commit -m "refactor(ddd): update multi_agency imports to DDD paths — Phase 18"
```

---

## Status-Checkliste

- [ ] Import-Audit für alle 8 Dateien durchgeführt
- [ ] `agent_identity.py` imports aktualisiert
- [ ] `agent_message_bus.py` imports aktualisiert
- [ ] `blackboard.py` imports aktualisiert
- [ ] `confidence_router.py` imports aktualisiert
- [ ] `consensus.py` imports aktualisiert
- [ ] `coordination_bridge.py` imports aktualisiert
- [ ] `parallel_executor.py` imports aktualisiert
- [ ] `supervisor.py` imports aktualisiert
- [ ] `__init__.py` clean public API
- [ ] Kein Import mehr aus `app.services.*`, `app.orchestrator.*`, `app.model_routing.*`, `app.agents.*`
- [ ] Circular-Import-Test bestanden
- [ ] Tests laufen durch
- [ ] Commit gemacht

---

> **Nächste Session:** [PHASE_19_WORKFLOWS_SKILLS.md](./PHASE_19_WORKFLOWS_SKILLS.md)
