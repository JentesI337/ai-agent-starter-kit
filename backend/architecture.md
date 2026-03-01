# Backend Architecture

Stand: 2026-03-01  
Scope: Nur Backend (`backend/`), Frontend ist bewusst nicht Teil dieses Dokuments.

## 1. Zielbild

## Was es ist

Dieses Backend ist ein Agent-Framework-Server mit einem Head-Agent als zentralem Orchestrator.

- Verarbeitet einfache und komplexe Prompts.
- Orchestriert Agentenläufe deterministisch über Pipeline-Schritte.
- Unterstützt Workflows/Custom Agents (anlegen, ausführen, monitoren, nachvollziehen).
- Bietet eine Control-Plane (REST) und eine interaktive Laufzeit (WebSocket).
- Läuft mit lokalen und API-basierten Modellen.

## Was es nicht ist

- Kein autonom „lebender“ Agent-Prozess, der ohne Anfrage selbstständig aktiv wird.
- Kein autonomes Langzeitgedächtnis mit eigenständigem Handlungsdrang.
- Kein Frontend-System (nur Backend-Verantwortung).

## 2. Architektur auf hoher Ebene

Das Backend ist eine FastAPI-Anwendung mit klaren Verantwortungsblöcken:

1) Transport/API
- REST-Endpunkte über Router-Builder in `app.routers/*` (inkl. Control-Plane, Agents, Runtime-Debug, Subruns), eingebunden in `app.main`.
- WebSocket-Endpunkt `/ws/agent` mit ausgelagerter Handler-Logik in `app.ws_handler`.

2) Agenten- und Orchestrierungs-Schicht
- `HeadAgent` (`app.agent`) führt Pipeline aus: Plan → Tool Selection/Execution → Synthese.
- `OrchestratorApi` (`app.interfaces.orchestrator_api`) kapselt Session-Lanes und PipelineRunner.
- `SubrunLane` (`app.orchestrator.subrun_lane`) verwaltet Child-Runs (Depth, Visibility, Kill, Status).

3) Laufzeit- und Modell-Schicht
- `RuntimeManager` steuert Runtime-Wechsel (`local`/`api`), Modellverfügbarkeit und Persistenz des aktiven Runtime-Zustands.
- Optionaler API-Auth-Guard über `API_AUTH_REQUIRED` + `API_AUTH_TOKEN`/`OLLAMA_API_KEY`.
- `ModelRouter` + `ModelRegistry` wählen Primär-/Fallback-Modelle auf Basis von Profilen.

4) Persistenz- und Zustands-Schicht
- `StateStore`: Run-States + Event-Historie + Summary-Snapshots auf Dateisystem.
- `MemoryStore`: Session-Kontext als JSONL, begrenzt pro Session.
- `CustomAgentStore`: Workflow-/Agent-Definitionen als JSON-Dateien.
- Idempotency-Registries bleiben In-Memory, sind aber per TTL + Max-Entries begrenzt.

5) Policy- und Guardrail-Schicht
- Zentrale Tool-Policy-Auflösung über `app.services.tool_policy_service`.
- Guardrails auf Input, Tool-Nutzung, Subrun-Depth, Idempotency-Konflikte.

## 3. Laufzeitmodell und Lifecycle

Das App-Lifecycle-Design ist auf kontrollierten Start/Shutdown ausgelegt:

- FastAPI-Lifespan führt Startup-Aufgaben aus (`_log_startup_paths`, optionales Cleanup von Memory/State).
- Runtime-Komponenten werden lazy über `app.app_state` aufgebaut (`LazyRuntimeRegistry`, Proxies).
- Beim Shutdown werden aktive Hintergrund-Run-Tasks sauber abgebrochen.

Wichtige Folge:
- Weniger Import-Time-Side-Effects.
- Bessere Testbarkeit und reproduzierbares Boot-Verhalten.

## 4. Kernkomponenten im Detail

