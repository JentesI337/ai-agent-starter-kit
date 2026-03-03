# Backend Execution + Verifikation (Codebasiert)

Stand: 03.03.2026  
Scope: `backend/app/*`  
Referenzen: `fahrplan.md`, `importantPattern.md`

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

Hinweis: Nächste offene Kernpunkte liegen in Welle B/C (Typed Tool Schemas, Directive Layer OOB, strict unknown-key fail-fast).

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

4. **Typed Tools + Action-Space Shaping** → **Teilweise**  
   - Function-calling Pfad ist vorhanden, aber Tool-Args bleiben weitgehend generisch.  
   - Kein durchgängig enger JSON-Schema-Contract pro Tool aus Registry für Auswahl/Validierung.

5. **Loop Guardrails** → **Erfüllt (stark)**  
   - `ToolCallGatekeeper` + Thresholds + lifecycle events sind implementiert.  
   - Circuit-breaker/Warning-Pfade vorhanden.

6. **Hooks/Interceptors als Middleware** → **Teilweise bis gut**  
   - Hooks `before_prompt_build`, `before_tool_call`, `after_tool_call`, `agent_end` sind integriert.  
   - Es fehlt ein versionierter Hook-Contract inkl. klarer Safety-Policy pro Hookpoint (Hard-Fail/Soft-Fail/Timeout als Vertragsebene).

7. **Multi-Agent Delegation + Isolation** → **Teilweise**  
   - Subrun-Lane, Depth-Guards, Child-Limits, Handover sind vorhanden.  
   - Harte Agent-Isolation (workspace/skills/credential-scope je Agent) ist noch nicht vollständig als Default-Contract umgesetzt.

8. **Operator Controls (Directive Layer OOB)** → **Fehlt (kernig)**  
   - Kein parserbasierter Strip für `/queue`, `/model`, `/reasoning`, `/verbose`.  
   - Kein `reasoning_visibility`-Kontrollpfad im RequestContext.

9. **Predictability by Schema (strict config)** → **Fehlt/Teilweise**  
   - `config.health` Endpoint ist vorhanden.  
   - `Settings` basiert auf Pydantic, aber ohne strikt erzwungenes Unknown-Key-Fail-Fast auf Gateway-Ebene.

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

1. **Directive Layer fehlt vollständig** → hohes Fehlsteuerungsrisiko.  
2. **Typed Tool Schemas nicht stringent** → unnötige Parse/Repair-Last.  
3. **Strict unknown-key fail-fast fehlt** → Drift/Ghost-Bugs wahrscheinlicher.

Damit ist der Fahrplan verifiziert und auf eine unmittelbar umsetzbare Reihenfolge verdichtet.