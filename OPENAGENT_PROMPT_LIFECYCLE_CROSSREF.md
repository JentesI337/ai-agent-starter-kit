# OpenAgent Deep Analysis (Prompt -> Lifecycle -> Response) + Cross-Reference zu `backend/app/agent.py`

## Scope / was explizit analysiert wurde

Diese Analyse fokussiert **nur** auf:
1. Prompt-Ingestion und Prompt-Build
2. Laufzeit-Lifecycle (Start, Streaming, Toolausführung, End/Error)
3. Response-Erzeugung und Auslieferung
4. Agent Agency, Toolchaining, Subagent-Orchestrierung, Hooking

Explizit **ausgenommen** (deine Vorgabe):
- Heartbeat-Mechaniken
- Memory/History-Features als eigenes Thema

Hinweis: Einige Dateien enthalten diese Themen trotzdem; sie werden hier nur erwähnt, wenn sie den Prompt->Lifecycle->Response-Flow unmittelbar beeinflussen.

---

## 1) OpenAgent: End-to-End-Fluss (Prompt -> Lifecycle -> Response)

## 1.1 Entry Points (Request Acceptance)

### Gateway RPC (`agent`, `agent.wait`)
- Haupt-RPC befindet sich in `src/gateway/server-methods/agent.ts`.
- `agent` validiert Parameter, löst Session/Agent-Zuordnung auf, dedupliziert über `idempotencyKey`, antwortet früh mit `accepted` (`runId`) und startet den Run asynchron.
- `agent.wait` wartet auf Lifecycle-Terminalzustand (`ok`, `error`, `timeout`) via `waitForAgentJob` in `src/gateway/server-methods/agent-job.ts`.

### CLI Entry
- `src/commands/agent.ts` (`agentCommand`) ist der Embedded-Run-Pfad.
- Optionaler Gateway-Transport in `src/commands/agent-via-gateway.ts` (`agentViaGatewayCommand`), fallback auf embedded bei Fehler.

### Alternative Agent-Runtimes in OpenAgent
OpenAgent hat mehrere Laufpfade für „Agent-Run“:
1. **Embedded Pi Runtime** (Standard): `runEmbeddedPiAgent`
2. **ACP Runtime**: via ACP Session Manager in `agentCommand`
3. **CLI-Provider Runtime**: `runCliAgent` branch in `runAgentAttempt`

Das ist wichtig für „Agency“: OpenAgent ist nicht 1 Laufmodell, sondern ein Router über mehrere Agent-Ausführungsmodi.

---

## 1.2 Prompt-Build (OpenAgent)

Der eigentliche Prompt-Build passiert im Embedded-Kern:
- `src/agents/pi-embedded-runner/run/attempt.ts` (`runEmbeddedAttempt`)

### Prompt-Komponenten
OpenAgent baut den finalen System-/Prompt-Kontext aus mehreren Quellen zusammen:
- User-Prompt (`params.prompt`)
- System Prompt Generator (`buildEmbeddedSystemPrompt`)
- Workspace/Bootstrap-Kontextfiles (`resolveBootstrapContextForRun`)
- Skills Prompt (`resolveSkillsPromptForRun`)
- Runtime/System-Metadaten (OS, Shell, Channel, Model etc.)
- Channel-spezifische Capability-/Action-Hinweise
- Sandbox-Status
- optionales `extraSystemPrompt`
- Hook-Injektionen (`before_prompt_build` + Legacy `before_agent_start`)

### Hook-Order im Prompt-Bereich
1. Früher Model-Resolve-Hook (`before_model_resolve`) in `run.ts`
2. Prompt-Build Hook (`before_prompt_build`) in `run/attempt.ts`
3. Legacy-Kompatibilität (`before_agent_start`) für beide Phasen

### System Prompt Override
- Über Hooks kann `systemPrompt` direkt ersetzt werden (nicht nur prepend).
- Prompt-Prepend wird explizit vor User-Text gesetzt.

---

## 1.3 Lifecycle-Orchestrierung (OpenAgent)

## Queueing / Serialization
- Session-Lane + Global-Lane (`resolveSessionLane`, `resolveGlobalLane`) in `src/agents/pi-embedded-runner/lanes.ts`.
- `runEmbeddedPiAgent` läuft über diese Queues -> deterministische Session-Serialisierung.

## Active Run Registry
- `src/agents/pi-embedded-runner/runs.ts`:
  - aktive Runs pro Session
  - `queueEmbeddedPiMessage` (Steering während Streaming)
  - `abortEmbeddedPiRun`
  - `waitForEmbeddedPiRunEnd`