### 4.1 `app.main`

Zentrale API-Wiring-Datei mit:

- FastAPI-App, CORS, Lifespan.
- DI/Wiring für Runtime-Komponenten über `app.app_state`.
- Handler-Funktionen für API-Operationen und Einbindung der Router-Builder.
- Einbindung der modularen Router:
	- `build_control_runs_router`
	- `build_control_sessions_router`
	- `build_control_workflows_router`
	- `build_control_tools_router`
	- `build_agents_router`
	- `build_runtime_debug_router`
	- `build_subruns_router`
- Registrierung des WebSocket-Endpunkts, Delegation an `handle_ws_agent`.

### 4.2 `app.ws_handler`

Enthält den kompletten `/ws/agent`-Nachrichtenfluss.

Verantwortungen:
- Session/Sequencing (`seq`-Envelope).
- Routing des gewünschten Agenten (inkl. Head-Agent-Delegation auf Coder/Review).
- Policy-Auflösung und Lifecycle-Event-Emission.
- Runtime-Switch-Requests.
- Subrun-Spawn + Fehler-Mapping (`GuardrailViolation`, Tool/LLM/Runtime-Fehler).
- Dependency-Schnittstelle ist über typed Protocols modelliert (`WsHandlerDependencies` ohne `Any`-Bag für Kernabhängigkeiten).

### 4.3 `app.agent` (`HeadAgent`)

Kern-Agent mit deterministischem Ablauf:

- Guardrails + Tool-Policy-Prüfung.
- Memory-Update + Context-Reduktion.
- Planning (`PlannerAgent`).
- Tool-Selection/Tool-Execution (`ToolSelectorAgent`, `ToolStepExecutor`).
- Synthese (`SynthesizerAgent`).
- Lifecycle- und Telemetrie-Events über den gesamten Run.

Aktueller Refactor-Stand:
- Konstruktor unterstützt optionale Dependency Injection (`LlmClient`, `MemoryStore`, `AgentTooling`, `ModelRegistry`, `ContextReducer`).
- `configure_runtime()` re-konfiguriert Sub-Agents in-place statt vollständigem Rebuild.
- Native Delegations-Fähigkeit über Tool `spawn_subrun` (mit Guardrails/Policy) zur direkten Child-Run-Erzeugung aus dem Agentenlauf.

### 4.4 `app.interfaces.orchestrator_api` + `app.orchestrator.pipeline_runner`

- `OrchestratorApi` serialisiert/koordiniert pro Session über `SessionLaneManager`.
- `OrchestratorApi` löst Tool-Policy kontextsensitiv (provider/model/agent/depth/request) auf und emittiert Lifecycle-Event `agent_depth_policy_applied`.
- `PipelineRunner` setzt Task-Status je Pipeline-Schritt, routed Modelle, führt Fallbacks aus.

### 4.5 `app.orchestrator.subrun_lane`

Verwaltet Child-Execution-Lanes inklusive:

- Max-Concurrency.
- Max-Spawn-Depth.
- Max-Children-per-Parent.
- Sichtbarkeit (`self`/`tree`/`agent`/`all`).
- Subrun-Status- und Announce-Events.
- Kill/Kill-All-Operationen.

### 4.6 `app.runtime_manager`

- Persistiert aktiven Runtime-Status.
- Schaltet zwischen `local` und `api` um (mit Retry/Rollback).
- Startet lokale Gateway-Prozesse bei Bedarf.
- Validiert/verfügbar macht Modelle (`ensure_model_ready`, API-Modelauflösung).
- Erzwingt bei Bedarf Authentifizierung für API-Runtime (`ensure_api_runtime_authenticated`).

### 4.7 Persistenz (`app.state.state_store`, `app.memory`, `app.custom_agents`)

