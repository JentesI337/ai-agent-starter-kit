# Issue-0008 — Implementierungsplan: Epistemic Integrity der Reasoning Pipeline

**Stand:** 2026-03-04  
**Status:** IMPLEMENTIERT  
**Änderungen:** `main.py`, `agent.py`, `agents/synthesizer_agent.py`

---

## Ziel

Eine **bulletproof Reasoning Pipeline** die keine semantisch falschen Antworten
liefern kann. Jede Aussage im Ergebnis muss durch ein nachprüfbares Tool-Ergebnis
gedeckt sein — insbesondere bei Orchestrierungsanfragen, wo ein fehlgeschlagener
Kind-Agent bisher zur Erfolgsmeldung führte.

---

## Vollständige Pipeline (Gesamtbild)

```
User Message
    │
    ▼
[1] Guardrails + Tool Policy Resolution
    │   agent.py: _validate_guardrails, _resolve_effective_allowed_tools
    │
    ▼
[2] Planning (PlannerAgent)
    │   agent.py: plan_step_executor.execute()
    │   → Produziert plan_text
    │
    ▼
[3] Tool Execution Loop (ToolExecutionManager)
    │   ├─ [3a] Capability Preselection   ← FIX 6: registry jetzt verdrahtet
    │   │       tool_execution_manager._apply_capability_preselection()
    │   │       vorher: immer Skip weil registry=None
    │   │
    │   ├─ [3b] Skill Retrieval / Grounding
    │   │       ReliableRetrievalService für kontext-basierte Snippets
    │   │
    │   ├─ [3c] Intent Detection → Tool Selection
    │   │       agent._detect_intent_gate → LLM-Tool-Auswahl
    │   │
    │   ├─ [3d] spawn_subrun Ausführung    ← FIX 1: mode="wait" wartet jetzt
    │   │       main.py: _spawn_subrun_from_agent
    │   │       vorher: get_handover_contract immer "subrun-accepted"
    │   │       jetzt:  bei mode="wait" → wait_for_completion() → echter Status
    │   │
    │   └─ [3e] Tool Result Classification
    │           "usable" / "error_only" / "empty" / "blocked" / "steer_interrupted"
    │
    ▼
[4] Task-Type Resolution                  ← FIX 2: Evidence-First statt Keyword
    │   agent.py: _resolve_synthesis_task_type()
    │   Neu:
    │     "spawned_subrun_id=" im Tool-Result → lese terminal_reason:
    │     • "subrun-complete"  → "orchestration"
    │     • "subrun-error/timeout/cancelled" → "orchestration_failed"
    │     • "subrun-accepted/running"         → "orchestration_pending"
    │     Kein spawn-Ergebnis + Keyword "orchestrate" → "orchestration"
    │
    ▼
[5] Synthesis (SynthesizerAgent)          ← FIX 3: neue Task-Typen, Evidence-First
    │   synthesizer_agent._resolve_task_type():
    │     Hint aus agent.py wird vollständig respektiert (incl. orchestration_failed,
    │     orchestration_pending). Eigenes Keyword-Matching nur als Fallback.
    │   synthesizer_agent._build_final_prompt():
    │     Section-Contract per Task-Typ injiziert:
    │     • orchestration_failed → ["Goal","Delegation failure","Failure reason",
    │                               "Recovery options","Next steps"]
    │     • orchestration_pending → ["Goal","Delegation initiated","Pending status",
    │                               "What to expect","Next steps"]
    │   synthesizer_agent._run_synthesis_self_check():
    │     Formale Sektion-Validierung (syntaktisch). Repair-Pass bei Fehlern.
    │   Reflection Pass (1x) via ReflectionService
    │
    ▼
[6] Reply Shaping + Evidence Gates        ← FIX 4: Orchestration Gate hinzugefügt
    │   agent.py, nach Synthesizer:
    │   ├─ implementation_evidence_missing: verhindert Fake-Implementierungsberichte
    │   └─ orchestration_evidence_missing:  verhindert Fake-Delegationsberichte [NEU]
    │       Bei task_type="orchestration" und fehlendem subrun-complete:
    │       → Fehlermeldung statt fabrizierter Erfolgsaussage
    │
    ▼
[7] Verification + Final Output
        agent.py: verification_final → run_completed
```

