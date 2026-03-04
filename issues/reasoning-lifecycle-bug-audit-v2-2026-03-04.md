# Reasoning Lifecycle — Vollständiger Bug-Audit (v2)

**Datum:** 4. März 2026  
**Scope:** Alle Dateien im Reasoning-Lifecycle-Pfad: Transport → Orchestration → Agents → Services → Memory/State  
**Methode:** Systematische Code-Analyse aller ~30 Kerndateien  

---

## Übersicht

| Severity | Anzahl |
|----------|--------|
| CRITICAL | 8 |
| HIGH | 14 |
| MEDIUM | 27 |
| LOW | 11 |
| **Gesamt** | **60** |

---

## CRITICAL (8)

### C-1 — Context-Window-Guard blockiert bei 0 verbleibenden Tokens NICHT

**Datei:** `backend/app/model_routing/context_window_guard.py` L21–24

```python
should_block=safe_tokens > 0 and safe_tokens < hard_min,
```

Bei `safe_tokens=0` ergibt `safe_tokens > 0` → `False`, also `should_block=False`. Der Guard lässt Requests durch, wenn das Kontext-Budget **vollständig** erschöpft ist.

**Fix:** `should_block=safe_tokens < hard_min`

---

### C-2 — `confidence`-Vergleich String vs. Float bricht Forced-Action-Failsafe

**Datei:** `backend/app/services/tool_execution_manager.py` L970, L560–566

```python
confidence = getattr(intent_decision, "confidence", "low")  # ← float (0.95)
if ... and confidence == "high":                              # ← IMMER False
```

`IntentGateDecision.confidence` ist ein `float`. `confidence == "high"` und `confidence == "low"` sind **immer `False`**. Dadurch wird:
1. Der Forced-Action-Fallback bei `execute_command`-Intent **nie** ausgelöst
2. `empty_reason` ist immer `"ambiguous_input"` statt `"low_confidence"`

**Fix:** Float-Thresholds verwenden (`confidence >= 0.8` statt `== "high"`)

---

### C-3 — `status = "completed"` fehlt bei web-search-unavailable Early-Return

**Datei:** `backend/app/agent.py` L1028–1039

```python
self.memory.add(session_id, "assistant", final_text)
return final_text  # ← status bleibt "failed"!
```

Alle anderen Early-Returns setzen `status = "completed"`. Dieser nicht. Im `finally`-Block wird `status == "failed"` gesehen → `_distill_session_knowledge` läuft nicht, `agent_end`-Hook meldet fälschlicherweise Failure.

**Fix:** `status = "completed"` vor `return` einfügen

---

### C-4 — Fallback State Machine inkrementiert Model-Index NACH Message-Transformation

**Datei:** `backend/app/orchestrator/fallback_state_machine.py` L652–654

```python
self._current_model_index += 1   # ← immer nächstes Modell
self._state = FallbackState.SELECT_MODEL
```

Wenn `prompt_compaction` oder `payload_truncation` die Nachricht transformiert hat (um ins Context-Window zu passen), soll das **gleiche** Modell erneut versucht werden. Stattdessen wird immer auf das nächste Modell gewechselt → Transformation wird verschwendet.

**Fix:** Nur inkrementieren wenn keine nachrichtenverändernde Strategie angewendet wurde

---

### C-5 — Recovery-Strategien durch `has_fallback` Guard bei letztem/einzigem Modell blockiert

**Datei:** `backend/app/orchestrator/recovery_strategy.py` L147, L204

```python
if reason == "context_overflow" and has_fallback:
    # prompt_compaction ist HIER DRIN — braucht aber kein Fallback!
```

`prompt_compaction` und `payload_truncation` transformieren die Nachricht und brauchen kein Fallback-Modell. Durch `and has_fallback` werden sie nie ausgeführt, wenn nur ein Modell konfiguriert ist.

**Fix:** `has_fallback`-Bedingung nur auf `overflow_fallback_retry` anwenden, nicht auf den gesamten Block

---

### C-6 — „Last model" Check verwirft gültige Recovery-Strategien

**Datei:** `backend/app/orchestrator/fallback_state_machine.py` L581–598

