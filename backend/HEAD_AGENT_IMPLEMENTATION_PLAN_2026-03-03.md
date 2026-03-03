# Head Agent — Implementierungsplan (03.03.2026)

## 1) Zielbild

Der Head Agent soll von einem robusten, aber in `hard`-Szenarien noch instabilen Orchestrator zu einem **zuverlässigen, selbstständigen Problemlöser** weiterentwickelt werden, der:

1. komplexe Aufgaben reproduzierbar in Teilaufgaben zerlegt,
2. Tool-Ausführung sicher und fehlertolerant steuert,
3. bei Fehlern adaptiv recovern kann,
4. die Ergebnisqualität strukturiert absichert,
5. über Benchmarking messbar verbessert wird.

---

## 2) Ausgangslage (Baseline)

### Codebasis (Backend)
- `backend/app`: **99 Python-Dateien**, ca. **16.392 LOC**
- `backend/tests`: **45 Python-Dateien**, ca. **10.206 LOC**

### Stabilitäts-/Qualitätslage
- Vollsuite laut Taskboard zuletzt: **402 passed, 3 skipped**
- Benchmark-Pipeline ist vorhanden (`backend/benchmarks/run_benchmark.py` + Szenario-Datei).
- Aktuelle Benchmark-Artefakte zeigen:
  - `easy`: stabil,
  - `mid`: überwiegend gut,
  - `hard` (insb. gated reasoning): noch instabil / teils 0% in letzten Läufen.

### Architekturstatus (hoch-level)
- Klar getrennte Rollen/Adapter vorhanden (`HeadAgentAdapter`, `CoderAgentAdapter`, `ReviewAgentAdapter`).
- Orchestrator + Recovery-Komponenten sind etabliert (`pipeline_runner`, `fallback_state_machine`, `recovery_strategy`).
- Tool-Policy und Security-Hardening existieren, aber limitieren in bestimmten Diagnostik-/Hard-Tool-Cases bewusst den Handlungsspielraum.

---

## 3) Zielmetriken (6–8 Wochen, sprintbasiert)

1. **Gated Hard Success Rate**: von aktuell niedrig/instabil auf **>= 70%**
2. **Gated Gesamt-Success**: **>= 85%** über mindestens 3 Benchmark-Läufe
3. **First Token Latenz (`hard`)**: p95 um **>= 20%** reduzieren
4. **Recovery-Wirksamkeit**: Anteil erfolgreich abgeschlossener Recovery-Pfade auf **>= 60%**
5. **Tool-Failure mit vermeidbarer Ursache** (Allowlist/Args/Format): um **>= 50%** senken

Hinweis: Zielwerte sind ambitioniert; falls Produkt-/Policy-Constraints greifen, werden sie nach Sprint 2 datenbasiert nachkalibriert.

---

## 4) Scope / Nicht-Scope

### In Scope
- Head-Agent-Laufzeitpfad (Planung, Tool-Selektion, Synthese)
- Orchestrierungs- und Recovery-Mechanik
- Tool-Policy-Interaktion im produktionsnahen Rahmen
- Benchmark- und Testabdeckung für Hard-Szenarien
- Operative Telemetrie und Diagnosefähigkeit

### Nicht-Scope (dieser Plan)
- Frontend-UX-Redesign
- Neue externe Plattform-Integrationen ohne klaren Benchmark-Mehrwert
- Vollständige Neuarchitektur des Agenten (stattdessen inkrementelle Härtung)

---

## 5) Workstreams mit konkreten Umsetzungsaufgaben

## WS-A — Hard-Reasoning-Output zuverlässig strukturieren

**Ziel:** Hard-Rechercheantworten erfüllen konsistent geforderte Struktur-/Regex-Kriterien.

**Dateien (primär):**
- `backend/app/agent.py`
- `backend/app/agents/planner_agent.py`
- `backend/app/agents/synthesizer_agent.py`
- `backend/app/services/reply_shaper.py`

