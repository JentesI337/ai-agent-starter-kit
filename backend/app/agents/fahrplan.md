# Backend-Agent Refactoring Masterplan (maximales Potenzial)

Stand: 03.03.2026  
Scope: `backend/app/*`  
Ziel: Euer Backend von „solider Agent-Laufzeit“ auf „steuerbares, vorhersagbares, production-grade Multi-Agent-System“ heben.

## Status-Update (03.03.2026)

- ✅ Phase-1-Kern umgesetzt: Session Inbox, `queue_mode`, WS receive/executor split, Steer-Checkpoint + Lifecycle-Events.
- ✅ Run-State/Stage-Instrumentierung aktiv inkl. optionaler Hard-Fail-Policy bei State-Violation.
- ✅ Phase-2-Kern umgesetzt: `PromptKernelBuilder` V1, `prompt_mode` (`full|minimal|subagent`), Context-Cost-APIs (`context.list`, `context.detail`) inkl. segmentierter Metrikpräzisierung.
- 🔜 Nächste priorisierte Gaps: Typed Tool Schemas (Phase 3), Directive Layer + Reasoning Visibility (Phase 6), strict unknown-key fail-fast (Phase 7).

---

## 1) Executive Summary

### Ist-Reifegrad (gegen Zielbild)

| Teil | Thema | Ist-Reife |
|---|---|---:|
| 1 | Stochastisch + deterministische Lane | 8.5/10 |
| 2 | Context Engineering + Kosten-Sichtbarkeit | 8.0/10 |
| 3 | Skills als Lazy-Loading | 8.0/10 |
| 4 | Typed Tools + Action-Space Shaping | 6.5/10 |
| 5 | Loop Guardrails | 8.5/10 |
| 6 | Hooks/Interceptors | 6.5/10 |
| 7 | Multi-Agent Arbeitsteilung | 6.5/10 |
| 8 | Operator Controls (/queue,/think,...) | 3.0/10 |
| 9 | Predictability by Schema | 5.5/10 |

**Gesamt:** 6.9/10

### Top-3 Hebel für sofortigen Impact
1. **Typed Tool-Schemas für Function Calling** statt generischer `additionalProperties=true` Tool-Args.  
2. **Directive-Layer (Out-of-Band Controls)** für `/queue`, `/model`, `/reasoning`, `/verbose`.  
3. **Strict Config Validation (unknown-key fail-fast)** zur Vermeidung von Drift/Ghost-Bugs.

---

## 2) Zielarchitektur (Soll)

### A) Run-Orchestrierung
- Pro Session genau eine Lane (beibehalten), plus **Inbox-Queue** mit Modi: `wait`, `follow_up`, `steer`.
- Steer-Checkpoint nach jedem Tool-Call.
- Bei Steer: verbleibende geplante Tool-Actions verwerfen, neuer User-Input in nächste Assistenz-Phase injizieren.

### B) Prompt-Kernel
- Versionierter Prompt-Bau mit festen Sektionen: `System`, `Policy`, `Context`, `Skills`, `Tools`, `Task`.
- `promptMode = full|minimal|subagent` (harte Sektionen statt „frei zusammengebaut“).

### C) Tool-Pipeline
- Pipeline-Stufen: `catalog` → `profile/policy filter` → `provider normalize` → `schema shrink/expand` → `execution` → `result persist transform`.
- Einheitlicher Audit-Trail je Stage.

### D) Control Plane
- Operator-Kommandos entkoppelt von User-Text.
- Kontextkosten als first-class API (`context.list`, `context.detail`).

### E) Konfigurationshärte
- Strict Config Schema mit Fail-Fast bei unknown keys/falschen Typen.

### F) Lifecycle-Vertrag Prompt → Response
- Jede Stage hat explizite **Entry-/Exit-Kriterien**, versionierte Events und klaren Fehlerpfad.
- Keine Stage darf „stumm“ mutieren (jede Mutation über Audit/Event nachvollziehbar).
- Abbruch- und Retry-Regeln sind pro Stage definiert (kein implizites Verhalten).

