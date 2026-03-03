# Head Agent → OpenAgent-Niveau: Sessionübergreifender Masterplan (03.03.2026)

## 0) Zielsetzung

Ziel ist, den Head-Agent in `backend/app/agent.py` und angrenzender Orchestrierung so auszubauen, dass er im Scope **Prompt -> Lifecycle -> Response** möglichst nahe an das OpenAgent-Level herankommt.

### Harte Nicht-Ziele (explizit ignorieren)
- Gateway-Features
- History-Subsysteme
- Memory-Subsysteme

Das gilt sowohl für Architekturarbeit als auch für Ticketpriorisierung.

---

## 1) Zielbild (Paritäts-Backbone)

Wir bauen nicht „alles“ nach, sondern die **leistungsrelevanten Kerneigenschaften**:

1. **Event-/Lifecycle-first Laufzeit**
   - klare Start/Tool/Assistant/End-Phasen
   - robustes Streaming- und Finalisierungsverhalten

2. **Resilienter Tool-Loop**
   - mehrstufige Tool-Policy-Pipeline
   - before/after-tool Hooks
   - Tool-Loop-Detection + sichere Degradierung

3. **Recovery-Engine auf Produktionsniveau**
   - Retry/Failover-Strategien mit Ursachenklassen
   - Overflow-/Timeout-Recovery ohne „silent fail“

4. **Agency-Ausbau über Subruns**
   - kontrollierte Delegation (wann/warum/wie)
   - standardisierte Rückführung von Subrun-Ergebnissen

5. **Schema-stabile Response-Qualität**
   - strukturierte Synthese
   - post-synthesis shaping mit klaren Contracts

---

## 2) Transformationsprinzipien (damit es wirklich funktioniert)

1. **Inkrementell statt Big Bang**
   - pro Session nur 1-2 Kernänderungen, immer mit Gate.

2. **Event-/Contract-first statt Prompt-Tuning-only**
   - Stabilität kommt primär aus Laufzeitverträgen, nicht aus längeren Prompts.

3. **Feature Flags für alle riskanten Änderungen**
   - jeder neue Pfad muss aktivierbar/deaktivierbar sein.

4. **Messbarkeit als harte Bedingung**
   - keine Änderung ohne Telemetrie und Benchmark-Signal.

5. **Regressionen sofort stoppen**
   - bei Gate-Fail sofort Root-Cause-Fix statt „weiterbauen“.

---

## 3) Workstreams (parallelisierbar, aber orchestriert)

## WS-1 Runtime-Lifecycle-Härtung

**Ziel:** deterministische Laufzeitphasen + sauberes Endeverhalten

**Kernfeatures:**
- Lifecycle-Phasenmodell (run_started, planning_started, tool_loop_started, tool_result, synth_started, run_completed/error)
- Streaming/Final-Entkopplung: kein verfrühtes Final bei transienten Tool-Fehlern
- „Wait-for-terminal-state“-Mechanik für interne Runner

**Primäre Dateien:**
- `backend/app/agent.py`
- `backend/app/orchestrator/pipeline_runner.py`
- `backend/app/orchestrator/events.py`
- `backend/app/ws_handler.py`

**Abhängigkeit:** Basis für WS-3 und WS-4.

---

## WS-2 Toolchaining-Parität

**Ziel:** OpenAgent-ähnliche Werkzeugsicherheit + Handlungsfähigkeit

**Kernfeatures:**
- Policy-Pipeline: profile/global/agent/run-scope (ohne Gateway-Bezug)
- Hookpunkte: `before_tool_call`, `after_tool_call`
- Tool-Loop-Detection (warn/block)
- standardisierte Tool-Event-Payloads (`start/update/result`)

**Primäre Dateien:**
- `backend/app/services/tool_execution_manager.py`
- `backend/app/services/tool_registry.py`
- `backend/app/services/tool_call_gatekeeper.py`
- `backend/app/tool_policy.py`
- `backend/app/tools.py`

