# Session Taskboard — Backend Refactoring (02.03.2026)

## Ziel dieses Dokuments
Dieses Taskboard hält den **arbeitsfähigen Next-Step-Backlog** für Folgesessions fest (auf Basis von `REFACTORING_PLAN.md` und aktuellem Codezustand).

## Status-Check (Ist)
- Große Refactoring-Phasen (0–5) sind im Kern umgesetzt.
- Backend-Tests sind grundsätzlich stabil; Recovery-Module sind entkoppelt und testbar.
- Recovery-Telemetrie-Hardening ist abgeschlossen; aktueller Schwerpunkt liegt auf punktueller Sicherheits- und Wartbarkeitshärtung.

## In dieser Session erledigt
1. Recovery-Telemetrie korrigiert (False-Positive-Vermeidung)
   - Datei: `app/orchestrator/pipeline_runner.py`
   - `signal_priority_applied` und `strategy_feedback_applied` werden jetzt aus tatsächlichen Reorder-Operationen abgeleitet.
   - Reason-Felder (`signal_priority_reason`, `strategy_feedback_reason`) sind bei nicht angewendeter Priorisierung konsistent auf `none`.

2. Regressionstests ergänzt
   - Datei: `tests/test_pipeline_runner_recovery.py`
   - Neue Tests decken die Fälle ab, in denen Priorisierung **nicht** reordern muss:
     - Signal-Priorität aktiv, aber Reihenfolge bereits optimal
     - Strategy-Feedback aktiv, aber fehlgeschlagene Strategie bereits am Ende

3. Verifikation
   - Ausgeführt: `pytest -q tests/test_pipeline_runner_recovery.py tests/test_recovery_strategy.py tests/test_fallback_state_machine.py`
   - Ergebnis: **16 passed**

## Fortsetzung (Session 2)

### Umgesetzt
1. P0.1 Additive Summary-Metriken ergänzt
   - Datei: `app/orchestrator/pipeline_runner.py`
   - Neu in `model_recovery_summary.details`:
     - `signal_priority_applied_vs_not_applied`
     - `strategy_feedback_applied_vs_not_applied`
     - `persistent_priority_applied_vs_not_applied`

2. P0.3 Event-Payload-Konsistenztests ergänzt
   - Datei: `tests/test_fallback_state_machine.py`
   - Konsistenz geprüft für `model_recovery_branch_selected` und `model_recovery_action` in beiden Pfaden:
     - retrybarer Fallback
     - fail-fast bei nicht-retrybarem Pfad
   - Datei: `tests/test_pipeline_runner_recovery.py`
   - Summary-Payload auf neue `applied_vs_not_applied`-Metriken abgesichert.

3. P0.2 Event-Schema dokumentiert
   - Datei: `architecture.md`
   - Neuer Abschnitt „Recovery-Lifecycle-Events (Schema)“ mit den tatsächlich emittierten Keys für:
     - `model_recovery_branch_selected`
     - `model_recovery_action`
     - `model_recovery_summary`

### Kritische Selbstprüfung (Session 2)
- Positiv:
  - Änderungen sind additiv und rückwärtskompatibel (keine bestehenden Keys entfernt/umbenannt).
  - Event-Payload-Verträge sind jetzt explizit dokumentiert und durch Unit-Tests abgesichert.
- Restrisiko:
  - `not_applied` wird derzeit als `failures_total - applied_total` berechnet (inkl. Fälle „disabled/not_applicable“), d. h. semantisch breit.
- Follow-up:
  - Falls nötig Trennung in `not_applied_due_to_disabled`, `not_applied_due_to_no_reorder`, `not_applicable` als feingranulare Metriken.

## Fortsetzung (Session 3)

### Umgesetzt
1. Feingranulare Not-Applied-Metriken umgesetzt
   - Dateien: `app/orchestrator/fallback_state_machine.py`, `app/orchestrator/pipeline_runner.py`
   - Für `signal_priority`, `strategy_feedback`, `persistent_priority` werden Not-Applied-Fälle jetzt getrennt gezählt in:
     - `disabled`
     - `not_applicable`
     - `no_reorder`
   - `*_applied_vs_not_applied.not_applied` basiert nun auf der Summe dieser Buckets statt auf einem pauschalen Restwert.

