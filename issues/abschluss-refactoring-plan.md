# Abschluss-Refactoring-Plan

> Stand: 2026-03-04  
> Scope: `backend/app/` — Python-Stack des ai-agent-starter-kit  
> Alle Zeilen wurden direkt aus den Quelldateien gelesen (kein Raten).

---

## Überblick

Drei bestätigte Bugs + zwei Architektur-Lücken, die aus dem Vergleich
mit openclaw und der Analyse des asyncio-Laufzeitverhaltens stammen.
Issues-0008 Fix 1–5 sind bereits implementiert und bleiben unangetastet.

| # | Typ | Datei | Zeile | Schwere |
|---|-----|-------|-------|---------|
| **B1** | Bug — Child-Task-Abbruch | `orchestrator/subrun_lane.py` | L234 | 🔴 Showstopper |
| **B2** | Bug — Race Condition | `main.py` | L293–295 | 🔴 Showstopper |
| **B3** | Bug — Dead Code | `agents/synthesizer_agent.py` | L174 | 🟠 Korrektheit |
| **A1** | Architektur — Skill-Gate zu eng | `services/tool_execution_manager.py` | L228–231 | 🟡 Reliability |
| **A2** | Architektur — Skills nur im Tool-Selector | `services/tool_execution_manager.py` | L259 ff. | 🟡 Qualität |

---

## B1 — `asyncio.wait_for` ohne `shield` bricht Child-Run ab

### Problemanalyse

```python
# subrun_lane.py  L226–236 (IST)
async def wait_for_completion(self, run_id: str, timeout: float = 10.0) -> dict | None:
    async with self._lock:
        task = self._run_tasks.get(run_id)
    if task is None:
        ...
        return self._run_status.get(run_id)

    await asyncio.wait_for(task, timeout=timeout)   # ← BUG L234
    ...
    return self._run_status.get(run_id)
```

`asyncio.wait_for(task)` **cancelt den Task** sobald das Timeout feuert.
Das bedeutet: der Child-Run (z.B. ein laufender Agent-Zyklus) wird mitten
in der Ausführung abgebrochen — nicht nur der *Warte-Vorgang*.

Das Caller-Muster in `main.py` fängt `asyncio.TimeoutError` und fährt fort,
aber der Kind-Prozess ist zu diesem Zeitpunkt schon tot.

### Fix

```python
# subrun_lane.py  L234 (SOLL)
    await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
```

`asyncio.shield()` entkoppelt den Task von der Cancellation:
- Timeout feuert → `wait_for` wirf `asyncio.TimeoutError` → Caller behandelt es
- Der Child-Task läuft **unbeeinflusst weiter**
- `_run_status` wird später über `_set_status()` befüllt, wenn der Task endet

**Einzeilige Änderung. Keine weiteren Anpassungen nötig.**

---

## B2 — Race Condition: Status wird gelesen bevor der Handler ihn schreibt

### Problemanalyse

```python
# main.py  L289–299 (IST)
if mode == "wait":
    wait_timeout = max(5.0, float(effective_timeout) + 5.0)
    try:
        await components.subrun_lane.wait_for_completion(run_id, timeout=wait_timeout)
    except asyncio.TimeoutError:
        pass  # ← event-loop wird NICHT an andere Coroutinen abgegeben

return {
    "run_id": run_id,
    ...
    "handover": _sanitize_handover_contract(
        components.subrun_lane.get_handover_contract(run_id)  # ← sofortiger Read
    ),
}
```

Nach `except asyncio.TimeoutError: pass` ist der `_run()`-Coroutine noch nicht
fertig mit dem Schreiben des Endstatus in `_run_status`. Der `CancelledError`-Handler
in `_run()` läuft erst, wenn der Event-Loop die Kontrolle bekommt.

Da `pass` keinen `await` enthält, bekommt der Event-Loop niemals die Chance
das `_set_status()`-Callback auszuführen bevor `get_handover_contract` liest.
Ergebnis: `handover.terminal_reason` ist `"subrun-accepted"` statt `"subrun-timeout"`.

