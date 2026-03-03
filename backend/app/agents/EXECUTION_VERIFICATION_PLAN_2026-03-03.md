# Backend Execution + Verifikation (Codebasiert)

Stand: 03.03.2026  
Scope: `backend/app/*`  
Referenzen: `fahrplan.md`, `importantPattern.md`

---

## Masterplan 2026-03-03 (codebasiert, präzise)

Quelle: direkte Analyse der produktiven Implementierung in `backend/app/*` (WS-Lane, Orchestrator, Agent-Loop, Tool-Execution, Skills, Control-Plane, Config).

### A) Reifegrad-Matrix (Ist)

1. Deterministische Lane + Queue/Steer: **9/10**
2. Context Engineering + Prompt Kernel: **8.5/10**
3. Skills Lazy-Loading: **8/10**
4. Typed Tools + Action-Space Shaping: **8/10**
5. Loop Guardrails (Anti-Stall): **9/10**
6. Hooks als Middleware: **8.5/10**
7. Multi-Agent Arbeitsteilung + Isolation: **7/10**
8. Operator Controls (OOB Directives): **6.5/10**
9. Predictability by Schema (Config): **7.5/10**

Gesamt: **~7.5/10 Agent-Core**, aber **~5.5/10 für „nahezu jedes Problem“**.

### B) Zielbild (90 Tage)

Ziel: von robustem Agent-Core zu einer Plattform, die komplexe, offene Aufgaben verlässlich löst.

- P0: harte Isolation + Verifier-Schicht + Eval-Gates
- P1: Follow-up/Steer Scheduling präzisieren + Capability Routing
- P2: Retrieval/Knowledge-Reliability + Kosten/Qualität adaptive Steuerung

### C) Konkreter 30/60/90-Plan

#### 0–30 Tage (P0, höchster Hebel)

1) **Hard Isolation Contract pro Agent/Subrun**
- Ziel: echte Trennung von Workspace/Secrets/Netz statt nur Policy-Metadaten.
- Betroffene Bereiche:
   - `backend/app/services/agent_isolation.py`
   - `backend/app/orchestrator/subrun_lane.py`
   - `backend/app/agent.py` (Tool-Ausführungskontext)
- Umsetzung:
   - harte Allowlist für Pfadzugriffe pro Session/Agent
   - Secret-Scope Enforcement vor Tool-Dispatch
   - deny-by-default für cross-scope Delegation ohne explizite Freigabe
- Akzeptanz:
   - Cross-Scope-Zugriffe werden deterministisch geblockt und auditiert
   - keine stillen Fallbacks auf globale Scopes

2) **Verifier-Layer nach Plan/Tool/Final**
- Ziel: Qualität nicht nur durch Prompting, sondern durch prüfbare Zwischenzustände.
- Betroffene Bereiche:
   - `backend/app/agent.py`
   - `backend/app/services/tool_execution_manager.py`
   - `backend/app/orchestrator/pipeline_runner.py`
- Umsetzung:
   - Plan-Validator: prüft Zielbezug/Tool-Notwendigkeit
   - Tool-Result-Validator: Fortschritt, Widerspruch, fehlende Artefakte
   - Final-Validator: Antwortvollständigkeit gegen User-Ziel
- Akzeptanz:
   - neue Lifecycle-Events `verification_*`
   - messbar weniger „completed, aber falsch/leer“ Fälle

3) **Eval-Gates als Release-Kriterium**
- Ziel: Regressionen vor Merge erkennen.
- Betroffene Bereiche:
   - `backend/tests/*`
   - `backend/monitoring/*`
- Umsetzung:
   - Golden-Task-Suite (mind. 30 repräsentative Flows)
   - Pflichtmetriken: Erfolgsrate, Replan-Rate, Tool-Loop-Rate, Invalid-Final-Rate
- Akzeptanz:
   - CI blockt bei Gate-Verletzung

#### 31–60 Tage (P1)

4) **Queue-Semantik schärfen (`wait` vs `follow_up` vs `steer`)**
- Ziel: `follow_up` darf nicht faktisch wie `wait` laufen.
- Betroffene Bereiche:
   - `backend/app/ws_handler.py`
   - `backend/app/services/session_inbox_service.py`
   - `backend/app/interfaces/request_context.py`
- Umsetzung:
   - separate Scheduling-Regeln für `follow_up`
   - fairness + starvation-sichere Reihenfolge
   - explizite Events für Follow-up-Merging/Deferral
- Akzeptanz:
   - reproduzierbares, unterscheidbares Laufzeitverhalten aller drei Modi

5) **Capability-basiertes Tool/Agent Routing**
- Ziel: bessere Erstentscheidung, weniger Replan-Zyklen.
- Betroffene Bereiche:
   - `backend/app/services/tool_registry.py`
   - `backend/app/services/tool_execution_manager.py`
   - `backend/app/services/agent_resolution.py`
- Umsetzung:
   - Capability-Metadaten pro Tool/Agent
   - intent + capability match als harte Vorselektion
- Akzeptanz:
   - sinkende `tool_selection_empty` / `replanning_started` Quote

#### 61–90 Tage (P2)

6) **Reliable Retrieval Layer**
- Ziel: bessere Problemlösung bei wissenslastigen Aufgaben.
- Betroffene Bereiche:
   - `backend/app/skills/*`
   - neuer Retrieval-Service + Caching/Source-Trust
- Umsetzung:
   - semantische Suche + Quellenranking
   - Antwortbezug auf tatsächlich verwendete Quellen im Laufzeitkontext
- Akzeptanz:
   - weniger Halluzinationsmuster in Research-Aufgaben

7) **Qualitäts-/Kosten-adaptive Inferenzsteuerung**
- Ziel: Qualität steigern ohne unkontrollierte Kosten.
- Betroffene Bereiche:
   - `backend/app/orchestrator/pipeline_runner.py`
   - `backend/app/model_routing/*`
- Umsetzung:
   - dynamische Wahl von reasoning level/model abhängig von Signals
   - harte Budgets + graceful degradation
- Akzeptanz:
   - stabile QoS bei Last, keine Kostenexplosion

### D) Verifikationskriterien (verbindlich)

Für jede Welle Pflicht:

1. **Funktional**
- deterministische Reproduzierbarkeit gleicher Inputs
- kein unbegründeter Status „completed“ bei fehlendem Ergebnis

2. **Sicherheit/Isolation**
- negative Tests für Cross-Scope/Secret-Leaks
- deny-by-default nachweisbar

3. **Observability**
- vollständige Lifecycle-Kette pro Run
- neue Events dokumentiert und in `context.detail` nachvollziehbar

4. **Qualität**
- Golden-Task-Passrate steigt je Welle
- Tool-Loop-Blockaden sinken ohne Genauigkeitsverlust

### E) Reihenfolge für sofortige Umsetzung

1. Isolation Contract (P0.1)
2. Verifier Layer (P0.2)
3. Eval-Gates (P0.3)
4. Queue-Semantik (P1.4)
5. Capability Routing (P1.5)

Diese Reihenfolge maximiert Reliability zuerst und erhöht dann Problemlösefähigkeit strukturell, statt nur Prompt-Verhalten zu ändern.


## Umsetzungsstatus (03.03.2026, Update)

