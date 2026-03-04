# Reasoning-Lifecycle — Vollständiger Bug-Audit (2026-03-04)

## Scope

Auditiert wurden **alle** Schichten des Reasoning-Lifecycle — vom WebSocket-Einstieg über Orchestrierung, Agent-Pipeline (Plan → Tool Select → Execute → Synthesis), State-Management, Memory, Skills, LTM bis hin zu Recovery und Policy-Enforcement.

### Geprüfte Dateien

| Schicht | Dateien |
|---------|---------|
| Transport / Entry | `ws_handler.py`, `run_endpoints.py`, `subrun_endpoints.py` |
| Orchestrierung | `pipeline_runner.py`, `run_state_machine.py`, `fallback_state_machine.py`, `session_lane_manager.py`, `subrun_lane.py`, `recovery_strategy.py`, `events.py`, `step_executors.py` |
| Agent Core | `agent.py` (HeadAgent), `head_agent_adapter.py`, `planner_agent.py`, `synthesizer_agent.py`, `tool_selector_agent.py` |
| Tool Execution | `tool_execution_manager.py`, `tool_call_gatekeeper.py`, `action_parser.py`, `action_augmenter.py` |
| Policy | `policy_approval_service.py`, `tool_policy_service.py` |
| Memory & State | `memory.py`, `state_store.py`, `task_graph.py`, `context_reducer.py`, `app_state.py` |
| LTM | `long_term_memory.py` |
| Skills | `skills/service.py`, `skills/discovery.py` |
| Services | `reflection_service.py`, `verification_service.py`, `intent_detector.py`, `reply_shaper.py`, `tool_result_context_guard.py`, `agent_resolution.py`, `prompt_kernel_builder.py` |

---

## Ergebnisübersicht

| Schweregrad | Anzahl |
|-------------|--------|
| **CRITICAL** | 5 |
| **HIGH** | 18 |
| **MEDIUM** | 26 |
| **LOW** | 13 |
| **Gesamt** | **62** |

---

## CRITICAL (5)

### C-1: Retrieval-Kontext wird beim Skills-Preview-Inject überschrieben

**Datei:** `tool_execution_manager.py` L399–L425  
**Root Cause:** Nach erfolgreichem Retrieval wird `effective_memory_context` korrekt erweitert (L403). Beim Skills-Preview-Inject (L425) wird `effective_memory_context` jedoch auf Basis des **originalen** `memory_context` neu zusammengebaut — die Retrieval-Quellen gehen verloren.

```python
# L403: Retrieval korrekt anfügen
effective_memory_context = f"{effective_memory_context}\n\n{retrieval_prompt}"
# L425: Skills-Preview ÜBERSCHREIBT mit Original
effective_memory_context = f"{memory_context}\n\n{contracted_prompt}"  # BUG
```

**Impact:** Tool-Selektion arbeitet ohne Retrieval-Quellen → schlechtere Entscheidungen, Halluzinationsrisiko.

---

### C-2: `tool_result_persisted` wird vom `tool_`-Prefix-Check verdeckt (State Machine)

**Datei:** `run_state_machine.py` L49–L67  
**Root Cause:** `resolve_run_state_from_stage()` prüft `startswith("tool_")` **vor** dem expliziten Check für `"tool_result_persisted"`. Da `"tool_result_persisted"` mit `"tool_"` beginnt, wird es als `"tool_loop"` statt `"persisted"` klassifiziert.

```python
if normalized.startswith("tool_"):     # ← matched "tool_result_persisted"!
    return "tool_loop"                  # ← falsch

# Zeile 64-65: wird NIE erreicht
if normalized in {"tool_result_persisted", ...}:
    return "persisted"                  # ← korrekt, aber unerreichbar
```

**Impact:** Die gesamte Post-Execution-Phase wird als falscher State reflektiert. Runs durchlaufen den terminalen Zustand nie korrekt.

---

### C-3: `sanitize_session_history` löscht gültige Assistant-Nachrichten nach Tool-Ergebnissen

**Datei:** `memory.py` L87–L113  
**Root Cause:** Die Duplikaterkennung verfolgt `last_conversation_role`, setzt diesen aber bei `tool:`-Nachrichten nicht zurück. Die Sequenz `assistant → tool:result → assistant` wird daher als `assistant → tool:result` gekürzt — die zweite `assistant`-Nachricht wird als Duplikat gelöscht.

