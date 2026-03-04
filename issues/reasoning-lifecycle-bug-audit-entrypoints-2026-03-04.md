# Reasoning Lifecycle Bug Audit — Entry Points (2026-03-04)

## Scope

Auditiert wurden die Entry-Point-Dateien der Reasoning-Lifecycle:

- `backend/app/ws_handler.py` (1358 Zeilen)
- `backend/app/run_endpoints.py` (191 Zeilen)
- `backend/app/subrun_endpoints.py` (150 Zeilen)

---

## Bereits bekannte Bugs (aus vorherigem Audit, hier der Vollständigkeit halber)

### K1) Unsupported-Type-Pfad hinterlässt aktive Runs ohne Terminal-Status

- **Datei:** `backend/app/ws_handler.py` Zeilen 629–663
- **Schwere:** Mittel
- **Root cause:** Run wird mit `init_run` + `set_task_status("active")` initialisiert. Nach `request_rejected_unsupported_type` folgt nur `continue` — kein `state_mark_failed_safe` / `state_mark_completed_safe`.
- **Impact:** Hängende Runs im State-Store.

### K2) `request_cancelled` (PolicyApprovalCancelledError) setzt keinen Terminal-State

- **Datei:** `backend/app/ws_handler.py` Zeilen 243–257 (`handle_request_failure`) und Zeilen 1240–1250 (Outer loop)
- **Schwere:** Mittel
- **Root cause:** Lifecycle `request_cancelled` wird emittiert, aber weder `state_mark_failed_safe` noch `state_mark_completed_safe` aufgerufen.
- **Impact:** Run bleibt im Status `active`.

### K3) Session-Overrides Cleanup nur für Connection-ID

- **Datei:** `backend/app/ws_handler.py` Zeile 1351
- **Schwere:** Hoch
- **Root cause:** `clear_session_overrides(connection_session_id)` im `finally`-Block. Clients die per `data.session_id` andere Sessions senden, werden nicht aufgeräumt.
- **Impact:** Policy-Approvals können über Verbindungen hinweg bestehen bleiben (Scope-Leak).

### K4) Falsche Agent-Attribution im Queue-Worker

- **Datei:** `backend/app/ws_handler.py` Zeile 350ff
- **Schwere:** Hoch
- **Root cause:** `execute_user_message_job()` setzt `active_event_agent_name` nicht. Lifecycle-Events bekommen den globalen Agent-Namen statt des resolved-Agent-Namens.
- **Impact:** Falsche Telemetrie/Tracing.

---

## Neue Bugs

### BUG-1: `runtime_switch_request` hinterlässt aktiven Run ohne Terminal-Status

- **Datei:** `backend/app/ws_handler.py` Zeilen 987–1035
- **Schwere:** Mittel
- **Root cause:** Vor dem `if data.type == "runtime_switch_request"` Block wird ein Run initialisiert:
  ```python
  # Zeile 987
  deps.state_store.init_run(...)
  # Zeile 995
  deps.state_store.set_task_status(..., status="active")
  # Zeile 996
  await send_lifecycle(stage="request_received", ...)
  ```
  Der `runtime_switch_request`-Handler (Zeile 1016–1035) sendet nur `runtime_switch_requested` und `runtime_switch_done`, führt dann `continue` aus — **ohne** `state_mark_completed_safe` oder `state_mark_failed_safe`. Der Run bleibt `active`.
- **Snippet:**
  ```python
  # Zeile 1016-1035
  if data.type == "runtime_switch_request":
      target = (data.runtime_target or "").strip().lower()
      await send_lifecycle(stage="runtime_switch_requested", ...)
      state = await deps.runtime_manager.switch_runtime(target, send_event, session_id)
      await send_event({"type": "runtime_switch_done", ...})
      continue  # ← kein state_mark_completed_safe!
  ```
- **Impact:** Jeder Runtime-Switch erzeugt einen hängenden Run im State-Store.

---

### BUG-2: `runtime_switch_request` Exception wird doppelt behandelt (outer + inner)