- ✅ `SessionInboxService` implementiert (`enqueue`, `dequeue`, `peek_newer_than`, Overflow/TTL).  
- ✅ `queue_mode` in `RequestContext` eingeführt (`wait|follow_up|steer`).  
- ✅ `queue_mode` durch WS/REST/Control-Pfade verdrahtet.  
- ✅ WS-Inbox-Events integriert: `inbox_enqueued`, `run_dequeued`, `queue_overflow`.  
- ✅ WS receive/executor entkoppelt: `user_message` wird gequeued, pro Session durch Worker verarbeitet.  
- ✅ Steer-Interrupt im Tool-Loop verankert (`ToolExecutionManager`): Checkpoint nach `tool_completed`/`tool_failed`, bei neuem Input Abbruch + `steer_detected`/`steer_applied`.  
- ✅ Steer-Callback durchgereicht: `RequestContext -> OrchestratorApi -> PipelineRunner -> FallbackStateMachine -> Agent -> ToolExecutionManager`.  
- ✅ `stage_event`/`run_state_event` Skeleton aktiv in Persistenzpfad (`state_append_event_safe`) inkl. `run_state_violation` Instrumentierung.  
- ✅ Optionale Hard-Fail-Policy umgesetzt: `RUN_STATE_VIOLATION_HARD_FAIL_ENABLED` markiert Runs bei ungültiger Transition als failed.  
- ✅ Fokus-Tests grün (37 passed für StateMachine+WS+Inbox+ToolExecutionManager+ToolSelectorAgent).
- ✅ Control-Plane Endpoints ergänzt: `/api/control/context.list`, `/api/control/context.detail`, `/api/control/config.health`.  
- ✅ Router + Handler + Tests für Context/Config-Sichtbarkeit integriert (46 passed fokussiert).
- ✅ Token-/Segment-Metrikpräzision umgesetzt: Agent emittiert `context_segmented` (planning/tool_loop/synthesis), Control-Handler priorisiert segmentierte Events vor Fallback-Heuristik.
- ✅ Regressions-Fokuslauf grün nach Präzisions-Upgrade (25 passed: context-config handlers, tool execution manager, ws handler, router units).
- ✅ `PromptKernelBuilder` V1 implementiert: deterministische Sektionen + `kernel_version` + `prompt_hash` in Prompt-Erzeugung.
- ✅ `prompt_mode` (`full|minimal|subagent`) implementiert und durch WS/REST/Orchestrator/Agent-Pfade verdrahtet (inkl. `subagent`-Default im Subrun-Pfad).
- ✅ Zusätzliche Fokus-Tests grün für Kernel/Mode-Normalisierung (`test_prompt_kernel_builder`, `test_planner_agent`, `test_session_inbox_service`).
- ✅ `PromptKernelBuilder` auf `prompt-kernel.v1.1` gehoben: stabile `section_fingerprints` ergänzt, `context_segmented` enthält nun `kernel_version`/`prompt_hash`/`prompt_mode`.
- ✅ Context-Cost APIs präzisiert: event-first Aggregation aktiv, additive Felder `segment_source`, `degraded_estimation`, `phase_breakdown` in `context.list`/`context.detail`.
- ✅ Skills Lazy-Loading S3 umgesetzt: Snapshot-Cache (TTL/mtime), Events `skills_snapshot_built|skills_snapshot_skipped|skills_preview_injected|skills_preview_omitted_by_prompt_mode|skills_manual_read`, prompt-mode Kontraktion aktiv.
- ✅ S3 Fokus-Tests grün (`test_skills_service`, `test_tool_execution_manager`), plus Regressions-Fokus (`test_prompt_kernel_builder`, `test_tools_handlers_context_config`, `test_planner_agent`, `test_session_inbox_service`).
- ✅ T1 Typed Tool Schemas umgesetzt: Registry-basierte Function-Calling-Definitionen inkl. typed `parameters` aktiv.
- ✅ T2 Directive Layer OOB + Reasoning Visibility umgesetzt: `/queue|/model|/reasoning|/verbose` parserbasiert, Prefix-Strip aktiv in WS/REST.
- ✅ T2 Hardening nachgezogen: Background-Run Directive-Fehler gehen garantiert durch Fail-/Cleanup-Pfad; WS-Non-User-Pfade nutzen konsistent bereinigten Content/Model-Override.
- ✅ API-Level Regression ergänzt: `run.start` + `run.wait` verifizieren Directive-only Fehlerpfad im Background-Run.

Hinweis: T3 ist umgesetzt/verifiziert; verbleibende priorisierte Kernpunkte sind Hook-Contract/Safety (P4) und Multi-Agent-Isolation (P5).

---

## 1) Verifizierter Ist-Stand (gegen Pattern 1..9)

Legende: **Erfüllt**, **Teilweise**, **Fehlt**

1. **Deterministische Lane / Serialisierung pro Session** → **Erfüllt**  
   - Explizite Session-Inbox ist implementiert (`SessionInboxService`) inkl. FIFO, Overflow/TTL, Queue-Modi `wait|follow_up|steer`.  
   - WS receive/executor ist getrennt; pro Session verarbeitet ein dedizierter Worker deterministisch.

2. **Context Engineering + Prompt Kernel + Kosten-Sichtbarkeit** → **Teilweise bis gut**  
   - Budgets und Context-Reduction sind vorhanden (`plan/tool/final`).  
   - `context.list` / `context.detail` sind vorhanden; segmentierte Metriken werden via `context_segmented` Lifecycle-Events geliefert.  
   - Versionierter `PromptKernelBuilder` ist eingeführt (`kernel_version`, `prompt_hash`, deterministische Sektionen).

3. **Skills als Lazy-Loading** → **Teilweise bis gut**  
   - Skills-Snapshot wird nur bei aktivem Gating geladen und in Tool-Selektion injiziert.  
   - `prompt_mode`-basiertes Segment-Contracting (`full|minimal|subagent`) ist implementiert; weitere Optimierung der Skills-Segmentierung bleibt möglich.

4. **Typed Tools + Action-Space Shaping** → **Teilweise bis gut**  
   - Function-calling nutzt Registry-basierte typed Tool-Schemas (`required`, `enum`, Constraints, `additionalProperties=false` where safe).  
   - Restarbeit liegt primär in weiterer Schema-Härtung/Provider-Kompatibilität, nicht mehr im Fehlen des Grundmechanismus.

5. **Loop Guardrails** → **Erfüllt (stark)**  
   - `ToolCallGatekeeper` + Thresholds + lifecycle events sind implementiert.  
   - Circuit-breaker/Warning-Pfade vorhanden.

6. **Hooks/Interceptors als Middleware** → **Teilweise bis gut**  
   - Hooks `before_prompt_build`, `before_tool_call`, `after_tool_call`, `agent_end` sind integriert.  
   - Es fehlt ein versionierter Hook-Contract inkl. klarer Safety-Policy pro Hookpoint (Hard-Fail/Soft-Fail/Timeout als Vertragsebene).

7. **Multi-Agent Delegation + Isolation** → **Teilweise**  
   - Subrun-Lane, Depth-Guards, Child-Limits, Handover sind vorhanden.  
   - Harte Agent-Isolation (workspace/skills/credential-scope je Agent) ist noch nicht vollständig als Default-Contract umgesetzt.