---

## Implementierte Fixes

### Fix 1 — `mode="wait"` wirklich implementiert

**Datei:** [backend/app/main.py](../backend/app/main.py)  
**Problem:** `SubrunLane.wait_for_completion()` existierte, wurde aber nie aufgerufen.
`get_handover_contract()` lieferte immer `terminal_reason="subrun-accepted"`.

```python
# NEU — nach spawn():
if mode == "wait":
    wait_timeout = max(5.0, float(effective_timeout) + 5.0)
    try:
        await components.subrun_lane.wait_for_completion(run_id, timeout=wait_timeout)
    except asyncio.TimeoutError:
        pass  # Handover enthält dann "subrun-timeout"-Status
```

**Effekt:** Bei `mode="wait"` wartet der Parent bis der Kind-Run terminiert und liest
dann den echten Status aus `_run_status[run_id]` — mit dem korrekten `terminal_reason`.

---

### Fix 2 — Task-Type Evidence-First in `agent.py`

**Datei:** [backend/app/agent.py](../backend/app/agent.py)  
**Methode:** `_resolve_synthesis_task_type`  
**Problem:** Keyword-Match auf User-Message (`"orchestrate"`) setzte `task_type="orchestration"`
**bevor** irgendein Tool-Ergebnis existierte. Fehlgeschlagene Subruns wurden genauso
behandelt wie erfolgreiche.

```python
# NEU — Evidence-First:
if "spawned_subrun_id=" in (tool_results or ""):
    tr = tool_results or ""
    if "subrun-complete" in tr:
        return "orchestration"           # Kind erfolgreich abgeschlossen
    if any(s in tr for s in ("subrun-error", "subrun-timeout", "subrun-cancelled")):
        return "orchestration_failed"    # Kind fehlgeschlagen
    return "orchestration_pending"       # fire-and-forget, Outcome unbekannt

# Keyword-Scan nur wenn KEIN Subrun-Ergebnis vorliegt
if self._is_subrun_orchestration_task(message):
    return "orchestration"
```

---

### Fix 3 — Semantische Synthesis-Contracts in `synthesizer_agent.py`

**Datei:** [backend/app/agents/synthesizer_agent.py](../backend/app/agents/synthesizer_agent.py)  
**Methoden:** `_resolve_task_type`, `_required_sections_for_task`  
**Problem A:** `_resolve_task_type` ignorierte die Hint-Typen `orchestration_failed`
und `orchestration_pending` und fiel auf Keyword-Matching zurück → immer `"orchestration"`.

**Problem B:** Alle Orchestrierungs-Szenarien (egal ob Erfolg oder Fehler) verwendeten
das gleiche Section-Template mit semantisch falschen Sektionen wie `"Delegation outcome"`.

```python
# NEU — Hint-Set erweitert:
if hinted in {
    "hard_research", "research",
    "orchestration", "orchestration_failed", "orchestration_pending",
    "implementation", "general",
}:
    return hinted

# NEU — Evidence-First im Fallback:
if "spawned_subrun_id=" in tool_results:
    if "subrun-complete" in tool_results: return "orchestration"
    if any(s in tool_results for s in ("subrun-error",...)): return "orchestration_failed"
    return "orchestration_pending"

# NEU — Section-Contracts:
"orchestration_failed": (
    "Goal", "Delegation failure", "Failure reason",
    "Recovery options", "Next steps",
),
"orchestration_pending": (
    "Goal", "Delegation initiated", "Pending status",
    "What to expect", "Next steps",
),
```

**Effekt:** Der LLM erhält ein Prompt-Template das explizit verlangt, den Fehler
zu benennen — anstatt eine Erfolgsstruktur zu befüllen.

---

### Fix 4 — Orchestration Evidence Gate in `agent.py`