**Aufgaben:**
1. Struktur-Contracts für Hard-Antworten definieren (z. B. feste Sections, KPI-Block, Phasen-Format).
2. Planner-Ausgabe auf explizites Section-Schema trimmen.
3. Synthesizer mit „schema-first“ Prompting + self-check vor Finalisierung erweitern.
4. ReplyShaper um minimale Strukturerhaltungsregeln erweitern (ohne Overfitting).

**DoD WS-A:**
- Hard-Reasoning-Case besteht in >= 7/10 Läufen lokal.
- Regex-bedingte Failures sinken signifikant (Trend im Benchmark-Ordner sichtbar).

---

## WS-B — Tool-Selektion robuster gegen Leerselektion/Fehlgriff

**Ziel:** Weniger unnötige „tool_selection_empty/failed“-Pfade bei komplexen Aufgaben.

**Dateien (primär):**
- `backend/app/agent.py`
- `backend/app/agents/tool_selector_agent.py`
- `backend/app/orchestrator/step_executors.py`
- `backend/app/services/action_parser.py`
- `backend/app/services/action_augmenter.py`

**Aufgaben:**
1. Tool-Auswahlentscheidungen um Confidence- und Fallback-Regeln ergänzen.
2. Bei Leerselektion kontrollierten Replan-Slot einführen (einmalig, bounded).
3. Aktion-Parsing mit „repair hints“ gegen häufige Fehlformate härten.
4. Instrumentierung: Ursachenklassen für Tool-Fehlentscheidungen emitten.

**DoD WS-B:**
- Anteil `tool_selection_empty` in Mid/Hard messbar reduziert.
- Replan-Fallback erhöht Pass-Rate ohne Event-Stürme.

---

## WS-C — Recovery-Policy für echte Selbstheilung statt nur Fail-Fast

**Ziel:** Recovery-Pfade führen öfter zu erfolgreichem Abschluss.

**Dateien (primär):**
- `backend/app/orchestrator/pipeline_runner.py`
- `backend/app/orchestrator/fallback_state_machine.py`
- `backend/app/orchestrator/recovery_strategy.py`

**Aufgaben:**
1. Recovery-Entscheidungen um „error class -> next best action“ Matrix erweitern.
2. Retry-/Backoff-Politik für transient errors verfeinern.
3. Adaptive Priorisierung von Modell-/Tool-Alternativen nach Fehlerhistorie je Session.
4. Recovery-Telemetrie um „recovered_successfully“ und „terminal_reason“ vereinheitlichen.

**DoD WS-C:**
- Recovery-Erfolgsquote steigt auf >= 60% in Hard-Diagnostikläufen.
- Keine Regression in bestehenden Recovery-Tests.

---

## WS-D — Tool-Policy operativ machen (streng, aber handlungsfähig)

**Ziel:** Sicherheitsmodell bleibt strikt, blockiert aber sinnvolle Diagnostik nicht unnötig.

**Dateien (primär):**
- `backend/app/tool_policy.py`
- `backend/app/tools.py`
- `backend/app/services/tool_call_gatekeeper.py`
- `backend/tests/test_tools_command_security.py`

**Aufgaben:**
1. Häufige legitime Diagnose-Kommandos als kontrollierte, auditierbare Profile definieren.
2. `allow/deny/also_allow`-Auflösung für Sessions transparenter machen (Telemetry + Debug-Hinweis).
3. Command-Policy-Verstöße besser kategorisieren (security vs. unsupported vs. env-missing).
4. Regressionstests für Cross-OS-Befehle und neue Profile ergänzen.

**DoD WS-D:**
- Weniger vermeidbare Tool-Fehler in Hard-Tools-Diagnostik.
- Sicherheits-Tests bleiben vollständig grün.

---

## WS-E — Subrun-Orchestrierung für komplexe Tasks ausbauen

**Ziel:** Head Agent delegiert kontrolliert und effektiv bei Mehrschrittaufgaben.

**Dateien (primär):**
- `backend/app/agent.py`
- `backend/app/subrun_endpoints.py`
- `backend/app/orchestrator/subrun_lane.py`
- `backend/app/custom_agents.py`