- **Datei:** `backend/app/ws_handler.py` Zeilen 1016–1035 vs. 1230–1245 vs. 1267–1280
- **Schwere:** Niedrig
- **Root cause:** Wenn `switch_runtime()` eine `RuntimeSwitchError` wirft, wird sie im outer-loop exception handler gefangen (Zeile 1267), der `state_mark_failed_safe` aufruft. Allerdings: Wenn `switch_runtime()` *vor* erfolgreicher Initialisierung eine andere Exception wirft (z.B. bei `ensure_model_ready`), wird ein anderer Request-ID referenziert als der tatsächlich fehlschlagende Run.
- **Impact:** Gering – meist korrekt, aber theoretisch State-Mismatch möglich.

---

### BUG-3: Queued Run (`user_message`/`clarification_response`) wird doppelt als failed markiert

- **Datei:** `backend/app/ws_handler.py` Zeilen 575–578 + 1226–1310
- **Schwere:** Niedrig
- **Root cause:** Für den Queue-Pfad (`user_message`/`clarification_response`) rufen sowohl `drain_session_queue` (Zeile 577: `handle_request_failure`) **als auch** der äußere Exception-Handler (Zeile 1226ff) `state_mark_failed_safe` auf, wenn die Exception durch `execute_user_message_job` → `handle_request_failure` nicht gänzlich gefangen wird. In der Praxis wird die Exception durch `handle_request_failure` abgefangen, ABER: Wenn `handle_request_failure` selbst eine Exception wirft (z.B. `ClientDisconnectedError` aus `send_event`), propagiert die Exception nach oben in den outer handler, der den **neuen** `request_id` des aktuellen Loop-Iterations markiert, NICHT den des fehlschlagenden Jobs.
- **Snippet:**
  ```python
  # drain_session_queue, Zeile 574-578
  try:
      await execute_user_message_job(dict(dequeued.meta))
  except Exception as exc:
      await handle_request_failure(...)  # kann ClientDisconnectedError werfen
  
  # Outer loop, Zeile 1226ff - fängt Exception mit NEUEM request_id
  except Exception as exc:
      deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
  ```
- **Impact:** Falscher Run wird als failed markiert; der eigentlich fehlgeschlagene Job bleibt `active`.

---

### BUG-4: `handle_request_failure` kann `ClientDisconnectedError` aus `send_event` propagieren — Run-State bleibt inkonsistent

- **Datei:** `backend/app/ws_handler.py` Zeilen 243–330
- **Schwere:** Hoch
- **Root cause:** `handle_request_failure` ruft `send_event()` und `send_lifecycle()` auf. `send_event()` kann `ClientDisconnectedError` bei Disconnect werfen. Bei Exceptions wie `PolicyApprovalCancelledError` wird `state_mark_failed_safe` **nicht** vor `send_event` aufgerufen (Zeile 243–257). Das heißt: wenn der Client disconnected zwischen dem `isinstance`-Check und dem `send_event`-Aufruf, bleibt der Run `active`, und die Exception propagiert als `ClientDisconnectedError`.
- **Snippet:**
  ```python
  async def handle_request_failure(*, request_id, session_id, exc):
      if isinstance(exc, PolicyApprovalCancelledError):
          await send_event({...})         # ← kann ClientDisconnectedError werfen
          await send_lifecycle(...)       # ← wird nie erreicht
          return                          # ← state_mark nie aufgerufen
      if isinstance(exc, GuardrailViolation):
          deps.state_mark_failed_safe(...)  # ← hier korrekt VOR send
          await send_event({...})
  ```
  Für `GuardrailViolation`, `ToolExecutionError`, `RuntimeSwitchError`, `LlmClientError`, und den Default-Fall wird `state_mark_failed_safe` **vor** `send_event` aufgerufen — korrekt. Aber bei `PolicyApprovalCancelledError` fehlt es komplett (bekannter Bug K2), und die Kombination mit Disconnect macht es kritischer.
- **Impact:** Run bleibt dauerhaft in `active` wenn Client während Cancellation-Verarbeitung disconnected.

---

### BUG-5: Queue Worker Disconnect lässt queued Runs im `active`-Status