```python
if self._current_model_index >= len(self._models) - 1:
    self._state = FallbackState.FINALIZE_FAILURE
    continue  # ← auch wenn prompt_compaction retryable=True gesetzt hat!
```

Selbst wenn eine Recovery-Strategie die Nachricht erfolgreich transformiert und `retryable=True` markiert hat, wird bei letztem Modell sofort aufgegeben.

**Fix:** Prüfen ob eine nachrichtenverändernde Strategie angewendet wurde und Retry erlauben

---

### C-7 — `sanitize_session_history` löscht gültige User-Messages nach Tool-Ergebnissen

**Datei:** `backend/app/memory.py` L110–117

```python
if item.role == last_conversation_role:
    continue  # ← LÖSCHT das zweite user-message!
```

Bei Sequenz `user → tool:result → user` wird `last_conversation_role` durch tool-Messages **nicht** zurückgesetzt. Das zweite `user`-Message wird gelöscht → Multi-Tool-Conversations verlieren Kontext.

**Fix:** `last_conversation_role = None` setzen bei tool-role Messages

---

### C-8 — Race Condition bei `active_event_agent_name` (shared nonlocal über Tasks)

**Datei:** `backend/app/ws_handler.py` L169, L229, L387–388, L600, L976

`active_event_agent_name` ist eine nonlocal-Variable, die von der Hauptschleife UND von multiplen `drain_session_queue`-Tasks konkurrierend gelesen und geschrieben wird. Lifecycle-Events werden dem **falschen Agenten** zugeordnet.

**Fix:** Agent-Name als Parameter statt shared state übergeben

---

## HIGH (14)

### H-1 — Parallel-Read-Only-Actions umgehen Loop-Gatekeeper komplett

**Datei:** `backend/app/services/tool_execution_manager.py` L1075–1115

`_execute_read_only_action` ruft weder `loop_gatekeeper.before_tool_call()` noch Lifecycle-Events/Hooks auf. Identische Read-Only-Calls werden parallel ohne Loop-Erkennung oder Audit ausgeführt.

---

### H-2 — Alle Safety-Checks bei `COMMAND_ALLOWLIST_ENABLED=false` umgangen

**Datei:** `backend/app/tools.py` L818–819

```python
if not self._command_allowlist_enabled:
    return self._extract_command_leader(command)
```

Nicht nur die Allowlist, sondern **alle** Safety-Checks (blocked leaders, shell chaining, SSRF) werden übersprungen. `rm -rf /`, `curl | sh` etc. möglich.

**Fix:** Safety-Checks unabhängig von Allowlist-Flag ausführen

---

### H-3 — `_resolve_command_cwd` erlaubt beliebige absolute Pfade außerhalb Workspace

**Datei:** `backend/app/tools.py` L919–930

Kein Workspace-Containment-Check wie bei `_resolve_workspace_path`. Agent kann Befehle in jedem Verzeichnis ausführen.

**Fix:** `workspace_root in candidate.parents`-Check hinzufügen

---

### H-4 — Concurrent WebSocket-Sends ohne Serialisierung

**Datei:** `backend/app/ws_handler.py` L177–207

Mehrere concurrent Tasks greifen auf denselben WebSocket zu. Out-of-order Sequence Numbers und concurrent WebSocket-Writes sind möglich.

**Fix:** `asyncio.Lock` um `send_event`-Body

---

### H-5 — `runtime_switch_request` hinterlässt verwaiste Run-States

**Datei:** `backend/app/ws_handler.py` L1023–1041

Run wird mit `status="active"` erstellt, aber nach dem Runtime-Switch wird weder `mark_completed` noch `mark_failed` aufgerufen.

---

### H-6 — Truthiness vs. `is not None` bei `_parse_blocked_tool_result`

**Datei:** `backend/app/agent.py` L1885 vs. L900

```python
if self._parse_blocked_tool_result(tool_results):      # L1885 — Truthiness
if blocked_payload is not None:                          # L900 — Identity
```

Bei leerem Dict `{}` divergiert das Verhalten → State-Klassifizierung als `"usable"` statt `"blocked"`.

---

### H-7 — `finally` kann Original-Exception durch Hook-Exception ersetzen

**Datei:** `backend/app/agent.py` L1375–1408

`_invoke_hooks("agent_end")` im `finally`-Block kann selbst eine Exception werfen und die Original-Exception überschreiben.

