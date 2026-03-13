# Plan: Legacy-Überreste entfernen — HeadAgent bleibt

**Ziel:** So viel toten/irreführenden Code wie möglich löschen, ohne `HeadAgent` als Klasse
oder öffentlichen Namen anzutasten. `HeadAgent` bleibt die Composition Root; was weg muss,
ist das Fossil-Gepäck aus der 3-Phasen-Pipeline.

**Status nach Analyse (Stand 13.03.2026):**
- `PlannerAgent`, `ToolSelectorAgent`, `SynthesizerAgent` — **bereits gelöscht** ✓
- `app/agent_runner.py`, `app/agent_runner_types.py` (Proxy-Shims) — **bereits gelöscht** ✓
- `settings.use_continuous_loop` Config-Key — **bereits nicht mehr vorhanden** ✓

Was noch übrig ist: totes Boilerplate *innerhalb* von `HeadAgent` und im Drumherum.

---

## Inventar der verbleibenden Überreste

| # | Überrest | Ort | Warum tot |
|---|----------|-----|-----------|
| R-1 | `PromptProfile.plan_prompt` Feld | `head_agent.py` L 80 | Befüllt, aber nie an `_build_sub_agents` oder `configure_runtime` übergeben. Kein Code liest es. |
| R-2 | Alle `*_agent_plan_prompt` Settings | `config/sections.py` (15 Felder) + `config/settings.py` (~20 Felder) | Existieren nur um `PromptProfile.plan_prompt` (R-1) zu befüllen. |
| R-3 | Lokale `IntentGateDecision` Dataclass-Kopie | `head_agent.py` L 66–78 | Original lebt in `app.reasoning.intent_detector`. Lokale Kopie ist identisch und wird durchgehend statt der Original-Klasse gebaut. |
| R-4 | `_detect_intent_gate()` Methode | `head_agent.py` L 1024–1031 | Eigener Docstring: *"Neutralised: LLM-based tool selection handles intent classification."* Gibt nur Hardcoded-`None`-Werte zurück, nirgendwo außerhalb aufgerufen. |
| R-5 | `USE_CONTINUOUS_LOOP` Erwähnung | `runner.py` Docstring L 4–5 | Flag existiert nicht mehr. Der Loop ist immer aktiv. |
| R-6 | `USE_CONTINUOUS_LOOP` in Tests | `test_agent_runner_integration.py`, `test_agent_runner_integration_events.py` | Tests prüfen Flag-Logik, die nicht mehr existiert. Beschreibungen irreführend. |
| R-7 | `backend/scripts/cleanup_agent.py` | `backend/scripts/` | Einmalig ausgeführtes Migrationsskript. Enthält alten `HeadAgent`-Code als Strings. |
| R-8 | `REASONING-PIPELINE.md` | Repo-Root | Beschreibt das 3-Phasen-Modell als autoritativ. Irreführend. |
| R-9 | `backend/coverage.json` | `backend/` | Veraltetes Coverage-Artefakt mit Klassen-Einträgen für `PlannerAgent`, `ToolSelectorAgent`, `SynthesizerAgent`. |
| R-10 | `app/agent/__init__.py` Proxy-Komplex | `app/agent/__init__.py` | 60 Zeilen `_AgentPackage(types.ModuleType)` Proxy existieren nur damit `patch("app.agent.settings")` in Tests funktioniert. Kann durch normalen Import + Patch auf `app.agent.head_agent.settings` ersetzt werden. |

---

## Phasen

### Phase 1 — `PromptProfile.plan_prompt` und tote Settings entfernen

**Scope:** `head_agent.py`, `config/sections.py`, `config/settings.py`

1. `PromptProfile.plan_prompt` Feld aus der Dataclass entfernen.
2. In `_resolve_prompt_profile()`: Die Zeile `plan_prompt=ps.plan.strip() or getattr(settings, ps.fallback_plan_key, ""),` und die entsprechende Fallback-Zeile entfernen.
3. In `config/sections.py`: Alle 15 `*_agent_plan_prompt: str = ""` Felder löschen.
4. In `config/settings.py`: Alle `*_agent_plan_prompt` Felder und deren `_resolve_prompt()`-Blöcke löschen (~20 Zeilen).

> **Hinweis:** `record.py`-Feld `fallback_plan_key` und `factory_defaults.py`-Einträge dafür
> **nicht anfassen** — sie werden über den `agents.py`-Router als Metadaten ausgeliefert.
> Es geht nur um die Laufzeit-Befüllung des toten `PromptProfile.plan_prompt`.

**Risiko:** Keins. Das Feld wird nie gelesen.

---

### Phase 2 — Lokale `IntentGateDecision`-Kopie und `_detect_intent_gate()` entfernen

**Scope:** `head_agent.py`

1. `class IntentGateDecision` (Dataclass, ~7 Zeilen) aus `head_agent.py` löschen.
   - Wird nur an einer Stelle im selben File definiert und zurückgegeben.
   - Das Original in `app.reasoning.intent_detector` bleibt unangetastet.
2. `_detect_intent_gate()` Methode (~8 Zeilen) löschen — explizit als neutralisiert markiert,
   kein externer Aufrufer.

**Risiko:** Keins. Kein Test, kein Transport-Code referenziert `IntentGateDecision` aus `head_agent`.

---

### Phase 3 — `USE_CONTINUOUS_LOOP` Referenzen tilgen

