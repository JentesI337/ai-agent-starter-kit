# Bugfix-Plan: `spawn_subrun` / `tool_policy` Pipeline-Failure

**Datum:** 2026-03-05  
**Severity:** CRITICAL – Orchestrierung schlägt stumm fehl, Subrun liefert kein Ergebnis  
**Betroffene Dateien:**
- `backend/app/services/tool_registry.py`
- `backend/app/services/tool_arg_validator.py`
- `backend/app/services/tool_execution_manager.py`
- `backend/app/agent.py`

---

## Root-Cause-Analyse

### Fehler 1 – Unvollständiges JSON-Schema für `tool_policy` (PRIMARY BUG)

**Datei:** `backend/app/services/tool_registry.py` → Zeile 523

```python
# IST (kaputt):
"tool_policy": {"type": "object"},

# SOLL:
"tool_policy": {
    "type": "object",
    "properties": {
        "allow": {"type": "array", "items": {"type": "string"}},
        "deny":  {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
},
```

Das LLM sieht `{"type": "object"}` ohne `properties`. Es errät einen String
(`"default"`) oder Array — beides ist kein `dict` → `tool_arg_validator.py`
blockiert hart mit `"argument 'tool_policy' must be an object"`.

---

### Fehler 2 – Kein Coercion bei ungültigem `tool_policy`-Typ

**Datei:** `backend/app/services/tool_arg_validator.py` → Zeile 396–398

```python
# IST:
if tool_policy is not None:
    if not isinstance(tool_policy, dict):
        return "argument 'tool_policy' must be an object"   # → hard block
```

Wenn der LLM einen String liefert, wird der gesamte Tool-Call geblockt, anstatt
`tool_policy=None` zu setzen und weiterzumachen. Stille Degradation wäre hier
besser als totaler Block.

---

### Fehler 3 – Tool-Selector-Prompt gibt kein `tool_policy`-Schema

**Datei:** `backend/app/services/tool_execution_manager.py` → `build_tool_selector_prompt()` → Zeile ~757

```python
# IST:
"- spawn_subrun: message, optional mode(run|session), optional agent_id, "
"optional model, optional timeout_seconds, optional tool_policy\n"

# Kein einziges Beispiel für das Format von tool_policy
```

Das LLM weiß nicht, dass `tool_policy` die Struktur
`{"allow": ["tool_name"], "deny": ["tool_name"]}` haben muss.

---

### Fehler 4 – `tool_blocked`-Event gibt kein korrigierendes Feedback

**Datei:** `backend/app/services/tool_execution_manager.py` → `run_tool_loop()` → Zeile ~1225

```python
# IST:
if prep.error:
    results.append(f"[{tool}] REJECTED: {prep.error}")
    await send_event({"type": "error", "message": f"Tool blocked ({tool}): {prep.error}"})
    await emit_lifecycle("tool_blocked", {"tool": tool, "error": prep.error})
    continue   # ← LLM plant neu, kennt aber nicht die korrekte Struktur
```

Das LLM bekommt nur `"argument 'tool_policy' must be an object"` — kein Beispiel,
kein Hint, wie es das korrigieren soll. Der zweite Plan lässt `tool_policy`
komplett weg, was zwar zum Tool-Call führt, aber ohne Delegation-Kontext.

---

### Fehler 5 – Subrun-Kontrakt-Fehler wird nicht an Parent propagiert

**Datei:** `backend/app/agent.py` → `_invoke_spawn_subrun_tool()` → Zeile ~2655

```python
# Aus dem Trace (Lifecycle-Event aus dem Bug):
synthesis_contract_check_completed:
  task_type: "general"
  valid: false
  correction_applied: true
  failure_count_before: 3
  failure_count_after: 3
```

Der Parent-Agent akzeptiert `spawned_subrun_id=... mode=run` als vollen Erfolg,
obwohl das Kind `valid: false` hatte und 3 Kontrakt-Korrekturen scheiterten.
`handover_contract` enthält nur `terminal_reason / confidence / result`, aber
keinen `synthesis_valid`-Flag.

---

### Fehler 6 – Orchestrierungskontext nicht an Subrun vererbt

**Datei:** `backend/app/agent.py` → `_invoke_spawn_subrun_tool()` → Zeile ~2617

Der Subrun erhält `task_type: "general"` statt `task_type: "orchestration_pending"`.
Dadurch plant das Kind das gesamte Ziel erneut statt einen delegierten Teilauftrag
auszuführen — Double-Planning-Anti-Pattern.

