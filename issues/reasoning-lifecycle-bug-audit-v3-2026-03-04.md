# Reasoning-Lifecycle — Vollständiger Bug-Audit v3 (2026-03-04)

## Scope

Vollständige Re-Auditierung aller Reasoning-Lifecycle-Schichten gegen den **aktuellen Code-Stand**. Jeder Bug aus dem v1-Audit wurde verifiziert (bestätigt / behoben). Zusätzlich wurden **15 neue Bugs** identifiziert.

---

## Statusübersicht vs. v1-Audit

| v1-ID | Status |
|-------|--------|
| C-1 | **BESTÄTIGT** (nuancierter: Prompt-Kernel-Truncation vernichtet Retrieval + Skills) |
| C-2 | **BESTÄTIGT** |
| C-3 | **BEHOBEN** |
| C-4 | **BESTÄTIGT** |
| C-5 | **BESTÄTIGT** |
| H-1 | **TEILWEISE BEHOBEN** (Budget/Steer Gates vorhanden, aber `after_tool_success` + Lifecycle fehlen) |
| H-2 | **BESTÄTIGT** |
| H-3 | **BEHOBEN** |
| H-4 | **BEHOBEN** |
| H-5 | **BEHOBEN** |
| H-6 | **BESTÄTIGT** |
| H-7 | **BEHOBEN** |
| H-8 | **BEHOBEN** |
| H-9 | **BESTÄTIGT** (升级 zu CRITICAL) |
| H-10 | **BESTÄTIGT** |
| H-11 | **BESTÄTIGT** |
| H-12 | **BESTÄTIGT** |
| H-13 | **BESTÄTIGT** |
| H-14 | **BESTÄTIGT** |
| H-15 | **BEHOBEN** (UUID statt Timestamp) |
| H-16 | **BESTÄTIGT** |
| H-17 | **BESTÄTIGT** |
| H-18 | **BESTÄTIGT** |
| M-1 | **BEHOBEN** |
| M-2 | **BESTÄTIGT** |
| M-3 | **BESTÄTIGT** |
| M-4 | **BESTÄTIGT** |
| M-5 | **BESTÄTIGT** |
| M-6 | **BESTÄTIGT** |
| M-7 | **BESTÄTIGT** |
| M-8 | **BESTÄTIGT** |
| M-9 | **BESTÄTIGT** |
| M-10 | **BESTÄTIGT** |
| M-11 | **BESTÄTIGT** (Dead Code wegen C-6) |
| M-12 | **BESTÄTIGT** |
| M-13 | **BESTÄTIGT** |
| M-14 | **BEHOBEN** |
| M-15 | **BESTÄTIGT** |
| M-16 | **BESTÄTIGT** |
| M-17 | **BESTÄTIGT** |
| M-18 | **BESTÄTIGT** |
| M-19 | **BEHOBEN** |
| M-20 | **BEHOBEN** |
| M-21 | **BEHOBEN** |
| M-22 | **BESTÄTIGT** |
| M-23 | **BESTÄTIGT** |
| M-24 | **BESTÄTIGT** |
| M-25 | **BESTÄTIGT** |
| M-26 | **BESTÄTIGT** |
| L-1…L-13 | Großteils bestätigt, Details unten |

---

## Ergebnisübersicht

| Schweregrad | Anzahl aktiv |
|-------------|-------------|
| **CRITICAL** | 4 |
| **HIGH** | 13 |
| **MEDIUM** | 22 |
| **LOW** | 14 |
| **Gesamt aktiv** | **53** |
| Behoben seit v1 | **12** |

---

## CRITICAL (4)

### C-1: Retrieval + Skills-Kontext wird durch Prompt-Kernel-Truncation vernichtet