- **Datei:** `backend/app/ws_handler.py` Zeilen 524–583
- **Schwere:** Hoch
- **Root cause:** `drain_session_queue` hat keinen try/except für `ClientDisconnectedError` um den Drain-Loop. Wenn der Client during eines Jobs disconnected:
  1. `send_event` wirft `ClientDisconnectedError`
  2. Die Exception propagiert durch `execute_user_message_job` → `handle_request_failure` → `send_event`
  3. `drain_session_queue` fängt dies nicht — es propagiert zum `finally`-Block (Zeile 579)
  4. Der Worker wird aus `session_workers` entfernt
  5. Alle verbleibenden Queue-Items werden weder bearbeitet noch als failed markiert
  6. Der aktuelle Run wurde möglicherweise per `state_mark_failed_safe` markiert (falls ein nicht-Cancel-Error), aber nicht immer.
- **Snippet:**
  ```python
  async def drain_session_queue(session_id: str) -> None:
      current_task = asyncio.current_task()
      try:
          while True:
              # ... dequeue ...
              try:
                  await execute_user_message_job(dict(dequeued.meta))
              except Exception as exc:
                  await handle_request_failure(...)  # kann ClientDisconnectedError reraisen
          # Keine Behandlung von ClientDisconnectedError!
      finally:
          session_workers.pop(session_id, None)
          follow_up_deferrals.pop(session_id, None)
          # Keine Cleanup der verbleibenden Queue-Items!
  ```
- **Impact:** Queued Runs bleiben als `active` im State-Store hängen, werden nie terminiert.

---

### BUG-6: Non-queued path (`subrun_spawn`, `runtime_switch_request`, etc.) — Exception in `send_lifecycle("request_received")` lässt Run ohne Lifecycle

- **Datei:** `backend/app/ws_handler.py` Zeilen 996–1015
- **Schwere:** Niedrig
- **Root cause:** `deps.state_store.init_run` und `set_task_status("active")` erfolgen synchron (Zeile 987–995). Danach wird `send_lifecycle("request_received")` aufgerufen (Zeile 996). Wenn der WebSocket zu diesem Zeitpunkt disconnected, wird `ClientDisconnectedError` geworfen — der Run existiert als `active`, hat aber kein einziges Lifecycle-Event.
- **Impact:** Zombie-Run ohne Lifecycle-Trail. Minimal wahrscheinlich, aber möglich.

---

### BUG-7: `active_event_agent_name` ist eine Connection-Scoped Closure-Variable, aber Queue-Worker läuft parallel

- **Datei:** `backend/app/ws_handler.py` Zeilen 170, 596, 223, 969
- **Schwere:** Hoch
- **Root cause:** `active_event_agent_name` ist eine nonlocal-Variable im `handle_ws_agent`-Scope. Sie wird vom Main-Loop auf Zeile 596 zurückgesetzt (`active_event_agent_name = deps.agent.name`), und vom non-queue-Pfad auf Zeile 969 auf den resolved Agent gesetzt. `drain_session_queue` läuft als **paralleler Task** (`asyncio.create_task`), teilt aber dieselbe Variable. Es gibt kein Locking und keinen Task-lokalen Zustand. Während der Queue-Worker arbeitet, kann der Main-Loop die Variable überschreiben (z.B. bei einer neuen Nachricht in einer anderen Session), und umgekehrt.
- **Snippet:**
  ```python
  # Zeile 170 (Closure-Variable)
  active_event_agent_name = deps.agent.name
  
  # Zeile 596 (Main-Loop: Reset bei jeder Iteration)
  active_event_agent_name = deps.agent.name
  
  # Zeile 969 (Non-queue-Pfad: Sets resolved agent)
  active_event_agent_name = selected_agent.name
  
  # Zeile 223 (send_lifecycle: Liest shared Variable)
  lifecycle_event = build_lifecycle_event(..., agent=active_event_agent_name)
  ```
  Da der Queue-Worker in `execute_user_message_job` die Variable **nicht** setzt (bekannter Bug K4), und der Main-Loop sie parallel überschreibt, entsteht ein **Race Condition auf shared mutable state**.
- **Impact:** Lifecycle-Events bekommen in Concurrent-Szenarien den falschen Agent-Namen. Verschärft Bug K4.

---