**Scope:** `runner.py`, `tests/test_agent_runner_integration.py`, `tests/test_agent_runner_integration_events.py`

1. `runner.py` Docstring (Zeilen 3–5): Ersetze *"Replaces the 3-phase pipeline … Activated via `USE_CONTINUOUS_LOOP=true` feature flag."* durch eine korrekte Beschreibung des heutigen Modells.
2. `test_agent_runner_integration.py`:
   - `make_settings(enabled)` Fixture entfernen — ruft `Settings(use_continuous_loop=enabled)` auf.
   - Die zwei Test-Klassen, die `HeadAgent` mit Feature-Flag-Logik testen, entfernen oder auf direkten `AgentRunner`-Test umstellen.
3. `test_agent_runner_integration_events.py`: Kommentar-Zeile *"AgentRunner is constructed when USE_CONTINUOUS_LOOP=true"* entfernen.

**Risiko:** Gering. Tests prüfen nicht mehr existierende Logik — kein Verhalten ändert sich.

---

### Phase 4 — Tote Dateien löschen

1. **Löschen:** `backend/scripts/cleanup_agent.py`
   - Einmalig ausgeführtes Migrationsskript, enthält alten Code als String-Literale.
2. **Löschen:** `REASONING-PIPELINE.md`
   - Beschreibt Planner → ToolSelector → Synthesizer als aktives Modell. Irreführend für neue Entwickler.
   - Optional ersetzen durch kurzes `AGENT-EXECUTION-MODEL.md` (siehe Phase 7).
3. **Löschen:** `backend/coverage.json`
   - Veraltetes Build-Artefakt. Sollte von CI neu generiert, nicht committed werden.

---

### Phase 5 — `app/agent/__init__.py` vereinfachen

**Scope:** `app/agent/__init__.py`

Aktuell: 60 Zeilen `_AgentPackage(types.ModuleType)` Proxy, der `__setattr__` und `__delattr__`
überladen hat, damit `unittest.mock.patch("app.agent.settings")` in Tests funktioniert.

Ziel:
```python
# app/agent/__init__.py  (nach Vereinfachung)
from app.agent.head_agent import HeadAgent

__all__ = ["HeadAgent"]
```

Tests, die `patch("app.agent.settings")` verwenden, müssen auf
`patch("app.agent.head_agent.settings")` umgestellt werden.

Zu prüfen: `grep -r 'patch.*app\.agent\.settings'` in `backend/tests/` — alle Treffer anpassen.

**Risiko:** Mittel. Könnte mehrere Test-Patches brechen. Daher separat prüfen.

---

### Phase 6 — Dokumentation aktualisieren

1. `runner.py` Docstring (nach Phase 3): Beschreibe den `AgentRunner` als primäre Ausführungseinheit
   ohne Erwähnung von Feature-Flags oder der alten Pipeline.
2. `ARCHITECTURE.md`: Alle Erwähnungen von Planner/ToolSelector/Synthesizer als aktive Komponenten entfernen.
3. `DDD_STRUCTURE_PLAN.md`: HeadAgent-Cleanup-Phase als abgeschlossen markieren (die Klasse bleibt, der tote Code ist weg).
4. Optional: `AGENT-EXECUTION-MODEL.md` anlegen — kurze ehrliche Beschreibung des `HeadAgent → AgentRunner`-Musters.

---

## Ausführungsreihenfolge

```
Phase 1  (plan_prompt + Settings)     → ~40 Zeilen Code gelöscht, kein Risiko
Phase 2  (IntentGateDecision)         → ~15 Zeilen Code gelöscht, kein Risiko
Phase 3  (USE_CONTINUOUS_LOOP)        → Docstring + 2 Testdateien, niedriges Risiko
Phase 4  (Dateien löschen)            → 3 Dateien weg, kein Laufzeit-Risiko
Phase 5  (app/agent/__init__.py)       → Test-Patches prüfen, mittleres Risiko
Phase 6  (Docs)                       → rein dokumentarisch
```

Phasen 1–4 können in einem einzigen PR gebündelt werden.
Phase 5 ist ein separater PR nach vollständiger Test-Prüfung.

---

## Was sich NICHT ändert

| Komponente | Begründung |
|---|---|
| `HeadAgent` Klasse, Name, Datei | Bleibt Composition Root und öffentlicher Entry Point |
| `AgentRunner` Logik | Kein Verhaltensänderung |
| `ToolExecutionManager` | Interface unverändert |
| `app/agent/record.py` `fallback_plan_key` | Wird im API-Router ausgeliefert — bleibt als Metadaten-Feld |
| `factory_defaults.py` Einträge `fallback_plan_key` | Metadaten für API-Response |
| `app/reasoning/intent_detector.py` | `IntentGateDecision` Original bleibt |
| Alle 15 Agenten-Definitionen | Keine Verhaltensänderung |
| `app/agent/runner_types.py` | Bleibt unverändert |

---

## Risiko-Übersicht

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| Test bricht wegen `patch("app.agent.settings")` | Mittel (Phase 5) | Grep vor der Änderung, gezielte Patch-Pfad-Anpassung |
| Irgendwo liest Code doch `plan_prompt` | Sehr gering | Codesuche vor Phase-1-Commit: `grep -r "plan_prompt"` |
| `coverage.json` wird aktiv gebraucht | Gering | CI prüfen ob die Datei generiert oder committed wird |
