# Sprint 4 — Phase E: Cleanup & Deprecation

## Ziel

Die gesamte Legacy-3-Phase-Pipeline (Planner → ToolSelector → Synthesizer) entfernen.
Der neue Continuous Streaming Tool Loop (AgentRunner) wird zum einzigen Ausführungspfad.

---

## Tickets

### S4-01 · Legacy-Unit-Tests löschen

Dateien löschen:
- `tests/test_planner_agent.py`
- `tests/test_planner_structured.py`
- `tests/test_synthesizer_agent.py`
- `tests/test_tool_selector_agent.py`

**AK**: Keiner dieser Tests existiert mehr.

---

### S4-02 · agent.py — Legacy-Imports entfernen

Imports entfernen:
- `from app.agents.planner_agent import PlannerAgent`
- `from app.agents.synthesizer_agent import SynthesizerAgent`
- `from app.agents.tool_selector_agent import ToolSelectorAgent`
- `from app.contracts.schemas import PlannerInput, SynthesizerInput, ToolSelectorInput`
- `from app.contracts.tool_selector_runtime import ToolSelectorRuntime`
- `from app.orchestrator.step_executors import PlannerStepExecutor, SynthesizeStepExecutor, ToolStepExecutor`
- `from app.services.dynamic_temperature import DynamicTemperatureResolver`
- `from app.services.prompt_ab_registry import PromptAbRegistry`

**AK**: `python -c "from app.agent import HeadAgent"` kompiliert fehlerfrei.

---

### S4-03 · agent.py — `_HeadToolSelectorRuntime` entfernen

Klasse `_HeadToolSelectorRuntime` (Zeile 104–133) löschen.

**AK**: Keine Referenz auf `_HeadToolSelectorRuntime` im gesamten Code.

---

### S4-04 · agent.py — `_build_sub_agents()` bereinigen

- Legacy-Agent-Instanziierungen entfernen (PlannerAgent, ToolSelectorAgent, SynthesizerAgent)
- Step-Executor-Instanziierungen entfernen (plan_step_executor, tool_step_executor, synthesize_step_executor)
- DynamicTemperatureResolver- und PromptAbRegistry-Erstellung entfernen
- `if settings.use_continuous_loop:` Guard entfernen — AgentRunner wird IMMER erstellt

**AK**: `_build_sub_agents()` erstellt nur noch den AgentRunner.

---

### S4-05 · agent.py — `run()` vereinfachen

- Feature-Flag-Check entfernen — immer AgentRunner verwenden
- `_run_legacy()`-Fallback entfernen
- Routing wird bedingungslos: `await self._agent_runner.run(...)`

**AK**: `run()` hat keinen Legacy-Fallback mehr.

---

### S4-06 · agent.py — `_run_legacy()` + Legacy-Methoden löschen

Methoden löschen (~1400 Zeilen):
- `_run_legacy()` (706–1824)
- `_execute_planner_step()` (1905–1937)
- `_execute_tool_step()` (1938–1982)
- `_execute_synthesize_step()` (1983–2024)
- `_step_budgets()` (2025–2041)
- `_build_context_segments()` (2042–2103)
- `_plan_still_valid()` (2464–2470)
- `_classify_tool_results_state()` (2471–2542)
- `_is_direct_answer_plan()` (2543–2574)
- `_is_steer_interrupted()` (2575–2577)
- `_resolve_replan_reason()` (2578–2621)
- `_build_root_cause_replan_prompt()` (2622–2639)

**AK**: Keine der gelisteten Methoden existiert in agent.py.

---

### S4-07 · agent.py — `configure_runtime()` bereinigen

- `self.planner_agent.configure_runtime(...)` entfernen
- `self.synthesizer_agent.configure_runtime(...)` entfernen
- `_failure_retriever`-Propagation an `planner_agent` entfernen
- `if self._agent_runner is not None:` Guard entfernen (Runner existiert immer)

**AK**: `configure_runtime()` hat keine Legacy-Agent-Referenzen.

---

### S4-08 · Legacy Agent-Dateien löschen

Dateien löschen:
- `app/agents/planner_agent.py`
- `app/agents/synthesizer_agent.py`
- `app/agents/tool_selector_agent.py`
- `app/agents/tool_selector_legacy.py`

`agents/__init__.py` aktualisieren — PlannerAgent, SynthesizerAgent, ToolSelectorAgent aus `__all__` entfernen.

**AK**: Keine Legacy-Agent-Datei existiert im agents-Verzeichnis.

---

### S4-09 · Step-Executors & Legacy-Contracts löschen

- `orchestrator/step_executors.py` löschen
- `orchestrator/__init__.py` aktualisieren
- `contracts/tool_selector_runtime.py` löschen
- `contracts/schemas.py` — PlannerInput/Output, ToolSelectorInput/Output, SynthesizerInput/Output entfernen
- `contracts/__init__.py` aktualisieren

**AK**: Keine Legacy-Schemas und keine Step-Executors im Code.

---

### S4-10 · Feature-Flag Default → `true`

`config.py`: `use_continuous_loop` Default von `False` auf `True` ändern.

**AK**: `settings.use_continuous_loop` ist standardmäßig `True`.

---

### S4-11 · Integration-Tests anpassen

| Test-Datei | Aktion |
|---|---|
| `test_backend_e2e.py` | Step-Executor-Import entfernen, 8 Tests die step_executor nutzen entfernen |
| `test_failure_journal.py` | Test 1 umschreiben für AgentRunner-Pfad, Test 2 LTM-Teil behalten |
| `test_reflection_loop.py` | Datei löschen (Verhalten durch Sprint-2 AgentRunner-Tests abgedeckt) |
| `test_session_distillation.py` | Test umschreiben für AgentRunner-Pfad |
| `test_tool_selection_offline_eval.py` | Step-Executor-Import entfernen, betroffene Tests entfernen |

**AK**: Kein Test-Modul importiert `step_executors` oder Legacy-Agents.

---

### S4-12 · Test-Suite & Akzeptanz

- `pytest tests/ -q --ignore=tests/test_browser_tools.py` — alle Tests grün
- `python -c "from app.agent import HeadAgent; print('OK')"` — Kompilierung OK
- Keine Referenz auf PlannerAgent/SynthesizerAgent/ToolSelectorAgent außerhalb von gelöschten Dateien

---

## Akzeptanzkriterien

| # | Kriterium | Prüfmethode |
|---|---|---|
| AK-1 | Kein Legacy-Agent-Code im Projekt | Grep nach `PlannerAgent\|SynthesizerAgent\|ToolSelectorAgent` → 0 Treffer |
| AK-2 | Keine Step-Executors im Projekt | Grep nach `PlannerStepExecutor\|ToolStepExecutor\|SynthesizeStepExecutor` → 0 Treffer |
| AK-3 | AgentRunner immer aktiv | `_build_sub_agents()` hat keinen `if settings.use_continuous_loop:` Guard |
| AK-4 | Kompilierung fehlerfrei | `python -c "from app.agent import HeadAgent; print('OK')"` → OK |
| AK-5 | Regressionstests grün | `pytest tests/ -q --ignore=tests/test_browser_tools.py` ≥ 1400 passed |