---

### H-8 — Clarification-Antwort wird nicht im Memory gespeichert

**Datei:** `backend/app/agent.py` L628–641

Die User-Nachricht wird gespeichert, die Clarification-Antwort des Agents nicht. Bei der nächsten User-Antwort fehlt der Kontext der Rückfrage.

---

### H-9 — ContextVars werden VOR `agent_end`-Hook zurückgesetzt

**Datei:** `backend/app/agent.py` L1375–1398

Hooks/Sub-Logik, die ContextVars lesen, erhalten `None` → stille Fehler oder `NoneType`-Exceptions.

---

### H-10 — Sandbox leakt alle Umgebungsvariablen inkl. Secrets

**Datei:** `backend/app/services/code_sandbox.py` L260–272

```python
env = dict(os.environ)  # ← kopiert ALLES
```

API-Keys, DB-Passwörter etc. sind im Sandbox-Code lesbar.

---

### H-11 — Tool-Retry kann Budget überschreiten

**Datei:** `backend/app/services/tool_execution_manager.py` L1350–1505

Budget-Check vor Tool-Call, aber Retry hat **keinen** Budget-Check. `tool_call_count` überschreitet `tool_call_cap`.

---

### H-12 — `_redact_secret_like_values` versagt bei JSON-formatierten Secrets

**Datei:** `backend/app/services/tool_execution_manager.py` L616–622

Regex `[^\s,;\"']+` matched nicht auf Werte die mit `"` beginnen. JSON wie `{"api_key": "sk-12345"}` wird nicht redactiert.

---

### H-13 — Race Condition in Subrun-Spawn Guardrails (TOCTOU)

**Datei:** `backend/app/orchestrator/subrun_lane.py` L130–145

Depth-/Children-Count-Checks lesen ohne Lock → zwei gleichzeitige Spawns können Limits überschreiten.

---

### H-14 — Session-Lock-Eviction Race in SessionLaneManager

**Datei:** `backend/app/orchestrator/session_lane_manager.py` L92–95

Lock-Objekt wird vor Akquirierung zurückgegeben. Eviction kann Lock zwischen Return und `async with` entfernen → zwei Coroutines halten verschiedene Locks für dieselbe Session.

---

## MEDIUM (27)

### M-1 — `_resolve_replan_reason` liefert falschen Replan-Grund bei Error-Budget-Exhaustion

**Datei:** `backend/app/agent.py` L1920–1933  
Error-Only State fällt durch zum regulären Budget → falscher Prompt.

### M-2 — `_step_budgets` Summe kann Context-Window überschreiten

**Datei:** `backend/app/agent.py` L1531–1540  
`max()`-Minima pumpen Summe über Budget bei kleinen Modellen.

### M-3 — `\bok\b` Regex False-Positive maskiert error_only State

**Datei:** `backend/app/agent.py` L1892  
Natürliches "ok" im Tool-Output unterdrückt Error-Erkennung.

### M-4 — Doppel-Timeout bei sync-Tools die Awaitables zurückgeben

**Datei:** `backend/app/agent.py` L2456–2465  
Maximale Gesamtzeit = 2× `policy.timeout_seconds`.

### M-5 — Substring-Match für `_resolve_synthesis_task_type` erzeugt False-Positives

**Datei:** `backend/app/agent.py` L2197–2210  
`"test"` matched in `"latest"`, `"bug"` in `"debug"`, `"code"` in `"barcode"`.

### M-6 — Private-Attribut-Mutation auf ToolExecutionManager

**Datei:** `backend/app/agent.py` L2362  
`self._tool_execution_manager._registry = self.tool_registry` — derived state wird nicht aktualisiert.

### M-7 — Terminal-State Self-Transition erlaubt

**Datei:** `backend/app/orchestrator/run_state_machine.py` L75–80  
`completed → completed` gibt `True` zurück → doppelte Completion-Events.

### M-8 — Subrun-Cancellation vor try-Block lässt "running" Status verwaist

**Datei:** `backend/app/orchestrator/subrun_lane.py` L537–555  
CancelledError vor `try` → Cleanup-Code läuft nicht.

### M-9 — Recovery-Metrics-Datei Race Condition (Lost Updates)