## Lifecycle Events
- Event-Mapping passiert in `src/agents/pi-embedded-subscribe.handlers.lifecycle.ts`:
  - `agent_start` -> Lifecycle `start`
  - `agent_end` normal -> Lifecycle `end`
  - `agent_end` mit assistant error -> Lifecycle `error`

## Streaming Event-Klassen
- `assistant` Stream
- `tool` Stream (`start/update/result`)
- `lifecycle` Stream (`start/end/error`)
- zusätzlich reasoning/thinking stream intern (wenn aktiviert)

## Abort / Timeout Verhalten
- Timeout-Abort in `run/attempt.ts` per Timer + AbortController
- Unterscheidung timeout während normalem Lauf vs. Compaction-Phase
- robustes Cleanup in `finally`: unsubscribe, run deregistration, lock release

---

## 1.4 Toolchaining (OpenAgent)

## Tool-Stack Aufbau
- Basis in `createOpenAgentCodingTools` (`src/agents/pi-tools.ts`)
- kombiniert:
  - Core coding tools (`read/write/edit/exec/process/apply_patch` je nach gating)
  - OpenAgent native tools (`sessions_*`, `subagents`, `browser`, `canvas`, `nodes`, `gateway`, `web_search`, `web_fetch`, `image`, `tts`, etc.)
  - plugin tools

## Tool-Policies / Gating
Mehrstufiges Policy-Pipeline-Modell:
- `tool-policy-pipeline.ts`: sequenzielle Anwendung mehrerer Policy-Ebenen
- Ebenen enthalten u.a. profile/global/provider/agent/group/subagent
- owner-only gating (`tool-policy.ts`)
- allow/deny + plugin-group-expansion + unknown allowlist handling

## Tool-Hooks
- `before_tool_call`: parameter mutation/blocking + loop detection (`pi-tools.before-tool-call.ts`)
- `after_tool_call`: post-result hook in Tool-End-Handler

## Tool-Execution Event Lifecycle
- start: summary emit + optional immediate tool summary to user streams
- update: partial updates
- result: normalized/sanitized result + dedupe/logik für messaging tools
- zusätzlich: messaging-tool-dupe suppression (um doppelte Antworten zu vermeiden)

## Tool-Loop & Safety
- Tool loop detection + warning/blocking buckets
- Param normalization/aliasing
- per-tool result sanitization
- runtime-enforced workspace/sandbox policies

---

## 1.5 Response-Synthese & Ausgabe (OpenAgent)

OpenAgent hat kein separates Planner/Synthesizer-Agent-Triplet wie dein `agent.py`, sondern einen eventgetriebenen Streaming-Assembler:

### Assistant-Text Verarbeitung
- In `pi-embedded-subscribe.handlers.messages.ts`:
  - text delta aggregation
  - directive parsing (`[[...]]` style)
  - block chunking / flush Regeln
  - silent token handling (`NO_REPLY` äquivalent über `SILENT_REPLY_TOKEN`)
  - duplicate suppression

### Tool-Antwort-Interaktion
- Tool-Resultate können als eigene result streams kommen.
- Bei messaging-tools wird finaler assistant confirmation text gedämpft, wenn Nachricht bereits extern gesendet wurde.

### Finalisierung
- Lifecycle `end/error` triggert chat-final emission in Gateway (`src/gateway/server-chat.ts`)
- Chat-Final wird aus gepufferten Deltas gebildet.

---

## 2) Agent Agency in OpenAgent

## 2.1 „Wie viele Agenten gibt es?“

### Logische Ebenen
1. **Default agent** (`main`)
2. **Multi-Agent Instanzen** über `agents.list` (isolierte Workspaces/agentDir/session stores)
3. **Subagents** zur Laufzeit via `sessions_spawn`/subagent APIs

=> Anzahl ist **dynamisch, konfigurations- und laufzeitabhängig**, nicht fix im Code.

### Agent-Typen/Run-Modi
- Embedded Pi-Agent Runtime
- ACP runtime path
- CLI provider runtime path
- Subagent run mode: `run` oder `session`

## 2.2 Subagent Lifecycle / Agency
- Subagent spawning in `src/agents/subagent-spawn.ts`
- Lifecycle reason/outcome taxonomy in `subagent-lifecycle-events.ts`
- Session/thread binding + depth limits + cleanup semantics
- registrierte aktive subagent runs + completion handling (via subagent registry files)

Das ist ein deutlich ausgebautes Agency-Modell: Parent-Agent kann Child-Runs starten, thread-binden, und über Sessions weitersteuern.

---

## 3) Feature-Inventar (nur Prompt->Lifecycle->Response-relevant)