**Datei:** `tool_execution_manager.py` ~L317–L340 + `prompt_kernel_builder.py` ~L46  
**Root Cause:** `effective_memory_context` wird korrekt mit Retrieval-Prompt und Skills-Preview angereichert. Aber der `PromptKernelBuilder` wendet im `minimal`-Mode ein per-Section-Limit von 1400 Zeichen an. Wenn der originale `memory_context` bereits >1400 Zeichen hat, werden Retrieval- und Skills-Kontext **komplett abgeschnitten**.

**Impact:** Tool-Selektion arbeitet in vielen Szenarien ohne Retrieval-Quellen und Skills-Preview → schlechtere Entscheidungen, Halluzinationsrisiko.

---

### C-2: `tool_result_persisted` wird vom `tool_`-Prefix-Check maskiert (State Machine)

**Datei:** `run_state_machine.py` L53–L72  
**Root Cause:** `resolve_run_state_from_stage()` prüft `startswith("tool_")` **vor** dem expliziten Check für `"tool_result_persisted"`. Da `"tool_result_persisted"` mit `"tool_"` beginnt, wird es als `"tool_loop"` statt `"persisted"` klassifiziert.

```python
if normalized.startswith("tool_"):     # ← matcht "tool_result_persisted"
    return "tool_loop"                  # ← falsch
# …
if normalized in {"tool_result_persisted", ...}:
    return "persisted"                  # ← unerreichbar
```

**Impact:** Post-Execution-Phase wird als falscher State reflektiert. Runs erreichen den terminalen Zustand nie korrekt.

---

### C-4: `LazyRuntimeRegistry` Double-Checked Locking — uninitialisierte Komponenten

**Datei:** `app_state.py` L87–L101  
**Root Cause:** `self._components = self._builder()` vor `self._initializer(self._components)`. Thread B sieht `self._components is not None` außerhalb des Locks und bekommt uninitialisierten State. Zusätzlich: Wenn `_initializer` fehlschlägt, bleibt `_components` gesetzt → alle nachfolgenden Aufrufe geben das nicht-initialisierte Objekt zurück.

**Impact:** Race Condition bei Startup. Agents/Orchestrator greifen auf teilweise initialisierte RuntimeComponents zu.

---

### C-5: Race Condition in `PolicyApprovalService.create()` — doppelte Approval-Prompts

**Datei:** `policy_approval_service.py` L47–L82  
**Root Cause:** Idempotenzprüfung und Insert verwenden zwei getrennte Lock-Akquisitionen mit Gap dazwischen.

**Impact:** Doppelte Approval-Prompts an den User, inkonsistenter State.

---

## HIGH (13)

### H-1 (residual): Paralleler Read-Only-Pfad — `after_tool_success` + Lifecycle nicht aufgerufen

**Datei:** `tool_execution_manager.py` ~L1028–L1145  
Budget- und Steer-Gates sind jetzt vorhanden. Aber: `loop_gatekeeper.after_tool_success()` wird nie für parallele Results aufgerufen → Poll-No-Progress-Detector ist blind. Keine Lifecycle-Events emittiert.

---

### H-2: `memory_context` statt `effective_memory_context` an Action-Pipeline

**Datei:** `tool_execution_manager.py` ~L534  
`apply_action_pipeline` bekommt den originalen `memory_context` ohne Retrieval + Skills.

---

### H-6: Shared Mutable State bei concurrenten `run()`-Aufrufen

**Datei:** `agent.py`, gesamte Klasse `HeadAgent`  
`self.client`, `self.tool_registry`, `self._mcp_initialized` sind shared mutable ohne Locks.

---

### H-9: `wait_for_completion` cancelt Subrun-Task bei Timeout → CRITICAL

**Datei:** `subrun_lane.py` ~L235–L242  
`asyncio.wait_for()` **cancelt** den übergebenen Task. Ein Polling-Aufruf mit kurzem Timeout zerstört den laufenden Subrun.

---

### H-10: Pipeline-Steps bleiben im Zombie-State bei Fehler