```python
if item.role in ("user", "assistant"):
    if item.role == last_conversation_role:  # "assistant" == "assistant" → BUG
        continue                              # gültige Nachricht wird gelöscht
    last_conversation_role = item.role
```

**Impact:** Multi-Tool-Calling-Konversationen werden zerstört. Der Agent verliert Kontext bei jeder Memory-Sanitization.

---

### C-4: `LazyRuntimeRegistry` Double-Checked Locking gibt uninitialisierte Komponenten frei

**Datei:** `app_state.py` L72–L85  
**Root Cause:** Die Zuweisung `self._components = self._builder()` erfolgt **vor** `self._initializer(self._components)`. Thread B kann die ungeschützte Prüfung passieren und uninitialisierte Komponenten erhalten.

```python
def get_components(self) -> RuntimeComponents:
    if self._components is not None:       # Thread B liest True...
        return self._components             # ...und bekommt uninitialisierten State

    with self._lock:
        if self._components is None:
            self._components = self._builder()     # Referenz gesetzt
            self._initializer(self._components)    # ...DANACH erst initialisiert
```

**Impact:** Race Condition bei Startup — Agents/Orchestrator greifen auf teilweise initialisierte RuntimeComponents zu.

---

### C-5: Race Condition in `PolicyApprovalService.create()` — doppelte Approval-Prompts

**Datei:** `policy_approval_service.py` L42–L87  
**Root Cause:** Idempotenzprüfung und Insert verwenden zwei getrennte Lock-Akquisitionen. Zwischen Check und Insert kann ein zweiter Request denselben Approval-Eintrag erstellen.

**Impact:** Doppelte Approval-Prompts an den User, inkonsistenter State.

---

## HIGH (18)

### H-1: Paralleler Read-Only-Pfad umgeht Budget-, Loop- und Steer-Gates komplett

**Datei:** `tool_execution_manager.py` L1023–L1071  
**Root Cause:** Read-only Actions werden parallel via `asyncio.gather` ausgeführt — ohne vorherige Budget-Prüfung (`call_cap`, `time_cap`), ohne Loop-Gatekeeper (`before_tool_call`/`after_tool_success`), und ohne `should_steer_interrupt()`-Check nach dem Batch.

**Impact:** Guardrails für Budget, Loop-Detection und User-Steering sind im parallelen Pfad wirkungslos. Beliebig viele read-only Calls möglich.

---

### H-2: `memory_context` statt `effective_memory_context` an Action-Pipeline übergeben

**Datei:** `tool_execution_manager.py` L531  
**Root Cause:** `execute()` übergibt den **originalen** `memory_context` statt den angereicherten `effective_memory_context` an `apply_action_pipeline`. Action-Augmentation arbeitet ohne Retrieval-Sources und Skills-Preview.

**Impact:** Tool-Augmentation basiert auf unvollständigem Kontext.

---

### H-3: Web-Research-Frühausstieg setzt `status` nie auf "completed"

**Datei:** `agent.py` L988–L1027  
**Root Cause:** Der `web_research_sources_unavailable` Early-Return-Pfad setzt `status` nicht. Da `status` initial `"failed"` ist, wird `agent_end`-Hook mit `status="failed"` aufgerufen und Session-Distillation übersprungen.

**Impact:** Korrekte Runs werden als fehlgeschlagen gemeldet.

---

### H-4: `configure_runtime` aktualisiert `tool_selector_agent` und `_tool_execution_manager` nicht

**Datei:** `agent.py` L354–L368  
**Root Cause:** Bei Runtime-Wechsel (Model/API) werden `planner_agent` und `synthesizer_agent` aktualisiert, aber `tool_selector_agent` und `_tool_execution_manager` nicht.

**Impact:** Tool Selection kann nach Runtime-Switch mit altem Client/Konfiguration arbeiten.

---

### H-5: Context-Reset vor Hook-Aufruf im `finally`-Block

**Datei:** `agent.py` L1375–L1402  
**Root Cause:** Im `finally`-Block werden die ContextVar-Tokens (request_id, session_id, send_event) **vor** dem `_invoke_hooks("agent_end")` zurückgesetzt. Hooks die auf ContextVars zugreifen, bekommen `None`.