## 3.1 Prompt-/Input-Seite
- Parameter-Validierung + agent/session consistency checks
- Idempotenz (gateway dedupe)
- Session reset/new in-band handling
- Attachment parsing (inkl. Bildpfad)
- Prompt Hooking (`before_model_resolve`, `before_prompt_build`, legacy `before_agent_start`)
- System prompt report generation

## 3.2 Lifecycle/Runtime
- Session- und Global-Lanes
- Run registry + steering + abort APIs
- Compaction-aware retry handling
- model/provider failover inkl. auth profile rotation
- context-overflow recovery (compaction + tool-result truncation)
- lifecycle event broadcasting to chat + websocket clients

## 3.3 Toolchaining
- große Toolpalette (core + openagent + plugin)
- policy pipeline (mehrere Ebenen)
- before/after tool hooks
- tool loop detection
- tool result sanitization + output shaping
- messaging tool dedupe suppressions

## 3.4 Response/Output
- delta streaming + block chunking
- directive/media extraction
- silent reply suppression
- final chat state emission on lifecycle terminal events

---

## 4) Cross-Reference mit `backend/app/agent.py` (ai-agent-starter-kit)

## 4.1 Gemeinsame Strukturmuster

1. **Guardrails zuerst**
- OpenAgent: RPC/session/model/policy checks vor Run.
- `agent.py`: `_validate_guardrails`, `_validate_tool_policy` vor Planung.

2. **Lifecycle Events als First-Class API**
- OpenAgent: `agent_start`, `agent_end`, tool start/update/result, lifecycle stream.
- `agent.py`: `_emit_lifecycle` stages wie `run_started`, `planning_started`, `run_completed`, etc.

3. **Tool-Policy/Gating + Hooking**
- OpenAgent: policy pipeline + before/after tool hooks.
- `agent.py`: allow/deny/also_allow, arg validator, policy override approval handler, hooks (`before_prompt_build`, `agent_end`).

4. **Streaming-/Eventorientierte Antwortbildung**
- OpenAgent: subscribe handlers + stream assembly.
- `agent.py`: send_event status/agent_step/final + reply shaping.

## 4.2 Hauptunterschiede im Core-Design

1. **Agent-Architektur-Stil**
- OpenAgent: eventbasierter monolithischer agent loop (pi runtime), ohne explizite Planner-Agent Klasse als feste Stufe.
- `agent.py`: explizite 3-Stage Pipeline: `PlannerAgent` -> `ToolSelectorAgent` -> `SynthesizerAgent`.

2. **Replanning-Strategie**
- OpenAgent: retries/failover/compaction-driven, weniger „plan text re-iteration“.
- `agent.py`: explizite replan loops (`max_replan_iterations`, `tool_selection_empty_replan`).

3. **Agency-Tiefe / Multi-Agent Routing**
- OpenAgent: Multi-Agent + Bindings + Subagent session/run modes + per-agent isolation tief integriert.
- `agent.py`: Klassen `HeadAgent`, `CoderAgent`, `ReviewAgent`; Subrun über `spawn_subrun` vorhanden, aber weniger infrastrukturell breit als OpenAgent Gateway-Ökosystem.

4. **Tooling-Breite**
- OpenAgent: sehr breiter tool catalog inkl. channels/sessions/subagents/browser/nodes/plugins.
- `agent.py`: ToolRegistry vorhanden, aber Fokus auf orchestrierte Tool-Aufrufe innerhalb einer dedizierten Backend-Agent-Laufzeit.

5. **Response-Shaping**
- OpenAgent: stream-level assembly, directive parsing, silent/messaging dedupe entlang des Eventstroms.
- `agent.py`: explizite `ReplyShaper`-Phase nach Synthese (suppress/remove/dedupe).

## 4.3 Lifecycle-Mapping (direkte Gegenüberstellung)

1. **Run Start**
- OpenAgent: `agent` RPC accepted -> async run -> lifecycle `start`.
- `agent.py`: `run()` -> `_emit_lifecycle(stage="run_started")`.

2. **Prompt Build**
- OpenAgent: `runEmbeddedAttempt` mit system prompt composition + hooks.
- `agent.py`: planner context reduction + `before_prompt_build` hook (planning/synthesize).

3. **Toolphase**
- OpenAgent: runtime tool executions als stream events, before/after hooks.
- `agent.py`: tool selector output -> `_execute_tools` via `ToolExecutionManager`.

4. **Responsephase**
- OpenAgent: assistant delta stream + final flush.
- `agent.py`: synthesizer text -> reply shaping -> final event.