**Datei:** `pipeline_runner.py` ~L109–L161  
Kein `try/finally`-Block setzt Steps auf `"failed"` bei Exception in `_run_with_fallback`.

---

### H-11: Falsche Agent-Attribution bei Queue-Worker-Lifecycle-Events

**Datei:** `ws_handler.py` ~L540–L590  
`active_agent_name_cv` wird erst im Job gesetzt; Queue-Events nutzen den Default-Agenten.

---

### H-12 / M-23: `StateStore.init_run` fehlt Lock-Akquisition — Data Race

**Datei:** `state_store.py` L37–L62 (File) + L316–L351 (SQLite)  
`init_run` ruft `_write_run()`/`_upsert_run()` ohne Lock auf, alle anderen Mutationen nutzen Lock.

---

### H-13: `set_task_status` zerstört `created_at`-Timestamps aller Tasks

**Datei:** `state_store.py` L101–L121 + `task_graph.py` L31–L38  
Jedes Status-Update erstellt frischen `TaskNode` mit aktuellem `created_at`; Bestehende Timestamps überschrieben.

---

### H-14: Typo in Tool-Allow-Liste erlaubt still ALLE Tools (Security-Bypass)

**Datei:** `tool_selector_agent.py` ~L169–L179  
Wenn alle Allow-Einträge unbekannt sind, bleibt `known_allow` leer → `if known_allow:` ist False → keine Einschränkung.

---

### H-16: `allow_session` genehmigt pauschal ALLE Tools der Session

**Datei:** `policy_approval_service.py` ~L196–L199  
`_session_allow_all.add(session_id)` gibt blanket Approval für alle Tools, nicht nur das anfragte.

---

### H-17: Circuit Breaker `_circuits` Dict wächst unbegrenzt

**Datei:** `circuit_breaker.py` ~L73–L77  
Kein Eviction-Mechanismus für Model-spezifische Circuit-Einträge.

---

### H-18: Queue-Worker ohne `ClientDisconnectedError`-Handling

**Datei:** `ws_handler.py` (Queue-Worker)  
Client-Disconnect im laufenden Job → verwaiste Runs im `active`-Status + queued Requests gehen stillschweigend verloren.

---

### NEW H-19: `_normalize_tool_name` in HeadAgent lowercase-Fehler

**Datei:** `agent.py` ~L2391–L2398  
Wenn LLM `"Read_File"` zurückgibt: `lowered = "read_file"` ist kein Alias → Return des originalen `"Read_File"` (Groß-/Kleinschreibung) → Tool wird als nicht erlaubt abgelehnt.

```python
def _normalize_tool_name(self, tool_name: str) -> str:
    normalized = tool_name.strip()
    lowered = normalized.lower()
    if lowered in TOOL_NAME_ALIASES:
        return TOOL_NAME_ALIASES[lowered]
    return normalized  # ← BUG: "Read_File" statt "read_file"
```

**Fix:** `return lowered` statt `return normalized`.

---

### NEW H-20: Subrun `_run` sendet Post-Completion-Events ohne try/except → Announce-Verlust

**Datei:** `subrun_lane.py` ~L590–L665  
Nach dem try/except für Run-Fehler stehen `send_event()`, `_emit_announce_with_retry()`, `_run_tasks.pop()` und completion_callback **ungeschützt**. Wenn `send_event()` eine `ClientDisconnectedError` wirft: kein Announce, Zombie-Task, kein Callback.

---

### NEW H-21: `confidence` Type-Mismatch macht forced-command und low-confidence Pfade zu Dead Code

**Datei:** `agent.py` ~L1960 + `tool_execution_manager.py` ~L554, L895  
`_detect_intent_gate` gibt `confidence` als **String** (`"high"`, `"medium"`, `"low"`) zurück. `execute()` vergleicht mit `isinstance(confidence, (int, float))` → **immer False** → forced `run_command` Insertion und low_confidence Empty-Reason **nie erreicht**.

