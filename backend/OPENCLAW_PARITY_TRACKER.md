# Openclaw Parity Tracker (Head-Agent)

Stand: 2026-03-02  
Owner: Backend Agent Team  
Scope: `backend/` Head-Agent, Toolchaining, Orchestration, Lifecycle

## 1) Ziel

Unser `HeadAgent` soll auf das Robustheits- und Leistungsniveau des Openclaw-Agenten bei:
- Reasoning-Zyklus
- Toolchaining
- Orchestrierung (inkl. Subruns)
- Recovery/Fallback-Verhalten

## 2) Quellenbasis (ohne Spekulation)

Analysierte Openclaw-Module:
- `examplerepos/openclaw/src/agents/pi-tools.before-tool-call.ts`
- `examplerepos/openclaw/src/agents/tool-loop-detection.ts`
- `examplerepos/openclaw/src/agents/tool-policy-pipeline.ts`
- `examplerepos/openclaw/src/agents/tool-policy-pipeline.test.ts`
- `examplerepos/openclaw/src/agents/pi-embedded-runner/run.ts`
- `examplerepos/openclaw/src/agents/pi-embedded-runner/compact.ts`
- `examplerepos/openclaw/src/agents/pi-embedded-subscribe.ts`
- `examplerepos/openclaw/src/agents/subagent-spawn.ts`
- `examplerepos/openclaw/src/agents/subagent-registry.ts`

Verglichene eigene Module:
- `backend/app/agent.py`
- `backend/app/orchestrator/pipeline_runner.py`
- `backend/app/orchestrator/subrun_lane.py`
- `backend/app/services/tool_policy_service.py`

---

## 3) Findings

### F1: Openclaw hat einen zentralen Pre-Tool Control-Point
Openclaw bündelt vor jedem Toolcall in einem Hook:
- Loop-Erkennung (warn/block)
- Warning-Key-Steuerung
- Param-Mutation
- Outcome-Tracking

Auswirkung: konsistente Regeln für alle Toolcalls, weniger verteilte Logik.

### F2: Loop-Detektion in Openclaw ist outcome-basiert und signaturbezogen
Insbesondere `poll_no_progress`/`ping_pong` prüfen Tool+Args-Signaturen und Ergebnis-Hashes, nicht nur globale Wiederholung.

Auswirkung: weniger False Positives, präziseres Blocken.

### F3: Openclaw nutzt abgestufte Signals (Warnung -> Critical)
Warnungen und Blockaden sind getrennt, inklusive deduplizierter/bucketed Warn-Emission.

Auswirkung: früheres Gegensteuern ohne unnötig harte Unterbrechungen.

### F4: Openclaw-Runloop hat robuste Recovery-Kette
Im Runner vorhanden:
- Retry-Limits (hart begrenzt)
- Context-overflow Behandlung
- Auto-Compaction
- Tool-Result-Truncation als Fallback
- reason-klassifizierte Failover-Pfade

Auswirkung: hohe Stabilität unter Last und bei problematischen Modellantworten.

### F5: Openclaw-Subagent-Registry ist resilient
Subagent-Handling beinhaltet Restore/Reconcile/Retry-Grace/Orphan-Cleanup und ausfallsichere Announce-Flows.

Auswirkung: robustere Child-Run-Lebenszyklen.

### F6: Tool-Policy-Pipeline degradiert unknown allowlist sicher
Unknown-Allows führen nicht zu Capability-Kollaps der Core-Tools; stattdessen Warnung + sichere Degradierung.

Auswirkung: weniger "Policy lockout" durch Fehlkonfiguration.

---

## 4) Bereits umgesetzte Verbesserungen (im Backend)

### U1: Poll-no-progress signaturbasiert
In `backend/app/agent.py` auf Tool+Args+Outcome umgestellt (statt globaler Outcome-Streak).

### U2: Ping-Pong nur mit No-Progress-Evidenz kritisch blocken
Ping-Pong-Blocking an stabile no-progress Evidenz gekoppelt.

### U3: Gestuftes Ping-Pong Verhalten
Warn-Event vor Critical-Block (`tool_loop_ping_pong_warn` -> `tool_loop_ping_pong_blocked`).

