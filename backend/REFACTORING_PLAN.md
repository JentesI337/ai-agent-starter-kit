# Backend Refactoring Plan — Detailliert & Priorisiert (Arbeitsstand)

Stand: 02.03.2026  
Scope: Backend (`backend/`)  
Ziel: Stabiler, testbarer, sicherer Runtime- und Orchestrator-Stack mit klarer Session-Agenda.

---

## 1. Strategie

### Aktueller Gesamtstatus
- ✅ Phase 0 (Sicherheitskritische Sofortmaßnahmen) umgesetzt.
- ✅ Phase 1 (HeadAgent-God-Class-Aufbruch) umgesetzt.
- ✅ Phase 2 (kritische Test-Coverage) umgesetzt.
- ✅ Phase 3 (Architektur-Bereinigung) umgesetzt.
- ✅ Phase 4 (Pipeline-Runner Refactoring) umgesetzt.
- ✅ Phase 5 (Feature-Verbesserungen, Kernpunkte) umgesetzt.
- ✅ Optionales Recovery-Telemetrie-Hardening umgesetzt (Session 1–3).
- ✅ P1-Security + P1-Wartbarkeit umgesetzt (Session 4).
- ✅ P2 Operability-Slice umgesetzt (Session 5: Mapping + Runbook + Pflichtfeld-Tests).

### Session-4 Delta (neu)
1. `run_command`-Sicherheitsmuster erweitert (`COMMAND_SAFETY_PATTERNS`)
   - `cmd /c|/k ... rd|rmdir`
   - `powershell|pwsh ... iex|Invoke-Expression`
   - `bash|sh|zsh -c`
2. Security-Tests erweitert (`tests/test_tools_command_security.py`)
   - Negative Bypass-Fälle + positive Basiskommandos.
3. Recovery-Priority-Deduplikation in `pipeline_runner.py`
   - Helper: `_resolve_reason_priority_config(...)`
   - Helper: `_apply_priority_recovery_pipeline(...)`
   - Typing-Nachschärfung: `RecoveryPriorityResolution`
4. Verifikation
   - `pytest -q tests/test_tools_command_security.py` → **33 passed**
   - `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py` → **17 passed**
   - Kombiniert → **50 passed**

### Session-5 Delta (neu)
1. Monitoring-Mapping ergänzt
   - Neue Datei: `monitoring/RECOVERY_TELEMETRY_MAPPING.md`
2. Operatives Recovery-Runbook ergänzt
   - Neue Datei: `RECOVERY_RUNBOOK.md`
3. Smoke-Runbook erweitert
   - Datei: `SMOKE_RUNBOOK.md` um Recovery-Telemetrie-Quickcheck ergänzt
4. Monitoring-Pflichtfelder testseitig abgesichert
   - Dateien: `tests/test_pipeline_runner_recovery.py`, `tests/test_fallback_state_machine.py`

### Session-6 Delta (Slice 1)
1. Semantischer Command-Sicherheitscheck ergänzt
   - Datei: `app/tools.py`
   - Neue zweite Schutzschicht neben Regex-Patterns für riskante PowerShell-Inline-Ausführungsmuster:
     - Remote-Code-Pull + dynamische Ausführung
     - Base64-Decoding + ScriptBlock-Ausführung
2. Security-Tests erweitert
   - Datei: `tests/test_tools_command_security.py`
   - Neue Negativfälle für semantische PowerShell-Muster
   - Positive Basiskommandos erweitert (`pwsh -NoProfile -Command Get-Date`)
3. Verifikation
   - `pytest -q tests/test_tools_command_security.py` → **36 passed**

### Session-6 Delta (Slice 2)
1. Allowlist-Regression erweitert
   - Datei: `tests/test_tools_command_security.py`
   - Cross-OS-Basiskommandos (inkl. `.exe`/absoluter Pfade für `cmd`, `powershell`, `pwsh`, `python`, `bash`, `sh`, `zsh`) als positive Regression ergänzt.
   - Negativfall ergänzt: sicheres, aber nicht allowlistetes Kommando (`git status`) wird korrekt blockiert.
2. Verifikation
   - `pytest -q tests/test_tools_command_security.py` → **44 passed**

### Session-6 Delta (Slice 3)
1. Monitoring-Alert-Tuning dokumentiert
   - Neue Datei: `monitoring/RECOVERY_ALERT_PROFILES.md`
   - Profile `conservative` / `balanced` / `aggressive` mit kalibrierbaren Schwellen ergänzt.