---

### NEW H-22: Unbehandelte Exceptions in EXECUTE_ATTEMPT ohne Health/CB Cleanup

**Datei:** `fallback_state_machine.py` ~L185–L260  
`except`-Block fängt nur `GuardrailViolation` und `LlmClientError`. Allgemeine Exceptions (z.B. `asyncio.CancelledError`, `TypeError`) hinterlassen Health-Tracker und Circuit-Breaker in inkonsistentem Zustand.

---

## MEDIUM (22)

### M-2: Steer-Interrupted-Pfad schreibt Antwort nicht ins Memory

**Datei:** `agent.py` ~L925–L970  
`interrupted_message` wird gesendet aber nicht in Memory geschrieben. Verursacht `[user, user]`-Sequenz bei nächster Sanitization.

---

### M-3: Off-by-One bei Regular-Replan-Budget

**Datei:** `agent.py` ~L1907  
Bei `max_replan_iterations=1`: `iteration < 0` → **immer False** → 0 reguläre Replans.

---

### M-4: Schwacher Regex für `[ok]`/`[error]`-Klassifizierung

**Datei:** `agent.py` ~L1891–L1896  
`" error:"` matcht beliebige Fehlererwähnungen in Tool-Output-Inhalten → False Positives bei Replan-Trigger.

---

### M-5: Error-/Empty-Replans konsumieren reguläres Replan-Budget

**Datei:** `agent.py` ~L752–L810  
Shared `iteration`-Counter für alle Replan-Typen. Error-Replans verbrauchen Budget für reguläre Replans.

---

### M-6: Keyword-Match zu breit in `_resolve_synthesis_task_type`

**Datei:** `agent.py` ~L2241–L2244  
`"test"` matcht "testimony", `"code"` matcht "zip code" → falsches Implementation-Evidence-Gate.

---

### M-7: `_build_root_cause_replan_prompt` — `user_message` unbegrenzt

**Datei:** `agent.py` ~L1930–L1935  
`user_message` ohne Limit im Prompt, kann Token-Budget sprengen.

---

### M-8: `_ensure_mcp_tools_registered` — partielle Init bei Retry

**Datei:** `agent.py` ~L2373–L2401  
Fehler nach initialize() → `_mcp_initialized = False` aber Bridge bereits initialisiert → Double-Init beim Retry.

---

### M-9: Doppel-Truncation nach Summary-Inject

**Datei:** `tool_execution_manager.py` ~L222–L240 + `prompt_kernel_builder.py` ~L46  
Skills auf 3000 Zeichen contracted, aber Prompt-Kernel-Limit schneidet auf 1400 → Skills komplett verloren.

---

### M-10: `web_fetch` Retry aktualisiert Loop-Gatekeeper nicht

**Datei:** `tool_execution_manager.py` ~L1406–L1510  
Retry-Ergebnis wird nicht an `loop_gatekeeper.after_tool_success()` gemeldet.

---

### M-11: Forced `run_command` umgeht Validation (Dead Code wegen H-21/C-6)

**Datei:** `tool_execution_manager.py` ~L895–L906  
Injected Action würde `validate_actions()` umgehen, aber Pfad ist unerreichbar.

---

### M-12: `tool_call_count` — parallele Fehler nicht gezählt

**Datei:** `tool_execution_manager.py` ~L1130–L1141  
Fehlgeschlagene parallele Calls zählen nicht zum Budget → unbegrenzter Retry bei Fehlern.

---

### M-13: `_execute_read_only_action` emittiert keine Lifecycle-Events

**Datei:** `tool_execution_manager.py` ~L1604–L1659  
Kein `tool_started`/`tool_completed`/`tool_failed` → unsichtbare Ausführung.

---

### M-15: Task-Registrierung nach `create_task` → Zombie möglich

**Datei:** `subrun_lane.py` ~L228–L231  
Task kann starten und enden bevor `_run_tasks[run_id] = task` ausgeführt wird.