### U4: Warning-Key Dedupe
Warnungen pro Pattern-Key nur einmal pro Run emittiert (`warning_key` in Lifecycle-Details).

### U5: Unknown-only request allowlist degradiert sicher
`tool_policy.allow` mit nur unbekannten Tools kollabiert nicht mehr die Baseline-Tools; inklusive Diagnostik in `tool_policy_resolved`.

### U6: Tests erweitert und grün
- `tests/test_tool_selection_offline_eval.py`
- `tests/test_backend_e2e.py`

### U7: P1-Teilstufe umgesetzt — zentraler ToolCallGatekeeper
- Neues Modul: `backend/app/services/tool_call_gatekeeper.py`
- `HeadAgent._execute_tools` nutzt jetzt zentralen Gatekeeper für:
   - pre-tool loop checks (warn/block)
   - post-tool no-progress checks
   - loop summary payload
- Verhalten/Events bleiben kompatibel; bestehende Tests bleiben grün.

### U8: P1-Teilstufe 2 — Policy-Override-Kandidaten zentralisiert
- Gatekeeper-Modul enthält jetzt auch die Extraktion von Policy-Override-Kandidaten (`run_command`, `spawn_subrun`) über `collect_policy_override_candidates(...)`.
- `HeadAgent._approve_blocked_process_tools_if_needed(...)` nutzt diesen zentralen Pfad statt eigener Kandidatenlogik.
- Ergebnis: weniger verstreute Approval-Logik, konsistenter Pre-Tool-Entscheidungspfad.

### U9: P1-Teilstufe 3 — Param-Normalisierung als expliziter Gatekeeper-Schritt
- Gatekeeper-Modul enthält jetzt `prepare_action_for_execution(...)` als expliziten Pre-Tool-Preparation-Step.
- `HeadAgent._execute_tools(...)` nutzt diesen Pfad für Action-Parsing, Tool-Normalisierung und Argument-Evaluierung vor der Toolausführung.
- Ergebnis: weiterer Abbau von Inline-Entscheidungslogik in `agent.py`, konsistenterer Gatekeeper-Flow.

### U10: P2-Teilstufe 1 — Runner Retry-Cap Guard
- Neue Config: `PIPELINE_RUNNER_MAX_ATTEMPTS` (`settings.pipeline_runner_max_attempts`, default `16`).
- `PipelineRunner._run_with_fallback(...)` erzwingt jetzt ein globales Attempt-Limit und emittiert bei Erreichen:
   - Lifecycle: `model_fallback_retry_limit_reached`
- Fallback-Retry-Event enthält zusätzlich Attempt-Metadaten (`attempt`, `max_attempts`).
- Unit-Test ergänzt: `test_pipeline_runner_enforces_retry_attempt_limit`.

### U11: P2-Teilstufe 2 — reason-klassifizierte Recovery-Branches
- `PipelineRunner` klassifiziert zusätzlich:
   - `context_overflow`
   - `compaction_failure`
- Neuer Lifecycle-Event: `model_recovery_branch_selected` mit Branch-Auswahl, z. B.:
   - `fail_fast_context_overflow`
   - `fail_fast_compaction_failure`
   - `retry_with_fallback`
   - `fail_fast_non_retryable`
- Beide neuen Gründe sind aktuell fail-fast (nicht retrybar) und werden transparent telemetriert.
- Unit-Tests ergänzt:
   - `test_pipeline_runner_classifies_context_overflow_as_non_retryable`
   - `test_pipeline_runner_classifies_compaction_failure_as_non_retryable`

### U12: P2-Teilstufe 3 — kontrollierte Recovery-Aktion je Branch
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_CONTEXT_OVERFLOW_FALLBACK_RETRY_ENABLED` (default: `false`)
   - `PIPELINE_RUNNER_CONTEXT_OVERFLOW_FALLBACK_RETRY_MAX_ATTEMPTS` (default: `1`)
- Für `context_overflow` kann optional ein strikt begrenzter Fallback-Retry aktiviert werden (guarded retry).
- Neue Lifecycle-Transparenz:
   - `model_recovery_branch_selected` enthält Overflow-Retry-Metadaten (`overflow_retry_applied`, attempts/max)
   - `model_recovery_action` beschreibt die konkrete Aktion (`retry_fallback` vs `fail_fast`)
- Unit-Test ergänzt:
   - `test_pipeline_runner_guarded_context_overflow_retry_with_fallback`

### U13: P2-Teilstufe 4 — vorbereiteter `compaction_failure`-Recovery-Hook
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_COMPACTION_FAILURE_RECOVERY_ENABLED` (default: `false`)
   - `PIPELINE_RUNNER_COMPACTION_FAILURE_RECOVERY_MAX_ATTEMPTS` (default: `1`)
