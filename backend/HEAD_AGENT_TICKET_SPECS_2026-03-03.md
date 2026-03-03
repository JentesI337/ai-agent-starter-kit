# Head Agent — Ticket-Spezifikationen (HA-01 bis HA-05)

Stand: 03.03.2026
Bezug: `HEAD_AGENT_IMPLEMENTATION_PLAN_2026-03-03.md`

## Arbeitsmodus (verbindlich für alle Tickets)

- Pro Ticket genau ein primäres Ziel (kein Scope-Mix).
- Reihenfolge: Design-Gate -> Unit/Contract-Gate -> Slice-Gate -> Suite-Gate -> Benchmark-Gate.
- Bei Gate-Fehler: sofort stoppen, Root Cause fixen, erneut beim fehlgeschlagenen Gate starten.
- Jede Änderung ist rückbaubar (Feature-Flag oder klarer Revert-Pfad).

---

## Empfohlene Implementierungsreihenfolge

1. HA-02 (Tests zuerst)
2. HA-01 (Schema-Implementierung)
3. HA-03 (Benchmark-Split + Metriken)
4. HA-04 (Recovery-Matrix)
5. HA-05 (Tool-Selection-Replan)

Diese Reihenfolge minimiert Fehlinterpretationen, da Mess- und Testgrundlage vor Logikänderungen stabilisiert wird.

---

## HA-02 — Contract-Tests für Hard-Reasoning-Output

### Ziel
Verbindliche Tests schaffen, die strukturelle Mindestqualität von Hard-Reasoning-Antworten absichern.

### Betroffene Dateien
- `backend/tests/` (neue Testdatei, z. B. `test_hard_reasoning_output_contracts.py`)
- ggf. `backend/tests/test_backend_e2e.py` (nur ergänzend)

### Nicht-Ziele
- Keine Änderung an Runtime-Logik in `app/`.

### Umsetzungsschritte
1. Contract-Definition als Test-Helpers definieren:
   - Pflicht-Sektionen (z. B. Phasen, KPI-Block, Risiken).
   - Regex-Mindesttreffer.
2. Positivfälle mit gültigen Beispielausgaben.
3. Negativfälle mit unstrukturierten Ausgaben.
4. Toleranzregeln gegen Flakiness (z. B. case-insensitive, robuste Patterns).

### Akzeptanzkriterien
- Neue Tests sind deterministisch und lokal reproduzierbar.
- Mindestens ein Positiv- und ein Negativpfad pro Pflichtkriterium.
- Keine Änderung bestehender Laufzeitpfade.

### Testkommandos
- `./.venv/Scripts/python.exe -m pytest tests/test_hard_reasoning_output_contracts.py -q`
- `./.venv/Scripts/python.exe -m pytest tests/test_backend_e2e.py -q` (optional/sliceabhängig)

### Risiken
- Overfitting auf zu enge Regex.

### Gegenmaßnahme
- Struktur + semantische Mindestchecks kombinieren, keine exakten Wortfolgen erzwingen.

### Rollback
- Neue Testdatei entfernen oder auf letzte stabile Version zurück.

---

## HA-01 — Hard-Output-Schema in Planner/Synthesizer

### Ziel
Hard-Reasoning-Ausgaben konsistent auf ein strukturiertes Antwortschema bringen.

### Betroffene Dateien
- `backend/app/agents/planner_agent.py`
- `backend/app/agents/synthesizer_agent.py`
- ggf. `backend/app/agent.py`
- ggf. `backend/app/services/reply_shaper.py`

### Nicht-Ziele
- Keine Recovery-Policy-Änderung.
- Keine Tool-Policy-Änderung.

### Umsetzungsschritte
1. Schema als klaren internen Contract definieren (Sections + Mindestinhalte).
2. Planner-Output auf schemafähige Vorstruktur trimmen.
3. Synthesizer mit schema-first-Erzeugung + Self-Check vor Finalisierung.
4. ReplyShaper nur minimal ergänzen (Strukturerhalt, kein Rewriting von Inhalt).