---

### M-17: `_cancel_task` ignoriert non-CancelledError

**Datei:** `subrun_lane.py` ~L510–L520  
Task mit anderer Exception → `await task` propagiert Exception unkontrolliert.

---

### M-18: `run_in_lane` verliert Ergebnis bei `on_released`-Fehler

**Datei:** `session_lane_manager.py` ~L115–L135  
`on_released`-Exception überschreibt den Return-Wert eines erfolgreichen Runs.

---

### M-22: `_normalize_session_id` Session-Kollisionen

**Datei:** `memory.py` ~L139–L141  
IDs aus Sonderzeichen werden alle auf `"session"` gemappt. `"user.1"` und `"user1"` kollidieren.

---

### M-24: Skills-Cache TTL-only Check umgeht mtime-Invalidierung

**Datei:** `skills/service.py` ~L98–L103  
Innerhalb des TTL-Fensters werden Dateiänderungen nicht erkannt.

---

### M-25: `discover_skills` Root-SKILL.md Parse-Fehler blockiert gesamte Discovery

**Datei:** `skills/discovery.py` ~L19–L24  
`return []` statt nur den fehlenden Skill zu überspringen.

---

### M-26: `is_shell_command` False Positive bei `/` und `\`

**Datei:** `intent_detector.py` ~L95–L96  
Jeder Text mit Schrägstrich wird als Shell-Befehl klassifiziert (URLs, Dateipfade).

---

### NEW M-27: Per-Agent Tool-Policy-Overrides ignoriert in HeadAgent

**Datei:** `agent.py` ~L1715–L1745  
`_resolve_effective_allowed_tools` verarbeitet `allow`/`deny`/`also_allow` aber ignoriert `tool_policy.agents[agent_id]`.

---

### NEW M-28: Pending Policy-Approvals werden nie evicted

**Datei:** `policy_approval_service.py` ~L86–L100  
`_evict_stale_records_locked()` überspringt `status == "pending"` → unbegrenztes Wachstum bei abgebrochenen Requests.

---

### NEW M-29: Distillation bekommt leere Daten bei Steer/Clarification Early-Exit

**Datei:** `agent.py` ~L1383–L1397  
Bei Steer- und Clarification-Pfaden bleibt `final_text = ""` → Distillation produziert irreführende LTM-Einträge.

---

### NEW M-30: Suppressed-Reply-Pfad: kein `"final"`-Event, kein Memory-Write

**Datei:** `agent.py` ~L1337–L1375  
Nur `"status"`-Event gesendet. Client erwartet `"final"` → UI hängt im Loading-State. Nächste Session hat `user` ohne `assistant` → Dedup-Probleme.

---

### NEW M-31: `pending_recovery_outcome` nicht gesetzt bei Same-Model-Content-Recovery (letztes Modell)

**Datei:** `fallback_state_machine.py` ~L478–L481  
Content-basierte Recovery auf dem letzten Modell: `has_fallback = False` → Recovery-Metrik wird nie gespeichert → adaptive Priority-Learning hat keine Daten.

---

### NEW M-32: Pipeline markiert ALLE Steps als "completed" ungeachtet tatsächlicher Ausführung

**Datei:** `pipeline_runner.py` ~L155–L161  
Bei einfachen Anfragen ohne Tools werden `TOOL_SELECT` und `TOOL_EXECUTE` trotzdem als `"completed"` markiert.

---

## LOW (14)

