# ARCHITECTURE.md — AI Agent Starter Kit

> **Version:** 1.5 · **Stand:** 2026-03-10  
> **Scope:** Vollständiges Backend-Architektur-Dokument — Design, Reasoning Pipeline, Orchestration Pipeline, Multi-Agency-Subsystem, 15-Agenten-Ökosystem, alle Subsysteme.

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
12. [Multi-Agency-Subsystem](#12-multi-agency-subsystem)
13. [Contract-System](#13-contract-system)
14. [Konfiguration](#14-konfiguration)
15. [Startup & Shutdown](#15-startup--shutdown)
16. [Datenfluss: Request Lifecycle (End-to-End)](#16-datenfluss-request-lifecycle-end-to-end)
17. [Concurrency-Modell](#17-concurrency-modell)
18. [Fehler-Taxonomie & Recovery](#18-fehler-taxonomie--recovery)
19. [Glossar](#19-glossar)

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
│  │  Agents: 15 Agenten (3 Core + 7 Specialist + 5 Industry) │ 
│  │  + CustomAgentStore (dynamisch aus JSON geladen)     │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Multi-Agency: CoordinationBridge · Supervisor       │   │
│  │  · AgentRegistry · Blackboard · MessageBus           │   │
│  │  · ConfidenceRouter · ParallelExecutor · Consensus   │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Orchestration: OrchestratorApi · PipelineRunner     │   │
│  │  · FallbackStateMachine · SessionLaneManager         │   │
│  │  · SubrunLane · RunStateMachine                      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Model Routing: ModelRouter · ModelRegistry          │   │
│  │  · ModelHealthTracker · ContextWindowGuard           │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │  Services: 60+ Dienste (Reflection, Verification,    │   │
│  │  ActionParser, PromptKernel, ToolExecution,          │   │
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
- **Konfiguration:** Pydantic `Settings` Klasse mit ~230 Feldern, alle über Umgebungsvariablen steuerbar

---

## 2. 6-Schichten-Architektur

```
Schicht 1   Transport          WebSocket Handler · REST Routers · Control API
                                ↕
Schicht 2   Agent/Orchestration HeadAgent.run() Pipeline · OrchestratorApi · PipelineRunner
                                · Multi-Agency: CoordinationBridge · Supervisor · Consensus
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
├── config.py                   # Settings(BaseModel) — ~230 konfigurierbare Felder
├── agent.py                    # HeadAgent (~1919 Zeilen) — Reasoning Pipeline
├── agent_runner.py             # AgentRunner (~1341 Zeilen) — Continuous Streaming Tool Loop
├── ws_handler.py               # WebSocket Handler (~1400 Zeilen)
├── llm_client.py               # LlmClient — OpenAI/Ollama Dual-Mode
│
├── agents/                     # Agent-Definitionen (UnifiedAgentRecord-basiert)
│   ├── unified_agent_record.py # UnifiedAgentRecord (Pydantic) — Single Model für alle Agents
│   ├── factory_defaults.py     # 15 builtin AgentRecords mit ConstraintSpec
│   ├── unified_adapter.py      # UnifiedAgentAdapter — AgentContract-Bridge
│   ├── agent_store.py          # AgentStore — Builtin + Custom Agent Registry
│   └── agents_manifest.json    # Agent-Manifest (IDs, Metadaten)
│
├── contracts/                  # Protocol-basierte Interfaces
│   ├── agent_contract.py       # AgentContract ABC + AgentConstraints
│   ├── schemas.py              # Shared Contract Schemas
│   └── tool_protocol.py        # ToolProvider Protocol (14 Methoden)
│
├── interfaces/                 # Orchestration-Interfaces
│   ├── orchestrator_api.py     # OrchestratorApi (PipelineRunner + SessionLaneManager)
│   └── request_context.py      # RequestContext frozen dataclass
│
├── orchestrator/               # Pipeline-Steuerung
│   ├── pipeline_runner.py      # PipelineRunner (~1160 Zeilen) — FallbackStateMachine-Integration
│   ├── fallback_state_machine.py # INIT→SELECT→EXECUTE→SUCCESS/FAILURE→FINALIZE (~750 Zeilen)
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
├── services/                   # 60+ Business-Services
│   ├── reflection_service.py   # ReflectionService — LLM-basierte Qualitätsbewertung
│   ├── verification_service.py # VerificationService — Final Verifikation (verify_final)
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
│   ├── agent_resolution.py     # resolve_agent(), capability_route_agent() — 15-Agenten-Routing
│   ├── agent_isolation.py      # AgentIsolationPolicy — Memory/Tool/State Isolation
│   ├── long_term_memory.py     # LongTermMemoryStore — SQLite, Failure/Episodic/Semantic
│   ├── failure_retriever.py    # FailureRetriever — Past-Failure-Kontext für Planner
│   ├── tool_retry_strategy.py  # ToolRetryStrategy — Fehler-Taxonomie + Retry-Entscheidung
│   ├── platform_info.py        # PlatformInfo, detect_platform() — OS/Shell/Runtime-Erkennung
│   ├── tool_outcome_verifier.py # ToolOutcomeVerifier — Deterministische Ergebnisprüfung
│   ├── tool_telemetry.py       # ToolTelemetry — Span-Tracking, Per-Tool-Statistiken
│   ├── tool_result_context_guard.py # enforce_tool_result_context_budget() + PII-Redaktion
│   ├── learning_loop.py        # LearningLoop — Tool-Outcome-Feedback an AdaptiveToolSelector
│   ├── adaptive_tool_selector.py # AdaptiveToolSelector — Weighted Scoring für Tool-Selection
│   ├── session_inbox_service.py # SessionInboxService — Message Queue pro Session
│   ├── session_query_service.py # SessionQueryService — Session-State-Abfragen
│   ├── session_security.py     # SessionSecurity — HMAC-signierte Session-IDs (SEC OE-07)
│   ├── state_encryption.py     # StateEncryption — AES-256-GCM Encryption-at-Rest (SEC OE-08)
│   ├── rate_limiter.py         # RateLimiter — Token-Bucket per IP/Session (SEC OE-03)
│   ├── directive_parser.py     # DirectiveParser — @queue:steer, @reasoning:high, etc.
│   ├── request_normalization.py# RequestNormalization — Queue/Prompt/Reasoning-Level Normalisierung
│   ├── action_augmenter.py     # ActionAugmenter — Intent-gesteuerte Argument-Erweiterung
│   ├── tool_arg_validator.py   # ToolArgValidator — Argument-Validierung + Command-Policy
│   ├── prompt_ab_registry.py   # PromptAbRegistry — Prompt-A/B-Testing-Varianten
│   ├── error_taxonomy.py       # ErrorTaxonomy — Canonical Error-Klassifikation für Tools
│   ├── self_healing_loop.py    # SelfHealingLoop — Root-Cause-Analyse + Recovery + Retry
│   ├── graceful_degradation.py # GracefulDegradation — Partial Results statt "Failed"
│   ├── tool_discovery_engine.py# ToolDiscoveryEngine — 4-Phasen Tool-Discovery-Pipeline
│   ├── tool_knowledge_base.py  # ToolKnowledgeBase — SQLite Tool-Wissens-Speicher
│   ├── tool_chain_planner.py   # ToolChainPlanner — Multi-Step Toolchain-Planung
│   ├── tool_ecosystem_map.py   # ToolEcosystemMap — Graph der Tool-Ökosysteme
│   ├── tool_provisioner.py     # ToolProvisioner — Install + Verify Pipeline mit Audit
│   ├── tool_synthesizer.py     # ToolSynthesizer — Ad-hoc Script-Generierung in Sandbox
│   ├── tool_policy_service.py  # ToolPolicyService — Policy-Verwaltung REST-Logik
│   ├── execution_contract.py   # ExecutionContract — Pre/Post-Conditions für Tool-Calls
│   ├── execution_pattern_detector.py # ExecutionPatternDetector — Anti-Pattern-Erkennung
│   ├── code_sandbox.py         # CodeSandbox — Isolierte Code-Ausführung
│   ├── environment_snapshot.py # EnvironmentSnapshot — Pre-Install-State + Rollback
│   ├── package_manager_adapter.py # PackageManagerAdapter — npm/pip/apt/brew/choco Adapter
│   ├── provisioning_policy.py  # ProvisioningPolicy — Governance für Tool-Installation
│   ├── vision_service.py       # VisionService — Bild-Analyse via LLM
│   ├── web_search.py           # WebSearch — Web-Suche mit Fallback-Providern
│   ├── benchmark_calibration.py# BenchmarkCalibration — Modell-Benchmark-Kalibrierung
│   ├── control_fingerprints.py # ControlFingerprints — Tool-Policy Fingerprint-Berechnung
│   ├── idempotency_service.py  # IdempotencyService — Request-Deduplizierung
│   ├── idempotency_manager.py  # IdempotencyManager — TTL-basierter Idempotency-Cache
│   └── reflection_feedback_store.py # ReflectionFeedbackStore — Reflection-Verdicts Persistenz
│
├── state/                      # Persistence Layer
│   ├── state_store.py          # SqliteStateStore + StateStore Protocol
│   ├── task_graph.py           # TaskGraph, TaskNode, TaskStatus
│   └── snapshots.py            # Run-Snapshot Serialisierung + Restore
│
├── skills/                     # Skills Engine
│   ├── service.py              # SkillsService — Discovery + Caching + Snapshot
│   ├── discovery.py            # discover_skills() — SKILL.md Scanner
│   ├── eligibility.py          # filter_eligible_skills()
│   ├── models.py               # SkillDefinition, SkillSnapshot, SkillMetadata
│   ├── parser.py               # Skill-Datei-Parser (SKILL.md → SkillDefinition)
│   ├── retrieval.py            # Skill-Retrieval mit Relevanz-Scoring
│   ├── snapshot.py             # build_skill_snapshot() + Prompt-Rendering
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

`HeadAgent` (`agent.py`, ~2900 Zeilen) ist die Kernklasse des Systems. 15 Agent-Typen spezialisieren sie:

```python
class HeadAgent:
    def __init__(self, name, role, client, memory, tools, model_registry,
                 spawn_subrun_handler, policy_approval_handler, agent_record): ...
```

**15 registrierte Agenten:**

| Agent-Klasse | Rolle | Adapter | Zugriff | Temp |
|---|---|---|---|---|
| `HeadAgent` | `head-agent` | `HeadAgentAdapter` | Unrestricted | 0.3 |
| `CoderAgent` | `coding-agent` | `CoderAgentAdapter` | Unrestricted | 0.3 |
| `ReviewAgent` | `review-agent` | `ReviewAgentAdapter` | Read-only | 0.2 |
| `ResearcherAgent` | `researcher-agent` | `ResearcherAgentAdapter` | Read-only | 0.25 |
| `ArchitectAgent` | `architect-agent` | `ArchitectAgentAdapter` | Read-only | 0.35 |
| `TestAgent` | `test-agent` | `TestAgentAdapter` | Read + Test-Runner | 0.15 |
| `SecurityAgent` | `security-agent` | `SecurityAgentAdapter` | Read + Audit-CLI | 0.1 |
| `DocAgent` | `doc-agent` | `DocAgentAdapter` | Read + Write (.md) | 0.4 |
| `RefactorAgent` | `refactor-agent` | `RefactorAgentAdapter` | Unrestricted | 0.2 |
| `DevOpsAgent` | `devops-agent` | `DevOpsAgentAdapter` | Unrestricted | 0.2 |
| `FinTechAgent` | `fintech-agent` | `FinTechAgentAdapter` | Read-only | 0.15 |
| `HealthTechAgent` | `healthtech-agent` | `HealthTechAgentAdapter` | Read-only (strict) | 0.1 |
| `LegalTechAgent` | `legaltech-agent` | `LegalTechAgentAdapter` | Read-only | 0.15 |
| `ECommerceAgent` | `ecommerce-agent` | `ECommerceAgentAdapter` | Unrestricted | 0.25 |
| `IndustryTechAgent` | `industrytech-agent` | `IndustryTechAgentAdapter` | Read + Commands | 0.2 |

**Adapter-Architektur (`head_agent_adapter.py`):**

```
_BASE_WRITE_DENY (frozenset)        ← Modul-Konstante: 6 verbotene Tools
     │
_ReadOnlyAgentAdapterMixin          ← Mixin: _build_read_only_policy()
     │
_BaseSpecialistAdapter(AgentContract) ← Gemeinsames Scaffold:
     │                                   name, configure_runtime, run(),
     │                                   normalize_tool_policy() → No-Op-Default
     │
     ├── HeadAgentAdapter            ← Unrestricted
     ├── CoderAgentAdapter           ← Unrestricted, output_schema=CoderAgentOutput
     ├── ReviewAgentAdapter(Mixin)   ← Read-only + _has_review_evidence() Guard
     ├── ResearcherAgentAdapter(Mixin) ← Read-only, max_context=16384
     ├── ArchitectAgentAdapter(Mixin)  ← Read-only, reflection=2, depth=4
     ├── TestAgentAdapter            ← _BASE_WRITE_DENY - {run_command, code_execute}
     ├── SecurityAgentAdapter(Mixin) ← _BASE_WRITE_DENY - {run_command}
     ├── DocAgentAdapter             ← No apply_patch/run_command/code_execute
     ├── RefactorAgentAdapter        ← Unrestricted (full access)
     ├── DevOpsAgentAdapter          ← Unrestricted (full access)
     ├── FinTechAgentAdapter(Mixin)  ← Read-only, depth=4, max_context=16384
     ├── HealthTechAgentAdapter(Mixin) ← Read-only (strictest), depth=4
     ├── LegalTechAgentAdapter(Mixin)  ← Read-only, depth=3, max_context=12288
     ├── ECommerceAgentAdapter       ← Unrestricted
     └── IndustryTechAgentAdapter    ← _BASE_WRITE_DENY - {run_command, code_execute}
```

**Injizierte Komponenten im Konstruktor:**

| Komponente | Typ | Funktion |
|-----------|-----|----------|
| `client` | `LlmClient` | LLM-Kommunikation |
| `memory` | `MemoryStore` | Session-Memory (JSONL) |
| `tools` | `ToolProvider` Protocol | Tooling (AgentTooling) |
| `model_registry` | `ModelRegistry` | Modell-Profile |
| `spawn_subrun_handler` | `Callable` | Subrun-Delegation |
| `policy_approval_handler` | `Callable` | Human-in-the-Loop |
| `agent_record` | `UnifiedAgentRecord` | Agent-Konfiguration (Constraints, Tools, Capabilities) |

**Intern erzeugter AgentRunner:**

```python
def _build_sub_agents(self):
    system_prompt = build_unified_system_prompt(
        role=self.role,
        tool_hints=self.prompt_profile.tool_selector_prompt,
        final_instructions=self.prompt_profile.final_prompt,
        platform_summary=..., agent_roster=..., capability_section=...,
    )
    self._agent_runner = AgentRunner(
        client=self.client, memory=self.memory,
        tool_registry=self.tool_registry,
        tool_execution_manager=self._tool_execution_manager,
        system_prompt=system_prompt,
        execute_tool_fn=self._runner_execute_tool,
        allowed_tools_resolver=self._resolve_effective_allowed_tools,
        reflection_service=self._reflection_service,
        verification_service=self._verification,
        reply_shaper=self._reply_shaper,
        max_reflections=self._agent_record.constraints.reflection_passes
            if self._agent_record else None,
        # ... 10+ weitere Dependency-Injection-Punkte
    )
```

**Intern erzeugte Services:**

| Service | Konfiguration |
|---------|-------------|
| `SkillsService` | `SkillsRuntimeConfig(enabled, skills_dir, max_discovered, max_prompt_chars, cache_ttl)` |
| `IntentDetector` | Stateless, Keyword-basiert |
| `ActionParser` | Multi-Stage JSON Recovery |
| `ActionAugmenter` | Intent-gesteuerte Argument-Erweiterung |
| `AmbiguityDetector` | Minimal: nur Empty + Pronoun |
| `ReplyShaper` | Deduplizierung, Tool-Marker-Entfernung, Suppression |
| `VerificationService` | Final Verifikation (nur `verify_final`) |
| `CompactionService` | LLM-basierte Kontext-Komprimierung (ersetzt ContextReducer) |
| `ReflectionService` (optional) | LLM-basierte Qualitätsbewertung |
| `ToolExecutionManager` | Zentraler Tool-Dispatcher |
| `ToolArgValidator` | Argument-Validierung + Command-Policy |
| `ToolRegistry` | Tool-Metadaten + Dispatch-Mapping |
| `ToolRetryStrategy` | Fehler-Taxonomie + Retry-Entscheidung |
| `ToolOutcomeVerifier` | Deterministische Tool-Ergebnisprüfung |
| `ToolTelemetry` | Span-Tracking + Per-Tool-Statistiken |
| `LearningLoop` | Tool-Outcome-Feedback (Selector, KB, Patterns) |

### 5.2 Continuous Streaming Tool Loop (`AgentRunner`)

> **Neu in v1.5.** Ersetzt die alte 11-Phasen-Pipeline (Planner → ToolSelector → Synthesizer) durch einen **kontinuierlichen Streaming-Loop**. Das LLM entscheidet autonom, wann Tools verwendet und wann direkt geantwortet wird. Aktiviert via `USE_CONTINUOUS_LOOP=true`.

**Implementierung:** `agent_runner.py` (~1341 Zeilen), Typen in `agent_runner_types.py`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        AgentRunner.run()                                  │
│                                                                          │
│  PRE-LOOP     INIT            Guardrails, MCP-Init, Tool-Resolution,     │
│     │                         Memory-Add, Orphan-Repair,                 │
│     │                         _build_initial_messages()                   │
│     ▼                                                                    │
│  CONTINUOUS   STREAMING LOOP  while not budget_exhausted:                │
│  LOOP            │              stream_chat_with_tools() → StreamResult   │
│     │            │                                                       │
│     │            ├── finish_reason == "stop"                              │
│     │            │     → LLM hat geantwortet → EXIT LOOP                 │
│     │            │                                                       │
│     │            ├── finish_reason == "tool_calls"                        │
│     │            │     → Blocked-Tool-Check (allowed_tools)              │
│     │            │     → Policy-Approval-Check                           │
│     │            │     → Tool-Ausführung via execute_tool_fn             │
│     │            │     → Tool-Ergebnisse an Messages anhängen            │
│     │            │     → Continue Loop                                   │
│     │            │                                                       │
│     │            ├── Tool-Loop-Detection (_detect_tool_loop)             │
│     │            │     Identische/Ping-Pong-Calls × 3 → Warning inject  │
│     │            │                                                       │
│     │            └── Steer-Interrupt-Check → Early Exit                  │
│     ▼                                                                    │
│  POST-LOOP    QUALITY GATES   Reflection (max_reflections per Agent),    │
│     │                         Evidence Gates (Implementation/Orchestr.), │
│     │                         Reply Shaping, Final Verification          │
│     ▼                                                                    │
│  FINALIZE     PERSIST         Memory-Persist, Session-Distillation       │
│                               (LTM), Lifecycle Events                    │
└──────────────────────────────────────────────────────────────────────────┘
```

#### PRE-LOOP: Init

```python
async def run(self, user_message, send_event, session_id, request_id,
              model=None, tool_policy=None, should_steer_interrupt=None) -> str:
    # 1. Guardrails (via guardrail_validator callback)
    # 2. MCP-Init (via mcp_initializer callback)
    # 3. Tool-Resolution: allowed_tools_resolver(tool_policy) → set[str]
    # 4. Memory: memory.add(), repair_orphaned_tool_calls()
    # 5. Messages: _build_initial_messages(memory_items, user_message)
    # 6. Tool-Definitionen: tool_registry.build_function_calling_tools(allowed_tools)
```

#### CONTINUOUS LOOP

```python
loop_state = LoopState()
while not loop_state.budget_exhausted:
    loop_state.iteration += 1
    if loop_state.iteration > self._max_iterations: break    # Safety
    if elapsed > self._time_budget_seconds: break            # Time budget
    if should_steer_interrupt and should_steer_interrupt(): break  # Steer

    result: StreamResult = await client.stream_chat_with_tools(
        messages=messages, tools=tool_definitions, model=model
    )

    if result.finish_reason == "stop":
        final_text = result.text
        break

    if result.finish_reason == "tool_calls":
        for tool_call in result.tool_calls:
            if tool_call.name not in effective_allowed_tools:
                # → Blocked-Fehlermeldung als Tool-Result
            elif requires_policy_approval(tool_call):
                # → Policy-Approval-Flow
            else:
                tool_result = await execute_tool_fn(tool_call.name, tool_call.arguments, ...)
            messages.append(tool_result_message)
```

**Safety-Mechanismen:**
- `runner_max_iterations` (Default aus Settings) — Maximale Loop-Iterationen
- `runner_time_budget_seconds` — Maximale Laufzeit
- `runner_max_tool_calls` — Maximale Tool-Aufrufe insgesamt
- `_detect_tool_loop()` — Erkennt identische Wiederholungen (Threshold=3) und Ping-Pong-Muster

**Kontext-Management:**
- `_compact_messages()` — Kürzt alte Tool-Results wenn Messages zu groß werden
- `CompactionService` — LLM-basierte Zusammenfassung älterer Konversationsabschnitte (Fallback: einfache Truncation)

#### POST-LOOP: Quality Gates

```python
# Reflection (per-Agent konfigurierbar)
max_passes = self._max_reflections or settings.runner_reflection_max_passes
for pass_idx in range(max_passes):
    verdict = await reflection_service.reflect(
        user_message=user_message, plan_text="",
        tool_results=all_tool_results, final_answer=final_text,
        model=model, task_type=task_type
    )
    if not verdict.should_retry: break
    # → Re-Stream mit Reflection-Feedback

# Evidence Gates
if requires_implementation_evidence and not has_implementation_evidence(tool_results):
    final_text = "I could not complete the implementation..."
if task_type == "orchestration" and not has_orchestration_evidence(tool_results):
    final_text = "The delegated subrun did not complete successfully..."

# Reply Shaping + Final Verification
shape_result = reply_shaper.shape(raw_response=final_text, tool_results=..., ...)
final_verification = verification_service.verify_final(user_message=..., final_text=...)
```

**Budget Exhaustion Fallback:** Wenn `max_iterations` erreicht wird, erzwingt `_handle_budget_exhaustion()` eine finale Antwort via separaten LLM-Call mit gesammeltem Kontext.

#### FINALIZE

```python
memory.add(session_id, "assistant", final_text)
await send_event({"type": "final", "agent": agent_name, "message": final_text})
# Session-Distillation: LLM extrahiert Fakten für LongTermMemoryStore
# Failure Journal: Bei Exceptions → FailureEntry in LTM
```

#### build_unified_system_prompt()

Erzeugt einen einzigen System-Prompt (kein separater Plan/Tool/Synthese-Prompt mehr):

```python
def build_unified_system_prompt(*, role, tool_hints, final_instructions,
    guardrails="", platform_summary="", current_datetime="",
    reasoning_hint="", agent_roster="", capability_section="") -> str:
    # Sections: Identity → DateTime → Working Style → Capabilities →
    # Agent Roster → Web Search Guidelines → Tool Guidelines →
    # Answer Guidelines → Platform → Safety → Reasoning
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
    "orchestration": 0.60,  "orchestration_failed": 0.55,
    "orchestration_pending": 0.55,  "general": 0.35,  "trivial": 0.40,
}
```

**Reflection-Passes** sind jetzt **per-Agent konfigurierbar** über `UnifiedAgentRecord.constraints.reflection_passes` → `AgentRunner._max_reflections`, Fallback auf `settings.runner_reflection_max_passes`.

**Evidence Gates** verhindern Halluzination bei Code-/Orchestration-Aufgaben:
- **Implementation:** Prüft ob `write_file`, `apply_patch`, `run_command` oder `code_execute` erfolgreich war
- **Orchestration:** Prüft ob `spawn_subrun` mit `terminal_reason=subrun-complete` vorhanden

### 5.3 UnifiedAgentRecord & Constraints

> **Neu in v1.5.** Ersetzt die separaten `PlannerAgent`, `ToolSelectorAgent`, `SynthesizerAgent` Sub-Agents durch ein einheitliches `UnifiedAgentRecord`-Modell.

15 Agent-Typen werden über `UnifiedAgentRecord` (Pydantic-Modell in `agents/unified_agent_record.py`) konfiguriert:

```python
class UnifiedAgentRecord(BaseModel):
    agent_id: str
    origin: Literal["builtin", "custom"]
    display_name: str
    category: Literal["core", "specialist", "industry", "custom"]
    role: str
    reasoning_strategy: str        # "plan_execute" | "breadth_first" | "depth_first" | "verify_first"
    specialization: str
    capabilities: list[str]
    constraints: ConstraintSpec
    tool_policy: ToolPolicySpec
    prompts: PromptSpec
    delegation: DelegationSpec
    behavior: BehaviorFlags

class ConstraintSpec(BaseModel):
    temperature: float = 0.3       # 0.0–2.0
    reflection_passes: int = 0     # → AgentRunner._max_reflections
    reasoning_depth: int = 2       # → ModelRouter Scoring
    max_context: int | None = None # ≥ 256
    combine_steps: bool = False

class ToolPolicySpec(BaseModel):
    read_only: bool = False
    mandatory_deny: list[str]      # Immer verbotene Tools
    preferred_tools: list[str]     # Bevorzugte Tools
    forbidden_tools: list[str]     # Zusätzlich verbotene Tools
```

**15 builtin Agents** (definiert in `agents/factory_defaults.py`):

| Agent-ID | Kategorie | Temp | Reflection | Reasoning | Read-Only |
|----------|-----------|------|------------|-----------|-----------|
| `head-agent` | core | 0.3 | 0 | 2 | Nein |
| `coder-agent` | core | 0.3 | 0 | 2 | Nein |
| `review-agent` | core | 0.2 | 1 | 2 | Ja |
| `researcher-agent` | specialist | 0.25 | 0 | 2 | Ja |
| `architect-agent` | specialist | 0.35 | 2 | 4 | Ja |
| `test-agent` | specialist | 0.15 | 0 | 2 | Teilweise |
| `security-agent` | specialist | 0.1 | 0 | 2 | Teilweise |
| `doc-agent` | specialist | 0.4 | 0 | 2 | Teilweise |
| `refactor-agent` | specialist | 0.2 | 0 | 2 | Nein |
| `devops-agent` | specialist | 0.2 | 0 | 2 | Nein |
| `fintech-agent` | industry | 0.15 | 0 | 4 | Ja |
| `healthtech-agent` | industry | 0.1 | 0 | 4 | Ja |
| `legaltech-agent` | industry | 0.15 | 0 | 3 | Ja |
| `ecommerce-agent` | industry | 0.25 | 0 | 2 | Nein |
| `industrytech-agent` | industry | 0.2 | 0 | 2 | Teilweise |

**AgentStore** (`agents/agent_store.py`) verwaltet builtin + custom Agents und stellt die Registry bereit.

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

Rekursive Agent-Delegation mit Tiefenbegrenzung und **Multi-Agency-Integration**:

```python
class SubrunLane:
    def __init__(self, max_concurrent, max_spawn_depth, max_children_per_parent, ...):
        self._semaphore = asyncio.Semaphore(max_concurrent)  # Default: 2
        self._max_spawn_depth = max_spawn_depth              # Default: 2
        self._max_children_per_parent = max_children_per_parent  # Default: 5
        self._coordination_bridge = None  # Multi-Agency CoordinationBridge

    def set_coordination_bridge(self, bridge):
        """Attach CoordinationBridge for confidence-based routing on completion."""
        self._coordination_bridge = bridge

    async def spawn(self, parent_request_id, parent_session_id, user_message,
                    runtime, model, timeout_seconds, tool_policy, send_event,
                    agent_id, mode, preset, orchestrator_agent_ids, orchestrator_api):
        # 1. Tiefe prüfen (max_spawn_depth)
        # 2. Kinder-Limit prüfen (max_children_per_parent)
        # 3. Semaphore erwerben
        # 4. orchestrator_api.run_user_message(message, ..., request_context)
        # 5. Bei Completion: CoordinationBridge.on_subrun_completed() → Confidence-Evaluation
        # 6. Confidence-Decision an handover_contract anhängen
        # 7. Ergebnis zurückgeben oder Timeout
```

**Spawn-Hierarchie:**
```
Root Run (depth=0)
  └── Subrun A (depth=1)
        ├── Subrun A.1 (depth=2) ← max_spawn_depth erreicht
        └── Subrun A.2 (depth=2)
  └── Subrun B (depth=1)
```

**Multi-Agency-Integration:** Wenn ein `CoordinationBridge` angehängt ist, wird nach dem Completion-Callback jeder Subrun-Abschluss durch `bridge.on_subrun_completed()` evaluiert. Die Confidence-Entscheidung (accept/review/redelegate/reject) wird am `handover_contract` als `confidence_decision` angehängt und fliesst in `agent.py` in die Handover-Auswertung ein.

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

### 8.4 CompactionService

> **Neu in v1.5.** Ersetzt die entfernte `ContextReducer`-Klasse (`state/context_reducer.py`).

LLM-basierte Kontext-Komprimierung mit progressiver Fallback-Chain:

```python
class CompactionService:
    """Summarises old conversation segments to keep context within budget."""
    # Verwendet von AgentRunner._compact_messages()

    # Fallback-Chain:
    # 1. LLM-basierte Zusammenfassung (beste Qualität)
    # 2. Text-basierte Extraktion (Headings + Identifiers)
    # 3. Einfache Truncation (Fallback)
```

**Konfiguration (über Settings):**
- `runner_compaction_enabled` — Komprimierung aktivieren
- `runner_compaction_tail_keep` — Anzahl neuester Messages die nicht komprimiert werden

**Identifier-Erhaltung:** UUIDs, Hashes, Dateipfade, URLs werden bei der Zusammenfassung erhalten (via `IDENTIFIER_RE` Regex).

**Trigger:** Komprimierung wird ausgelöst wenn die geschätzte Token-Nutzung `COMPACTION_TRIGGER_RATIO` (85%) des Context-Windows überschreitet.

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

Deterministische Qualitätsprüfung der finalen Antwort (ohne LLM):

```python
class VerificationService:
    def verify_final(self, *, user_message, final_text) -> VerificationResult: ...
```

> **v1.5:** `verify_plan()`, `verify_plan_semantically()` und `verify_tool_result()` wurden entfernt (Relikte der alten 3-Phasen-Pipeline). Nur `verify_final()` bleibt — prüft ob die finale Antwort leer oder zu kurz ist.

```python
@dataclass(frozen=True)
class VerificationResult:
    status: str       # "ok" | "warning" | "failed"
    reason: str       # "final_acceptable" | "final_too_short" | "empty_final"
    details: dict
```

### 8.7 ReplyShaper

Post-Processing der finalen Antwort:

```python
class ReplyShaper:
    def sanitize(self, final_text) -> str:
        # Entfernt [TOOL_CALL]...[/TOOL_CALL] Blöcke
        # Entfernt {tool => ...} Pattern
        # Komprimiert übermäßige Newlines

    def shape(self, raw_response, tool_results, *,
              final_text, tool_markers) -> ReplyShapeResult:
        # Dedupliziert wiederholte Tool-Confirmations
        # Entfernt Tool-Marker-Leaks
        # Leere Texte nach Shaping → suppression_reason="empty_after_shaping"
```

> **v1.5:** `NO_REPLY`/`ANNOUNCE_SKIP` Token-Stripping und `user_message`-Parameter wurden entfernt (Relikte der alten Synthesizer-Phase).

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

**Mitgelieferte Skills (11 SKILL.md-Dateien):**

| Skill-Verzeichnis | Beschreibung |
|---|---|
| `git-workflow/` | Git-Workflow-Best-Practices |
| `code-review-checklist/` | Code-Review-Checkliste |
| `test-generation/` | Test-Generierungs-Patterns |
| `api-design-patterns/` | REST-API-Design-Standards |
| `python-best-practices/` | Python-Idiome & Best Practices |
| `error-diagnosis/` | Fehlerdiagnose & Debugging |
| `fintech-compliance/` | FinTech-Regulatorik (PSD2, PCI-DSS) |
| `healthtech-compliance/` | HealthTech-Regulatorik (HIPAA, MDR) |
| `legaltech-compliance/` | LegalTech-Regulatorik (DSGVO, CCPA) |
| `ecommerce-patterns/` | E-Commerce-Patterns (Cart, Checkout) |
| `industrytech-iot/` | IndustryTech/IoT-Patterns (OPC UA, Edge) |

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

## 12. Multi-Agency-Subsystem

> **Neu in v1.2.** Echte Multi-Agent-Koordination jenseits des bisherigen parametrisierten Single-Agent-Modells.

### 12.1 Architektur-Überblick

Das Multi-Agency-Subsystem (`app/multi_agency/`) ersetzt das bisherige Hub-and-Spoke-Modell (gleicher Code, unterschiedliche Prompts) durch echte strukturelle Differenzierung zwischen Agents und deterministische Koordination:

```
┌──────────────────────────────────────────────────────────────────┐
│                     CoordinationBridge                           │
│              (Integration Layer → SubrunLane / Agent)            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│  │   Supervisor     │  │  Confidence      │  │  Consensus     │   │
│  │   Coordinator    │  │  Router          │  │  Engine        │   │
│  │                  │  │                  │  │                │   │
│  │  Task Decomp.    │  │  Handover Eval.  │  │  5 Strategies  │   │
│  │  Capability Fit  │  │  History Learn.  │  │  Conflict Res. │   │
│  │  Quality Gates   │  │  Quality Gates   │  │  Result Merge  │   │
│  │  Re-Delegation   │  │  Re-Delegation   │  │  Quorum        │   │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬───────┘   │
│           │                     │                     │           │
│  ┌────────▼─────────────────────▼─────────────────────▼───────┐   │
│  │                    Shared Infrastructure                   │   │
│  │                                                            │   │
│  │  ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐   │   │
│  │  │  Blackboard   │  │  Message Bus│  │  Agent Registry  │   │   │
│  │  │  (Shared      │  │  (Direct +  │  │  (Identity Cards │   │   │
│  │  │   State)      │  │   Pub/Sub)  │  │   + Capabilities)│   │   │
│  │  └──────────────┘  └─────────────┘  └──────────────────┘   │   │
│  │                                                            │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │  ParallelFanOutExecutor (DAG + Race + Quorum)       │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**Kern-Unterscheidung zum alten Modell:**

| Aspekt | Alt (v1.1) | Neu (v1.2) |
|--------|-----------|-----------|
| Agent-Differenzierung | Gleicher Code, anderes Prompt | Distinct IdentityCards mit Capabilities, Tools, Reasoning |
| Koordination | LLM entscheidet alles | Supervisor mit deterministischer Arbeitsverteilung |
| Kommunikation | Nur über Parent-Memory | Direkte Agent-zu-Agent-Messages + Blackboard |
| Confidence | Serialisiert, nie evaluiert | ConfidenceRouter mit Routing-Entscheidungen |
| Execution | Sequentiell | Parallel DAG, Fan-Out/Fan-In, Race, Quorum |
| Konfliktlösung | Keine | ConsensusEngine mit 5 Voting-Strategien |
| State Sharing | Implicit via Memory | Explizit via Blackboard mit Provenance |

### 12.2 Blackboard (`multi_agency/blackboard.py`)

Shared-State-System mit Provenance-Tracking, sichtbar für alle Agents einer Session:

```python
class Blackboard:
    async def write(*, section, key, value, author_agent_id, confidence, tags) -> BlackboardEntry
    async def read(*, section, key) -> BlackboardEntry | None
    async def read_section(section) -> dict[str, BlackboardEntry]
    async def read_by_agent(agent_id) -> list[BlackboardEntry]
    async def read_history(*, section, key) -> list[BlackboardEntry]
    async def get_conflicts() -> list[ConflictRecord]
    def watch(*, section, key, callback)      # Key-spezifisch
    def watch_all(callback)                    # Alle Änderungen
    async def snapshot() -> dict[str, Any]     # Serialisierbar
```

**Features:**
- **Sections:** Logische Gruppierung (z.B. `"plan"`, `"results"`, `"assignments"`)
- **Provenance:** Jeder Eintrag hat `author_agent_id`, `timestamp`, `entry_id`
- **Versioning:** Auto-inkrementierende Version pro Key, `supersedes`-Referenz
- **Conflict Detection:** Erkennt Schreibkonflikte innerhalb eines 2-Sekunden-Fensters
- **Watchers:** Async Callbacks bei Änderungen (key-spezifisch oder global)

### 12.3 Agent Message Bus (`multi_agency/agent_message_bus.py`)

Direkte Agent-zu-Agent-Kommunikation als Ersatz für die Hub-and-Spoke-Parent-Memory-Kommunikation:

```python
class AgentMessageBus:
    async def register_agent(agent_id)
    async def send(*, sender, recipient, payload, message_type, priority)
    async def request(*, sender, recipient, payload, timeout) -> AgentMessage | None  # RPC
    async def reply(*, original_message, sender, payload)
    async def subscribe(agent_id, topic)
    async def publish(*, sender, topic, payload)
    async def receive(agent_id) -> AgentMessage | None         # Non-blocking
    async def receive_wait(agent_id, timeout) -> AgentMessage | None  # Blocking
```

**Message-Typen:** `DIRECT`, `BROADCAST`, `REQUEST`, `REPLY`, `TOPIC`, `COORDINATION`, `RESULT`, `HEARTBEAT`

**Priority-System:** `URGENT` → Front der Queue, `HIGH` → nach URGENT, `NORMAL`/`LOW` → FIFO

**Dead Letter Queue:** Unzustellbare Nachrichten (unbekannter Recipient, voller Mailbox) landen in `_dead_letter_queue`

### 12.4 Agent Identity (`multi_agency/agent_identity.py`)

Echte strukturelle Differenzierung zwischen Agents (nicht nur Prompt-Unterschiede):

```python
@dataclass(frozen=True)
class AgentIdentityCard:
    agent_id: str
    role: AgentRole              # COORDINATOR | SPECIALIST | REVIEWER | RESEARCHER | ...
    reasoning_strategy: str      # BREADTH_FIRST | DEPTH_FIRST | VERIFY_FIRST | PLAN_EXECUTE | ...
    capability_profile: AgentCapabilityProfile
    confidence_threshold: float
    delegation_preference: str   # "eager" | "selective" | "reluctant"
```

**Vordefinierte Agents (15 IdentityCards in `DEFAULT_AGENT_IDENTITIES`):**

| Agent | Rolle | Reasoning | Key Capabilities | Delegation |
|-------|-------|-----------|-----------------|------------|
| `head-agent` | Coordinator | Plan-Execute | coordination, delegation, synthesis | Eager |
| `coder-agent` | Specialist | Depth-First | code_reasoning, debugging, testing | Reluctant |
| `review-agent` | Reviewer | Verify-First | review_analysis, security_review | Reluctant |
| `researcher-agent` | Researcher | Breadth-First | web_retrieval, fact_checking | Reluctant |
| `architect-agent` | Specialist | Breadth-First | system_design, architecture_review | Selective |
| `test-agent` | Specialist | Verify-First | test_generation, test_strategy | Reluctant |
| `security-agent` | Reviewer | Verify-First | security_audit, vulnerability_analysis | Reluctant |
| `doc-agent` | Specialist | Plan-Execute | documentation, api_docs | Reluctant |
| `refactor-agent` | Specialist | Depth-First | code_restructuring, pattern_application | Reluctant |
| `devops-agent` | Specialist | Plan-Execute | ci_cd, infrastructure, deployment | Selective |
| `fintech-agent` | Specialist | Verify-First | compliance_psd2, payment_systems | Reluctant |
| `healthtech-agent` | Specialist | Verify-First | hipaa_compliance, medical_data | Reluctant |
| `legaltech-agent` | Specialist | Verify-First | gdpr_compliance, legal_analysis | Reluctant |
| `ecommerce-agent` | Specialist | Plan-Execute | cart_checkout, catalog_management | Selective |
| `industrytech-agent` | Specialist | Depth-First | iot_protocols, edge_computing | Reluctant |

**AgentRegistry:** Runtime-Discovery, Lookup by Role/Capability, `find_best_match()` für optimales Agent-Matching.

### 12.5 Confidence Router (`multi_agency/confidence_router.py`)

Evaluiert Handover-Contracts und trifft echte Routing-Entscheidungen basierend auf Confidence-Scores:

```python
class ConfidenceRouter:
    def evaluate_handover(*, handover_contract, source_agent_id, task_description) -> ConfidenceRouteDecision
    def route_by_confidence(*, required_capabilities, preferred_quality) -> ConfidenceRouteDecision
    def record_outcome(*, agent_id, task_description, confidence, outcome)
```

**Entscheidungslogik:**

| Adjusted Score | Action | Beschreibung |
|---------------|--------|-------------|
| ≥ 0.7 | `accept` | Ergebnis angenommen |
| ≥ 0.5 | `review` | An Review-Agent weiterleiten |
| ≥ 0.3 | `redelegate` | An alternativen Agent delegieren |
| < 0.3 | `reject` | Ergebnis verworfen |

**Score-Faktoren:** Raw Confidence × (1 − history_weight) + Historical Confidence × history_weight, mit Penalties für `subrun-error`/`subrun-timeout` (×0.3) und `synthesis_valid=False` (×0.5).

### 12.6 Supervisor Coordinator (`multi_agency/supervisor.py`)

Deterministische Arbeitsverteilung — ersetzt LLM-gesteuerte Delegations-Entscheidungen:

```python
class SupervisorCoordinator:
    async def create_session(session_id, strategy) -> CoordinationSession
    async def decompose_and_assign(*, session_id, task_descriptions) -> list[SupervisorDecision]
    async def report_result(*, session_id, task_id, result, confidence, agent_id) -> SupervisorDecision
    async def cancel_task(session_id, task_id, reason)
    async def get_session_status(session_id) -> dict
```

**Workflow:**
1. **Task Decomposition:** Eingehende Tasks mit `required_capabilities` annotiert
2. **Capability Matching:** `AgentRegistry` findet den besten Agent (Score = matched/required)
3. **Overload-Check:** Wenn Agent an `max_concurrent_tasks`, nächstbester Agent gewählt
4. **Blackboard-Logging:** Jede Zuweisung und Re-Delegation wird auf das Blackboard geschrieben
5. **Quality Gate:** `report_result()` prüft Confidence gegen Thresholds
6. **Re-Delegation:** Bei Confidence < `re_delegation_threshold` → anderer Agent, maximal `max_retries`

**Strategien:** `SEQUENTIAL`, `PARALLEL`, `PIPELINE`, `COMPETITIVE`, `HIERARCHICAL`

### 12.7 Parallel Fan-Out Executor (`multi_agency/parallel_executor.py`)

Ersetzt die sequentielle PlanGraph-Ausführung durch echte parallele DAG-Execution:

```python
class ParallelFanOutExecutor:
    async def fan_out(*, tasks, mode, timeout) -> FanOutResult
    async def execute_dag(*, steps: list[DAGStep], timeout) -> list[dict]
```

**Fan-Out-Modi:**

| Modus | Verhalten |
|-------|-----------|
| `ALL` | Wartet auf alle Agents, gibt höchste Confidence zurück |
| `RACE` | Erster fertig gewordener Agent gewinnt |
| `QUORUM` | Akzeptiert wenn N Agents übereinstimmen |
| `BEST` | Wartet auf alle, wählt höchste Confidence |

**DAG-Execution:** Steps mit erfüllten Dependencies werden parallel ausgeführt. Dependency-Ergebnisse werden via `context["dependency_results"]` injiziert. Deadlock-Detection bei unerfüllbaren Dependencies.

### 12.8 Consensus Engine (`multi_agency/consensus.py`)

Multi-Agent-Abstimmung und Konfliktlösung:

```python
class ConsensusEngine:
    def vote(*, votes, strategy, required_capabilities) -> ConsensusResult
    def merge_results(*, results, merge_strategy) -> dict
```

**Voting-Strategien:**

| Strategie | Gewichtung | Konsens-Kriterium |
|-----------|-----------|-------------------|
| `MAJORITY` | Gleich (1.0) | > 50% der Stimmen |
| `WEIGHTED_CONFIDENCE` | Nach Confidence | > 50% des Gewichts |
| `WEIGHTED_EXPERTISE` | Nach Capability-Match | > 50% des Gewichts |
| `UNANIMOUS` | Gleich (1.0) | Alle müssen übereinstimmen |
| `BEST_OF_N` | Nach Confidence | Höchste Confidence gewinnt |

**Conflict Detection:** Jaccard-Similarity auf Wort-Ebene. Similarity < `conflict_similarity_threshold` (0.8) → Conflict Record.

**Merge-Strategien:** `concatenate` (alle), `deduplicate` (unique), `best_sections` (höchste Confidence).

### 12.9 Coordination Bridge (`multi_agency/coordination_bridge.py`)

Integration Layer — verbindet das Multi-Agency-Subsystem mit der bestehenden Architektur:

```python
class CoordinationBridge:
    def __init__(self, session_id, send_event)
    async def initialize(agent_executor)
    async def on_subrun_completed(*, parent_session_id, run_id, child_agent_id, ...) -> ConfidenceRouteDecision
    def route_agent(*, required_capabilities, preferred_quality) -> ConfidenceRouteDecision
    async def assign_tasks(tasks) -> list[SupervisorDecision]
    async def execute_plan_parallel(steps, timeout) -> list[dict]
    async def fan_out(tasks, mode, timeout) -> FanOutResult
    async def vote_on_results(results, strategy) -> ConsensusResult
    async def send_agent_message(*, sender, recipient, payload)
    async def request_from_agent(*, sender, recipient, payload, timeout)
```

**7 Integrationspunkte:**

1. **SubrunLane Completion** → `on_subrun_completed()` evaluiert Confidence, schreibt auf Blackboard
2. **Agent Routing** → `route_agent()` mit historischer Confidence-Gewichtung
3. **Task Assignment** → `assign_tasks()` via Supervisor mit Capability Matching
4. **Parallel DAG** → `execute_plan_parallel()` ersetzt sequentiellen PlanGraph
5. **Fan-Out** → `fan_out()` für parallele Agent-Ausführung
6. **Consensus** → `vote_on_results()` für Multi-Agent-Abstimmung
7. **Agent Messaging** → `send_agent_message()` / `request_from_agent()` für direkte Kommunikation

**Blackboard-Watcher:** Reagiert automatisch auf `"results"` Section-Einträge und leitet Task-Ergebnisse an den Supervisor weiter.

---

## 13. Contract-System

Alle Schicht-Grenzen sind durch **Protocol-basierte Interfaces** definiert (kein Tight Coupling):

### 13.1 AgentContract

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

### 13.2 ToolProvider Protocol

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

### 13.3 Agent Schemas (`contracts/schemas.py`)

```python
class AgentInput(BaseModel):
    user_message: str
    session_id: str
    request_id: str
    model: str | None = None
    tool_policy: ToolPolicyDict | None = None

HeadAgentInput = AgentInput
CoderAgentInput = AgentInput

class HeadAgentOutput(BaseModel):
    final_text: str

class CoderAgentOutput(BaseModel):
    final_text: str
```

> **v1.5:** Die alten Pipeline-Schemas (`PlannerInput/Output`, `ToolSelectorInput/Output`, `SynthesizerInput/Output`) und das `ToolSelectorRuntime` Protocol wurden entfernt. Die Continuous-Loop-Architektur nutzt direkte Parameter statt typisierter Schema-Objekte.

### 13.4 RequestContext

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

## 14. Konfiguration

### 14.1 Settings-Klasse (`config.py`)

~230 Felder als Pydantic `BaseModel`, alle über Umgebungsvariablen steuerbar:

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
| `multi_agency_enabled` | `False` | Multi-Agency-Koordination (CoordinationBridge in SubrunLane) |
| `capability_routing_enabled` | `True` | Capability-basiertes Agent-Routing (15 Agenten) |

---

## 15. Startup & Shutdown

### 15.1 Startup-Sequenz (`startup_tasks.py`)

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

### 15.2 Shutdown-Sequenz

```python
def run_shutdown_sequence(*, active_run_tasks, logger):
    for _, task in list(active_run_tasks.items()):
        if not task.done():
            task.cancel()
    active_run_tasks.clear()
```

### 15.3 App-Lifespan

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

### 15.4 main.py — Wiring

`main.py` ist die **Composition Root** — alle Abhängigkeiten werden hier verdrahtet:

```python
app = build_fastapi_app(title="AI Agent Starter Kit", settings=settings)

# Agents (15 IDs)
PRIMARY_AGENT_ID = "head-agent"
CODER_AGENT_ID = "coder-agent"
REVIEW_AGENT_ID = "review-agent"
RESEARCHER_AGENT_ID = "researcher-agent"
ARCHITECT_AGENT_ID = "architect-agent"
TEST_AGENT_ID = "test-agent"
SECURITY_AGENT_ID = "security-agent"
DOC_AGENT_ID = "doc-agent"
REFACTOR_AGENT_ID = "refactor-agent"
DEVOPS_AGENT_ID = "devops-agent"
FINTECH_AGENT_ID = "fintech-agent"
HEALTHTECH_AGENT_ID = "healthtech-agent"
LEGALTECH_AGENT_ID = "legaltech-agent"
ECOMMERCE_AGENT_ID = "ecommerce-agent"
INDUSTRYTECH_AGENT_ID = "industrytech-agent"

# Control Plane
control_plane_state = ControlPlaneState()
idempotency_mgr = IdempotencyManager(ttl_seconds=..., max_entries=...)

# Router Wiring
include_control_routers(app, run_start_handler=..., sessions_list_handler=..., ...)

# Runtime Components (Lazy)
# → 15 Agents (HeadAgent..IndustryTechAgent) via base_agent_registry
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

## 16. Datenfluss: Request Lifecycle (End-to-End)

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
   │       → "head-agent" | "coder-agent" | … | "industrytech-agent" (15 Agenten)
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

## 17. Concurrency-Modell

### 17.1 Architektur

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

### 17.2 Guards

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

### 17.3 Steer-Interrupt

```python
def should_steer_interrupt() -> bool:
    return queue_mode == "steer" and session_inbox.has_newer_than(session_id, request_id)
```

Wird in der Tool-Loop geprüft — bei `True` wird der aktuelle Run mit `steer_interrupted` beendet und die neuere Nachricht verarbeitet.

---

## 18. Fehler-Taxonomie & Recovery

### 18.1 Exception-Hierarchie

| Exception | Kategorie | Recovery |
|-----------|----------|---------|
| `GuardrailViolation` | `guardrail_violation` | Sofort-Abbruch, kein Retry |
| `PolicyApprovalCancelledError` | `policy_error` | Sofort-Abbruch |
| `ToolExecutionError` | `tool_error` | Replan möglich |
| `LlmClientError` | `llm_error` | Failover via FallbackStateMachine |
| `RuntimeSwitchError` | `runtime_error` | Benutzer informieren |
| `ClientDisconnectedError` | `client_error` | Run abbrechen, State aufräumen |

### 18.2 LLM-Failover-Recovery

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

### 18.3 Tool-Loop-Recovery

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

### 18.4 Failure Journal

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

## 19. Glossar

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
| **CompactionService** | LLM-basierte Kontext-Komprimierung (ersetzt ContextReducer) |
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
| **Blackboard** | Shared-State-System im Multi-Agency-Subsystem mit Provenance-Tracking und Conflict Detection |
| **AgentMessageBus** | Direkte Agent-zu-Agent-Kommunikation (Direct, Broadcast, Request/Reply, Pub/Sub) |
| **AgentIdentityCard** | Frozen Dataclass mit Rolle, Capabilities, Reasoning-Strategie pro Agent |
| **AgentRegistry** | Runtime-Discovery für Agent-Identitäten (Lookup by Role, Capability, Best-Match) |
| **ConfidenceRouter** | Evaluiert Handover-Confidence und trifft Routing-Entscheidungen (accept/review/redelegate/reject) |
| **SupervisorCoordinator** | Deterministische Arbeitsverteilung mit Capability-Matching und Quality Gates |
| **ParallelFanOutExecutor** | Parallele Agent-Ausführung mit Fan-Out/Fan-In, DAG, Race und Quorum Modi |
| **ConsensusEngine** | Multi-Agent-Abstimmung mit 5 Voting-Strategien und Conflict Detection |
| **CoordinationBridge** | Integration Layer zwischen Multi-Agency-Subsystem und bestehender SubrunLane/Agent-Architektur |
| **Fan-Out/Fan-In** | Pattern: Aufgabe parallel an N Agents verteilen, Ergebnisse aggregieren |
| **Quality Gate** | Confidence-basierte Prüfung ob ein Agent-Ergebnis akzeptiert, reviewed oder redelegiert wird |

---

*Erstellt aus dem tatsächlichen Quellcode des Projekts. Alle Codebeispiele, Konfigurationswerte und Architekturbeschreibungen basieren auf dem aktuellen Stand der Codebase.*