2. Tests erweitert
   - `tests/test_pipeline_runner_recovery.py` prüft neue Breakdown-Felder im Summary-Event.
   - `tests/test_fallback_state_machine.py` prüft, dass die neuen Counter durchgereicht und korrekt aggregiert werden.

3. Doku erweitert
   - `architecture.md` ergänzt um die neuen Breakdown-Felder im `model_recovery_summary`-Schema.

4. Verifikation
   - Ausgeführt: `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py`
   - Ergebnis: **17 passed**

### Kritische Selbstprüfung (Session 3)
- Positiv:
  - Telemetrie ist jetzt analytisch deutlich aussagekräftiger (Root-Cause-Cluster möglich, z. B. `disabled` vs `no_reorder`).
  - Bestehende Event-Verträge bleiben kompatibel; neue Felder sind additiv.
- Restrisiko:
  - Für `strategy_feedback` tritt `not_applicable` aktuell faktisch selten auf; Bucket ist vor allem zukunftssicher.
- Follow-up:
  - Optional Dashboard-/Alert-Mapping auf die neuen Breakdown-Felder (bisher rein Backend-seitig verfügbar).

## Fortsetzung (Session 4)

### Umgesetzt
1. P1 Security-Hardening für `run_command`
   - Datei: `app/tools.py`
   - `COMMAND_SAFETY_PATTERNS` um klar reproduzierbare Bypass-Varianten erweitert:
     - `cmd /c|/k rd|rmdir ...`
     - `powershell|pwsh ... iex|Invoke-Expression ...`
     - `bash|sh|zsh -c ...`

2. Security-Tests erweitert (negativ + positiv)
   - Datei: `tests/test_tools_command_security.py`
   - Neue Blockier-Tests für die obigen Varianten ergänzt.
   - Positive Kompatibilitäts-Tests ergänzt, damit legitime Basiskommandos weiter erlaubt bleiben (z. B. `echo hello`, `python --version`, `cmd /c echo hello`).

3. P1 Wartbarkeit im Recovery-Priority-Pfad umgesetzt
   - Datei: `app/orchestrator/pipeline_runner.py`
   - Deduplikation des `context_overflow`/`truncation_required`-Pfads über gemeinsame Helper:
     - `_resolve_reason_priority_config(...)`
     - `_apply_priority_recovery_pipeline(...)`
   - Lokale Typing-/Lesbarkeits-Nachschärfung über `RecoveryPriorityResolution` und präzisere Methoden-Docstrings.

4. Verifikation
   - Ausgeführt (Slice 1): `pytest -q tests/test_tools_command_security.py`
   - Ergebnis: **33 passed**
   - Ausgeführt (Slice 2): `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py`
   - Ergebnis: **17 passed**
   - Ausgeführt (Final Combined): `pytest -q tests/test_tools_command_security.py tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py`
   - Ergebnis: **50 passed**

### Kritische Selbstprüfung (Session 4)
- Positiv:
  - Security-Patterns decken zusätzliche praxisnahe Bypass-Vektoren ab, ohne Basiskommandos pauschal zu blocken.
  - Recovery-Priority-Code ist strukturell klarer und reduziert duplizierte Branch-Logik.
- Restrisiko:
  - Pattern-basierte Command-Sicherheit bleibt heuristisch; neue Shell-Syntaxvarianten können weiterhin nachgezogen werden müssen.
- Follow-up:
  - Optional: semantische Command-Policy (Tokenisierung/AST) als spätere Härtungsstufe.

## Kritische Selbstprüfung (zu den erledigten Tasks)
- Positiv:
  - Semantik von Telemetrie-Flags ist jetzt präziser, ohne Recovery-Laufzeitfluss zu verändern.
  - Niedriges Regressionsrisiko, da Änderungen lokal in Priorisierungs-Metadaten liegen.