**Impact:** `agent_end`-Hooks mit ContextVar-Zugriff erhalten ungültige Werte.

---

### H-6: Shared Mutable State bei concurrenten `run()`-Aufrufen

**Datei:** `agent.py` L443–L1402  
**Root Cause:** `self.memory`, `self.tools`, `self._long_term_memory`, `self.tool_registry` sind shared mutable state ohne Locks. Concurrente `run()` für verschiedene Sessions können sich gegenseitig stören — z.B. bei `_ensure_mcp_tools_registered` oder `_refresh_long_term_memory_store`.

**Impact:** Race Conditions bei gleichzeitigen Agent-Runs.

---

### H-7: Content-basierte Recovery-Strategien fehlerhaft hinter `has_fallback` gegated

**Datei:** `recovery_strategy.py` L133–L194  
**Root Cause:** `context_overflow`, `compaction_failure` und `truncation_required` sind alle hinter `has_fallback` gegated. Content-basierte Strategien (Prompt-Compaction, Payload-Truncation) benötigen aber kein Fallback-Model — sie modifizieren die Nachricht, nicht das Modell.

**Impact:** Auf dem letzten Model ist keine Content-basierte Recovery möglich. Runs scheitern unnötig.

---

### H-8: Recovery-Strategien retryten immer das nächste Model statt desselben

**Datei:** `fallback_state_machine.py` L556–L558  
**Root Cause:** Im `HANDLE_FAILURE`-State wird `_current_model_index` immer inkrementiert, auch nach Content-basierter Recovery (Prompt-Compaction). Die verkleinerte Nachricht wird ans nächste Model geschickt statt ans aktuelle.

**Impact:** Prompt-Compaction ist sinnlos, da sie nicht auf dem gleichen Model retryt wird.

---

### H-9: `wait_for_completion` cancelt den Subrun-Task bei Timeout

**Datei:** `subrun_lane.py` L261–L270  
**Root Cause:** `asyncio.wait_for` **cancelt** den übergebenen Task bei Timeout. Ein Polling-Aufruf mit kurzem Timeout zerstört den laufenden Subrun.

**Impact:** Jeder Versuch, den Status eines Subruns mit Timeout abzufragen, killt den Subrun.

---

### H-10: Pipeline-Steps bleiben im Zombie-State bei Fehler

**Datei:** `pipeline_runner.py` L106–L226  
**Root Cause:** Wenn `_run_with_fallback` eine Exception wirft, werden Pipeline-Steps nie auf `"failed"` gesetzt. Sie bleiben in `"pending"` oder `"active"` — es gibt keinen `try/except/finally`-Block.

**Impact:** Fehlgeschlagene Runs zeigen falsche Task-Stati im UI/API.

---

### H-11: Falsche Agent-Attribution bei Queue-Worker-Lifecycle-Events

**Datei:** `ws_handler.py` L350–L383  
**Root Cause:** `execute_user_message_job()` resolved den Agenten, setzt aber `active_event_agent_name` nicht. Lifecycle-Events nutzen den alten/globalen Agentnamen.

**Impact:** Telemetrie/Tracing zeigt falschen ausführenden Agenten.

---

### H-12: `StateStore.init_run` fehlt Lock-Akquisition — Data Race

**Datei:** `state_store.py` L37–L62  
**Root Cause:** `init_run` ruft `_write_run()` ohne `self._lock` auf, während alle anderen mutierten Methoden den Lock korrekt nutzen.

**Impact:** Gleichzeitige Run-Initialisierungen können sich überschreiben.

---

### H-13: `set_task_status` vernichtet `created_at`-Timestamps aller bestehenden Tasks

**Datei:** `state_store.py` L98–L118, `task_graph.py` L25–L30  
**Root Cause:** Bei jedem Status-Update wird ein leerer `TaskGraph` erstellt. Jeder `ensure_task()`-Aufruf erzeugt ein neues `TaskNode` mit aktuellem `created_at`. Bestehende Timestamps werden überschrieben.

**Impact:** Task-Timing-Daten für Auditing und Metriken sind unbrauchbar.

---

### H-14: Typo in Tool-Allow-Liste lässt still ALLE Tools zu (Security-Bypass)