**Aufgaben:**
1. Delegationskriterien explizit machen (wann Subrun statt monolithischer Antwort).
2. Subrun-Resultate standardisiert in Hauptlauf rückführen (inkl. Confidence).
3. Retry-/Timeout-Verhalten für Subruns robust machen.
4. Kosten-/Tiefe-Limits pro Session in Telemetrie offenlegen.

**DoD WS-E:**
- `mid_orchestration_subrun` gated stabil grün über 3 Läufe.
- Keine Lane-Leaks / Hanging-Subruns in Tests.

---

## WS-F — Benchmark-Qualität erhöhen (weniger Rauschen, mehr Aussagekraft)

**Ziel:** Benchmarks steuern Entwicklung direkt und reproduzierbar.

**Dateien (primär):**
- `backend/benchmarks/scenarios/default.json`
- `backend/benchmarks/run_benchmark.py`
- `backend/BENCHMARK_STRATEGY.md`

**Aufgaben:**
1. Hard-Cases in 2–3 präzise Failure-Typen splitten (Format, Reasoning, Tools).
2. Pro Case 3 Runs als Standard für Stabilitätsaussage (statt 1).
3. Aggregierte Kennzahlen um p50/p95 für `first_token_ms`/`duration_ms` erweitern.
4. Gating-Regeln klar trennen: Qualitätsgating vs. reine Diagnosefälle.

**DoD WS-F:**
- Benchmark-Reports erlauben eindeutige Root-Cause-Zuordnung.
- CI-geeignete Schwellenwerte dokumentiert.

---

## WS-G — Teststrategie für Agent-Intelligenz und Contracts

**Ziel:** Neue Fähigkeiten sind testbar, nicht nur „Prompt-Glück“.

**Dateien (primär):**
- `backend/tests/test_backend_e2e.py`
- `backend/tests/test_subrun_lane.py`
- `backend/tests/test_pipeline_runner_recovery.py`
- neue fokussierte Tests in `backend/tests/`

**Aufgaben:**
1. Contract-Tests für Strukturpflichten im Hard-Output ergänzen.
2. Deterministische Unit-Tests für Recovery-Entscheidungsmatrix ergänzen.
3. Tool-Selection-Fallback-Pfade mit synthetischen Fixtures abdecken.
4. E2E-Smoke für delegierte Mehrschrittfälle aufbauen.

**DoD WS-G:**
- Kritische neue Pfade sind unit- oder contract-tested.
- Keine neuen fragilen Flaky-Tests.

---

## WS-H — Operative Transparenz und Runbooks

**Ziel:** Oncall/Entwicklung kann Fehlerbilder schnell einordnen und beheben.

**Dateien (primär):**
- `backend/RECOVERY_RUNBOOK.md`
- `backend/SMOKE_RUNBOOK.md`
- `backend/monitoring/RECOVERY_TELEMETRY_MAPPING.md`
- `backend/monitoring/RECOVERY_ALERT_PROFILES.md`

**Aufgaben:**
1. Failure-Taxonomie (Reasoning, ToolPolicy, Recovery, Timeout, Context) vereinheitlichen.
2. Für jede Klasse: Detection-Signal, Sofortmaßnahme, dauerhafte Maßnahme dokumentieren.
3. Alert-Profile an neue Metriken koppeln und Rollout-Prozess schärfen.

**DoD WS-H:**
- Runbooks decken Top-Fehlerklassen vollständig ab.
- Reproduzierbare Incident-Triage ohne Implizitwissen.

---

## 6) Meilensteinplan (Sprint-basiert)

## Sprint 1 (Woche 1–2): Stabilitätsfundament Hard-Reasoning
- Fokus: WS-A + WS-F (Teil) + WS-G (Teil)
- Primärziel: regex-/strukturbedingte Hard-Fails stark reduzieren
- Exit-Kriterium: Hard-Reasoning >= 50% bei 10 lokalen Runs