- Restrisiko:
  - Downstream-Auswertungen könnten bisherige False-Positives implizit „erwartet“ haben.
- Abfederung:
  - Neue Regressionstests verhindern Rückfall in unpräzise Flag-Semantik.

## Priorisierte Next Tasks (für nächste Session)

### P0 — Recovery-Telemetrie Hardening fertigziehen
1. ✅ Additive Summary-Metriken ergänzt (`applied_vs_not_applied` je Signal/Feedback/Persistent)
2. ✅ Recovery-Event-Schema dokumentiert (architecture.md, tatsächlich emittierte Keys)
3. ✅ Tests für Event-Payload-Konsistenz ergänzt (`model_recovery_branch_selected` / `model_recovery_action`)
4. ✅ Feingranulare Not-Applied-Breakdowns ergänzt (`disabled` / `not_applicable` / `no_reorder`)

### P1 — Sicherheits-/Robustheits-Härtung Tooling
1. ✅ `COMMAND_SAFETY_PATTERNS` um 2–3 bekannte Bypass-Varianten erweitert
2. ✅ Negative/Positive-Tests in `tests/test_tools_command_security.py` ergänzt
3. ✅ Verifiziert, dass legitime Basiskommandos nicht geblockt werden

### P1 — Wartbarkeit
1. ✅ Kleine Deduplikation im Recovery-Priority-Pfad umgesetzt
2. ✅ Lokale Typing-/Docstring-Nachschärfung in `pipeline_runner.py` umgesetzt

### P2 — Optionale Folgearbeiten
1. Dashboard-/Alert-Mapping auf `*_not_applied_breakdown`-Felder
2. Optionaler semantischer Sicherheitscheck für `run_command` (über reine Regex-Patterns hinaus)

## Konkrete Agenda (nächste Session / Session 5)
1. Recovery-Metrik-Mapping spezifizieren
  - Ziel: klare Zuordnung der `model_recovery_summary`-Breakdowns zu Dashboard/Alert-Signalen.
2. Runbook ergänzen
  - Ziel: Diagnose-Matrix `disabled` / `not_applicable` / `no_reorder` mit empfohlenen Maßnahmen.
3. Monitoring-relevante Pflichtfelder testseitig absichern
  - Ziel: Payload-Tests auf notwendige Schlüssel erweitern, damit keine stillen Schema-Regressionen auftreten.

### Definition of Done (Session 5)
- Mapping und Runbook sind im Repo dokumentiert.
- Erweiterte Tests sind grün.
- Taskboard ist aktualisiert (Impact, Restrisiko, Follow-up).

## Fortsetzung (Session 5)

### Umgesetzt
1. Recovery-Metrik-Mapping spezifiziert
   - Neue Datei: `monitoring/RECOVERY_TELEMETRY_MAPPING.md`
   - Dashboard-/Alert-Zuordnung für `model_recovery_summary.details` ergänzt.

2. Operatives Recovery-Runbook ergänzt
   - Neue Datei: `RECOVERY_RUNBOOK.md`
   - Diagnose-Matrix für Buckets `disabled` / `not_applicable` / `no_reorder` inkl. Maßnahmen ergänzt.

3. Smoke-Runbook erweitert
   - Datei: `SMOKE_RUNBOOK.md`
   - Recovery-Telemetrie-Quickcheck und Verweise auf Mapping/Runbook ergänzt.

4. Monitoring-Pflichtfelder testseitig abgesichert
   - Datei: `tests/test_pipeline_runner_recovery.py`
     - Pflichtfeld-Check für `model_recovery_summary.details` ergänzt.
   - Datei: `tests/test_fallback_state_machine.py`
     - Key-Präsenz für `model_recovery_branch_selected` und `model_recovery_action` erweitert.

5. Verifikation
   - Ausgeführt: `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py`
   - Ergebnis: **18 passed**

### Kritische Selbstprüfung (Session 5)
- Positiv:
  - Operative Nutzbarkeit der Recovery-Telemetrie ist deutlich verbessert (Mapping + Handlungspfad).
  - Pflichtfeld-Tests reduzieren Risiko stiller Schema-Regressionen.
