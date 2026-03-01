# Backend Refactoring Plan (Constraint-First, Model-Agnostic)

## Implementierungsstatus (2026-03-01)

- ✅ Phase 0: Baseline-Tests stabilisiert
- ✅ Phase 1: Contract-Layer + Head-Agent-Adapter eingeführt
- ✅ Phase 2: Externer State Store + Snapshots integriert
- ✅ Phase 3: Deterministischer Pipeline-Runner + Orchestrator-API verdrahtet
- ✅ Phase 4: Context-Reducer + harte Step-Budgets aktiviert
- ✅ Phase 5: Capability Registry + zentraler Model Router mit Fallback
- ✅ Phase 6: Split in Planner/ToolSelector/Synthesizer Contract-Agents
- ✅ Phase 7: Legacy-Pfade bereinigt (u. a. alter `_create_plan`-Pfad entfernt)

## 1) Zielbild

Das bestehende Head-Agent-Verhalten bleibt funktional erhalten, wird aber in eine Orchestrierungs-Architektur eingebettet, die:
- strikt über Agent-Contracts arbeitet,
- Zustand ausschließlich extern verwaltet,
- Modelle über Capability-Profile routet,
- lokal (7B/klein) und cloud (70B+/groß) ohne Code-Änderungen am Agent-Flow unterstützt.

## 2) Kurzdiagnose des Ist-Zustands

Aktuell sind zentrale Verantwortlichkeiten eng gekoppelt:
- `app/agent.py`: Planung, Tool-Selektion, Tool-Ausführung, Finalisierung, Memory-Zugriff, Lifecycle-Events.
- `app/main.py`: API/WebSocket, Request-Flow, Runtime-Switching, Agent-Lifecycle.
- `app/memory.py`: sessionbasierte Persistenz, aber als Prompt-Kontext direkt an den Agent gebunden.
- `app/runtime_manager.py`: Runtime und Modellumschaltung, jedoch ohne explizite Capability-Routing-Entscheidung.

Das ist funktional, aber für Multi-Agent- oder Multi-Model-Skalierung zu monolithisch.

## 3) Zielarchitektur (ohne Big-Bang)

### 3.1 Schichten

1. **Transport Layer**
   - FastAPI/WS bleibt Entry-Point.
   - Verantwortlich nur für Validierung, Auth, Event-Streaming, Request/Response-Envelopes.

2. **Orchestration Layer (neu)**
   - Deterministischer Flow-Runner (lineare Pipelines zuerst).
   - Verwaltet Task Graph, Steps, Retries, Status-Transitionen.
   - Ruft Agents nur über Contracts auf.

3. **Agent Layer (neu strukturiert)**
   - Jeder Agent implementiert expliziten Contract (`role`, `input_schema`, `output_schema`, `constraints`).
   - Kein direkter Zugriff auf globalen Zustand.

4. **State Layer (neu)**
   - Externer State Store (JSON-Dateien je Session/Run).
   - Task Graph + Summary Snapshots + Context Reducer.
   - Single Source of Truth.

5. **Model Routing Layer (neu)**
   - Capability Registry (Kontextlimit, reasoning depth, reflection passes, combine steps, temperature).
   - Router wählt Modell/Policy pro Step anhand Contract + Budget.

6. **Infrastructure Layer**
   - LLM-Client, Tooling, Runtime-Gateway, Observability/Tracing.

## 4) Zielstruktur im Backend

Vorgeschlagene Modulstruktur (schrittweise einführen):

- `app/contracts/`
  - `agent_contract.py` (Basis-Contract, Constraint-Objekte)
  - `schemas.py` (Pydantic-Schemas pro Agent In/Out)
- `app/orchestrator/`
  - `pipeline_runner.py` (deterministischer Step-Runner)
  - `step_types.py` (Plan, ToolSelect, ToolExec, Synthesize)
  - `events.py` (standardisierte Lifecycle-Events)
- `app/state/`
  - `state_store.py` (persistenter JSON-Store)
  - `task_graph.py` (pending/active/completed)
  - `context_reducer.py` (tokenbudget-basierte Selektion)
  - `snapshots.py` (rehydrierbare Summary-Snapshots)
- `app/model_routing/`
  - `capability_profile.py`
  - `model_registry.py`
  - `router.py`
- `app/agents/`
  - `head_agent_adapter.py` (wrappt bestehende `HeadCodingAgent`-Logik)
  - später: `planner_agent.py`, `tool_selector_agent.py`, `synthesizer_agent.py`
- `app/interfaces/`
  - `request_context.py` (request/session/run Metadaten)
  - `orchestrator_api.py` (stabile Einstiegsschnittstelle für `main.py`)

## 5) Migrationsplan in Phasen

## Phase 0 — Baseline stabilisieren

- Bestehende Tests als Guardrail behalten (`tests/test_backend_e2e.py`, `tests/test_tool_selection_offline_eval.py`).
- Zusätzlich Snapshot-Tests für WS-Lifecycle-Reihenfolge ergänzen (nur minimale Erweiterung).
- Ziel: Refactoring ohne Verhaltensdrift.