- Für `compaction_failure` existiert jetzt ein optionaler, strikt begrenzter Recovery-Hook, der bei Aktivierung kontrolliert Fallback-Retry erlaubt.
- Lifecycle-Telemetrie erweitert:
   - `model_recovery_branch_selected` enthält `compaction_recovery_applied`, attempts/max
   - `model_recovery_action` enthält die konkrete Aktion inklusive `compaction_recovery_applied`
- Unit-Test ergänzt:
   - `test_pipeline_runner_guarded_compaction_failure_recovery_with_fallback`

### U14: P3 — Warning-Bucket-Progression für lange Runs
- Neue Setting: `TOOL_LOOP_WARNING_BUCKET_SIZE` (`settings.tool_loop_warning_bucket_size`, default `10`).
- `ToolCallGatekeeper` emittiert Loop-Warnungen jetzt bucket-basiert statt strikt one-shot:
   - erste Warnung bei `warn_threshold`
   - kontrollierte Rewarnung bei fortlaufenden Hits gemäß Bucket-Größe
- Erweiterte Telemetrie in Warn-Events (`tool_loop_warn`, `tool_loop_ping_pong_warn`):
   - `warning_bucket_index`
   - `warning_bucket_size`
- `tool_audit_summary` enthält `loop_warning_bucket_size` für Laufdiagnostik.
- Neue Unit-Tests:
   - `test_execute_tools_generic_repeat_warning_bucket_progression`
   - `test_execute_tools_ping_pong_warning_bucket_progression`

### U15: P4 — Subrun Registry Hardening (Orphan-Reconcile + Lifecycle-Error-Grace)
- `SubrunLane` führt beim Registry-Restore jetzt ein explizites Orphan-Reconcile für nicht-terminale Altzustände (`accepted`/`running`) durch.
- Reconcile-Verhalten:
   - Status wird auf `failed` gesetzt
   - Details enthalten `reconciled=true`, `reconcile_reason=orphaned_after_restore`, `reconciled_at`
   - StateStore wird mit Fehlerstatus aktualisiert
   - Audit-Event `subrun_orphan_reconciled` wird persistiert
- Lifecycle-Forwarding ist jetzt fehlertolerant:
   - Fehler beim Weiterleiten von Subrun-`lifecycle`-Events brechen den Subrun nicht mehr hart ab
   - Stattdessen persistiert der Lane-Pfad ein Deferred-Event `lifecycle_delivery_deferred`
   - Nicht-Lifecycle-Events bleiben unverändert streng
- Neue Unit-Tests:
   - `test_subrun_lane_restore_reconciles_orphaned_running_run`
   - `test_subrun_lane_lifecycle_delivery_error_is_deferred`

### U16: P4-Finetuning — konfigurierbare Betriebs-Defaults
- Neue Subrun-Settings:
   - `SUBRUN_RESTORE_ORPHAN_RECONCILE_ENABLED` (default: `true`)
   - `SUBRUN_RESTORE_ORPHAN_GRACE_SECONDS` (default: `0`)
   - `SUBRUN_LIFECYCLE_DELIVERY_ERROR_GRACE_ENABLED` (default: `true`)
- `SubrunLane` nutzt diese Settings jetzt explizit zur Laufzeitsteuerung:
   - Orphan-Reconcile kann deaktiviert oder per Grace-Fenster verzögert werden
   - Lifecycle-Error-Grace kann für stricte Umgebungen deaktiviert werden
- Neue Unit-Tests:
   - `test_subrun_lane_restore_respects_orphan_grace_window`
   - `test_subrun_lane_lifecycle_delivery_error_grace_can_be_disabled`