8. **Operator Controls (Directive Layer OOB)** → **Erfüllt (grundlegend)**  
   - Parserbasierter Strip für `/queue`, `/model`, `/reasoning`, `/verbose` ist aktiv (Prefix-only Semantik).  
   - `reasoning_visibility`-Kontrollpfad ist in `RequestContext` und Lifecycle-Details verdrahtet.

9. **Predictability by Schema (strict config)** → **Erfüllt (grundlegend)**  
   - Strict unknown-key validation ist implementiert (feature-flagged) inkl. Startup-Fail-Fast bei aktivem Strict-Mode.  
   - `config.health` liefert Validierungsstatus (`validation_status`, `strict_unknown_keys_enabled`, `unknown_key_count`, `invalid_or_unknown`).

---

## 2) Hart priorisierte Implementierungsreihenfolge (exakt)

Ziel: Erst Steuerbarkeit + Reproduzierbarkeit, dann Kontext-/Tool-Qualität.

### Welle A (72h, sofort)

1. **SessionInboxService + queue_mode in RequestContext**
   - Neue Komponente: `backend/app/services/session_inbox_service.py`
   - RequestContext erweitern: `queue_mode: Literal["wait", "follow_up", "steer"]`
   - Config: `QUEUE_MODE_DEFAULT`, Queue-Limits (max length, TTL)
   - Acceptance:
     - deterministische FIFO-Reihenfolge pro Session
     - Overflow produziert kontrollierten Reject + Audit-Event

2. **WS receive/executor Split pro Session-Lane**
   - `ws_handler.py`: Receiver nur parse/enqueue, Executor arbeitet Inbox ab
   - Ein Worker pro Session-ID; kein Verlust bei parallel eingehenden Nachrichten
   - Acceptance:
     - 20 parallele Inputs in 1 Session -> alle verarbeitet, Reihenfolge stabil

3. **Steer-Checkpoint nach jedem Tool-Call**
   - In `ToolExecutionManager.run_tool_loop(...)`: nach jedem erfolgreich/fail abgeschlossenen Tool-Call Inbox prüfen
   - Bei `steer`: Restplan abbrechen, `steer_detected` + `steer_applied`, neue Message als Follow-up-Kontext
   - Acceptance:
     - Fehlrichtung wird innerhalb eines Tool-Zyklus unterbrochen

4. **Run-State + Stage-Event Skeleton (instrumentation first)**
   - Introduce states: `received -> queued -> planning -> tool_loop -> synthesis -> finalizing -> persisted -> completed|failed|cancelled`
   - Instrumentierung ist aktiv; optionaler harter Block bei Violation ist verfügbar via `RUN_STATE_VIOLATION_HARD_FAIL_ENABLED`
   - Acceptance:
     - jede Run-ID hat rekonstruierbare Stage-Kette inkl. `stage_skipped`

### Welle B (nächste 7–14 Tage)

5. **PromptKernelBuilder V1 + prompt_mode (`full|minimal|subagent`)**
   - Neues Modul `prompt_kernel_builder.py`
   - deterministische Sektionen + `prompt_hash` + `kernel_version`
   - Status: ✅ umgesetzt (03.03.2026)

6. **Context Cost APIs**
   - Neue Endpoints: `/api/control/context.list`, `/api/control/context.detail`
   - Segmentierte Token-Schätzung (system/policy/context/skills/tools/task)
   - Status: ✅ umgesetzt (03.03.2026, inklusive `context_segmented`-Präzisierung)

7. **Typed Tool Schemas aus ToolRegistry**
   - ToolSpec um enge JSON-Schemas erweitern
   - Function-calling Payload pro Tool mit `required`, `enum`, constraints

### Welle C (danach)

8. **Directive Layer OOB + Reasoning Visibility**
   - Parser + Strip-Logik vor Prompt-Build
   - `reasoning_visibility=off|summary|stream`

9. **Strict Config Validation + config.health**
   - fail-fast unknown keys
   - `/api/control/config.health` (schema version, overrides, risks)

---

## 3) Verifikationsprotokoll (pro Welle zwingend)

## A) Funktional
- Session-Lane unter Last: 1 Session, 20 parallele Inputs, Reihenfolge und Vollständigkeit prüfen
- Steer-Szenarien:
  - neuer Input zwischen Tool-Call 1 und 2
  - mehrere neue Inputs während langer Tool-I/O
- Queue-Modi:
  - `wait`: sequentiell warten
  - `follow_up`: hinten anstellen
  - `steer`: laufenden Plan nach Checkpoint abbrechen

## B) Audit/Observability
- Pflicht-Events vorhanden: `inbox_enqueued`, `run_dequeued`, `steer_detected`, `steer_applied`, `stage_event`
- Stage-Completeness >= 99.9%
- Event-Loss nahe 0

## C) Nicht-funktional
- `lane_queue_wait_ms_p95`
- `steer_interrupt_rate`
- `tool_selection_parse_repair_rate`
- `context_overhead_ratio`
- `tool_schema_token_share`
- `skills_snapshot_cache_hit_rate`
- `skills_preview_injection_rate` (inkl. `prompt_mode`-Split)
- `skills_preview_omitted_rate` (reason-basiert)
- `skills_manual_read_rate` (`read_file` auf `SKILL.md`)

Zielwerte (ab Canary, danach in Default stabilisieren):
- `skills_snapshot_cache_hit_rate` >= 70% bei wiederholten Hot-Session-Läufen
- `skills_preview_injection_rate`:
   - `full`: >= 90%
   - `minimal`: 50-85% (task-abhängig)
   - `subagent`: <= 35% (nur bei klarer Relevanz)
- `skills_preview_omitted_rate`:
   - `subagent_low_relevance` als häufigster Grund in `subagent`
   - `contracted_to_empty` <= 5% (sonst Kontraktionsbudget prüfen)
- `skills_manual_read_rate`:
   - >= 60% in Skill-intensiven Delegationsfällen (Qualitätsprobe)
   - <= 20% in Standardfällen ohne Skill-Bezug (Overfetch-Schutz)

## D) Security/Safety
- Directive-Injection-Test: Direktive im Fließtext darf keinen OOB-Effekt haben
- Policy-Konflikte (`allow/deny/also_allow`) bleiben deterministisch
- Persist-Transform-Policies bleiben aktiv (Redaction/Truncation)

---

## 4) Ticket-Schablone (verpflichtend je PR)

- Betroffene Stage(s): 0..9
- Entry-/Exit-Kriterien dokumentiert
- Neue Events + Payload dokumentiert
- Failure-Policy: `retry|abort|degrade|skip`
- Auditfelder: `run_id`, `session_id`, `stage`, `status`, `reason`, `latency_ms`
- Tests: unit + integration (+load/security falls betroffen)

---

## 5) Exakte 72h-Aufgabe (Copy/Paste)

1. Implement `SessionInboxService` + Unit Tests  
2. Extend `RequestContext` um `queue_mode` + defaults  
3. Refactor `ws_handler` in Receiver/Executor  
4. Add `steer` checkpoint into Tool-Loop  
5. Emit lifecycle events `steer_detected`/`steer_applied`  
6. Add run-state/stage skeleton events (instrumentation only)  
7. Run Lastprobe: 1 Session / 20 Inputs / Vollständigkeitsreport

---

## 6) Konkrete Verifikationskommandos (Backend)

Hinweis: in `backend/` ausführen.

