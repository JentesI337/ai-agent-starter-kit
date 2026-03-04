# Reasoning Lifecycle Bug Audit (2026-03-04)

## Scope

Auditiert wurden die zentralen Lifecycle-Pfade:

- `backend/app/services/tool_execution_manager.py`
- `backend/app/ws_handler.py`
- `backend/app/orchestrator/pipeline_runner.py`
- `backend/app/orchestrator/fallback_state_machine.py`
- `backend/app/orchestrator/run_state_machine.py`
- `backend/app/services/policy_approval_service.py`

## Wichtiger Test-Hinweis

Gezielte Tests konnten in dieser Umgebung nicht laufen, weil die aktive Python-Version `3.14.0b3` mit `pydantic/fastapi` im Projekt nicht kompatibel ist (Collection bricht vor Testausführung ab).

## Gefundene Bugs (priorisiert)

### 1) Retrieval-Kontext wird stillschweigend überschrieben (kritisch)

**Root cause:** Nach erfolgreichem Retrieval wird `effective_memory_context` zunächst korrekt erweitert, später beim Skills-Inject jedoch auf `memory_context` zurückgesetzt.

**Evidenz:**

- Retrieval-Append: `backend/app/services/tool_execution_manager.py:402`
- Skills-Block startet: `backend/app/services/tool_execution_manager.py:404`
- Überschreiben statt Append: `backend/app/services/tool_execution_manager.py:424`

**Auswirkung:** Tool-Selektion arbeitet ohne Retrieval-Quellen, obwohl sie zuvor extrahiert wurden → schlechtere Entscheidungen / Halluzinationsrisiko.

---

### 2) Parallel-Read-Only-Mode umgeht Budget- und Loop-Gates (kritisch)

**Root cause:** Read-only Actions werden vor der normalen Schleife parallel via `asyncio.gather` ausgeführt. Budget-, Zeit- und Loop-Gatekeeper werden erst in der nachgelagerten sequenziellen Schleife geprüft.

**Evidenz:**

- Parallel-Read-Only-Partition: `backend/app/services/tool_execution_manager.py:1026`
- Ungebremstes `gather`: `backend/app/services/tool_execution_manager.py:1038`
- Gates greifen erst später: `backend/app/services/tool_execution_manager.py:1085`, `backend/app/services/tool_execution_manager.py:1102`, `backend/app/services/tool_execution_manager.py:1135`

**Auswirkung:** Cap- und Loop-Schutz kann für große Read-only-Batches wirkungslos werden; Lifecycle-Guardrails sind inkonsistent.

---

### 3) Steer-Interrupt wird im Parallel-Read-Only-Pfad nicht geprüft (hoch)

**Root cause:** `should_steer_interrupt()` wird nur in der sequenziellen Tool-Schleife geprüft, nicht im vorgezogenen Parallel-Block.

**Evidenz:**

- Steer-Checks nur hier: `backend/app/services/tool_execution_manager.py:1272`, `backend/app/services/tool_execution_manager.py:1484`
- Parallel-Block ohne Steer-Prüfung: `backend/app/services/tool_execution_manager.py:1026-1071`

**Auswirkung:** Neue User-Steuerung kann während parallel laufender Read-only-Tools verzögert oder ignoriert werden.

---

### 4) Falsche Agent-Attribution bei Queue-Worker-Lifecycle-Events (hoch)

**Root cause:** `execute_user_message_job()` resolved zwar den Agenten, setzt aber `active_event_agent_name` nicht. Die Lifecycle-Events nutzen dadurch den alten/globalen Agentnamen.

**Evidenz:**

- Worker-Job-Entry: `backend/app/ws_handler.py:350`
- Agent wird aufgelöst: `backend/app/ws_handler.py:383`
- `send_lifecycle` nutzt Closure-Variable: `backend/app/ws_handler.py:223`
- Korrekte Setzung existiert nur im anderen Pfad: `backend/app/ws_handler.py:969`

**Auswirkung:** Telemetrie/Tracing zeigt falschen ausführenden Agenten (Audit- und Debug-Fehler).

---

### 5) Session-Overrides werden am Ende nur für Connection-ID gelöscht (hoch)

**Root cause:** Cleanup nutzt `connection_session_id`, Requests können aber abweichende `data.session_id` verwenden.

**Evidenz:**

- Effektive Session kann clientseitig abweichen: `backend/app/ws_handler.py:672`
- Cleanup löscht nur Connection-ID: `backend/app/ws_handler.py:1351`
- Service arbeitet session-id-basiert: `backend/app/services/policy_approval_service.py` (`_session_allow_all` / `clear_session_overrides`)

**Auswirkung:** Session-scoped Policy-Approvals können über Verbindungen hinweg „kleben“ bleiben (Scope-Leak).

---

### 6) Unsupported-Type-Pfad hinterlässt aktive Runs ohne Terminal-Status (mittel)

**Root cause:** In diesem Pfad wird ein Run initialisiert und auf `active` gesetzt, danach bei `request_rejected_unsupported_type` nur geloggt und `continue` ausgeführt.

**Evidenz:**

- Run-Init: `backend/app/ws_handler.py:629`
- Task auf `active`: `backend/app/ws_handler.py:637`
- Rejection-Lifecycle: `backend/app/ws_handler.py:663`

**Auswirkung:** State-Store enthält hängende Runs (weder completed noch failed/cancelled), verfälscht Monitoring.

---

### 7) `request_cancelled` setzt keinen Terminal-State im Run (mittel)

**Root cause:** Bei `PolicyApprovalCancelledError` wird Lifecycle `request_cancelled` emittiert, aber kein `state_mark_failed_safe`/`state_mark_completed_safe` aufgerufen.

**Evidenz:**

- Cancellation-Branch: `backend/app/ws_handler.py:243-257`
- Keine State-Markierung im Branch (im Gegensatz zu Guardrail/Tool/LLM-Branches direkt darunter)
- Gleiches Muster im Outer-Loop: `backend/app/ws_handler.py:1240`

**Auswirkung:** Runs bleiben bei Cancel im Status `active` statt terminal, wodurch Queue-/Run-Status inkonsistent wird.

---

## Priorisierte Fix-Reihenfolge

1. Bug 1 (Kontextverlust) und Bug 2 (Gate-Bypass) sofort beheben.
2. Bug 4 und 5 (Attribution + Session-Leak) für korrekte Governance/Observability.
3. Bug 6 und 7 (hängende Runs) für sauberen Run-State-Lifecycle.
4. Anschließend Test-Umgebung auf unterstützte Python-Version (z. B. 3.11/3.12) stabilisieren und Regression-Tests ergänzen.