### G) State-Machine statt implizitem Flow
- Run-Status als endliche Zustandsmaschine: `received -> queued -> planning -> tool_loop -> synthesis -> finalizing -> persisted -> completed|failed|cancelled`.
- Erlaubte Transitionen sind fix; ungültige Transition erzeugt `run_state_violation`.
- Jeder Zustandswechsel schreibt `run_state_event` inkl. `run_id`, `session_id`, `stage`, `reason`, `latency_ms`.

---

## 2.1) Vollständiger Lifecycle-Blueprint (Prompt → Response)

### Stage 0 – Intake & Directive-Parsing (Out-of-Band)
**Input:** Raw User Message, Session-Meta, optionale Direktiven  
**Output:** `clean_user_payload`, `directive_overrides`, `queue_mode`  
**Gates:** Unknown Directive -> klare Fehlerantwort; Direktiven werden aus Prompt-Text entfernt.  
**Events:** `message_received`, `directives_parsed`, `directives_rejected`

### Stage 1 – Queueing, Lane, Scheduling
**Input:** bereinigte Nachricht + `queue_mode`  
**Output:** deterministische Run-Reihenfolge pro Session  
**Gates:** Max Queue Length, TTL, Backpressure; Overflow => expliziter Reject/Audit.  
**Events:** `inbox_enqueued`, `run_dequeued`, `queue_overflow`

### Stage 2 – Context Snapshot & Budgeting
**Input:** Session-Historie, Memory, Skills-Index, Tool-Katalog  
**Output:** segmentierter Kontext mit Budget (`system/policy/context/skills/tools/task`)  
**Gates:** Segment-Budgets + Overhead-Ratio-Limits; harte Truncation-Regeln dokumentiert.  
**Events:** `context_segmented`, `context_trimmed`, `context_budget_violation`

### Stage 3 – Prompt Kernel Build
**Input:** segmentierter Kontext, `prompt_mode`, Policies  
**Output:** versionierter Prompt + `prompt_hash` + `kernel_version`  
**Gates:** deterministische Reihenfolge der Sektionen; identische Inputs => identischer Hash.  
**Events:** `prompt_kernel_built`

### Stage 4 – Model Resolve & Inference
**Input:** Prompt-Kernel, Model-Policy, Reasoning/Verbose-Controls  
**Output:** Assistant-Plan oder Tool-Calls (strukturiert)  
**Gates:** erlaubte Modelle/Reasoning-Levels; Provider-Fallbacks nur nach Regelwerk.  
**Events:** `model_resolved`, `inference_started`, `inference_completed`, `inference_failed`

### Stage 5 – Tool Selection & Normalization
**Input:** Tool-Intent aus Modell, ToolRegistry, Profile/Policy  
**Output:** provider-normierte, validierte Tool-Calls  
**Gates:** Typed Schemas, deny/allow/profile/provider rules, parse/repair mit Max-Retry.  
**Events:** `tool_selected`, `tool_schema_validated`, `tool_schema_repaired`, `tool_selection_failed`

### Stage 6 – Tool Execution & Steer-Checkpoint
**Input:** validierte Tool-Calls + Run-Context  
**Output:** Tool-Resultate oder kontrollierter Abbruch/Steer  
**Gates:** Timeout, Cancellation, Loop-Guardrail, Read-only Parallelitätsregeln.  
**Steer:** nach jedem Tool-Call Inbox-Prüfung; bei neuem Input Rest-Plan verwerfen und Kontext aktualisieren.  
**Events:** `tool_call_started`, `tool_call_finished`, `tool_loop_blocked`, `steer_detected`, `steer_applied`

### Stage 7 – Result Transform & Persist
**Input:** rohe Tool-Outputs  
**Output:** persistierbare, policy-konforme Artefakte (redacted/compacted/chunked/summarized)  
**Gates:** PII/Size-Policies, Persist-Limits, Transcript-Safety.  
**Events:** `tool_result_transformed`, `tool_result_persisted`, `persist_rejected`

### Stage 8 – Synthesis & Final Response
**Input:** transformierte Resultate + aktueller User-Kontext  
**Output:** finale Antwort + optional reasoning summary/stream events  
**Gates:** Antwortschema/Formatregeln, keine Leaks aus redacted Daten.  
**Events:** `synthesis_started`, `response_emitted`, `response_stream_completed`