- `StateStore`: pro Run JSON + Summary-Snapshot, Thread-Lock, atomarer Replace mit Retry.
- `StateStore.list_runs()` nutzt einen lazy In-Memory-mtime-Index (statt Vollsortierung jedes Mal über alle Dateien).
- Persistenz-Transform: optionale Secret-Redaction + String-Truncation.
- `MemoryStore`: JSONL-basiertes Session-Memory mit Max-Items.
- `CustomAgentStore`: CRUD für benutzerdefinierte Agenten/Workflows als Dateien.

### 4.8 Konfiguration (`app.config`)

- Prompt-Fallbacks werden zentral über `_resolve_prompt(...)` aufgelöst.
- Aufgelöste Prompt-Werte sind über `resolved_prompt_settings(...)` verfügbar.
- Debug-Endpoint für effective Prompt-Werte: `GET /api/debug/prompts/resolved`.

## 5. API-Oberfläche (Backend)

## WebSocket

- `GET ws /ws/agent`

Inbound-Nachrichtentypen:
- `user_message`
- `runtime_switch_request`
- `subrun_spawn`

Outbound-Eventklassen (Auszug):
- `status`, `final`, `error`, `lifecycle`
- `runtime_switch_progress`, `runtime_switch_done`, `runtime_switch_error`
- `subrun_status`, `subrun_announce`

## REST (Core)

- `GET /api/runtime/status`
- `GET /api/debug/prompts/resolved`
- `GET /api/monitoring/schema`
- `GET /api/test/ping`
- `POST /api/test/agent`
- `POST /api/runs/start`
- `GET /api/runs/{run_id}/wait`
- `GET /api/agents`
- `GET /api/presets`
- `GET /api/custom-agents`
- `POST /api/custom-agents`
- `DELETE /api/custom-agents/{agent_id}`
- `GET /api/subruns`
- `GET /api/subruns/{run_id}`
- `GET /api/subruns/{run_id}/log`
- `POST /api/subruns/{run_id}/kill`
- `POST /api/subruns/kill-all`

## Control-Plane (modularisiert)

Gruppen:
- Runs: `/api/control/run.start`, `/api/control/run.wait`, `/api/control/agent.run`, `/api/control/agent.wait`, `/api/control/runs.*`
- Sessions: `/api/control/sessions.*`
- Workflows: `/api/control/workflows.*`
- Tools/Policy: `/api/control/tools.catalog`, `/api/control/tools.profile`, `/api/control/tools.policy.matrix`, `/api/control/tools.policy.preview`

Idempotency:
- Relevante write-/execute-Endpoints unterstützen `Idempotency-Key` (Header + Payload-Konventionen).
- Registries verwenden TTL- und Capacity-Pruning (`IDEMPOTENCY_REGISTRY_TTL_SECONDS`, `IDEMPOTENCY_REGISTRY_MAX_ENTRIES`).

## 6. Policy-, Sicherheits- und Guardrail-Modell

Tool-Policies werden schichtweise zusammengeführt:

Reihenfolge:
1. global (Settings)
2. profile
3. preset
4. provider
5. model
6. agent_depth
7. request

Praktische Wirkung von `agent_depth`:
- Nicht-orchestrierende Agenten bzw. tiefe Delegationsstufen (`depth >= 2`) erhalten `spawn_subrun` effektiv per `deny` entzogen (worker-only Verhalten).
- Top-Level Head-Agent-Runs (`depth = 0`) behalten Delegationsfähigkeit gemäß übriger Policy-Layer.

Regel bei Konflikten:
- `deny` überschreibt `allow`.

Weitere Schutzmechanismen:
- Input-/Model-/Session-Guardrails in Agent- und API-Flows.
- Tool-Allowlist für Kommandoausführung.
- Subrun-Depth- und Child-Limits.
- Secret-Redaction in persisted state payloads.
- API-Runtime-Auth-Guard (konfigurierbar, expliziter Fehlerpfad bei fehlender Auth im API-Mode).

## 7. Datenhaltung und Artefakte