### U17: P2-Follow-up — expliziter Truncation-Recovery-Branch
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_TRUNCATION_RECOVERY_ENABLED` (default: `false`)
   - `PIPELINE_RUNNER_TRUNCATION_RECOVERY_MAX_ATTEMPTS` (default: `1`)
- `PipelineRunner` klassifiziert jetzt zusätzlich `truncation_required` (z. B. `truncated`, `max tokens`, `token limit`).
- Neuer Recovery-Branch:
   - default: `fail_fast_truncation_required`
   - optional: `guarded_truncation_recovery` mit strikt begrenztem Fallback-Retry
- Lifecycle-Telemetrie erweitert:
   - `model_recovery_branch_selected` enthält `truncation_recovery_applied`, attempts/max
   - `model_recovery_action` enthält `truncation_recovery_applied`
- Neue Unit-Tests:
   - `test_pipeline_runner_classifies_truncation_required_as_non_retryable`
   - `test_pipeline_runner_guarded_truncation_recovery_with_fallback`

### U18: P2-Follow-up — deterministischer Prompt-Compaction-Hook im Recovery-Loop
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_PROMPT_COMPACTION_ENABLED` (default: `false`)
   - `PIPELINE_RUNNER_PROMPT_COMPACTION_MAX_ATTEMPTS` (default: `1`)
   - `PIPELINE_RUNNER_PROMPT_COMPACTION_RATIO` (default: `0.7`)
   - `PIPELINE_RUNNER_PROMPT_COMPACTION_MIN_CHARS` (default: `200`)
- Bei `context_overflow` kann der Runner jetzt optional den Prompt vor dem nächsten Fallback-Attempt kontrolliert verkürzen.
- Recovery-Branch:
   - `guarded_prompt_compaction_recovery` (attempt-limitiert, telemetriert)
- Lifecycle-Telemetrie erweitert um Compaction-Metadaten:
   - `prompt_compaction_applied`, attempts/max
   - `prompt_compaction_previous_chars`, `prompt_compaction_new_chars`
- Neue Unit-Tests:
   - `test_pipeline_runner_guarded_prompt_compaction_recovery_with_fallback`

### U19: P2-Follow-up — Result-/Payload-Truncation-Transformations-Hook
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_PAYLOAD_TRUNCATION_ENABLED` (default: `false`)
   - `PIPELINE_RUNNER_PAYLOAD_TRUNCATION_MAX_ATTEMPTS` (default: `1`)
   - `PIPELINE_RUNNER_PAYLOAD_TRUNCATION_TARGET_CHARS` (default: `1200`)
   - `PIPELINE_RUNNER_PAYLOAD_TRUNCATION_MIN_CHARS` (default: `120`)
- Für `truncation_required` kann der Runner jetzt optional den Retry-Payload vor dem Fallback-Attempt deterministisch kürzen.
- Neuer Recovery-Branch:
   - `guarded_payload_truncation_recovery`
- Lifecycle-Telemetrie erweitert um Truncation-Transformationsmetadaten:
   - `payload_truncation_applied`, attempts/max
   - `payload_truncation_previous_chars`, `payload_truncation_new_chars`
- Neue Unit-Tests:
   - `test_pipeline_runner_guarded_payload_truncation_recovery_with_fallback`

### U20: P2-Follow-up — Adaptive Recovery-Eskalation (Transformation-first)
- `PipelineRunner` priorisiert pro Fehlergrund jetzt deterministisch genau einen Recovery-Schritt pro Attempt:
   - `context_overflow`: zuerst `guarded_prompt_compaction_recovery`, danach optional `guarded_context_overflow_fallback_retry`
   - `truncation_required`: zuerst `guarded_payload_truncation_recovery`, danach optional `guarded_truncation_recovery`
- Dadurch werden konkurrierende Recovery-Flags pro Attempt vermieden und Branches klar sequenziert.
- Neue Telemetrie:
   - `recovery_strategy` in `model_recovery_branch_selected` und `model_recovery_action`
- Neue Unit-Tests:
   - `test_pipeline_runner_prioritizes_prompt_compaction_over_overflow_fallback_retry`
   - `test_pipeline_runner_prioritizes_payload_truncation_over_truncation_retry`

### U21: P2-Follow-up — Runtime-/Profil-abhängige Recovery-Prioritäten
- Neue Runner-Settings für profilabhängige Priorisierung:
   - `PIPELINE_RUNNER_CONTEXT_OVERFLOW_PRIORITY_LOCAL`
   - `PIPELINE_RUNNER_CONTEXT_OVERFLOW_PRIORITY_API`
   - `PIPELINE_RUNNER_TRUNCATION_PRIORITY_LOCAL`
   - `PIPELINE_RUNNER_TRUNCATION_PRIORITY_API`
- `PipelineRunner` wählt die Recovery-Reihenfolge jetzt runtime-basiert (`local` vs `api`) und normalisiert fehlerhafte/duplizierte Prioritätskonfigurationen robust.
- Ergebnis: adaptive Heuristik ohne Verlust der deterministischen „ein Schritt pro Attempt“-Regel.
- Neue Unit-Tests:
   - `test_pipeline_runner_api_prefers_overflow_fallback_retry_over_prompt_compaction`
   - `test_pipeline_runner_api_prefers_truncation_fallback_retry_over_payload_truncation`

### U22: P2-Follow-up — Verlaufssensitive Prioritätsumschaltung (Reason-Streak)
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_RECOVERY_PRIORITY_FLIP_ENABLED` (default: `true`)
   - `PIPELINE_RUNNER_RECOVERY_PRIORITY_FLIP_THRESHOLD` (default: `2`)
