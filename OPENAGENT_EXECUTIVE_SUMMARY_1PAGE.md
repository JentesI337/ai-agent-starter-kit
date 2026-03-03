# OpenAgent Executive Summary (1 Seite, code-verifiziert)

## Zweck
Diese Kurzfassung verdichtet die verifizierten Kernaussagen aus der Deep-Analyse für den Scope **Prompt -> Lifecycle -> Response** (ohne Heartbeat/Memory/History-Fokus).

## Verifikationsbasis
Code-Check gegen OpenAgent-Quellen (u. a.):
- `src/gateway/server-methods/agent.ts`
- `src/gateway/server-methods/agent-job.ts`
- `src/commands/agent.ts`
- `src/agents/pi-embedded-runner/run.ts`
- `src/agents/pi-embedded-runner/run/attempt.ts`
- `src/agents/pi-embedded-runner/runs.ts`
- `src/agents/pi-embedded-runner/lanes.ts`
- `src/agents/pi-embedded-subscribe.handlers.ts`
- `src/agents/pi-embedded-subscribe.handlers.lifecycle.ts`
- `src/agents/pi-embedded-subscribe.handlers.tools.ts`
- `src/agents/pi-tools.before-tool-call.ts`
- `src/agents/openagent-tools.ts`
- `src/agents/subagent-spawn.ts`
- `src/agents/subagent-lifecycle-events.ts`

Evidenzdatei: `OPENAGENT_VERIFICATION_EVIDENCE.txt`

---

## 1) Architekturbild in einem Satz
OpenAgent ist eine **eventgetriebene Multi-Runtime-Agent-Orchestrierung** mit Session-Serialisierung, Tool-Policy-Pipeline, Hook-System und Subagent-Agency.

## 2) Prompt -> Lifecycle -> Response (faktisch)

### Prompt
- Prompt-Build läuft im Embedded-Path über `runEmbeddedAttempt`.
- Systemprompt entsteht aus Workspace-/Bootstrap-/Skills-/Runtime-Kontext plus optionalem Override.
- Hooks vor Modellauflösung und vor Prompt-Build sind aktiv (`before_model_resolve`, `before_prompt_build`, legacy `before_agent_start`).

### Lifecycle
- Entry über `agent` RPC (async accepted + `runId`) oder CLI (`agentCommand`).
- Runs werden über Session- und Global-Lanes serialisiert.
- Aktive Runs sind registriert, inklusive Steering/Abort API.
- Lifecycle-Terminalsignale: `start`, `end`, `error`.

### Response
- Assistant- und Tool-Events werden gestreamt.
- Gateway-Webchat bildet daraus `delta` und `final` (oder `error`).
- `agent.wait` liefert finalen Job-Status (`ok`, `error`, `timeout`).

## 3) Toolchaining & Steuerung
- Toolset = coding core + OpenAgent-native tools + Plugin-Tools.
- Tool-Gating läuft mehrstufig (profile/global/provider/agent/group/subagent).
- Hooks an Toolgrenzen: `before_tool_call`, `after_tool_call`.
- Loop-Detection und Result-Sanitization sind eingebaut.

## 4) Agency / Multi-Agent
- Mindestens ein Agent (`main`), plus beliebig viele konfigurierte Agenten (`agents.list`).
- Subagents sind Laufzeit-Entities (Spawn `run` oder `session`).
- Subagent-Lifecycle hat explizite Reason-/Outcome-Typen (`ok/error/timeout/killed/reset/deleted`).

## 5) Robustheit im Run-Loop
- Model-Fallback ist aktiv (`runWithModelFallback`).
- Auth-Profile-Rotation und Thinking-Level-Fallbacks sind implementiert.
- Bei Context-Overflow: Compaction + Truncation-Fallback.
- Timeout-/Abort-Pfade sind getrennt und cleanup-sicher.

## 6) Gegenüber `backend/app/agent.py` (Essenz)
- OpenAgent: event-/runtime-zentrierter Loop mit breiter Plattformfunktionalität.
- `agent.py`: klar gestufte 3-Phase (`Planner` -> `ToolSelector` -> `Synthesizer`) mit explizitem Replanning.
- Beide teilen Guardrails, Lifecycle-Events, Tool-Policies und Hook-basierte Erweiterbarkeit.

## 7) Ergebnis der Re-Verifikation
Status: **Bestätigt** für die zentralen Aussagen im Scope.

Keine harte Gegen-Evidenz gefunden, die die Kernaussagen der Datei `OPENAGENT_PROMPT_LIFECYCLE_CROSSREF.md` im betrachteten Scope widerlegt.