5. **Run End/Wait**
- OpenAgent: lifecycle `end/error`, `agent.wait` snapshot via cache/listener.
- `agent.py`: final emit + `run_completed` lifecycle, Fehler in `finally` an hooks.

---

## 5) „Amount of agents“ / konkrete Zählung, soweit code-sicher ableitbar

## OpenAgent
- **Mindestens 1** Agent (`main`) im Single-Agent Mode.
- **Beliebig viele** konfigurierte Agenten (`agents.list`).
- **Zusätzliche dynamische Subagents** pro Laufzeit (`sessions_spawn` / `subagents`).
- Technisch also: `N_configured + N_dynamic_subagents`, ohne festen Upper Bound im Code (abgesehen von Konfig-/Depth-Limits für Subagent-Spawn).

## `backend/app/agent.py`
- Definiert konkret:
  - `HeadAgent`
  - `CoderAgent` (Subklasse)
  - `ReviewAgent` (Subklasse)
  - Alias `HeadCodingAgent = HeadAgent`
- Zusätzlich `spawn_subrun`-fähige Orchestrierung für Child-Runs.

---

## 6) Verifizierte Schlüsseldateien (OpenAgent)

Für den analysierten Flow wurden primär diese Dateien ausgewertet:
- `src/commands/agent.ts`
- `src/commands/agent-via-gateway.ts`
- `src/gateway/server-methods/agent.ts`
- `src/gateway/server-methods/agent-job.ts`
- `src/gateway/server-chat.ts`
- `src/agents/pi-embedded-runner/run.ts`
- `src/agents/pi-embedded-runner/run/attempt.ts`
- `src/agents/pi-embedded-runner/runs.ts`
- `src/agents/pi-embedded-runner/lanes.ts`
- `src/agents/pi-embedded-subscribe.ts`
- `src/agents/pi-embedded-subscribe.handlers.ts`
- `src/agents/pi-embedded-subscribe.handlers.lifecycle.ts`
- `src/agents/pi-embedded-subscribe.handlers.messages.ts`
- `src/agents/pi-embedded-subscribe.handlers.tools.ts`
- `src/agents/pi-tools.ts`
- `src/agents/pi-tools.before-tool-call.ts`
- `src/agents/tool-policy-pipeline.ts`
- `src/agents/tool-policy.ts`
- `src/agents/openagent-tools.ts`
- `src/agents/subagent-spawn.ts`
- `src/agents/subagent-lifecycle-events.ts`
- plus Konzeptdokus: `docs/concepts/agent-loop.md`, `agent.md`, `multi-agent.md`, `streaming.md`

Cross-reference Ziel-Datei:
- `backend/app/agent.py`

---

## 7) Fazit (kompakt)

OpenAgent ist im betrachteten Scope eine **eventgetriebene, multi-runtime Agent-Orchestrierungsplattform** mit starker Lifecycle- und Toolchaining-Infrastruktur (Queueing, Hooks, Policy-Pipeline, Failover, Subagent-Agency). Dein `backend/app/agent.py` verfolgt dagegen ein **klar gestuftes 3-Phasen-Agent-Muster** (Plan -> Tool -> Synthesize) mit explizitem Replanning und Reply-Shaping.

Beide sind strukturell robust, aber OpenAgent ist breiter als Plattform (Routing/Channel/Subagents), während `agent.py` stärker als deterministischer orchestrierter Agent-Workflow ausgeprägt ist.

---

## 8) Exhaustive Appendix (Scope-bezogen)

## 8.1 Vollständige Lifecycle-Signale im analysierten OpenAgent-Pfad

### Agent Lifecycle
- `start`
- `end`
- `error`

### Tool Lifecycle (`stream: tool`)
- `phase: start`
- `phase: update`
- `phase: result`

### Assistant Stream
- kontinuierliche `assistant`-deltas (`text`, `delta`, optional `mediaUrls`)

### Chat State Bridge (Gateway Webchat)
- `state: delta`
- `state: final`
- `state: error`

### Wait-Snapshot (`agent.wait`)
- `status: ok`
- `status: error`
- `status: timeout`

## 8.2 Hook-Inventar (Prompt->Lifecycle->Response-relevant)

Im analysierten Codepfad sichtbar/verwendet:
- `before_model_resolve`
- `before_prompt_build`
- `before_agent_start` (legacy kompat)
- `before_tool_call`
- `after_tool_call`
- `agent_end`
- `llm_input`
- `llm_output`
- `subagent_spawning` (subagent session/thread binding)

Semantik (Kurz):
- `before_model_resolve`: Provider/Model Override vor Modellauflösung
- `before_prompt_build`: Prompt/SystemPrompt Manipulation
- `before_tool_call`: Tool block/param mutation
- `after_tool_call`: post tool telemetry/logic
- `agent_end`: post-run inspection