- Unit/Integration schnell:
  - `pytest -q tests`
- Fokusläufe (nach Einführung neuer Tests):
  - `pytest -q tests -k "inbox or queue_mode or steer or ws_handler"`
- Optional Qualitätslauf:
  - `pytest -q --maxfail=1`

---

## 7) Entscheidende Gaps, die nicht weiter geschoben werden sollten

1. **Hook-Contract + Safety-Policy V2 fehlt** → unklare Hard-/Soft-Fail- und Timeout-Verträge je Hookpoint.  
2. **Multi-Agent-Isolation als Default-Contract fehlt** → erhöhtes Risiko von Workspace-/Credential-Kollisionen.  
3. **Strict Config Validation nur grundlegend** → zusätzliche Feldbereichs-/Typ-Härtungen für kritische Grenzwerte stehen aus.

Damit ist der Fahrplan verifiziert und auf eine unmittelbar umsetzbare Reihenfolge verdichtet.

---

## 8) Umsetzungsplan Vertiefung (Pattern 2 + 3)

Ziel: von „teilweise bis gut“ auf „stabil, messbar, reproduzierbar“ heben, ohne die bereits stabile Lane-/Steer-Logik zu gefährden.

### 8.1 Scope und Nicht-Ziele

In Scope:
- Context Engineering: Segment-Budgets, deterministischer Prompt-Kernel, belastbare Kosten-Sichtbarkeit (`context.list`/`context.detail`) und Event-Konsistenz.
- Skills Lazy-Loading: Snapshot nur bei aktivem Gating, harte Trennung „Skills Preview“ vs. „Skill Manual Load“, bessere Segmentierung nach `prompt_mode`.

Nicht in Scope (für diese Welle):
- Directive Layer OOB (`/queue`, `/model`, `/reasoning`, `/verbose`).
- Typed Tool Schemas / Action-Space-Härtung.
- Strict unknown-key fail-fast (Settings/Gateway).

### 8.2 Zielzustand (DoD für Pattern 2 + 3)

1. **Prompt-Kernel Determinismus V1.1**
    - Gleiche Inputs erzeugen identischen `prompt_hash`.
    - Sektionen und Truncation verhalten sich deterministisch je `prompt_mode`.
    - `kernel_version` + `prompt_hash` sind durchgängig in Audit/Lifecycle sichtbar.

2. **Kontextkosten belastbar statt heuristisch**
    - `context.list` / `context.detail` nutzen primär segmentierte Lifecycle-Events (`context_segmented`) je Phase (`planning|tool_loop|synthesis`).
    - Fallback-Heuristik nur noch, wenn Segment-Events fehlen (inkl. Flag `degraded_estimation=true`).
    - Tool-Schema-/Skills-Overhead ist getrennt ausweisbar.

3. **Skills Lazy-Loading reproduzierbar**
    - Bei deaktiviertem/gebocktem Skills-Gating wird kein Snapshot gebaut.
    - Bei aktivem Gating wird nur kompakte Skills-Preview injiziert (Name/Description/Location), kein vollständiges SKILL.md.
    - Skill-Manual-Lesen bleibt expliziter Tool-Schritt und wird als Event messbar.

### 8.3 Konkrete Implementierungswellen

#### Welle S1 (2–3 Tage): Prompt-Kernel + Segmentvertrag härten

Dateien:
- `backend/app/services/prompt_kernel_builder.py`
- `backend/app/agent.py`
- `backend/tests/test_prompt_kernel_builder.py`

Änderungen:
- `prompt-kernel.v1` auf `prompt-kernel.v1.1` heben, ohne Sektionen zu brechen.
- Zusätzlich zu `prompt_hash` einen stabilen `section_fingerprint` je Abschnitt erzeugen (Hash pro Sektion, keine Inhalte im Event).
- In `agent.py` bei `context_segmented` die Kernel-Metadaten (`kernel_version`, `prompt_hash`, `prompt_mode`, `phase`) konsistent mitschreiben.

Akzeptanz:
- Snapshot-basierte Tests: gleiche Inputs -> gleicher Hash; einzelne Sektionsänderung -> nur zugehöriger `section_fingerprint` ändert sich.
- Regressionslauf für vorhandene Kernel/Planner/Inbox-Tests bleibt grün.

#### Welle S2 (2–4 Tage): Context-Cost APIs präzisieren

Dateien:
- `backend/app/handlers/tools_handlers.py`
- `backend/app/control_models.py` (optional: Detail-Request erweitern)
- `backend/tests/test_context_*` (bestehende Context-Handler-Tests erweitern)

Änderungen:
- Segmentquelle strikt priorisieren: `context_segmented` Events > Fallback-Heuristik.
- In `context.detail` zusätzlich ausgeben:
   - `segment_source`: `event` oder `fallback`
   - `degraded_estimation`: bool
   - `phase_breakdown`: `planning|tool_loop|synthesis` inkl. Tokens/Share.
- In `context.list` Top-Overhead stabil sortieren und um `skills`/`tools` Gewichtung ergänzen.

Akzeptanz:
- Läufe mit Segment-Events zeigen 1:1 Event-basierte Werte.
- Läufe ohne Segment-Events liefern valide Fallback-Ausgabe inkl. `degraded_estimation=true`.
- Kein Breaking Change im bestehenden Response-Schema (`schema` bleibt `context.list.v1` / `context.detail.v1`, additive Felder erlaubt).

#### Welle S3 (3–5 Tage): Skills Lazy-Loading vertraglich absichern

Dateien:
- `backend/app/skills/service.py`
- `backend/app/services/tool_execution_manager.py`
- `backend/app/skills/prompt.py`
- `backend/app/handlers/skills_handlers.py`
- `backend/tests/test_skills_*` + `backend/tests/test_tool_execution_manager.py`

Änderungen:
- `SkillsService.build_snapshot()` mit leichter Cache-Strategie (TTL/mtime-basiert) für wiederholte Discover-Last in Hot Sessions.
- `tool_execution_manager.execute()` ergänzt klare Events:
   - `skills_snapshot_built`
   - `skills_snapshot_skipped`
   - `skills_preview_injected`
   - `skills_preview_omitted_by_prompt_mode`
- `prompt_mode`-basierte Skills-Kontraktion explizit machen:
   - `full`: normale Preview
   - `minimal`: reduzierte Preview (kürzeres Budget)
   - `subagent`: nur bei hoher Relevanz oder explizitem Bedarf
- `skills.prompt` Leittext schärfen: „erst Skill-Liste prüfen, dann gezielt SKILL.md lesen“ als verbindliche Schrittfolge.

Akzeptanz:
- Bei `skills_enabled=false`: kein Discover/Filter/Snapshot-Aufwand.
- Bei `prompt_mode=subagent`: mediane Skills-Segmentgröße signifikant kleiner als `full`.
- Kein Anstieg der Tool-Selection-Fehlrate durch zu aggressive Kürzung.

### 8.4 Verifikationsmatrix (verpflichtend)

Funktional:
- `full|minimal|subagent` gegen identischen Input vergleichen (Hash, Segmentgrößen, Antwortqualität).
- Canary-Gating testen (Agent-/Model-Match true/false).
- Snapshot-Truncation testen (`skills_max_prompt_chars` hart am Limit).