### BUG-8: `run_agent_test` sendet `mark_completed` mit keyword `run_id`, aber Protocol definiert positional

- **Datei:** `backend/app/run_endpoints.py` Zeile 120
- **Schwere:** Niedrig (funktioniert aktuell nur weil die Implementation keyword-args akzeptiert)
- **Root cause:** `deps.mark_completed(run_id=request_id)` nutzt keyword-arg, ebenso `deps.mark_failed(run_id=request_id, error=str(exc))`. Das `AgentTestDependencies`-Dataclass definiert die Callbacks als:
  ```python
  mark_completed: Callable[[str], None]
  mark_failed: Callable[[str, str], None]
  ```
  Die Type-Hints suggerieren positionelle Args. Aktuell funktioniert es, weil die Implementierung (`state_mark_completed_safe(run_id: str)`) keyword-args akzeptiert. Aber ein Refactoring der Implementierung auf positional-only würde dies brechen.
- **Impact:** Fragil, aber aktuell funktional.

---

### BUG-9: `run_agent_test` ignoriert model override bei API-Runtimes

- **Datei:** `backend/app/run_endpoints.py` Zeilen 75–90
- **Schwere:** Mittel
- **Root cause:** `agent.configure_runtime` wird mit `runtime_state.model` aufgerufen (Zeile 76), **bevor** `selected_model` aufgelöst wird (Zeilen 85–90). Das heißt: der Agent wird mit dem Default-Model konfiguriert, nicht mit dem per Request gewählten Model.
  ```python
  deps.agent.configure_runtime(
      base_url=runtime_state.base_url,
      model=runtime_state.model,          # ← Default, nicht selected_model!
  )
  # ... Danach erst:
  selected_model = (request.model or ...).strip() or runtime_state.model
  ```
  Im WS-Handler (Zeile 432) wird `configure_runtime` dagegen auch mit `runtime_state.model` aufgerufen — gleiches Problem, aber dort wird `selected_model` in die `RequestContext` übergeben und der Orchestrator nutzt es.
- **Impact:** Agent-Konfiguration nutzt falsches Model bei explizitem Model-Override.

---

### BUG-10: `subrun_spawn` nutzt potentiell uninitialisierte `incoming_tool_policy` und `incoming_also_allow`

- **Datei:** `backend/app/ws_handler.py` Zeilen 1037–1065
- **Schwere:** Mittel
- **Root cause:** Der `subrun_spawn`-Branch (Zeile 1037) wird erreicht, wenn `data.type == "subrun_spawn"` nach dem non-queue-Pfad (ab Zeile 940). Die Variablen `incoming_tool_policy` und `incoming_also_allow` werden in Zeilen 940–960 gesetzt. **ABER:** `applied_preset` wird ebenfalls dort gesetzt (Zeile 961). Wenn `data.type == "user_message"` oder `"clarification_response"`, wird Code schon bei Zeile 830 abgezweigt. Der non-queue-Pfad ab 940 deckt `subrun_spawn`, `runtime_switch_request` und sonstige Typen ab. Die Variablen sind also korrekt initialisiert.
  
  **Korrektur:** Nach nochmaliger Prüfung ist dies **kein Bug** — die Variablen werden auf Zeile 940–961 für den non-queue-Pfad korrekt gesetzt bevor der `subrun_spawn`-check erreicht wird.

---

### BUG-10 (korrigiert): `subrun_spawn` Exception-Handler markiert falschen Run als failed

- **Datei:** `backend/app/ws_handler.py` Zeilen 1073–1076
- **Schwere:** Mittel
- **Root cause:** Bei `GuardrailViolation` im `subrun_spawn`-Pfad:
  ```python
  deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
  ```
  `request_id` ist hier die **parent** request ID (generiert am Loop-Start, Zeile 592). Wenn `subrun_lane.spawn` eine eigene `run_id` erzeugt hat, bevor die Exception geworfen wurde, bleibt *die eigentliche Subrun-ID* unmarkiert, und der **Parent-Run** wird fälschlich als failed markiert.
- **Impact:** Parent-Run wird als failed markiert, obwohl nur der Subrun rejected wurde. Subrun-State ist unklar.

---