- Restrisiko:
  - Alert-Schwellen sind initial konservativ und müssen mit echten Lastprofilen nachkalibriert werden.
- Follow-up:
  - Session 6: semantische Command-Sicherheitsprüfung evaluieren + Alert-Tuning.

## Konkrete Agenda (nächste Session / Session 6)
1. Semantischen Sicherheitscheck für `run_command` evaluieren (ergänzend zu Regex)
2. Allowlist-Regression um legitime Cross-OS-Basisbefehle erweitern
3. Alert-Schwellen auf Recovery-Metriken anhand realer Daten kalibrieren

## Fortsetzung (Session 6 — Slice 1)

### Umgesetzt
1. Semantischen Sicherheitscheck für `run_command` ergänzt
   - Datei: `app/tools.py`
   - Neue semantische Erkennung als zweite Schicht nach Regex-Mustern für:
     - PowerShell Inline Remote-Code-Pull + dynamische Ausführung
     - PowerShell Base64-Decode + ScriptBlock-Ausführung

2. Security-Tests erweitert
   - Datei: `tests/test_tools_command_security.py`
   - Neue Negativfälle für semantische PowerShell-Muster ergänzt.
   - Positive Basiskommandos um `pwsh -NoProfile -Command Get-Date` erweitert.

3. Verifikation
   - Ausgeführt: `pytest -q tests/test_tools_command_security.py`
   - Ergebnis: **36 passed**

### Kritische Selbstprüfung (Session 6 — Slice 1)
- Positiv:
  - Sicherheitsabdeckung verbessert sich über reine Pattern-Matches hinaus.
  - Keine Regression in bestehenden Security-Tests.
- Restrisiko:
  - Semantik bleibt heuristisch; zusätzliche legitime Spezialfälle können bei Ausbau der Erkennung berücksichtigt werden müssen.
- Follow-up:
  - Session 6 Slice 2: Allowlist-Regression für legitime Cross-OS-Befehle erweitern.

## Konkrete Agenda (nächster Slice / Session 6 — Slice 2)
1. Allowlist-Regression um legitime Cross-OS-Basisbefehle erweitern
2. Danach Monitoring-Alert-Tuning vorbereiten

## Fortsetzung (Session 6 — Slice 2)

### Umgesetzt
1. Allowlist-Regression um legitime Cross-OS-Basisbefehle erweitert
   - Datei: `tests/test_tools_command_security.py`
   - Positive Regression ergänzt für:
     - `cmd.exe`, `powershell.exe`, `pwsh.exe`, `python.exe`
     - absolute Pfade für `/bin/bash`, `/bin/sh`, `/bin/zsh`

2. Negativfall für Allowlist-Härtung ergänzt
   - Sicheres, aber nicht allowlistetes Kommando (`git status`) wird weiterhin blockiert.

3. Verifikation
   - Ausgeführt: `pytest -q tests/test_tools_command_security.py`
   - Ergebnis: **44 passed**

### Kritische Selbstprüfung (Session 6 — Slice 2)
- Positiv:
  - Cross-OS-Whitelisting ist robuster abgesichert (inkl. Leader-Normalisierung über `.exe`/Pfade).
  - Sicherheit bleibt strikt: nicht allowlistete Commands werden weiterhin geblockt.
- Restrisiko:
  - Weitere projektspezifische Dev-Commands können je Teamumgebung ergänzungsbedürftig sein.
- Follow-up:
  - Nächster Slice: Monitoring-Alert-Tuning auf Recovery-Metriken.

## Konkrete Agenda (nächster Slice / Session 6 — Slice 3)
1. Alert-Schwellen aus `monitoring/RECOVERY_TELEMETRY_MAPPING.md` mit Betriebsprofilen kalibrierbar machen
2. Kurzes Tuning-Protokoll im Runbook ergänzen (Baseline, Rollout, Nachjustierung)

## Fortsetzung (Session 6 — Slice 3)