Observability:
- Pflichtfelder in `context_segmented`: `phase`, `prompt_mode`, `kernel_version`, `prompt_hash`, Segmentgrößen.
- `context.detail` zeigt Quelle und Degradierungsstatus zuverlässig.

Nicht-funktional:
- `context_overhead_ratio` trendet nach unten (insb. `skills`/`tools`).
- `tool_schema_token_share` bleibt stabil oder sinkt trotz besserer Sichtbarkeit.
- Zusatzlatenz durch Segment-Metrik < 5% p95.

Regression:
- Fokus: `pytest -q tests -k "prompt_kernel or context or skills or tool_execution_manager"`
- Full: `pytest -q tests`

### 8.5 Rollout und Risikoabsicherung

Rollout:
1. Shadow: nur Events/API-Felder erweitern, kein Verhalten ändern.
2. Canary: `skills`-Kontraktion je `prompt_mode` nur für definierte Agent-/Model-Profile.
3. Default: Kontraktion + Snapshot-Optimierung global aktiv.

Feature Flags (empfohlen):
- `PROMPT_KERNEL_V11_ENABLED`
- `CONTEXT_SEGMENT_EVENTS_STRICT_ENABLED`
- `SKILLS_PREVIEW_CONTRACTION_ENABLED`
- `SKILLS_SNAPSHOT_CACHE_ENABLED`

Abort-Kriterien:
- Antwortqualität regressiv in Kernpfaden.
- p95-Latenzanstieg > 10% über Baseline.
- Event-Completeness < 99.5%.

### 8.6 Ticket-Schnitt (direkt sprintfähig)

1. **P2-S1:** PromptKernel V1.1 + section fingerprints + Tests
2. **P2-S2:** Context APIs: event-first aggregation + degraded fallback flags
3. **P3-S1:** Skills snapshot cache + skip-path verification
4. **P3-S2:** Prompt-mode Skills contraction + lifecycle events
5. **P2/P3-QA:** KPI-baseline vs. delta report (mind. 3 Lastprofile)

Damit sind Pattern 2 und 3 in einer Reihenfolge geplant, die erst Messbarkeit/Determinismus absichert und danach die Kosten/Qualität optimiert.

---

## 9) Verifikations-Evidenz (03.03.2026, codebasiert)

### 9.1 Ausgeführte Fokusläufe

Ausgeführt in Repo-Root mit `backend/.venv`:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_prompt_kernel_builder.py backend/tests/test_tools_handlers_context_config.py backend/tests/test_tool_execution_manager.py backend/tests/test_ws_handler.py --maxfail=1 -o faulthandler_timeout=20`
- Ergebnis: **29 passed**

Hinweis zur Reproduzierbarkeit:
- Lauf mit Root-`.venv` (`.venv/Scripts/python.exe`) ist auf dieser Maschine wegen FastAPI/Pydantic/Typing-Inkompatibilität (Python 3.14 beta) nicht repräsentativ für Backend-Regressionen.
- Verbindliche Verifikation für dieses Backend erfolgt daher über `backend/.venv`.

### 9.2 Harte Codebelege (historischer Gap C, inzwischen geschlossen)

1. **Strict unknown-key fail-fast (historischer Stand vor T3)**
   - Vor T3 basierte `Settings` auf env-basierter Feldbelegung ohne explizites Unknown-Key-Enforcement.
   - `config.health` war vorhanden, zeigte jedoch keinen durchgängigen Validierungsstatus.
   - Dieser Gap ist in Abschnitt 12.4 als umgesetzt/verifiziert dokumentiert.

---

## 10) Exakte Next-72h-Reihenfolge (nach T3)

### T4) Hook-Contract + Safety-Policy V2 (P4)

Ziel:
- Versionierter Hook-Vertrag mit expliziten Timeout-/Failure-Policies je Hookpoint.

Dateien (Startschnitt):
- `backend/app/agent.py`
- `backend/app/services/tool_execution_manager.py`
- `backend/app/handlers/run_handlers.py`
- neue Tests: `backend/tests/test_hooks_*`

Akzeptanz:
- Jeder Hookpoint dokumentiert `hook_contract_version`, `timeout_ms`, `failure_policy`.
- Defekter Hook führt standardmäßig nicht zu globalem Run-Abbruch (außer explizit Hard-Fail).

### T5) Multi-Agent-Isolation Default-Contract (P5)

Ziel:
- Harte Default-Isolation für Workspace/Skills/Credentials je Agent.

Dateien (Startschnitt):
- `backend/app/custom_agents.py`
- `backend/app/main.py`
- `backend/app/subrun_endpoints.py`
- neue Tests: `backend/tests/test_multi_agent_isolation.py`

Akzeptanz:
- Kein impliziter Zugriff eines Agents auf fremde Workspace-/Credential-Scopes.
- Delegation/Handover bleibt funktional, aber strikt scoped.

### Pflicht-Verifikation nach Umsetzung

Fokus:
- `pytest -q backend/tests -k "hooks or ws_handler or tool_execution_manager or subrun or isolation" --maxfail=1`

Regression (Backend):
- `pytest -q backend/tests --maxfail=1`

Exit-Gates:
- Keine Regression in Lane/Steer/PromptKernel/Context/Config-Tests.
- Neue Unit-/Integrations-Cases für Hook-Safety + Isolation grün.
- Event-/Audit-Vertrag aktualisiert und dokumentiert.

---

## 11) Fortschritt T1/T2 + Hardening (03.03.2026, verifiziert)

### T1 – Typed Tool Schemas (Status: ✅ umgesetzt)

Code:
- `backend/app/services/tool_registry.py`: typed `parameters` pro Tool + `build_function_calling_tools(...)`.
- `backend/app/agent.py`: Registry-basierte Tool-Definitionen in Tool-Selection verdrahtet.
- `backend/app/services/tool_execution_manager.py`: typed Tool-Definitionen in Function-Calling-Pfad durchgereicht.
- `backend/app/llm_client.py`: übergebene typed `tool_definitions` werden im Request-Payload genutzt.

Tests:
- `backend/tests/test_tool_registry.py`
- `backend/tests/test_llm_client.py`

### T2 – Directive Layer OOB + Reasoning Visibility (Status: ✅ umgesetzt)

Code:
- Neu: `backend/app/services/directive_parser.py`
   - Parser + Strip für `/queue`, `/model`, `/reasoning`, `/verbose`.
   - Prefix-only Semantik (Inline-Text bleibt unverändert, kein OOB-Effekt).
- `backend/app/ws_handler.py`
   - Directive-Parsing im Receive-Pfad vor Enqueue/Dispatch.
   - Overrides + `directives_applied` in Lifecycle-Details.
   - `reasoning_level` und `reasoning_visibility` in `RequestContext` durchgereicht.
- `backend/app/handlers/run_handlers.py` und `backend/app/run_endpoints.py`
   - Directive-Parsing auch im REST-/Background-Pfad.
- `backend/app/interfaces/request_context.py`
   - Neue Felder: `reasoning_level`, `reasoning_visibility`.

Tests:
- Neu: `backend/tests/test_directive_parser.py`
- Erweiterung: `backend/tests/test_ws_handler.py`

### Verifikationsläufe (grün)

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_directive_parser.py backend/tests/test_ws_handler.py --maxfail=1 -o faulthandler_timeout=20` → **12 passed**
- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_backend_e2e.py -k "websocket_user_message_emits_final_and_request_completed or websocket_command_intent_policy_block_emits_tool_selection_empty or websocket_tool_selection_empty_triggers_single_replan_then_completes" --maxfail=1 -o faulthandler_timeout=20` → **3 passed**
- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_prompt_kernel_builder.py backend/tests/test_tools_handlers_context_config.py backend/tests/test_tool_execution_manager.py backend/tests/test_ws_handler.py backend/tests/test_tool_registry.py backend/tests/test_llm_client.py backend/tests/test_directive_parser.py --maxfail=1 -o faulthandler_timeout=20` → **47 passed**
- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_handlers_contracts.py backend/tests/test_run_state_machine.py backend/tests/test_ws_handler.py -o faulthandler_timeout=20 --maxfail=1` → **21 passed**

### Zusatz-Hardening (nach T2)

- `run_handlers._run_background_message(...)`: Directive-Parsing in den `try`-Block verschoben, damit `GuardrailViolation` deterministisch in Fail-/Cleanup-Pfad läuft.
- `ws_handler`: Non-User-Pfade (`init_run`, Routing-Heuristik, `subrun_spawn`) nutzen nun konsistent bereinigten Directive-Content + Model-Override.
- API-Regressionstest ergänzt (`run.start` + `run.wait`) für Directive-only Fehlerfall im Background-Run.

### Verbleibender Kernpunkt

- **T3 Strict Config Validation (unknown-key fail-fast)** ist umgesetzt/verifiziert.
- Nächste priorisierte Kernpunkte: **P4 Hook-Contract/Safety** und **P5 Multi-Agent-Isolation**.

---

## 12) Exakter T3-Ausführungsschnitt (Strict Config Validation)

Ziel: Unknown Keys im Settings-/Gateway-Config-Pfad kontrolliert fail-fast machen (rollout-fähig), ohne bestehende Laufzeitpfade zu brechen.

### 12.1 Implementierung (exakt, in Reihenfolge)

1. **`config.py`: Strict-Validator als explizite Komponente einführen**
   - Neue Routine: z. B. `validate_environment_config(strict_unknown_keys: bool) -> dict`.
   - Basis: erlaubte Key-Menge aus `Settings.model_fields` + Whitelist für nicht-backend-relevante Systemvariablen.
   - Ergebnisobjekt enthält mindestens:
      - `schema_version`
      - `strict_mode`
      - `unknown_keys`
      - `warnings`
      - `is_valid`

2. **Feature-Flag für harte Durchsetzung**
   - Neue Settings-Felder:
      - `config_strict_unknown_keys_enabled` (bool, default `False`)
      - optional `config_strict_unknown_keys_allowlist` (CSV, default leer)
   - Bei aktivem Flag und `unknown_keys` > 0: deterministischer Startup-Abbruch mit präziser Fehlermeldung.

3. **`main.py`: Startup-Validation Hook verdrahten**
   - Validation früh im Startup ausführen (vor Runtime-Init).
   - Bei Hard-Fail: sauberer `RuntimeError` mit `unknown_keys`-Auszug.
   - Bei Soft-Mode: Warning-Log + normaler Start.

4. **`tools_handlers.py`: `config.health` um Validierungsstatus erweitern**
   - `invalid_or_unknown` aus Validator-Ergebnis befüllen.
   - Additive Felder ergänzen:
      - `validation_status` (`ok|warning|error`)
      - `strict_unknown_keys_enabled`
      - `unknown_key_count`
   - Schema bleibt `config.health.v1` (nur additive Felder).

5. **Tests ergänzen**
   - Neu: `backend/tests/test_config_validation.py`
      - unknown keys im soft mode -> `is_valid=True`, unknown list gefüllt
      - unknown keys im strict mode -> `is_valid=False` bzw. Startup-Fehler
      - allowlist respektiert
   - Erweiterung: `backend/tests/test_tools_handlers_context_config.py`
      - `config.health` enthält Validation-Felder und Unknown-Summary.

### 12.2 Verifikationsprotokoll (nach Implementierung, verpflichtend)

Ausführung in Repo-Root:

- Fokuslauf:
  - `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_config_validation.py backend/tests/test_tools_handlers_context_config.py backend/tests/test_router_units.py --maxfail=1 -o faulthandler_timeout=20`
- Regression:
  - `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "config_validation or context_config or ws_handler or directive or tool_registry" --maxfail=1 -o faulthandler_timeout=20`

Exit-Gates:
- Strict-Mode blockiert Start bei unbekannten Config-Keys reproduzierbar.
- Soft-Mode liefert Warnungen ohne Startup-Abbruch.
- `config.health` zeigt Unknown-Key-Status ohne Breaking Changes.

### 12.3 Live-Verifikation (03.03.2026, erneut ausgeführt)

Fokusläufe auf aktuellem Stand:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_tools_handlers_context_config.py backend/tests/test_router_units.py -o faulthandler_timeout=20 --maxfail=1`
  - Ergebnis: **10 passed**