---

## Fix-Plan (priorisiert)

---

### Fix 1 (KRITISCH) – Schema in `tool_registry.py` vervollständigen

**Datei:** `backend/app/services/tool_registry.py` → ca. Zeile 519–523

**Änderung:**
```python
"tool_policy": {
    "type": "object",
    "description": "Restrict or expand tools available to the spawned subrun. "
                   "Use 'allow' to whitelist, 'deny' to blacklist tool names.",
    "properties": {
        "allow": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tool names the subrun is allowed to use.",
        },
        "deny": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tool names the subrun must not use.",
        },
    },
    "additionalProperties": False,
},
```

**Akzeptanzkriterien:**
- [ ] Function-calling-fähige Modelle erhalten das vollständige Schema über `build_function_calling_tools()`
- [ ] Kein Modell kann `tool_policy` als String oder Array on top-level anlegen; JSON-Schema-Validation schlägt sofort fehl
- [ ] Bestehende Unit-Tests in `tests/` für `tool_registry` laufen grün

---

### Fix 2 (KRITISCH) – Coercion statt Hard-Block in `tool_arg_validator.py`

**Datei:** `backend/app/services/tool_arg_validator.py` → `_validate_spawn_subrun_args()` → Zeile 396

**Änderung:**
```python
tool_policy = normalized_args.get("tool_policy")
if tool_policy is not None:
    if not isinstance(tool_policy, dict):
        # Coerce statt hard-block: ungültige Typen werden ignoriert, Tool-Call läuft durch
        normalized_args["tool_policy"] = None
    else:
        # ... (restliche Validierung bleibt unverändert)
```

**Alternative (strenger):** Fehler zurückgeben, aber im `run_tool_loop` als
`warning` weitergeben statt als `block`.

**Akzeptanzkriterien:**
- [ ] Übergibt LLM `tool_policy: "default"`, wird der Call trotzdem ausgeführt (ohne Policy)
- [ ] Übergibt LLM `tool_policy: {"allow": ["web_fetch"]}`, wird es korrekt angewendet
- [ ] Test: `test_validate_spawn_subrun_args_invalid_policy_type` → kein Fehler, `tool_policy=None`

---

### Fix 3 (HOCH) – Tool-Selector-Prompt um `tool_policy`-Beispiel erweitern

**Datei:** `backend/app/services/tool_execution_manager.py` → `build_tool_selector_prompt()` → `instructions`-String

**Änderung:**
```python
"- spawn_subrun: message, optional mode(run|session), optional agent_id, "
"optional model, optional timeout_seconds, "
"optional tool_policy={\"allow\":[\"tool_name\"],\"deny\":[\"tool_name\"]}\n"
```

**Akzeptanzkriterien:**
- [ ] Prompt-Snapshot-Tests reflektieren das neue Format
- [ ] Manuelle Verifikation: LLM-Ausgabe für Orchestrierungsaufgaben enthält `tool_policy` als Objekt, nicht als String

---

### Fix 4 (HOCH) – Korrigierendes Feedback bei `tool_blocked` einschleusen

**Datei:** `backend/app/services/tool_execution_manager.py` → `run_tool_loop()` → nach `emit_lifecycle("tool_blocked", ...)`

**Änderung:**
```python
if prep.error:
    results.append(f"[{tool}] REJECTED: {prep.error}")
    
    # Korrigierendes Feedback anstatt nur Fehlerstring
    correction_hint = _build_tool_correction_hint(tool, prep.error)
    await send_event({
        "type": "error",
        "agent": agent_name,
        "message": f"Tool blocked ({tool}): {prep.error}",
        "correction_hint": correction_hint,   # NEU
    })
    await emit_lifecycle(
        "tool_blocked",
        {"tool": tool, "index": idx, "call_id": call_id,
         "error": prep.error, "correction_hint": correction_hint},  # NEU
    )
    continue
```

```python
# Neue Hilfsfunktion (gleiche Datei oder helpers.py):
def _build_tool_correction_hint(tool: str, error: str) -> str | None:
    if tool == "spawn_subrun" and "tool_policy" in error:
        return (
            'tool_policy must be a JSON object, e.g. '
            '{"allow": ["web_fetch", "read_file"], "deny": ["run_command"]}'
        )
    return None
```