### Umgesetzt
1. Alert-Schwellen als kalibrierbare Profile dokumentiert
   - Neue Datei: `monitoring/RECOVERY_ALERT_PROFILES.md`
   - Profile ergänzt: `conservative`, `balanced`, `aggressive`.

2. Tuning-Protokoll in Doku verankert
   - Datei: `monitoring/RECOVERY_TELEMETRY_MAPPING.md`
   - Datei: `RECOVERY_RUNBOOK.md`
   - Baseline-, Canary- und Nachjustierungsprozess ergänzt.

### Kritische Selbstprüfung (Session 6 — Slice 3)
- Positiv:
  - Alert-Tuning ist jetzt reproduzierbar und teamfähig dokumentiert.
  - Rollout-Risiko sinkt durch klaren Profil- und Beobachtungsprozess.
- Restrisiko:
  - Schwellen bleiben ohne reale Lastdaten nur Startwerte.
- Follow-up:
  - Bei Verfügbarkeit von Betriebsdaten Profilwechsel protokolliert ausrollen.

## Fortsetzung (Session 6 — Wartbarkeit-Cleanup)

### Umgesetzt
1. Recovery-Reason/Branch-Mapping konsolidiert
   - Datei: `app/orchestrator/pipeline_runner.py`
   - Reason-Pattern und Non-Retryable-Branch-Mappings zentralisiert.

2. Regressionstests ergänzt
   - Datei: `tests/test_pipeline_runner_recovery.py`
   - Parametrisierte Tests für Reason-Klassifikation und Branch-Mapping ergänzt.

3. Verifikation
   - Ausgeführt: `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py tests/test_tools_command_security.py`
   - Ergebnis: **75 passed**

### Kritische Selbstprüfung (Session 6 — Wartbarkeit-Cleanup)
- Positiv:
  - Mapping-Logik ist zentraler und leichter wartbar, ohne Laufzeitverhalten zu ändern.
  - Neue parametrisierte Tests schützen gegen versehentliche Mapping-Regression.
- Restrisiko:
  - Weitere Typing-Nachschärfung in angrenzenden Helpers bleibt offen.
- Follow-up:
  - Nächster Slice: lokale Typing-/Contract-Nachschärfung im Orchestrator.

## Konkrete Agenda (nächster Slice / Session 7)
1. Lokale Typing-/Contract-Nachschärfung in `app/orchestrator/*` (ohne Verhaltensänderung)
2. Danach optional Vollsuite zur finalen Stabilitätsbestätigung

## Fortsetzung (Session 7)

### Umgesetzt
1. Lokale Typing-/Contract-Nachschärfung in `app/orchestrator/*`
   - Datei: `app/orchestrator/fallback_state_machine.py`
     - Konkrete Typen für `route` (`ModelRouteDecision`) und `send_event` (`SendEvent`) ergänzt.
     - `FallbackHooks` präzisiert (`agent -> AgentContract`, `_resolve_recovery_strategy -> RecoveryStrategyResolution`).
   - Datei: `app/orchestrator/pipeline_runner.py`
     - Route-Typen (`ModelRouteDecision`) an den Übergabeschnitten konkretisiert.

2. Verifikation
   - Ausgeführt: `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py tests/test_tools_command_security.py`
   - Ergebnis: **75 passed**

### Kritische Selbstprüfung (Session 7)
- Positiv:
  - Contracts an Orchestrator-Schnittstellen sind klarer und robuster dokumentiert.
  - Keine Verhaltensänderung; Regressionstests vollständig grün.
- Restrisiko:
  - Endgültige Gesamtstabilität ohne Vollsuite nur auf den fokussierten Suiten bestätigt.
- Follow-up:
  - Optional Vollsuite (`pytest -q tests`) als finalen Stabilitätsbeleg ausführen.

## Konkrete Agenda (nächster Slice / Session 8)
1. Optionaler Vollsuite-Lauf als finaler Stabilitätscheck
2. Danach Abschluss-Review und ggf. Merge-Vorbereitung