### Stage 9 – Post-Run Accounting & Learnings
**Input:** vollständiger Run-Audit  
**Output:** KPI-Aggregate, Kosten- und Qualitätssignale, optionale Memory-Writes  
**Gates:** Memory-Writes nur bei Relevanz/Policy; idempotente Run-Abschlusslogik.  
**Events:** `run_accounted`, `memory_write_applied|skipped`, `run_completed|run_failed`

---

## 2.2) Lifecycle-Invarianten (dürfen nie verletzt werden)

1. **Single-Lane pro Session**: niemals zwei aktive Executor für dieselbe Session.  
2. **Out-of-Band Control**: Direktiven gelangen nie als Rohtext ins Modell.  
3. **Deterministische Prompt-Kernel-Builds** bei gleichen Inputs.  
4. **Tool-Calls nur mit validiertem Typed Schema** (oder explizitem Compat-Flag).  
5. **Steer nur an sicheren Checkpoints** (nach Tool-Call, nie mitten in Tool-I/O).  
6. **Persist nur nach Transform-Chain** (kein Raw-Tool-Output direkt ins Transcript).  
7. **Jede Stage emittiert Events** oder explizites `stage_skipped`.

---

## 3) Programmstruktur (Epics, Reihenfolge, Dauer)

## Phase 0 – Baseline & Governance (1 Woche)

### Epic P0.1: Messgrundlage und Quality Gates
**Outcome:** Vorher/Nachher objektiv messbar.

**Tasks**
- Definiere Metriken und Zielwerte:
	- `lane_queue_wait_ms_p95`
	- `steer_interrupt_rate`
	- `tool_loop_blocked_rate`
	- `tool_selection_parse_repair_rate`
	- `context_overhead_ratio` (non-task tokens / total)
	- `tool_schema_token_share`
- Ergänze Run-Audit Aggregationen in bestehendem Monitoring.
- Lege Release-Gates fest (keine Promotion ohne KPI-Baseline).

**Akzeptanzkriterien**
- Jede Run-Antwort erzeugt KPI-relevante Audit-Felder.
- Dashboard/Report liefert mindestens p50/p95 und Trend pro Tag.

### Epic P0.2: Lifecycle Contract & Run-State-Machine
**Outcome:** E2E-Verhalten ist spezifiziert, testbar und reproduzierbar.

**Tasks**
- Definiere Run-State-Machine inkl. erlaubter Transitionen.
- Implementiere Stage-Contract-Objekte (`entry_checks`, `exit_checks`, `failure_policy`).
- Ergänze `run_state_event` und `stage_event` in Audit.
- Ergänze `stage_skipped` Semantik mit Grund (`policy`, `prompt_mode`, `no_tool_needed`, ...).

**Akzeptanzkriterien**
- Ungültige Transitionen werden geblockt und als `run_state_violation` auditiert.
- Jede Run-ID besitzt eine lückenlose Stage-Sequenz (inkl. skips/failures).

---

## Phase 1 – Deterministische Steuerung (2–3 Wochen)

### Epic P1.1: Session Inbox + Queue-Modi
**Outcome:** Kein blindes Weiterlaufen mehr bei neuen User-Inputs.

**Tasks**
- Implementiere `SessionInboxService`:
	- `enqueue(session_id, message, meta)`
	- `dequeue(session_id)`
	- `peek_newer_than(run_id)`
- Füge Queue-Modus ins Request-Context ein:
	- `queue_mode = wait|follow_up|steer`
- Standardmodus konfigurierbar (`QUEUE_MODE_DEFAULT`).

**Akzeptanzkriterien**
- Parallel eintreffende Nachrichten werden deterministisch gepuffert.
- Reihenfolge in Session bleibt reproduzierbar.

### Epic P1.2: Steer-Interrupt im Tool-Loop
**Outcome:** Run kann kontrolliert „umgelenkt“ werden.

**Tasks**
- Nach jedem Tool-Call: `if inbox.has_new(session_id, since=run_start)`.
- Bei Treffer:
	- markiere `steer_interrupt=true`
	- verwerfe restliche geplante Actions
	- hänge neue User-Nachricht an `synthesis_context` an
	- emittiere Lifecycle-Events: `steer_detected`, `steer_applied`
- Fallback-Regel bei mehr als N neuen Inputs: kompakte Zusammenfassung statt Vollinjektion.