**Datei:** `backend/app/orchestrator/pipeline_runner.py` L1103–1140  
Parallele Instanzen: read-modify-write ohne File-Locking.

### M-10 — PolicyApprovalService Memory-Leak (`_records`/`_events` nie aufgeräumt)

**Datei:** `backend/app/services/policy_approval_service.py` L46–80  
Kein TTL/Eviction-Mechanismus → unbegrenztes Wachstum.

### M-11 — `repeat_signature_hits` Counter monoton wachsend (Circuit Breaker False-Positives)

**Datei:** `backend/app/services/tool_call_gatekeeper.py` L108–110  
Counter wird nie dekrementiert/zurückgesetzt → legitime lange Runs werden abgebrochen.

### M-12 — Synchrone File-I/O blockiert Event Loop unter Lock

**Datei:** `backend/app/services/policy_approval_service.py` L120–131  
`tmp.write_text()` / `tmp.replace()` sind synchron, Lock bleibt gehalten.

### M-13 — Sandbox Network-Blocking ist trivial umgehbar

**Datei:** `backend/app/services/code_sandbox.py` L308–330  
Token-Matching umgehbar durch `__import__('socket')`, `importlib.import_module()`, etc.

### M-14 — Sandbox Filesystem-Escape-Detection ist umgehbar

**Datei:** `backend/app/services/code_sandbox.py` L333–348  
Umgehbar durch `chr()`, `base64`, `bytes([...])`.

### M-15 — Prompt Injection via Tool Results in Reflection-Service

**Datei:** `backend/app/services/reflection_service.py` L92–102  
Ungefilterte Tool-Results direkt in Reflection-Prompt → Verdict manipulierbar.

### M-16 — `wait_for_decision` ignoriert Status "cancelled"

**Datei:** `backend/app/services/policy_approval_service.py` L208–215  
Gecanceltes Approval blockiert ggf. Aufrufer.

### M-17 — MCP StdioConnection liest Content ohne Größenlimit

**Datei:** `backend/app/services/mcp_bridge.py` L306–308  
`content_length` unbegrenzt → DoS durch bösartigen MCP-Server.

### M-18 — `StateStore.init_run` nicht durch Lock geschützt

**Datei:** `backend/app/state/state_store.py` L29–62  
Alle anderen mutierenden Methoden verwenden Lock, `init_run` nicht.

### M-19 — Trailing orphaned Tool-Calls nicht repariert

**Datei:** `backend/app/memory.py` L75–97  
Wenn Konversation mit assistant-message (tool_calls) endet → invalide History für LLM.

### M-20 — LongTermMemoryStore hat keine Thread-Synchronisierung

**Datei:** `backend/app/long_term_memory.py` L45–50  
Kein Lock, keine persistente Connection → `sqlite3.OperationalError` bei Concurrent Writes.

### M-21 — `EpisodicEntry.entry_id` Timestamp-basiert → PK-Kollisionen

**Datei:** `backend/app/long_term_memory.py` L37, L92  
Zwei Entries innerhalb Mikrosekunde → `INSERT OR REPLACE` → Datenverlust.

### M-22 — Komma-Trennung korruptiert Daten mit Kommas in key_actions/tags

**Datei:** `backend/app/long_term_memory.py` L88–90, L268–269  
`"read file_a, file_b"` wird zu `["read file_a", "file_b"]`.

### M-23 — `StateStore._replace_with_retry` blockiert Event-Loop mit `time.sleep`

**Datei:** `backend/app/state/state_store.py` L270–280  
Synchrone Sleeps (bis 75ms) im async-Kontext.

### M-24 — Clarification-Response ignoriert ursprünglichen Agent

**Datei:** `backend/app/ws_handler.py` L855–890  
Antwort wird nicht an den fragenden Agent zurückgeroutet.

### M-25 — Race Condition in `RuntimeManager.switch_runtime`

**Datei:** `backend/app/runtime_manager.py` L115–150  
`self._state` wird ohne Lock gelesen/geschrieben. Parallele Switches können inkonsistenten State erzeugen.

### M-26 — File-Handle-Leak in `start_background_command`

**Datei:** `backend/app/tools.py` L223–233  
Wenn `subprocess.Popen` scheitert, wird `log_file` nicht geschlossen.