## Fortsetzung (Session 8)

### Umgesetzt
1. Finalen Vollsuite-Lauf durchgeführt
   - Ausgeführt: `pytest -q tests`
   - Ergebnis: **402 passed, 3 skipped**

2. Abschluss-Review durchgeführt
   - Security-, Recovery-, Operability- und Wartbarkeits-Slices sind durch fokussierte Suiten plus Vollsuite abgesichert.

### Kritische Selbstprüfung (Session 8)
- Positiv:
  - Stabilitätsnachweis ist jetzt nicht nur fokussiert, sondern vollumfänglich erbracht.
  - Session-Artefakte (Plan + Taskboard + Runbooks) sind synchron und anschlussfähig.
- Restrisiko:
  - Restaufgaben sind primär betriebsgetrieben (echte Last-/Incident-Daten).
- Follow-up:
  - Nur bei Bedarf incident-driven Nachjustierung (Alert-Schwellen, Policy-Feintuning).

## Konkrete Agenda (nächste Session)
1. Optional: incident-driven Tuning anhand realer Monitoring-Daten
2. Optional: Merge-/Release-Vorbereitung nach Teamprozess

## Arbeitsmodus für Folgesessions
- Pro Session maximal 1–2 zusammenhängende Refactoring-Slices.
- Nach jedem Slice:
  1. gezielte Tests
  2. kurze kritische Selbstprüfung (Impact, Restrisiko, Follow-up)
  3. Taskboard-Update

## Fortsetzung (Session 9 — HA-02/HA-03, 03.03.2026)

### Umgesetzt
1. HA-01 (schema-first Output) umgesetzt
   - Datei: `app/agents/planner_agent.py`
     - Hard-Research-Schema-Erkennung ergänzt.
     - Planner-Prompt für passende Hard-Requests um verbindlichen Struktur-Contract erweitert.
   - Datei: `app/agents/synthesizer_agent.py`
     - Hard-Research-Schema-Erkennung ergänzt.
     - Final-Prompt-Builder eingeführt und bei passenden Hard-Requests mit verpflichtendem Output-Schema erweitert.
   - Neue Tests:
     - `tests/test_planner_agent.py`
     - Erweiterung `tests/test_synthesizer_agent.py`

2. HA-02 (tests-first) umgesetzt
   - Neue Datei: `tests/test_hard_reasoning_output_contracts.py`
   - Positiv-/Negativ-Contract-Tests für Hard-Reasoning-Ausgaben ergänzt.
   - Drift-Schutz gegen Benchmark-Szenario eingebaut (Case-Contracts aus `benchmarks/scenarios/default.json`).

3. HA-03 (Benchmark-Qualität) umgesetzt
   - Datei: `benchmarks/scenarios/default.json`
     - Hard-Case-Split eingeführt:
       - `hard_reasoning_format` (gated)
       - `hard_reasoning_depth` (gated)
       - `hard_tools_diagnostic` (non-gated, bestehend)
   - Datei: `benchmarks/run_benchmark.py`
     - Latenz-Aggregation ergänzt: `p50/p95` für `duration_ms` und `first_token_ms`.
     - Summary um `latency_ms`-Block erweitert (gesamt + by_level).
     - CLI-Standard `--runs-per-case` von 1 auf 3 gesetzt.
   - Datei: `BENCHMARK_STRATEGY.md`
     - Strategie auf Hard-Case-Split und 3 Runs/Case als Standard aktualisiert.

4. Tests für HA-03-Metriken ergänzt
   - Neue Datei: `tests/test_run_benchmark_metrics.py`
   - Unit-Tests für Percentile-Berechnung und Latenz-Aggregation ergänzt.

### Verifikation
- Ausgeführt: `./.venv/Scripts/python.exe -m pytest tests/test_planner_agent.py tests/test_synthesizer_agent.py tests/test_hard_reasoning_output_contracts.py tests/test_run_benchmark_metrics.py -q`
- Ergebnis: **15 passed**