**Akzeptanzkriterien**
- Laufende Fehlrichtung wird innerhalb eines Tool-Call-Zyklus gestoppt.
- Event-Log zeigt Zeitpunkt + Ursache der Unterbrechung.

### Epic P1.3: WS-Entkopplung Receive vs Execute
**Outcome:** Empfang neuer Messages blockiert nicht auf laufenden Run.

**Tasks**
- Trenne WS-Handler in zwei asynchrone Pfade:
	- Receiver Task (nur parse/enqueue)
	- Executor Task (lane/run)
- Führe per-Session Worker ein, der aus Inbox arbeitet.
- Backpressure-Limits je Session (max queue length + TTL).

**Akzeptanzkriterien**
- Neue WS-Nachrichten gehen auch bei langem Run nicht verloren.
- Bei Queue-Overflow klare Fehlerantwort + Audit-Eintrag.

---

## Phase 2 – Context Engineering auf Produktionsniveau (2 Wochen)

### Epic P2.1: Prompt Kernel Builder
**Outcome:** Reproduzierbare Prompt-Komposition.

**Tasks**
- Neues Modul `prompt_kernel_builder.py`:
	- `build(prompt_mode, request_context, snapshots, policies)`
- Feste Sektionen inkl. Reihenfolge und Max-Budget je Sektion.
- Prompt-Versionierung (`kernel_version`).

**Akzeptanzkriterien**
- Für identische Inputs identischer Prompt-Hash.
- Jede Antwort trägt `kernel_version` im Audit.

### Epic P2.2: Prompt Modes (full/minimal/subagent)
**Outcome:** Kontext klein halten, Spezialisten fokussieren.

**Tasks**
- `prompt_mode` in RequestContext und SubrunSpec aufnehmen.
- `minimal`: ohne globale Policies/Skills-Preview, nur task-lokaler Kern.
- `subagent`: reduzierte Sektionen + klare Übergabeverträge.

**Akzeptanzkriterien**
- Subrun-Prompts sind signifikant kleiner als Full-Prompts.
- Keine regressiven Qualitätsabbrüche in Kern-Use-Cases.

### Epic P2.3: Kontextkosten-APIs
**Outcome:** Tokenfresser sichtbar und optimierbar.

**Tasks**
- Neue Control-Endpoints:
	- `/api/control/context.list`
	- `/api/control/context.detail`
- Ausgabe nach Segmenten:
	- system prompt
	- memory
	- skills preview
	- tool schema/context
	- user payload
- Token-Schätzung plus Prozentanteile.

**Akzeptanzkriterien**
- Für jeden Run abrufbar: Segment-Token + Anteil + Top-Overhead-Quellen.

---

## Phase 3 – Tooling-Qualität und Action-Space-Shaping (2–3 Wochen)

### Epic P3.1: Typed Function Schemas aus ToolRegistry
**Outcome:** Modell bekommt präzise Tool-Argumente statt generischer Objekte.

**Tasks**
- Erweitere ToolSpec um JSON-Schema-Properties (type, enum, min/max, required).
- Generiere `tools[]` für Function Calling aus ToolRegistry.
- Entferne generische `additionalProperties=true` Default-Schablone.

**Akzeptanzkriterien**
- Function-Calling Payload enthält pro Tool ein valides, enges Schema.
- Parse/Repair-Rate sinkt messbar.

### Epic P3.2: Tool-Pipeline modularisieren
**Outcome:** Klare Stages, bessere Wartbarkeit, provider-safe Verhalten.

**Tasks**
- Stages als explizite Komponenten:
	- `resolve_catalog`
	- `apply_profile_policy`
	- `apply_provider_model_rules`
	- `normalize_for_provider`
	- `execute`
	- `persist_transform`
- Einheitliche Stage-Events je Run.

**Akzeptanzkriterien**
- Jede Tool-Aktion durchläuft nachvollziehbare Pipeline-Schritte.
- Fehlersuche über Stage-Events ohne Code-Debug möglich.

### Epic P3.3: Read-only Parallelität absichern
**Outcome:** Geschwindigkeit ohne Race-Risiken.

**Tasks**
- Read-only Klassen explizit markieren und zentral verwalten.
- Deterministische Merge-Order der Parallel-Resultate.
- Schutz gegen „falsch als read-only klassifiziert“.