| ID | Datei | Beschreibung |
|----|-------|-------------|
| L-1 | `agent.py` | `_run_tool_with_policy` Retry ohne Backoff |
| L-2 | `agent.py` | `_plan_still_valid` ignoriert `plan_text`-Parameter |
| L-3 | `agent.py` | `_distill_session_knowledge` — ungeschütztes JSON-Parsing vom LLM |
| L-4 | `agent.py` | `_has_successful_tool_output` — Regex erwartet `\n` nach Tool-Header |
| L-5 | `agent.py` | `_shape_final_response` vor `_requires_implementation_evidence`-Gate |
| L-6 | `tool_execution_manager.py` | `error_elapsed_ms` stale im Retry-Fehlerpfad |
| L-7 | `tool_execution_manager.py` | `_smart_truncate` kann Output > `max_chars` produzieren |
| L-8 | `events.py` | Error-Stages wie `model_fallback_exhausted` erhalten `"progress"` statt `"error"` |
| L-9 | `tool_result_context_guard.py` | `_TOOL_BLOCK_PATTERN` erfordert Trailing Newline |
| L-10 | `reflection_service.py` | `_extract_json_payload` greedy Regex versagt bei mehreren JSON-Objekten |
| L-12 | `context_reducer.py` | Budget-Allokation summiert zu 120% (Hard-coded splits) |
| L-13 | `verification_service.py` | Naives Substring-Matching für `" error"`/`" ok"` |
| NEW L-14 | `memory.py` | `plan`-Rolle resettet `last_conversation_role` nicht in `sanitize_session_history` |
| NEW L-15 | `agent.py` | `_IMPLEMENTATION_RE` wird bei jedem Aufruf neu kompiliert statt als Modulkonstante |
| NEW L-16 | `app_state.py` | `threading.Lock` für `ControlPlaneState` statt `asyncio.Lock` |
| NEW L-17 | `agent.py` | Doppelter Timeout im `_retry_run_command_after_policy_approval` (2× Timeout) |
| NEW L-18 | `memory.py` | `_load_from_disk` `.strip()` entfernt signifikanten Content-Whitespace |

---

## Priorisierte Fix-Reihenfolge

### Phase 1 — Kritische Korrektheit (sofort)
1. **C-2** — `tool_result_persisted` vor `startswith("tool_")` prüfen
2. **C-4** — `LazyRuntimeRegistry`: lokale Variable, erst nach Init zuweisen
3. **C-5** — `PolicyApprovalService.create()`: atomaren Lock nutzen
4. **C-1** — Prompt-Kernel-Limits anpassen oder `effective_memory_context` korrekt budgetieren

### Phase 2 — Security & State-Integrity (hoch)
5. **H-14** — Leeres `known_allow` = leeres Set, nicht alle
6. **H-16** — Per-Tool Session-Approval statt blanket
7. **H-9** — `asyncio.wait` + `asyncio.FIRST_COMPLETED` statt `asyncio.wait_for`
8. **H-19** — `_normalize_tool_name`: `return lowered` statt `return normalized`
9. **H-21** — Confidence-Type-Mismatch → float-Vergleich oder String-API konsistent
10. **H-10** — Pipeline `try/finally` für Step-Status
11. **H-13** — `created_at` aus bestehendem State übernehmen
12. **H-12** — Lock in `init_run` hinzufügen
13. **H-20** — Subrun `_run` Post-Completion in try/except wrappen
14. **H-22** — Catch-all `except Exception` in EXECUTE_ATTEMPT

### Phase 3 — Guardrails & Lifecycle (mittel)
15. **M-30** — Suppressed-Reply: `"final"`-Event + Memory-Write
16. **M-2** — Steer-Interrupted: Memory-Write
17. **M-29** — Distillation: `final_text` bei Early-Exit korrekt setzen
18. **M-3** — Off-by-One Replan Budget korrigieren
19. **M-5** — Separate Counters für Error- vs. Regular-Replans
20. **M-26** — `is_shell_command` Regex verschärfen
21. **H-2** — `effective_memory_context` an Action-Pipeline
22. **M-6** — Word-Boundary + Kontext für Synthesis-Task-Type

### Phase 4 — Ergänzende Korrekturen
- Remaining M-* und L-* systematisch nach Aufwand/Impact abarbeiten