### M-27 — `ControlPlaneState` verwendet `threading.Lock` im asyncio-Kontext

**Datei:** `backend/app/app_state.py` L17–20  
Kann Event-Loop blockieren und zu Deadlocks führen.

---

## LOW (11)

### L-1 — `_refresh_long_term_memory_store` schluckt Exceptions lautlos

**Datei:** `backend/app/agent.py` L393–400  
Kein Logging bei LTM-Init-Fehler → LTM wird still deaktiviert.

### L-2 — `_distill_session_knowledge` Exception komplett verschluckt

**Datei:** `backend/app/agent.py` L1389–1395  
`except Exception: pass` ohne Logging.

### L-3 — Failure-Journal-Einträge haben immer leere `solution`/`prevention`

**Datei:** `backend/app/agent.py` L1359–1369  
"Fix"-Hinweis in LTM-Kontext ist immer leer.

### L-4 — `register_hook` ohne Deduplizierung

**Datei:** `backend/app/agent.py` L228  
Derselbe Hook kann mehrfach registriert werden → doppelte Side-Effects.

### L-5 — `on_released` Exception wird bei vorherigem run()-Fehler verschluckt

**Datei:** `backend/app/orchestrator/session_lane_manager.py` L117–121  
Kein Logging bei Cleanup-Fehler.

### L-6 — `_detect_ping_pong_pattern` Off-by-one bei `alternating_count`

**Datei:** `backend/app/services/tool_call_gatekeeper.py` L303  
Threshold wird einen Call zu früh erreicht.

### L-7 — `ModelHealthTracker.snapshot()` nicht async-safe (irreführender Kommentar)

**Datei:** `backend/app/services/model_health_tracker.py` L100–101  
Kommentar behauptet GIL-Safety, deque kann bei Multi-Thread modifiziert werden.

### L-8 — Gemini VisionService übergibt API Key als URL-Parameter

**Datei:** `backend/app/services/vision_service.py` L136  
Key in Query-String → potenzielle Secret-Leakage über URL-Logging.

### L-9 — `_is_sensitive_key` matcht zu breit ("auth" → "author")

**Datei:** `backend/app/state/state_store.py` L217–222  
Legitime Felder werden fälschlich redactiert.

### L-10 — `_start_gateway` speichert Popen-Handle nicht

**Datei:** `backend/app/runtime_manager.py` L175–184  
Ollama-Prozesse können nicht beendet werden → Akkumulation verwaister Prozesse.

### L-11 — DNS-Rebinding TOCTOU in SSRF-Schutz

**Datei:** `backend/app/tools.py` L633–650  
Zwischen DNS-Check und HTTP-Request kann Hostname auf interne IP rebinden.

---

## Abhängigkeitsgraph der kritischsten Bugs

```
C-4 + C-5 + C-6 → Recovery/Fallback ist bei 1-Modell-Setups effektiv deaktiviert
    ↓
C-1 → Guard lässt 0-Token-Requests durch → Context-Overflow → Recovery greift nicht

C-2 → Forced-Action-Failsafe tot → leere Antworten bei execute_command
C-7 → User-Messages gehen verloren → Agent verliert Kontext

H-2 + H-3 → Bei deaktivierter Allowlist sind alle OS-Befehle in jedem Verzeichnis erlaubt
H-10 → Sandbox leakt Credentials → Agent könnte sie ins Web exfiltrieren
```

---

## Priorisierte Fix-Reihenfolge

1. **C-1** Context-Window-Guard (1-Zeilen-Fix)
2. **C-2** Confidence-Vergleich (2-Zeilen-Fix)
3. **C-7** sanitize_session_history (3-Zeilen-Fix)
4. **H-2 + H-3** Command Safety Bypass (struktureller Fix)
5. **H-10** Sandbox Environment-Leak (Whitelist-Ansatz)
6. **C-4 + C-5 + C-6** Recovery/Fallback-Kette (zusammenhängend refactoren)
7. **C-3** Status bei web-unavailable (1-Zeilen-Fix)
8. **C-8** active_event_agent_name (Parameter statt nonlocal)
9. **H-4** WebSocket-Send-Lock
10. **H-12** Secret-Redaction Regex