**Akzeptanzkriterien:**
- [ ] `correction_hint` erscheint im `tool_blocked`-Lifecycle-Event
- [ ] Frontend zeigt `correction_hint` an (falls vorhanden) unterhalb der Fehlermeldung
- [ ] Folge-LLM-Plan nutzt das enthaltene Beispiel zur Selbstkorrektur — Test mit Mock-LLM

---

### Fix 5 (MITTEL) – Subrun-Kontrakt-Status an Parent propagieren

**Datei:** `backend/app/agent.py` → `_invoke_spawn_subrun_tool()` → `handover_contract`-Aufbau → Zeile ~2660

**Änderung — `spawn_result` muss `synthesis_valid` kennen:**
```python
handover_contract: dict = {
    "terminal_reason": "subrun-accepted",
    "confidence": 0.0,
    "result": None,
    "synthesis_valid": None,   # NEU: wird aus spawn_result befüllt
}

# ... und beim Auslesen von spawn_result:
if isinstance(spawn_result, dict):
    synthesis_valid = spawn_result.get("synthesis_valid")
    if synthesis_valid is not None:
        handover_contract["synthesis_valid"] = bool(synthesis_valid)
```

**Datei:** Subrun-Completion-Handler (ws_handler.py oder runtime_manager.py) muss
`synthesis_valid` in das `spawn_result`-Dict schreiben, wenn der Subrun
abgeschlossen ist.

**Akzeptanzkriterien:**
- [ ] `handover_contract.synthesis_valid` ist `false`, wenn Subrun `synthesis_contract_check_completed valid: false` emittiert
- [ ] Parent-Agent emittiert `subrun_quality_warning`, wenn `synthesis_valid=false`
- [ ] Parent-Antwort enthält einen "caveat"-Hinweis, wenn Subrun-Kontrakt fehlgeschlagen ist; kein stilles Erfolg-Reporting

---

### Fix 6 (MITTEL) – Orchestrierungskontext an Subrun übergeben

**Datei:** `backend/app/agent.py` → `_invoke_spawn_subrun_tool()` → `spawn_result`-Aufbau

**Änderung:**
```python
# Wenn der Parent task_type == "orchestration_pending" hat und
# dieser Subrun ein Delegations-Task ist:
spawn_result = await self._spawn_subrun_handler(
    ...
    orchestration_context={           # NEU
        "parent_task_type": self._current_task_type,
        "delegated_task": True,
        "delegation_scope": delegation_scope,
    },
)
```

Der Subrun-Handler muss `orchestration_context` empfangen und als `task_type` im
Kind-Agent setzen, damit der Subrun keinen eigenen Planning-Cycle startet.

**Akzeptanzkriterien:**
- [ ] Lifecycle-Event `queued` im Subrun enthält `task_type: "delegated_task"` statt `"general"`
- [ ] `synthesis_contract_check_started` im Subrun emittiert `required_sections` passend für delegierte Tasks (nicht für orchestration_pending)
- [ ] Kein Double-Planning: Subrun verschickt keinen `planning_started`-Event für das Gesamtziel

---

## Dos & Don'ts

### ✅ DOs

- **Schema zuerst.** Jedes neue optionale Argument in einem `ToolSpec.parameters`-Dict muss
  vollständig typisiert sein (`type`, `properties`, `items`, `description`). Nie nur `{"type": "object"}`.

- **Coerce statt Block bei optionalen Parametern.** Wenn ein optionales Argument ungültig ist
  und die Kernfunktionalität des Tools nicht davon abhängt, auf `None` zurückfallen statt den
  kompletten Tool-Call abzublocken.

- **Korrekturhinweise embedded in Tool-Errors.** Wenn ein Validation-Error bei `prep.error`
  entsteht, muss ein maschinenlesbarer `correction_hint` mitgesendet werden, der das korrekte
  Format beschreibt. Platte Fehlermeldungen geben dem LLM zu wenig Signal.

- **Subrun-Qualität ist eine Observable.** Jeder Subrun-Abschluss muss seinen
  `synthesis_valid`-Status nach oben propagieren. Der Parent darf nicht blind `completed`
  als Erfolg werten.

- **Delegation-Context explizit übergeben.** Ein via `spawn_subrun` gestarteter delegierter
  Task muss wissen, dass er ein Teilauftrag ist (`task_type: "delegated_task"`). Das verhindert
  erneutes Full-Planning.