**Akzeptanzkriterien**
- Parallele Runs liefern stabile, reproduzierbare Ergebnisreihenfolge.

---

## Phase 4 – Hook Middleware V2 + Persist-Transform (2 Wochen)

### Epic P4.1: Hook-Vertragsmodell erweitern
**Outcome:** Saubere Middleware statt Ad-hoc-Eingriffe.

**Tasks**
- Neue Hookpoints:
	- `before_model_resolve`
	- `before_prompt_build`
	- `before_tool_call`
	- `after_tool_call`
	- `tool_result_persist`
	- `before_transcript_append`
- Hook-Signaturen versionieren (`hook_contract_version`).

**Akzeptanzkriterien**
- Alle Hookpoints dokumentiert und testbar.

### Epic P4.2: Hook-Safety
**Outcome:** Hooks destabilisieren den Agenten nicht.

**Tasks**
- Per-Hook Timeout.
- Fehlerisolation (`hook_failed` blockiert Run nicht per default).
- Optionale Hard-Fail Hooks für Security-Policies.

**Akzeptanzkriterien**
- Defekter Hook verursacht keine globale Run-Störung.

### Epic P4.3: Result-Transform vor Persist
**Outcome:** Kontext schlanker und sicherer.

**Tasks**
- `tool_result_persist` Transform-Kette:
	- redaction
	- compaction
	- chunking
	- semantic summary
- Größe/PII-Regeln als Policy konfigurierbar.

**Akzeptanzkriterien**
- Persistierte Tool-Outputs sind unter Max-Size und policy-konform.

---

## Phase 5 – Multi-Agent-Isolation und Delegation (2 Wochen)

### Epic P5.1: Hartere Isolierung je Agent
**Outcome:** Weniger Kontext-/Credential-Kollisionen.

**Tasks**
- Optionales `workspace_root` je Agent.
- Optionales `skills_dir` je Agent.
- Optionales `tool_policy_defaults` je Agent.
- Optionales Credential-Scope (read-only token maps).

**Akzeptanzkriterien**
- Agent A kann nicht implizit Kontext/Secrets von Agent B sehen.

### Epic P5.2: Structured Delegation Contracts
**Outcome:** Delegation reproduzierbar, begrenzt, nachvollziehbar.

**Tasks**
- Standardisiere Handover Contract:
	- `terminal_reason`
	- `confidence`
	- `result_summary`
	- `follow_up_questions`
- Begrenze ping-pong Delegationszyklen (max rounds).

**Akzeptanzkriterien**
- Parent-Agent kann Child-Resultat maschinenlesbar auswerten.

---

## Phase 6 – Operator Controls und Control Plane (1–2 Wochen)

### Epic P6.1: Directive Parser (Out-of-Band)
**Outcome:** Steuerbefehle getrennt von User-Content.

**Tasks**
- Parser für Direktiven:
	- `/queue wait|follow_up|steer`
	- `/model <name>`
	- `/reasoning low|medium|high|ultrathink|adaptive`
	- `/verbose on|off`
- Direktiven in RequestContext schreiben, aus User-Text strippen.

**Akzeptanzkriterien**
- Prompt enthält keine Roh-Direktiven mehr.
- Steuerwerte sind im Run-Meta/Audit sichtbar.

### Epic P6.2: Reasoning Visibility Controls
**Outcome:** Denken und Transparenz unabhängig steuerbar.

**Tasks**
- `reasoning_visibility = off|summary|stream`.
- Trennung von finaler Antwort und Reasoning-Events.

**Akzeptanzkriterien**
- Umschaltung ohne Änderung der fachlichen Antwortlogik.

---

## Phase 7 – Predictability by Schema (1 Woche)

### Epic P7.1: Strict Settings Validation
**Outcome:** Keine Ghost-Bugs durch Config-Drift.

**Tasks**
- Settings-Modell auf strict umstellen (unknown keys => Start-Fehler).
- Typ- und Bereichsvalidierung für kritische Felder (timeouts, thresholds, list sizes).
- Startup-Validation Report mit `errors`, `warnings`, `effective_defaults`.

**Akzeptanzkriterien**
- Gateway startet nicht bei ungültiger Config.