## Sprint 2 (Woche 3–4): Tool-/Recovery-Robustheit
- Fokus: WS-B + WS-C + WS-D
- Primärziel: weniger vermeidbare Tool-Fails, höhere Recovery-Erfolgsrate
- Exit-Kriterium: Gated gesamt >= 75%, Hard gesamt >= 60%

## Sprint 3 (Woche 5–6): Delegation + Operative Reife
- Fokus: WS-E + WS-H + WS-F final
- Primärziel: verlässliche Subrun-Orchestrierung + belastbare Telemetrie
- Exit-Kriterium: Gated gesamt >= 85%, Hard gated >= 70%

## Sprint 4 (Woche 7–8, optional): Feintuning & CI-Gating
- Fokus: Threshold-Kalibrierung, Flaky-Reduktion, Dokumentation final
- Exit-Kriterium: 3 aufeinanderfolgende stabile Benchmark-Runs im Zielkorridor

---

## 7) Priorisierter Umsetzungs-Backlog (konkret)

1. **P0:** Hard-Output-Contract in Planner/Synthesizer einziehen (WS-A)
2. **P0:** Hard-Benchmark-Cases nach Failure-Typ splitten (WS-F)
3. **P0:** Recovery-Entscheidungsmatrix implementieren + Tests (WS-C/WS-G)
4. **P1:** Tool-Selection-Replan-Fallback einführen (WS-B)
5. **P1:** Tool-Policy-Profile für legitime Diagnostik ergänzen (WS-D)
6. **P1:** Subrun-Delegationskriterien operationalisieren (WS-E)
7. **P2:** Runbooks/Alerting konsolidieren und schärfen (WS-H)

---

## 8) Risiken und Gegenmaßnahmen

1. **Overfitting auf Benchmark-Regex**
   - Gegenmaßnahme: Struktur-Contract + semantische Inhaltschecks kombinieren.
2. **Mehr Logik = mehr Latenz**
   - Gegenmaßnahme: harte Limits für Replan/Retry, p95-Latenz pro Sprint tracken.
3. **Security vs. Capability Konflikt**
   - Gegenmaßnahme: profilierte Allowlist statt globaler Aufweichung, volle Audit-Telemetrie.
4. **Flaky E2E-Tests**
   - Gegenmaßnahme: kritische Logik in deterministische Unit-/Contract-Tests verschieben.

---

## 9) Mess- und Review-Rhythmus

- Nach jedem Sprint:
  1. `pytest -q tests`
  2. Benchmark-Lauf mit mindestens 3 Runs/Case
  3. Vergleich gegen Zielmetriken
  4. Taskboard-Update mit Impact, Restrisiko, Follow-up

- Review-Template pro Sprint:
  - Was verbessert? (Metrik)
  - Was bleibt instabil? (Root Cause)
  - Welche Maßnahme im nächsten Sprint?

---

## 10) Umsetzungsstart (erste 5 konkreten Tickets)

1. Ticket HA-01: Hard-Output-Schema in `planner_agent` + `synthesizer_agent`
2. Ticket HA-02: Regex/Structure-Contract-Tests für Hard-Reasoning-Output
3. Ticket HA-03: Benchmark-Szenario-Split (`hard_reasoning_format`, `hard_reasoning_depth`, `hard_tools_diagnostic`)
4. Ticket HA-04: Recovery-Decision-Matrix in `fallback_state_machine` + Unit-Tests
5. Ticket HA-05: Tool-Selection-Replan-Fallback (1 Versuch, bounded) + Telemetrie

---

## 11) Gesamt-Definition of Done (Programm)

Der Implementierungsplan gilt als erfolgreich abgeschlossen, wenn:

1. die Zielmetriken aus Abschnitt 3 in mindestens 3 aufeinanderfolgenden Benchmark-Runs erreicht werden,
2. die Vollsuite stabil grün bleibt,
3. Runbooks/Monitoring-Dokumente den neuen Betriebszustand vollständig abbilden,
4. die verbleibenden Restrisiken explizit dokumentiert und priorisiert sind.

---

