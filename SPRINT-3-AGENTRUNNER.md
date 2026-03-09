# Sprint 3 — Phase D: Integration & Cutover

## Kontext

- **Sprint 1** (Phase A+B): AgentRunner Grundgerüst + Streaming Tool Loop — 53 Tests ✅
- **Sprint 2** (Phase C): Guards & Safety migriert — Evidence Gates, Reflection, Reply Shaping, Verification — 28 Tests ✅
- **Sprint 3** (Phase D): Integration & Cutover — diesen Sprint

## Ziel

Den neuen AgentRunner nahtlos in die bestehende Infrastruktur integrieren, sodass
bei `USE_CONTINUOUS_LOOP=true` der komplette Request-Pfad korrekt funktioniert:
WebSocket → HeadAgent.run() → AgentRunner.run() → Events → Frontend.

---

## Tickets

### S3-01: Token-Event-Kompatibilität (Backend)

**Problem:** AgentRunner emittiert `{"type": "stream", "content": chunk}`, aber das
Frontend erwartet `{"type": "token", "token": chunk}` (wie `synthesizer_agent.py`).

**Änderung:** In `agent_runner.py` alle 3 `on_text_chunk`-Lambdas ändern:
```python
# ALT:
on_text_chunk=lambda chunk: send_event({"type": "stream", "content": chunk})
# NEU:
on_text_chunk=lambda chunk: send_event({"type": "token", "token": chunk})
```

**Dateien:** `backend/app/agent_runner.py`

---

### S3-02: Agent-Name in Events

**Problem:** Legacy-Events enthalten `"agent": self.name` (z.B. `"agent": "head-agent"`).
AgentRunner-Events fehlt dieses Feld. Frontend-Monitoring zählt Events nach agent-Name.

**Änderung:** AgentRunner bekommt `agent_name: str` als Constructor-Parameter.
Alle `send_event`-Aufrufe in `agent_runner.py` erhalten `"agent": self._agent_name`.
HeadAgent übergibt `agent_name=self.name` beim Konstruktor-Aufruf.

**Dateien:** `backend/app/agent_runner.py`, `backend/app/agent.py`

---

### S3-03: Lifecycle-Kompatibilität Pre-Loop

**Problem:** Legacy-Pipeline emittiert granulare Pre-Loop-Events die das Debug-Dashboard braucht:
`guardrail_check_completed`, `guardrails_passed`, `tool_policy_resolved`, `toolchain_checked`,
`memory_updated`, `context_reduced`. AgentRunner emittiert nur `runner_started`.

**Änderung:** Im AgentRunner Pre-Loop-Abschnitt von `run()` nach den bestehenden
Guardrail/MCP/Memory-Aufrufen Lifecycle-Events emittieren — analog zur Legacy-Pipeline.
Mindestens: `guardrails_passed`, `memory_updated` nach den jeweiligen Schritten.

**Dateien:** `backend/app/agent_runner.py`

---

### S3-04: Session Distillation im neuen Pfad

**Problem:** Legacy-Pipeline startet nach erfolgreichem Run eine Background-Distillation
(`_distill_session_knowledge`) für Long-Term Memory. Der AgentRunner-Pfad hat das nicht.

**Änderung:** AgentRunner bekommt optional einen `distill_fn: Callable | None` Parameter.
HeadAgent übergibt `distill_fn=self._distill_session_knowledge`. Im AgentRunner
wird nach dem `runner_completed` Event die Distillation als Fire-and-Forget gestartet
(identisch zum Legacy-Pattern mit `asyncio.create_task`).

**Dateien:** `backend/app/agent_runner.py`, `backend/app/agent.py`

---

### S3-05: Hook-Integration

**Problem:** Legacy-Pipeline ruft `_invoke_hooks("agent_end", ...)` nach jedem Run auf.
Der AgentRunner-Pfad in `HeadAgent.run()` macht das nicht.

**Änderung:** In `HeadAgent.run()` den AgentRunner-Branch um einen `finally`-Block
erweitern der `_invoke_hooks("agent_end", ...)` aufruft — analog zum Legacy-Pfad.

**Dateien:** `backend/app/agent.py`

---

### S3-06: Long-Term Memory Context