### Epic P7.2: Config Health Endpoint
**Outcome:** Operator sieht sofort, was aktiv ist.

**Tasks**
- Endpoint `/api/control/config.health` mit:
	- schema version
	- active overrides
	- invalid/unknown summary
	- risk flags

**Akzeptanzkriterien**
- Config-Zustand ohne Log-Suche abrufbar.

---

## 4) Ticket-Backlog (konkret, direkt sprintfähig)

## Sprint A (Steuerungskern)
- A1: `SessionInboxService` + unit tests
- A2: RequestContext um `queue_mode` erweitern
- A3: WS receive/executor entkoppeln
- A4: Steer-Check in Tool-Loop + Lifecycle Events
- A5: Queue Overflow Handling + TTL

## Sprint B (Prompt & Kontext)
- B1: PromptKernelBuilder V1
- B2: PromptMode full/minimal/subagent
- B3: Context APIs list/detail
- B4: Token Segment Estimator + Overhead Ranking

## Sprint C (Tool Schemas)
- C1: ToolSpec Schema-Felder ergänzen
- C2: Function-Calling payload aus ToolRegistry erzeugen
- C3: Provider-normalized tool schema adapter
- C4: Regression tests parse_repair_rate

## Sprint D (Hooks + Persist)
- D1: Hook Contract V2
- D2: Hook timeout/error isolation
- D3: tool_result_persist transform chain
- D4: Audit Erweiterung für hook timings

## Sprint E (Operator + Config)
- E1: Directive parser + strip logic
- E2: reasoning visibility controls
- E3: strict config validation
- E4: config.health endpoint

---

## 5) Teststrategie (pro Phase)

### Funktional
- Session-Lane Serialisierung unter Last (N parallele Requests, gleiche Session).
- Steer-Fälle:
	- neuer Input zwischen Tool-Call 1 und 2
	- mehrfacher neuer Input während langer Tool-Phase
- Directive-Fälle:
	- valide Direktiven
	- unbekannte Direktiven
	- Mischung aus Direktive + normalem Text
- Lifecycle-Fälle (vollständig):
	- happy path ohne Tool
	- happy path mit Tool-Loop + Synthesis
	- failure in Stage 4/5/6/7 inkl. Recovery-Pfad
	- stage skip (z.B. kein Tool nötig) inkl. sauberem Audit

### Nicht-funktional
- p95 queue wait, p95 run latency, error rate.
- Prompt-Größe vor/nach PromptMode minimal.
- parse_repair_rate vor/nach typed schemas.
- Stage-Latenzen p95 je Lifecycle-Stage (0..9).
- Event-Loss-Rate (`expected_stage_events - actual_stage_events`) ~= 0.

### Sicherheit
- Policy bypass tests (`also_allow`/deny conflicts).
- Hook abuse tests (timeout, exception, mutation attempts).
- Web/tool output persist redaction tests.
- Directive-Injection-Tests (Direktive im Fließtext darf keinen OOB-Effekt haben).
- Cross-Agent-Isolation (kein impliziter Zugriff auf fremde Credentials/Workspace).

---

## 6) KPIs und Zielwerte

| KPI | Baseline | Ziel |
|---|---:|---:|
| steer_interrupt_rate | n/a | > 90% bei künstlichen Fehlrichtungs-Tests |
| tool_selection_parse_repair_rate | aktuell messen | -40% |
| context_overhead_ratio | aktuell messen | -25% |
| tool_schema_token_share | aktuell messen | -30% |
| lane_queue_wait_ms_p95 | aktuell messen | <= 300ms (normal load) |
| tool_loop_blocked_false_positive_rate | aktuell messen | < 2% |
| stage_event_completeness_rate | aktuell messen | >= 99.9% |
| run_state_violation_rate | aktuell messen | 0 in prod |
| directive_strip_success_rate | aktuell messen | >= 99.5% |

---

## 7) Risiken und Gegenmaßnahmen

- **Steer führt zu inkonsistentem Zwischenzustand**  
	Gegenmaßnahme: Interrupt nur an sicheren Checkpoints nach Tool-Call.

- **Typed Schemas zu strikt, Modell scheitert öfter**  
	Gegenmaßnahme: Compat-Mode + schrittweise Härtung.