### Akzeptanzkriterien
- HA-02 Contract-Tests grün.
- Hard-Reasoning-Fehler wegen Struktur/Regex sinken sichtbar.
- Keine Regression in Mid/Easy-Case-Antwortqualität.

### Testkommandos
- `./.venv/Scripts/python.exe -m pytest tests/test_hard_reasoning_output_contracts.py -q`
- `./.venv/Scripts/python.exe -m pytest tests/test_backend_e2e.py -q`
- `./.venv/Scripts/python.exe -m pytest tests -q` (Suite-Gate)

### Benchmark-Gate
- Betroffene Hard-Reasoning-Cases mit mindestens 3 Runs/Case.
- Keine Verschlechterung von `gated_success_rate_percent` gegenüber letzter stabiler Baseline.

### Risiken
- Höhere Latenz durch zusätzliche Self-Checks.

### Gegenmaßnahme
- Self-Check auf 1 Pass begrenzen, harte Timeout-Grenzen beibehalten.

### Rollback
- Schema-Erweiterung per Flag deaktivieren oder gezielt auf Vorversion zurücksetzen.

---

## HA-03 — Benchmark-Szenario-Split + Aggregationsmetriken

### Ziel
Benchmarking so erweitern, dass Root-Causes in Hard-Fails eindeutig klassifizierbar sind.

### Betroffene Dateien
- `backend/benchmarks/scenarios/default.json`
- `backend/benchmarks/run_benchmark.py`
- `backend/BENCHMARK_STRATEGY.md`

### Nicht-Ziele
- Keine Änderung der Agenten-Laufzeitlogik.

### Umsetzungsschritte
1. Hard-Cases splitten in:
   - `hard_reasoning_format`
   - `hard_reasoning_depth`
   - `hard_tools_diagnostic`
2. `runs_per_case` standardmäßig auf 3 setzen (oder klar dokumentiert konfigurierbar).
3. Report um p50/p95 für `first_token_ms` und `duration_ms` ergänzen.
4. Gating klar trennen (`gate=true` vs. diagnostisch `gate=false`).

### Akzeptanzkriterien
- Report zeigt pro Split-Case klare Pass/Fail- und Latenzsignale.
- p50/p95 korrekt berechnet und dokumentiert.
- Kein Bruch mit bestehenden Benchmark-Artefakten.

### Testkommandos
- `./.venv/Scripts/python.exe -m pytest tests -k benchmark -q` (falls vorhanden)
- Dry-Run/kurzer Benchmark-Lauf auf 1–2 Cases

### Risiken
- Vergleichbarkeit zu alten Runs sinkt.

### Gegenmaßnahme
- Migration-Hinweis in Doku + Übergangsphase mit Alt-/Neu-Vergleich.

### Rollback
- Szenario-Split zurücknehmen und Aggregation auf vorherige Felder begrenzen.

---

## HA-04 — Recovery-Decision-Matrix + Unit-Tests

### Ziel
Recovery-Verhalten deterministischer und erfolgreicher machen.

### Betroffene Dateien
- `backend/app/orchestrator/fallback_state_machine.py`
- `backend/app/orchestrator/recovery_strategy.py`
- `backend/app/orchestrator/pipeline_runner.py`
- `backend/tests/test_fallback_state_machine.py`
- `backend/tests/test_pipeline_runner_recovery.py`

### Nicht-Ziele
- Keine Änderungen an Prompting/Output-Schema.

### Umsetzungsschritte
1. Error-Klassen in eine explizite Decision-Matrix überführen (`error class -> next best action`).
2. Retry-/Backoff-Politik je Klasse festlegen (inkl. terminal reason).
3. Telemetrie-Felder konsistent durchreichen (`recovered_successfully`, `terminal_reason`).
4. Parametrisierte Unit-Tests für alle Matrix-Zweige ergänzen.

### Akzeptanzkriterien
- Matrix ist vollständig durch Tests abgedeckt.
- Recovery-Regressionstests bleiben grün.
- Diagnostikfall zeigt verbesserte Recovery-Erfolgsquote.