2. Mapping/Runbook erweitert
   - Dateien: `monitoring/RECOVERY_TELEMETRY_MAPPING.md`, `RECOVERY_RUNBOOK.md`
   - Profilbasierte Kalibrierung + Tuning-Protokoll (Baseline, Canary, Nachjustierung) ergänzt.

### Session-6 Delta (Wartbarkeit-Cleanup)
1. Recovery-Reason/Branch-Mapping konsolidiert
   - Datei: `app/orchestrator/pipeline_runner.py`
   - Zentrale Reason-Pattern- und Branch-Mappings extrahiert (`FAILOVER_REASON_PATTERNS`, `NON_RETRYABLE_FAIL_FAST_BRANCH_BY_REASON`).
2. Regressionstests ergänzt
   - Datei: `tests/test_pipeline_runner_recovery.py`
   - Parametrisierte Tests für Failover-Reason-Klassifikation und Branch-Resolution ergänzt.
3. Verifikation
   - `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py tests/test_tools_command_security.py` → **75 passed**

### Session-7 Delta (Typing/Contracts)
1. Lokale Contract-Nachschärfung im Orchestrator
   - Dateien: `app/orchestrator/fallback_state_machine.py`, `app/orchestrator/pipeline_runner.py`
   - Konkrete Typen für Route-/SendEvent-Übergaben ergänzt (`ModelRouteDecision`, `SendEvent`).
   - `FallbackHooks`-Protocol für `agent` und `_resolve_recovery_strategy(...)` präzisiert.
2. Verifikation
   - `pytest -q tests/test_pipeline_runner_recovery.py tests/test_fallback_state_machine.py tests/test_recovery_strategy.py tests/test_tools_command_security.py` → **75 passed**

### Session-8 Delta (Finale Stabilitätsverifikation)
1. Vollsuite ausgeführt
   - `pytest -q tests`
   - Ergebnis: **402 passed, 3 skipped**
2. Abschlussstatus
   - Kernphasen + nachgelagerte Hardening-/Operability-Slices sind stabil verifiziert.

---

## 2. Offene Arbeit (ab jetzt)

Die Kernphasen sind abgeschlossen. Offene Punkte sind **gezieltes Hardening und Operability**.

### P2 — Operability / Observability (nächste sinnvolle Priorität)
1. ✅ Dashboard-/Alert-Mapping auf Recovery-Breakdowns dokumentiert
2. ✅ Runbook für Interpretation der Recovery-Metriken ergänzt
3. ✅ Monitoring-Pflichtfelder in Tests abgesichert
4. ✅ Alert-Schwellen als kalibrierbare Profile dokumentiert

### P2 — Command Security (optional, aber high-value)
1. ✅ Semantischer Sicherheitscheck als ergänzende Schicht umgesetzt (Session 6, Slice 1)
2. ✅ Allowlist-Regression für legitime Cross-OS-Basisbefehle erweitert (Session 6, Slice 2)

### P2 — Wartbarkeit / Cleanup
1. ✅ Kleinere Konsolidierung von Recovery-Reason-/Branch-Mapping umgesetzt
2. ✅ Lokale Typing-Nachschärfung in Orchestrator-Modulen mit hoher Entscheidungsdichte

---

## 3. Qualitätsgates (verbindlich)

Für jeden Slice:
1. gezielte Tests für den geänderten Scope,
2. kurze kritische Selbstprüfung (Impact, Restrisiko, Follow-up),
3. Dokumentation/Taskboard synchronisieren.

Empfohlene Test-Reihenfolge:
1. betroffene Tests (`-q` gezielt),
2. benachbarte Recovery-/Security-Suites,
3. optional Vollsuite bei größerem Eingriff.

---

## 4. Nächste Session — konkrete Agenda (Session 6)

### Ziel
Abschluss erledigt; weitere Sessions nur bei neuen Anforderungen/Incidents.

### Arbeitspakete
1. **Optional: Incident-driven Nachjustierung**
   - Nur bei realen Betriebsdaten/Incidents gezielte Threshold- oder Policy-Anpassungen.

### Definition of Done
- Vollsuite ist grün.
- Plan/Taskboard sind aktualisiert.
- Offene Agenda ist auf optionales Incident-Driven-Tuning reduziert.

---

## 5. Hinweise zur Kontinuität

- Dieses Dokument ist der persistente Arbeitsplan im Repo.
- Detailverlauf je Session bleibt im `SESSION_TASKBOARD_2026-03-02.md`.
- Bei Scope-Änderungen zuerst Priorität (P0/P1/P2) und Erfolgskriterium aktualisieren.
