# AI Agent Starter Kit — Umfassender Architektur-Bericht

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Systemarchitektur & Komponenten](#2-systemarchitektur--komponenten)
3. [Datenfluss (End-to-End)](#3-datenfluss-end-to-end)
4. [Agent-Architektur](#4-agent-architektur)
5. [Planning-System](#5-planning-system)
6. [Tool- & Skill-System](#6-tool---skill-system)
7. [Prompt-System](#7-prompt-system)
8. [Memory-System](#8-memory-system)
9. [LLM-Integration](#9-llm-integration)
10. [Runtime & Model Routing](#10-runtime--model-routing)
11. [Orchestrator & Pipeline](#11-orchestrator--pipeline)
12. [Selbstkorrektur & Feedback-Schleifen](#12-selbstkorrektur--feedback-schleifen)
13. [Sicherheit & Guardrails](#13-sicherheit--guardrails)
14. [Konfiguration](#14-konfiguration)
15. [Limitierungen](#15-limitierungen)
16. [Datei-Verzeichnis (backend/app/)](#16-datei-verzeichnis-backendapp)

---

## 1. Executive Summary

Das System ist ein **produktionsreifer AI-Agent-Orchestrator**, aufgebaut als FastAPI-Backend mit WebSocket-Echtzeit-Kommunikation und Angular-Frontend. Der zentrale `HeadAgent` orchestriert eine deterministische Pipeline: **Plan → Tool Selection/Execution → Synthesis**, gestützt durch Sub-Agents, eine Model-Fallback-State-Machine, ein mehrschichtiges Tool-Policy-System und eine Skills-Engine.

**Kern-Technologien:** Python 3.12+, FastAPI, Pydantic, httpx, asyncio, SQLite/JSON-Persistenz, OpenAI-kompatible LLM-API + native Ollama-API.

---

## 2. Systemarchitektur & Komponenten

### 2.1 Schichtenmodell (6 Schichten)

```
┌──────────────────────────────────────────────────────┐
│  1. Transport-Schicht                                │
│     WebSocket /ws/agent · REST-API · CORS            │
├──────────────────────────────────────────────────────┤
│  2. Agent/Orchestration-Schicht                      │
│     HeadAgent · PlannerAgent · ToolSelectorAgent     │
│     SynthesizerAgent · CustomAgentAdapter             │
├──────────────────────────────────────────────────────┤
│  3. Runtime/Model-Schicht                            │
│     RuntimeManager · ModelRouter · PipelineRunner    │
│     FallbackStateMachine · RecoveryStrategy          │
├──────────────────────────────────────────────────────┤
│  4. Persistenz/State-Schicht                         │
│     StateStore/SqliteStateStore · Memory (JSONL)     │
│     CustomAgentStore · RuntimeState (JSON)           │
├──────────────────────────────────────────────────────┤
│  5. Policy/Guardrail-Schicht                         │
│     ToolPolicyService · ToolCallGatekeeper           │
│     CommandSafetyPatterns · SSRF-Schutz              │
├──────────────────────────────────────────────────────┤
│  6. Skills-Schicht                                   │
│     SkillsService · Discovery · Eligibility          │
│     Parser · Retrieval · PromptBuilder               │
└──────────────────────────────────────────────────────┘
```

### 2.2 Registrierte Basis-Agents

| Agent-ID       | Klasse                | Rolle                        |
|----------------|-----------------------|------------------------------|
| `head-agent`   | `HeadAgentAdapter`    | Standard-Orchestrator        |
| `coder-agent`  | `CoderAgentAdapter`   | Code-optimiertes Profil      |
| `review-agent` | `ReviewAgentAdapter`  | Code-Review-Profil           |

Zusätzlich: Custom Agents (JSON-Dateien auf Disk) mit `CustomAgentAdapter` (Workflow-Steps, eigener Tool-Policy).

### 2.3 Kern-Komponenten (RuntimeComponents)

```python
@dataclass
class RuntimeComponents:
    agent_registry: dict[str, AgentContract]     # Basis-Agent-Registry
    runtime_manager: RuntimeManager              # Local/API-Switching
    state_store: StateStore                      # Run-Persistenz
    session_query_service: SessionQueryService   # Session-Abfragen
    policy_approval_service: PolicyApprovalService
    orchestrator_registry: dict[str, OrchestratorApi]
    custom_agent_store: CustomAgentStore
    subrun_lane: SubrunLane                      # Sub-Run Concurrency
```

---

## 3. Datenfluss (End-to-End)

```
User-Nachricht (WebSocket /ws/agent)
  │
  ▼
WsHandler: Session erstellen/laden, Message parsen
  │
  ▼
OrchestratorApi.run_user_message()
  ├── Session Lane erwerben (Concurrency-Control)
  ├── Tool-Policy auflösen (6-stufig)
  ├── Policy-Events emittieren
  └── PipelineRunner.run() delegieren
        │
        ▼
      ModelRouter: Modell wählen (Scoring: Health, Latenz, Kosten)
        │
        ▼
      FallbackStateMachine: INIT → SELECT_MODEL → EXECUTE_ATTEMPT
        │
        ▼
      HeadAgent.run()
        ├── 1. Guardrails prüfen
        ├── 2. Tool-Policy anwenden
        ├── 3. Memory aktualisieren
        ├── 4. Context Reduction (Token-Budget)
        ├── 5. PlannerAgent → Plan (2-5 Bullets)
        ├── 6. ToolSelectorAgent → Tool-Loop
        │     ├── Intent Detection
        │     ├── Skills Snapshot bauen
        │     ├── Tool Selection (LLM oder Function Calling)
        │     ├── Action Parsing & Validation
        │     ├── Action Augmentation (web_fetch, spawn_subrun)
        │     ├── Tool Execution (sandboxed)
        │     ├── Loop Detection (repeat, ping-pong, poll)
        │     └── Replan bei Fehler/Leer-Ergebnis
        ├── 7. SynthesizerAgent → Finale Antwort
        │     ├── Task-Type-Erkennung
        │     ├── Streaming an Client
        │     └── Section-Contract-Validierung + Self-Repair
        ├── 8. Reply Shaping (Marker entfernen, Deduplizieren)
        ├── 9. Verification (Plan, Tools, Output)
        └── 10. Final Emit → WebSocket → Client
```

---

## 4. Agent-Architektur

### 4.1 HeadAgent (agent.py, 2082 Zeilen)

Der `HeadAgent` ist der **zentrale Orchestrator**. Er implementiert die vollständige Pipeline als deterministische Sequenz und delegiert an drei Sub-Agents:

**Pipeline-Schritte:**
1. **Guardrails** — Eingabevalidierung
2. **Tool Policy** — Policy-Auflösung und -Anwendung
3. **Toolchain Check** — Verfügbarkeits-Prüfung
4. **Memory Update** — Session-Memory aktualisieren
5. **Context Reduction** — Token-Budget-basierte Kontextreduktion
6. **Planning** → `PlannerAgent`
7. **Tool Selection/Execution** → `ToolSelectorAgent` + `ToolExecutionManager`
8. **Synthesis** → `SynthesizerAgent`
9. **Reply Shaping** — Post-Processing
10. **Verification** — Qualitätsprüfung
11. **Final Emit** — Ergebnis an Client

**Replan-Logik:**
- `max_replan_iterations` — Maximale Replan-Zyklen
- `max_empty_tool_replan_attempts` — Bei leeren Tool-Ergebnissen
- `max_error_tool_replan_attempts` — Bei Tool-Fehlern
- Tool-Ergebnisse klassifiziert als: `empty`, `error_only`, `blocked`, `usable`, `steer_interrupted`

**Hooks-System:**
- `register_hook()` — Hooks für Pipeline-Events registrieren
- Policies: `hard_fail`, `soft_fail`, `skip`
- Timeout-fähig

**Agent-Varianten:**
- `CoderAgent` — Sub-Klasse mit Code-optimiertem Prompt-Profil
- `ReviewAgent` — Sub-Klasse mit Review-Prompt-Profil

### 4.2 AgentContract (contracts/agent_contract.py)

Abstrakte Basis für alle Agents:

```python
class AgentContract(ABC):
    role: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    constraints: AgentConstraints  # max_context, temperature, reasoning_depth, etc.

    async def run(user_message, send_event, session_id, request_id, model, tool_policy) -> str
    def configure_runtime(base_url, model) -> None
```

### 4.3 CustomAgentAdapter

Wraps einen Basis-Agent mit:
- **Workflow-Steps** — Instruktionen werden der User-Nachricht vorangestellt
- **Tool-Policy-Merge** — Custom Policy wird mit Basis-Policy zusammengeführt
- **Capability/Scope-Einschränkungen** — workspace_scope, skills_scope, credential_scope
- Persistenz als JSON-Dateien im `custom_agents/`-Verzeichnis

### 4.4 Sub-Agents

| Agent | Datei | Constraints | Aufgabe |
|-------|-------|-------------|---------|
| **PlannerAgent** | `agents/planner_agent.py` | max_context=4096, temp=0.2, reasoning=2 | Erstellt Ausführungsplan (2-5 Bullets) |
| **ToolSelectorAgent** | `agents/tool_selector_agent.py` | max_context=4096, temp=0.1, reasoning=1 | Delegiert Tool-Auswahl und -Ausführung |
| **SynthesizerAgent** | `agents/synthesizer_agent.py` | max_context=8192, temp=0.3, reasoning=2 | Generiert finale Antwort mit Streaming |

---

## 5. Planning-System

### 5.1 PlannerAgent

- Erstellt einen **kurzen Ausführungsplan (2-5 Bullets)** basierend auf der Benutzeranfrage
- **Adaptive Planung**: Einfache Anfragen → minimaler Plan; technische Anfragen → detaillierte Implementierungsschritte
- Verwendet `PromptKernelBuilder` für strukturierten Prompt-Aufbau
- **Hard Contract**: Für spezifische Research-Anfragen (Architektur-Risiken, Performance-Hotspots etc.) wird ein verbindlicher Ausgabe-Schema erzwungen

### 5.2 Replan-Mechanismus

Der `HeadAgent` implementiert eine Replan-Schleife:
1. Tool-Ergebnisse werden klassifiziert (`empty`, `error_only`, `blocked`, `usable`)
2. Bei `empty` oder `error_only` → erneute Tool-Auswahl mit angepasstem Kontext
3. Maximale Iterationen konfigurierbar
4. Bei `steer_interrupted` → sofortiger Abbruch der Tool-Schleife

### 5.3 Task-Type-Erkennung (SynthesizerAgent)

Der SynthesizerAgent erkennt automatisch den Task-Type:
- **hard_research** — Tiefe technische Analyse mit vorgegebenem Schema
- **research** — Web-Research mit Quellenangaben
- **orchestration** — Multi-Agent-Delegation
- **implementation** — Code-Implementierung
- **general** — Allgemeine Anfragen

Jeder Task-Type bekommt einen eigenen **Section Contract** mit obligatorischen Abschnitten.

---

## 6. Tool- & Skill-System

### 6.1 Verfügbare Tools (14 Kern-Tools)

| Tool | Beschreibung | Kategorie |
|------|-------------|-----------|
| `list_dir` | Verzeichnis auflisten | filesystem_read |
| `read_file` | Datei lesen | filesystem_read |
| `write_file` | Datei schreiben | filesystem_write |
| `apply_patch` | Patch auf Datei anwenden | filesystem_write |
| `file_search` | Dateien nach Glob-Pattern suchen | filesystem_read |
| `grep_search` | Textsuche in Dateien | filesystem_read |
| `list_code_usages` | Code-Referenzen finden | filesystem_read |
| `get_changed_files` | Geänderte Dateien (git) auflisten | filesystem_read |
| `run_command` | Shell-Befehl ausführen | command_execution |
| `start_background_command` | Hintergrund-Prozess starten | command_execution |
| `get_background_output` | Hintergrund-Prozess-Output lesen | command_execution |
| `kill_background_process` | Hintergrund-Prozess beenden | command_execution |
| `web_fetch` | Webseite abrufen (mit SSRF-Schutz) | web_retrieval |
| `spawn_subrun` | Sub-Agent-Run starten | orchestration |

**Tool-Aliase:** `createfile` → `write_file`, `webfetch` → `web_fetch` etc.

### 6.2 Tool Execution Pipeline

```
LLM-Antwort → Action Parser → Validation → Policy Check → Execution → Loop Detection
                                    ↓                           ↓
                              Blocked? → encode_blocked    Error? → Retry/Replan
```

**ToolExecutionManager** (1561 Zeilen) orchestriert:
1. **Intent Detection** — Erkennt Benutzerabsicht (execute_command, web_research, etc.)
2. **Capability Preselection** — Filtert Tools nach benötigten Capabilities
3. **Skills Snapshot** — Baut Skills-Kontext für Tool-Auswahl
4. **Retrieval Service** — Relevante Skills-Quellen abrufen
5. **Tool Selection** — LLM-basiert oder Function Calling
6. **Action Parsing** — Extrahiert Tool-Calls aus LLM-Antwort
7. **Action Augmentation** — Fügt `web_fetch` oder `spawn_subrun` hinzu
8. **Validation** — Argument-Validierung, Policy-Check
9. **Execution** — Sandboxed mit Workspace-Path-Beschränkung
10. **Loop Detection** — Erkennt: generic_repeat, ping_pong, poll_no_progress

### 6.3 Tool Policy System (6-stufig)

Auflösungsreihenfolge (deny überschreibt allow):

```
1. Global Policy
2. Tool Profile (minimal, coding, review)
3. Preset Policy (research, review)
4. Provider Policy (local → allow commands; api → deny background)
5. Model-specific Policy
6. Agent Depth Policy + Request Override
```

### 6.4 Skills Engine

**Architektur:**
- `SkillsService` — Facade mit mtime-basiertem Cache
- `skills/discovery.py` — Scannt nach SKILL.md-Dateien (eine Ebene tief)
- `skills/eligibility.py` — Filtert berechtigte Skills
- `skills/parser.py` — Parst SKILL.md-Inhalte
- `skills/prompt.py` — Baut Skills-Prompt
- `skills/retrieval.py` — Retrieval-Service mit Relevanz-Scoring

**Verfügbare Skills (openagent/skills/):** 72+ Skills darunter:
- **Kommunikation:** slack, voice-call
- **Produktivität:** trello, things-mac, github
- **Medien:** spotify-player, video-frames, songsee, gifgrep
- **System:** tmux, blucli, wacli, sonoscli
- **Web:** xurl, summarize
- **Wetter:** weather
- und viele mehr

**Canary-Gating:** Skills können per Feature-Flag schrittweise aktiviert werden.

---

## 7. Prompt-System

### 7.1 PromptKernelBuilder

Baut strukturierte Prompts mit:
- **Versions-Hash** und **Section-Fingerprints** für Reproduzierbarkeit
- **Geordnete Sektionen:** system → policy → context → skills → tools → task
- **Mode-basierte Trunkierung:**
  - `full` — unbegrenzt
  - `minimal` — max 1400 Zeichen
  - `subagent` — max 900 Zeichen

### 7.2 Prompt-Profile (PromptProfile)

Jede Agent-Variante hat eigene Prompts:

```python
@dataclass
class PromptProfile:
    system: str          # System-Prompt
    plan: str            # Planner-Instruktionen
    tool_selector: str   # Tool-Auswahl-Instruktionen
    tool_repair: str     # Tool-Reparatur-Prompt
    final: str           # Synthese-Prompt
```

Konfiguration über Umgebungsvariablen mit Fallback-Ketten:
- `HEAD_AGENT_SYSTEM_PROMPT` → `AGENT_SYSTEM_PROMPT` → Default
- `CODER_AGENT_SYSTEM_PROMPT` → `HEAD_AGENT_SYSTEM_PROMPT` → Default

### 7.3 Context Reduction

`ContextReducer` verwaltet Token-Budgets:

| Bereich | Budget-Anteil |
|---------|--------------|
| Task    | 25%          |
| Tools   | 45%          |
| Memory  | 35%          |
| Snapshot | 15%         |

Token-Schätzung via Regex-basiertes Wort-Counting.

---

## 8. Memory-System

### 8.1 Session Memory (memory.py)

- **Format:** JSONL-Dateien (eine pro Session)
- **Thread-safe:** RLock-basiert
- **Auto-Trimming:** Alte Einträge werden entfernt wenn `max_items` überschritten
- **API:**
  - `add(session_id, content)` — Eintrag hinzufügen
  - `render_context(session_id)` — Gesamtkontext als String
  - `get_items(session_id)` — Alle Items abrufen
  - `clear_all()` — Alle Sessions löschen

### 8.2 State Store

- **StateStore** — JSON-basierte Persistenz für Runs, Sessions
- **SqliteStateStore** — SQLite-Backend (konfigurierbar)
- **Snapshots** — State-Snapshots für Recovery
- **TaskGraph** — Aufgaben-Graph-Verwaltung

---

## 9. LLM-Integration

### 9.1 LlmClient (llm_client.py)

Unterstützt zwei API-Modi:
1. **OpenAI-kompatible API** — Standard-Chat-Completions
2. **Native Ollama API** — Auto-Detection wenn `base_url` auf `/api` endet

**Methoden:**
- `stream_chat_completion()` — Streaming-Antwort (SSE)
- `complete_chat()` — Non-Streaming-Completion
- `complete_chat_with_tools()` — Function Calling

**Retry-Logik:**
- 3 Retries für 429 (Rate Limit) und 5xx (Server-Fehler)
- 0.8s Base-Delay mit Backoff
- 120s Timeout

**Auth:** Bearer-Token aus Settings (`API_AUTH_TOKEN`)

### 9.2 Function Calling

- Tool-Registry baut OpenAI-konforme Function-Calling-Definitionen
- ToolSelector kann zwischen LLM-Text-Parsing und nativem Function Calling wählen
- Konfigurierbar via `tool_selection_function_calling_enabled`

---

## 10. Runtime & Model Routing

### 10.1 RuntimeManager

- **Dual Runtime:** Local (Ollama) ↔ API-basiert
- **Persistenz:** JSON-Datei für Runtime-State
- **Model Pulling:** Automatisches Herunterladen von Ollama-Modellen
- **Rollback:** Bei Fehler Zurückwechseln zur vorherigen Runtime
- **API Auth Guard:** `API_AUTH_REQUIRED` / `API_AUTH_TOKEN`

### 10.2 ModelRouter

**Scoring-basierte Modellauswahl:**

```
Score = Health × w_h + (1 - Latency_norm) × w_l + (1 - Cost_norm) × w_c
        + Runtime_bonus + Reasoning_bonus
```

**Reasoning-Level:**
- `low` — Schnelle, einfache Aufgaben
- `medium` — Standard
- `high` — Komplexe Aufgaben
- `ultrathink` — Maximale Reasoning-Tiefe
- `adaptive` — Dynamisch basierend auf Aufgabe

### 10.3 FallbackStateMachine

Explizite State-Machine für Model-Fallback:

```
INIT → SELECT_MODEL → EXECUTE_ATTEMPT → HANDLE_SUCCESS → done
                                       └→ HANDLE_FAILURE → SELECT_MODEL (retry)
                                                         └→ FINALIZE_FAILURE
```

**Recovery-Strategien (RecoveryStrategyResolver):**
- Prompt Compaction
- Context Overflow Retry
- Payload Truncation
- Overflow Fallback Retry

---

## 11. Orchestrator & Pipeline

### 11.1 OrchestratorApi

High-Level-Facade:
1. Message in Queue einreihen
2. Session Lane erwerben (Concurrency-Control)
3. Tool-Policy auflösen (6-stufig)
4. Policy-Events emittieren
5. `PipelineRunner.run()` delegieren

### 11.2 PipelineRunner

- Model-Routing via `ModelRouter`
- Adaptive Inference anwenden
- Context Window Guards
- `FallbackStateMachine` orchestrieren
- Recovery-Metriken persistieren

### 11.3 Session Lane Manager

- **Global Semaphore** — Begrenzt gleichzeitige Verarbeitung
- **Per-Session Locks** — Verhindert parallele Verarbeitung derselben Session
- **Idle Eviction** — TTL-basierte Lock-Bereinigung

### 11.4 SubrunLane

- Concurrency-Control für Sub-Runs
- Max concurrent, max spawn depth, max children per parent
- Orphan-Reconciliation
- Leaf spawn depth guard

### 11.5 Run State Machine

```
received → queued → planning → tool_loop → synthesis → finalizing → persisted
                                                                      ↓
                                                            completed / failed / cancelled
```

Forward-only State-Progression erzwungen.

---

## 12. Selbstkorrektur & Feedback-Schleifen

### 12.1 Tool-Level

1. **Tool Repair:** Bei fehlerhafter Tool-Auswahl → LLM-basierte JSON-Reparatur
2. **Replan:** Bei leeren/fehlerhaften Ergebnissen → erneute Planung + Tool-Auswahl
3. **Loop Detection:** Erkennt repetitive Muster:
   - `generic_repeat` — Gleicher Tool-Call wiederholt
   - `ping_pong` — Wechselnde Tool-Calls ohne Fortschritt
   - `poll_no_progress` — Polling ohne Ergebnis-Änderung

### 12.2 Synthesis-Level

1. **Section Contract Validation:** Prüft ob alle obligatorischen Abschnitte vorhanden sind
2. **Self-Repair:** Bei fehlenden Abschnitten → LLM generiert reparierte Version
3. **Hard Research Validation:** Spezielle Prüfung für strukturierte Research-Antworten:
   - Alle 6 Pflicht-Sektionen vorhanden?
   - Top-10-Nummerierung vollständig?
   - Phase 1/2/3 im Rollout-Plan?
   - KPI-Zeilen mit messbaren Werten?

### 12.3 Pipeline-Level

1. **Model Fallback:** Bei LLM-Fehler → nächstes Modell aus Fallback-Kette
2. **Recovery Strategy:** Context Overflow → Compaction → Truncation → Retry
3. **Verification Service:** Prüft Qualität von Plan, Tool-Ergebnissen und Final-Output

### 12.4 Hooks-System

- Events an registrierte Hooks emittieren (z.B. `before_prompt_build`)
- Policies: `hard_fail` (Exception bei Hook-Fehler), `soft_fail` (loggen), `skip`

---

## 13. Sicherheit & Guardrails

### 13.1 Command Safety

- **COMMAND_SAFETY_PATTERNS** — Regex-basierte Erkennung gefährlicher Befehle
- **Command Allowlist** — Nur erlaubte Befehle (konfigurierbar)
- **Blocked Leaders** — Liste verbotener Befehlspräfixe
- **Semantic Safety Check** — PowerShell-Inline-Pattern-Erkennung

### 13.2 Web Fetch Security (SSRF-Schutz)

- Blockiert: localhost, Metadata-Endpoints, nicht-öffentliche IPs
- Redirect-Limit
- Content-Type-Blocking
- Max Download Size
- HTML → Text Normalisierung

### 13.3 Workspace Sandboxing

- Alle Datei-Operationen auf konfigurierten Workspace-Pfad beschränkt
- Path-Traversal-Schutz

### 13.4 Agent Isolation

- `AgentIsolationPolicy` definiert Isolations-Profile
- Workspace-Scope, Skills-Scope, Credential-Scope pro Agent

### 13.5 Policy Approval Service

- Dynamische Policy-Übersteuerung mit Approval-Workflow
- Blocked-Tool-Freigabe auf Anfrage

---

## 14. Konfiguration

### 14.1 Zentrale Konfiguration (config.py, ~150+ Env-Vars)

Kategorien:

| Kategorie | Beispiel-Variablen |
|-----------|-------------------|
| **LLM** | `OLLAMA_BASE_URL`, `API_BASE_URL`, `DEFAULT_MODEL` |
| **Prompts** | `HEAD_AGENT_SYSTEM_PROMPT`, `CODER_AGENT_SYSTEM_PROMPT` |
| **Workspace** | `WORKSPACE_DIR`, `CUSTOM_AGENTS_DIR` |
| **Memory** | `MEMORY_MAX_ITEMS`, `MEMORY_DIR` |
| **Orchestrator** | `ORCHESTRATOR_STATE_BACKEND`, `ORCHESTRATOR_STATE_DIR` |
| **Skills** | `SKILLS_ENGINE_ENABLED`, `SKILLS_CANARY_ENABLED`, `SKILLS_MAX_DISCOVERED` |
| **Tool Policy** | `TOOL_POLICY_PRESET`, `COMMAND_ALLOWLIST` |
| **Subruns** | `SUBRUN_MAX_CONCURRENT`, `SUBRUN_MAX_SPAWN_DEPTH` |
| **Session** | `SESSION_LANE_GLOBAL_CONCURRENCY`, `SESSION_LOCK_TTL` |
| **Hooks** | Hook-Konfiguration |
| **Idempotency** | `IDEMPOTENCY_REGISTRY_TTL_SECONDS`, `IDEMPOTENCY_REGISTRY_MAX_ENTRIES` |
| **Loop Detection** | `LOOP_DETECT_GENERIC_REPEAT`, `LOOP_DETECT_PING_PONG` |
| **Context Window** | Context Window Guard Einstellungen |
| **Adaptive Inference** | Adaptive Inference Einstellungen |
| **Pipeline Recovery** | Recovery-bezogene Einstellungen |

### 14.2 Prompt-Auflösung

`_resolve_prompt()` mit Env-Var-Fallback-Ketten:
```
CODER_AGENT_SYSTEM_PROMPT → HEAD_AGENT_SYSTEM_PROMPT → AGENT_SYSTEM_PROMPT → Default
```

---

## 15. Limitierungen

### 15.1 Architekturelle Limitierungen

1. **Single-Process:** Kein verteiltes Clustering, keine horizontale Skalierung
2. **Datei-basierte Persistenz:** Primär JSON/JSONL auf Disk (SQLite optional) — nicht für High-Concurrency optimiert
3. **Token-Schätzung:** Regex-basiertes Wort-Counting statt echter Tokenizer — Ungenauigkeit bei nicht-lateinischen Sprachen
4. **Synchrones Memory-Locking:** RLock kann bei hoher Last zum Bottleneck werden

### 15.2 Agent-Limitierungen

1. **Deterministische Pipeline:** Keine dynamische Umordnung von Schritten
2. **Replan-Limits:** Feste maximale Iterationen können bei komplexen Aufgaben unzureichend sein
3. **Sub-Agent-Tiefe:** `subrun_max_spawn_depth` begrenzt Delegations-Ketten
4. **Keine persistente Agent-Lernfähigkeit:** Kein langfristiges Lernen über Sessions hinweg

### 15.3 Tool-Limitierungen

1. **14 Kern-Tools:** Erweiterung erfordert Code-Änderungen in `tools.py` und `tool_catalog.py`
2. **Command Safety:** Regex-basiert — kann bei obfuskierten Befehlen umgangen werden
3. **Web Fetch:** Nur text-basierte Inhalte, kein JavaScript-Rendering
4. **Keine Datei-Upload/Download-Funktionalität** von externen Quellen

### 15.4 LLM-Limitierungen

1. **Provider-Abhängigkeit:** OpenAI-kompatible API oder Ollama — keine native Anthropic/Google-API
2. **Keine Multi-Modal-Unterstützung:** Nur Text-basierte Interaktion
3. **Retry-Logik:** Einfacher exponentieller Backoff, kein Circuit-Breaker-Pattern
4. **Streaming-Timeout:** Fest konfiguriert (120s/180s für Research)

---

## 16. Datei-Verzeichnis (backend/app/)

### Kern-Dateien

| Datei | Zeilen | Zweck |
|-------|--------|-------|
| [agent.py](backend/app/agent.py) | 2082 | HeadAgent — zentraler Orchestrator, vollständige Pipeline |
| [config.py](backend/app/config.py) | 791 | Zentrale Konfiguration, ~150+ Env-Vars, Pydantic Settings |
| [tools.py](backend/app/tools.py) | 678 | AgentTooling — 14 Tool-Implementierungen |
| [ws_handler.py](backend/app/ws_handler.py) | 1122 | WebSocket-Handler, Message-Lifecycle |
| [main.py](backend/app/main.py) | 701 | FastAPI-App, CORS, Lifespan, Router-Registrierung |
| [llm_client.py](backend/app/llm_client.py) | 451 | LLM API Client (OpenAI + Ollama) |
| [runtime_manager.py](backend/app/runtime_manager.py) | 375 | Runtime-Switching (local ↔ API) |
| [memory.py](backend/app/memory.py) | ~100 | JSONL Session Memory Store |
| [models.py](backend/app/models.py) | ~80 | WS Inbound Message Types |
| [control_models.py](backend/app/control_models.py) | ~200 | Control-Plane Request Models |
| [custom_agents.py](backend/app/custom_agents.py) | ~200 | Custom Agent Definitions & Adapter |
| [tool_catalog.py](backend/app/tool_catalog.py) | ~50 | Tool-Name-Registry & Aliase |
| [run_endpoints.py](backend/app/run_endpoints.py) | ~150 | REST Run-Endpoint-Handler |
| [app_state.py](backend/app/app_state.py) | ~100 | RuntimeComponents, LazyProxy |
| [app_setup.py](backend/app/app_setup.py) | — | FastAPI-App-Builder |
| [errors.py](backend/app/errors.py) | — | Error-Typen (GuardrailViolation, etc.) |
| [control_router_wiring.py](backend/app/control_router_wiring.py) | — | Router-Wiring-Utilities |
| [runtime_debug_endpoints.py](backend/app/runtime_debug_endpoints.py) | — | Debug-Endpoints |
| [startup_tasks.py](backend/app/startup_tasks.py) | — | Startup-Task-Execution |
| [subrun_endpoints.py](backend/app/subrun_endpoints.py) | — | Subrun REST Endpoints |
| [tool_policy.py](backend/app/tool_policy.py) | — | ToolPolicyDict Type & Normalisierung |

### agents/ — Sub-Agent-Implementierungen

| Datei | Zweck |
|-------|-------|
| [planner_agent.py](backend/app/agents/planner_agent.py) | PlannerAgent — Ausführungsplan (2-5 Bullets) |
| [tool_selector_agent.py](backend/app/agents/tool_selector_agent.py) | ToolSelectorAgent — Tool-Auswahl-Delegation |
| [synthesizer_agent.py](backend/app/agents/synthesizer_agent.py) | SynthesizerAgent — Finale Antwort mit Streaming & Self-Repair |
| [tool_selector_legacy.py](backend/app/agents/tool_selector_legacy.py) | Legacy Runner Binding |
| [head_agent_adapter.py](backend/app/agents/head_agent_adapter.py) | Adapter für HeadAgent/CoderAgent/ReviewAgent |

### contracts/ — Verträge & Schemas

| Datei | Zweck |
|-------|-------|
| [agent_contract.py](backend/app/contracts/agent_contract.py) | AgentContract ABC, AgentConstraints |
| [schemas.py](backend/app/contracts/schemas.py) | PlannerInput/Output, ToolSelectorInput/Output, SynthesizerInput/Output |
| [tool_protocol.py](backend/app/contracts/tool_protocol.py) | Tool-Protokoll-Definition |
| [tool_selector_runtime.py](backend/app/contracts/tool_selector_runtime.py) | ToolSelectorRuntime Interface |

### orchestrator/ — Pipeline & State Machine

| Datei | Zeilen | Zweck |
|-------|--------|-------|
| [pipeline_runner.py](backend/app/orchestrator/pipeline_runner.py) | 1220 | Model-Routing, Context Guards, FallbackStateMachine |
| [fallback_state_machine.py](backend/app/orchestrator/fallback_state_machine.py) | 661 | Model-Fallback State Machine |
| [recovery_strategy.py](backend/app/orchestrator/recovery_strategy.py) | 274 | Recovery-Strategie-Resolver |
| [events.py](backend/app/orchestrator/events.py) | ~150 | Lifecycle Event Builder |
| [run_state_machine.py](backend/app/orchestrator/run_state_machine.py) | ~100 | Run State Contract |
| [step_executors.py](backend/app/orchestrator/step_executors.py) | ~50 | Step-Executor Wrappers |
| [session_lane_manager.py](backend/app/orchestrator/session_lane_manager.py) | ~120 | Session Concurrency Control |
| [subrun_lane.py](backend/app/orchestrator/subrun_lane.py) | — | Sub-Run Lane Management |

### services/ — Business-Services (22 Module)

| Datei | Zeilen | Zweck |
|-------|--------|-------|
| [tool_execution_manager.py](backend/app/services/tool_execution_manager.py) | 1561 | Tool-Execution-Loop, Skills-Injection, Loop-Detection |
| [tool_policy_service.py](backend/app/services/tool_policy_service.py) | 407 | 6-stufige Tool-Policy-Auflösung |
| [tool_registry.py](backend/app/services/tool_registry.py) | 443 | Tool-Spezifikations-Registry, Function-Calling-Builder |
| [intent_detector.py](backend/app/services/intent_detector.py) | 350 | Intent-Erkennung & Command-Extraktion |
| [prompt_kernel_builder.py](backend/app/services/prompt_kernel_builder.py) | ~200 | Strukturierter Prompt-Builder mit Versionierung |
| [action_augmenter.py](backend/app/services/action_augmenter.py) | 284 | Intent-basierte Tool-Action-Erweiterung |
| [reply_shaper.py](backend/app/services/reply_shaper.py) | 203 | Antwort-Post-Processing, Section-Contract-Validierung |
| [verification_service.py](backend/app/services/verification_service.py) | ~150 | Qualitäts-Verifikation (Plan, Tools, Output) |
| [agent_resolution.py](backend/app/services/agent_resolution.py) | — | Agent-Auflösung, Capability-Routing |
| [agent_isolation.py](backend/app/services/agent_isolation.py) | — | Agent-Isolationsprofile |
| [session_inbox_service.py](backend/app/services/session_inbox_service.py) | — | Session-Inbox-Queuing |
| [session_query_service.py](backend/app/services/session_query_service.py) | — | Session-Abfragen |
| [policy_approval_service.py](backend/app/services/policy_approval_service.py) | — | Policy-Approval-Workflows |
| [idempotency_manager.py](backend/app/services/idempotency_manager.py) | — | Idempotenz-Management |
| [idempotency_service.py](backend/app/services/idempotency_service.py) | — | Idempotenz-Service |
| [action_parser.py](backend/app/services/action_parser.py) | — | Tool-Action-Parsing aus LLM-Text |
| [directive_parser.py](backend/app/services/directive_parser.py) | — | Direktiven-Parser |
| [tool_arg_validator.py](backend/app/services/tool_arg_validator.py) | — | Tool-Argument-Validierung |
| [tool_call_gatekeeper.py](backend/app/services/tool_call_gatekeeper.py) | — | Tool-Call-Gatekeeper |
| [hook_contract.py](backend/app/services/hook_contract.py) | — | Hook-Verträge |
| [control_fingerprints.py](backend/app/services/control_fingerprints.py) | — | Fingerprint-Builder für Idempotenz |
| [request_normalization.py](backend/app/services/request_normalization.py) | — | Request-Normalisierung |

### skills/ — Skills Engine (8 Module)

| Datei | Zweck |
|-------|-------|
| [service.py](backend/app/skills/service.py) | Skills-Service-Facade mit mtime-Cache |
| [discovery.py](backend/app/skills/discovery.py) | SKILL.md-Datei-Scanner |
| [eligibility.py](backend/app/skills/eligibility.py) | Skill-Berechtigungsprüfung |
| [parser.py](backend/app/skills/parser.py) | SKILL.md-Parser |
| [prompt.py](backend/app/skills/prompt.py) | Skills-Prompt-Builder |
| [retrieval.py](backend/app/skills/retrieval.py) | Relevanz-basierter Retrieval-Service |
| [snapshot.py](backend/app/skills/snapshot.py) | Skills-Snapshot-Modelle |
| [models.py](backend/app/skills/models.py) | Skills-Datenmodelle |

### model_routing/ — Modell-Routing

| Datei | Zweck |
|-------|-------|
| [router.py](backend/app/model_routing/router.py) | ModelRouter mit Scoring-Algorithmus |
| [model_registry.py](backend/app/model_routing/model_registry.py) | Modell-Registry |
| [capability_profile.py](backend/app/model_routing/capability_profile.py) | Modell-Capability-Profile |
| [context_window_guard.py](backend/app/model_routing/context_window_guard.py) | Context Window Guards |

### state/ — State Management

| Datei | Zweck |
|-------|-------|
| [state_store.py](backend/app/state/state_store.py) | StateStore (JSON) / SqliteStateStore |
| [context_reducer.py](backend/app/state/context_reducer.py) | Token-budgetierte Kontext-Reduktion |
| [snapshots.py](backend/app/state/snapshots.py) | State-Snapshots |
| [task_graph.py](backend/app/state/task_graph.py) | Task-Graph-Verwaltung |

### interfaces/ — API-Schnittstellen

| Datei | Zweck |
|-------|-------|
| [orchestrator_api.py](backend/app/interfaces/orchestrator_api.py) | OrchestratorApi High-Level-Facade |
| [request_context.py](backend/app/interfaces/request_context.py) | Request-Kontext-Modell |

### handlers/ — Domain-Handler

| Datei | Zweck |
|-------|-------|
| [agent_handlers.py](backend/app/handlers/agent_handlers.py) | Agent CRUD |
| [policy_handlers.py](backend/app/handlers/policy_handlers.py) | Policy-Verwaltung |
| [run_handlers.py](backend/app/handlers/run_handlers.py) | Run-Verwaltung |
| [session_handlers.py](backend/app/handlers/session_handlers.py) | Session-Verwaltung |
| [skills_handlers.py](backend/app/handlers/skills_handlers.py) | Skills-Verwaltung |
| [tools_handlers.py](backend/app/handlers/tools_handlers.py) | Tool-Verwaltung |
| [workflow_handlers.py](backend/app/handlers/workflow_handlers.py) | Workflow-Verwaltung |

### routers/ — FastAPI Router

| Datei | Zweck |
|-------|-------|
| [ws_agent.py](backend/app/routers/ws_agent.py) | WebSocket `/ws/agent` Router |
| [run_api.py](backend/app/routers/run_api.py) | REST Run API Router |
| [agents.py](backend/app/routers/agents.py) | Agent Management Router |
| [subruns.py](backend/app/routers/subruns.py) | Subruns Router |
| [control_*.py](backend/app/routers/) | Control-Plane Router (sessions, tools, skills, policies, workflows) |

---

*Generiert am: $(date). Basierend auf vollständiger Analyse aller Kern-Dateien im Repository.*