### BUG-11: `api_subruns_get` prüft Visibility **vor** Existenz — leakt Information

- **Datei:** `backend/app/subrun_endpoints.py` Zeilen 86–95
- **Schwere:** Niedrig
- **Root cause:** 
  ```python
  def api_subruns_get(*, run_id, requester_session_id, visibility_scope, deps):
      decision = _enforce_subrun_visibility_or_403(run_id, ...)  # prüft Visibility zuerst
      info = deps.subrun_lane.get_info(run_id)
      if info is None:
          raise HTTPException(status_code=404, ...)
  ```
  Die Visibility-Prüfung erfolgt **vor** der Existenz-Prüfung. Bei einem nicht existenten Subrun gibt `evaluate_visibility` möglicherweise `allowed=True` zurück (da kein Eintrag vorhanden), woraufhin 404 gesendet wird. Bei `allowed=False` würde 403 gesendet werden. Das bedeutet: Ein Angreifer kann anhand des Statuscodes (403 vs. 404) Information über die Existenz von Subruns leaken.
  
  Gleiches Pattern in `api_subruns_log` (Zeile 98–108) und `api_subruns_kill` (Zeile 111–122).
- **Impact:** Information Disclosure. Severity abhängig von der Sensitivity der Run-IDs.

---

### BUG-12: `api_subruns_kill_all_async` prüft keine Visibility pro Subrun

- **Datei:** `backend/app/subrun_endpoints.py` Zeilen 125–141
- **Schwere:** Mittel
- **Root cause:** `api_subruns_kill_all_async` ruft `deps.subrun_lane.kill_all(...)` auf und übergibt dabei `parent_session_id` und `parent_request_id`. Die Visibility-Prüfung `_enforce_subrun_visibility_or_403` wird **nicht** aufgerufen. `scope` wird zwar normalisiert, aber nie zur Zugriffskontrolle verwendet.
  ```python
  async def api_subruns_kill_all_async(request_data, deps):
      request = KillAllSubrunsRequest.model_validate(request_data)
      scope = _normalize_visibility_scope(request.visibility_scope, deps)
      killed_count = await deps.subrun_lane.kill_all(
          parent_session_id=request.parent_session_id,
          parent_request_id=request.parent_request_id,
          cascade=request.cascade,
      )
      # scope wird nur im Response zurückgegeben, nie enforced!
  ```
- **Impact:** Jeder Client kann potenziell alle Subruns killen, unabhängig von Visibility-Einstellungen.

---

### BUG-13: Direct-Execution-Pfad (non-queue) hat kein Error-Recovery für `run_user_message`

- **Datei:** `backend/app/ws_handler.py` Zeilen 1196–1225
- **Schwere:** Hoch
- **Root cause:** Im non-queue-Pfad wird `selected_orchestrator.run_user_message(...)` direkt aufgerufen (Zeile 1196). Es gibt **keinen** try/except um diesen Aufruf. Exceptions propagieren zum äußeren Exception-Handler (Zeile 1226ff). Allerdings:
  - Der äußere Handler nutzt `request_id` und `session_id` vom **Loop-Iterations-Start** (Zeile 592–593), was korrekt ist.
  - **ABER:** Zwischen `run_user_message` (Zeile 1196) und dem Exception-Handler liegt keine Möglichkeit, `clarification_requested` korrekt zu tracken — der non-queue-Pfad nutzt `send_event` statt `send_event_wrapped`, d.h. Clarification-Tracking fehlt komplett.
  ```python
  # Zeile 1196 - non-queue-Pfad
  await selected_orchestrator.run_user_message(
      user_message=content,
      send_event=send_event,       # ← nicht send_event_wrapped!
      request_context=RequestContext(...)
  )
  ```
- **Snippet (Vergleich mit queue-Pfad, Zeile 489):**
  ```python
  # Queue-Pfad
  await selected_orchestrator.run_user_message(
      user_message=content,
      send_event=send_event_wrapped,  # ← trackt Clarification
      request_context=RequestContext(...)
  )
  ```
- **Impact:** Clarification-Requests werden im non-queue-Pfad nicht getrackt; `pending_clarifications` Dict wird nicht aktualisiert; nachfolgende `clarification_response`-Nachrichten können keine Zuordnung finden.

