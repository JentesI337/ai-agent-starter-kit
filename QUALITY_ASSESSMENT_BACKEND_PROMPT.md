# Backend Quality Assessment — Vollständige Bewertung

**Datum:** 2026-03-05  
**Scope:** Gesamtes Backend (`backend/`) — alle Module, Services, Tests, Infrastruktur  
**Basis:** Live-Codeanalyse, fokussierte Regressionstests (66 passed), statische Fehlerprüfung (0 Errors), vorhandene Audit-Artefakte

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Architektur & Modulstruktur](#2-architektur--modulstruktur)
3. [Agent-Kern (HeadAgent)](#3-agent-kern-headagent)
4. [Sub-Agents (Planner / ToolSelector / Synthesizer)](#4-sub-agents)
5. [Orchestrator & Pipeline](#5-orchestrator--pipeline)
6. [Fallback & Recovery](#6-fallback--recovery)
7. [Model Routing & Runtime](#7-model-routing--runtime)
8. [Tool-System](#8-tool-system)
9. [Tool Policy & Approval](#9-tool-policy--approval)
10. [Sicherheit & Guardrails](#10-sicherheit--guardrails)
11. [Memory-System (Short-Term / Long-Term)](#11-memory-system)
12. [Skills Engine](#12-skills-engine)
13. [Prompt-System](#13-prompt-system)
14. [Reflection & Verification](#14-reflection--verification)
15. [WebSocket-Handler & Transport](#15-websocket-handler--transport)
16. [REST API & Control Plane](#16-rest-api--control-plane)
17. [State Management & Persistenz](#17-state-management--persistenz)
18. [Konfiguration (config.py)](#18-konfiguration)
19. [Fehlerbehandlung & Error-Typen](#19-fehlerbehandlung--error-typen)
20. [Concurrency & Session-Management](#20-concurrency--session-management)
21. [Sub-Runs & Agent-Isolation](#21-sub-runs--agent-isolation)
22. [Idempotenz](#22-idempotenz)
23. [MCP Bridge](#23-mcp-bridge)
24. [Benchmarking & Eval-Gates](#24-benchmarking--eval-gates)
25. [Monitoring & Observability](#25-monitoring--observability)
26. [Test-Suite & Coverage](#26-test-suite--coverage)
27. [Code-Hygiene & Wartbarkeit](#27-code-hygiene--wartbarkeit)
28. [Bekannte Bugs & Technische Schuld](#28-bekannte-bugs--technische-schuld)
29. [Limitierungen](#29-limitierungen)
30. [Gesamtbewertung & Scorecard](#30-gesamtbewertung--scorecard)
31. [Priorisierter Maßnahmenplan](#31-priorisierter-massnahmenplan)

---

## 1. Executive Summary

Das Backend ist ein **produktionsreifer AI-Agent-Orchestrator** auf Basis von FastAPI mit WebSocket-Echtzeit-Kommunikation. Der zentrale `HeadAgent` führt eine deterministische 4-Phasen-Pipeline aus: **Plan → Tool Selection/Execution → Synthesis → Verification**, gestützt durch Sub-Agents, eine Model-Fallback-State-Machine, ein 6-stufiges Tool-Policy-System und eine optionale Skills-Engine.

### Kennzahlen

| Metrik | Wert |
|--------|------|
| Python-Version | 3.12+ |
| App-Dateien (backend/app/) | ~85 Module |
| Service-Module | 38 |
| Orchestrator-Module | 10 |
| Kern-Tools | 14 + MCP-erweiterbar |
| Test-Dateien | 82 |
| Fokussierter Regressionstest | 66 passed / 4.31s |
| Coverage-Gate (global) | ≥ 70% |
| Konfigurierbare Parameter | ~200+ Env-Vars |
| Eval-Golden-Suite-Cases | 30 |
| Benchmark-Levels | 3 (easy/mid/hard) |
| Bug-Fixes seit letztem Audit | 14 (12 vollständig, 2 teilweise) |
| Statische IDE-Errors | 0 |

### Gesamtnote: **8.5 / 10**

---

## 2. Architektur & Modulstruktur

### 2.1 Schichtenmodell (6 Schichten)

```
┌────────────────────────────────────────────────────────────┐
│  1. Transport-Schicht                                      │
│     WebSocket /ws/agent · REST-API · CORS                  │
├────────────────────────────────────────────────────────────┤
│  2. Agent/Orchestration-Schicht                            │
│     HeadAgent · PlannerAgent · ToolSelectorAgent           │
│     SynthesizerAgent · CustomAgentAdapter                  │
├────────────────────────────────────────────────────────────┤
│  3. Runtime/Model-Schicht                                  │
│     RuntimeManager · ModelRouter · PipelineRunner          │
│     FallbackStateMachine · RecoveryStrategy                │
├────────────────────────────────────────────────────────────┤
│  4. Persistenz/State-Schicht                               │
│     StateStore/SqliteStateStore · Memory (JSONL)           │
│     CustomAgentStore · RuntimeState (JSON)                 │
├────────────────────────────────────────────────────────────┤
│  5. Policy/Guardrail-Schicht                               │
│     ToolPolicyService · ToolCallGatekeeper                 │
│     CommandSafetyPatterns · SSRF-Schutz                    │
├────────────────────────────────────────────────────────────┤
│  6. Skills/Extensions-Schicht                              │
│     SkillsService · Discovery · Eligibility                │
│     Parser · Retrieval · MCP Bridge                        │
└────────────────────────────────────────────────────────────┘
```

### 2.2 Bewertung

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Schichtentrennung | ★★★★☆ | Klare Separation; einige Cross-Cuts (ws_handler liest State direkt) |
| Modulares Design | ★★★★★ | 38 Services, 10 Orchestrator-Module, 5 Contracts — vorbildliche Aufteilung |
| Interface-Contracts | ★★★★★ | Protocol-basierte Interfaces (keine Tight-Coupling-Imports in ws_handler) |
| Dependency Injection | ★★★★☆ | LazyRuntimeRegistry, RuntimeComponents Dataclass; kein DI-Container |
| Verzeichnis-Organisation | ★★★★★ | agents/, contracts/, handlers/, interfaces/, model_routing/, orchestrator/, prompts/, routers/, services/, skills/, state/ |

---

## 3. Agent-Kern (HeadAgent)

### 3.1 Pipeline (11 Schritte)

```
1. Guardrails ─→ 2. Tool Policy ─→ 3. Toolchain Check ─→ 4. Memory Update
    ─→ 5. Context Reduction ─→ 6. Planning ─→ 7. Tool Selection/Execution
    ─→ 8. Synthesis ─→ 9. Reply Shaping ─→ 10. Verification ─→ 11. Final Emit
```

### 3.2 Bewertung

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Pipeline-Determinismus | ★★★★★ | Feste Schrittfolge, kein nicht-deterministisches Branching |
| Replan-Mechanismus | ★★★★☆ | Konfigurierbare max_replan_iterations, Tool-Result-Klassifikation (empty/error_only/blocked/usable/steer_interrupted) |
| Hooks-System | ★★★★☆ | register_hook() mit hard_fail/soft_fail/skip-Policies, Timeout-fähig |
| Agent-Varianten | ★★★★☆ | CoderAgent/ReviewAgent als Sub-Klassen mit eigenem PromptProfile |
| Steer-Interrupt | ★★★★★ | Externe Unterbrechung der Tool-Schleife über should_steer_interrupt Callback |
| Reconfigure-Guard | ★★★☆☆ | _active_run_count Guard vorhanden; _configure_lock existiert aber wird nicht vollständig genutzt |

### 3.3 Risiken

- **Dateigröße:** `agent.py` hat 2924 Zeilen — schwer navigierbar und review-intensiv
- **Concurrency Guard:** `_configure_lock` (asyncio.Lock) existiert, wird aber nicht in `run()` geprüft — der Guard beruht nur auf `_active_run_count` und `_reconfiguring`-Flag (synchron)

---

## 4. Sub-Agents

### 4.1 PlannerAgent

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Aufgabe | ★★★★★ | Erstellt 2-5-Bullet-Pläne, adaptive Komplexität |
| Failure-Retrieval | ★★★★☆ | Optional FailureRetriever-Integration für historische Fehler-Guidance |
| Hard Contracts | ★★★★☆ | Spezielle Research-Anfragen erzwingen verbindliches Ausgabe-Schema |
| Constraints | ★★★★☆ | max_context=4096, temp=0.2, reasoning=2 — konservativ und stabil |

### 4.2 ToolSelectorAgent

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Tool-Auswahl | ★★★★☆ | LLM-basierte oder Function-Calling-Auswahl (konfigurierbar) |
| Capability Pre-Selection | ★★★★★ | Filtert Tools nach erkannten Capabilities vor LLM-Aufruf |
| Skills-Integration | ★★★★☆ | Skills-Snapshot wird in den Prompt eingebaut |
| Action Augmentation | ★★★★☆ | Automatische Ergänzung von web_fetch/spawn_subrun basierend auf Intent |

### 4.3 SynthesizerAgent

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Task-Type-Erkennung | ★★★★★ | 6 Typen: hard_research, research, orchestration, implementation, general, orchestration_failed |
| Section-Contract | ★★★★★ | Pflicht-Abschnitte je Task-Type, LLM-basierte Self-Repair bei fehlenden Sections |
| Evidence Check | ★★★★☆ | Prüft ob Tool-Output die Synthese belegt (Implementation/Orchestration) |
| Streaming | ★★★★★ | Token-Level-Streaming mit Lifecycle-Events |
| Dynamic Temperature | ★★★★☆ | DynamicTemperatureResolver mit Task-Type-spezifischen Overrides |

---

## 5. Orchestrator & Pipeline

### 5.1 OrchestratorApi

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Session Lane Control | ★★★★★ | Concurrency-Serialisierung pro Session via SessionLaneManager |
| Tool Policy Resolution | ★★★★★ | 6-stufige Auflösung (global→profile→preset→provider→model→depth→request) |
| Policy Event Emission | ★★★★☆ | Lifecycle-Events für resolved Policy mit Details |
| Delegation | ★★★★★ | Saubere Delegation an PipelineRunner.run() |

### 5.2 PipelineRunner

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Model Routing | ★★★★★ | Integration mit ModelRouter, Scoring-basierte Auswahl |
| Adaptive Inference | ★★★★☆ | Auto-Degradierung bei Budget-Überschreitung |
| Context Window Guard | ★★★★★ | Verhindert Overflow vor LLM-Aufruf |
| Failover Classification | ★★★★★ | Regex-basierte Fehlerklassifikation (context_overflow, truncation, rate_limited, timeout, network_error) |
| Non-Retryable Detection | ★★★★★ | Sofortiger Abbruch bei nicht-wiederholbaren Fehlern |
| State Tracking | ★★★★☆ | Per-Task-State (pending→active→completed/failed) mit Persistenz |

### 5.3 Run State Machine

```
received → queued → planning → tool_loop → synthesis → finalizing → persisted
                                                                      ↓
                                                            completed / failed / cancelled
```

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Forward-Only | ★★★★★ | State-Transitions nur vorwärts erlaubt |
| Violation Detection | ★★★★☆ | Optional run_state_violation Events bei ungültigen Übergängen |
| Stage Events | ★★★★★ | Strukturierte stage_event und run_state_event Ableitung |

---

## 6. Fallback & Recovery

### 6.1 FallbackStateMachine

```
INIT → SELECT_MODEL → EXECUTE_ATTEMPT → HANDLE_SUCCESS → done
                                       └→ HANDLE_FAILURE → SELECT_MODEL (retry)
                                                         └→ FINALIZE_FAILURE
```

| Aspekt | Score | Begründung |
|--------|-------|------------|
| State-Machine-Design | ★★★★★ | Explizite Enum-basierte Zustände, saubere Übergänge |
| Recovery-Metriken | ★★★★★ | ~30 Tracking-Felder (Attempts, Overflow/Compaction/Truncation-Counts, Strategie-Feedback) |
| Konfigurierbarkeit | ★★★★★ | FallbackRuntimeConfig mit 28 Parametern, alle via Env-Vars steuerbar |
| Hooks | ★★★★☆ | Protocol-basierte FallbackHooks für Pipeline-Runner-Integration |
| Backoff | ★★★★☆ | Konfigurierbarer Backoff, könnte von exponentiellem Muster profitieren |

### 6.2 RecoveryStrategyResolver

| Strategie | Verfügbar | Bewertung |
|-----------|-----------|-----------|
| Prompt Compaction | ✅ | Reduziert Kontext-Overhead vor Retry |
| Context Overflow Retry | ✅ | Retry mit verkleinertem Kontext |
| Payload Truncation | ✅ | Abschneiden überlanger Payloads |
| Overflow Fallback Retry | ✅ | Wechsel auf Fallback-Modell bei Overflow |
| Signal-Priority | ✅ | Bevorzugte Strategie basierend auf Fehlersignal |
| Persistent Feedback Loop | ✅ | Strategie-Erfolg wird persistiert und beeinflusst künftige Entscheidungen |

**Gesamtbewertung Recovery: ★★★★★ — architektonisch die stärkste Komponente des Backends**

---

## 7. Model Routing & Runtime

### 7.1 ModelRouter

**Scoring-Formel:**
```
Score = Health × w_h + (1 − Latency_norm) × w_l + (1 − Cost_norm) × w_c
        + Runtime_bonus + Reasoning_bonus
```

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Scoring-Algorithmus | ★★★★☆ | Multi-Kriterien-Scoring mit konfigurierbaren Gewichten |
| Health-Tracker-Override | ★★★★★ | Gemessene Profile überschreiben statische Defaults |
| Reasoning Level Support | ★★★★☆ | 5 Stufen: low/medium/high/ultrathink/adaptive |
| Deduplication | ★★★★☆ | Kandidaten werden vor Scoring dedupliziert |

### 7.2 RuntimeManager

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Dual Runtime | ★★★★★ | Nahtloser Local↔API-Wechsel |
| Rollback | ★★★★★ | Automatischer Rollback bei Switch-Fehler |
| Model Pulling | ★★★★☆ | Automatisches Ollama-Model-Pulling |
| API Auth Guard | ★★★★★ | API_AUTH_REQUIRED + Token-Validierung |
| State Persistence | ★★★★☆ | JSON-persistierter Runtime-State inkl. Feature-Flags |

### 7.3 ModelHealthTracker

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Latenz-Messung | ★★★★☆ | p95-Latenz-Tracking pro Modell |
| Health-Score | ★★★★☆ | Dynamischer Health-Score basierend auf Erfolgs-/Fehler-Rate |
| Persistenz | ★★★★☆ | JSON-basierte Persistenz über Neustarts |
| Diagnostik | ★★★★☆ | all_snapshots() für Debug-Endpunkte |

### 7.4 Circuit Breaker

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Zustände | ★★★★★ | CLOSED→OPEN→HALF_OPEN mit konfigurierbaren Schwellen |
| Window-basiert | ★★★★★ | Zeitfenster-basierte Failure-Rate statt unbounded Counter (Bug 5 gefixt) |
| Force-Reset | ★★★★☆ | Admin-API für Circuit-Reset |

---

## 8. Tool-System

### 8.1 Verfügbare Kern-Tools (14)

| Tool | Kategorie | Sicherheitsstufe |
|------|-----------|-----------------|
| `list_dir` | filesystem_read | ★★★★★ |
| `read_file` | filesystem_read | ★★★★★ |
| `write_file` | filesystem_write | ★★★★☆ |
| `apply_patch` | filesystem_write | ★★★★☆ |
| `file_search` | filesystem_read | ★★★★★ |
| `grep_search` | filesystem_read | ★★★★★ |
| `list_code_usages` | filesystem_read | ★★★★★ |
| `get_changed_files` | filesystem_read | ★★★★★ |
| `run_command` | command_execution | ★★★☆☆ |
| `start_background_command` | command_execution | ★★★☆☆ |
| `get_background_output` | command_management | ★★★★★ |
| `kill_background_process` | command_management | ★★★★☆ |
| `web_fetch` | web_retrieval | ★★★★☆ |
| `spawn_subrun` | orchestration | ★★★★★ |

### 8.2 Tool Execution Pipeline

```
LLM-Antwort → ActionParser → Validation → PolicyCheck → ArgValidator
    → GatekeeperCheck → Execution → LoopDetection → ResultContextGuard
```

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Action Parsing | ★★★★☆ | Mehrstufige Recovery: Standard→Balanced-Extract→Truncation-Recovery→LLM-Repair |
| Action Augmentation | ★★★★☆ | Intent-basiert: automatisches web_fetch/spawn_subrun-Hinzufügen |
| Arg Validation | ★★★★★ | 22 registrierte Validators mit Type-Check, Range-Check, Null-Byte-Detection |
| Gatekeeper | ★★★★★ | Loop-Detection (generic_repeat, ping_pong, poll_no_progress) mit 3-stufiger Eskalation |
| Result Context Guard | ★★★★☆ | Preamble-Preservation (Bug 7 gefixt), Tool-Block-Normalisierung |

### 8.3 Tool Aliase

| Alias | Kanonisch |
|-------|-----------|
| `createfile`, `CreateFile` | `write_file` |
| `webfetch`, `WebFetch` | `web_fetch` |
| ... | ... |

**Bewertung:** Alias-Normalisierung verhindert Tool-Selection-Fehler durch LLM-Varianten.

### 8.4 CodeSandbox

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Multi-Strategy | ★★★★☆ | process/docker/direct — erweiterbar |
| Sprachen | ★★★★☆ | Python, JavaScript |
| Network Guard | ★★★★★ | Blockiert Netzwerkzugriff wenn allow_network=False |
| Filesystem Escape | ★★★★★ | Path-Traversal-Erkennung vor Ausführung |
| Timeouts | ★★★★★ | Konfigurierbare Timeouts + Output-Truncation |

---

## 9. Tool Policy & Approval

### 9.1 6-stufiges Policy-System

```
1. Global Policy        →  Basis-Set: allow/deny Listen
2. Tool Profile          →  minimal/coding/review Profile
3. Preset Policy         →  research/review Preset-Overrides
4. Provider Policy       →  local: +commands; api: −background
5. Model-specific Policy →  Modell-spezifische Einschränkungen
6. Agent Depth Policy    →  spawn_subrun-Entzug in tiefen Ebenen
   + Request Override    →  Per-Request allow/deny/also_allow
```

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Layered Resolution | ★★★★★ | deny überschreibt allow, also_allow nur additiv für bekannte Tools |
| Depth-basiert | ★★★★★ | Automatische Einschränkung bei verschachtelten Agent-Aufrufen |
| Transparenz | ★★★★☆ | Policy-Resolution-Details als Lifecycle-Events |

### 9.2 PolicyApprovalService

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Entscheidungsmodell | ★★★★★ | allow_once/allow_session/allow_always/deny/cancel |
| Scope-Validierung | ★★★★★ | _validate_scope() wirft ValueError bei ungültigem Scope (Bug 14 gefixt) |
| Idempotente Erstellung | ★★★★★ | Duplicate-Detection bei create() |
| Session-Scoped Rules | ★★★★☆ | Session-Tool-Keys korrekt, clear_session_overrides bereinigt auch disk-backed Rules (Bug 3 gefixt) |
| Persistenz | ★★★★☆ | JSON-Datei mit atomarem Schreiben (tmp→rename) |
| TTL-Eviction | ★★★★☆ | Stale-Record-Entfernung nach 2×TTL |
| Duplicate-Decision-Handling | ★★★★★ | Zweite Entscheidung wird als Duplikat markiert, nicht überschrieben |

---

## 10. Sicherheit & Guardrails

### 10.1 Command Safety

| Maßnahme | Score | Beschreibung |
|----------|-------|------------|
| COMMAND_SAFETY_PATTERNS | ★★★★★ | 22 Regex-Muster: rm -rf, format, shutdown, curl\|sh, encoded PowerShell etc. |
| Semantische Erkennung | ★★★★☆ | PowerShell-Inline-Patterns, Remote-Code-Execution-Erkennung |
| Command Allowlist | ★★★★☆ | Explizit erlaubte Executables |
| Blocked Leaders | ★★★★☆ | Verbotene Befehlspräfixe |
| Shell Operator Check | ★★★★★ | Erkennung von Shell-Operatoren (Bug 6 gefixt: kein False-Positive bei / und \) |

### 10.2 Web Fetch Security (SSRF-Schutz)

| Maßnahme | Score |
|----------|-------|
| Localhost-Blocking | ★★★★★ |
| Metadata-Endpoint-Blocking | ★★★★★ |
| Non-Public-IP-Blocking | ★★★★★ |
| Redirect-Limit | ★★★★★ |
| Content-Type-Blocking | ★★★★☆ |
| Max Download Size | ★★★★★ |
| HTML→Text Normalisierung | ★★★★☆ |

### 10.3 Workspace Sandboxing

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Path Traversal Guard | ★★★★★ | _resolve_workspace_path mit Canonical-Path-Check |
| Workspace-Root-Restriction | ★★★★★ | Alle Dateioperationen auf Workspace beschränkt |
| read_file Limit | ★★★★☆ | Max 1 MB pro Lesevorgang |
| grep Scan Limit | ★★★★☆ | Max 8 MB Gesamtscan |

### 10.4 Input Guardrails

| Guard | Status |
|-------|--------|
| Empty-Input-Blocking | ✅ |
| Oversized-Input-Blocking | ✅ |
| Invalid-Model-Blocking | ✅ |
| Invalid-Session-Blocking | ✅ |
| Queue-Overflow-Guard | ✅ |
| Context-Window-Guard | ✅ |
| Subrun-Depth-Guard | ✅ |
| Agent-Depth-Guard | ✅ |

---

## 11. Memory-System

### 11.1 Short-Term Memory (MemoryStore)

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Rolling Buffer | ★★★★★ | deque mit max_items_per_session=20 |
| Thread Safety | ★★★★★ | RLock-basiert |
| Persistenz | ★★★★☆ | JSONL-Format pro Session, append-optimiert |
| Orphan Repair | ★★★★★ | repair_orphaned_tool_calls() injiziert synthetische Responses bei verwaisten Tool-Calls |
| Auto-Trimming | ★★★★☆ | Alte Einträge werden bei Überschreitung entfernt |
| Reset-on-Startup | ★★★★☆ | Konfigurierbar pro Environment (dev: true, prod: false) |

### 11.2 Long-Term Memory (LongTermMemoryStore)

| Aspekt | Score | Begründung |
|--------|-------|------------|
| SQLite-Backend | ★★★★☆ | 3 Tabellen: episodic, semantic, failure_journal |
| Episodic Memory | ★★★★☆ | Session-Zusammenfassungen mit Zeitstempel |
| Semantic Facts | ★★★★☆ | Key-Value-Store für User-Präferenzen |
| Failure Journal | ★★★★★ | Task → Root-Cause → Solution — wird beim Planen abgefragt |
| Session Distillation | ★★★★☆ | Automatische Extraktion in episodic/semantic nach erfolgreichen Runs |
| Refresh-Mechanismus | ★★★☆☆ | _refresh_long_term_memory_store() bei jedem run() — Performance-Overhead bei hohem Durchsatz |

### 11.3 FailureRetriever

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Similarity Search | ★★★★☆ | Sucht ähnliche Failure-Einträge für Plan-Guidance |
| Planner Integration | ★★★★★ | Direkte Injection in PlannerAgent._failure_retriever |
| Clear-All-Guardian | ★★★★★ | _clear_all() setzt ALLE Referenzen zurück inkl. planner_agent (CB-2 gefixt) |

---

## 12. Skills Engine

### 12.1 Architektur

```
SkillsService (Facade)
  ├── Discovery (SKILL.md Scanner)
  ├── Parser (SKILL.md → SkillSpec)
  ├── Eligibility (Berechtigungsprüfung)
  ├── Retrieval (Relevanz-Scoring)
  ├── Prompt (Skills→Prompt-Builder)
  └── Snapshot (Freeze für Pipeline)
```

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Feature-Flag | ★★★★★ | SKILLS_ENGINE_ENABLED + SKILLS_CANARY_ENABLED |
| Canary-Gating | ★★★★★ | Agent-ID + Model-Profile Matchers für graduelles Rollout |
| mtime-Cache | ★★★★☆ | Filesystem-Watch statt periodisches Polling |
| Discovery | ★★★★☆ | Scannt nach SKILL.md, eine Ebene tief |
| Limit Guards | ★★★★☆ | SKILLS_MAX_DISCOVERED=150, SKILLS_MAX_PROMPT_CHARS=30000 |
| Sync Control-Plane | ★★★★★ | skills.sync mit dry-run, apply, clean_target, confirm-Guard |

---

## 13. Prompt-System

### 13.1 PromptKernelBuilder

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Strukturierte Sektionen | ★★★★★ | system → policy → context → skills → tools → task |
| Versions-Hash | ★★★★★ | Reproduzierbare Prompt-Builds mit Fingerprints |
| Mode-basierte Trunkierung | ★★★★☆ | full/minimal/subagent mit konfigurierbaren Zeichenlimits |
| Section Fingerprints | ★★★★★ | Delta-Detektion zwischen Prompt-Versionen |

### 13.2 Prompt A/B Registry

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Experimentelles Framework | ★★★★☆ | A/B-Tests für Prompt-Varianten |
| Dateibasiert | ★★★☆☆ | JSON-Config; kein statistisches Significance-Tracking |

### 13.3 Context Reduction

| Bereich | Budget-Anteil |
|---------|--------------|
| Task | 25% |
| Tools | 45% |
| Memory | 35% |
| Snapshot | 15% |

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Token-Budget | ★★★★☆ | Proportionale Verteilung nach Bereich |
| Token-Schätzung | ★★★☆☆ | Regex-basiertes Wort-Counting statt echter Tokenizer — ungenau bei CJK/Emoji |
| Konfigurierbarkeit | ★★★★☆ | Anteile via Settings anpassbar |

---

## 14. Reflection & Verification

### 14.1 ReflectionService

| Aspekt | Score | Begründung |
|--------|-------|------------|
| LLM-basierte Qualitätsbewertung | ★★★★☆ | Strukturiertes ReflectionVerdict mit 7 Dimensionen |
| Task-Type-sensitive Thresholds | ★★★★★ | hard_research=0.75, research=0.70, implementation=0.65, trivial=0.40 |
| Anti-Halluzinations-Check | ★★★★★ | Factual-Grounding-Score mit Hard-Min=0.4 → erzwingt Tool-Output-Treue |
| Retry-Empfehlung | ★★★★☆ | should_retry Flag bei Score unter Schwelle |
| Konfigurierbarkeit | ★★★★★ | Threshold, Hard-Min, Tool-Results-Max-Chars, Plan-Max-Chars |

### 14.2 VerificationService

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Plan-Verifikation | ★★★★☆ | Längencheck + semantischer Coverage-Check (Wortüberlappung) |
| Tool-Result-Verifikation | ★★★☆☆ | Zeilenverankerte Regex statt Substring (Bug 3.2 verbessert), bleibt aber regelbasiert fragil |
| Final-Verifikation | ★★★★☆ | Leere/zu kurze Antworten werden erkannt |
| Semantic Coverage Threshold | ★★★★☆ | Warn-Schwelle (0.15) + konfigurierbare Hard-Fail-Schwelle |

### 14.3 ReflectionFeedbackStore

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Historische Score-Aggregation | ★★★★☆ | Durchschnitt pro Task-Type |
| Calibration Input | ★★★★☆ | Dient als Input für BenchmarkCalibrationService |

---

## 15. WebSocket-Handler & Transport

### 15.1 ws_handler.py (1428 Zeilen)

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Typed Protocol Interfaces | ★★★★★ | RuntimeManagerLike, StateStoreLike, AgentLike, OrchestratorLike, SubrunLaneLike |
| Inbound Message Types | ★★★★★ | user_message, clarification_response, runtime_switch_request, subrun_spawn, policy_decision |
| Sequenced Events | ★★★★★ | seq-Counter pro Verbindung |
| Error Classification | ★★★★★ | Differenziert: PolicyCancelled, Guardrail, Toolchain, RuntimeSwitch, LLM, Catch-All |
| Disconnect Handling | ★★★★★ | ClientDisconnectedError + Run-Failed-Marking + Queue-Drain (BUG-3/4/5 gefixt) |
| Clarification Tracking | ★★★★☆ | Pending-Clarification per Session (BUG-13/14 gefixt) |
| Queue-Management | ★★★★☆ | SessionInboxService mit Modes: wait, follow_up, steer |
| Directive Parsing | ★★★★☆ | Modell/Reasoning/Queue-Overrides aus Nachrichtentext |

### 15.2 Risiken

- **Dateigröße:** 1428 Zeilen — könnte in MessageHandler, LifecycleManager, SessionManager aufgeteilt werden
- **Event-Volumen:** Bei komplexen Runs können hunderte Events pro Verbindung entstehen

---

## 16. REST API & Control Plane

### 16.1 Core REST Endpoints

| Gruppe | Endpoints | Bewertung |
|--------|-----------|-----------|
| Runtime | GET /api/runtime/status, GET /api/runtime/features | ★★★★★ |
| Debug | GET /api/debug/prompts/resolved, GET /api/test/ping | ★★★★☆ |
| Runs | POST /api/runs/start, GET /api/runs/{id}/wait | ★★★★☆ |
| Agents | GET /api/agents, GET /api/presets | ★★★★★ |
| Custom Agents | CRUD /api/custom-agents | ★★★★☆ |
| Subruns | GET/POST /api/subruns/* | ★★★★☆ |

### 16.2 Control Plane (Modular)

| Gruppe | Endpoints | Bewertung |
|--------|-----------|-----------|
| Runs | /api/control/run.*, /api/control/runs.* | ★★★★☆ |
| Sessions | /api/control/sessions.* | ★★★★☆ |
| Workflows | /api/control/workflows.* | ★★★★☆ |
| Tools/Policy | /api/control/tools.*, /api/control/tools.policy.* | ★★★★★ |
| Approvals | /api/control/policy-approvals.* | ★★★★★ |
| Skills | /api/control/skills.* (list/preview/check/sync) | ★★★★★ |
| Diagnostics | /api/control/context.*, /api/control/config.health, /api/control/memory.overview | ★★★★★ |
| Calibration | GET /debug/calibration-recommendations | ★★★★☆ |

### 16.3 Allgemeine API-Qualität

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Router-Wiring | ★★★★☆ | Modulare Router in routers/, Wiring in main.py + control_router_wiring.py |
| Handler-Separation | ★★★★★ | Domain-Logik in handlers/*, nicht in Routern |
| Error-Responses | ★★★★☆ | Strukturierte Fehler-Events, HTTP-Status-Codes |
| Idempotenz | ★★★★☆ | Idempotency-Key-Header für Write-Endpoints |
| CORS | ★★★★★ | Konfigurierbare CORS-Mittleware |

---

## 17. State Management & Persistenz

### 17.1 StateStore (Datei-basiert)

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Run-Persistenz | ★★★★☆ | JSON-Dateien pro Run |
| Snapshots | ★★★★☆ | Summary-Snapshots für Recovery |
| Transform Pipeline | ★★★★☆ | Redaction/Truncation von sensiblen Daten |
| Cleanup | ★★★★☆ | Startup-basiert, Environment-abhängig |

### 17.2 SqliteStateStore (Optional)

| Aspekt | Score | Begründung |
|--------|-------|------------|
| WAL Mode | ★★★★★ | Write-Ahead-Logging für Concurrency |
| Sortierte list_runs | ★★★★★ | Index-basiert für schnelle Abfragen |
| Migration | ★★★☆☆ | Kein Schema-Migrations-Framework |

### 17.3 Persistiertes Dateisystem

| Artefakt | Format | Pfad |
|----------|--------|------|
| Session Memory | JSONL | MEMORY_PERSIST_DIR/*.jsonl |
| Long-Term Memory | SQLite | LONG_TERM_MEMORY_DB_PATH |
| Run State | JSON/SQLite | ORCHESTRATOR_STATE_DIR/ |
| Runtime State | JSON | RUNTIME_STATE_FILE |
| Custom Agents | JSON | CUSTOM_AGENTS_DIR/*.json |
| Subrun Registry | JSON | ORCHESTRATOR_STATE_DIR/subrun_registry.json |
| Policy Rules | JSON | ORCHESTRATOR_STATE_DIR/policy_allow_always_rules.json |
| Recovery Metrics | JSON | Pipeline-Runner-persistiert |
| Health Tracker | JSON | ModelHealthTracker-persistiert |

---

## 18. Konfiguration

### 18.1 Settings-Klasse (config.py, 1148 Zeilen)

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Umfang | ★★★★★ | ~200+ konfigurierbare Parameter über Env-Vars |
| Pydantic-Validierung | ★★★★★ | ge/le-Constraints für numerische Felder |
| Environment-Awareness | ★★★★★ | Dev vs. Prod Defaults (Reset-on-Startup etc.) |
| Prompt-Loading | ★★★★☆ | Lädt Prompt-Appendices aus app/prompts/ |
| CSV/Mapping-Parsing | ★★★★☆ | Robustes Parsing mit strip() und Fehlertoleranz |
| Pfad-Auflösung | ★★★★★ | Relative Pfade vom Workspace-Root aufgelöst |

### 18.2 Risiken

- **Monolithisch:** 1148 Zeilen, keine Sub-Model-Gruppierung — schwer navigierbar
- **Keine Hot-Reload-Validierung:** Some Settings werden bei jedem run() gelesen, andere nur beim Startup

### 18.3 Feature-Flags (Runtime-schaltbar)

| Flag | Default | Steuerbar zur Laufzeit |
|------|---------|----------------------|
| long_term_memory_enabled | false | ✅ via /api/runtime/features |
| reflection_enabled | true | ✅ |
| skills_engine_enabled | false | ✅ |
| mcp_enabled | false | ❌ (Startup) |
| vision_enabled | false | ✅ |
| web_search_enabled | false | ✅ |

---

## 19. Fehlerbehandlung & Error-Typen

### 19.1 Custom Exceptions

| Exception | Verwendung |
|-----------|-----------|
| `GuardrailViolation` | Input-/Session-/Model-Violations |
| `ToolExecutionError` | Tool-Ausführungsfehler |
| `PolicyApprovalCancelledError` | Nutzer hat Policy-Approval abgebrochen |
| `LlmClientError` | LLM-API-Fehler (HTTP, Parse, Timeout) |
| `RuntimeSwitchError` | Runtime-Wechsel fehlgeschlagen |
| `ClientDisconnectedError` | WebSocket-Disconnect |

### 19.2 Bewertung

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Error-Typisierung | ★★★★★ | Differenzierte Exception-Hierarchie |
| WS-Error-Mapping | ★★★★★ | Jeder Exception-Typ → spezifischer Error-Event-Type |
| Structured Logging | ★★★★☆ | Durchgängig Python-Logging mit kontextuellen Parametern |
| Silent Exception Swallowing | ★★★☆☆ | Einige except Exception: pass-Blöcke (Persistenz, Health-Tracker) — schwer debuggbar |

---

## 20. Concurrency & Session-Management

### 20.1 SessionLaneManager

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Global Semaphore | ★★★★★ | Begrenzt gleichzeitige Gesamtverarbeitung |
| Per-Session Locks | ★★★★★ | Verhindert parallele Verarbeitung derselben Session |
| TTL-basierte Eviction | ★★★★☆ | Idle-Lock-Bereinigung |

### 20.2 SessionInboxService

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Queue-Modes | ★★★★☆ | wait/follow_up/steer |
| Overflow-Guard | ★★★★☆ | Begrenzte Queue-Tiefe |

---

## 21. Sub-Runs & Agent-Isolation

### 21.1 SubrunLane

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Concurrency-Control | ★★★★★ | Semaphore + Limits (max concurrent, max depth, max children/parent) |
| Spawn-Modi | ★★★★☆ | run/session mit unterschiedlichen Lifecycle-Semantiken |
| Visibility Scopes | ★★★★★ | self/tree/agent/all — granulare Sichtbarkeit |
| Persistenz | ★★★★☆ | subrun_registry.json + Restore bei Neustart |
| Orphan Reconciliation | ★★★★☆ | Automatische Bereinigung nach Restore |

### 21.2 Agent Isolation

| Aspekt | Score | Begründung |
|--------|-------|------------|
| AgentIsolationPolicy | ★★★★☆ | Workspace/Skills/Credential-Scope pro Agent |
| Scope-Pair-Allowlist | ★★★★☆ | Explizite Erlaubnis für Agent-Delegationen |
| Depth-basierte Einschränkungen | ★★★★★ | spawn_subrun wird in tiefen Ebenen automatisch entzogen |
| Info-Leak-Prevention | ★★★★★ | Existence-Check vor 403/404 um Informations-Seitenkanal zu vermeiden (BUG-11 gefixt) |

---

## 22. Idempotenz

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Idempotency-Key | ★★★★☆ | Header + Payload-Fingerprint |
| TTL + Capacity | ★★★★☆ | Bounded Registry |
| Registry | ★★★☆☆ | In-Memory — nicht persistent über Neustarts |
| Fingerprint-Builder | ★★★★☆ | control_fingerprints.py für konsistente Hashes |

---

## 23. MCP Bridge

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Server-Verwaltung | ★★★★☆ | Multi-Server-Support mit Namespace-Isolation |
| Tool-Discovery | ★★★★☆ | Automatische Konvertierung von MCP-Specs in ToolSpec |
| Naming Convention | ★★★★★ | mcp_{server}_{tool} — kein Name-Clash mit internen Tools |
| Lifecycle | ★★★★☆ | Clean initialize/close |
| Schema Extraction | ★★★★☆ | JSON-Schema → required/optional Args |
| Feature-Flag | ★★★★★ | MCP_ENABLED + MCP_SERVERS Konfiguration |
| Testbarkeit | ★★★★☆ | Protocol-Interface McpConnection für Mocking |

---

## 24. Benchmarking & Eval-Gates

### 24.1 Benchmark-Pipeline

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Szenario-basiert | ★★★★★ | JSON-Szenarien mit easy/mid/hard Levels |
| WebSocket-basiert | ★★★★★ | Authentische E2E-Messung über echte WS-Verbindungen |
| Multi-Kriterien Pass/Fail | ★★★★★ | Regex-Patterns, Completion-Stages, Clarification-Responses |
| Artefakt-Persistenz | ★★★★★ | summary.md, results.json, *.events.jsonl pro Lauf |
| Reproduzierbarkeit | ★★★★☆ | Szenario-Override, deterministische Seeds |

### 24.2 Eval-Gates

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Golden Suite | ★★★★★ | 30 repräsentative Flows (success/replan/tool_loop/invalid_final) |
| Default-Gates | ★★★★★ | overall_success_rate ≥ 1.0, replan_success_rate ≥ 1.0, tool_loop ≥ 1.0, invalid_final ≤ 0.0 |
| Override via Env-Vars | ★★★★☆ | Alle Schwellen überschreibbar |
| CI-Gating | ★★★★☆ | Skript-basiert, integrierbar |

### 24.3 BenchmarkCalibrationService

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Reflection-basiert | ★★★★☆ | Empfehlungen aus historischen Reflection-Scores |
| Health-basiert | ★★★★☆ | Empfehlungen aus ModelHealthTracker-Daten |
| Recovery-basiert | ★★★★☆ | Empfehlungen aus Recovery-Metriken (CB-3 gefixt: keine No-Op-Empfehlungen mehr) |
| Export | ★★★★☆ | Env-Patch-Format für direkte Anwendung |

---

## 25. Monitoring & Observability

### 25.1 Lifecycle-Events

| Event-Kategorie | Beispiele | Bewertung |
|-----------------|-----------|-----------|
| Pipeline | planning_started/completed, tool_selection_started/completed | ★★★★★ |
| Tool | tool_started, tool_completed, tool_failed | ★★★★★ |
| Streaming | streaming_started, streaming_completed | ★★★★★ |
| Recovery | model_route_selected, model_fallback_retry | ★★★★★ |
| Skills | skills_discovered, skills_truncated, skills_skipped_canary | ★★★★★ |
| Run | run_started, run_completed, request_completed | ★★★★★ |
| Policy | policy_approval_required, policy_approval_updated | ★★★★★ |

### 25.2 Monitoring-Artefakte

| Artefakt | Format | Zweck |
|----------|--------|-------|
| eval_golden_suite.json | JSON | 30 Golden-Test-Cases |
| RECOVERY_ALERT_PROFILES.md | Markdown | Alert-Schwellen für Recovery-Metriken |
| RECOVERY_TELEMETRY_MAPPING.md | Markdown | Metriken→Alert-Mapping |
| RECOVERY_RUNBOOK.md | Markdown | Diagnose-Matrix + Eskalationsregeln |
| ws_orchestration_monitor_*.json | JSON | Historische WS-Monitoring-Snapshots |

### 25.3 Diagnostik-Endpunkte

| Endpoint | Zweck | Bewertung |
|----------|-------|-----------|
| /api/control/context.list | Token-/Segment-Schätzungen | ★★★★★ |
| /api/control/context.detail | Detailansicht eines Kontexts | ★★★★★ |
| /api/control/config.health | Config-Risikoflags | ★★★★★ |
| /api/control/memory.overview | Memory-/LTM-Übersicht | ★★★★★ |
| /api/runtime/status | Runtime-Status + Modell-Info | ★★★★★ |
| /debug/calibration-recommendations | Kalibrierungs-Empfehlungen | ★★★★☆ |

---

## 26. Test-Suite & Coverage

### 26.1 Test-Dateien (82 Module)

| Kategorie | Dateien | Beispiele |
|-----------|---------|-----------|
| Agent Core | 11 | test_agent_runtime_reconfigure, test_head_agent_replan_policy, test_planner_agent, test_synthesizer_agent, test_tool_selector_agent |
| Tool Execution | 12 | test_tool_execution_manager, test_tool_arg_validator, test_tool_call_gatekeeper, test_tool_selection_offline_eval |
| Security | 5 | test_tools_command_security, test_tools_path_traversal, test_tools_web_fetch_security, test_sandbox_isolation, test_code_sandbox |
| Policy | 3 | test_policy_approval_service, test_tool_policy_depth, test_multi_agent_isolation |
| Orchestrator | 6 | test_pipeline_runner_recovery, test_fallback_state_machine, test_recovery_strategy, test_run_state_machine, test_session_lane_manager, test_orchestrator_events |
| Memory | 5 | test_long_term_memory, test_failure_journal, test_session_distillation, test_memory_store_repair, test_memory_store_thread_safety |
| Services | 14 | test_action_parser, test_ambiguity_detector, test_circuit_breaker, test_intent_detector, test_reflection_service, test_verification_service |
| E2E | 3 | test_backend_e2e, test_backend_e2e_real_api, test_ws_handler |
| Infrastructure | 12 | test_config_validation, test_router_units, test_runtime_manager_auth, test_runtime_feature_persistence, test_model_router |
| Regression | 2 | test_bug_regressions, test_root_cause_replan |
| Skills/MCP | 5 | test_skills_service, test_mcp_bridge, test_mcp_config, test_mcp_tool_registry |
| Helpers | 2 | async_test_guards, mock_contract_guards |

### 26.2 Coverage-Gates

| Modul | Minimum Coverage |
|-------|-----------------|
| Global | ≥ 70% |
| tool_call_gatekeeper.py | ≥ 90% |
| tools.py | ≥ 80% |
| agent.py | ≥ 60% |
| pipeline_runner.py | ≥ 65% |
| tool_arg_validator.py | ≥ 95% |

### 26.3 Bewertung

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Test-Breite | ★★★★★ | 82 Dateien, jede wesentliche Komponente hat Tests |
| Kritische Pfade | ★★★★★ | Security, Policy, Recovery, E2E alle dediziert getestet |
| Regression-Tests | ★★★★★ | Explizite Bug-Regression-Suite |
| Coverage-Gates | ★★★★☆ | Kritische Module mit erhöhten Schwellen |
| Async Test Guards | ★★★★★ | receive_json_with_timeout statt blockierendem ws.receive_json() |
| Real API Tests | ★★★★☆ | Optional mit echter Ollama-API |
| Coverage-Daten | ★★☆☆☆ | coverage.json aktuell leer — kein persistierter Nachweis |

---

## 27. Code-Hygiene & Wartbarkeit

### 27.1 Dateigröße (Top-Dateien)

| Datei | Zeilen | Risiko |
|-------|--------|--------|
| agent.py | 2924 | ⚠️ HOCH — schwer zu reviewen und zu navigieren |
| tool_execution_manager.py | 1561 | ⚠️ MITTEL — umfangreicher Execution-Loop |
| ws_handler.py | 1428 | ⚠️ MITTEL — könnte aufgeteilt werden |
| pipeline_runner.py | 1256 | ⚠️ MITTEL |
| config.py | 1148 | ⚠️ MITTEL — monolithische Settings-Klasse |
| tools.py | 991 | OK |
| fallback_state_machine.py | 804 | OK |

### 27.2 Code-Qualitätsindikatoren

| Aspekt | Score | Begründung |
|--------|-------|------------|
| Statische Fehler (IDE) | ★★★★★ | 0 Errors detektiert |
| TODO/FIXME/HACK | ★★★★★ | Keine offenen Marker im Produktionscode |
| Bug-Fix-Kommentare | ★★★★★ | Alle historischen BUG-Marker als gefixt dokumentiert |
| Type Hints | ★★★★☆ | Durchgängig vorhanden, wenige Any-Typen |
| Docstrings | ★★★☆☆ | Partiell vorhanden; Services-Layer gut, Agent-Methoden spärlich |
| Import-Organisation | ★★★★☆ | Protocol-basierte Imports in ws_handler vermeiden Tight-Coupling |
| Naming Conventions | ★★★★☆ | Konsistent snake_case, klare Service-Suffixe |
| Pydantic Models | ★★★★★ | Durchgängig für Contracts, Constraints, Settings |
| Dataclasses | ★★★★★ | Frozen Dataclasses für Immutable-Datenstrukturen |

---

## 28. Bekannte Bugs & Technische Schuld

### 28.1 Behobene Bugs (Audit 2026-03-04 → 2026-03-05)

| # | Beschreibung | Status | Testing |
|---|-------------|--------|---------|
| 1 | Race Condition in create() Idempotenz | ✅ BEHOBEN | ✅ Getestet |
| 2 | allow_session genehmigt alle Tools | ✅ BEHOBEN | ✅ Getestet |
| 3 | clear_session_overrides + Disk Rules | ✅ BEHOBEN | ✅ Getestet |
| 4 | wait_for_decision ignoriert cancelled | ✅ BEHOBEN | ✅ Getestet |
| 5 | Circuit Breaker unbounded counter | ✅ BEHOBEN | ✅ Getestet |
| 6 | is_shell_command False-Positive / \ | ✅ BEHOBEN | ✅ Getestet |
| 7 | Preamble-Text vor Tool-Block verloren | ✅ BEHOBEN | ✅ Getestet |
| 8 | _TOOL_BLOCK_PATTERN Trailing NL | ✅ BEHOBEN | ✅ Getestet |
| 9 | verify_tool_result Substring-Erkennung | ⚠️ VERBESSERT | ✅ Getestet |
| 10 | parse() Extra-Felder abgelehnt | ✅ BEHOBEN | ✅ Getestet |
| 11 | is_web_research_task False-Positives | ✅ BEHOBEN | ✅ Getestet |
| 12 | looks_like_coding_request False-Positives | ✅ BEHOBEN | ✅ Getestet |
| 13 | _extract_json_payload greedy Regex | ✅ BEHOBEN | ✅ Getestet |
| 14 | _normalize_scope silent promotion | ✅ BEHOBEN | ✅ Getestet |

### 28.2 Verbleibende Tech-Debt

| ID | Severity | Beschreibung | Aufwand |
|----|----------|-------------|---------|
| N-1 | HIGH | configure_runtime() Concurrency Guard nicht vollständig wirksam | ~1h |
| N-2 | MEDIUM | _refresh_long_term_memory_store() bei jedem run() → Performance | ~30min |
| N-3 | MEDIUM | LLM-Retry nutzt lineares statt exponentielles Backoff | ~30min |
| N-4 | LOW | all_snapshots() Exception silent swallowed | ~10min |
| TD-1 | MEDIUM | agent.py 2924 Zeilen — Refactoring-Kandidat | ~4h |
| TD-2 | LOW | config.py monolithisch — Sub-Model-Gruppierung | ~2h |
| TD-3 | LOW | Token-Schätzung regex-basiert statt Tokenizer | ~2h |
| TD-4 | LOW | Idempotenz-Registry nicht persistent | ~1h |
| TD-5 | LOW | ws_handler.py 1428 Zeilen — Aufteilung möglich | ~3h |
| TD-6 | LOW | coverage.json leer — kein persistierter Nachweis | ~10min |

---

## 29. Limitierungen

### 29.1 Architekturelle Limitierungen

| Limitierung | Impact | Workaround |
|------------|--------|------------|
| Single-Process | Keine horizontale Skalierung | Vertikale Skalierung, Multi-Instanz-Deploy |
| Dateibasierte Persistenz | Begrenzte Concurrency | SQLite-Variante verwenden |
| Kein Migrations-Framework | Manuelle Schema-Updates bei SQLite | Schema-Version in StateStore prüfen |
| Kein verteiltes Locking | Multi-Instanz-Sessions ungünstig | Single-Instanz-Betrieb |

### 29.2 Agent-Limitierungen

| Limitierung | Impact | Workaround |
|------------|--------|------------|
| Deterministische Pipeline | Keine dynamische Schrittumordnung | Replan-Loop als Escape |
| Feste Replan-Limits | Kann bei sehr komplexen Tasks unzureichend sein | Limits hochsetzen via Env-Var |
| Kein Cross-Session-Lernen | Sessions isoliert | Long-Term-Memory für Persistenz nutzen |
| Token-Schätzung ungenau | CJK/Emoji-Sprachen betroffen | Echter Tokenizer integrieren |

### 29.3 Tool-Limitierungen

| Limitierung | Impact | Workaround |
|------------|--------|------------|
| 14 Kern-Tools fix | Erweiterung erfordert Code-Änderungen | MCP-Bridge für externe Tools |
| Regex-basierte Command Safety | Obfuskierte Befehle theoretisch möglich | Allowlist zusätzlich |
| Kein JS-Rendering bei web_fetch | SPAs nicht abrufbar | Headless-Browser nicht vorhanden |
| Kein Datei-Upload von extern | Feature fehlt | Workaround via web_fetch + write_file |

### 29.4 LLM-Limitierungen

| Limitierung | Impact | Workaround |
|------------|--------|------------|
| Nur OpenAI-/Ollama-kompatibel | Keine native Anthropic/Google API | OpenAI-kompatibler Proxy |
| Kein Multi-Modal (nutzbar) | Nur Text, Vision als Feature-Flag | vision_enabled aktivieren |
| Fester Streaming-Timeout | 120s/180s | Via Env-Var anpassbar |

---

## 30. Gesamtbewertung & Scorecard

### 30.1 Domänen-Scores

| Domäne | Score | Gewicht | Gewichteter Score |
|--------|-------|---------|-------------------|
| Architektur & Modularität | 9.0 | 15% | 1.35 |
| Agent-Pipeline & Determinismus | 9.0 | 12% | 1.08 |
| Fallback & Recovery | 9.5 | 10% | 0.95 |
| Tool-System & Execution | 8.5 | 10% | 0.85 |
| Sicherheit & Guardrails | 9.0 | 12% | 1.08 |
| Policy & Approval | 8.5 | 8% | 0.68 |
| Memory & State | 8.0 | 6% | 0.48 |
| Prompt-System | 8.5 | 5% | 0.43 |
| Reflection & Verification | 7.5 | 5% | 0.38 |
| Test-Suite & Coverage | 8.5 | 7% | 0.60 |
| Monitoring & Observability | 9.0 | 5% | 0.45 |
| Code-Hygiene & Wartbarkeit | 7.5 | 5% | 0.38 |
| **Gesamt** | | **100%** | **8.71 / 10** |

### 30.2 Risiko-Matrix

```
          ┌──────────────────────────────────────────────────┐
 IMPACT   │                                                  │
  HIGH    │  configure_runtime Guard (N-1)                   │
          │                                                  │
  MEDIUM  │  agent.py Größe (TD-1)    LLM Backoff (N-3)     │
          │  LTM Refresh (N-2)                               │
          │                                                  │
  LOW     │  Token-Schätzung (TD-3)   config.py Mono (TD-2) │
          │  Idempotenz (TD-4)        coverage.json (TD-6)  │
          │                                                  │
          └──────────────────────────────────────────────────┘
            LOW                MEDIUM              HIGH
                          WAHRSCHEINLICHKEIT
```

---

## 31. Priorisierter Maßnahmenplan

### Sprint 1 — Korrektheit & Sicherheit (Woche 1)

| # | Maßnahme | Aufwand | Impact |
|---|---------|--------|--------|
| 1 | N-1: configure_runtime() Guard vollständig implementieren | 1h | HIGH |
| 2 | N-3: LLM-Client exponentielles Backoff + Jitter | 30min | MEDIUM |
| 3 | TD-6: Coverage-Pipeline aktivieren, coverage.json generieren | 10min | LOW |

### Sprint 2 — Performance & Stabilität (Woche 2)

| # | Maßnahme | Aufwand | Impact |
|---|---------|--------|--------|
| 4 | N-2: LTM-Refresh-Flag statt per-run Check | 30min | MEDIUM |
| 5 | N-4: Exception-Logging in benchmark_calibration | 10min | LOW |
| 6 | verify_tool_result auf strukturiertes Parsing umstellen | 1h | MEDIUM |

### Sprint 3 — Wartbarkeit (Wochen 3–4)

| # | Maßnahme | Aufwand | Impact |
|---|---------|--------|--------|
| 7 | TD-1: agent.py refactoring — Pipeline-Steps in eigene Module extrahieren | 4h | MEDIUM |
| 8 | TD-5: ws_handler.py aufteilen (MessageHandler, LifecycleManager) | 3h | LOW |
| 9 | TD-2: config.py Sub-Model-Gruppierung einführen | 2h | LOW |
| 10 | TD-3: Token-Schätzung durch tiktoken ersetzen | 2h | LOW |

---

*Generiert am 2026-03-05. Basierend auf vollständiger Codeanalyse, fokussierten Regressionstests (66 passed / 4.31s), statischer Fehlerprüfung (0 Errors) und vorhandenen Audit-Artefakten.*