Standardpfade (konfigurierbar via Env):

- Memory: `MEMORY_PERSIST_DIR` (JSONL je Session)
- Run-State: `ORCHESTRATOR_STATE_DIR/runs/*.json`
- Snapshots: `ORCHESTRATOR_STATE_DIR/snapshots/*.summary.json`
- Runtime-Status: `RUNTIME_STATE_FILE`
- Custom Agents: `CUSTOM_AGENTS_DIR/*.json`

Hinweis:
- Datenhaltung bleibt dateibasiert; `list_runs(limit=...)` ist durch In-Memory-Index optimiert, aber nicht DB-backed.

## 8. Modell- und Runtime-Strategie

Runtimes:
- `local` (lokales Modell/Gateway)
- `api` (Cloud/API-Modelle)

Routing:
- `ModelRouter` priorisiert requested model, ansonsten score-basierte Auswahl.
- Fallback-Kette bei modellbezogenen LLM-Fehlern.
- Health/Latency/Cost/Profile fließen in Entscheidung ein.

## 9. Beobachtbarkeit und Testbarkeit

Beobachtbarkeit:
- Strukturierte Logs für WS, Runtime-Switch, Fehlerpfade, Shutdown-Cleanup.
- Lifecycle-Events als durchgehender Audit-/Status-Stream.
- Zusätzliche Lifecycle-Sichtbarkeit für Depth-Policy-Entscheidungen über `agent_depth_policy_applied` (inkl. requested/resolved/depth-layer Details).

Teststatus (Kernsuiten):
- `tests/test_control_plane_contracts.py`
- `tests/test_backend_e2e.py`
- `tests/test_subrun_lane.py`
- `tests/test_ws_handler.py`
- `tests/test_runtime_manager_auth.py`
- `tests/test_idempotency_service.py`
- `tests/test_state_store_list_runs_index.py`
- `tests/test_head_agent_adapter_constraints.py`

Aktueller Stand: relevante Kern-/Regressionssuiten grün (zuletzt lokal validiert).

## 10. Benchmarking-Strategie (neu)

Zusätzlich zu Smoke-/E2E-Tests existiert eine szenariobasierte Benchmark-Pipeline für den produktionsnahen WS-Pfad:

- Runner: `benchmarks/run_benchmark.py`
- Levels: `easy`, `mid`, `hard`
- Szenarioquelle: `benchmarks/scenarios/default.json`
- Artefakte: `monitoring/benchmarks/<timestamp-uuid>/` mit `summary.md`, `results.json`, `*.events.jsonl`

Die Pipeline misst nicht nur Pass/Fail, sondern auch Laufzeit-/Event-Metriken (z. B. `duration_ms`, `first_token_ms`, Lifecycle-Stages) und ist auf Erweiterbarkeit über zusätzliche Cases ausgelegt.

## 11. Bekannte Grenzen / technische Schulden

1) Idempotency-Registries sind weiterhin in-memory (jetzt bounded via TTL/Eviction, aber ohne Persistenz über Restart).  
2) Session/Run-Queries bleiben dateibasiert; Index-Optimierung reduziert Hot-Path-Kosten, ersetzt aber keine persistente Query-Schicht.  
3) `RuntimeManager` vereint weiterhin mehrere Verantwortungen (State, Process, Model-Katalog, Auth-Gating).  
4) `HeadAgent` bleibt ein großer, leistungsfähiger Kernbaustein mit hoher Komplexität.

## 12. Architekturprinzipien für weitere Änderungen

- Keine API-Breaks an bestehenden REST-/WS-Verträgen.
- Strukturverbesserung vor Feature-Ausbau, wenn Risiko sinkt.
- Policies zentral halten (Single Source of Truth).
- Lifecycle zuerst (Startup/Shutdown explizit), dann Featurelogik.
- Kleine, testgetriebene Refactor-Schritte mit Contract-Regressionen.