## 12) Fehlervermeidungs-Protokoll (verbindlich)

Dieses Protokoll ist für jede Implementierung in diesem Plan verpflichtend. Ziel ist, Regressionen früh zu stoppen und riskante Änderungen kontrolliert auszurollen.

### 12.1 Go/No-Go Gates pro Änderung

Jede Änderung muss diese Gates in Reihenfolge passieren:

1. **Design-Gate (vor Coding)**
   - Betroffene Dateien, Risiken, Fallback-Strategie in 3–5 Punkten notieren.
   - Änderungen auf **ein Workstream-Ziel** begrenzen (kein Scope-Mix).
2. **Unit/Contract-Gate (lokal, kleinster Scope)**
   - Nur relevante Tests zuerst ausführen.
   - Bei Fehlern: sofort stoppen, Root Cause fixen, erneut laufen lassen.
3. **Slice-Gate (Workstream-Scope)**
   - Alle Tests des betroffenen Workstreams grün.
   - Telemetrie-/Event-Felder auf Schema-Konsistenz prüfen.
4. **Suite-Gate (Integrationssicherheit)**
   - `pytest -q tests` oder definierte Vollsuite erfolgreich.
5. **Benchmark-Gate (Qualitätsnachweis)**
   - Betroffene Cases mit mindestens 3 Runs/Case.
   - Keine Verschlechterung der Gated-Metriken gegenüber letzter stabiler Baseline.

Wenn ein Gate fehlschlägt: **kein Weiterarbeiten am nächsten Gate**, erst Stabilisierung.

### 12.2 Änderungsregeln zur Risikobegrenzung

1. **Maximalprinzip pro PR/Slice**
   - Max. ein primäres Ziel + ein eng gekoppelter Nebeneffekt.
2. **Keine stillen Contract-Änderungen**
   - Event-/Schema-Felder nur additiv ändern oder explizit migrieren.
3. **Keine gleichzeitige Prompt- und Logik-Neuverdrahtung**
   - Erst Prompt/Output-Form stabilisieren, dann Laufzeitlogik ändern (oder umgekehrt).
4. **Feature Flags für riskante Pfade**
   - Neue Recovery-/Replan-Pfade standardmäßig guarded ausrollen.
5. **Deterministische Defaults**
   - Timeouts, Retry-Limits, Max-Depth immer explizit setzen.

### 12.3 Pflicht-Testmatrix je Workstream

- **WS-A (Reasoning-Output):**
  - Contract-Tests auf strukturierte Sections + KPI-Muster.
  - Negativtests: absichtlich unstrukturierte Ausgabe muss erkannt werden.
- **WS-B (Tool-Selection):**
  - Unit-Tests für Leerselektion, Replan einmalig, Abbruch nach Limit.
  - Event-Tests für Ursachenklassifikation.
- **WS-C (Recovery):**
  - Entscheidungs-Matrix als parametrisierte Unit-Tests.
  - Retry/Backoff-Verhalten inkl. terminalem Abbruchgrund.
- **WS-D (Tool-Policy):**
  - Security-Negativfälle + legitime Cross-OS-Positivfälle.
  - Tests für `allow/deny/also_allow`-Auflösung.
- **WS-E (Subrun):**
  - Lane-/Timeout-/Hanging-Tests.
  - Delegationskriterien und Rückführung in Hauptlauf.
- **WS-F (Benchmarks):**
  - Parser-/Aggregationstests für p50/p95 und Gating.
  - Validierung der Case-Splits.
- **WS-G (Teststrategie):**
  - Flaky-Schutz: feste Seeds/Fixtures, keine zeitabhängigen Assertions ohne Toleranz.
- **WS-H (Runbooks/Monitoring):**
  - Doku-Checks: alle neuen Telemetrie-Felder und Alert-Profile referenziert.

### 12.4 Minimaler Implementierungsablauf pro Ticket