**Datei:** `tool_selector_agent.py` L153–L168  
**Root Cause:** Wenn alle Einträge in `allow` unbekannte Tool-Namen sind, bleibt `known_allow` leer. Der Check `if known_allow:` ist `False`, und `allowed` wird nicht eingeschränkt.

**Impact:** Policy-Bypass — unbekannte/falsche Allow-Einträge erlauben vollen Tool-Zugriff.

---

### H-15: `EpisodicEntry.entry_id` Timestamp-basiert → Daten-Verlust

**Datei:** `long_term_memory.py` L29–L35  
**Root Cause:** `entry_id` nutzt `datetime.now().isoformat()` als Primary Key. `INSERT OR REPLACE` bei gleichem Timestamp überschreibt den vorherigen Eintrag.

**Impact:** Bei schnellen aufeinanderfolgenden Writes geht der erste Eintrag verloren.

---

### H-16: `allow_session` genehmigt pauschal ALLE Tools der Session

**Datei:** `policy_approval_service.py` L232–L235  
**Root Cause:** `allow_session` setzt ein Session-weites Flag, das alle Tools dieser Session genehmigt — nicht nur das angefragte Tool+Resource.

**Impact:** Übermäßige Genehmigungsreichweite, Policy-Scope-Verletzung.

---

### H-17: Circuit Breaker nutzt unbegrenzten monotonen Zähler

**Datei:** `tool_call_gatekeeper.py` L139–L143  
**Root Cause:** `repeat_signature_hits` wird nie zurückgesetzt und wächst unbegrenzt. Nach genügend (auch nicht aufeinanderfolgenden) Calls löst der Circuit Breaker fälschlicherweise aus.

**Impact:** Valide Tool-Calls werden nach langem Betrieb blockiert.

---

### H-18: Queue-Worker hat kein `ClientDisconnectedError`-Handling

**Datei:** `ws_handler.py` (Queue-Worker-Pfad)  
**Root Cause:** Wenn der Client disconnectet während ein queued Job läuft, wird die Exception nicht gefangen. Der Run verwaist im `active`-Status.

**Impact:** Hängende Runs bei Client-Disconnect.

---

## MEDIUM (26)

### M-1: `clarification_needed`-Pfad speichert Antwort nicht in Memory
**Datei:** `agent.py` L620–L631  
Rückfrage an User wird nicht per `memory.add()` gespeichert. Kontext bei nächster User-Nachricht unvollständig.

### M-2: Steer-Interrupted-Pfad schreibt Antwort nicht ins Memory
**Datei:** `agent.py` L935–L987  
`interrupted_message` wird gesendet aber nicht in Memory geschrieben.

### M-3: Off-by-one bei Regular-Replan-Budget
**Datei:** `agent.py` L1898–L1916  
Bei `max_replan_iterations=1` ist `regular_replan_budget_remaining` immer `False`.

### M-4: `_classify_tool_results_state` — schwache Regex für `[ok]`/`[error]`
**Datei:** `agent.py` L1879–L1891  
`\bok\b` matcht jedes alleinstehende "ok" (auch in "It's ok to proceed"). `" error:"` verpasst Fehler am Zeilenanfang.

### M-5: Error/Empty-Replans konsumieren fälschlich reguläres Replan-Budget
**Datei:** `agent.py` L718–L805  
`regular_replan_budget_remaining = iteration < max_replan_iterations - 1` basiert auf globalem `iteration`-Counter, der durch alle Replan-Typen inkrementiert wird.

### M-6: Keyword-Match zu breit bei `_resolve_synthesis_task_type`
**Datei:** `agent.py` L2193–L2217  
`"test"` matcht "testimony", `"code"` matcht "barcode", `"bug"` matcht "debug". Falsche Task-Typ-Zuweisungen lösen Implementation-Evidence-Gate bei Textfragen aus.

### M-7: `_build_root_cause_replan_prompt` — `user_message` ungekürzt
**Datei:** `agent.py` L1918–L1932  
`user_message` wird ohne Limit eingefügt, kann Token-Budget überschreiten.

### M-8: `_ensure_mcp_tools_registered` — teilinitialisierter `_mcp_bridge` bei Retry
**Datei:** `agent.py` L2358–L2382  
Bei Fehler wird `_mcp_initialized = False` gesetzt, aber `_mcp_bridge` nicht zurückgesetzt. Erneuter `initialize()`-Aufruf auf teilinitialisiertem Bridge.