---

### BUG-14: Non-queue-Pfad ruft `state_mark_completed_safe` bei Clarification auf

- **Datei:** `backend/app/ws_handler.py` Zeilen 1220–1225
- **Schwere:** Mittel (direkte Folge von BUG-13)
- **Root cause:** Da der non-queue-Pfad kein Clarification-Detection hat, wird nach `run_user_message` immer `request_completed` + `state_mark_completed_safe` aufgerufen:
  ```python
  # Zeile 1220-1225
  await send_lifecycle(stage="request_completed", ...)
  deps.state_mark_completed_safe(run_id=request_id)
  ```
  Selbst wenn der Orchestrator ein `clarification_needed`-Event gesendet hat, wird der Run als completed markiert. Im Queue-Pfad (Zeile 513–522) gibt es dagegen korrekte Clarification-Detection, die den Run als wartend belässt.
- **Impact:** Run wird als completed markiert, obwohl Clarification noch aussteht.

---

### BUG-15: `send_lifecycle` Lifecycle-Status für `clarification_waiting_response` ist falsch

- **Datei:** `backend/app/ws_handler.py` Zeile 230 + `backend/app/handlers/run_handlers.py` Zeilen 145–165
- **Schwere:** Niedrig
- **Root cause:** `lifecycle_status_from_stage("clarification_waiting_response")` → endet nicht auf `_received`, `_accepted`, `_started`, `_dispatched`, `_completed`, `_failed`, `_rejected`, `_cancelled`, `_timeout`. Es enthält `_response` — matcht auf nichts. Rückgabe: `None`. Der Status wird daher nicht gesetzt:
  ```python
  lifecycle_status = deps.lifecycle_status_from_stage(stage)
  if lifecycle_status is not None:  # None → übersprungen
      lifecycle_event["status"] = lifecycle_status
  ```
  Das bedeutet: Der Lifecycle-Event `clarification_waiting_response` hat keinen `status`/`run_status`-Key und ist für State-Tracking unsichtbar.
- **Impact:** Clarification-Wartezeit wird im Run-Status nicht reflektiert.

---

### BUG-16: `policy_decision` Handler nutzt Loop-generierte `request_id`, nicht die des Approvals

- **Datei:** `backend/app/ws_handler.py` Zeilen 670–700
- **Schwere:** Niedrig
- **Root cause:** Für `policy_decision`-Nachrichten wird keine `init_run` aufgerufen. Lifecycle-Events wie `policy_approval_decision_rejected` nutzen die am Loop-Start generierte `request_id` (Zeile 592), die keinem existierenden Run zugeordnet ist. Erst nach dem `deps.policy_approval_service.decide()`-Aufruf (Zeile 718) wird `target_request_id` auf Basis der Approval-Daten gesetzt (Zeile 741).
  ```python
  # Zeile 692-700 (vor decide())
  await send_lifecycle(
      stage="policy_approval_decision_rejected",
      request_id=request_id,       # ← Loop-request_id, kein existierender Run!
      session_id=session_id,
      details={"reason": "missing_approval_id"},
  )
  ```
- **Impact:** Lifecycle-Events referenzieren nicht-existente Run-IDs. Schwer zu corellieren.

---

### BUG-17: `run_agent_test` nutzt `KeyError` bei fehlendem `request.message`

- **Datei:** `backend/app/run_endpoints.py` Zeilen 56–67
- **Schwere:** Niedrig
- **Root cause:** `request.message or ""` wird verwendet. Wenn `request.message` ein leerer String ist, wird `content_len=0` korrekt gesetzt. Aber: `request.model or runtime_state.model` bei `init_run` bedeutet, dass ein explizites `model=""` den Default nutzt, statt einen leeren String als fehlerhafte Eingabe zu behandeln.
- **Impact:** Minimal — Edge-Case-Handling.

---

### BUG-18: Outer Exception Handler fängt Exceptions ohne `init_run` — `state_mark_failed_safe` auf nicht-existenten Run