Mit **B1 behoben** (shield) tritt dieser Fehler seltener auf, aber er bleibt
strukturell korrekt: der Task ist dann noch am Laufen, schreibt aber `_run_status`
asynchron. Ohne ein `await asyncio.sleep(0)` ist der Status nicht garantiert present.

### Fix

```python
# main.py  L292–295 (SOLL)
    except asyncio.TimeoutError:
        await asyncio.sleep(0)  # Event-Loop-Zyklus abgeben → _set_status() kann laufen
```

`asyncio.sleep(0)` ist das idiomatische Python-Pattern um
"anderen pending Coroutinen einen Zyklus zu geben" ohne wirklich zu warten.

**Einzeilige Änderung.**

---

## B3 — Dead Code in `_resolve_task_type()`

### Problemanalyse

```python
# agents/synthesizer_agent.py  L173–175 (IST)
        if any(marker in user_message for marker in ("orchestrate", "delegate", "spawn subrun", "multi-agent")):
            return "orchestration"
        if "subrun_announce" in tool_results:   # ← IMMER False
            return "orchestration"
```

`subrun_announce` ist ein **WebSocket-Event** (`send_event({"type": "subrun_announce", ...})`).
Es wird in `_emit_announce_with_retry()` (`subrun_lane.py` L881) gefeuert.
Es landet **nie** im `tool_results`-String — der enthält ausschließlich Tool-Return-Values.

Die Zeile ist seit Einführung strukturell tot. Sie gibt eine falsche mentale
Annahme über die Datenflüsse weiter und verleitet zu falschen Fixes.

### Fix

```python
# agents/synthesizer_agent.py  L173–175 (SOLL)
        if any(marker in user_message for marker in ("orchestrate", "delegate", "spawn subrun", "multi-agent")):
            return "orchestration"
        # subrun_announce ist ein WebSocket-Event, kein Tool-Result.
        # Erreichbarkeit über tool_results ist strukturell ausgeschlossen.
        # Orchestration-Erkennung erfolgt ausschließlich über den Evidence-Block
        # ("spawned_subrun_id=" in tool_results) weiter oben.
```

**Zeile entfernen.** Kein Ersatz nötig — der Evidence-Block (L163–170) deckt
alle echten Orchestrierungs-Fälle bereits ab.

---

## A1 — Subagent Skill-Gate ist zu eng

### Problemanalyse

```python
# services/tool_execution_manager.py  L228–231 (IST)
@staticmethod
def _should_inject_skills_preview_in_subagent(*, user_message: str, plan_text: str) -> bool:
    text = f"{user_message}\n{plan_text}".lower()
    markers = ("skill", "skills", "skill.md", "read_file", "manual", "runbook")
    return any(marker in text for marker in markers)
```

Ein Subagent der z.B. `deploy`, `test`, `migrate`, `build` ausführen soll,
bekommt keine Skills angezeigt — auch wenn passende SKILL.md-Dateien existieren.
Der Jaccard-Retrieval-Service würde sie als relevant einstufen, aber das Gate
blockiert den gesamten Skills-Inject.

Openclaw injiziert Skills **immer** in den System-Prompt (kein Keyword-Gate).
Das Starter-Kit hat den zweistufigen Ansatz (Eligibility + Relevanz-Ranking)
der prinzipiell besser ist — aber das Gate davor macht ihn wirkungslos.

### Fix

Das Gate entfernen und stattdessen dem Retrieval-Service vertrauen:
Wenn kein Skill einen `min_score`-Schwellwert trifft, ist der Inject eh leer.

```python
# services/tool_execution_manager.py  L228–231 (SOLL)
@staticmethod
def _should_inject_skills_preview_in_subagent(*, user_message: str, plan_text: str) -> bool:  # noqa: ARG004
    # Kein Keyword-Gate — Relevanz-Filterung übernimmt der ReliableRetrievalService.
    # Wenn kein Skill den min_score trifft, bleibt der Inject leer.
    return True
```

**Einzeilige Logikänderung.** Der bestehende `_contract_skills_prompt`-Mechanismus
mit `subagent`-Cap (1200 Zeichen) bleibt als Token-Budget-Schutz erhalten.