### M-9: Doppel-Truncation nach Summary-Inject in Tool-Ergebnissen
**Datei:** `tool_execution_manager.py` L694–L710  
Summary vorangestellt → `max_chars` überschritten → erneute Truncation zerstört Chunk-Grenzen.

### M-10: web_fetch Retry aktualisiert Loop-Gatekeeper nicht
**Datei:** `tool_execution_manager.py` L1321–L1400  
`loop_gatekeeper.after_tool_success()` wird bei erfolgreicher Retry nicht aufgerufen.

### M-11: Forced `run_command` umgeht Validation
**Datei:** `tool_execution_manager.py` L934–L950  
Direkt erstellte `run_command`-Action durchläuft keine `validate_actions()`.

### M-12: `tool_call_count`-Inkonsistenz — parallele Fehler nicht gezählt
**Datei:** `tool_execution_manager.py` L1054–L1058  
Fehlgeschlagene parallele Calls erhöhen `tool_call_count` nicht → kein Budget-Verbrauch.

### M-13: `_execute_read_only_action` emittiert keine Lifecycle-Events
**Datei:** `tool_execution_manager.py` L1525–L1574  
Kein `tool_started`/`tool_completed`/`tool_failed` → unsichtbare Ausführung.

### M-14: Subrun `spawn` TOCTOU-Race auf `max_children_per_parent`
**Datei:** `subrun_lane.py` L141–L160  
Children-Count-Check und Registrierung sind nicht atomar.

### M-15: Task wird vor Registrierung erstellt → mögliche Zombie-Tasks
**Datei:** `subrun_lane.py` L200–L204  
`asyncio.create_task` startet den Task, der sich vor der Registrierung aus `_run_tasks` entfernen kann.

### M-16: Unbehandelte Exceptions in EXECUTE_ATTEMPT ohne Health-Tracker/Circuit-Breaker Cleanup
**Datei:** `fallback_state_machine.py` L215–L262  
Non-`LlmClientError` Exceptions hinterlassen Health-Tracker/Circuit-Breaker inkonsistent.

### M-17: `_cancel_task` ignoriert nicht-CancelledError Exceptions
**Datei:** `subrun_lane.py` L498–L507  
Wenn Task mit anderer Exception terminiert hat, wirft `await task` die originale Exception.

### M-18: `run_in_lane` verliert erfolgreiches Ergebnis bei `on_released`-Failure
**Datei:** `session_lane_manager.py` L98–L112  
Release-Exception überschreibt den Return-Wert eines erfolgreichen Runs.

### M-19: Unsupported-Type-Pfad hinterlässt aktive Runs ohne Terminal-Status
**Datei:** `ws_handler.py` L629–L663  
Run wird initialisiert und auf `active` gesetzt, bei `request_rejected_unsupported_type` nur geloggt — kein Terminal-State.

### M-20: `request_cancelled` setzt keinen Terminal-State im Run
**Datei:** `ws_handler.py` L243–L257  
Bei `PolicyApprovalCancelledError` wird Lifecycle-Event emittiert, aber kein `state_mark_failed_safe`/`state_mark_completed_safe` aufgerufen.

### M-21: Session-Overrides werden nur für Connection-ID gelöscht
**Datei:** `ws_handler.py` L1351  
Cleanup nutzt `connection_session_id`, Requests können aber abweichende `data.session_id` verwenden → Scope-Leak.

### M-22: `_normalize_session_id` verursacht Session-Kollisionen
**Datei:** `memory.py` L139–L141  
IDs aus Sonderzeichen werden alle auf `"session"` gemappt. `"user.1"` und `"user1"` kollidieren.

### M-23: `SqliteStateStore.init_run` umgeht Lock
**Datei:** `state_store.py` L219–L249  
Analog zum FileStore: `init_run` ruft `_upsert_run()` ohne Lock auf.

### M-24: Skills-Cache TTL-only Check umgeht mtime-Invalidierung
**Datei:** `skills/service.py` L100–L107  
`_try_read_snapshot_cache_ttl_only()` ignoriert mtime. Innerhalb des TTL-Fensters werden Änderungen nicht erkannt.

### M-25: `discover_skills` Root-SKILL.md Parse-Fehler blockiert gesamte Discovery
**Datei:** `skills/discovery.py` L14–L21  
Single Parse-Fehler → `return []` statt nur den fehlenden Skill zu überspringen.