- Unknown-Key-Nachweis (Code-Snippet im `backend`-CWD):
  - `os.environ['THIS_SHOULD_BE_UNKNOWN_KEY']='1'` + `Settings()`
  - Ergebnis:
     - `unknown_key_present_in_dump False`
     - kein Startup-/Init-Fehler

Interpretation:
- (Historischer Stand vor T3) Unknown Keys wurden bis dahin nicht als Fail-Fast erzwungen.

### 12.4 Umsetzung T3 (03.03.2026, abgeschlossen)

Implementiert:

- `backend/app/config.py`
   - Neue Settings-Flags:
      - `CONFIG_STRICT_UNKNOWN_KEYS_ENABLED`
      - `CONFIG_STRICT_UNKNOWN_KEYS_ALLOWLIST`
   - Neue Validator-Funktion `validate_environment_config(...)` mit:
      - scoped Unknown-Key-Erkennung für Backend-Config-Keys
      - Soft-/Strict-Mode (`warning` vs. `error`)
      - reproduzierbare Summary (`unknown_keys`, `validation_status`, `is_valid`)

- `backend/app/main.py`
   - Startup-Hook validiert Config vor Runtime-Initialisierung.
   - Bei Strict-Mode + Unknown-Keys: deterministischer Startup-Abbruch via `RuntimeError`.
   - Bei Soft-Mode: Warning-Logging.

- `backend/app/handlers/tools_handlers.py`
   - `config.health` nutzt Validator-Ergebnis und liefert additive Felder:
      - `validation_status`
      - `strict_unknown_keys_enabled`
      - `unknown_key_count`
      - `invalid_or_unknown` (Unknown-Key-Liste)

Tests:

- Neu: `backend/tests/test_config_validation.py`
   - soft mode: Unknown-Key -> `warning`, `is_valid=True`
   - strict mode: Unknown-Key -> `error`, `is_valid=False`
   - allowlist: Unknown-Key unterdrückt -> `ok`, `is_valid=True`

- Erweiterung: `backend/tests/test_tools_handlers_context_config.py`
   - `config.health`-Response enthält neue Validierungsfelder.

Verifikation nach Implementierung:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_config_validation.py backend/tests/test_tools_handlers_context_config.py backend/tests/test_router_units.py -o faulthandler_timeout=20 --maxfail=1`
   - Ergebnis: **13 passed**

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "config_validation or context_config or ws_handler or directive or tool_registry" --maxfail=1 -o faulthandler_timeout=20`
   - Ergebnis: **29 passed, 475 deselected**