**Problem:** Legacy-Pipeline baut LTM-Context (`_build_long_term_memory_context`) in den
System-Prompt ein. AgentRunner nutzt das nur beim Konstruieren des `system_prompt` (einmalig
in `_build_sub_agents`), aber LTM-Context ändert sich zur Laufzeit.

**Änderung:** AgentRunner bekommt einen optionalen `long_term_context_fn: Callable[[str], str] | None`
Parameter. Im `_build_initial_messages` wird der LTM-Context zum System-Prompt hinzugefügt,
wenn die Funktion vorhanden ist.

**Dateien:** `backend/app/agent_runner.py`, `backend/app/agent.py`

---

### S3-07: Failure-Logging bei Fehlern

**Problem:** Legacy-Pipeline loggt Failures ins Long-Term Memory (`_long_term_memory.add_failure()`)
bei Exceptions. Der AgentRunner-Pfad in `HeadAgent.run()` hat keinen Exception-Handler dafür.

**Änderung:** In `HeadAgent.run()` den AgentRunner-Branch um Exception-Handling erweitern:
bei Exception → `_long_term_memory.add_failure(FailureEntry(...))` + `_emit_lifecycle(run_error)`.

**Dateien:** `backend/app/agent.py`

---

### S3-08: ContextVar-Propagation

**Problem:** Legacy-Pipeline setzt ContextVars für `request_id`, `session_id`, `send_event`
via `_active_*_context.set(...)`. Der Runner-Branch setzt diese nicht — dadurch können
nested tool calls die ContextVars nicht lesen.

**Änderung:** Im AgentRunner-Branch von `HeadAgent.run()` die 3 ContextVars setzen
(analog zum Legacy-Pfad) und im finally-Block zurücksetzen.

**Dateien:** `backend/app/agent.py`

---

### S3-09: configure_runtime Vollständigkeit

**Problem:** `configure_runtime()` propagiert nur `client` und `_reflection_service`
an den AgentRunner. Fehlend: `system_prompt` (bei Model-Wechsel kann sich der Prompt
nicht anpassen) und andere Services die neu instanziiert werden.

**Änderung:** In `configure_runtime()` auch `system_prompt` (via `build_unified_system_prompt`)
an den AgentRunner propagieren, wenn der Prompt model-abhängig ist.

**Dateien:** `backend/app/agent.py`

---

### S3-10: Unit Tests Token-Events

**Ziel:** Verifizieren dass `on_text_chunk` das korrekte `{"type": "token", "token": ...}`
Format emittiert.

**Tests:** ≥4 Tests — Token-Format korrekt, Agent-Name in Events, Final-Event hat Agent-Name.

**Dateien:** `backend/tests/test_agent_runner_integration_events.py`

---

### S3-11: Unit Tests Distillation + Hooks + LTM

**Ziel:** Verifizieren dass distill_fn aufgerufen wird, Hooks feuern,
LTM-Context in Messages eingebaut wird.

**Tests:** ≥6 Tests — Distill bei Erfolg, Distill nicht bei Fehler,
LTM-Context in System-Prompt, Hook-Aufruf, ContextVar-Propagation.

**Dateien:** `backend/tests/test_agent_runner_integration_events.py`

---

### S3-12: Integration-Tests Feature-Flag-Toggle

**Ziel:** Sicherstellen dass `USE_CONTINUOUS_LOOP=true/false` korrekt zwischen
Legacy und neuem Pfad wechselt und beide Pfade die gleichen Events emittieren.

**Tests:** ≥4 Tests — Flag true → Runner, Flag false → Legacy,
configure_runtime propagiert korrekt, Error-Handling im Runner-Pfad.

**Dateien:** `backend/tests/test_agent_runner_integration_events.py`

---

## Abnahmekriterien

1. Alle Sprint-3-Tests grün (≥14 neue Tests)
2. Alle Sprint-1/2-Tests grün (81 bestehende)
3. Regressions-Suite grün (≥1490 Tests, exkl. Browser-Tests)
4. `python -c "from app.agent_runner import AgentRunner; print('OK')"` → OK
5. Bei `USE_CONTINUOUS_LOOP=true` emittiert der Runner dieselben Event-Typen
   (`token`, `final`, `lifecycle`) wie die Legacy-Pipeline