### M-26: `is_shell_command` False Positive bei `/` und `\`
**Datei:** `intent_detector.py` L109–L112  
Jeder Text mit Schrägstrich wird als Shell-Befehl klassifiziert.

---

## LOW (13)

### L-1: `_run_tool_with_policy` Retry ohne Backoff
**Datei:** `agent.py` L2430–L2478

### L-2: `_plan_still_valid` ignoriert den `plan_text`-Parameter
**Datei:** `agent.py` L1870–L1873

### L-3: `_distill_session_knowledge` — ungeschützte JSON-Parsing vom LLM
**Datei:** `agent.py` L1406–L1497

### L-4: `_has_successful_tool_output` — Regex erwartet `\n` nach Tool-Header
**Datei:** `agent.py` L2239–L2243

### L-5: `_shape_final_response` wird vor `_requires_implementation_evidence`-Gate aufgerufen
**Datei:** `agent.py` L1228–L1266

### L-6: `error_elapsed_ms` stale im Retry-Fehlerpfad
**Datei:** `tool_execution_manager.py` L1290

### L-7: `_smart_truncate` kann Output > `max_chars` produzieren
**Datei:** `tool_execution_manager.py` L597–L604

### L-8: Lifecycle-Phase-Klassifikation unvollständig in `events.py`
**Datei:** `events.py` L68–L76  
Error-Stages wie `model_fallback_exhausted` erhalten `phase="progress"` statt `"error"`.

### L-9: `_TOOL_BLOCK_PATTERN` erfordert Trailing Newline
**Datei:** `tool_result_context_guard.py` L8

### L-10: `_extract_json_payload` greedy Regex versagt bei mehreren JSON-Objekten
**Datei:** `reflection_service.py` L119–L132

### L-11: Fehlender `Callable`-Import in Adapter-Dateien
**Datei:** `head_agent_adapter.py` L1–L8

### L-12: `ContextReducer` Budget-Allokation summiert zu 120%
**Datei:** `context_reducer.py` L29–L36

### L-13: `verify_tool_result` — naives Substring-Matching für `" error"` / `" ok"`
**Datei:** `verification_service.py` L122–L131

---

## Priorisierte Fix-Reihenfolge

### Phase 1 — Kritische Datenintegrität (sofort)
1. **C-1** — Retrieval-Kontext-Verlust → `effective_memory_context` statt `memory_context` in Skills-Inject
2. **C-2** — State Machine unerreichbare Zustände → `tool_result_persisted` vor `startswith("tool_")` prüfen
3. **C-3** — Memory Sanitization zerstört Tool-Conversations → `last_conversation_role` bei tool-Nachrichten zurücksetzen
4. **C-4** — Lazy Registry Race Condition → Initializer vor Referenz-Zuweisung abschließen
5. **C-5** — PolicyApproval Race → Atomare Lock-Akquisition

### Phase 2 — Guardrails & Lifecycle Consistency (hoch)
6. **H-1** — Parallel Read-Only Budget/Loop/Steer → Gates vor `asyncio.gather` prüfen
7. **H-7 + H-8** — Recovery Strategy → Content-basierte Strategien auf gleichem Model retryen
8. **H-9** — Subrun `wait_for_completion` → `asyncio.wait` statt `asyncio.wait_for`
9. **H-10** — Pipeline Steps Zombie-State → `finally`-Block für Task-Status-Cleanup
10. **H-3 + H-5** — Agent `status`-Setting → Fehlende `status = "completed"` in allen Return-Pfaden

### Phase 3 — State & Memory Correctness (hoch)
11. **H-12 + M-23** — StateStore Init-Lock → `self._lock` in `init_run` hinzufügen
12. **H-13** — TaskGraph Timestamp-Verlust → `created_at` aus bestehendem State übernehmen
13. **H-14** — Tool-Allow Security-Bypass → Leeres `known_allow` = leeres Set, nicht alle
14. **H-15** — LTM Entry-ID → UUID statt Timestamp
15. **M-22** — Session-ID-Kollision → Robustere Normalisierung

### Phase 4 — Ergänzende Korrekturen (mittel)
- M-1 bis M-26 systematisch nach Aufwand/Impact abarbeiten
- L-1 bis L-13 bei Gelegenheit