- Bei wiederholtem identischem Fehlergrund kann die Recovery-Priorität automatisch umgeschaltet werden (rotierende Reihenfolge), um festgefahrene Muster schneller zu durchbrechen.
- Zusätzliche Telemetrie in Recovery-Events:
   - `reason_streak`
   - `recovery_priority_overridden`
- Neue Unit-Tests:
   - `test_pipeline_runner_flips_context_overflow_priority_on_reason_streak`
   - `test_pipeline_runner_flips_truncation_priority_on_reason_streak`

### U23: P2-Follow-up — Signalbasierte Priorisierung aus Routing-Profil
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_SIGNAL_PRIORITY_ENABLED` (default: `true`)
   - `PIPELINE_RUNNER_SIGNAL_LOW_HEALTH_THRESHOLD` (default: `0.55`)
   - `PIPELINE_RUNNER_SIGNAL_HIGH_LATENCY_MS` (default: `2500`)
- `PipelineRunner` wertet jetzt zusätzlich Routing-Signale (`health_score`, `expected_latency_ms`) aus und kann dadurch Recovery-Prioritäten gezielt umordnen.
- Signal-Heuristik:
   - low health → fallback-first
   - high latency → transform-first
- Erweiterte Lifecycle-Telemetrie:
   - `signal_priority_applied`
   - `signal_priority_reason` (`low_health_prefer_fallback` / `high_latency_prefer_transform`)
- Neue Unit-Tests:
   - `test_pipeline_runner_signal_low_health_prefers_fallback_for_context_overflow`
   - `test_pipeline_runner_signal_high_latency_prefers_transform_for_truncation`

### U24: P2-Follow-up — Mehrdimensionale Signalgewichtung + branch-spezifisches Feedback
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_SIGNAL_HIGH_COST_THRESHOLD` (default: `0.75`)
   - `PIPELINE_RUNNER_STRATEGY_FEEDBACK_ENABLED` (default: `true`)
- Signal-Heuristik erweitert um `cost_score`:
   - high cost → transform-first (`high_cost_prefer_transform`)
- Zusätzliche branch-spezifische Verlaufskomponente im selben Run:
   - zuletzt fehlgeschlagene Recovery-Strategie pro Fehlergrund wird für den nächsten gleichartigen Fehlergrund nach hinten priorisiert (demotion), um festgefahrene Muster schneller zu durchbrechen.
- Erweiterte Lifecycle-Telemetrie:
   - `strategy_feedback_applied`
   - `strategy_feedback_reason` (z. B. `demote:prompt_compaction`)
- Neue Unit-Tests:
   - `test_pipeline_runner_signal_high_cost_prefers_transform_for_context_overflow`
   - `test_pipeline_runner_strategy_feedback_demotes_last_failed_strategy`