1. Ticket-Intent in 1 Satz formulieren (Problem + messbares Ziel).
2. Betroffene Dateien und Nicht-Ziele festhalten.
3. Änderung in kleinsten commit-fähigen Schritten implementieren.
4. Relevante Tests (klein) → Workstream-Tests (mittel) → Suite (groß).
5. Benchmark-Case(s) laufen lassen, Metriken gegen Baseline prüfen.
6. Taskboard aktualisieren: Impact, Restrisiko, Follow-up.

### 12.5 Stop-Kriterien (sofortiger Abbruch der aktuellen Änderung)

Änderung sofort stoppen und auf letzte stabile Variante zurück, wenn mindestens eines zutrifft:

1. Gleicher Fehler tritt nach 3 zielgerichteten Fixversuchen unverändert auf.
2. Vollsuite bricht mit neuen, nicht erklärbaren Fehlerclustern.
3. Gated-Metrik sinkt in zwei aufeinanderfolgenden Benchmark-Runs.
4. Event-/Schema-Contract wird unbeabsichtigt verletzt.

### 12.6 Rollback- und Recovery-Protokoll

1. Letzten stabilen Commit/State markieren.
2. Riskante Änderung per Feature Flag deaktivieren oder revertieren.
3. Relevante Tests + betroffene Benchmarks erneut ausführen.
4. Incident-Notiz im Taskboard: Ursache, Auswirkung, nächste sichere Iteration.

### 12.7 Verbindliche Qualitäts-Checkliste vor Abschluss eines Slices

- Zielmetrik des Slices verbessert oder mindestens nicht verschlechtert.
- Keine neue Flakiness in den betroffenen Tests.
- Keine unbeabsichtigte Contract-/Schema-Änderung.
- Latenz-/Retry-Limits weiterhin innerhalb definierter Schranken.
- Runbook/Monitoring-Doku bei neuen Feldern/Pfaden aktualisiert.

---

## 13) Konkrete Implementierungsreihenfolge (fehlerarm)

Empfohlene Ausführung, um Risiko zu minimieren:

1. **HA-02 vor HA-01:** erst Contract-Tests schreiben, dann Output-Schema implementieren.
2. **HA-03 früh:** Benchmark-Cases splitten, damit spätere Verbesserungen sauber messbar sind.
3. **HA-04 vor HA-05:** erst Recovery-Matrix stabilisieren, dann Replan-Fallback aktivieren.
4. **WS-D parallel zu WS-B/C:** Tool-Policy-Fehler früh klassifizieren, damit Diagnose klar bleibt.
5. **WS-E erst nach WS-B/C stabil:** Delegation erst ausbauen, wenn Kernpfade reproduzierbar sind.

Diese Reihenfolge reduziert Fehlinterpretationen, weil Messung, Recovery und Policy zuerst stabilisiert werden und neue Komplexität erst danach hinzukommt.

---

## 14) Operativer Tagesplan (pro Umsetzungstag)

1. **Start (15 min):** Baseline prüfen (letzte grüne Tests + letzte Benchmark-Metriken).
2. **Build-Phase (90–150 min):** genau ein Ticket-Slice implementieren.
3. **Test-Phase (30–60 min):** Pflicht-Testmatrix für den Slice ausführen.
4. **Benchmark-Phase (20–45 min):** nur betroffene Cases, mindestens 3 Runs/Case.
5. **Dokuphase (10–20 min):** Taskboard + ggf. Runbook aktualisieren.

Dadurch wird jede Änderung am selben Tag vollständig verifiziert und das Risiko kumulierter Fehler sinkt deutlich.

---

## 15) Detaillierte Ticket-Spezifikationen

Die konkrete Ausarbeitung der ersten Umsetzungstickets (HA-01 bis HA-05) ist in folgender Datei dokumentiert:

- `backend/HEAD_AGENT_TICKET_SPECS_2026-03-03.md`

Diese Spezifikation enthält pro Ticket:
- Ziel / Nicht-Ziele
- betroffene Dateien
- Implementierungsschritte
- Akzeptanzkriterien
- Testkommandos
- Risiken, Gegenmaßnahmen und Rollback-Pfad
