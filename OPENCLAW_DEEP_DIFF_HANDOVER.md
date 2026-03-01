# OpenClaw Deep-Diff Handover (Stand: 2026-03-01)

## 1) Aktuelle Systemfunktionalität (ai-agent-starter-kit)

### Kern-Runloop
- Deterministische Pipeline mit festen Schritten: **Plan → Tool-Select/Execute → Synthesize**.
- Implementiert in `HeadAgent` + Step-Executors.
- Tool-Selection ist LLM-getrieben (`{"actions": [...]}`), mit Reparaturpfad bei fehlerhaftem JSON.

### Agenten-Modell
- Built-in Agenten: `head-agent`, `coder-agent`, `review-agent`.
- Routing in `main.py` anhand Intent-Heuristik + Preset (`review` delegiert auf Review-Agent).
- Custom Agents: persistente Definitionen (`base_agent_id`, Workflow-Textschritte, optionale Tool-Policy), ausgeführt als Adapter über Base-Agent.

### Tooling/Sicherheit
- Tools: File/grep/search/git/command/web-fetch/background-process.
- Tool-Policy: global + per-request (`allow`/`deny`) mit Validierung.
- **Zusätzliche Command-Allowlist** auf Shell-Leader-Ebene (`run_command`/background), getrennt von Tool-Policy.

### Orchestrierung/State
- REST + WS (`/ws/agent`) Event-Streaming: status/lifecycle/token/final/error.
- StateStore + externe Run-Snapshots.
- SubrunLane: Spawn-Depth, Concurrency, Child-Limits, Visibility (`self/tree/agent/all`), Kill/Log APIs.

---

## 2) OpenClaw – relevante Architektur (ohne Heartbeat/Spinup)

### A) Gateway als echte Control Plane (größter Unterschied)
OpenClaw hat ein einheitliches WS-Protokoll mit Rollen/Scopes und breiter API-Fläche (Sessions, Agent-Runs, Nodes, Skills, Cron, Approvals, etc.).

### B) Agent Loop als asynchrones Job-Modell
- `agent` akzeptiert Request und gibt sofort `runId` zurück.
- `agent.wait` liefert terminalen Status (`ok|error|timeout`).
- Lifecycle/Assistant/Tool-Events sind strikt als Streams modelliert.

### C) Toolchain ist Policy- und Runtime-getrieben (mehrdimensional)
- Tool-Profiles (`minimal/coding/messaging/full`) als Basis.
- `allow/deny` + `alsoAllow` + provider-/model-spezifische Policies.
- Sandbox-spezifische Tool-Policy + Agent-spezifische Overrides.
- Session-Tools mit Sichtbarkeitsregeln + Agent-to-Agent Policy.

### D) Subagent-/Session-Orchestrierung als First-Class Tooling
- `sessions_list/history/send/spawn/session_status` + `subagents` Management.
- Spawn-Depth-/Policy-Logik für orchestrierende vs. leaf subagents.

### E) Loop-Detection im Tool-Layer
- Wiederholungs-/Ping-Pong-/No-progress-Erkennung mit warn/critical thresholds.
- Vor Tool-Call Hook kann blocken, bevor Endlosschleifen eskalieren.

### F) Skills als dynamische Capability-Schicht
- Skills (bundled/managed/workspace) mit Gating (env/bin/config), Snapshot, Watcher, Install-Flow.
- Skills beeinflussen Prompt/Commands und erweitern Toolnutzung strukturiert.

### G) Plugin-/Hook-System
- Hooks vor Model-Resolve, Prompt-Build, Tool-Call, Agent-Start/End usw.
- Ermöglicht runtime-spezifische Anpassung ohne Kernumbau.

---

## 3) Core-Differences mit hohem Impact (für euer Ziel)

## 3.1 Von „Chat + Agent“ zu „Control Plane + Runtime Contracts"
**Ist:** WS-Endpunkt für Chat-orientierte Requests + ein paar REST-Hilfsendpunkte.  
**OpenClaw-artig:** standardisierte Methoden + Rollen/Scopes + Versionierung + idempotente Mutation.

**Impact:**
- Stabilere Multi-Client-Integration (UI, CLI, Automations, externe Orchestratoren).
- Saubere Entkopplung zwischen Oberfläche und Agentenlaufzeit.

## 3.2 Tool-Policy-Stack statt einzelner Allow/Deny-Layer
**Ist:** effektive Tool-Policy (global + per-run), plus Command-Allowlist separat.  
**OpenClaw-artig:** Profile + allow/alsoAllow/deny + byProvider + sandbox + per-agent.

**Impact:**
- Gleiche Agent-UX auf großem/kleinem LLM bei konsistenten Sicherheitsgrenzen.
- Präzise Capability-Tuning pro Model/Agent/Context.

## 3.3 Session- und Subagent-Topologie als Primärabstraktion
**Ist:** SubrunLane stark, aber noch primär backend-intern.  
**OpenClaw-artig:** Session-Methoden sind Toolchain-Bausteine für Agent-zu-Agent-Arbeit.

