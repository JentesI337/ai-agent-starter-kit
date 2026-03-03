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
- ✅ `PromptKernelBuilder` auf `prompt-kernel.v1.1` gehoben: stabile `section_fingerprints` ergänzt, `context_segmented` enthält nun `kernel_version`/`prompt_hash`/`prompt_mode`.
- ✅ Context-Cost APIs präzisiert: event-first Aggregation aktiv, additive Felder `segment_source`, `degraded_estimation`, `phase_breakdown` in `context.list`/`context.detail`.
- ✅ Skills Lazy-Loading S3 umgesetzt: Snapshot-Cache (TTL/mtime), Events `skills_snapshot_built|skills_snapshot_skipped|skills_preview_injected|skills_preview_omitted_by_prompt_mode|skills_manual_read`, prompt-mode Kontraktion aktiv.
- ✅ S3 Fokus-Tests grün (`test_skills_service`, `test_tool_execution_manager`), plus Regressions-Fokus (`test_prompt_kernel_builder`, `test_tools_handlers_context_config`, `test_planner_agent`, `test_session_inbox_service`).

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

1. **Directive Layer fehlt vollständig** → hohes Fehlsteuerungsrisiko.  
2. **Typed Tool Schemas nicht stringent** → unnötige Parse/Repair-Last.  
3. **Strict unknown-key fail-fast fehlt** → Drift/Ghost-Bugs wahrscheinlicher.

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