Status T3:
- ✅ **Strict Config Validation (unknown-key fail-fast) implementiert und fokussiert verifiziert**.

---

## 13) Exakte Verifikation + Next-72h-Schnitt für P4/P5 (03.03.2026, live)

### 13.1 Live-Verifikation (heute ausgeführt)

Ausführung in Repo-Root:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "hooks or isolation or subrun or ws_handler or config_validation" --maxfail=1 -o faulthandler_timeout=20`
   - Ergebnis: **49 passed, 1 skipped, 456 deselected**

Interpretation:
- Lane/WS/Config/Subrun-Basis ist weiterhin stabil.
- Für den priorisierten Restscope bleiben die erwarteten Kernlücken: **Hook-Contract/Safety V2** und **Default-Multi-Agent-Isolation**.

### 13.2 Codebasierter Ist-Stand (P4/P5, belegt)

P4 (Hooks):
- Hook-Invocation ist vorhanden (`before_prompt_build`, `before_tool_call`, `after_tool_call`, `agent_end`) und emittiert `hook_invoked`/`hook_failed`.
- Es fehlt weiterhin ein expliziter, versionierter Hook-Vertrag pro Hookpoint (`hook_contract_version`, `timeout_ms`, `failure_policy`) als enforcebarer Runtime-Contract.
- Es gibt keine dedizierte Hook-V2-Testdatei (`test_hooks_*`), nur indirekte Hook-Abdeckung in bestehenden Tool-Tests.

P5 (Isolation):
- Subrun-Lane/Visibility/Depth-Guards sind vorhanden und getestet.
- Harte Agent-Isolation als Default-Contract (separate `workspace_root`/`skills_dir`/Credential-Scope je Agent) ist noch nicht als durchgehender Standard verdrahtet.
- Es gibt keine dedizierte Isolations-Testdatei (`test_multi_agent_isolation.py`) mit negativen Cross-Scope-Fällen.

### 13.3 Exakter 72h-Umsetzungsschnitt (nur P4/P5)

1. **P4-S1 Hook-Contract V2 (Schema + Resolver)**
    - Dateien:
       - `backend/app/services/hook_contract.py` (neu)
       - `backend/app/agent.py`
       - `backend/app/services/tool_execution_manager.py`
    - Inhalt:
       - Contract je Hookpoint: `hook_contract_version`, `timeout_ms`, `failure_policy` (`soft_fail|hard_fail|skip`).
       - zentraler Resolver für Defaults + optionale Settings-Overrides.
    - Exit:
       - Hookpoint-Metadaten werden konsistent in Lifecycle-Details emittiert.

2. **P4-S2 Hook-Safety Enforcement (Timeout + Failure-Isolation)**
    - Dateien:
       - `backend/app/agent.py`
       - `backend/app/services/tool_execution_manager.py`
    - Inhalt:
       - Hook-Ausführung via `asyncio.wait_for` (per Hookpoint).
       - Fehlerpfad strikt nach `failure_policy`:
          - `soft_fail`: Event + Run läuft weiter
          - `hard_fail`: deterministischer Abbruch
          - `skip`: Hook überspringen + Event
    - Exit:
       - Defekter Hook verursacht keinen globalen Abbruch ohne explizite Hard-Fail-Policy.

3. **P5-S1 Agent-Isolation Contract (Defaults + Guardrails)**
    - Dateien:
       - `backend/app/custom_agents.py`
       - `backend/app/main.py`
       - `backend/app/subrun_endpoints.py`
       - ggf. `backend/app/config.py` (Flags/Defaults)
    - Inhalt:
       - pro Agent effektive Isolation-Config (workspace, skills, credential scope).
       - deny-by-default bei Scope-Überschreitung; nur explizite allow-Regeln erlauben Cross-Scope.
    - Exit:
       - Kein impliziter Zugriff zwischen Agent-Scopes im Standardpfad.

4. **P5-S2 Delegation/Handover gegen Isolation härten**
    - Dateien:
       - `backend/app/main.py`
       - `backend/app/subrun_endpoints.py`
    - Inhalt:
       - Spawn/Handover transportiert nur erlaubte Scope-Metadaten.
       - Visibility-Entscheide bleiben kompatibel, aber nicht scope-erweiternd.
    - Exit:
       - Delegation funktioniert, ohne Isolation aufzuweichen.

5. **QA/Verifikation (verpflichtend)**
    - Neue Tests:
       - `backend/tests/test_hooks_contract_v2.py`
       - `backend/tests/test_multi_agent_isolation.py`
    - Fokuslauf:
       - `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "hooks_contract_v2 or multi_agent_isolation or subrun or ws_handler" --maxfail=1 -o faulthandler_timeout=20`
    - Regressionslauf:
       - `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests --maxfail=1 -o faulthandler_timeout=20`

### 13.4 Harte Exit-Gates (P4/P5)

- Hookpoint-Events tragen stets `hook_contract_version`, `timeout_ms`, `failure_policy`, `status`.
- Timeouts und Exceptions sind auditierbar (`hook_timeout`/`hook_failed`) und policy-konsistent.
- Mindestens ein negativer Isolationstest blockiert Cross-Agent-Workspace/Skills/Credential-Zugriff.
- Keine Regression in bestehenden `ws_handler`-, `subrun`-, `config_validation`-Fokusläufen.

### 13.5 Fortschritt P4-S1 (03.03.2026, umgesetzt + verifiziert)

Implementiert:

- Neues Modul: `backend/app/services/hook_contract.py`
   - `resolve_hook_execution_contract(...)` liefert versionierten Contract pro Hookpoint.
   - Contract-Felder: `hook_contract_version`, `timeout_ms`, `failure_policy` (`soft_fail|hard_fail|skip`).
- `backend/app/config.py`
   - Neue Hook-Settings:
      - `HOOK_CONTRACT_VERSION`
      - `HOOK_TIMEOUT_MS_DEFAULT`
      - `HOOK_TIMEOUT_MS_OVERRIDES` (CSV `hook:ms,...`)
      - `HOOK_FAILURE_POLICY_DEFAULT`
      - `HOOK_FAILURE_POLICY_OVERRIDES` (CSV `hook:policy,...`)
- `backend/app/agent.py`
   - `_invoke_hooks(...)` nutzt nun Contract-Resolver + `asyncio.wait_for`-Timeouts.
   - Lifecycle-Events enthalten konsistent Contract-Metadaten.
   - Failure-Policies sind enforced (`soft_fail`, `hard_fail`, `skip`).
   - Hookpoints erweitert um `before_model_resolve` und `before_transcript_append`.
- `backend/app/services/tool_execution_manager.py`
   - Neuer Hookpoint `tool_result_persist` vor Persistierung von Tool-Resultaten.

Tests:

- Neu: `backend/tests/test_hooks_contract_v2.py`
   - Defaults/Overrides des Contract-Resolvers.
   - Soft-Fail mit Event-Metadaten.
   - Hard-Fail bei Timeout.

Live-Verifikation:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_hooks_contract_v2.py backend/tests/test_tool_execution_manager.py backend/tests/test_ws_handler.py -o faulthandler_timeout=20 --maxfail=1`
   - Ergebnis: **25 passed**

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "hooks or isolation or subrun or ws_handler or config_validation" --maxfail=1 -o faulthandler_timeout=20`
   - Ergebnis: **53 passed, 1 skipped, 456 deselected**

### 13.6 Fortschritt P5-S1 (03.03.2026, umgesetzt + verifiziert)

Implementiert:

- Neues Modul: `backend/app/services/agent_isolation.py`
   - `AgentIsolationPolicy` mit Default-Enforcement und Pair-Allowlist.
   - `resolve_agent_isolation_profile(...)` für `workspace_scope` / `skills_scope` / `credential_scope`.
- `backend/app/config.py`
   - Neue Settings:
      - `AGENT_ISOLATION_ENABLED` (Default: `true`)
      - `AGENT_ISOLATION_ALLOWED_SCOPE_PAIRS` (CSV, z. B. `head-agent->coder-agent`)
- `backend/app/custom_agents.py`
   - `CustomAgentDefinition` / `CustomAgentCreateRequest` erweitert um optionale Scope-Felder:
      - `workspace_scope`, `skills_scope`, `credential_scope`
   - Persistenzpfad (`upsert`) schreibt Scope-Felder deterministisch mit.
- `backend/app/main.py`
   - Subrun-Spawn prüft Isolation-Entscheid zwischen Source- und Target-Agent vor Spawn.
   - Bei Verstoß: `subrun_isolation_blocked` + `GuardrailViolation` (deny-by-default).
   - Source-Agent wird beim Setzen des Spawn-Handlers pro Agent gebunden (`owner_agent_id`).

Tests:

- Neu: `backend/tests/test_multi_agent_isolation.py`
   - Blocked-by-default bei Cross-Scope.
   - Allowlist-Freigabe für explizite Paare.
   - Persistenz/Resolution der neuen Custom-Agent-Scope-Felder.

Live-Verifikation:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_multi_agent_isolation.py backend/tests/test_subrun_visibility_scope.py backend/tests/test_hooks_contract_v2.py backend/tests/test_ws_handler.py -o faulthandler_timeout=20 --maxfail=1`
   - Ergebnis: **19 passed**

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "hooks or isolation or subrun or ws_handler or config_validation" --maxfail=1 -o faulthandler_timeout=20`
   - Ergebnis: **58 passed, 1 skipped, 456 deselected**

### 13.7 Fortschritt P5-S2 (03.03.2026, umgesetzt + verifiziert)

Implementiert:

- `backend/app/main.py`
   - Delegation-Scope-Metadaten werden vor Rückgabe explizit sanitisiert (`source_agent_id`, `target_agent_id`, `allowed`, `reason`).
   - Handover-Contract aus Subrun-Lane wird im Spawn-Rückgabepfad auf erlaubte Felder reduziert (`terminal_reason`, `confidence`, `result`).
- `backend/app/agent.py`
   - Structured `spawn_subrun`-Antworten werden im Agent vor Weitergabe explizit sanitisiert.
   - Whitelist für Handover-Metadaten (`terminal_reason`, `confidence`, `result`, optional `follow_up_questions`).
   - Whitelist für Delegation-Scope-Metadaten (`source_agent_id`, `target_agent_id`, `allowed`, `reason`).
   - Nicht erlaubte Felder werden nicht in `handover_contract`/`delegation_scope` weitertransportiert.

Tests:

- Erweiterung: `backend/tests/test_tool_selection_offline_eval.py`
   - Neuer Fall verifiziert, dass zusätzliche/sensitive Felder aus structured `spawn_subrun`-Payloads nicht durchgereicht werden.

Live-Verifikation:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_tool_selection_offline_eval.py backend/tests/test_multi_agent_isolation.py backend/tests/test_ws_handler.py -o faulthandler_timeout=20 --maxfail=1`
   - Ergebnis: **58 passed**

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "hooks or isolation or subrun or ws_handler or config_validation" --maxfail=1 -o faulthandler_timeout=20`
   - Ergebnis: **59 passed, 1 skipped, 456 deselected**

### 13.8 Review-Follow-up (03.03.2026): Source-Agent-Identität im Delegationspfad gehärtet

Anlass:
- Code-Review hat gezeigt, dass Custom-Agent-Delegation im `spawn_subrun`-Pfad potenziell mit Base-Agent-Identität ausgewertet werden konnte.

Fix:

- `backend/app/agent.py`
   - Source-Agent-Identität wird per `ContextVar` im Agent gehalten und im `spawn_subrun`-Call explizit als `source_agent_id` weitergereicht.
- `backend/app/agents/head_agent_adapter.py`
   - Forwarder für `set_source_agent_context(...)` / `reset_source_agent_context(...)` ergänzt.
- `backend/app/custom_agents.py`
   - `CustomAgentAdapter.run(...)` setzt Source-Agent-Context auf `definition.id` für die Dauer des Runs und resettet deterministisch im `finally`.
- `backend/app/main.py`
   - Bound Spawn-Handler nutzt Owner-ID nur noch als Fallback, wenn `source_agent_id` nicht explizit übergeben wurde.

Tests:

- Erweiterung: `backend/tests/test_multi_agent_isolation.py`
   - Neuer Test verifiziert Source-Context-Propagation + Cleanup für Custom-Agent-Delegation.

Live-Verifikation:

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_multi_agent_isolation.py backend/tests/test_tool_selection_offline_eval.py backend/tests/test_hooks_contract_v2.py backend/tests/test_ws_handler.py -o faulthandler_timeout=20 --maxfail=1`
   - Ergebnis: **63 passed**

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests -k "hooks or isolation or subrun or ws_handler or config_validation" --maxfail=1 -o faulthandler_timeout=20`
   - Ergebnis: **60 passed, 1 skipped, 456 deselected**

### 13.9 Full-Regression-Evidenz + Rest-Risiko-Matrix (03.03.2026)

Full-Regression (Backend):

- `./backend/.venv/Scripts/python.exe -m pytest -q backend/tests --maxfail=1 -o faulthandler_timeout=20`
  - Ergebnis: **514 passed, 3 skipped**

Rest-Risiko-Matrix (nach aktuellem Stand):

1. **Hook-Safety bei synchronen, blockierenden Hooks**
   - Risiko: `asyncio.wait_for` schützt nur awaitables; harte sync-Blocker können Event-Loop-Latenz verursachen.
   - Impact: mittel
   - Mitigation (nächste Iteration): optionale Ausführung synchroner Hooks in separatem Executor + Timeout-Watchdog.

2. **Isolation-Allowlist-Fehlkonfiguration (Operator-Risiko)**
   - Risiko: zu breite `AGENT_ISOLATION_ALLOWED_SCOPE_PAIRS` kann Schutzwirkung reduzieren.
   - Impact: mittel
   - Mitigation (nächste Iteration): `config.health` um Isolation-Warnflags erweitern (z. B. Wildcard-Paare, ungewöhnlich viele Freigaben).

3. **Lifecycle-Contract-Drift bei neuen Hook-/Isolation-Events**
   - Risiko: künftige Event-Änderungen ohne Schema-Contract-Test könnten Consumer brechen.
   - Impact: niedrig bis mittel
   - Mitigation (nächste Iteration): dedizierte Contract-Tests für `hook_*` + `subrun_isolation_*` Payload-Schemas.