**Impact:**
- Bessere Multi-Agent-Workflows, Revision-Loops und Delegation ohne Sonderpfade.

## 3.4 Deterministische Anti-Loop-Layer vor Tool-Execution
**Ist:** mehrere Guardrails, aber kein systematischer Tool-Loop-Detektor.  
**OpenClaw-artig:** detector-basierter pre-tool-call breaker.

**Impact:**
- Weniger Kosten/Deadlocks bei großen LLMs.
- Robustheit bei langen/rekursiven Chains.

## 3.5 Skills-/Capability-Lifecycle
**Ist:** custom agents + workflow steps + policy merge.  
**OpenClaw-artig:** skill snapshots, eligibility, install/update, shared/per-agent layering.

**Impact:**
- Skalierbare Erweiterbarkeit ohne Core-Code-Inflation.
- Reproduzierbare Agent-Fähigkeiten pro Workspace/Team.

---

## 4) Zielbild für euer Framework (Large+Small LLMs, gleiche Agency)

### Layer 1 — Control Plane API
Ein methodenbasiertes Protokoll (WS/JSON-RPC-artig):
- `agent.run`, `agent.wait`, `runs.list/get/events`
- `sessions.list/resolve/history/send/spawn/patch/reset`
- `tools.catalog`, `tools.policy.preview`
- `workflows.list/create/update/execute`

### Layer 2 — Execution Engine
- Behaltet euren deterministischen PipelineRunner als **Execution-Kern**.
- Ergänzt „Execution Contracts“ (status, lifecycle phases, usage, retries, idempotency).

### Layer 3 — Tool Governance
- Einführung von:
	- `tools.profile`
	- `tools.allow` / `tools.deny` / `tools.also_allow`
	- `tools.by_model` oder `tools.by_provider`
	- `tools.sandbox.*`
- Command-Allowlist bleibt als Low-Level-Safety, aber an Policy-Layer angebunden.

### Layer 4 — Multi-Agent + Revision Flows
- Erstellt native Workflow-Objekte statt nur Prompt-Injection:
	- `plan -> implement -> review -> revise -> verify`
	- mit stop conditions, budget caps, escalation rules.
- SubrunLane wird zur „session graph runtime“ ausgebaut.

### Layer 5 — Small-vs-Large Model Strategy
- **Head (large LLM):** Planung, Delegation, Konfliktauflösung, End-Synthese.
- **Worker (small LLM):** eng begrenzte Tools + enges Prompt-Template + kurze Kontexte.
- Deterministische Übergabeverträge (structured task payloads) zwischen den Agenten.

---

## 5) Konkrete Umsetzung in 4 Phasen

### Phase 1 (1–2 Wochen): Contract-First Control Plane
1. Neue run/session APIs hinzufügen (`run.start`, `run.wait`, `sessions.*` minimal).
2. Einheitliches Event-Schema + Statusmaschine fixieren.
3. Idempotency-Key für mutierende Calls.

### Phase 2 (1–2 Wochen): Tool Policy Matrix
1. Tool-Profile + `also_allow` + model/provider-scoped policies.
2. `tools.catalog` + policy preview endpoint.
3. Policy-Entscheidung in Lifecycle transparent emitten.

### Phase 3 (1–2 Wochen): Multi-Agent Workflow Runtime
1. Workflow-Definitionen (JSON/YAML) speichern/versionieren.
2. Native Revision-Flow-Executor über Subrun graph.
3. Sichtbarkeits-/A2A-Regeln analog session graph ausrollen.

### Phase 4 (1 Woche): Runtime Hardening
1. Tool-loop detection (warn/critical breaker).
2. Budget Guards (token/time/tool-call caps) pro Step und pro Subrun.
3. Replay-/audit-fähige Run-Telemetrie.

---

## 6) Wichtigste Entscheidungen (für nächste Session)

1. **API-Shape:** Wollt ihr ein internes JSON-RPC-ähnliches WS-Protokoll (OpenClaw-nah) oder REST+WS-Hybrid behalten?
2. **Workflow-Spec:** Lieber deklarativ (YAML/JSON DAG) oder „custom agent steps++“ inkrementell erweitern?
3. **Policy-Scope:** nur global+agent zuerst oder direkt provider/model-spezifisch?
4. **Safety-First:** Loop-Detection + Budget-Caps sofort vor Feature-Ausbau einschieben.

---

## 7) Paste-ready Prompt für eine neue Session

Nutze diesen Prompt 1:1 in einer neuen Session:

"Arbeite auf Basis von OPENCLAW_DEEP_DIFF_HANDOVER.md.  
Ziel: Implementiere Phase 1 (Contract-First Control Plane) in kleinen, testbaren Schritten.  
Erstelle zuerst nur: run.start, run.wait, sessions.list/minimal, ein konsistentes Lifecycle-Event-Schema und Idempotency-Key-Handling.  
Kein UI-Umbau außer zwingend nötig.  
Nutze vorhandene Orchestrator-/Subrun-Struktur, vermeide große Refactors außerhalb dieses Scopes.  
Füge/aktualisiere gezielte Backend-Tests für die neuen Contracts."