### Kritische Selbstprüfung (Session 9)
- Positiv:
  - Hard-Failure-Root-Causes sind jetzt besser trennbar (Format vs. Depth vs. Tools).
  - Benchmark-Reports enthalten robuste Latenzkennzahlen für Vergleich über Sprints.
  - Hard-Research-Requests werden im Planner/Synthesizer nun schema-first behandelt.
- Restrisiko:
  - Neue Hard-Cases können in frühen Läufen initial niedrigere Erfolgsraten zeigen (strengere Messung).
  - Schema-Erkennung basiert derzeit auf Keyword-Heuristik und kann bei stark abweichenden Formulierungen nicht triggern.
- Follow-up:
  - Nächster Slice: HA-04 (Recovery-Decision-Matrix) mit parametrierten Unit-Tests und Telemetrie-Abgleich.

## Fortsetzung (Session 10 — HA-04/HA-05, 03.03.2026)

### Umgesetzt
1. HA-04 (Recovery-Telemetrie-Vereinheitlichung) umgesetzt
   - Datei: `app/orchestrator/pipeline_runner.py`
   - `model_recovery_summary.details` additiv erweitert um:
     - `recovered_successfully`
     - `terminal_reason`
   - Semantik:
     - bei `final_outcome=success` => `recovered_successfully=true`, `terminal_reason=recovered`
     - bei `final_outcome=failure` => `recovered_successfully=false`, `terminal_reason=<final_reason|unknown>`

2. HA-04 Tests erweitert
   - Datei: `tests/test_pipeline_runner_recovery.py`
   - Pflichtfeld-Prüfungen auf `recovered_successfully` und `terminal_reason` ergänzt.
   - Failure-Pfad für `terminal_reason` explizit abgesichert.

3. HA-05 (bounded Replan-Fallback) umgesetzt
   - Datei: `app/agent.py`
   - Tool-Resultat-Klassifikation formalisiert:
     - `blocked`, `empty`, `error_only`, `usable`
   - Replan-Entscheidung formalisiert über `_resolve_replan_reason(...)`.
   - Neuer bounded Pfad:
     - genau ein Zusatz-Replan bei `empty`-Tool-Resultat (`tool_selection_empty_replan`), auch wenn `RUN_MAX_REPLAN_ITERATIONS=1`.
   - Replan-Telemetrie erweitert (`replanning_started`/`replanning_completed` Details mit Grund und Zählerständen).

4. HA-05 Tests ergänzt
   - Neue Datei: `tests/test_head_agent_replan_policy.py`
   - Klassifikations- und Replan-Policy-Tests für bounded empty fallback ergänzt.

5. HA-05 E2E-Nachweis (WS-Pfad) ergänzt
  - Datei: `tests/test_backend_e2e.py`
  - Neuer Test: `test_websocket_tool_selection_empty_triggers_single_replan_then_completes`
  - Verifiziert:
    - genau ein `replanning_started` mit `reason=tool_selection_empty_replan`
    - korrespondierendes `replanning_completed`
    - erfolgreicher Request-Abschluss (`request_completed`) ohne Endlosschleife