**Abhängigkeit:** benötigt WS-1 Event-Rahmen.

---

## WS-3 Recovery/Failover-Engine

**Ziel:** keine fragilen Hard-Fails bei transienten/klassifizierbaren Fehlern

**Kernfeatures:**
- Error-Class-Matrix → nächste Aktion
- bounded Retry + Backoff + Replan-Slots
- Overflow-Recovery (Kontextkompression/Tool-Output-Truncation im bestehenden Kontextreducer/Reply-Shaper-Rahmen)
- terminal_reason + recovered_successfully Telemetrie

**Primäre Dateien:**
- `backend/app/orchestrator/recovery_strategy.py`
- `backend/app/orchestrator/fallback_state_machine.py`
- `backend/app/orchestrator/pipeline_runner.py`
- `backend/app/agent.py`

**Abhängigkeit:** WS-1 + WS-2.

---

## WS-4 Agency/Subrun-Orchestrierung

**Ziel:** kontrollierte Delegation auf Top-Level-Qualität

**Kernfeatures:**
- Delegationskriterien (Task-Komplexität/Toolbedarf/Timeout-Risiko)
- Subrun-Depth/Quota-Limits
- standardisierte Rückführung: Ergebnis + confidence + terminal_reason
- „handover contracts“ zwischen Parent und Child

**Primäre Dateien:**
- `backend/app/agent.py`
- `backend/app/subrun_endpoints.py`
- `backend/app/orchestrator/subrun_lane.py`
- `backend/app/custom_agents.py`

**Abhängigkeit:** WS-1 + WS-3.

---

## WS-5 Synthese-/Response-Contracts

**Ziel:** reproduzierbare Ausgabequalität bei komplexen Aufgaben

**Kernfeatures:**
- schema-first synthesis (Section-Contracts)
- self-check vor finaler Antwort
- reply shaping: dedupe/suppress/cleanup ohne semantischen Verlust

**Primäre Dateien:**
- `backend/app/agents/synthesizer_agent.py`
- `backend/app/services/reply_shaper.py`
- `backend/app/agent.py`

**Abhängigkeit:** kann früh starten, liefert aber maximalen Wert nach WS-2/WS-3.

---

## 4) Orchestrierter Umsetzungsfahrplan (sessionübergreifend)

## Phase A — Fundament (Sessions 1-4)

### Session 1
- WS-1: Lifecycle-Phasenmodell präzisieren + Event-Schema definieren
- DoD: dokumentiertes Event-Contract + erste Instrumentierung

### Session 2
- WS-1: terminal-state handling + wait semantics intern
- DoD: keine verfrühten finals in kritischen Tests

### Session 3
- WS-2: before/after-tool Hook-Infrastruktur + Event `tool:start/result`
- DoD: Hooks feuern deterministisch, keine Tool-Regression

### Session 4
- WS-2: Policy-Pipeline v1 + allow/deny conflict resolution
- DoD: Policy-Auflösung deterministisch + auditiert

---

## Phase B — Resilienz (Sessions 5-8)

### Session 5
- WS-3: Error-Class-Matrix + bounded retry policies
- DoD: Matrix-Unit-Tests grün

### Session 6
- WS-3: Replan-Slot-Strategie bei leeren/ungültigen Tool-Aktionen
- DoD: `tool_selection_empty`-Rate sinkt in Mid/Hard

### Session 7
- WS-3: Overflow-Recovery (truncate/compact im aktuellen Architekturrahmen)
- DoD: weniger terminal overflow fails

### Session 8
- WS-2/WS-3: Tool-Loop-Detection + Safe Degradation
- DoD: loop warnings/blocks messbar ohne false-positive Flut

---

## Phase C — Agency + Qualität (Sessions 9-12)

### Session 9
- WS-4: Delegationskriterien + Subrun-Governance (depth/quota)
- DoD: kontrollierte Delegation in definierten Szenarien

### Session 10
- WS-4: Subrun-Rückführung (result/confidence/terminal_reason)
- DoD: Parent-Antwort nutzt Child-Ergebnis konsistent

