# DDD Structure Plan — AI Agent Starter Kit Backend

> **Schritt 1 von 2** — Assessment + Zielstruktur  
> **Stand:** März 2026  
> **Scope:** Vollständige Neustrukturierung des `backend/` nach Domain-Driven Design  
> Schritt 2 (Datei-Migrationen, Import-Rewrites) erfolgt separat nach Freigabe dieses Plans.

---

## Inhaltsverzeichnis

1. [Ist-Zustand: Probleme](#1-ist-zustand-probleme)
2. [Domänen-Analyse](#2-domänen-analyse)
3. [Zielstruktur `backend/`](#3-zielstruktur-backend)
4. [Zielstruktur `backend/app/` (DDD)](#4-zielstruktur-backendapp-ddd)
5. [Monolithen-Aufteilung](#5-monolithen-aufteilung)
6. [Migrations-Mapping (Alt → Neu)](#6-migrations-mapping-alt--neu)
7. [Dependency-Regeln](#7-dependency-regeln)

---

## 1. Ist-Zustand: Probleme

### 1.1 `backend/app/` — Root-Level Chaos (27 lose Dateien)

Die `app/`-Ebene ist eine Catch-all-Ablage ohne klare Domänenzugehörigkeit:

| Datei | Problem |
|-------|---------|
| `agent.py` (~1919 Zeilen) | **Monolith** — HeadAgent mit Reasoning-Pipeline, soll in `agent/` |
| `agent_runner.py` (~1341 Zeilen) | **Monolith** — AgentRunner Tool-Loop, soll in `agent/` |
| `agent_runner_types.py` | Typen für Runner, gehört zu `agent/` |
| `ws_handler.py` (~1400 Zeilen) | **Monolith** — WebSocket-Logik, soll in `transport/` |
| `tools.py` (riesige Datei) | **Monolith** — alle Tool-Implementierungen als Mixin-Klasse |
| `tools_api_connectors.py` | Tool-Mixin ohne eigenes Modul |
| `tools_devops.py` | Tool-Mixin ohne eigenes Modul |
| `tools_multimodal.py` | Tool-Mixin ohne eigenes Modul |
| `tool_catalog.py` | Soll in `tools/` |
| `tool_policy.py` | Soll in `tools/` oder `policy/` |
| `memory.py` | MemoryStore soll in `memory/` |
| `llm_client.py` | Soll in `llm/` |
| `mcp_types.py` | Soll in `mcp/` |
| `content_security.py` | Soll in `policy/` oder `tools/` |
| `url_validator.py` | Soll in `tools/` (SSRF-Schutz) |
| `errors.py` | Soll in `shared/` |
| `models.py` | WS-Modelle, soll in `transport/` |
| `control_models.py` | API-Modelle, soll in `transport/` |
| `control_router_wiring.py` | Gehört zu `transport/` |
| `run_endpoints.py` | Gehört zu `transport/routers/` |
| `subrun_endpoints.py` | Gehört zu `transport/routers/` |
| `runtime_debug_endpoints.py` | Gehört zu `transport/routers/` |
| `startup_tasks.py` | Soll in `transport/` |
| `app_setup.py` | Soll in `transport/` |
| `app_state.py` | Soll in `transport/` |
| `runtime_manager.py` | Soll in `transport/` oder `llm/` |
| `policy_store.py` | Soll in `policy/` |

### 1.2 `services/` — Dumping Ground (60+ Dateien ohne Sub-Domains)

`services/` enthält sechs logisch völlig verschiedene Domänen gemischt:

| Echte Domäne | Dateien in `services/` |
|--------------|----------------------|
| **Tool-Execution** | `tool_execution_manager.py`, `tool_call_gatekeeper.py`, `tool_arg_validator.py`, `tool_retry_strategy.py`, `tool_outcome_verifier.py`, `tool_parallel_executor.py`, `tool_loop_detector.py`, `tool_result_processor.py`, `tool_result_context_guard.py` |
| **Tool-Discovery** | `tool_discovery_engine.py`, `tool_knowledge_base.py`, `tool_capability_router.py`, `tool_ecosystem_map.py`, `tool_detector.py` |
| **Tool-Provisioning** | `tool_provisioner.py`, `tool_budget_manager.py`, `tool_policy_service.py`, `tool_telemetry.py` |
| **Reasoning/Prompt** | `action_parser.py`, `action_augmenter.py`, `intent_detector.py`, `directive_parser.py`, `request_normalization.py`, `dynamic_temperature.py`, `output_parsers.py`, `reply_shaper.py`, `prompt_kernel_builder.py`, `prompt_ab_registry.py` |
| **Quality/Verification** | `reflection_service.py`, `verification_service.py`, `execution_contract.py`, `execution_pattern_detector.py`, `self_healing_loop.py`, `graceful_degradation.py` |
| **Memory/Learning** | `long_term_memory.py`, `failure_retriever.py`, `reflection_feedback_store.py`, `learning_loop.py`, `adaptive_tool_selector.py`, `plan_graph.py` |
| **Session** | `session_inbox_service.py`, `session_query_service.py`, `session_security.py`, `compaction_service.py` |
| **Security/Policy** | `state_encryption.py`, `rate_limiter.py`, `log_secret_filter.py`, `circuit_breaker.py`, `agent_isolation.py`, `policy_approval_service.py`, `provisioning_policy.py` |
| **Media** | `audio_service.py`, `audio_deps_service.py`, `vision_service.py`, `image_gen_service.py`, `pdf_service.py` |
| **Sandbox** | `code_sandbox.py`, `persistent_repl.py`, `repl_session_manager.py` |
| **Browser** | `browser_pool.py` |
| **LLM/Model** | `model_health_tracker.py` |
| **Agent** | `agent_resolution.py`, `agent_isolation.py` |
| **Monitoring** | `platform_info.py`, `environment_snapshot.py`, `visualization.py` |
| **Connectivity** | `mcp_bridge.py`, `web_search.py` |

### 1.3 `handlers/` + `routers/` — Duplizierte Schicht

`handlers/` und `routers/` erfüllen beide die HTTP-Handler-Rolle, was zu:
- Unklarer Verantwortung führt (wer macht was?)
- Drei-Ebenen-Wiring erfordert: `main.py` → `control_router_wiring.py` → `routers/` → `handlers/`
- `main.py` wird zu einem 200+-Zeilen Import-Monolithen

### 1.4 `backend/` Root — Fälschlich platzierte Verzeichnisse

| Pfad | Problem |
|------|---------|
| `backend/backend/` | **Nested duplicate** — vermutlich Migrations-Artefakt |
| `backend/frontend/` | **Frontend-Code in Backend-Root** — muss nach root |
| `backend/custom_agents/` | Agent-JSON-Configs sollen unter `data/agents/` |
| `backend/agents/` | Agent-JSON configs (nicht Code), sollen unter `data/agents/` |
| `backend/agent_configs/` | Weiterer Config-Ordner, soll in `data/` |
| `backend/generate_speech.py` | Utility-Script auf Root-Ebene, soll in `scripts/` |
| `backend/generate_tone.py` | Utility-Script auf Root-Ebene, soll in `scripts/` |
| `backend/memory_store/` | Runtime-Daten, soll unter `data/memory/` |
| `backend/state_store/` | Runtime-Daten, soll unter `data/state/` |
| `backend/piper_voices/` | Runtime-Assets, soll unter `data/assets/voices/` |
| `backend/generated_audio/` | Runtime-Output, soll unter `data/output/audio/` |

### 1.5 Naming-Konflikte

| Konflikt | Problem |
|----------|---------|
| `backend/agents/` (JSON) vs `backend/app/agents/` (Py-Code) | Gleicher Name, fundamental anderer Inhalt |
| `custom_agents/` existiert 3x (backend root, workspace root, app/) | Verwirrende Redundanz |
| `skills/` existiert 2x (backend root, `app/skills/`) | Data vs. Code gemischt |

---

## 2. Domänen-Analyse

Das System hat folgende klar trennbare Domänen:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        API / TRANSPORT                              │
│     WebSocket · REST Routers · Middleware · App Bootstrap           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                           AGENT DOMAIN                              │
│   HeadAgent · AgentRunner · AgentStore · AgentResolution            │
└──────┬──────────────┬──────────────┬──────────────┬─────────────────┘
       │              │              │              │
┌──────▼───┐  ┌───────▼──────┐  ┌───▼──────────┐  ┌▼────────────────┐
│ORCHESTR. │  │ MULTI-AGENCY │  │   WORKFLOW   │  │     SKILLS      │
│Pipeline  │  │ Coordination │  │  Engine      │  │  Discovery      │
│State M.  │  │ Supervisor   │  │  Scheduler   │  │  Eligibility    │
└────┬─────┘  └──────────────┘  └──────────────┘  └─────────────────┘
     │
┌────▼──────────────────────────────────────────────────────────────┐
│                         TOOL DOMAIN                               │
│   Catalog · Registry · Implementations · Execution · Discovery    │
│   Provisioning · Telemetry · Policy                               │
└────┬────────────────────────────────────────────────────────────┘
     │
┌────▼──────────────────────────────────────────────────────────────┐
│                     REASONING DOMAIN                              │
│   ActionParser · IntentDetector · PromptKernel · ReplyShaper      │
└────┬────────────────────────────────────────────────────────────┘
     │
┌────▼──────────────────────────────────────────────────────────────┐
│                      QUALITY DOMAIN                               │
│   Reflection · Verification · SelfHealing · GracefulDegradation   │
└────┬────────────────────────────────────────────────────────────┘
     │
┌────▼──────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                           │
│  LLM Client · Model Routing · Memory · State · Connectors        │
│  Media · Sandbox · Browser · MCP · Monitoring                    │
└───────────────────────────────────────────────────────────────────┘
     │
┌────▼──────────────────────────────────────────────────────────────┐
│                       POLICY / SECURITY                           │
│   ToolPolicy · CircuitBreaker · RateLimiter · Encryption          │
│   AgentIsolation · PolicyApproval · ContentSecurity               │
└───────────────────────────────────────────────────────────────────┘
```

---

## 3. Zielstruktur `backend/`

```
backend/
├── app/                          # Python-Anwendungscode (DDD-Struktur, siehe §4)
├── data/                         # Runtime-Datenhaltung (kein Python-Code)
│   ├── agents/                   # Agent-JSON-Configs (war: backend/agents/, agent_configs/, custom_agents/)
│   ├── memory/                   # MemoryStore JSONL-Dateien (war: backend/memory_store/)
│   ├── state/                    # SQLite + State-Snapshots (war: backend/state_store/)
│   ├── assets/
│   │   └── voices/               # Piper TTS Voices (war: backend/piper_voices/)
│   └── output/
│       └── audio/                # Generiertes Audio (war: backend/generated_audio/)
├── scripts/                      # Utility-Scripts (war: generate_speech.py, generate_tone.py auf Root)
│   ├── generate_speech.py
│   └── generate_tone.py
├── tests/                        # Alle Tests (bleibt)
├── policies/                     # Policy-YAML-Definitionen (bleibt, ist Config-Data)
├── skills/                       # Skills-YAML/Markdown (bleibt, ist Config-Data)
├── skills_synced/                # Synced Skills (bleibt)
├── monitoring/                   # Monitoring-Config (prüfen ob nötig)
├── benchmarks/                   # Benchmark-Tools (bleibt)
├── pyproject.toml
├── requirements.txt
├── requirements-test.txt
└── README.md

# ENTFERNEN / AUFLÖSEN:
# backend/backend/     → löschen (Duplikat)
# backend/frontend/    → gehört zum Workspace-Root /frontend/
# backend/custom_agents/ → nach data/agents/
```

---

## 4. Zielstruktur `backend/app/` (DDD)

```
backend/app/
│
├── main.py                            # Schlanker Entry-Point: App-Instanz + Router-Registration
│
├── config/                            # DOMAIN: Konfiguration
│   ├── __init__.py
│   ├── settings.py                    # [war: config.py] — Settings(BaseModel), ~230 Felder
│   ├── sections.py                    # [war: config_sections.py]
│   ├── service.py                     # [war: config_service.py]
│   └── overrides.py                   # Runtime-Config-Overrides
│
├── transport/                         # DOMAIN: HTTP/WebSocket Transport
│   ├── __init__.py
│   ├── app_factory.py                 # [war: app_setup.py] — build_fastapi_app(), Middleware
│   ├── app_state.py                   # [war: app_state.py] — ControlPlaneState, LazyProxies
│   ├── startup.py                     # [war: startup_tasks.py]
│   ├── runtime_manager.py             # [war: runtime_manager.py]
│   ├── ws_handler.py                  # [war: ws_handler.py] — WebSocket Handler
│   ├── ws_models.py                   # [war: models.py] — WsInboundEnvelope, WsUserMessage…
│   └── routers/
│       ├── __init__.py                # [war: routers/__init__.py + control_router_wiring.py]
│       ├── agents.py                  # [war: routers/agents.py + handlers/agent_handlers.py + handlers/agent_config_handlers.py]
│       ├── runs.py                    # [war: run_endpoints.py + routers/control_runs.py + handlers/run_handlers.py]
│       ├── sessions.py                # [war: routers/control_sessions.py + handlers/session_handlers.py]
│       ├── subruns.py                 # [war: subrun_endpoints.py + routers/subruns.py]
│       ├── tools.py                   # [war: routers/control_tools.py + routers/control_tool_config.py + handlers/tools_handlers.py + handlers/tool_config_handlers.py]
│       ├── policies.py                # [war: routers/policies.py + handlers/policy_handlers.py]
│       ├── skills.py                  # [war: handlers/skills_handlers.py]
│       ├── integrations.py            # [war: routers/control_integrations.py + handlers/integration_handlers.py]
│       ├── uploads.py                 # [war: routers/uploads.py]
│       ├── webhooks.py                # [war: routers/webhooks.py]
│       ├── workflows.py               # [war: workflows/router.py]
│       ├── config.py                  # [war: routers/control_config.py + routers/control_execution_config.py + handlers/config_handlers.py + handlers/execution_config_handlers.py]
│       ├── audio_deps.py              # [war: handlers/audio_deps_handlers.py]
│       ├── debug.py                   # [war: runtime_debug_endpoints.py + routers/runtime_debug.py]
│       └── ws_agent.py                # [war: routers/ws_agent_router.py]
│
├── agent/                             # DOMAIN: Agent (Kern-Domäne)
│   ├── __init__.py
│   ├── head_agent.py                  # [war: agent.py] — HeadAgent
│   ├── runner.py                      # [war: agent_runner.py] — AgentRunner Tool-Loop
│   ├── runner_types.py                # [war: agent_runner_types.py]
│   ├── store.py                       # [war: agents/agent_store.py] — UnifiedAgentStore
│   ├── record.py                      # [war: agents/unified_agent_record.py]
│   ├── adapter.py                     # [war: agents/unified_adapter.py]
│   ├── factory_defaults.py            # [war: agents/factory_defaults.py] — 15 Builtin-Agents
│   ├── manifest.json                  # [war: agents/agents_manifest.json]
│   └── resolution.py                  # [war: services/agent_resolution.py]
│
├── contracts/                         # QUERSCHNITT: Protocol-Interfaces (kein Domain-Coupling)
│   ├── __init__.py
│   ├── agent_contract.py              # AgentContract ABC — bleibt
│   ├── schemas.py                     # Shared Schemas — bleibt
│   ├── tool_protocol.py               # ToolProvider Protocol — bleibt
│   └── orchestrator_api.py            # [war: interfaces/orchestrator_api.py + interfaces/request_context.py]
│
├── orchestration/                     # DOMAIN: Orchestration Pipeline
│   ├── __init__.py
│   ├── pipeline_runner.py             # [war: orchestrator/pipeline_runner.py]
│   ├── fallback_state_machine.py      # [war: orchestrator/fallback_state_machine.py]
│   ├── run_state_machine.py           # [war: orchestrator/run_state_machine.py]
│   ├── session_lane_manager.py        # [war: orchestrator/session_lane_manager.py]
│   ├── subrun_lane.py                 # [war: orchestrator/subrun_lane.py]
│   ├── events.py                      # [war: orchestrator/events.py]
│   ├── step_types.py                  # [war: orchestrator/step_types.py]
│   └── recovery_strategy.py           # [war: orchestrator/recovery_strategy.py]
│
├── multi_agency/                      # DOMAIN: Multi-Agent-Koordination
│   ├── __init__.py
│   ├── coordination_bridge.py
│   ├── supervisor.py
│   ├── agent_identity.py
│   ├── agent_message_bus.py
│   ├── blackboard.py
│   ├── confidence_router.py
│   ├── consensus.py
│   └── parallel_executor.py
│
├── llm/                               # DOMAIN: LLM-Client & Model-Routing
│   ├── __init__.py
│   ├── client.py                      # [war: llm_client.py] — LlmClient
│   ├── health_tracker.py              # [war: services/model_health_tracker.py]
│   └── routing/
│       ├── __init__.py
│       ├── router.py                  # [war: model_routing/router.py]
│       ├── registry.py                # [war: model_routing/model_registry.py]
│       ├── capability_profile.py      # [war: model_routing/capability_profile.py]
│       └── context_window_guard.py    # [war: model_routing/context_window_guard.py]
│
├── tools/                             # DOMAIN: Tool-Ökosystem
│   ├── __init__.py
│   ├── catalog.py                     # [war: tool_catalog.py]
│   ├── policy.py                      # [war: tool_policy.py]
│   ├── content_security.py            # [war: content_security.py] — SSRF, URL-Validierung
│   ├── url_validator.py               # [war: url_validator.py]
│   ├── telemetry.py                   # [war: services/tool_telemetry.py]
│   │
│   ├── implementations/               # Konkrete Tool-Implementierungen (aus tools.py aufgeteilt)
│   │   ├── __init__.py
│   │   ├── base.py                    # AgentTooling Basisklasse + Mixin-Assembly
│   │   ├── filesystem.py              # list_dir, read_file, write_file, apply_patch, file_search, grep_search
│   │   ├── shell.py                   # run_command, probe_command, start_background_command
│   │   ├── web.py                     # web_fetch, web_search, http_request [war: tools.py + tools_api_connectors.py]
│   │   ├── browser.py                 # browser_open/click/type/screenshot/dom/js [aus tools.py]
│   │   ├── code_execution.py          # code_execute, code_reset [aus tools.py]
│   │   ├── multimodal.py              # analyze_image, emit_visualization [war: tools_multimodal.py]
│   │   └── devops.py                  # DevOps-Tools [war: tools_devops.py]
│   │
│   ├── registry/                      # Tool-Registrierung
│   │   ├── __init__.py
│   │   ├── registry.py                # [war: services/tool_registry.py]
│   │   └── config_store.py            # [war: tool_modules/tool_config_store.py]
│   │
│   ├── execution/                     # Tool-Ausführungs-Pipeline
│   │   ├── __init__.py
│   │   ├── manager.py                 # [war: services/tool_execution_manager.py]
│   │   ├── gatekeeper.py              # [war: services/tool_call_gatekeeper.py]
│   │   ├── arg_validator.py           # [war: services/tool_arg_validator.py]
│   │   ├── retry_strategy.py          # [war: services/tool_retry_strategy.py]
│   │   ├── outcome_verifier.py        # [war: services/tool_outcome_verifier.py]
│   │   ├── parallel_executor.py       # [war: services/tool_parallel_executor.py]
│   │   ├── loop_detector.py           # [war: services/tool_loop_detector.py]
│   │   ├── result_processor.py        # [war: services/tool_result_processor.py]
│   │   └── result_context_guard.py    # [war: services/tool_result_context_guard.py]
│   │
│   ├── discovery/                     # Tool-Discovery & Intelekt
│   │   ├── __init__.py
│   │   ├── engine.py                  # [war: services/tool_discovery_engine.py]
│   │   ├── knowledge_base.py          # [war: services/tool_knowledge_base.py]
│   │   ├── capability_router.py       # [war: services/tool_capability_router.py]
│   │   ├── ecosystem_map.py           # [war: services/tool_ecosystem_map.py]
│   │   └── detector.py                # [war: services/tool_detector.py]
│   │
│   └── provisioning/                  # Tool-Bereitstellung & Lifecycle
│       ├── __init__.py
│       ├── provisioner.py             # [war: services/tool_provisioner.py]
│       ├── budget_manager.py          # [war: services/tool_budget_manager.py]
│       ├── policy_service.py          # [war: services/tool_policy_service.py]
│       └── command_security.py        # [war: tool_modules/command_security.py]
│
├── reasoning/                         # DOMAIN: Reasoning & Prompt-Verarbeitung
│   ├── __init__.py
│   ├── action_parser.py               # [war: services/action_parser.py]
│   ├── action_augmenter.py            # [war: services/action_augmenter.py]
│   ├── intent_detector.py             # [war: services/intent_detector.py]
│   ├── directive_parser.py            # [war: services/directive_parser.py]
│   ├── request_normalization.py       # [war: services/request_normalization.py]
│   ├── dynamic_temperature.py         # [war: services/dynamic_temperature.py]
│   ├── output_parsers.py              # [war: services/output_parsers.py]
│   ├── reply_shaper.py                # [war: services/reply_shaper.py]
│   ├── plan_graph.py                  # [war: services/plan_graph.py]
│   └── prompt/
│       ├── __init__.py
│       ├── kernel_builder.py          # [war: services/prompt_kernel_builder.py]
│       ├── ab_registry.py             # [war: services/prompt_ab_registry.py]
│       └── templates/                 # [war: prompts/] — Prompt-Markdown-Templates
│           ├── cognitive/
│           ├── agent_rules.md
│           ├── tool_routing.md
│           ├── tool_routing_multimodal.md
│           └── validation_execution.md
│
├── quality/                           # DOMAIN: Qualitätskontrolle & Selbstheilung
│   ├── __init__.py
│   ├── reflection_service.py          # [war: services/reflection_service.py]
│   ├── verification_service.py        # [war: services/verification_service.py]
│   ├── execution_contract.py          # [war: services/execution_contract.py]
│   ├── execution_pattern_detector.py  # [war: services/execution_pattern_detector.py]
│   ├── self_healing_loop.py           # [war: services/self_healing_loop.py]
│   └── graceful_degradation.py        # [war: services/graceful_degradation.py]
│
├── memory/                            # DOMAIN: Persistente Memory & Lernen
│   ├── __init__.py
│   ├── session_memory.py              # [war: memory.py] — MemoryStore (JSONL, Session-scoped)
│   ├── long_term.py                   # [war: services/long_term_memory.py] — SQLite LTM
│   ├── failure_retriever.py           # [war: services/failure_retriever.py]
│   ├── reflection_store.py            # [war: services/reflection_feedback_store.py]
│   ├── learning_loop.py               # [war: services/learning_loop.py]
│   └── adaptive_selector.py           # [war: services/adaptive_tool_selector.py]
│
├── session/                           # DOMAIN: Session-Verwaltung
│   ├── __init__.py
│   ├── inbox_service.py               # [war: services/session_inbox_service.py]
│   ├── query_service.py               # [war: services/session_query_service.py]
│   ├── security.py                    # [war: services/session_security.py]
│   └── compaction.py                  # [war: services/compaction_service.py]
│
├── state/                             # DOMAIN: State-Persistenz
│   ├── __init__.py
│   ├── state_store.py                 # [war: state/state_store.py]
│   ├── snapshots.py                   # [war: state/snapshots.py]
│   ├── task_graph.py                  # [war: state/task_graph.py]
│   └── encryption.py                  # [war: services/state_encryption.py]
│
├── policy/                            # DOMAIN: Policy, Sicherheit & Guardrails
│   ├── __init__.py
│   ├── store.py                       # [war: policy_store.py]
│   ├── approval_service.py            # [war: services/policy_approval_service.py]
│   ├── circuit_breaker.py             # [war: services/circuit_breaker.py]
│   ├── agent_isolation.py             # [war: services/agent_isolation.py]
│   ├── rate_limiter.py                # [war: services/rate_limiter.py]
│   ├── provisioning_policy.py         # [war: services/provisioning_policy.py]
│   ├── log_secret_filter.py           # [war: services/log_secret_filter.py]
│   └── errors.py                      # [war: errors.py] — GuardrailViolation, PolicyApprovalCancelledError…
│
├── workflows/                         # DOMAIN: Workflows (bleibt weitgehend)
│   ├── __init__.py
│   ├── engine.py
│   ├── models.py
│   ├── router.py                      # → Router-Logik zu transport/routers/workflows.py
│   ├── scheduler.py
│   ├── store.py
│   ├── handlers.py
│   ├── chain_resolver.py
│   ├── tools.py
│   └── transforms.py
│
├── skills/                            # DOMAIN: Skills & Extensions (bleibt)
│   ├── __init__.py
│   ├── discovery.py
│   ├── eligibility.py
│   ├── models.py
│   ├── parser.py
│   ├── prompt.py
│   ├── retrieval.py
│   ├── service.py
│   ├── snapshot.py
│   └── validation.py
│
├── connectors/                        # INFRASTRUKTUR: Externe Integrationen (bleibt)
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── connector_store.py
│   ├── credential_store.py
│   ├── generic_rest_connector.py
│   ├── oauth2_flow.py
│   ├── github_connector.py
│   ├── google_connector.py
│   ├── jira_connector.py
│   ├── slack_connector.py
│   └── x_connector.py
│
├── mcp/                               # INFRASTRUKTUR: Model Context Protocol
│   ├── __init__.py
│   ├── bridge.py                      # [war: services/mcp_bridge.py]
│   └── types.py                       # [war: mcp_types.py]
│
├── media/                             # INFRASTRUKTUR: Audio/Vision/Image/PDF
│   ├── __init__.py
│   ├── audio_service.py               # [war: services/audio_service.py]
│   ├── audio_deps.py                  # [war: services/audio_deps_service.py]
│   ├── vision_service.py              # [war: services/vision_service.py]
│   ├── image_gen_service.py           # [war: services/image_gen_service.py]
│   └── pdf_service.py                 # [war: services/pdf_service.py]
│
├── sandbox/                           # INFRASTRUKTUR: Code-Execution Sandbox
│   ├── __init__.py
│   ├── code_sandbox.py                # [war: services/code_sandbox.py]
│   ├── persistent_repl.py             # [war: services/persistent_repl.py]
│   └── repl_session_manager.py        # [war: services/repl_session_manager.py]
│
├── browser/                           # INFRASTRUKTUR: Browser-Automatisierung
│   ├── __init__.py
│   └── pool.py                        # [war: services/browser_pool.py]
│
├── monitoring/                        # INFRASTRUKTUR: Observability
│   ├── __init__.py
│   ├── visualization.py               # [war: services/visualization.py]
│   ├── environment_snapshot.py        # [war: services/environment_snapshot.py]
│   └── platform_info.py               # [war: services/platform_info.py]
│
└── shared/                            # QUERSCHNITT: Geteilte Typen (kein Domain-Coupling)
    ├── __init__.py
    ├── control_models.py              # [war: control_models.py]
    ├── errors.py                      # Basis-Fehlertypen
    └── idempotency/
        ├── __init__.py
        ├── manager.py                 # [war: services/idempotency_manager.py]
        └── service.py                 # [war: services/idempotency_service.py]
```

---

## 5. Monolithen-Aufteilung

### 5.1 `tools.py` (~1100+ Zeilen) → `tools/implementations/`

Die `AgentTooling`-Klasse wird durch Composition über Mixins zu konkreten, testbaren Modulen aufgeteilt:

```
tools.py (Monolith)
├── Filesystem-Methoden     → tools/implementations/filesystem.py  (FileSystemToolMixin)
├── Shell-Methoden          → tools/implementations/shell.py        (ShellToolMixin)
├── Web-Methoden            → tools/implementations/web.py          (WebToolMixin)
├── Browser-Methoden        → tools/implementations/browser.py      (BrowserToolMixin)
├── Code-Execute-Methoden   → tools/implementations/code_execution.py (CodeExecToolMixin)
├── find_command_safety_*   → tools/policy.py                       (Security-Utils)
└── AgentTooling Assembly   → tools/implementations/base.py         (AgentTooling)
```

### 5.2 `main.py` (200+ Imports) → Schlanker Entry-Point

`main.py` wird zu einem reinen Bootstrap-File. Die Handler-Wiring-Logik wandert in die jeweiligen Router-Dateien:

```
main.py (Monolith)
├── App-Bootstrap           → transport/app_factory.py
├── Router-Wiring           → transport/routers/__init__.py
├── Handler-Registrierung   → jeweiliger Router (z.B. transport/routers/agents.py)
└── main.py                 bleibt als reiner Entry: app = create_app()
```

### 5.3 `handlers/` → in `transport/routers/` zusammenführen

Die künstliche Trennung `routers/` + `handlers/` entfällt. Jeder Router ist selbst für seine Handler verantwortlich:

```
handlers/agent_handlers.py        ─┐
handlers/agent_config_handlers.py  ├→ transport/routers/agents.py
routers/agents.py                 ─┘

handlers/run_handlers.py          ─┐
routers/control_runs.py           ─┤→ transport/routers/runs.py
run_endpoints.py                  ─┘
```

---

## 6. Migrations-Mapping (Alt → Neu)

### `backend/app/` Root-Dateien

| Alt | Neu |
|-----|-----|
| `app/agent.py` | `app/agent/head_agent.py` |
| `app/agent_runner.py` | `app/agent/runner.py` |
| `app/agent_runner_types.py` | `app/agent/runner_types.py` |
| `app/agents/agent_store.py` | `app/agent/store.py` |
| `app/agents/unified_agent_record.py` | `app/agent/record.py` |
| `app/agents/unified_adapter.py` | `app/agent/adapter.py` |
| `app/agents/factory_defaults.py` | `app/agent/factory_defaults.py` |
| `app/ws_handler.py` | `app/transport/ws_handler.py` |
| `app/models.py` | `app/transport/ws_models.py` |
| `app/control_models.py` | `app/shared/control_models.py` |
| `app/app_setup.py` | `app/transport/app_factory.py` |
| `app/app_state.py` | `app/transport/app_state.py` |
| `app/startup_tasks.py` | `app/transport/startup.py` |
| `app/runtime_manager.py` | `app/transport/runtime_manager.py` |
| `app/control_router_wiring.py` | `app/transport/routers/__init__.py` |
| `app/run_endpoints.py` | `app/transport/routers/runs.py` (merged) |
| `app/subrun_endpoints.py` | `app/transport/routers/subruns.py` (merged) |
| `app/runtime_debug_endpoints.py` | `app/transport/routers/debug.py` (merged) |
| `app/llm_client.py` | `app/llm/client.py` |
| `app/memory.py` | `app/memory/session_memory.py` |
| `app/mcp_types.py` | `app/mcp/types.py` |
| `app/content_security.py` | `app/tools/content_security.py` |
| `app/url_validator.py` | `app/tools/url_validator.py` |
| `app/errors.py` | `app/policy/errors.py` |
| `app/policy_store.py` | `app/policy/store.py` |
| `app/tools.py` | `app/tools/implementations/` (aufgeteilt) |
| `app/tools_api_connectors.py` | `app/tools/implementations/web.py` |
| `app/tools_devops.py` | `app/tools/implementations/devops.py` |
| `app/tools_multimodal.py` | `app/tools/implementations/multimodal.py` |
| `app/tool_catalog.py` | `app/tools/catalog.py` |
| `app/tool_policy.py` | `app/tools/policy.py` |

### `app/orchestrator/` → `app/orchestration/`

| Alt | Neu |
|-----|-----|
| `app/orchestrator/pipeline_runner.py` | `app/orchestration/pipeline_runner.py` |
| `app/orchestrator/fallback_state_machine.py` | `app/orchestration/fallback_state_machine.py` |
| `app/orchestrator/run_state_machine.py` | `app/orchestration/run_state_machine.py` |
| `app/orchestrator/session_lane_manager.py` | `app/orchestration/session_lane_manager.py` |
| `app/orchestrator/subrun_lane.py` | `app/orchestration/subrun_lane.py` |
| `app/orchestrator/events.py` | `app/orchestration/events.py` |
| `app/orchestrator/step_types.py` | `app/orchestration/step_types.py` |
| `app/orchestrator/recovery_strategy.py` | `app/orchestration/recovery_strategy.py` |
| `app/interfaces/orchestrator_api.py` | `app/contracts/orchestrator_api.py` |
| `app/interfaces/request_context.py` | `app/contracts/orchestrator_api.py` (merged) |

### `app/model_routing/` → `app/llm/routing/`

| Alt | Neu |
|-----|-----|
| `app/model_routing/router.py` | `app/llm/routing/router.py` |
| `app/model_routing/model_registry.py` | `app/llm/routing/registry.py` |
| `app/model_routing/capability_profile.py` | `app/llm/routing/capability_profile.py` |
| `app/model_routing/context_window_guard.py` | `app/llm/routing/context_window_guard.py` |

### `app/services/` → Domänen-Module

| Alt (`services/`) | Neu |
|-------------------|-----|
| `action_parser.py` | `app/reasoning/action_parser.py` |
| `action_augmenter.py` | `app/reasoning/action_augmenter.py` |
| `intent_detector.py` | `app/reasoning/intent_detector.py` |
| `directive_parser.py` | `app/reasoning/directive_parser.py` |
| `request_normalization.py` | `app/reasoning/request_normalization.py` |
| `dynamic_temperature.py` | `app/reasoning/dynamic_temperature.py` |
| `output_parsers.py` | `app/reasoning/output_parsers.py` |
| `reply_shaper.py` | `app/reasoning/reply_shaper.py` |
| `plan_graph.py` | `app/reasoning/plan_graph.py` |
| `prompt_kernel_builder.py` | `app/reasoning/prompt/kernel_builder.py` |
| `prompt_ab_registry.py` | `app/reasoning/prompt/ab_registry.py` |
| `reflection_service.py` | `app/quality/reflection_service.py` |
| `verification_service.py` | `app/quality/verification_service.py` |
| `execution_contract.py` | `app/quality/execution_contract.py` |
| `execution_pattern_detector.py` | `app/quality/execution_pattern_detector.py` |
| `self_healing_loop.py` | `app/quality/self_healing_loop.py` |
| `graceful_degradation.py` | `app/quality/graceful_degradation.py` |
| `long_term_memory.py` | `app/memory/long_term.py` |
| `failure_retriever.py` | `app/memory/failure_retriever.py` |
| `reflection_feedback_store.py` | `app/memory/reflection_store.py` |
| `learning_loop.py` | `app/memory/learning_loop.py` |
| `adaptive_tool_selector.py` | `app/memory/adaptive_selector.py` |
| `session_inbox_service.py` | `app/session/inbox_service.py` |
| `session_query_service.py` | `app/session/query_service.py` |
| `session_security.py` | `app/session/security.py` |
| `compaction_service.py` | `app/session/compaction.py` |
| `state_encryption.py` | `app/state/encryption.py` |
| `policy_approval_service.py` | `app/policy/approval_service.py` |
| `circuit_breaker.py` | `app/policy/circuit_breaker.py` |
| `agent_isolation.py` | `app/policy/agent_isolation.py` |
| `rate_limiter.py` | `app/policy/rate_limiter.py` |
| `provisioning_policy.py` | `app/policy/provisioning_policy.py` |
| `log_secret_filter.py` | `app/policy/log_secret_filter.py` |
| `tool_registry.py` | `app/tools/registry/registry.py` |
| `tool_execution_manager.py` | `app/tools/execution/manager.py` |
| `tool_call_gatekeeper.py` | `app/tools/execution/gatekeeper.py` |
| `tool_arg_validator.py` | `app/tools/execution/arg_validator.py` |
| `tool_retry_strategy.py` | `app/tools/execution/retry_strategy.py` |
| `tool_outcome_verifier.py` | `app/tools/execution/outcome_verifier.py` |
| `tool_parallel_executor.py` | `app/tools/execution/parallel_executor.py` |
| `tool_loop_detector.py` | `app/tools/execution/loop_detector.py` |
| `tool_result_processor.py` | `app/tools/execution/result_processor.py` |
| `tool_result_context_guard.py` | `app/tools/execution/result_context_guard.py` |
| `tool_discovery_engine.py` | `app/tools/discovery/engine.py` |
| `tool_knowledge_base.py` | `app/tools/discovery/knowledge_base.py` |
| `tool_capability_router.py` | `app/tools/discovery/capability_router.py` |
| `tool_ecosystem_map.py` | `app/tools/discovery/ecosystem_map.py` |
| `tool_detector.py` | `app/tools/discovery/detector.py` |
| `tool_provisioner.py` | `app/tools/provisioning/provisioner.py` |
| `tool_budget_manager.py` | `app/tools/provisioning/budget_manager.py` |
| `tool_policy_service.py` | `app/tools/provisioning/policy_service.py` |
| `tool_telemetry.py` | `app/tools/telemetry.py` |
| `model_health_tracker.py` | `app/llm/health_tracker.py` |
| `agent_resolution.py` | `app/agent/resolution.py` |
| `mcp_bridge.py` | `app/mcp/bridge.py` |
| `web_search.py` | `app/tools/implementations/web.py` (merged) |
| `audio_service.py` | `app/media/audio_service.py` |
| `audio_deps_service.py` | `app/media/audio_deps.py` |
| `vision_service.py` | `app/media/vision_service.py` |
| `image_gen_service.py` | `app/media/image_gen_service.py` |
| `pdf_service.py` | `app/media/pdf_service.py` |
| `code_sandbox.py` | `app/sandbox/code_sandbox.py` |
| `persistent_repl.py` | `app/sandbox/persistent_repl.py` |
| `repl_session_manager.py` | `app/sandbox/repl_session_manager.py` |
| `browser_pool.py` | `app/browser/pool.py` |
| `visualization.py` | `app/monitoring/visualization.py` |
| `environment_snapshot.py` | `app/monitoring/environment_snapshot.py` |
| `platform_info.py` | `app/monitoring/platform_info.py` |
| `idempotency_manager.py` | `app/shared/idempotency/manager.py` |
| `idempotency_service.py` | `app/shared/idempotency/service.py` |
| `hook_contract.py` | `app/contracts/hook_contract.py` |
| `error_taxonomy.py` | `app/policy/error_taxonomy.py` |
| `package_manager_adapter.py` | `app/tools/provisioning/package_manager_adapter.py` |
| `control_fingerprints.py` | `app/transport/routers/` oder `app/session/` |
| `benchmark_calibration.py` | bleibt in `benchmarks/` |

### `app/routers/` → `app/transport/routers/`

| Alt | Neu |
|-----|-----|
| `routers/agents.py` | `transport/routers/agents.py` |
| `routers/control_agent_config.py` | `transport/routers/agents.py` (merged) |
| `routers/control_config.py` | `transport/routers/config.py` |
| `routers/control_execution_config.py` | `transport/routers/config.py` (merged) |
| `routers/control_integrations.py` | `transport/routers/integrations.py` |
| `routers/control_policy_approvals.py` | `transport/routers/policies.py` (merged) |
| `routers/control_runs.py` | `transport/routers/runs.py` |
| `routers/control_sessions.py` | `transport/routers/sessions.py` |
| `routers/control_tools.py` | `transport/routers/tools.py` |
| `routers/control_tool_config.py` | `transport/routers/tools.py` (merged) |
| `routers/policies.py` | `transport/routers/policies.py` |
| `routers/runtime_debug.py` | `transport/routers/debug.py` |
| `routers/run_api.py` | `transport/routers/runs.py` (merged) |
| `routers/subruns.py` | `transport/routers/subruns.py` |
| `routers/uploads.py` | `transport/routers/uploads.py` |
| `routers/webhooks.py` | `transport/routers/webhooks.py` |
| `routers/ws_agent_router.py` | `transport/routers/ws_agent.py` |

---

## 7. Dependency-Regeln (DDD Layering)

```
transport/          → darf nutzen: agent, orchestration, workflows, shared, policy, contracts
agent/              → darf nutzen: llm, tools, memory, reasoning, quality, policy, contracts, shared
orchestration/      → darf nutzen: agent (via contracts), session, state, memory, policy, shared
multi_agency/       → darf nutzen: agent (via contracts), orchestration, shared
tools/              → darf nutzen: policy, sandbox, browser, media, monitoring, shared, contracts
reasoning/          → darf nutzen: llm (via contracts), shared
quality/            → darf nutzen: reasoning, memory, shared
memory/             → darf nutzen: state, shared
session/            → darf nutzen: memory, state, shared, policy
state/              → darf nutzen: shared (keine Domänen-Imports!)
policy/             → darf nutzen: shared (keine Domänen-Imports!)
llm/                → darf nutzen: shared (keine Domänen-Imports!)
connectors/         → darf nutzen: shared, policy
mcp/                → darf nutzen: contracts, shared
media/              → darf nutzen: shared
sandbox/            → darf nutzen: policy, shared
browser/            → darf nutzen: policy, tools/url_validator, shared
monitoring/         → darf nutzen: shared
workflows/          → darf nutzen: agent (via contracts), state, memory, shared
skills/             → darf nutzen: shared, state
config/             → wird von allen genutzt, importiert NICHTS aus Domänen
shared/             → importiert NICHTS aus anderen App-Modulen
contracts/          → importiert NICHTS außer typing + shared
```

**Goldene Regel:** `shared/` und `contracts/` sind rein "outward-facing" — sie haben keine Imports aus anderen Domänen.  
**Verbotene Richtungen:** `state/ → agent/`, `policy/ → tools/`, `llm/ → agent/`, `memory/ → reasoning/`

---

*Schritt 2: Datei-Migrationen, Import-Rewrites, Test-Anpassungen — separat nach Freigabe dieses Plans.*