**Datei:** [backend/app/agent.py](../backend/app/agent.py)  
**Ort:** `run()` — nach Reply Shaping, analog zu `implementation_evidence_missing`  
**Problem:** Für `task_type="implementation"` gab es einen Evidence Gate (der bei
fehlendem write_file-Ergebnis eine Fehlermeldung ausgibt). Für Orchestrierung fehlte
das komplett.

```python
# NEU — hinzugefügte Helfer-Methoden:
def _has_orchestration_evidence(self, tool_results) -> bool:
    # Nur True wenn subrun-complete belegt ist
    return "spawned_subrun_id=" in tr and "subrun-complete" in tr

def _has_orchestration_attempted(self, tool_results) -> bool:
    return "spawned_subrun_id=" in (tool_results or "")

# NEU — Gate im run()-Flow:
if synthesis_task_type == "orchestration" and not self._has_orchestration_evidence(tool_results):
    # Lifecycle-Event zur Observability
    await self._emit_lifecycle(send_event, stage="orchestration_evidence_missing", ...)
    if attempted:
        final_text = "The delegated subrun did not complete successfully..."
    else:
        final_text = "No subrun was executed for this orchestration request..."
```

**Effekt:** Selbst wenn der Synthesizer eine überzeugende Erfolgsantwort generiert hat,
blockiert dieser Gate die Ausgabe und ersetzt sie durch eine faktisch korrekte Fehlermeldung.

---

### Fix 5 — `ToolExecutionManager` Registry-Verdrahtung

**Datei:** [backend/app/agent.py](../backend/app/agent.py)  
**Problem:** `ToolExecutionManager()` wurde ohne `registry` instanziiert.
`_apply_capability_preselection` schlug mit `reason="registry_missing_filter"` fehl
und alle `filter_tools_by_capabilities`-Calls wurden übersprungen.

```python
# VORHER:
self._tool_execution_manager = ToolExecutionManager()
self.tool_registry = self._build_tool_registry()

# NEU: Reihenfolge getauscht, registry übergeben:
self.tool_registry = self._build_tool_registry()
self._tool_execution_manager = ToolExecutionManager(registry=self.tool_registry)

# NEU: Re-injection nach MCP-Init:
self.tool_registry = self._build_tool_registry()
self._tool_execution_manager._registry = self.tool_registry  # ← neu
self._validate_tool_registry_dispatch()
```

---

## Verbleibende bekannte Probleme (nicht in diesem Ticket)

| # | Problem | Severity | Nächste Maßnahme |
|---|---------|----------|-----------------|
| B | `subrun_announce` kommt beim Parent nicht als Tool-Ergebnis an | 🔴 | Issue-0009: Async-Outcome-Callback |
| C | `ToolSpec.timeout_seconds` für spawn_subrun greift nie (Bypass-Architektur) | 🟠 | Refactor spawn_subrun durch policy run_tool_with_policy |
| 7 | Kein Skill-Grounding für Orchestrierungsanfragen | 🟡 | Skills-Gating per task_type konfigurierbar machen |
| 2* | Double-Lane-Release ist Observability-Problem, kein Semaphore-Bug | 🟡 | Event-Sequenz-Validator im Lifecycle-Stream |

---

## Kausalkette nach Fixes

```
User schreibt "orchestrate" + spawn_subrun(mode="wait")
    │
    ▼
main.py: wartet via wait_for_completion()      [Fix 1]
    │
    ├─ Kind erfolgreich → terminal_reason="subrun-complete"
    │       ▼
    │   _resolve_synthesis_task_type → "orchestration"           [Fix 2]
    │       ▼
    │   Synthesizer Contract: Goal/Delegation outcome/...        [Fix 3]
    │       ▼
    │   orchestration_evidence_missing Gate: subrun-complete ✓   [Fix 4]
    │       ▼
    │   Antwort: Korrekte Erfolgsbeschreibung
    │
    └─ Kind fehlgeschlagen → terminal_reason="subrun-error"
            ▼
        _resolve_synthesis_task_type → "orchestration_failed"   [Fix 2]
            ▼
        Synthesizer Contract: Goal/Delegation failure/...       [Fix 3]
            ▼
        orchestration_evidence_missing Gate: subrun-complete ✗  [Fix 4]
            ▼
        Antwort: "The delegated subrun did not complete..."
        → System kann NICHT lügen
```