- **Datei:** `backend/app/ws_handler.py` Zeilen 1226–1310
- **Schwere:** Niedrig
- **Root cause:** Der äußere Exception-Handler im Main-Loop fängt alle Exceptions inklusive derer, die **vor** `init_run` aufgeworfen werden (z.B. bei `peek_ws_inbound_type`, `parse_ws_inbound_message`, `sync_custom_agents`). In diesen Fällen:
  ```python
  except Exception as exc:
      deps.state_mark_failed_safe(run_id=request_id, error=str(exc))
  ```
  `request_id` wurde am Loop-Start generiert (Zeile 592), aber `init_run` wurde nie aufgerufen. `state_mark_failed_safe` versucht, einen nicht-existenten Run zu markieren. Die `_safe`-Variante fängt dies via try/except ab, aber es erzeugt unnötige Debug-Logs.
- **Impact:** Harmlos wegen `_safe`-Wrapper, aber verunreinigt Logs.

---

### BUG-19: `start_run` in `run_endpoints.py` validiert weder Message noch Model

- **Datei:** `backend/app/run_endpoints.py` Zeilen 161–176
- **Schwere:** Niedrig
- **Root cause:** `start_run` nimmt `request.message` ohne Validierung an und übergibt es direkt an `start_run_background`. Ein leerer Message-String oder `None` wird nicht abgefangen.
  ```python
  def start_run(request, deps):
      session_id = request.session_id or str(uuid.uuid4())
      run_id = deps.start_run_background(
          agent_id=None,
          message=request.message,   # ← keine Validierung
          ...
      )
  ```
- **Impact:** Leere Runs können gestartet werden.

---

### BUG-20: `api_subruns_kill` schreibt `visibility_decision` Event via `_enforce_subrun_visibility_or_403` — auch bei Kill-Failure

- **Datei:** `backend/app/subrun_endpoints.py` Zeilen 111–122 + 38–55
- **Schwere:** Niedrig
- **Root cause:** `_enforce_subrun_visibility_or_403` schreibt immer ein `visibility_decision`-Event per `state_append_event_safe`, auch wenn der nachfolgende `kill` fehlschlägt (404). Das Event suggeriert, dass eine Aktion durchgeführt wurde.
- **Impact:** Irreführende Events im State-Store.

---

## Zusammenfassung nach Schwere

| Schwere  | Bugs |
|----------|------|
| Kritisch | — |
| Hoch     | BUG-4, BUG-5, BUG-7, BUG-13, K3, K4 |
| Mittel   | BUG-1, BUG-10, BUG-12, BUG-14, BUG-9, K1, K2 |
| Niedrig  | BUG-2, BUG-3, BUG-6, BUG-8, BUG-11, BUG-15, BUG-16, BUG-17, BUG-18, BUG-19, BUG-20 |

## Priorisierte Fix-Reihenfolge

1. **BUG-5 + BUG-4:** Queue-Worker Disconnect-Handling: Fange `ClientDisconnectedError` in `drain_session_queue`, markiere verbleibende Queued-Runs als failed. Stelle sicher, dass `handle_request_failure` den State **vor** `send_event` setzt (für alle Exception-Typen).
2. **BUG-7:** Ersetze `active_event_agent_name` Closure-Variable durch einen Parameter an `send_lifecycle` bzw. einen Task-lokalen Context.
3. **BUG-13 + BUG-14:** Non-Queue-Pfad: Nutze `send_event_wrapped` statt `send_event` und füge Clarification-Detection hinzu.
4. **K3:** Session-Overrides: Tracke alle genutzten Session-IDs und räume alle im `finally`-Block auf.
5. **BUG-1:** `runtime_switch_request`: Füge `state_mark_completed_safe` nach `runtime_switch_done` hinzu.
6. **K2 + BUG-4:** `PolicyApprovalCancelledError`: Füge `state_mark_failed_safe` hinzu.
7. **K1:** Unsupported-Type-Pfad: Füge `state_mark_failed_safe` hinzu.
8. **BUG-12:** `kill_all_async`: Enforciere Visibility- oder Auth-Prüfung.
9. **BUG-10:** `subrun_spawn` Exception: Markiere nicht den Parent-Run als failed.
10. Restliche Low-Severity-Bugs nach Kapazität.