**Definition of Done**
- Alle bestehenden Tests grün.
- Baseline-Lifecycle dokumentiert.

## Phase 1 — Contracts einführen (ohne Behavior-Change)

- Agent-Contract-Basisklassen und Pydantic-Schemas anlegen.
- Bestehenden `HeadCodingAgent` über `head_agent_adapter` in Contract-Form verfügbar machen.
- Bestehende Prompts/Tooling unverändert lassen.

**Definition of Done**
- `main.py` ruft Agent nicht mehr direkt an, sondern über Contract-Adapter.
- Kein API/WS-Breaking-Change.

## Phase 2 — External State Manager aufbauen

- Neuen `state_store` einführen (JSON pro session/run).
- `task_graph` und `snapshots` implementieren.
- `memory.py` nicht sofort entfernen, sondern als Legacy-Quelle nur lesend in den neuen Store migrieren.

**Definition of Done**
- Run-Zustände sind außerhalb des Agents persistiert.
- Agent erhält nur State-Slices, nicht den Vollzustand.

## Phase 3 — Deterministischen Pipeline-Runner einführen

- Orchestrator-Runner mit festen Steps: `plan -> tool_select -> tool_execute -> synthesize`.
- Retries/Timeouts aus Agent herauslösen und in Runner zentralisieren.
- Lifecycle-Events aus Runner standardisieren.

**Definition of Done**
- `app/main.py` delegiert an `orchestrator_api`.
- `HeadCodingAgent` enthält keine Flow-Koordination mehr.

## Phase 4 — Context Reducer + Budget Enforcement

- `context_reducer` implementieren mit hard token budget pro Modellprofil.
- Priorisierung: aktuelle Task > letzte Tool-Outputs > kompakte Historie > Snapshot.
- Bei Budget-Überschreitung deterministische Kürzung.

**Definition of Done**
- Jeder Agent-Step bekommt explizit reduzierten Kontext.
- Keine ungefilterte Memory-Einspeisung in Prompts.

## Phase 5 — Capability Profiles + Model Router

- Profile in JSON/YAML registrieren (lokal + cloud Modelle).
- Router entscheidet pro Step anhand Contract-Constraints.
- Fallback-Kette definieren (z. B. local-small -> local-large -> api-large).

**Definition of Done**
- Modellwechsel erfolgt policy-basiert, nicht per harter Verzweigung im Agent-Code.
- Gleicher Workflow lokal und cloud (nur Konfigurationsänderung).

## Phase 6 — Multi-Agent-Separation (optional nach Stabilität)

- Planner/ToolSelector/Synthesizer als getrennte Contract-Agents extrahieren.
- Orchestrator bleibt linear-deterministisch (kein emergentes Agent-Chaos).

**Definition of Done**
- Kein Agent teilt implizites Wissen.
- Alle Agent-Outputs strikt schema-validiert.

## Phase 7 — Clean-up und Legacy-Abbau

- Alte direkte Kopplungen entfernen (`main.py` -> `HeadCodingAgent`, direkte Memory-Calls im Agent).
- Dokumentation und Betriebsleitfaden finalisieren.

**Definition of Done**
- Monolithische Flow-Logik entfernt.
- Architektur entspricht den Core Principles aus `instructions.md`.

## 6) Konkrete Contract-Vorlage

Jeder Agent definiert:
- `role`
- `input_schema`
- `output_schema`
- `constraints`:
  - `max_context`
  - `temperature`
  - `reasoning_depth`
  - `reflection_passes`
  - `combine_steps`

Zusätzlich:
- Strikte JSON-Outputs (kein freier Text im Inter-Agent-Protokoll).
- Harte Validierung vor/nach jedem Step.

## 7) Risiken und Gegenmaßnahmen

- **Risiko: Verhaltensdrift durch Refactoring**
  - Maßnahme: Phase-0 Baseline + golden-path E2E-Tests.
- **Risiko: Zu früher Multi-Agent-Split erhöht Komplexität**
  - Maßnahme: Erst Runner + External State stabilisieren.
- **Risiko: Lokale Modelle überlaufen Kontext**
  - Maßnahme: Context Reducer + Step-spezifische Budgets verpflichtend.
- **Risiko: Modellabhängige Prompt-Workarounds wachsen**
  - Maßnahme: Capability Router + Contract-gebundene Policies statt Prompt-Hacks.

## 8) Rollout-Empfehlung

- In vertikalen Increments deployen (Phase für Phase).
- Nach jeder Phase:
  1. Tests,
  2. Smoke über `/api/test/agent` und `/ws/agent`,
  3. kurze Lastprobe (mehrere parallele WS-Sessions),
  4. erst dann nächste Phase.

So bleibt das System jederzeit lauffähig, lokal entwickelbar und cloudskalierbar ohne erneuten Architekturbruch.