### Verifikation
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py -q`
- Ergebnis: **32 passed**
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_head_agent_replan_policy.py tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py -q`
- Ergebnis: **35 passed**
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_backend_e2e.py::test_websocket_tool_selection_empty_triggers_single_replan_then_completes tests/test_planner_agent.py tests/test_synthesizer_agent.py tests/test_hard_reasoning_output_contracts.py tests/test_run_benchmark_metrics.py tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py tests/test_head_agent_replan_policy.py -q`
- Ergebnis: **51 passed**

### Kritische Selbstprüfung (Session 10)
- Positiv:
  - Recovery-Summary ist operativ klarer (direktes Signal, ob Recovery final erfolgreich war).
  - Leere Tool-Selektion bekommt jetzt einen streng begrenzten Selbstheilungsversuch statt sofortigem Abbruch.
  - E2E bestätigt den neuen bounded Replan-Pfad im produktionsnahen WS-Lauf.
- Restrisiko:
  - OK/ERROR-Heuristik in Tool-Resultat-Klassifikation bleibt textbasiert.
- Follow-up:
  - Nächster Slice: WS-D (Tool-Policy-Diagnostikprofile + Klassifikationsschärfung `security`/`unsupported`/`env-missing`).

## Fortsetzung (Session 11 — WS-D Klassifikationsschärfung, 03.03.2026)

### Umgesetzt
1. WS-D Command-Policy-Kategorien in `run_command` implementiert
   - Datei: `app/tools.py`
   - Strukturierte Fehlercodes für Command-Policy-Pfade ergänzt:
     - `command_policy_security`
     - `command_policy_unsupported`
     - `command_policy_env_missing`
   - Einheitliche Fehlerdetails ergänzt (`details.category`, `details.leader`).

2. Security-/Unsupported-Pfade auf strukturierte Fehler umgestellt
   - Datei: `app/tools.py`
   - `_enforce_command_allowlist(...)` liefert jetzt den normalisierten Command-Leader zurück.
   - Safety- und Allowlist-Verstöße laufen über zentrale `_raise_command_policy_error(...)`.

3. `env-missing`-Diagnostik ergänzt
   - Datei: `app/tools.py`
   - Bei nicht erfolgreichem Exit + typischen „command not found / not recognized“-Signalen wird ein expliziter `env-missing`-Fehler geworfen statt stiller Rückgabe als normales Tool-Ergebnis.

4. Regressionstests für Kategorien ergänzt
   - Datei: `tests/test_tools_command_security.py`
   - Neue Tests validieren `error_code` und `details.category` für:
     - Security-Block (`shell chaining`)
     - Unsupported Command (`git` nicht allowlisted)
     - Env-Missing-Fall (allowlisted Command, simuliert nicht verfügbar)

### Verifikation
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_tools_command_security.py -q`
- Ergebnis: **47 passed**
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_head_agent_replan_policy.py -q`
- Ergebnis: **31 passed**
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_hard_reasoning_output_contracts.py tests/test_run_benchmark_metrics.py tests/test_planner_agent.py tests/test_synthesizer_agent.py -q`
- Ergebnis: **15 passed**
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_backend_e2e.py::test_websocket_tool_selection_empty_triggers_single_replan_then_completes -q`
- Ergebnis: **1 passed**

### Kritische Selbstprüfung (Session 11)
- Positiv:
  - Tool-Policy-Fehler sind jetzt operativ auswertbar und maschinenlesbar kategorisiert.
  - Bestehende Blockierlogik bleibt strikt; es wurde keine Security-Lockerung eingeführt.
- Restrisiko:
  - `env-missing`-Erkennung basiert auf robusten, aber textbasierten Shell-Signalen.
- Follow-up:
  - Optional: Kategorie-Propagation in Lifecycle/Telemetry explizit aufnehmen (z. B. `tool_failed.details.error_code`).

## Fortsetzung (Session 11b — WS-D Telemetry-Propagation, 03.03.2026)

### Umgesetzt
1. Kategorie-Propagation in Runtime-Telemetrie ergänzt
   - Datei: `app/services/tool_execution_manager.py`
   - Bei `ToolExecutionError` enthalten `error`-Event und `tool_failed`-Lifecycle jetzt additiv:
     - `error_code`
     - `error_category`

2. Retry-Fehlerkette metadata-stabilisiert
   - Datei: `app/services/tool_execution_manager.py`
   - Bei Web-Fetch-Retry-Failure bleibt der ursprüngliche `error_code` erhalten; vorhandene Details werden additiv mit Retry-Details zusammengeführt.

3. Regressionstest ergänzt
   - Datei: `tests/test_tool_execution_manager.py`
   - Neuer Test verifiziert, dass `tool_failed` und `error`-Event `command_policy_security` + `security` korrekt führen.

### Verifikation
- Ausgeführt: `./backend/.venv/Scripts/python.exe -m pytest tests/test_tool_execution_manager.py tests/test_tools_command_security.py -q`
- Ergebnis: **55 passed**