## 8.3 Retry/Failover/Recovery-Matrix (OpenAgent)

Beobachtete Recovery-Mechaniken:
- Auth-Profile Rotation bei auth/rate-limit/failover Klassen
- model fallback pipeline (`runWithModelFallback`)
- thinking-level fallback (z.B. downgrade von unsupported level)
- context overflow recovery:
  - in-attempt compaction retry
  - explizite overflow compaction
  - oversized tool-result truncation fallback
- timeout handling inkl. spezieller compaction-timeout Zweig

Implikation für Lifecycle:
- Zwischenfehler können transient sein; terminale `error` wird im Wait-Cache mit Grace-Window behandelt.

## 8.4 Tool-Inventar (aus Core-Katalog + OpenAgent-Toolset im Scope)

### Core coding/runtime
- `read`, `write`, `edit`, `apply_patch`, `exec`, `process`

### OpenAgent native (relevant für Agency/Lifecycle)
- `sessions_list`, `sessions_history`, `sessions_send`, `sessions_spawn`, `session_status`, `subagents`
- `agents_list`

### Weitere integrierte Toolklassen
- `browser`, `canvas`, `nodes`, `gateway`, `cron`, `message`, `web_search`, `web_fetch`, `image`, `tts`

### Plugin tools
- dynamisch per Plugin-Registry eingebunden
- durch Tool-Policy-Pipeline gefiltert/erweitert (inkl. Plugin-Group Expansion)

## 8.5 Agency-Fähigkeiten (präzise)

OpenAgent Agency (innerhalb Scope):
- Multi-agent Routing via bindings
- pro Agent isolierte Workspace/State/Session Domäne
- Subagent Spawn in zwei Modi (`run`, `session`)
- thread binding für session-mode
- subagent lifecycle outcome taxonomy (`ok`, `error`, `timeout`, `killed`, `reset`, `deleted`)

`backend/app/agent.py` Agency:
- primary orchestrator `HeadAgent`
- role-basierte Varianten (`CoderAgent`, `ReviewAgent`)
- child-run delegation via `spawn_subrun`
- explizite policy-approval interaction bei blockierten Aktionen

## 8.6 Prompt->Lifecycle->Response Differenz-Scorecard

### OpenAgent (charakteristisch)
- Event-first, stream-native, runtime-zentriert
- Tool-/Lifecycle-Signale als primäre Orchestrationswährung
- Recovery-heavy loop (failover/compaction/truncation)

### `agent.py` (charakteristisch)
- Plan-first staged pipeline (Plan -> Tool -> Synthesize)
- explizite Replanning-Schleifen mit Ergebniszustandsklassifikation
- finale Reply-Shaping-Phase als dedizierter Postprozessor

---

## 9) Double-Check Ergebnis

Nach Erstellung wurde die Datei in voller Länge erneut geprüft auf:
1. Scope-Compliance (Prompt->Lifecycle->Response, ohne Fokus auf Heartbeat/Memory/History)
2. Cross-Reference-Abdeckung zu `backend/app/agent.py`
3. Vollständigkeit der identifizierten Kernkomponenten (Entry, Prompt-Build, Lifecycle, Toolchaining, Agency, Response)

Status: **abgeschlossen**.

---

## 10) Re-Verifikation (zweiter codebasierter Prüfpass)

Zusätzlicher Verifikationspass wurde gegen die OpenAgent-Codebasis durchgeführt.

Artefakte:
- Evidenzsammlung: `OPENAGENT_VERIFICATION_EVIDENCE.txt`
- 1-Seiten-Kurzfassung: `OPENAGENT_EXECUTIVE_SUMMARY_1PAGE.md`

Re-verifizierte Kernclaims:
1. Entry/Wait-Mechanik (`agent`, `agent.wait`, `waitForAgentJob`)
2. Runtime-Pfade (`runEmbeddedPiAgent`, `runCliAgent`, model fallback)
3. Prompt-/Lifecycle-Hooks (`before_model_resolve`, `before_prompt_build`, `before_tool_call`, `after_tool_call`, `agent_end`, `llm_input`, `llm_output`)
4. Queueing/Run-Registry (`resolveSessionLane`, `resolveGlobalLane`, `queueEmbeddedPiMessage`, `abortEmbeddedPiRun`)
5. Recovery-Pfade (compaction + tool-result truncation)
6. Subagent-Agency (spawn constraints, thread-binding, lifecycle outcomes)

Ergebnis: **Kernaussagen dieser Analyse bleiben bestätigt** (im Scope Prompt -> Lifecycle -> Response).
