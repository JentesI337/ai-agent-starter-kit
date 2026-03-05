# ARCHITECTURE.md — AI Agent Starter Kit

> **Version:** 1.1 · **Stand:** 2025-07-16  
> **Scope:** Vollständiges Backend-Architektur-Dokument — Design, Reasoning Pipeline, Orchestration Pipeline, alle Subsysteme.

---

## Inhaltsverzeichnis

1. [Systemübersicht](#1-systemübersicht)
2. [6-Schichten-Architektur](#2-6-schichten-architektur)
3. [Verzeichnisstruktur](#3-verzeichnisstruktur)
4. [Transport-Schicht](#4-transport-schicht)
5. [Agent-Schicht (Reasoning Pipeline)](#5-agent-schicht-reasoning-pipeline)
6. [Orchestration-Schicht](#6-orchestration-schicht)
7. [Model-Routing-Schicht](#7-model-routing-schicht)
8. [Service-Schicht](#8-service-schicht)
9. [Persistence-Schicht](#9-persistence-schicht)
10. [Policy- & Guardrail-Schicht](#10-policy--guardrail-schicht)
11. [Skills- & Extensions-Schicht](#11-skills--extensions-schicht)
12. [Contract-System](#12-contract-system)
13. [Konfiguration](#13-konfiguration)
14. [Startup & Shutdown](#14-startup--shutdown)
15. [Datenfluss: Request Lifecycle (End-to-End)](#15-datenfluss-request-lifecycle-end-to-end)
16. [Concurrency-Modell](#16-concurrency-modell)
17. [Fehler-Taxonomie & Recovery](#17-fehler-taxonomie--recovery)
18. [Glossar](#18-glossar)

---

## 1. Systemübersicht

Das AI Agent Starter Kit ist ein **autonomes Multi-Agent-System** mit deterministischer Reasoning-Pipeline und rekursiver Delegation. Die Kernkomponenten:

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Angular)                     │
│                   WebSocket + REST Client                   │
└────────────────────────┬────────────────────────────────────┘
                         │ WebSocket / HTTP
┌────────────────────────▼────────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Transport: ws_handler · REST Routers · Control API  │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Agents: HeadAgent · CoderAgent · ReviewAgent        │   │
│  │  + CustomAgentStore (dynamisch aus JSON geladen)     │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Orchestration: OrchestratorApi · PipelineRunner     │   │
│  │  · FallbackStateMachine · SessionLaneManager         │   │
│  │  · SubrunLane · RunStateMachine                      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Model Routing: ModelRouter · ModelRegistry          │   │
│  │  · ModelHealthTracker · ContextWindowGuard           │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Services: 45+ Dienste (Reflection, Verification,    │   │
│  │  ActionParser, PromptKernel, ToolExecution,           │   │
│  │  ToolTelemetry, LearningLoop, PlatformInfo, …)       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Persistence: MemoryStore · SqliteStateStore         │   │
│  │  · LongTermMemoryStore · ReflectionFeedbackStore     │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Policy: ToolPolicy · PolicyApprovalService          │   │
│  │  · CircuitBreaker · AgentIsolation                   │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Skills: SkillsService · Discovery · Eligibility     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  LLM Backend: Ollama (lokal) │ OpenAI-kompatible API        │
└─────────────────────────────────────────────────────────────┘
```

**Technologie-Stack:**
- **Runtime:** Python 3.12+, asyncio
- **Web-Framework:** FastAPI mit WebSocket + REST
- **LLM-Integration:** `LlmClient` — OpenAI-kompatible API (`/v1/chat/completions`) oder native Ollama (`/api/chat`)
- **Persistence:** SQLite (StateStore, LTM), JSONL (MemoryStore), JSON (CustomAgents, RuntimeState)
- **Contracts:** Protocol-basierte Interfaces (kein Tight Coupling)
- **Konfiguration:** Pydantic `Settings` Klasse mit ~180 Feldern, alle über Umgebungsvariablen steuerbar

---

## 2. 6-Schichten-Architektur

```
Schicht 1   Transport          WebSocket Handler · REST Routers · Control API
                                ↕
Schicht 2   Agent/Orchestration HeadAgent.run() Pipeline · OrchestratorApi · PipelineRunner
                                ↕
Schicht 3   Runtime/Model       ModelRouter · ModelRegistry · LlmClient · ModelHealthTracker
                                ↕
Schicht 4   Persistence         MemoryStore · SqliteStateStore · LongTermMemoryStore
                                ↕
Schicht 5   Policy/Guardrail    ToolPolicy · ToolProfiles · PolicyApprovalService · CircuitBreaker · AgentIsolation
                                ↕
Schicht 6   Skills/Extensions   SkillsService · McpBridge · CustomAgentStore · Hooks
```

**Abhängigkeitsregel:** Jede Schicht darf nur auf gleiche oder tiefere Schichten zugreifen. Die Transport-Schicht kennt keine Persistence-Details. Agents nutzen Services über Protocol-Interfaces.

---

## 3. Verzeichnisstruktur

```
backend/app/
├── main.py                     # FastAPI App-Instanz, Router-Wiring, LazyRuntimeRegistry
├── app_setup.py                # build_fastapi_app(), configure_cors(), build_lifespan_context()
├── app_state.py                # ControlPlaneState, LazyMappingProxy, RuntimeComponents
├── config.py                   # Settings(BaseModel) — ~180 konfigurierbare Felder
├── agent.py                    # HeadAgent (2924 Zeilen) — Reasoning Pipeline
├── ws_handler.py               # WebSocket Handler (1428 Zeilen)
├── llm_client.py               # LlmClient — OpenAI/Ollama Dual-Mode
│
├── agents/                     # Spezialisierte Sub-Agents
│   ├── planner_agent.py        # PlannerAgent (max_context=4096, temp=0.2, depth=2)
│   ├── synthesizer_agent.py    # SynthesizerAgent (max_context=8192, temp=0.3, reflection=1)
│   ├── tool_selector_agent.py  # ToolSelectorAgent (max_context=4096, temp=0.1)
│   └── head_agent_adapter.py   # HeadAgentAdapter, CoderAgentAdapter wrapping concrete agents
│
├── contracts/                  # Protocol-basierte Interfaces
│   ├── agent_contract.py       # AgentContract ABC + AgentConstraints
│   ├── schemas.py              # PlannerInput/Output, ToolSelector*, Synthesizer*
│   ├── tool_protocol.py        # ToolProvider Protocol (14 Methoden)
│   └── tool_selector_runtime.py # ToolSelectorRuntime Protocol
│
├── interfaces/                 # Orchestration-Interfaces
│   ├── orchestrator_api.py     # OrchestratorApi (PipelineRunner + SessionLaneManager)
│   └── request_context.py      # RequestContext frozen dataclass
│
├── orchestrator/               # Pipeline-Steuerung
│   ├── pipeline_runner.py      # PipelineRunner (1256 Zeilen) — FallbackStateMachine-Integration
│   ├── fallback_state_machine.py # INIT→SELECT→EXECUTE→SUCCESS/FAILURE→FINALIZE (804 Zeilen)
│   ├── run_state_machine.py    # received→queued→planning→tool_loop→synthesis→persisted
│   ├── step_types.py           # PipelineStep: PLAN | TOOL_SELECT | TOOL_EXECUTE | SYNTHESIZE
│   ├── step_executors.py       # Frozen-Dataclass Wrappers für Step-Functions
│   ├── events.py               # 50+ LifecycleStage, build_lifecycle_event(), classify_error()
│   ├── session_lane_manager.py # Global Semaphore + Per-Session Locks + TTL Eviction
│   ├── subrun_lane.py          # Semaphore, max_spawn_depth, max_children_per_parent
│   └── recovery_strategy.py    # RecoveryStrategyResolution, RecoveryContext
│
├── model_routing/              # Modell-Auswahl & Scoring
│   ├── router.py               # ModelRouter — Scoring-Algorithmus
│   ├── model_registry.py       # ModelRegistry — statische + gemessene Profile
│   ├── capability_profile.py   # ModelCapabilityProfile (Pydantic)
│   └── context_window_guard.py # evaluate_context_window_guard()
│
├── services/                   # 45+ Business-Services
│   ├── reflection_service.py   # ReflectionService — LLM-basierte Qualitätsbewertung
│   ├── verification_service.py # VerificationService — Plan/Tool/Final Verifikation
│   ├── action_parser.py        # ActionParser — JSON-Reparatur, Truncation Recovery
│   ├── prompt_kernel_builder.py# PromptKernelBuilder — Deterministic Prompt Assembly
│   ├── tool_execution_manager.py # ToolExecutionManager — ~50 Dependency Injection Points
│   ├── tool_registry.py        # ToolRegistry, ToolExecutionPolicy
│   ├── tool_call_gatekeeper.py # collect_policy_override_candidates()
│   ├── intent_detector.py      # IntentDetector — Command/Research/General Intent
│   ├── ambiguity_detector.py   # AmbiguityDetector — Minimal (nur empty/pronoun)
│   ├── dynamic_temperature.py  # DynamicTemperatureResolver — Task-Type-abhängig
│   ├── reply_shaper.py         # ReplyShaper — Token-Entfernung, Deduplizierung, Suppression
│   ├── hook_contract.py        # HookExecutionContract — Timeout/Policy pro Hook
│   ├── policy_approval_service.py # PolicyApprovalService — Human-in-the-Loop
│   ├── circuit_breaker.py      # CircuitBreakerRegistry — Failure/Recovery Tracking
│   ├── model_health_tracker.py # ModelHealthTracker — Ring-Buffer, gemessene Profile
│   ├── agent_resolution.py     # resolve_agent(), capability_route_agent()
│   ├── agent_isolation.py      # AgentIsolationPolicy — Memory/Tool/State Isolation
│   ├── long_term_memory.py     # LongTermMemoryStore — SQLite, Failure/Episodic/Semantic
│   ├── failure_retriever.py    # FailureRetriever — Past-Failure-Kontext für Planner
│   ├── tool_retry_strategy.py  # ToolRetryStrategy — Fehler-Taxonomie + Retry-Entscheidung
│   ├── platform_info.py        # PlatformInfo, detect_platform() — OS/Shell/Runtime-Erkennung
│   ├── tool_outcome_verifier.py # ToolOutcomeVerifier — Deterministische Ergebnisprüfung
│   ├── tool_telemetry.py       # ToolTelemetry — Span-Tracking, Per-Tool-Statistiken
│   ├── tool_result_context_guard.py # enforce_tool_result_context_budget() + PII-Redaktion
│   ├── learning_loop.py        # LearningLoop — Tool-Outcome-Feedback an AdaptiveToolSelector
│   └── …                       # (+ 12 weitere)
│
├── state/                      # Persistence Layer
│   ├── state_store.py          # SqliteStateStore + StateStore Protocol
│   ├── task_graph.py           # TaskGraph, TaskNode, TaskStatus
│   └── context_reducer.py      # ContextReducer — Budget-basierte Kontext-Komprimierung
│
├── skills/                     # Skills Engine
│   ├── service.py              # SkillsService — Discovery + Caching + Snapshot
│   ├── discovery.py            # discover_skills() — SKILL.md Scanner
│   ├── eligibility.py          # filter_eligible_skills()
│   ├── models.py               # SkillSnapshot
│   └── prompt.py               # Skill-Prompt Rendering
│
├── routers/                    # FastAPI Router-Definitionen
│   ├── ws_agent_router.py      # /ws/agent WebSocket Endpoint
│   ├── run_api.py              # /api/v1/runs/* REST Endpoints
│   ├── subruns.py              # /api/v1/subruns/* Endpoints
│   ├── control_runs.py         # /api/v1/control/runs/*
│   ├── control_sessions.py     # /api/v1/control/sessions/*
│   ├── control_tools.py        # /api/v1/control/tools/*
│   ├── control_workflows.py    # /api/v1/control/workflows/*
│   ├── control_policy_approvals.py # /api/v1/control/policy-approvals/*
│   ├── runtime_debug.py        # /api/v1/debug/*
│   └── agents.py               # /api/v1/agents/*
│
├── handlers/                   # Business-Logic Handlers (Router-unabhängig)
│   ├── run_handlers.py
│   ├── session_handlers.py
│   ├── tools_handlers.py
│   ├── workflow_handlers.py
│   ├── policy_handlers.py
│   ├── skills_handlers.py
│   └── agent_handlers.py
│
├── prompts/                    # Prompt-Templates (Markdown)
│   ├── agent_rules.md          # Agent-Verhaltensregeln (Appendix zu Final-Prompt)
│   └── tool_routing.md         # Tool-Routing-Regeln (Appendix zu Tool-Selector-Prompt)
│
└── monitoring/                 # Benchmark & Monitoring
    └── …
```

---

## 4. Transport-Schicht

### 4.1 WebSocket Handler (`ws_handler.py`)

Der primäre Kommunikationskanal ist eine **persistente WebSocket-Verbindung** unter `/ws/agent`.

**Architektur des Handlers:**

```
Client ← WebSocket → handle_ws_agent(websocket, deps: WsHandlerDependencies)
                         │
                         ├── send_event(payload) ← Thread-Safe via asyncio.Lock
                         │
                         ├── SessionInboxService ← Message Queue pro Session
                         │     ├── enqueue() → Priorisierte Warteschlange
                         │     └── dequeue_prioritized() → Follow-Up-Deferral-Logik
                         │
                         ├── ensure_session_worker(session_id) ← 1 Worker-Task pro Session
                         │     └── drain_session_queue() → Loop über Inbox
                         │           └── execute_user_message_job(job) ← Kernlogik
                         │
                         └── Hauptschleife: receive_text() → parse → dispatch
```

**WsHandlerDependencies** injiziert alle Abhängigkeiten als Protokoll-Typen (kein Import konkreter Klassen):

```python
@dataclass
class WsHandlerDependencies:
    logger: LoggerLike
    settings: SettingsLike
    agent: AgentLike
    agent_registry: dict[str, AgentLike]
    runtime_manager: RuntimeManagerLike
    state_store: StateStoreLike
    subrun_lane: SubrunLaneLike
    sync_custom_agents: Callable[[], None]
    normalize_agent_id: Callable[[str | None], str]
    effective_orchestrator_agent_ids: Callable[[], set[str]]
    looks_like_review_request: Callable[[str], bool]
    looks_like_coding_request: Callable[[str], bool]
    route_agent_for_message: Callable[...]   # Capability-basiertes Routing
    resolve_agent: Callable[...]             # Agent + Orchestrator auflösen
    state_append_event_safe: Callable[...]
    state_mark_failed_safe: Callable[...]
    state_mark_completed_safe: Callable[...]
    lifecycle_status_from_stage: Callable[...]
    primary_agent_id: str                    # "head-agent"
    coder_agent_id: str                      # "coder-agent"
    review_agent_id: str                     # "review-agent"
    policy_approval_service: PolicyApprovalServiceLike | None
```

**Unterstützte Inbound-Message-Types:**

| Type | Beschreibung |
|------|-------------|
| `user_message` | Standard-Nutzeranfrage → Inbox → Agent Pipeline |
| `clarification_response` | Antwort auf `clarification_needed` Event |
| `policy_decision` | Allow/Deny für Tool-Policy-Approval |
| `runtime_switch_request` | Wechsel local ↔ api Runtime |
| `subrun_spawn` | Expliziter Subrun-Start |

**Message-Processing Flow:**

1. **Receive** → `parse_ws_inbound_message(raw)` — Pydantic-Validierung
2. **Directive Parsing** → `parse_directives_from_message()` — `@queue:steer`, `@reasoning:high`, etc.
3. **Normalization** → `normalize_queue_mode()`, `normalize_prompt_mode()`, `normalize_reasoning_level()`
4. **Agent Resolution** → `route_agent_for_message()` → Capability Matching → `resolve_agent()`
5. **Model Resolution** → `ensure_model_ready()` (lokal) oder `resolve_api_request_model()` (API)
6. **Enqueue** → `session_inbox.enqueue(session_id, run_id, message, meta)`
7. **Worker Start** → `ensure_session_worker(session_id)` → `drain_session_queue()`
8. **Execute** → `orchestrator.run_user_message(user_message, send_event, request_context)`

**Queue-Modi:**

| Modus | Verhalten |
|-------|-----------|
| `wait` | Sequentielle Verarbeitung, Client wartet auf Abschluss |
| `steer` | Neue Nachricht kann laufenden Run unterbrechen (`should_steer_interrupt()`) |
| `follow_up` | Follow-Up-Nachrichten können deferred werden (max `session_follow_up_max_deferrals`) |

### 4.2 REST API (Routers)

10 Router-Module, alle über Factory-Functions erzeugt (`build_*_router()`):

| Router | Prefix | Zweck |
|--------|--------|-------|
| `run_api` | `/api/v1/runs` | Run Start, Wait, Status |
| `subruns` | `/api/v1/subruns` | Subrun List, Get, Kill |
| `control_runs` | `/api/v1/control/runs` | Runs CRUD + Events + Audit |
| `control_sessions` | `/api/v1/control/sessions` | Session CRUD + History + Status |
| `control_tools` | `/api/v1/control/tools` | Tool Catalog, Policy Matrix |
| `control_workflows` | `/api/v1/control/workflows` | Workflow CRUD + Execute |
| `control_policy_approvals` | `/api/v1/control/policy-approvals` | Pending + Allow + Decide |
| `runtime_debug` | `/api/v1/debug` | Status, Features, Ping, Calibration, Tool-Telemetry |
| `agents` | `/api/v1/agents` | Agent Test, List |
| `ws_agent_router` | `/ws/agent` | WebSocket Upgrade |

**Handler-Layer-Separation:** Router definieren nur HTTP-Kontrakte (Path, Method, Schemas). Die Business-Logik liegt in `handlers/` (7 Module), die wiederum auf Services und OrchestratorApi delegieren.

### 4.3 CORS-Konfiguration

```python
def configure_cors(*, app, settings):
    cors_origins = list(settings.cors_allow_origins)
    if settings.app_env != "production" and not cors_origins:
        cors_origins = ["*"]
    cors_allow_credentials = settings.cors_allow_credentials
    if "*" in cors_origins:
        cors_allow_credentials = False  # Security: Wildcard + Credentials = verboten
```

---

## 5. Agent-Schicht (Reasoning Pipeline)

### 5.1 HeadAgent — Zentrale Klasse

`HeadAgent` (`agent.py`, 2924 Zeilen) ist die Kernklasse des Systems. Jeder Agent-Typ (head, coder, review) ist eine Spezialisierung:

```python
class HeadAgent:
    def __init__(self, name, role, client, memory, tools, model_registry, context_reducer,
                 spawn_subrun_handler, policy_approval_handler): ...

class CoderAgent(HeadAgent):
    def __init__(self):
        super().__init__(name=settings.coder_agent_name, role="coding-agent")

class ReviewAgent(HeadAgent):
    def __init__(self):
        super().__init__(name=settings.review_agent_name, role="review-agent")
```

**Injizierte Komponenten im Konstruktor:**

| Komponente | Typ | Funktion |
|-----------|-----|----------|
| `client` | `LlmClient` | LLM-Kommunikation |
| `memory` | `MemoryStore` | Session-Memory (JSONL) |
| `tools` | `ToolProvider` Protocol | Tooling (AgentTooling) |
| `model_registry` | `ModelRegistry` | Modell-Profile |
| `context_reducer` | `ContextReducer` | Budget-basierte Kontext-Komprimierung |
| `spawn_subrun_handler` | `Callable` | Subrun-Delegation |
| `policy_approval_handler` | `Callable` | Human-in-the-Loop |

**Intern erzeugte Sub-Agents:**

```python
def _build_sub_agents(self):
    self.planner_agent = PlannerAgent(client, system_prompt, failure_retriever)
    self.tool_selector_agent = ToolSelectorAgent(runtime=_HeadToolSelectorRuntime(self))
    self.synthesizer_agent = SynthesizerAgent(client, agent_name, emit_lifecycle_fn,
                                              system_prompt, temperature_resolver, prompt_ab_registry)
    self.plan_step_executor = PlannerStepExecutor(execute_fn=self._execute_planner_step)
    self.tool_step_executor = ToolStepExecutor(execute_fn=self._execute_tool_step)
    self.synthesize_step_executor = SynthesizeStepExecutor(execute_fn=self._execute_synthesize_step)
```

**Intern erzeugte Services:**

| Service | Konfiguration |
|---------|-------------|
| `SkillsService` | `SkillsRuntimeConfig(enabled, skills_dir, max_discovered, max_prompt_chars, cache_ttl)` |
| `IntentDetector` | Stateless, Keyword-basiert |
| `ActionParser` | Multi-Stage JSON Recovery |
| `ActionAugmenter` | Intent-gesteuerte Argument-Erweiterung |
| `AmbiguityDetector` | Minimal: nur Empty + Pronoun |
| `ReplyShaper` | Token-Entfernung, Deduplizierung |
| `VerificationService` | Plan/Tool/Final Coverage-Prüfung |
| `ReflectionService` (optional) | LLM-basierte Qualitätsbewertung |
| `ToolExecutionManager` | Zentraler Tool-Dispatcher |
| `ToolArgValidator` | Argument-Validierung + Command-Policy |
| `ToolRegistry` | Tool-Metadaten + Dispatch-Mapping |
| `ToolRetryStrategy` | Fehler-Taxonomie + Retry-Entscheidung |
| `ToolOutcomeVerifier` | Deterministische Tool-Ergebnisprüfung |
| `ToolTelemetry` | Span-Tracking + Per-Tool-Statistiken |
| `LearningLoop` | Tool-Outcome-Feedback (Selector, KB, Patterns) |

### 5.2 Die 11-Phasen Reasoning Pipeline (`run()`)

Die `run()` Methode implementiert eine **deterministische 11-Phasen-Pipeline**, die über Lifecycle-Events getrieben wird. Es gibt keine LLM-gesteuerte Entscheidung über den Pipeline-Ablauf — jede Phase folgt deterministisch auf die vorherige.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          HeadAgent.run()                                 │
│                                                                          │
│  Phase 1   INIT             Reconfiguration-Guard, ContextVars, emit     │
│     │                       run_started                                  │
│     ▼                                                                    │
│  Phase 2   GUARDRAILS       Input-Validierung (message, session_id,      │
│     │                       model, tool_policy), emit guardrails_passed  │
│     ▼                                                                    │
│  Phase 3   TOOL RESOLUTION  MCP-Tools registrieren, Tool-Policy          │
│     │                       auflösen (6-Layer), Toolchain prüfen         │
│     ▼                                                                    │
│  Phase 4   MEMORY & CONTEXT Memory-Add, Orphan-Repair, LTM-Context,      │
│     │                       ContextReducer.reduce(budget=plan)           │
│     ▼                                                                    │
│  Phase 5   AMBIGUITY GATE   AmbiguityDetector → Early-Return mit         │
│     │                       Rückfrage oder proceed                       │
│     ▼                                                                    │
│  Phase 6   PLANNING         PlannerAgent.execute() → LLM-Plan,           │
│     │                       Plan-Verifikation (strukturell+semantisch)   │
│     ▼                                                                    │
│  Phase 7   TOOL LOOP        ToolSelectorAgent → ToolExecutionManager     │
│     │                       → Replan bei empty/error/partial_error/      │
│     │                       all_suspicious/invalidated                  │
│     │                       (max 3 Zyklen: regular + empty + error)      │
│     ▼                                                                    │
│  Phase 8   TOOL RESULT      Tool-Result-Verifikation, Blocked-Handling,  │
│     │      VALIDATION       Steer-Interrupt, Web-Research-Fallback       │
│     ▼                                                                    │
│  Phase 9   SYNTHESIS        ContextReducer.reduce(budget=final),         │
│     │                       SynthesizerAgent.execute() → LLM-Synthese    │
│     ▼                                                                    │
│  Phase 10  REFLECTION +     ReflectionService.reflect() → Quality Score, │
│     │      EVIDENCE GATES   Retry bei should_retry, Evidence-Gates       │
│     │                       (Implementation/Orchestration), ReplyShaper  │
│     ▼                                                                    │
│  Phase 11  FINALIZATION     Final-Verifikation, Memory-Persist,          │
│                             Session-Distillation, Hooks(agent_end),      │
│                             Counter-Release, emit run_completed          │
└──────────────────────────────────────────────────────────────────────────┘
```

#### Phase 1: INIT

```python
if self._reconfiguring:
    raise RuntimeError("run() abgewiesen: Agent wird gerade rekonfiguriert.")
self._active_run_count += 1
# ContextVars setzen: send_event, session_id, request_id
await self._emit_lifecycle(send_event, stage="run_started", ...)
```

- **Reconfiguration Guard:** `_reconfiguring`-Flag verhindert gleichzeitigen `configure_runtime()`-Aufruf
- **Run Counter:** `_active_run_count` tracked parallele Runs (H-6 Concurrency-Safety)

#### Phase 2: GUARDRAILS

```python
self._validate_guardrails(user_message, session_id, model)
self._validate_tool_policy(tool_policy)
await self._emit_lifecycle(send_event, stage="guardrails_passed", ...)
```

- Input-Länge (`max_user_message_length`), Session-ID-Format, Model-Existenz
- Tool-Policy-Struktur validieren

#### Phase 3: TOOL RESOLUTION

```python
await self._ensure_mcp_tools_registered(send_event, request_id, session_id)
effective_allowed_tools = self._resolve_effective_allowed_tools(tool_policy)
toolchain_ok, toolchain_details = self.tools.check_toolchain()
```

- **MCP-Integration:** Bei `mcp_enabled=True` registriert `McpBridge` externe Tool-Server dynamisch
- **6-Layer Tool-Policy-Resolution** (siehe Abschnitt 10)
- **Toolchain-Check:** Prüft ob Workspace-Pfad und Shell verfügbar sind

#### Phase 4: MEMORY & CONTEXT

```python
self.memory.add(session_id, "user", user_message)
repaired_orphans = self.memory.repair_orphaned_tool_calls(session_id)
sanitized_items = self.memory.sanitize_session_history(session_id)

memory_items = self.memory.get_items(session_id)
memory_lines = [f"{item.role}: {item.content}" for item in memory_items]
ltm_context = self._build_long_term_memory_context(user_message)

plan_context = self.context_reducer.reduce(
    budget_tokens=budgets["plan"],
    user_message=user_message,
    memory_lines=memory_lines,
    tool_outputs=[],
    snapshot_lines=[ltm_context] if ltm_context else None,
)
```

- **Orphan-Repair:** Tool-Calls ohne Tool-Response bekommen `[orphaned]`-Marker
- **Sanitization:** Ungültige History-Einträge entfernen
- **Token-Budget:** `_step_budgets(max_context)` teilt das Kontext-Budget auf:
  - Plan: 25% (`max(256, int(budget * 0.25))`)
  - Tool: 30% (`max(256, int(budget * 0.30))`)
  - Final: 45% (`max(512, int(budget * 0.45))`)
- **Long-Term Memory:** `FailureRetriever` holt relevante Past-Failures für den Planner

#### Phase 5: AMBIGUITY GATE

```python
if settings.clarification_protocol_enabled and effective_prompt_mode != "subagent":
    ambiguity = self._ambiguity_detector.assess(user_message, plan_context.rendered)
    threshold = settings.clarification_confidence_threshold  # Default: 0.5
    if ambiguity.is_ambiguous and ambiguity.confidence < threshold:
        if ambiguity.default_interpretation:
            # → proceed with default
        else:
            # → Early-Return: clarification_needed Event an Client
            return clarification_text
```

- **Intentional minimal:** Nur `empty` und `bare pronoun` Fälle sind ambiguous
- **Subagent-Mode:** Kein Clarification-Gate (Subruns dürfen nicht den User fragen)

#### Phase 6: PLANNING

```python
plan_text = await self.plan_step_executor.execute(
    PlannerInput(user_message, reduced_context, prompt_mode), model
)
plan_verification = self._verification.verify_plan(user_message, plan_text)
semantic_plan_verification = self._verification.verify_plan_semantically(user_message, plan_text)
self.memory.add(session_id, "plan", plan_text)
```

- **PlannerAgent Constraints:** `max_context=4096`, `temperature=0.2`, `reasoning_depth=2`
- **Failure-Retriever:** Injiziert Past-Failure-Kontext wenn `failure_context_enabled=True`
- **Structured Planning:** Optional (`structured_planning_enabled`) → `PlanGraph` mit `as_plan_text()`
- **Verifikation:**
  - Strukturell: `verify_plan()` — Leer-Check, Länge, Coverage
  - Semantisch: `verify_plan_semantically()` — Keyword-Overlap User→Plan

#### Phase 7: TOOL LOOP

```python
max_replan_iterations = settings.run_max_replan_iterations           # Default: 1
max_empty_tool_replan = settings.run_empty_tool_replan_max_attempts  # Default: 1
max_error_tool_replan = settings.run_error_tool_replan_max_attempts  # Default: 1
total_replan_cycles = max_replan + max_empty + max_error             # Default: 3

for iteration in range(total_replan_cycles):
    tool_context = self.context_reducer.reduce(budget_tokens=budgets["tool"], ...)
    tool_results = await self.tool_step_executor.execute(
        ToolSelectorInput(user_message, plan_text, reduced_context, prompt_mode),
        session_id, request_id, send_event, model, effective_allowed_tools, steer_interrupt
    )
    tool_results_state = self._classify_tool_results_state(tool_results)
    # "usable" | "blocked" | "steer_interrupted" → break
    # "empty" → empty_replan  |  "error_only" → error_replan  |  "timeout_error" → break
    # "partial_error" → error_replan  |  "all_suspicious" → error_replan
    replan_reason = self._resolve_replan_reason(...)
    if replan_reason is None: break
    plan_text = await self.plan_step_executor.execute(replan_input, model)  # Re-Plan
```

**Tool-Result-States:**

| State | Bedeutung | Aktion |
|-------|-----------|--------|
| `usable` | Mind. 1 Tool-OK, kein reiner Fehler | → Weiter zu Synthesis |
| `blocked` | Tool benötigt Policy-Approval | → Early Return mit Blocked-Message |
| `steer_interrupted` | Neuere Nachricht in Inbox | → Early Return mit Interrupt-Message |
| `empty` | Kein Tool ausgewählt | → Replan (max `run_empty_tool_replan_max_attempts`) |
| `error_only` | Nur Fehler, kein OK | → Replan (max `run_error_tool_replan_max_attempts`) |
| `partial_error` | Mix aus OK + ERROR Results | → Replan (max `run_error_tool_replan_max_attempts`) |
| `all_suspicious` | Nur leere/Placeholder-Ergebnisse | → Replan (max `run_error_tool_replan_max_attempts`) |
| `timeout_error` | Tool-Timeout | → Kein Replan, sofort weiter |

**Root-Cause Replan:** Bei `plan_root_cause_replan_enabled=True` wird der Replan-Prompt mit Fehleranalyse angereichert.

#### Phase 8: TOOL RESULT VALIDATION

```python
tool_result_verification = self._verification.verify_tool_result(plan_text, tool_results)
# Blocked → Early Return mit blocked-Nachricht
# Steer Interrupted → Early Return mit Interrupt-Nachricht
# Web Research ohne Web-Fetch → Fallback-Reply
# Tool-Result-Context-Guard → PII-Redaktion + Truncation bei Überschreitung
```

- **Context Guard:** `enforce_tool_result_context_budget()` begrenzt Tool-Output-Größe relativ zum Context-Window
- **PII-Redaktion:** 6 Regex-Pattern (API-Keys, AWS-Keys, E-Mail, US-Telefon, SSN, IPv4) werden vor Truncation entfernt. Bei geändertem Output wird die Reason `"pii_redacted"` gesetzt.

#### Phase 9: SYNTHESIS

```python
synthesis_task_type = self._resolve_synthesis_task_type(user_message, tool_results)
# → "hard_research" | "research" | "implementation" | "orchestration" | "general" | "trivial"

final_context = self.context_reducer.reduce(budget_tokens=budgets["final"], ...)
final_text = await self.synthesize_step_executor.execute(
    SynthesizerInput(user_message, plan_text, tool_results, reduced_context,
                     prompt_mode, task_type=synthesis_task_type),
    session_id, request_id, send_event, model
)
```

- **SynthesizerAgent Constraints:** `max_context=8192`, `temperature=0.3`, `reflection_passes=1`
- **Dynamic Temperature:** `DynamicTemperatureResolver` passt Temperatur an Task-Type an:
  ```
  hard_research: 0.1  |  research: 0.15  |  implementation: 0.15
  orchestration: 0.2  |  general: 0.3    |  trivial: 0.4
  ```
- **Prompt-A/B-Testing:** `PromptAbRegistry` kann alternative Prompts für Synthese bereitstellen
- **Task-Type-Erkennung:**
  - `hard_research` → Bestimmte Research-Pattern im User-Message
  - `orchestration` → `spawned_subrun_id=` in Tool-Results
  - `implementation` → implement/fix/refactor/test Keywords
  - `research` → Web-Research oder `source_url` in Results

#### Phase 10: REFLECTION + EVIDENCE GATES

```python
# Reflection Loop
for reflection_pass in range(reflection_passes):
    verdict = await self._reflection_service.reflect(
        user_message, plan_text, tool_results, final_answer=final_text,
        model, task_type=synthesis_task_type
    )
    # verdict.score, .goal_alignment, .completeness, .factual_grounding
    if not verdict.should_retry: break
    # → Re-Synthesize mit Reflection-Feedback
    final_text = await self.synthesize_step_executor.execute(
        SynthesizerInput(..., tool_results + "\n[REFLECTION FEEDBACK]\n" + feedback, ...),
        session_id, request_id, send_event, model
    )

# Implementation Evidence Gate
if self._requires_implementation_evidence(...) and not self._has_implementation_evidence(tool_results):
    final_text = "I could not complete the implementation..."

# Orchestration Evidence Gate
if synthesis_task_type == "orchestration" and not self._has_orchestration_evidence(tool_results):
    final_text = "The delegated subrun did not complete successfully..."

# Reply Shaping
shape_result = self._shape_final_response(final_text, tool_results)
final_text = shape_result.text
```

**ReflectionService** — LLM-basierte Qualitätsbewertung:

| Dimension | Beschreibung | Scoring |
|-----------|-------------|---------|
| `goal_alignment` | Löst die Antwort das User-Intent? | 0.0–1.0 |
| `completeness` | Sind alle Teile beantwortet? | 0.0–1.0 |
| `factual_grounding` | Sind Fakten durch Tool-Outputs belegt? | 0.0–1.0 (hard_min=0.4) |

**Task-Type-sensitive Thresholds:**
```python
_REFLECTION_THRESHOLDS_BY_TASK_TYPE = {
    "hard_research": 0.75,  "research": 0.70,  "implementation": 0.65,
    "orchestration": 0.60,  "general": 0.55,    "trivial": 0.40,
}
```

**Evidence Gates** verhindern Halluzination bei Code-/Orchestration-Aufgaben:
- **Implementation:** Prüft ob `write_file`, `apply_patch`, `run_command` oder `code_execute` erfolgreich war
- **Orchestration:** Prüft ob `spawn_subrun` mit `terminal_reason=subrun-complete` vorhanden

#### Phase 11: FINALIZATION

```python
final_verification = self._verification.verify_final(user_message, final_text)
if not final_verification.ok:
    final_text = "No output generated."

self.memory.add(session_id, "assistant", final_text)
await send_event({"type": "final", "agent": self.name, "message": final_text})
await self._emit_lifecycle(send_event, stage="run_completed", ...)
status = "completed"
return final_text

# finally-Block:
# → Session-Distillation (LLM-gestützte Wissensdestillation für LTM)
# → Hooks: agent_end
# → ContextVars Reset
# → _active_run_count -= 1
```

- **Session-Distillation:** `_distill_session_knowledge()` — LLM extrahiert episodische + semantische Fakten aus dem Run und speichert sie in `LongTermMemoryStore`
- **Failure Journal:** Bei Exceptions wird `FailureEntry` in LTM geschrieben

### 5.3 Sub-Agents

Spezialisierte Agents mit eigenen `AgentConstraints`:

| Agent | max_context | temperature | reasoning_depth | reflection_passes | combine_steps |
|-------|------------|-------------|----------------|-------------------|---------------|
| `PlannerAgent` | 4096 | 0.2 | 2 | 0 | False |
| `ToolSelectorAgent` | 4096 | 0.1 | — | — | — |
| `SynthesizerAgent` | 8192 | 0.3 | — | 1 | — |

**PlannerAgent:**
- System-Prompt: `head_agent_plan_prompt` (mit optionalem LTM-Failure-Kontext)
- Structured Planning: Optional `PlanGraph` mit Steps
- Hard-Research-Detection: Erkennt tiefgreifende Research-Anfragen

**ToolSelectorAgent:**
- Delegiert an `ToolSelectorRuntime` Protocol
- `_HeadToolSelectorRuntime` bindet sich an `HeadAgent._execute_tools()`
- Legacy-Binding: `LegacyRunnerBinding` mit `WeakMethod` für Rückwärtskompatibilität

**SynthesizerAgent:**
- Dynamische Temperatur via `DynamicTemperatureResolver`
- Prompt-Varianten via `PromptAbRegistry`
- Reflection-Passes: 1 (Standard) — Synthesis wird nach Reflection-Feedback wiederholt

### 5.4 Step Executors

Frozen-Dataclass-Wrappers, die Pipeline-Steps typsicher kapseln:

```python
@dataclass(frozen=True)
class PlannerStepExecutor:
    execute_fn: Callable[..., Awaitable[str]]
    async def execute(self, payload: PlannerInput, model: str | None) -> str:
        return await self.execute_fn(payload, model)

@dataclass(frozen=True)
class ToolStepExecutor:
    execute_fn: Callable[..., Awaitable[str]]
    async def execute(self, payload, session_id, request_id, send_event, model,
                      allowed_tools, should_steer_interrupt) -> str:
        return await self.execute_fn(payload, session_id, request_id, ...)

@dataclass(frozen=True)
class SynthesizeStepExecutor:
    execute_fn: Callable[..., Awaitable[str]]
    async def execute(self, payload, session_id, request_id, send_event, model) -> str:
        return await self.execute_fn(payload, session_id, request_id, ...)
```

---

## 6. Orchestration-Schicht

### 6.1 OrchestratorApi (`interfaces/orchestrator_api.py`)

Entry-Point für alle Agent-Ausführungen — kombiniert Concurrency-Management mit Pipeline-Ausführung:

```python
class OrchestratorApi:
    def __init__(self, pipeline_runner: PipelineRunner, session_lane_manager: SessionLaneManager):
        self._pipeline_runner = pipeline_runner
        self._session_lane_manager = session_lane_manager

    async def run_user_message(self, user_message, send_event, request_context: RequestContext):
        # 1. Lane erwerben (SessionLaneManager)
        # 2. Tool-Policy auflösen (6-Layer)
        # 3. PipelineRunner.run() aufrufen
        # 4. Lane freigeben
```

**Tool-Policy-Resolution (6 Layered):**
```
Layer 1: preset-Policy (z.B. "safe", "full")
Layer 2: agent_tools_allow / agent_tools_deny (Settings)
Layer 3: incoming tool_policy (Client-Request)
Layer 4: also_allow (zusätzliche Tools per Request)
Layer 5: TOOL_POLICY_BY_MODEL (modell-spezifisch)
Layer 6: TOOL_POLICY_BY_PROVIDER (provider-spezifisch)
```

### 6.2 PipelineRunner (`orchestrator/pipeline_runner.py`)

Der PipelineRunner wickelt die LLM-Aufrufe ab und implementiert das **Failover-System**:

```
PipelineRunner.run()
    │
    ├── ModelRouter.route() → ModelRouteDecision (primary + fallbacks)
    │
    ├── Adaptive Inference Check (cost_budget, latency_budget)
    │
    ├── Context Window Guard (warn_below_tokens, hard_min_tokens)
    │
    └── FallbackStateMachine.run()
          │
          ├── SELECT_MODEL → Nächstes Modell aus Fallback-Liste
          │
          ├── EXECUTE_ATTEMPT → agent.run() aufrufen
          │
          ├── HANDLE_SUCCESS → Return
          │
          └── HANDLE_FAILURE → Fehlerklassifikation
                │
                ├── NON_RETRYABLE → Abbruch
                │
                ├── FAILOVER_REASON → Nächster Versuch
                │     ├── context_overflow → Recovery-Strategien
                │     ├── truncation_error → Recovery-Strategien
                │     ├── rate_limit → Backoff + Retry
                │     ├── model_unavailable → Fallback-Model
                │     └── timeout → Retry (limited)
                │
                └── FINALIZE_FAILURE → Alle Versuche erschöpft
```

**Failover-Reason-Patterns (Regex-basiert):**
```python
FAILOVER_REASON_PATTERNS = [
    ("context_overflow", r"context.*(length|window|overflow|exceed|limit|too long)"),
    ("truncation_error", r"truncat|input .* too long|max.*token"),
    ("model_unavailable", r"model.*not found|404.*model|pull.*model"),
    ("rate_limit", r"rate.?limit|429|too many requests"),
    ("timeout", r"timed?\s*out|timeout|deadline"),
    ("empty_response", r"empty.*(completion|response|content)"),
    ...
]
```

**Nicht-wiederholbar (NON_RETRYABLE_FAIL_FAST_BRANCH_BY_REASON):**
```python
NON_RETRYABLE = {
    "guardrail_violation", "policy_approval_cancelled",
    "invalid_input", "authentication_error", ...
}
```

### 6.3 FallbackStateMachine (`orchestrator/fallback_state_machine.py`)

Implementiert ein deterministisches **State-Machine-Pattern** für Modell-Failover:

```
               ┌──────────┐
               │  INIT    │
               └────┬─────┘
                    │
            ┌───────▼────────┐
            │ SELECT_MODEL   │◄───────────────────┐
            └───────┬────────┘                    │
                    │                             │
          ┌─────────▼──────────┐                  │
          │ EXECUTE_ATTEMPT    │                  │
          └─────────┬──────────┘                  │
                    │                             │
              ┌─────┴─────┐                       │
              │           │                       │
    ┌─────────▼────┐ ┌────▼──────────┐            │
    │HANDLE_SUCCESS│ │HANDLE_FAILURE │────────────┘
    └─────────┬────┘ └────┬──────────┘    (retry)
              │           │
              │    ┌──────▼──────────┐
              │    │FINALIZE_FAILURE │
              │    └─────────────────┘
              │
         (return result)
```

**FallbackAttemptState** — ~30 Tracking-Felder pro Versuch:
```python
@dataclass
class FallbackAttemptState:
    attempt: int
    model_id: str
    started_at: float
    ended_at: float | None
    duration_ms: float | None
    success: bool
    error: str | None
    error_category: str | None
    failover_reason: str | None
    recovery_strategy: str | None
    # ... ~20 weitere Felder
```

**FallbackRuntimeConfig** — 28 konfigurierbare Parameter:
```python
@dataclass(frozen=True)
class FallbackRuntimeConfig:
    max_attempts: int                               # Default: 16
    context_overflow_fallback_retry_enabled: bool    # Default: False
    prompt_compaction_enabled: bool                  # Default: False
    prompt_compaction_ratio: float                   # Default: 0.7
    payload_truncation_enabled: bool                 # Default: False
    recovery_backoff_enabled: bool                   # Default: True
    recovery_backoff_base_ms: int                    # Default: 500
    recovery_backoff_max_ms: int                     # Default: 5000
    recovery_backoff_multiplier: float               # Default: 2.0
    signal_priority_enabled: bool                    # Default: True
    persistent_priority_enabled: bool                # Default: True
    strategy_feedback_enabled: bool                  # Default: True
    # ... weitere
```

**Recovery-Strategien:**
- **Prompt Compaction:** Kürzt Prompt im Verhältnis `compaction_ratio` (0.7)
- **Payload Truncation:** Reduziert auf `target_chars` (1200)
- **Overflow Fallback Retry:** Wechsel auf nächstes Modell mit mehr Context
- **Truncation Fallback Retry:** Wechsel auf Modell mit besserer Truncation-Handling
- **Backoff:** Exponentiell (base=500ms, max=5000ms, multiplier=2.0, jitter=True)

**Recovery-Priority-Reihenfolge:**
```python
# Lokal:
context_overflow_priority_local = ["prompt_compaction", "overflow_fallback_retry"]
truncation_priority_local = ["payload_truncation", "truncation_fallback_retry"]

# API:
context_overflow_priority_api = ["overflow_fallback_retry", "prompt_compaction"]
truncation_priority_api = ["truncation_fallback_retry", "payload_truncation"]
```

**Priority Flip:** Nach `recovery_priority_flip_threshold` (Default: 2) Versuchen wird die Reihenfolge invertiert.

### 6.4 RunStateMachine (`orchestrator/run_state_machine.py`)

Forward-Only State-Transitions für Run-Lifecycle:

```
received → queued → planning → tool_loop → synthesis → finalizing → persisted
                                                                        │
                                                             ┌──────────┤
                                                             │          │
                                                          completed  failed  cancelled
```

```python
RUN_STATES_ORDER = [
    "received", "queued", "planning", "tool_loop",
    "synthesis", "finalizing", "persisted",
]
TERMINAL_RUN_STATES = {"completed", "failed", "cancelled"}

def is_allowed_run_state_transition(current, target) -> bool:
    if target in TERMINAL_RUN_STATES:
        return True  # Terminal-States sind immer erreichbar
    current_idx = RUN_STATES_ORDER.index(current)
    target_idx = RUN_STATES_ORDER.index(target)
    return target_idx >= current_idx  # Nur vorwärts
```

### 6.5 SessionLaneManager (`orchestrator/session_lane_manager.py`)

Concurrency-Controller für parallele Session-Ausführung:

```python
class SessionLaneManager:
    def __init__(self, global_max_concurrent: int, ttl_seconds: int):
        self._global_semaphore = asyncio.Semaphore(global_max_concurrent)  # Default: 8
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_last_access: dict[str, float] = {}
        self._ttl_seconds = ttl_seconds
```

- **Global Semaphore:** Max 8 gleichzeitige Runs system-weit
- **Per-Session Lock:** 1 Run pro Session gleichzeitig
- **TTL Eviction:** Idle Locks werden nach TTL entfernt

### 6.6 SubrunLane (`orchestrator/subrun_lane.py`)

Rekursive Agent-Delegation mit Tiefenbegrenzung:

```python
class SubrunLane:
    def __init__(self, max_concurrent, max_spawn_depth, max_children_per_parent, ...):
        self._semaphore = asyncio.Semaphore(max_concurrent)  # Default: 2
        self._max_spawn_depth = max_spawn_depth              # Default: 2
        self._max_children_per_parent = max_children_per_parent  # Default: 5

    async def spawn(self, parent_request_id, parent_session_id, user_message,
                    runtime, model, timeout_seconds, tool_policy, send_event,
                    agent_id, mode, preset, orchestrator_agent_ids, orchestrator_api):
        # 1. Tiefe prüfen (max_spawn_depth)
        # 2. Kinder-Limit prüfen (max_children_per_parent)
        # 3. Semaphore erwerben
        # 4. orchestrator_api.run_user_message(message, ..., request_context)
        # 5. Ergebnis zurückgeben oder Timeout
```

**Spawn-Hierarchie:**
```
Root Run (depth=0)
  └── Subrun A (depth=1)
        ├── Subrun A.1 (depth=2) ← max_spawn_depth erreicht
        └── Subrun A.2 (depth=2)
  └── Subrun B (depth=1)
```

### 6.7 Lifecycle Events (`orchestrator/events.py`)

50+ Lifecycle-Stages für vollständige Pipeline-Observability:

```python
class LifecycleStage(str, Enum):
    # Run-Level
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_INTERRUPTED = "run_interrupted"
    
    # Request-Level
    REQUEST_RECEIVED = "request_received"
    REQUEST_DISPATCHED = "request_dispatched"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_FAILED = "request_failed"
    
    # Pipeline-Phasen
    GUARDRAILS_PASSED = "guardrails_passed"
    TOOL_POLICY_RESOLVED = "tool_policy_resolved"
    TOOLCHAIN_CHECKED = "toolchain_checked"
    MEMORY_UPDATED = "memory_updated"
    CONTEXT_REDUCED = "context_reduced"
    CONTEXT_SEGMENTED = "context_segmented"
    PLANNING_STARTED = "planning_started"
    PLANNING_COMPLETED = "planning_completed"
    REPLANNING_STARTED = "replanning_started"
    REPLANNING_COMPLETED = "replanning_completed"
    
    # Verification
    VERIFICATION_PLAN = "verification_plan"
    VERIFICATION_PLAN_SEMANTIC = "verification_plan_semantic"
    VERIFICATION_TOOL_RESULT = "verification_tool_result"
    VERIFICATION_FINAL = "verification_final"
    
    # Reflection
    REFLECTION_COMPLETED = "reflection_completed"
    REFLECTION_FAILED = "reflection_failed"
    REFLECTION_SKIPPED = "reflection_skipped"
    
    # Evidence Gates
    IMPLEMENTATION_EVIDENCE_MISSING = "implementation_evidence_missing"
    ORCHESTRATION_EVIDENCE_MISSING = "orchestration_evidence_missing"
    WEB_RESEARCH_SOURCES_UNAVAILABLE = "web_research_sources_unavailable"
    
    # Tool Loop
    TOOL_RESULT_CONTEXT_GUARD_APPLIED = "tool_result_context_guard_applied"
    TERMINAL_WAIT_STARTED = "terminal_wait_started"
    TERMINAL_WAIT_COMPLETED = "terminal_wait_completed"
    
    # ... und weitere
```

```python
def build_lifecycle_event(*, request_id, session_id, stage, details=None, agent=None) -> dict:
    return {
        "type": "lifecycle",
        "request_id": request_id,
        "session_id": session_id,
        "stage": stage,
        "phase": _detect_phase(stage),    # "planning" | "tool_loop" | "synthesis" | "meta"
        "details": details or {},
        "agent": agent,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
```

**Error Classification:**
```python
class ErrorCategory(str, Enum):
    LLM = "llm_error"
    TOOL = "tool_error"
    GUARDRAIL = "guardrail_violation"
    RUNTIME = "runtime_error"
    CLIENT = "client_error"
    POLICY = "policy_error"
    UNKNOWN = "unknown_error"

def classify_error(exc: Exception) -> str:  # Maps Exception-Type → ErrorCategory
```

---

## 7. Model-Routing-Schicht

### 7.1 ModelRouter (`model_routing/router.py`)

Wählt das optimale Modell basierend auf Runtime, Health, Latency, Cost und Reasoning-Level:

```python
class ModelRouter:
    def route(self, *, runtime, requested_model, reasoning_level=None) -> ModelRouteDecision:
        # 1. Kandidaten sammeln: requested → runtime-default → fallback
        # 2. Score berechnen pro Kandidat
        # 3. Ranking: höchster Score = primary, Rest = fallbacks
        # 4. Profil auflösen (Registry + Health-Tracker Override)
```

**Scoring-Formel:**
```
Score = health_score × weight_health
      − expected_latency_ms × weight_latency
      − cost_score × weight_cost
      + runtime_bonus (wenn Modell zur Runtime passt)
      + reasoning_bonus (abhängig von reasoning_level)
```

**Reasoning-Level-Einfluss:**

| Level | Bonus |
|-------|-------|
| `high` / `ultrathink` | `+reasoning_depth × 10.0 + max_context / 8000.0` |
| `low` | `−reasoning_depth × 5.0 − cost_score × 6.0 + latency_savings` |
| `adaptive` | `+reasoning_depth × 3.0 − cost_score × 2.0` |
| `medium` (default) | Kein Bonus |

**Default-Weights:**
```python
model_score_weight_health = 100.0
model_score_weight_latency = 0.01
model_score_weight_cost = 10.0
model_score_runtime_bonus = 6.0
```

### 7.2 ModelRegistry (`model_routing/model_registry.py`)

Statische Modell-Profile + Fallback-Default:

```python
class ModelRegistry:
    def resolve(self, model_id: str) -> ModelCapabilityProfile:
        # Exakter Match → Prefix-Match → Default-Profil
```

**Vorkonfigurierte Profile:**

| model_id | max_context | reasoning | reflection | combine | temp | health | latency | cost |
|----------|------------|-----------|------------|---------|------|--------|---------|------|
| `settings.local_model` | 8000 | 2 | 0 | False | 0.2 | 0.92 | 950ms | 0.15 |
| `settings.api_model` | 16000 | 3 | 1 | True | 0.3 | 0.88 | 700ms | 0.75 |
| `minimax-m2:cloud` | 16000 | 2 | 0 | False | 0.3 | 0.9 | 650ms | 0.15 |
| `gpt-oss:20b-cloud` | 24000 | 3 | 1 | True | 0.25 | 0.9 | 900ms | (mid) |
| Default | 8000 | 2 | 0 | False | 0.3 | 0.85 | 1400ms | 0.5 |

### 7.3 ModelCapabilityProfile

```python
class ModelCapabilityProfile(BaseModel):
    model_id: str
    max_context: int             # ≥ 512
    reasoning_depth: int         # 0–10
    reflection_passes: int       # 0–10
    combine_steps: bool          # Mehrere Steps in einem LLM-Call
    temperature: float           # 0.0–2.0
    health_score: float          # 0.0–1.0 (Verfügbarkeit)
    expected_latency_ms: int     # ≥ 1
    cost_score: float            # 0.0–1.0 (relative Kosten)
```

### 7.4 ContextWindowGuard

```python
def evaluate_context_window_guard(*, tokens, warn_below_tokens, hard_min_tokens):
    return ContextWindowGuardResult(
        tokens=safe_tokens,
        should_warn=safe_tokens < warn_below_tokens,   # Default: 12000
        should_block=safe_tokens < hard_min_tokens,     # Default: 4000
    )
```

### 7.5 ModelHealthTracker

Live-Performance-Tracking via Ring-Buffer:
- `ring_buffer_size=50` Samples pro Modell
- `min_samples=10` bevor gemessene Werte statische Profile überschreiben
- `stale_after_seconds=300` — Daten verfallen nach 5 Minuten
- `apply_to_profile(profile)` → Überschreibt `health_score` und `expected_latency_ms`

---

## 8. Service-Schicht

### 8.1 ToolExecutionManager

Zentraler Dispatcher für Tool-Ausführung mit **~50 Dependency-Injection-Points**:

```python
class ToolExecutionManager:
    def __init__(self, registry: ToolRegistry): ...

    async def execute(
        self,
        user_message, plan_text, memory_context, prompt_mode,
        app_settings, model, allowed_tools, agent_name,
        request_id, session_id, client_model,
        complete_chat_fn, stream_chat_completion_fn,
        complete_chat_with_tools_fn, supports_function_calling_fn,
        emit_lifecycle_fn, invoke_hooks_fn,
        add_memory_fn, get_memory_fn, build_prompt_kernel_fn,
        action_parser, action_augmenter, arg_validator,
        invoke_tool_fn, invoke_spawn_subrun_fn,
        resolve_tool_policy_fn, run_tool_with_policy_fn,
        policy_override_candidates_fn, collect_lifecycle_event_fn,
        # ... weitere callables
    ) -> str: ...
```

**Konfiguration:**
```python
@dataclass(frozen=True)
class ToolExecutionConfig:
    tool_call_cap: int           # Default: 8
    tool_time_cap_seconds: float # Default: 90
    result_max_chars: int        # Default: 6000
    smart_truncate_enabled: bool # Default: True
    parallel_read_only: bool     # Default: False
    function_calling_enabled: bool # Default: True
```

**READ_ONLY_TOOLS** — Parallelisierbare Tools:
```python
READ_ONLY_TOOLS = {"read_file", "list_directory", "web_search", "web_fetch", "grep_search", ...}
```

**Erweiterte Ausführungs-Pipeline (neu):**

Der ToolExecutionManager integriert jetzt drei zusätzliche Subsysteme pro Tool-Aufruf:

1. **Safe Hook Invocation:** Alle `invoke_hooks()`-Aufrufe werden über `_safe_invoke_hooks()` gewrapped — 0.5s Timeout + Exception-Isolation. Hooks können den Tool-Loop nicht mehr crashen.

2. **ToolTelemetry Span-Tracking:** Jeder Tool-Aufruf wird als Span erfasst:
   ```python
   span = self._telemetry.start_span(tool=tool_name, call_id=call_id, args=args)
   try:
       result = await invoke_tool(...)
   finally:
       self._telemetry.end_span(span, status=status, error_category=...,
                                 retried=retried, outcome_status=outcome, result_chars=len(result))
   ```
   Spans werden auch bei `CancelledError` geschlossen (finally-Block).

3. **ToolOutcomeVerifier:** Nach erfolgreicher Tool-Ausführung prüft `ToolOutcomeVerifier.verify()` deterministisch ob das Ergebnis valide ist:
   - `"verified"` — Ergebnis OK
   - `"suspicious"` — Leere/Placeholder-Ergebnisse erkannt
   - `"failed"` — Expliziter Fehler im Output

4. **LearningLoop Feedback:** Ergebnisse werden an `LearningLoop.on_tool_outcome()` gemeldet — Fähigkeits-Mapping (`_infer_capability_from_tool`) weist Tool-Namen Capability-Tags zu (z.B. `list_dir` → `"filesystem"`, `web_fetch` → `"web"`).

**ToolRegistry — Erweiterte Fähigkeiten (neu):**

- **Transient-Retry-Whitelist:** `_TRANSIENT_RETRY_TOOLS` definiert idempotente Tools, die bei transienten Fehlern automatisch retry-fähig sind. **Wichtig:** `run_command` ist bewusst *nicht* enthalten (side-effectful). MCP-Tools (`mcp_*`) erhalten automatisch `retry_class="transient"`.

- **Provider-spezifische Schema-Normalisierung:** `build_function_calling_tools(provider=...)` normalisiert JSON-Schemas je nach LLM-Provider:
  - **Gemini:** `_normalize_schema_gemini()` entfernt nicht unterstützte JSON-Schema-Keys (`$schema`, `additionalProperties`, `examples`, etc.) rekursiv
  - **Anthropic:** `_normalize_schema_anthropic()` ersetzt Root-Level `anyOf`/`oneOf`-Unions durch `object` mit optionalen Properties

- **Function-Calling-Toggle:** `tool_selection_function_calling_enabled` ist jetzt über `settings.tool_selection_function_calling_enabled` steuerbar (vorher hardcoded `False`)

### 8.2 ActionParser

Multi-Stage JSON-Reparatur für LLM-Output:

```
Stage 1: Standard JSON parse
    │ fail
Stage 2: Balanced-Bracket Extraction
    │ fail
Stage 3: Truncation Recovery (unvollständiges JSON)
    │ fail
Stage 4: LLM Repair (Tool-Repair-Prompt)
    │ fail
Stage 5: Empty-Action Fallback
```

```python
class ActionParser:
    def parse(self, raw_output: str) -> list[dict]:
        # → [{"tool": "...", "args": {...}}, ...]
    def repair(self, raw_output: str) -> list[dict]: ...
    def extract_json_candidate(self, text: str) -> str | None: ...
```

### 8.3 PromptKernelBuilder

Deterministischer Prompt-Aufbau mit garantierter Section-Reihenfolge:

```python
SECTION_ORDER = ["system", "platform", "policy", "context", "skills", "tools", "task"]

_MODE_SECTION_LIMITS = {
    "full": None,         # Unbegrenzt
    "minimal": 2000,      # 2000 Chars pro Section
    "subagent": 1500,     # 1500 Chars pro Section
}
```

- **`platform`-Section (neu):** Enthält `PlatformInfo.summary()` — Einzeiler mit OS, Architektur, Shell und verfügbaren Runtimes. Wird vom HeadAgent bei `_build_prompt_sections()` unter dem Key `"platform"` injiziert. Aliases: `"platform_info"`, `"environment"`.
```

```python
class PromptKernelBuilder:
    def build(self, *, prompt_type, prompt_mode, sections) -> PromptKernel:
        ordered = self._ordered_sections(sections, prompt_mode)
        prompt_hash = self._build_hash(prompt_type, prompt_mode, ordered)
        section_fingerprints = self._build_section_fingerprints(ordered)
        rendered = self._render(prompt_type, prompt_mode, prompt_hash, ordered)
        return PromptKernel(kernel_version, prompt_type, prompt_mode,
                           prompt_hash, section_fingerprints, rendered)
```

**Output:**
```python
@dataclass(frozen=True)
class PromptKernel:
    kernel_version: str          # "prompt-kernel.v4"
    prompt_type: str             # "planning" | "tool_selection" | "synthesis"
    prompt_mode: str             # "full" | "minimal" | "subagent"
    prompt_hash: str             # SHA-256 Fingerprint
    section_fingerprints: dict   # Per-Section Hashes
    rendered: str                # Finaler Prompt-Text
```

### 8.4 ContextReducer

Budget-basierte Kontext-Komprimierung:

```python
class ContextReducer:
    def reduce(self, *, budget_tokens, user_message, memory_lines,
               tool_outputs, snapshot_lines=None) -> ReducedContext:
        budget = max(128, budget_tokens)
        tool_budget = max(32, int(budget * 0.40))     # 40% für Tools
        memory_budget = max(32, int(budget * 0.30))   # 30% für Memory
        snapshot_budget = max(16, int(budget * 0.10)) # 10% für Snapshots
        # Task: 20%
        # Identifier Preservation: UUIDs, Pfade, Hashes bleiben intakt
        # Sensitive Data Redaction: Bearer, API-Keys, Passwords → [REDACTED]
```

**Sensitive Patterns (automatisch redacted):**
```python
_SENSITIVE_PATTERNS = [
    (r"Bearer\s+[...]{12,}", r"\1[REDACTED]"),
    (r"api_?key[...]{8,}", r"\1[REDACTED]"),
    (r"Authorization:\s*[...]{8,}", r"\1[REDACTED]"),
    (r"-----BEGIN.*KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"password[...]{6,}", r"\1[REDACTED]"),
]
```

### 8.5 ReflectionService

LLM-basierte Qualitätsbewertung der Synthese:

```python
class ReflectionService:
    async def reflect(self, *, user_message, plan_text, tool_results,
                      final_answer, model, task_type) -> ReflectionVerdict:
        effective_threshold = _REFLECTION_THRESHOLDS_BY_TASK_TYPE.get(task_type, self.threshold)
        reflection_prompt = self._build_reflection_prompt(...)
        raw_verdict = await self.client.complete_chat(
            system_prompt=_REFLECTION_SYSTEM_PROMPT,
            user_prompt=reflection_prompt,
            model=model,
            temperature=0.1,  # Niedrig für konsistente Bewertung
        )
        return self._parse_verdict(raw_verdict, threshold=effective_threshold)
```

**Prompt-Injection-Schutz:**
```python
def _sanitize_for_prompt(text, max_chars):
    sanitized = text[:max_chars]
    sanitized = sanitized.replace("```", "` ` `")
    sanitized = re.sub(
        r"(return\s+json|you\s+must|ignore\s+previous|disregard|override|system\s*:)",
        r"[\1]", sanitized, flags=re.IGNORECASE
    )
```

### 8.6 VerificationService

Deterministische Qualitätsprüfung (ohne LLM):

```python
class VerificationService:
    def verify_plan(self, *, user_message, plan_text) -> VerificationResult: ...
    def verify_plan_semantically(self, *, user_message, plan_text) -> VerificationResult: ...
    def verify_tool_result(self, *, plan_text, tool_results) -> VerificationResult: ...
    def verify_final(self, *, user_message, final_text) -> VerificationResult: ...
```

**Plan-Coverage-Prüfung:**
```python
plan_coverage_warn_threshold = 0.15   # Warnung bei <15% Keyword-Overlap
plan_coverage_fail_threshold = 0.0    # Fail bei 0% (deaktiviert per Default)
```

### 8.7 ReplyShaper

Post-Processing der finalen Antwort:

```python
class ReplyShaper:
    def sanitize(self, final_text) -> str:
        # Entfernt [TOOL_CALL]...[/TOOL_CALL] Blöcke
        # Entfernt {tool => ...} Pattern
        # Komprimiert übermäßige Newlines
    
    def shape(self, raw_response, tool_results, user_message, *,
              final_text, tool_markers) -> ReplyShapeResult:
        # Erkennt NO_REPLY, ANNOUNCE_SKIP Tokens → Suppression
        # Dedupliziert wiederholte Zeilen
        # Entfernt Tool-Marker-Leaks
```

### 8.8 DynamicTemperatureResolver

Task-Type-abhängige Temperatur:

```python
class DynamicTemperatureResolver:
    def resolve(self, task_type, *, reasoning_level=None) -> float:
        base = self._overrides.get(task_type, self._base)
        if reasoning_level in {"high", "ultrathink"}:
            return base - 0.05   # Kälter für tiefes Reasoning
        if reasoning_level == "low":
            return base + 0.05   # Wärmer für schnelle Antworten
        return base
```

### 8.9 IntentDetector

Keyword-basierte Intent-Erkennung:

```python
class IntentDetector:
    def detect(self, user_message) -> IntentGateDecision:
        # Erkennt: "run command", "execute command", "shell command",
        #          "führe aus", "starte" → Command-Intent
        # Extrahiert: command aus Backticks/Quotes
        # Erkennt: missing_slots (kein Command angegeben)
```

### 8.10 HookContract

Konfigurierbare Hook-Ausführung mit Timeout und Failure-Policy:

```python
@dataclass(frozen=True)
class HookExecutionContract:
    hook_name: str                 # z.B. "before_model_resolve"
    hook_contract_version: str     # "hook-contract.v2"
    timeout_ms: int                # Default: 1500
    failure_policy: str            # "soft_fail" | "hard_fail" | "skip"
```

**Verfügbare Hooks:**
- `before_model_resolve` — Vor Modell-Auswahl
- `before_prompt_build` — Vor Prompt-Assembly
- `before_transcript_append` — Vor Memory-Persist
- `agent_end` — Nach Run-Abschluss

---

## 9. Persistence-Schicht

### 9.1 MemoryStore

Session-basierter Kurzzeitspeicher (JSONL):

```python
class MemoryStore:
    def __init__(self, max_items_per_session: int, persist_dir: str):
        # max_items_per_session = 30 (Default)
    
    def add(self, session_id, role, content): ...
    def get_items(self, session_id) -> list[MemoryItem]: ...
    def repair_orphaned_tool_calls(self, session_id) -> int: ...
    def sanitize_session_history(self, session_id) -> int: ...
```

**Rollen:** `user`, `assistant`, `plan`, `tool_call`, `tool_result`

### 9.2 SqliteStateStore

Run- und Snapshot-Persistenz:

```python
class SqliteStateStore:
    def init_run(self, run_id, session_id, request_id, user_message, runtime, model): ...
    def set_task_status(self, run_id, task_id, label, status): ...
    # Runs: JSON-Dateien in state_store/runs/
    # Snapshots: JSON-Dateien in state_store/snapshots/
```

### 9.3 LongTermMemoryStore

SQLite-basierter Langzeitspeicher mit 3 Datentypen:

| Typ | Beschreibung | Quelle |
|-----|-------------|--------|
| `failure` | Vergangene Fehler (error_type, root_cause, solution, prevention) | Exception-Handler im `run()` Finally-Block |
| `episodic` | Session-Destillate (was wurde gelernt) | `_distill_session_knowledge()` |
| `semantic` | Schlüsselfakten (key_facts) | `_distill_session_knowledge()` |

### 9.4 ReflectionFeedbackStore

Speichert Reflection-Verdicts für Analyse:

```python
@dataclass(frozen=True)
class ReflectionRecord:
    record_id: str
    session_id: str
    request_id: str
    task_type: str
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    model_id: str
    prompt_variant: str | None
    retry_triggered: bool
    timestamp_utc: str
```

---

## 10. Policy- & Guardrail-Schicht

### 10.1 Tool-Policy-System

6-Layer Tool-Policy-Resolution:

```python
TOOL_POLICY_RESOLUTION_ORDER = [
    "preset",          # Layer 1: Preset → "safe" | "full" | "minimal"
    "settings",        # Layer 2: agent_tools_allow / agent_tools_deny
    "request",         # Layer 3: Incoming tool_policy vom Client
    "also_allow",      # Layer 4: Zusätzliche Tools per Request
    "model",           # Layer 5: TOOL_POLICY_BY_MODEL
    "provider",        # Layer 6: TOOL_POLICY_BY_PROVIDER
]
```

**Tool-Profile (neu):**

Vordefinierte Tool-Sets für typische Einsatzszenarien, definiert in `tool_policy.py`:

```python
TOOL_PROFILES = {
    "read_only": frozenset({"list_dir", "read_file", "file_search", "grep_search", ...}),
    "research":  frozenset({...read_only + "web_search", "web_fetch", "http_request"}),
    "coding":    frozenset({...read/write/execute, keine Web-Tools}),
    "full":      None,  # Keine Einschränkung
}

def resolve_tool_profile(profile_name, *, extra_allow=None, extra_deny=None) -> frozenset[str] | None:
    # Löst Profilname auf, wendet extra_allow/deny an
    # None = keine Einschränkung (full profile)
```

### 10.2 PolicyApprovalService

Human-in-the-Loop für risikoreiche Tool-Aufrufe:

```python
class PolicyApprovalService:
    async def request_approval(self, tool, resource, session_id) -> bool: ...
    async def decide(self, approval_id, decision, scope=None) -> dict | None: ...
    async def clear_session_overrides(self, session_id) -> None: ...
```

**Policy-Override-Kandidaten:**
```python
def collect_policy_override_candidates(*, actions, allowed_tools, normalize_tool_name,
                                        process_tools={"run_command", "code_execute", "spawn_subrun"}):
    # Erkennt Tools die nicht in allowed_tools sind
    # Extrahiert: command aus run_command, code aus code_execute, message aus spawn_subrun
    # → PolicyOverrideCandidate(tool="run_command", resource="pip install requests")
```

### 10.3 CircuitBreaker

Schutz vor wiederholten Fehlern pro Modell:

```python
class CircuitBreakerConfig:
    failure_threshold: int = 5          # Fehler für OPEN
    failure_window_seconds: int = 60    # Fehlerfenster
    recovery_timeout_seconds: int = 120 # Wartezeit vor HALF_OPEN
    success_threshold: int = 2          # Erfolge für CLOSED

class CircuitBreakerRegistry:
    def get_or_create(self, key: str) -> CircuitBreaker: ...
```

**States:** `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`

### 10.4 AgentIsolation

Isolation-Profile pro Agent:

```python
class AgentIsolationPolicy:
    memory_isolated: bool      # Eigene Memory-Instanz
    tool_scope_restricted: bool # Eingeschränkte Tool-Auswahl
    state_isolated: bool       # Eigener State-Namespace
```

### 10.5 ToolCallGatekeeper

Erkennt und blockiert Tools die Policy-Approval benötigen:

```python
def collect_policy_override_candidates(*, actions, allowed_tools, ...):
    # Filtert: run_command, code_execute, spawn_subrun
    # Prüft: tool ∉ allowed_tools
    # → List[PolicyOverrideCandidate]
```

### 10.6 Command-Allowlist

```python
command_allowlist_enabled: bool = True
command_allowlist: list[str] = ["python", "py", "pip", "pytest", ...]
command_allowlist_extra: list[str] = []  # Benutzerdefinierte Erweiterungen
```

---

## 11. Skills- & Extensions-Schicht

### 11.1 SkillsService

Dynamisches Skill-System basierend auf `SKILL.md`-Dateien:

```python
class SkillsService:
    def __init__(self, config: SkillsRuntimeConfig):
        # enabled, skills_dir, max_discovered, max_prompt_chars,
        # snapshot_cache_ttl_seconds, snapshot_cache_use_mtime
    
    def get_snapshot(self) -> SkillSnapshot:
        # 1. Cache-Check (TTL + mtime-Signatur)
        # 2. discover_skills(skills_dir, max=150)
        # 3. filter_eligible_skills()
        # 4. build_skill_snapshot()
        # 5. Cache Update
```

**Pipeline:**
```
skills_dir/SKILL.md → discover_skills() → filter_eligible_skills() →
    build_skill_snapshot() → SkillSnapshot(prompt, skills, counts)
```

### 11.2 McpBridge

Model Context Protocol (MCP) Integration:

```python
class McpBridge:
    def __init__(self, mcp_servers: list[McpServerConfig]): ...
    # Registriert externe Tool-Server dynamisch
    # MCP-Tools werden in ToolRegistry eingepflegt
```

**Retry & Reconnect (neu):**
- `call_tool()` implementiert einen Retry-Loop (max 2 Retries) mit `asyncio.wait_for(timeout=30.0)`
- Bei Verbindungsverlust wird automatisch ein Reconnect versucht, bevor der nächste Retry stattfindet
- Fehler-Isolation: Jeder Retry-Versuch fängt `Exception` ab und loggt den Fehlergrund

**Health-Check:**
```python
async def health_check(self) -> dict[str, bool]:
    # Pingt alle konfigurierten MCP-Server via list_tools() mit 5s Timeout
    # Gibt pro Server True/False zurück
```

### 11.3 CustomAgentStore

Dynamisch aus JSON-Dateien geladene Agent-Konfigurationen:

```
custom_agents/
  └── workflow-create-*.json  →  CustomAgentStore  →  Agent-Registry
```

### 11.4 Hook-System

Extensible via `_hooks: list[object]` auf HeadAgent:

```python
async def _invoke_hooks(self, *, hook_name, send_event, request_id, session_id, payload):
    for hook in self._hooks:
        contract = resolve_hook_execution_contract(settings=settings, hook_name=hook_name)
        # timeout_ms, failure_policy ("soft_fail" | "hard_fail" | "skip")
        hook_fn = getattr(hook, hook_name, None)
        if hook_fn:
            await asyncio.wait_for(hook_fn(payload), timeout=contract.timeout_ms / 1000)
```

> **Hinweis (neu):** Im ToolExecutionManager werden Hook-Aufrufe über `_safe_invoke_hooks()` gewrapped — 0.5s globaler Timeout + Exception-Isolation. Dies ist unabhängig vom `HookExecutionContract`-Timeout und stellt sicher, dass Hook-Fehler den Tool-Loop nicht blockieren.

---

## 12. Contract-System

Alle Schicht-Grenzen sind durch **Protocol-basierte Interfaces** definiert (kein Tight Coupling):

### 12.1 AgentContract

```python
class AgentContract(ABC):
    constraints: AgentConstraints  # max_context, temperature, reasoning_depth, ...
    @abstractmethod
    async def execute(self, payload, **kwargs): ...

@dataclass(frozen=True)
class AgentConstraints:
    max_context: int        # Token-Limit
    temperature: float      # LLM-Temperatur
    reasoning_depth: int    # Denk-Tiefe (0=flach, 10=tief)
    reflection_passes: int  # Reflexions-Runden
    combine_steps: bool     # Steps zusammenfassen
```

### 12.2 ToolProvider Protocol

```python
class ToolProvider(Protocol):
    def read_file(self, *, path, **kwargs) -> str: ...
    def write_file(self, *, path, content, **kwargs) -> str: ...
    def list_directory(self, *, path, **kwargs) -> str: ...
    def run_command(self, *, command, **kwargs) -> str: ...
    def web_search(self, *, query, **kwargs) -> str: ...
    def web_fetch(self, *, url, **kwargs) -> str: ...
    def code_execute(self, *, code, language, **kwargs) -> str: ...
    def check_toolchain(self) -> tuple[bool, dict]: ...
    # ... 14 Methoden gesamt

    @staticmethod
    def probe_command(cmd: str) -> bool:
        # Prüft via shutil.which ob ein Command auf PATH existiert
        # Wird vor run_command genutzt um fehlende Tools frühzeitig zu erkennen
```

### 12.3 ToolSelectorRuntime Protocol

```python
class ToolSelectorRuntime(Protocol):
    async def run_tools(
        self, *, payload: ToolSelectorInput, session_id, request_id, send_event,
        model, allowed_tools, should_steer_interrupt
    ) -> str: ...
```

### 12.4 Pipeline Schemas

```python
# Input/Output-Contracts für jeden Pipeline-Step:

@dataclass(frozen=True)
class PlannerInput:
    user_message: str
    reduced_context: str
    prompt_mode: str

@dataclass(frozen=True)
class PlannerOutput:
    plan_text: str

@dataclass(frozen=True)
class ToolSelectorInput:
    user_message: str
    plan_text: str
    reduced_context: str
    prompt_mode: str

@dataclass(frozen=True)
class ToolSelectorOutput:
    tool_results: str

@dataclass(frozen=True)
class SynthesizerInput:
    user_message: str
    plan_text: str
    tool_results: str
    reduced_context: str
    prompt_mode: str
    task_type: str

@dataclass(frozen=True)
class SynthesizerOutput:
    final_text: str
```

### 12.5 RequestContext

```python
@dataclass(frozen=True)
class RequestContext:
    session_id: str
    request_id: str
    runtime: str               # "local" | "api"
    model: str
    tool_policy: ToolPolicyDict | None
    also_allow: list[str] | None
    agent_id: str
    depth: int                 # Subrun-Tiefe (0 = root)
    preset: str | None
    orchestrator_agent_ids: list[str]
    queue_mode: str            # "wait" | "steer" | "follow_up"
    prompt_mode: str           # "full" | "minimal" | "subagent"
    reasoning_level: str       # "low" | "medium" | "high" | "ultrathink" | "adaptive"
    reasoning_visibility: str
    should_steer_interrupt: Callable[[], bool] | None
```

---

## 13. Konfiguration

### 13.1 Settings-Klasse (`config.py`)

~180 Felder als Pydantic `BaseModel`, alle über Umgebungsvariablen steuerbar:

#### Kern-Parameter

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `app_env` | `"development"` | Umgebung |
| `llm_base_url` | `"http://localhost:11434/v1"` | LLM-Endpoint |
| `llm_model` | `"llama3.3:70b-instruct-q4_K_M"` | Default-Modell |
| `local_model` | `= llm_model` | Lokales Modell |
| `api_model` | `"minimax-m2:cloud"` | API-Modell |
| `workspace_root` | (auto-resolved) | Arbeitsverzeichnis |

#### Pipeline-Kontrolle

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `run_max_replan_iterations` | `1` | Max reguläre Replans |
| `run_empty_tool_replan_max_attempts` | `1` | Max Replans bei leerem Tool-Output |
| `run_error_tool_replan_max_attempts` | `1` | Max Replans bei Tool-Fehler |
| `run_tool_call_cap` | `8` | Max Tool-Aufrufe pro Run |
| `run_tool_time_cap_seconds` | `90` | Max Tool-Ausführungszeit |
| `tool_result_max_chars` | `6000` | Max Chars pro Tool-Result |

#### Reflection & Verification

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `reflection_enabled` | `True` | Reflection aktiv |
| `reflection_threshold` | `0.6` | Min. Score für Akzeptanz |
| `reflection_factual_grounding_hard_min` | `0.4` | Hard-Fail unter diesem Wert |
| `plan_coverage_warn_threshold` | `0.15` | Plan-Coverage Warnschwelle |
| `plan_coverage_fail_threshold` | `0.0` | Plan-Coverage Fail (deaktiviert) |

#### Concurrency & Limits

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `session_lane_global_max_concurrent` | `8` | Max parallele Runs |
| `subrun_max_concurrent` | `2` | Max parallele Subruns |
| `subrun_max_spawn_depth` | `2` | Max Rekursionstiefe |
| `subrun_max_children_per_parent` | `5` | Max Kinder pro Eltern-Run |
| `subrun_timeout_seconds` | `900` | Subrun-Timeout (15min) |
| `policy_approval_wait_seconds` | `30` | Approval-Timeout |
| `max_user_message_length` | `8000` | Max Nachrichtenlänge |
| `memory_max_items` | `30` | Max Memory-Einträge pro Session |

#### Context Window & Model Routing

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `context_window_warn_below_tokens` | `12000` | Warnung unter diesem Wert |
| `context_window_hard_min_tokens` | `4000` | Hard-Block unter diesem Wert |
| `adaptive_inference_cost_budget_max` | `0.9` | Max Cost-Score für Inference |
| `adaptive_inference_latency_budget_ms` | `2400` | Max Latency für Inference |
| `pipeline_runner_max_attempts` | `16` | Max Failover-Versuche |

#### Feature Flags

| Flag | Default | Beschreibung |
|------|---------|-------------|
| `clarification_protocol_enabled` | `True` | Ambiguity-Gate aktiv |
| `structured_planning_enabled` | `False` | PlanGraph statt Freitext |
| `skills_engine_enabled` | `False` | Skills-System aktiv |
| `mcp_enabled` | `False` | MCP-Integration aktiv |
| `long_term_memory_enabled` | `True` | LTM-System aktiv |
| `session_distillation_enabled` | `True` | Wissensdestillation aktiv |
| `failure_journal_enabled` | `True` | Fehler-Journal aktiv |
| `dynamic_temperature_enabled` | `False` | Task-Type-Temperature aktiv |
| `prompt_ab_enabled` | `False` | Prompt-A/B-Testing aktiv |
| `circuit_breaker_enabled` | `False` | Circuit-Breaker aktiv |
| `model_health_tracker_enabled` | `False` | Live Health-Tracking aktiv |
| `tool_selection_function_calling_enabled` | `False` | Function-Calling-basierte Tool-Selection |

---

## 14. Startup & Shutdown

### 14.1 Startup-Sequenz (`startup_tasks.py`)

```python
def run_startup_sequence(*, settings, logger, ensure_runtime_components_initialized):
    log_startup_paths(settings, logger)
    clear_startup_persistence(settings, logger)   # Memory + State Reset (non-prod)
    ensure_runtime_components_initialized()        # LazyRuntimeRegistry
```

**Persistence-Reset (non-production):**
```python
def clear_startup_persistence(*, settings, logger):
    if settings.memory_reset_on_startup:     # True in development
        # Löscht alle .jsonl in memory_store/
    if settings.orchestrator_state_reset_on_startup:  # True in development
        # Löscht alle .json in state_store/runs/ und state_store/snapshots/
```

### 14.2 Shutdown-Sequenz

```python
def run_shutdown_sequence(*, active_run_tasks, logger):
    for _, task in list(active_run_tasks.items()):
        if not task.done():
            task.cancel()
    active_run_tasks.clear()
```

### 14.3 App-Lifespan

```python
def build_lifespan_context(*, on_startup, on_shutdown):
    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        await on_startup() if awaitable else on_startup()
        try:
            yield
        finally:
            await on_shutdown() if awaitable else on_shutdown()
    return _lifespan
```

### 14.4 main.py — Wiring

`main.py` ist die **Composition Root** — alle Abhängigkeiten werden hier verdrahtet:

```python
app = build_fastapi_app(title="AI Agent Starter Kit", settings=settings)

# Agents
PRIMARY_AGENT_ID = "head-agent"
CODER_AGENT_ID = "coder-agent"
REVIEW_AGENT_ID = "review-agent"

# Control Plane
control_plane_state = ControlPlaneState()
idempotency_mgr = IdempotencyManager(ttl_seconds=..., max_entries=...)

# Router Wiring
include_control_routers(app, run_start_handler=..., sessions_list_handler=..., ...)

# Runtime Components (Lazy)
# → HeadAgent, CoderAgent, ReviewAgent
# → OrchestratorApi pro Agent
# → ModelRouter, ModelHealthTracker, CircuitBreakerRegistry
# → SubrunLane, SessionLaneManager
# → SqliteStateStore

# Tool-Telemetry-Endpoint (neu)
# _get_tool_telemetry() → Lazy-Accessor für ToolTelemetry aus Agent-TEM
# GET /api/tools/stats → api_tool_telemetry_stats()
#   → {summary, tool_stats, session_trace} aus ToolTelemetry
```

---

## 15. Datenfluss: Request Lifecycle (End-to-End)

```
 Client
   │
   │ WebSocket: {"type": "user_message", "content": "...", "session_id": "..."}
   │
   ▼
 ws_handler.handle_ws_agent()
   │
   ├── 1. parse_ws_inbound_message() → WsInboundEnvelope
   ├── 2. parse_directives_from_message() → @queue:steer, @reasoning:high, etc.
   ├── 3. normalize_queue_mode(), normalize_prompt_mode()
   ├── 4. route_agent_for_message() → capability_route_agent()
   │       → "head-agent" | "coder-agent" | "review-agent"
   ├── 5. resolve_agent(agent_id) → (agent_id, AgentLike, OrchestratorApi)
   ├── 6. session_inbox.enqueue(session_id, run_id, message, meta)
   ├── 7. ensure_session_worker(session_id)
   │
   ▼
 drain_session_queue() → execute_user_message_job()
   │
   ├── 8. runtime_manager.ensure_model_ready() / resolve_api_request_model()
   │
   ▼
 OrchestratorApi.run_user_message()
   │
   ├── 9. SessionLaneManager.acquire_lane(session_id)
   ├── 10. Tool-Policy-Resolution (6-Layer)
   │
   ▼
 PipelineRunner.run()
   │
   ├── 11. ModelRouter.route() → ModelRouteDecision
   ├── 12. Adaptive Inference Guard
   ├── 13. Context Window Guard
   │
   ▼
 FallbackStateMachine.run()
   │
   ├── 14. SELECT_MODEL → primary_model
   │
   ▼
 HeadAgent.run() — 11-Phasen-Pipeline (siehe Abschnitt 5.2)
   │
   ├── Phase 1-2:   Init + Guardrails
   ├── Phase 3:     Tool Resolution + Toolchain Check
   ├── Phase 4:     Memory + Context Reduction
   ├── Phase 5:     Ambiguity Gate
   ├── Phase 6:     Planning → LLM → Plan-Verifikation
   ├── Phase 7:     Tool Loop → Tool Selection → Tool Execution → Replan
   ├── Phase 8:     Tool Result Validation
   ├── Phase 9:     Synthesis → LLM → Final Text
   ├── Phase 10:    Reflection + Evidence Gates + Reply Shaping
   ├── Phase 11:    Finalization + Memory-Persist + Distillation
   │
   ▼
 FallbackStateMachine
   │
   ├── HANDLE_SUCCESS → Return
   ├── HANDLE_FAILURE → Classify → Retry/Failover/Abort
   │
   ▼
 PipelineRunner → OrchestratorApi → ws_handler
   │
   ▼
 send_event({"type": "final", "message": "..."})
   │
   ▼
 Client empfängt WebSocket-Event
```

---

## 16. Concurrency-Modell

### 16.1 Architektur

```
                    ┌──────────────────────────────┐
                    │ Global Semaphore (max=8)     │
                    │ SessionLaneManager           │
                    └──────────┬───────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
   ┌───────▼─────┐    ┌───────▼─────┐    ┌───────▼─────┐
   │ Session A   │    │ Session B   │    │ Session C   │
   │ Lock (1 run)│    │ Lock (1 run)│    │ Lock (1 run)│
   └───────┬─────┘    └─────────────┘    └─────────────┘
           │
   ┌───────▼──────────────────┐
   │ SubrunLane (max=2)       │
   │ ├── Subrun A.1 (depth=1) │
   │ └── Subrun A.2 (depth=1) │
   │     └── A.2.1 (depth=2)  │  ← max_spawn_depth
   └──────────────────────────┘
```

### 16.2 Guards

| Guard | Mechanismus | Default |
|-------|-----------|---------|
| Global Concurrency | `asyncio.Semaphore` | 8 |
| Per-Session Exclusion | `asyncio.Lock` | 1 pro Session |
| Subrun Concurrency | `asyncio.Semaphore` | 2 |
| Subrun Depth | Counter-Check | max 2 |
| Children per Parent | Counter-Check | max 5 |
| Reconfiguration Guard | `_reconfiguring` Flag | Mutual Exclusion |
| Active Run Counter | `_active_run_count` | Prevents configure during run |
| Send-Event Lock | `asyncio.Lock` | Sequentielle WS-Sends |

### 16.3 Steer-Interrupt

```python
def should_steer_interrupt() -> bool:
    return queue_mode == "steer" and session_inbox.has_newer_than(session_id, request_id)
```

Wird in der Tool-Loop geprüft — bei `True` wird der aktuelle Run mit `steer_interrupted` beendet und die neuere Nachricht verarbeitet.

---

## 17. Fehler-Taxonomie & Recovery

### 17.1 Exception-Hierarchie

| Exception | Kategorie | Recovery |
|-----------|----------|---------|
| `GuardrailViolation` | `guardrail_violation` | Sofort-Abbruch, kein Retry |
| `PolicyApprovalCancelledError` | `policy_error` | Sofort-Abbruch |
| `ToolExecutionError` | `tool_error` | Replan möglich |
| `LlmClientError` | `llm_error` | Failover via FallbackStateMachine |
| `RuntimeSwitchError` | `runtime_error` | Benutzer informieren |
| `ClientDisconnectedError` | `client_error` | Run abbrechen, State aufräumen |

### 17.2 LLM-Failover-Recovery

```
Fehler → classify(message) → failover_reason
  │
  ├── context_overflow → [prompt_compaction → overflow_fallback_retry]
  ├── truncation_error → [payload_truncation → truncation_fallback_retry]
  ├── rate_limit → exponential_backoff + retry
  ├── model_unavailable → next_fallback_model
  ├── timeout → retry (limited)
  ├── empty_response → retry mit anderem Model
  └── non_retryable → sofort abbrechen
```

### 17.3 Tool-Loop-Recovery

```
Tool-Result-State → Recovery-Strategie
  │
  ├── empty → Replan (max run_empty_tool_replan_max_attempts)
  ├── error_only → Replan (max run_error_tool_replan_max_attempts)
  ├── partial_error → Replan (max run_error_tool_replan_max_attempts)
  ├── all_suspicious → Replan (max run_error_tool_replan_max_attempts)
  ├── timeout_error → Kein Replan, weiter zu Synthesis
  ├── blocked → Early Return mit blocked-Message
  ├── steer_interrupted → Early Return mit Interrupt-Message
  └── usable → Weiter zu Synthesis
```

**Retry-Delegation (neu):** `_is_retryable_tool_error()` delegiert an `ToolRetryStrategy.decide()` anstatt inline Retry-Logik. Der Retry-Strategy klassifiziert Fehler nach Taxonomie (`ErrorCategory`) und wählt die passende Strategie (`BACKOFF`, `ESCALATE`, `REPLAN`, `SKIP`).

### 17.4 Failure Journal

```python
# Bei jeder Exception in run():
self._long_term_memory.add_failure(FailureEntry(
    failure_id=request_id,
    task_description=user_message[:500],
    error_type=type(exc).__name__,
    root_cause=str(exc)[:500],
    solution=f"Review {type(exc).__name__} handling",
    prevention=f"Add guard for {type(exc).__name__}",
    tags=[type(exc).__name__],
))
```

---

## 18. Glossar

| Begriff | Definition |
|---------|-----------|
| **Run** | Eine einzelne Agent-Ausführung (user_message → final_text) |
| **Subrun** | Ein per `spawn_subrun` delegierter Kind-Run eines Eltern-Runs |
| **Session** | Logische Konversation mit shared Memory |
| **Lane** | Concurrency-Slot für eine Session im SessionLaneManager |
| **Pipeline Step** | PLAN → TOOL_SELECT → TOOL_EXECUTE → SYNTHESIZE |
| **Lifecycle Stage** | Atomares Event im Run-Lifecycle (50+ definiert) |
| **Failover** | Automatischer Wechsel auf Fallback-Modell bei Fehler |
| **Evidence Gate** | Prüfung ob Tool-Ergebnisse die behauptete Aktion belegen |
| **Reflection** | LLM-basierte Qualitätsbewertung der Synthese |
| **Replan** | Neuplanung nach fehlgeschlagener Tool-Ausführung |
| **Steer** | Interrupt eines laufenden Runs durch neuere Nachricht |
| **PromptKernel** | Deterministisch assemblierter Prompt mit Hash-Fingerprint |
| **ToolProvider** | Protocol-Interface für Tool-Implementierungen |
| **ContextReducer** | Budget-basierte Kontext-Komprimierung |
| **ModelRouteDecision** | Ergebnis des Model-Routings (primary + fallbacks + scores) |
| **FallbackStateMachine** | State-Machine für Modell-Failover (INIT→SELECT→EXECUTE→SUCCESS/FAILURE) |
| **HookContract** | Konfigurierbare Extension-Points (timeout, failure_policy) |
| **Task Type** | hard_research \| research \| implementation \| orchestration \| general \| trivial |
| **ToolRetryStrategy** | Fehler-Taxonomie-basierte Retry-Entscheidung (BACKOFF/ESCALATE/REPLAN/SKIP) |
| **ToolTelemetry** | Span-Tracking + Per-Tool-Statistiken für Tool-Ausführung |
| **ToolOutcomeVerifier** | Deterministische Prüfung ob Tool-Ergebnis valide ist (verified/suspicious/failed) |
| **LearningLoop** | Feedback-Loop: Tool-Outcomes → AdaptiveToolSelector + KnowledgeBase + PatternDetector |
| **PlatformInfo** | Gecachter Snapshot der Plattform-Umgebung (OS, Shell, Runtimes) |
| **ToolProfile** | Vordefiniertes Tool-Set (read_only, research, coding, full) für Policy-Resolution |
| **PII-Redaktion** | Automatische Entfernung sensibler Daten (API-Keys, E-Mail, etc.) aus Tool-Output |

---

*Erstellt aus dem tatsächlichen Quellcode des Projekts. Alle Codebeispiele, Konfigurationswerte und Architekturbeschreibungen basieren auf dem aktuellen Stand der Codebase.*