### Session 11
- WS-5: Synthesis-Schema v1 + final self-check
- DoD: Hard-Output-Contracts stabil

### Session 12
- WS-5: ReplyShaper-Härtung + End-to-End-Tuning
- DoD: Qualitäts-/Stabilitätsziele über 3 Benchmark-Läufe

---

## 5) Session-Protokoll (verbindlich pro Arbeitssession)

Jede Session folgt exakt diesem Ablauf:

1. **Scope-Freeze (10 Min)**
   - 1 Primärziel, max. 1 Nebenziel
2. **Design-Gate (15-30 Min)**
   - Contract, Flag, Rollback definiert
3. **Implementierungs-Slice**
   - kleinster lauffähiger Increment
4. **Test-Gate**
   - betroffene Unit/Contract-Tests
5. **Benchmark-/Smoke-Gate**
   - minimaler Mid/Hard-Slice
6. **Session-Handover**
   - Delta, Risiken, nächster Slice

Kein Gate-Pass => kein Merge in den Hauptpfad.

---

## 6) Backlog-Struktur (epic -> ticket)

## Epic E1: Lifecycle Runtime
- E1-T1 Event Schema v1
- E1-T2 terminal wait semantics
- E1-T3 stream/final separation guard

## Epic E2: Tool Pipeline
- E2-T1 before/after tool hooks
- E2-T2 policy pipeline resolver
- E2-T3 tool event normalization
- E2-T4 loop detector + thresholds

## Epic E3: Recovery
- E3-T1 error taxonomy
- E3-T2 retry/backoff engine
- E3-T3 replan fallback bounded
- E3-T4 overflow recovery strategy

## Epic E4: Agency
- E4-T1 delegation policy
- E4-T2 subrun depth/quota governance
- E4-T3 child->parent handover contract

## Epic E5: Response Quality
- E5-T1 schema-first synthesis
- E5-T2 synthesis self-check
- E5-T3 reply shaper hardening

---

## 7) Messgrößen (paritätsnah, gateway/history/memory-frei)

1. Hard success rate (gated)
2. Anteil `tool_selection_empty`
3. Recovery success rate
4. terminal error rate nach retry
5. p95 first token / duration in Hard
6. Anteil Subrun-Fälle mit erfolgreicher Rückführung
7. Anteil Antworten, die Output-Contract erfüllen

---

## 8) Risiken und Gegenmaßnahmen

1. **Überkomplexität durch parallele Umbauten**
   - Gegenmaßnahme: striktes Session-Protokoll + max 2 Tickets/Session

2. **Regressionen im Tooling**
   - Gegenmaßnahme: Contract-Tests + Feature Flags + stufenweise Aktivierung

3. **Prompt-Tuning kompensiert Architekturprobleme nur temporär**
   - Gegenmaßnahme: zuerst Runtime-Contracts, dann Prompt-Finetuning

4. **Subrun-Kaskaden (Kosten/Timeouts)**
   - Gegenmaßnahme: harte depth/quota/time budgets

---

## 9) Done-Kriterien für „nahe OpenAgent-Level"

Als erreicht gilt das Ziel, wenn über mindestens 3 aufeinanderfolgende Benchmark-Zyklen gilt:

1. Hard gated success stabil auf Zielniveau
2. Recovery-Wirksamkeit klar > Baseline
3. Tool-Fehler mit vermeidbarer Ursache signifikant reduziert
4. Subrun-Orchestrierung ist stabil und reproduzierbar
5. Keine relevanten Regressionen in bestehenden E2E-/Security-Tests

---

## 10) Konkreter Start (nächste Session)

Empfohlener Start ohne Diskussion:
1. E1-T1 Event Schema v1
2. E2-T1 Hook-Infrastruktur (before/after tool)

Warum: Diese beiden Tickets schaffen das Tragwerk für fast alle Folgefeatures und reduzieren Rework drastisch.