### U25: P2-Follow-up — Persistente Recovery-Metriken über mehrere Runs
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_PERSISTENT_PRIORITY_ENABLED` (default: `true`)
   - `PIPELINE_RUNNER_PERSISTENT_PRIORITY_MIN_SAMPLES` (default: `3`)
- `PipelineRunner` persistiert jetzt branch-/reason-/modell-spezifische Recovery-Outcomes in
  `state_store/pipeline_recovery_metrics.json` und nutzt diese beim nächsten Run zur Prioritätsauswahl.
- Persistente Heuristik:
   - Strategien mit ausreichend Samples werden nach historischer Erfolgsrate priorisiert.
   - Bei fehlender Stichprobe bleibt die bestehende Signal-/Feedback-/Flip-Logik unverändert.
- Erweiterte Lifecycle-Telemetrie:
   - `persistent_priority_applied`
   - `persistent_priority_reason` (z. B. `metrics_prefer:overflow_fallback_retry`)
- Neue Unit-Tests:
   - `test_pipeline_runner_persistent_metrics_prefer_fallback_for_context_overflow`
   - `test_pipeline_runner_persistent_metrics_prefer_transform_for_truncation`

### U26: P2-Follow-up — Time-Decay + Sliding-Window für persistente Priorisierung
- Neue Runner-Settings:
   - `PIPELINE_RUNNER_PERSISTENT_PRIORITY_DECAY_ENABLED` (default: `true`)
   - `PIPELINE_RUNNER_PERSISTENT_PRIORITY_DECAY_HALF_LIFE_SECONDS` (default: `86400`)
   - `PIPELINE_RUNNER_PERSISTENT_PRIORITY_WINDOW_SIZE` (default: `50`)
   - `PIPELINE_RUNNER_PERSISTENT_PRIORITY_WINDOW_MAX_AGE_SECONDS` (default: `604800`)
- `PipelineRunner` führt persistente Recovery-Metriken jetzt als Event-History (`events[{outcome, ts}]`) und berechnet Priorität auf einem geprunten Sliding-Window.
- Decay wird auf Event-Gewichtung angewandt; dadurch zählen neuere Outcomes stärker als ältere Samples (Drift-robuster).
- Backward-Kompatibilität bleibt erhalten:
   - Bestehende Counter (`success`/`failure`) werden weiterhin gelesen.
   - Wenn keine Event-History vorhanden ist, greift Counter-Fallback (inkl. optionaler Last-Update-Decay).
- Neue Unit-Tests:
   - `test_pipeline_runner_persistent_metrics_decay_prefers_recent_signal`
   - `test_pipeline_runner_persistent_metrics_window_prefers_recent_trend`

### U27: G3 — Aggregierte Recovery-Observability mit kompakten Lifecycle-Summaries
- `PipelineRunner` emittiert jetzt bei Recovery-Fällen zusätzlich ein kompaktes Aggregat-Event:
   - Lifecycle-Stage: `model_recovery_summary`
   - Enthält u. a. `failures_total`, `reason_counts`, `branch_counts`, `strategy_counts`,
     Summen für Signal-/Feedback-/Persistent-Priority-Anwendungen sowie Transform-/Retry-Anwendungszähler.
- Summary wird sowohl auf Success- als auch Failure-Pfaden emittiert (wenn mindestens ein Recovery-Failure im Run auftrat).
- Ziel: bessere Run-weite Recovery-Diagnostik ohne Event-Flut pro Einzelentscheidung.
- Neue Unit-Tests:
   - `test_pipeline_runner_emits_recovery_summary_on_success`
   - `test_pipeline_runner_emits_recovery_summary_on_fail_fast`

---

## 5) Offene Gaps zur Openclaw-Parity

### G1: Persistente Heuristik ist jetzt drift-robust, aber noch ohne Auto-Tuning
Decay/Windowing sind implementiert; offen bleibt eine adaptive Kalibrierung von Half-Life/Window je Runtime/Modellklasse (aktuell statische Defaults).

### G2: Subrun-Reconcile-Policy ist jetzt konfigurierbar, aber noch nicht heuristisch
Aktuell erfolgt Reconcile status-/zeitbasiert; tiefergehende Heuristiken (z. B. getrennte Policies je Modus/Agent/Depth) sind noch offen.

### G3: Recovery-Observability ist für Runner-Recovery aggregiert, Subrun-/Delivery-Aggregate noch offen
`model_recovery_summary` deckt Runner-Recovery ab; offen bleibt eine analoge Aggregation für Subrun-Delivery-/Deferred-Patterns.

---

## 6) Umsetzungsplan (priorisiert)

### Phase P1 — Pre-Tool Gatekeeper extrahieren
**Ziel:** Einheitlicher Kontrollpunkt für Toolcalls.

Arbeitspakete:
1. Neues Modul in `backend/app/` für `before_tool_call`/`after_tool_call` Orchestrierung.
2. Loop-Detection, Policy-Checks, Approval-Hook, Param-Normalisierung dort bündeln.
3. `HeadAgent._execute_tools` auf diesen Pfad umstellen.
4. Lifecycle-Events unverändert kompatibel halten.

Akzeptanzkriterien:
- Keine API-/WS-Contract-Breaks.
- Bestehende Tool-Selection-Tests bleiben grün.
- Neue unit tests für Gatekeeper-Entscheidungen.

### Phase P2 — Run-Recovery State Machine im Runner
**Ziel:** Robustes Fehlermanagement unter Overflow/Failover.

Arbeitspakete:
1. Retry-Cap + Iteration-Guard in `pipeline_runner.py`.
2. Context-overflow Klassifikation zentralisieren.
3. Recovery-Kette definieren: retry -> compaction -> truncation -> fail-fast.
4. Telemetrie: reason-coded Lifecycle-Events je Branch.

Akzeptanzkriterien:
- Deterministische Abbruchgrenzen.
- Reproduzierbare Events für alle Recovery-Branches.
- Keine Endlosschleifen.

### Phase P3 — Warning Buckets statt reinem One-Shot
**Ziel:** Sinnvolle Rewarnung bei langen Runs ohne Spam.

Arbeitspakete:
1. Bucket-Strategie (z. B. alle 10 Treffer) pro warning_key.
2. Begrenzter In-Memory Cache pro Run.
3. Tests für bucket progression und dedupe.

Akzeptanzkriterien:
- Warn-Events steigen kontrolliert mit persistierender Schleife.
- Kein Event-Spam.

### Phase P4 — Subrun Registry Hardening
**Ziel:** Höhere Robustheit bei Neustarts/Fehlern.

Arbeitspakete:
1. Orphan-Reconcile beim Restore.
2. Deferred error grace bei transienten Fehler-Lifecycle-Events.
3. Bessere Retry/Backoff-Strategie für Announce-Flows.

Akzeptanzkriterien:
- Keine "hängenden" Subruns nach Restore.
- Stabiler Endzustand trotz transienter Fehler.

---

## 7) Teststrategie

Pro Phase:
1. Zuerst gezielte Unit-Tests der neuen Logik.
2. Danach betroffene Suite(s):
   - `tests/test_tool_selection_offline_eval.py`
   - `tests/test_backend_e2e.py`
   - `tests/test_subrun_lane.py`
3. Danach relevante Contract/E2E Regression.

Nicht-Ziel:
- Unrelated Fails außerhalb Scope mitfixen.

---

## 8) Fortschritts-Tracking

Status:
- [x] Openclaw Deep-Dive durchgeführt
- [x] Erste Parity-Schritte (Loop + Policy) umgesetzt
- [x] Warn-vs-Critical Ping-Pong eingeführt
- [x] Warn-Key Dedupe eingeführt
- [x] P1 Pre-Tool Gatekeeper
- [x] P2 Runner Recovery State Machine
- [x] P3 Warning Buckets
- [x] P4 Subrun Registry Hardening

Nächster konkreter Schritt:
- **Next**: Subrun-Observability-Aggregate ergänzen (insb. Deferred-Delivery-Rate und Restore-Reconcile-Kennzahlen) für einheitliche End-to-End-Summaries.

Checkpoint (P4 abgeschlossen):
- Subrun-Orphan-Reconcile beim Restore und deferred Lifecycle-Error-Grace implementiert.
- Betriebs-Finetuning für Reconcile/Grace ist jetzt per Settings steuerbar.
- Regressionen grün:
   - `tests/test_subrun_lane.py` + `tests/test_subrun_visibility_scope.py`: 13 passed
   - `tests/test_model_router.py`: 26 passed
   - `tests/test_tool_selection_offline_eval.py`: 39 passed
   - `tests/test_backend_e2e.py`: 29 passed