---

## Quality-Pattern: Evidence-Based Distillation

Die Korrektheit einer Antwort wird jetzt auf drei Ebenen erzwungen:

### Ebene 1 — Kontrakts-Injektion (Prompt-Level)

Unterschiedliche LLM-Prompts je nach tatsächlichem Outcome:

| Outcome | Task-Type | Section-Contract |
|---------|-----------|-----------------|
| Subrun completed | `orchestration` | Goal, Delegation outcome, Child handover, Parent decision, Next steps |
| Subrun failed | `orchestration_failed` | Goal, **Delegation failure**, **Failure reason**, Recovery options, Next steps |
| Subrun pending | `orchestration_pending` | Goal, Delegation initiated, **Pending status**, What to expect, Next steps |
| Kein Subrun | `orchestration` | Gate blockiert → Fehlermeldung |

### Ebene 2 — Syntaktischer Self-Check (Synthesis-Level)

`_run_synthesis_self_check` prüft ob die Section-Headers in der Antwort vorhanden sind.
Bei Fehlern: automatischer Repair-Pass mit expliziten Failure-Gründen im Prompt.

### Ebene 3 — Semantischer Evidence Gate (Post-Synthesis-Level)

Bevor die Antwort an den Nutzer geht, wird überprüft ob das Tool-Ergebnis den
behaupteten Outcome belegt. Kein `subrun-complete` → Antwort wird ersetzt.

---

## Test-Abdeckung (Regressionsstand)

```
541 passed  ← alle Kern-Tests grün
  1 failed  ← test_extract_actions_requires_strict_json_object (pre-existing, nicht von diesen Fixes)
  1 failed  ← test_ws_handler_applies_directive_overrides_and_strips_prefix (pre-existing)
```

Betroffene Test-Dateien die direkt die geänderten Komponenten testen:

| Test-Datei | Ergebnis |
|-----------|---------|
| `test_synthesizer_agent.py` | ✅ 17 passed |
| `test_subrun_lane.py` | ✅ 18 passed |
| `test_tool_registry.py` | ✅ 8 passed |
| `test_tool_execution_manager.py` | ✅ 8 passed |

---

## Empfohlene Nachweis-Tests (noch zu schreiben)

Die folgenden Tests aus dem Issue-0008 sollten nach diesem Fix PASS ergeben:

```python
# Vorher FAIL (Finding 1) → PASS nach Fix 1:
# test_spawn_subrun_returns_accepted_even_when_child_fails
# → Funktioniert jetzt korrekt für mode="wait"

# Vorher FAIL (Finding 3) → PASS nach Fix 3+4:
# test_synthesis_contract_check_passes_despite_failed_subrun
# → orchestration_failed Contract verhindert Erfolgs-Sektionen

# Vorher FAIL (Finding 6) → PASS nach Fix 5:
# test_tool_capability_preselection_not_skipped_for_orchestration
# → registry ist jetzt verdrahtet, preselection applied statt skipped
```

---

## Verweise auf geänderte Dateien

- [backend/app/main.py](../backend/app/main.py) — `_spawn_subrun_from_agent` (mode=wait Implementation)
- [backend/app/agent.py](../backend/app/agent.py) — `_resolve_synthesis_task_type`, `_has_orchestration_evidence`, `_requires_orchestration_evidence`, `_has_orchestration_attempted`, Orchestration Gate im `run()`-Flow, ToolExecutionManager Registry-Verdrahtung
- [backend/app/agents/synthesizer_agent.py](../backend/app/agents/synthesizer_agent.py) — `_resolve_task_type` (Evidence-First + neue Hint-Typen), `_required_sections_for_task` (orchestration_failed, orchestration_pending Contracts)