### Testkommandos
- `./.venv/Scripts/python.exe -m pytest tests/test_fallback_state_machine.py -q`
- `./.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner_recovery.py -q`
- `./.venv/Scripts/python.exe -m pytest tests/test_recovery_strategy.py -q`

### Risiken
- Unbeabsichtigte Event-/Schema-Abweichungen.

### Gegenmaßnahme
- Additive Feldstrategie, bestehende Keys unverändert lassen.

### Rollback
- Matrix hinter Flag deaktivieren oder auf vorheriges Branching zurückgehen.

---

## HA-05 — Tool-Selection-Replan-Fallback (1x, bounded)

### Ziel
Leerselektion/Fehlgriff in komplexen Aufgaben durch kontrollierten Replan-Fallback reduzieren.

### Betroffene Dateien
- `backend/app/agent.py`
- `backend/app/agents/tool_selector_agent.py`
- `backend/app/orchestrator/step_executors.py`
- `backend/app/services/action_parser.py`
- `backend/app/services/action_augmenter.py`
- passende Tests in `backend/tests/`

### Nicht-Ziele
- Kein unbounded Retry.
- Keine globale Lockerung der Tool-Security.

### Umsetzungsschritte
1. Trigger-Kriterien für Replan definieren (nur bei klarer Leerselektion/ungültiger Aktion).
2. Replan strikt auf **einen** Zusatzversuch begrenzen.
3. Ursachenklassifikation in Events emitten.
4. Safeguards: Timeout/Depth/Event-Limits explizit durchsetzen.

### Akzeptanzkriterien
- `tool_selection_empty` in Mid/Hard sinkt messbar.
- Keine Event-Stürme, keine Endlosschleifen.
- Sicherheits- und Orchestrierungs-Tests bleiben grün.

### Testkommandos
- `./.venv/Scripts/python.exe -m pytest tests -k "tool_selector or action_parser or action_augmenter" -q`
- `./.venv/Scripts/python.exe -m pytest tests/test_tools_command_security.py -q`
- `./.venv/Scripts/python.exe -m pytest tests/test_subrun_lane.py -q` (zur Abgrenzung von Nebeneffekten)

### Benchmark-Gate
- Mid/Hard-Cases mit 3 Runs/Case prüfen.
- Keine Verschlechterung in Gated-Hard, gleichzeitig Rückgang `tool_selection_empty`.

### Risiken
- Bessere Pass-Rate bei gleichzeitig höherer Latenz.

### Gegenmaßnahme
- Harte Grenzen für Replan-Latenz und Step-Anzahl; bei Überschreitung sofortiger Fallback.

### Rollback
- Replan-Fallback per Flag abschaltbar machen und bei Bedarf deaktivieren.

---

## Cross-Ticket Telemetrie- und Doku-Pflicht

Bei jedem der fünf Tickets prüfen und ggf. aktualisieren:
- `backend/SESSION_TASKBOARD_2026-03-02.md`
- `backend/architecture.md` (bei Contract-/Event-Änderungen)
- `backend/RECOVERY_RUNBOOK.md` / `backend/SMOKE_RUNBOOK.md` (bei operativen Änderungen)

Mindestinhalt im Taskboard je Ticket:
1. Änderung
2. Verifikation (exakte Kommandos + Ergebnis)
3. Kritische Selbstprüfung (Impact, Restrisiko)
4. Follow-up

---

## Definition of Ready (pro Ticket)

Ein Ticket darf erst umgesetzt werden, wenn:
1. Ziel und Nicht-Ziele klar sind,
2. betroffene Dateien benannt sind,
3. Akzeptanzkriterien testbar formuliert sind,
4. Rollback-Option dokumentiert ist.

## Definition of Done (pro Ticket)

Ein Ticket ist abgeschlossen, wenn:
1. alle zugeordneten Tests grün sind,
2. relevante Benchmark-Gates erfüllt sind,
3. keine unbeabsichtigte Contract-Regression vorliegt,
4. Taskboard/Doku aktualisiert wurde.