- **Hooks verursachen Latenzspitzen**  
	Gegenmaßnahme: harte Hook-Timeouts + parallel-safe execution policy.

- **Operator-Directives missverständlich**  
	Gegenmaßnahme: klare Fehlermeldungen + Hilfe-Endpoint.

---

## 8) Rollout-Plan (3 Phasen)

### Phase 1 – Shadow Mode
- Steer/Directive/Typed-Schema zunächst nur messen, nicht erzwingen.
- Vergleichsmetriken mit Legacy-Verhalten.

### Phase 2 – Canary
- Aktivierung für definierte Agent-IDs + Session-Segmente.
- Schneller Rollback über Feature Flags.

### Phase 3 – Full Rollout
- Default aktiv, Legacy-Pfade entfernen.
- Nachlauf mit KPI-Härtung und Cleanup.

---

## 9) Definition of Done (programmweit)

- Alle Epics haben automatisierte Tests (unit + integration).
- KPIs werden im Monitoring kontinuierlich erhoben.
- Rollback-Strategie pro Feature dokumentiert.
- Control-Plane dokumentiert (Operator-Handbuch).
- Keine offene P0/P1 Known Issue vor Full Rollout.
- Jeder Run ist als Stage-Kette vollständig rekonstruierbar (inkl. skip/failure).
- Prompt-, Tool- und Persist-Pfade besitzen explizite Contract-Versionen.
- Shadow/Canary-Metriken belegen keine Regression bei Kern-Use-Cases.

---

## 10) Sofort startbare nächste 72h (konkrete Reihenfolge)

1. `ToolSpec` um enge JSON-Schema-Felder erweitern (`required`, `enum`, `min/max`, `additionalProperties=false` where safe).  
2. Function-Calling `tools[]` strikt aus ToolRegistry-Schemas generieren (provider-kompatible Normalisierung).  
3. Parse/Repair-Telemetrie für Tool-Selektion ergänzen und Baseline/Delta messen.  
4. Directive-Parser OOB (`/queue`, `/model`, `/reasoning`, `/verbose`) implementieren inkl. Strip-Logik vor Prompt-Build.  
5. `reasoning_visibility=off|summary|stream` verdrahten (RequestContext, Events, Ausgabe).  
6. Strict Config Validation vorbereiten: unknown keys im Settings-Pfad fail-fast (Feature-flagged Einführungsmodus).  
7. Fokus-Verifikation: typed-schema + directive + config-health Regression-Suite ausführen und dokumentieren.

---

## 13) Lifecycle-Checkliste pro Ticket (Copy/Paste für PR-Template)

- Betroffene Stage(s) klar benannt (0..9).  
- Entry-/Exit-Kriterien aktualisiert oder explizit unverändert.  
- Neue/angepasste Events dokumentiert (`name`, `payload`, `sampling`).  
- Failure-Policy definiert (`retry`, `abort`, `degrade`, `skip`).  
- Audit-Felder ergänzt (mind. `run_id`, `session_id`, `stage`, `latency_ms`, `reason`).  
- Security/Privacy geprüft (Directive-Strip, PII-Redaction, Isolation).  
- Tests vorhanden (unit + integration, ggf. load/security).

## 14) Minimales Datenmodell für Stage-Events

```json
{
	"run_id": "string",
	"session_id": "string",
	"stage": "int|name",
	"event": "string",
	"timestamp": "iso8601",
	"latency_ms": 0,
	"status": "ok|failed|skipped",
	"reason": "optional-string",
	"contract_version": "string"
}
```

---

## 11) Ownership-Vorschlag

- **Orchestrierungsteam:** Phase 1 + 5  
- **Prompt/Reasoning-Team:** Phase 2 + 6  
- **Tooling-Team:** Phase 3 + 4  
- **Platform/Infra:** Phase 7 + Monitoring + Rollout

---

## 12) Abschluss

Dieser Plan ist so strukturiert, dass er direkt in Sprints überführt werden kann, ohne weitere Architektur-Workshops als Blocker.  
Wenn ihr strikt nach dieser Reihenfolge geht, erhaltet ihr zuerst die größten Produktivitäts- und Reliability-Gewinne und reduziert gleichzeitig das Risiko teurer Regressionswellen.