- **Prompts und Schemas synchron halten.** Wenn sich `ToolSpec.parameters` ändert, muss sich
  der entsprechende Prompt-Hint in `build_tool_selector_prompt()` synchron mitändern.
  Idealerweise wird der Hint aus dem Schema generiert, nicht manuell gepflegt.

---

### ❌ DON'Ts

- **NIEMALS ein `{"type": "object"}` ohne `properties` in einem Tool-Schema lassen.**
  Das LLM kann nicht erraten, welche Keys erwartet werden.

- **NIEMALS einen Tool-Block ohne strukturiertes Feedback abschließen.**
  `results.append(f"[{tool}] REJECTED: {prep.error}")` allein reicht nicht. Das LLM sieht
  diesen String in der nächsten Runde und hat keinen Hinweis, wie es sich korrigieren soll.

- **NIEMALS `synthesis_valid: false` eines Subruns im Parent-Agent ignorieren.**
  Das führt zu halbtoten Orchestrations-Flows, bei denen der User denkt, alles sei erledigt,
  aber nichts passiert ist.

- **NIEMALS einen Subrun spawnen, ohne `delegation_scope` und `task_type` zu übergeben,**
  wenn es sich um eine echte Orchestrierungs-Delegation handelt (nicht um eine standalone-Query).

- **NIEMALS Manual-Sync zwischen `ToolSpec.parameters` und `build_tool_selector_prompt()`.**
  Das führt langfristig unweigerlich zu Drift. Prompt soll Schema-Hints aus dem ToolSpec ableiten.

- **NIEMALS einen `tool_blocked continue` ohne Prüfung des Retry-Kontexts.**
  Wenn das gleiche Tool mit dem gleichen fehlerhaften Argument im nächsten Zyklus wieder auftaucht,
  sollte eine `loop_gatekeeper`-Signatur das erkennen und den Circuit-Breaker auslösen.

---

## Akzeptanzkriterien (Gesamt-Flow)

| # | Kriterium | Prüfmethode |
|---|-----------|-------------|
| A1 | LLM übergibt `tool_policy: "default"` → Tool-Call wird trotzdem ausgeführt (ohne Policy) | Unit-Test `test_spawn_subrun_invalid_policy_coerced` |
| A2 | LLM übergibt `tool_policy: {"allow": ["web_fetch"]}` → Subrun erhält eingeschränkte Policy | Integration-Test (Mock-Subrun-Handler) |
| A3 | `tool_blocked`-Event enthält `correction_hint` mit Schema-Beispiel wenn `tool_policy` falsch | Unit-Test + Lifecycle-Snapshot |
| A4 | Subrun mit `synthesis_valid: false` → Parent emittiert `subrun_quality_warning` | Lifecycle-Event-Trace-Test |
| A5 | Parent-Antwort im Orchestrierungsfall enthält "caveat"-Sektion wenn Subrun-Kontrakt fehlschlug | Synthesis-Contract-Test |
| A6 | Erneuter Flow "orchestrate app development" → `spawn_subrun` wird **beim ersten Versuch** ausgeführt, kein `tool_blocked` | End-to-End-Benchmark-Scenario |
| A7 | Spawned Subrun enthält `task_type: "delegated_task"` in Lifecycle-Events, kein zweites Full-Planning | Lifecycle-Trace-Verifikation |
| A8 | Function-Calling-Schema für `spawn_subrun` enthält vollständige `tool_policy`-Struktur | JSON-Schema-Validation-Test |
| A9 | Alle bestehenden Tests in `backend/tests/` laufen weiterhin grün | `pytest -q` Exit Code 0 |
| A10 | Keine neuen Pylint/Mypy-Fehler durch die Änderungen | CI-Check |

---

## Dateien & Zeilen (Zusammenfassung)

| Datei | Zeile(n) | Änderung |
|-------|----------|----------|
| `backend/app/services/tool_registry.py` | 519–523 | `tool_policy`-Schema vervollständigen |
| `backend/app/services/tool_arg_validator.py` | 396–398 | Coercion statt Hard-Block |
| `backend/app/services/tool_execution_manager.py` | ~757 (Prompt) | `tool_policy`-Beispiel in Hint |
| `backend/app/services/tool_execution_manager.py` | ~1220 (run_tool_loop) | `correction_hint` in `tool_blocked` |
| `backend/app/agent.py` | ~2650 (handover_contract) | `synthesis_valid` propagieren |
| `backend/app/agent.py` | ~2639 (spawn_subrun_handler Aufruf) | `orchestration_context` übergeben |