---

## A2 — Skills nur im Tool-Selector sichtbar, nicht im Haupt-Agent

### Problemanalyse

Im Starter-Kit injiziert `tool_execution_manager.execute()` den Skills-Retrieval-Prompt
in `effective_memory_context` — der Kontext für den Tool-Selector-LLM-Call.
Der `HeadAgent` auf seiner Synthese-Ebene sieht die Skills **nicht**.

In openclaw steht der Skills-Prompt im **System-Prompt** des laufenden Agents.
Das LLM kann dort:
- explizit auf Skill-Abläufe verweisen ("laut SKILL.md deploy-workflow…")
- seinen Plan anhand der Skill-Beschreibungen strukturieren
- Tool-Calls direkt mit Skill-Namen begründen

Im Starter-Kit fehlt dem Haupt-Agent dieser Kontext. Er kann nur reagieren
wenn der Tool-Selector zufällig das richtige Tool wählt.

### Fix

Den Skills-Prompt aus dem Snapshot in den `memory`/`context`-Block des
`HeadAgent`-System-Prompts einspeisen. Der geeignetste Ort ist
`_build_system_prompt()` / `_assemble_context()` in `agent.py`:

```python
# agent.py — in _assemble_context() oder äquivalenter Methode
if skills_snapshot := self._config.get("skills_snapshot"):
    prompt_text = skills_snapshot.get("prompt", "").strip()
    if prompt_text:
        context_parts.append(
            f"## Available Skills\n\n{prompt_text}\n"
        )
```

Der `skills_snapshot` ist bereits in `tool_execution_manager.py` gebaut
(`build_snapshot()`) und als `SkillSnapshot`-Dict verfügbar — er muss nur
durch die `_run()`-Pipeline bis zu `_build_system_prompt()` weitergegeben werden.

**Scope:** Mittelgroße Änderung. Erfordert, dass `skills_snapshot` im
`AgentRun`-Payload oder als Closure-Variable durch `_run()` fließt.

---

## Implementierungsreihenfolge

```
B1 (1 Zeile, subrun_lane.py)
  ↓
B2 (1 Zeile, main.py)
  — beide gemeinsam testen mit: pytest backend/tests/test_subrun_lane.py -q
  ↓
B3 (1 Zeile entfernen, synthesizer_agent.py)
  — testen: pytest backend/tests/test_synthesizer_agent.py -q
  ↓
A1 (1 Zeile, tool_execution_manager.py)
  — testen: pytest backend/tests/test_tool_execution_manager.py -q
  ↓
A2 (Architektur-Änderung, agent.py + Übergang)
  — isoliert entwickeln, nach Baseline-Test-Durchlauf integrieren
```

**B1 + B2 müssen zusammen deployed werden** — B1 ohne B2 behebt den Deadlock
aber lässt die Race Condition bestehen; B2 ohne B1 behebt die Race Condition
aber der Child-Task wird trotzdem gecancelt.

---

## Test-Baseline

Vor jedem Merge:
```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q `
  --ignore=backend/tests/test_backend_e2e.py `
  --ignore=backend/tests/test_backend_e2e_real_api.py `
  --ignore=backend/tests/test_tool_selection_offline_eval.py
```
Erwartetes Ergebnis: **541 passed, 2 pre-existing failures** (unverändert).

---

## Was bewusst ausgelassen wurde

| Thema | Begründung |
|-------|------------|
| Openclaw-Skill-Precedence (6 Quellen) | Feature, kein Bug. Sinnvoll sobald Plugin-Ökosystem wächst. |
| `before_tool_call` / `after_tool_call` Hooks | Feature. Kein akuter Defekt. |
| Session-Guard nach Tool-Fehler | Feature. Vorher A2 fertigstellen. |
| Skill-Frontmatter `disableModelInvocation` | Nice-to-have. Relevanter wenn A2 umgesetzt. |

Diese Punkte sind im [final_refactoring.md](final_refactoring.md) als Gap 7–10 dokumentiert.
