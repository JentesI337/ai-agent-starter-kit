# End-to-End Autonome Problemlösungsfähigkeit — von 7.1/10 zu 11/10

## Meta
- ID: issue-0005
- Status: open
- Priorität: critical
- Owner: unassigned
- Erstellt: 2026-03-04
- Zuletzt aktualisiert: 2026-03-04

## Executive Summary
Die aktuelle 7.1/10 ist **kein Qualitätsproblem**, sondern ein **Capability- und Safety-Limit**.
Das System ist stabil, modular, testbar und orchestriert zuverlässig. Der Hauptgrund, warum es noch nicht „autonom Ende-zu-Ende“ ist: fehlende sichere Ausführungs-Isolation plus mehrere produktionskritische Lücken in Tooling, Recovery und Langzeit-Lernschleifen.

**Ziel 11/10 bedeutet hier:**
- nicht nur „funktioniert“,
- sondern „liefert wiederholbar richtige Ergebnisse unter realen Bedingungen, mit belegbarer Sicherheit, Governance, Kostenkontrolle und Selbstverbesserung“.

---

## Was 11/10 konkret heißt (Definition)
11/10 wird als **übererfüllte Produktionsfähigkeit** definiert, wenn alle folgenden Säulen gleichzeitig erfüllt sind:

1. **Solve-Rate**: ≥ 90% auf repräsentativen, realistischen Multi-Step Tasks.
2. **Safety**: 0 kritische Policy-Bypasses in Red-Team-Suite.
3. **Reliability**: p95 Run-Completion ohne manuelle Eingriffe ≥ 98%.
4. **Autonomie-Tiefe**: Agent kann planen, ausführen, verifizieren, korrigieren und finalisieren.
5. **Recovery**: deterministische Wiederaufnahme nach Fehlern/Disconnects.
6. **Governance**: vollständig auditierbare Entscheidungen, Policies, Overrides, Tool-Nutzung.
7. **Economics**: definierte Kostenbudgets pro Task-Typ mit hartem Abbruch bei Überschreitung.

---

## Harte Diagnose: Warum heute 7.1/10

## 1) Primärblocker — sichere Ausführung fehlt
- `run_command` ist hostnah (mit Guardrails, aber ohne echte Jail-Isolation).
- Folge: Kein sicherer Verify-Loop für autonomes Coding/Data-Execution.
- Referenz: [backend/app/tools.py](../backend/app/tools.py)
- Offenes Item: [issues/issue-0003-code-execution-sandbox-tool.md](issue-0003-code-execution-sandbox-tool.md)

## 2) MCP-Sicherheits-/Transporthärtung ist nicht abgeschlossen
- Dynamische Tool-Flächen und Lifecycle-Risiken begrenzen Produktionsvertrauen.
- Offenes Item: [issues/issue-0002-mcp-bridge-hardening-and-security.md](issue-0002-mcp-bridge-hardening-and-security.md)

## 3) LTM-Injektion noch nicht ausreichend budget-/relevanzgehärtet
- Risiko für Prompt-Drift, Token-Waste und schwankende Qualität.
- Offenes Item: [issues/issue-0001-ltm-context-hardening.md](issue-0001-ltm-context-hardening.md)

## 4) Capability-Gaps über Kern-Workflows hinweg
- Browser-Automation, strukturierte Datenpfade, echte Parallel-Rendezvous, Human-in-the-loop Mid-Task etc.
- Offenes Item: [issues/issue-0004-agent-capability-gaps-roadmap.md](issue-0004-agent-capability-gaps-roadmap.md)

---

## 11/10 Architektur-Upgrade (Priorisierte Workstreams)

## WS-A (P0): Secure Execution Core (7.1 -> 8.8)
**Ziel:** sichere, kontrollierte Codeausführung als First-Class Tool.

### Muss liefern
- `code_execute` mit Strategien `docker | process | direct`.
- Python + JavaScript Pfade mit Timeout, Output-Limit, Cleanup.
- Structured Errors statt roher Exceptions.
- ToolSpec + Validator + Policy-Integration + E2E.

### Sicherheits-Gates
- Kein Netzwerk im Sandbox-Pfad standardmäßig.
- Kein ungefilterter Zugriff außerhalb Workspace/Temp-Jail.
- Child-Prozess-Tree wird bei Timeout hart beendet.

### Done-Definition
- Issue-0003 Akzeptanzkriterien vollständig grün.
- Dedizierte Red-Team-Tests für Escape-Versuche grün.

---

## WS-B (P0): Trust & Compliance Layer (8.8 -> 9.4)
**Ziel:** dynamische Toolflächen und MCP transport/protokolltreu absichern.

### Muss liefern
- MCP Transportpfade sauber getrennt (`stdio`, `sse`, `streamable-http`).
- Deny-by-default für `mcp_*` in restriktiven Profilen.
- Config-Strictness + startup diagnostics.
- Deterministisches close/re-init ohne Leaks.

### Done-Definition
- Issue-0002 Akzeptanzkriterien grün.
- Leak-/Re-init-Stresstest (>=100 cycles) ohne Ressourcenwachstum.

---

## WS-C (P1): Memory Relevance & Prompt Budget (9.4 -> 9.8)
**Ziel:** mehr Trefferquote bei weniger Kontextmüll.

### Muss liefern
- Query-basierte Semantik statt globalem Memory-Broadcast.
- Harte char/line/item Limits auf LTM-Injection.
- Sanitizing + Priorisierung (Failures vor Preferences).
- Telemetrie: `ltm_items_used`, `ltm_chars`, Wirkung auf Solve-Rate.

### Done-Definition
- Issue-0001 Akzeptanzkriterien grün.
- Keine Kontextüberschreitung in Stress-Suite.

---

## WS-D (P1): Capability Expansion for Real Tasks (9.8 -> 10.4)
**Ziel:** reale End-to-End Aufgaben abdecken statt nur Code-Editing.

### Muss liefern (MVP-Reihenfolge)
1. Browser-Interaktion (JS-rendered Web).
2. Strukturierte Datenpfade (`query_csv`, `query_sqlite` read-only).
3. `spawn_subrun_and_wait` für echtes Ergebnis-Rendezvous.
4. `ask_user` für Mid-Task Klärung ohne Run-Abbruch.

### Done-Definition
- Relevante Tier-1/2 Akzeptanzkriterien aus Issue-0004 grün.
- Neue E2E-Szenarien in Benchmark-Suite enthalten.

---

## WS-E (P2): Autonomous Quality Loop (10.4 -> 11/10)
**Ziel:** Agent verbessert sich im Lauf selbst statt nur statisch zu reagieren.

### Muss liefern
- Verifikations-Policy pro Task-Typ (z. B. coding: tests required).
- Self-Repair mit max. Iterationen + Abbruchregeln.
- Outcome-Scoring + Fail-Reason Taxonomy.
- Automatische Lernrückführung in LTM (sanitized, relevance-gated).

### Done-Definition
- Solve-Rate-Zuwachs über 4 Benchmark-Wellen nachweisbar.
- Fehlertypen sinken signifikant in mindestens 3 Top-Kategorien.

---

## Messmodell (Scorecard)

Gesamtscore:

$$
Score = 0.30 \cdot SolveRate + 0.20 \cdot Safety + 0.15 \cdot Reliability + 0.10 \cdot Recovery + 0.10 \cdot Governance + 0.10 \cdot CostControl + 0.05 \cdot Latency
$$

Alle Teilwerte normiert auf 0..10.

### KPI-Ziele
- SolveRate: 9.0+
- Safety: 9.8+
- Reliability: 9.5+
- Recovery: 9.0+
- Governance: 9.0+
- CostControl: 8.5+
- Latency: 8.0+

**11/10-Freigabe-Regel:**
- gewichteter Score >= 9.3
- **und** alle P0/P1 Security-Gates bestanden
- **und** kein offener Critical-Issue im Sicherheits- oder Ausführungspfad

---

## Benchmarking & Verifikation (hart, nicht kosmetisch)

## Erweiterung der bestehenden Benchmark-Strategie
Referenz: [backend/BENCHMARK_STRATEGY.md](../backend/BENCHMARK_STRATEGY.md)

### Neue obligatorische Suites
1. **Autonomy Suite**: reale, mehrstufige Tasks mit Verifikationspflicht.
2. **Security Suite**: Sandbox-Escape, SSRF, Policy-Bypass, Prompt-Injection.
3. **Recovery Suite**: WS-Disconnect, Runtime-Switch, Fallback-Ketten, Reconnect.
4. **Cost Suite**: Budget-Grenzen, Abbruch-Policies, degradierte Strategien.

### Required Artifacts je Lauf
- `results.json` (maschinenlesbar)
- `summary.md` (entscheidungsfähig)
- `events.jsonl` (forensisch)
- `scorecard.json` (neues normiertes KPI-Objekt)

---

## Delivery-Plan (30/60/90)

## 0-30 Tage (P0 schließen)
- Issue-0003 komplett umsetzen.
- Issue-0002 kritische Sicherheits-/Lifecycle-Blöcke abschließen.
- Security-Suite minimal lauffähig machen.

**Gate:** kein Merge ohne grüne P0-Security-Tests.

## 31-60 Tage (P1 Funktionsbreite + Qualität)
- Issue-0001 abschließen.
- Tier-1/Tier-2 Kernpunkte aus Issue-0004 (MVP-Reihenfolge) implementieren.
- Benchmark um Autonomy/Recovery-Suiten erweitern.

**Gate:** Solve-Rate +10pp gegenüber Baseline.

## 61-90 Tage (Autonomous Quality Loop)
- WS-E vollständig integrieren.
- Scorecard-Automation in CI/CD.
- Release Candidate mit belastbarer Betriebsdoku.

**Gate:** 11/10-Freigaberegel erfüllt.

---

## Risiko-Matrix (Top 5)
1. **False sense of sandbox security**
   - Mitigation: deny-by-default, escape tests, staged rollout.
2. **Capability bloat ohne Governance**
   - Mitigation: capability flags, policy matrix, per-agent allow profiles.
3. **Kostenexplosion durch autonome Replans**
   - Mitigation: harte token/tool/cost budgets + cut-off policies.
4. **Nichtdeterministische Recovery-Pfade**
   - Mitigation: state-machine invariants + deterministic replay tests.
5. **Observability-Lücken**
   - Mitigation: einheitliche lifecycle schema contracts + scorecard pipeline.

---

## Sofort umsetzbare Next Actions (diese Woche)
1. Issue-0003 in 3 PRs schneiden:
   - PR1: `CodeSandbox` Service + process strategy + tests.
   - PR2: Tool wiring (`code_execute`) + validator + policy.
   - PR3: security tests + docs + benchmark scenario.
2. P0 Security-Gates als Pflicht-Check in CI markieren.
3. Benchmark-Scorecard (`scorecard.json`) einführen.
4. Release-Entscheidung nur noch über Scorecard + Security-Gates.

---

## Abgrenzung
Dieses Dokument bewertet und plant ausschließlich die Backend-Agent-Fähigkeit Ende-zu-Ende. Frontend-UX-Optimierungen sind nicht Bestandteil des 11/10-Kriteriums, solange sie die Agenten-Outcome-Qualität nicht direkt beeinflussen.

---

## Verknüpfte Issues
- [issue-0001-ltm-context-hardening.md](issue-0001-ltm-context-hardening.md)
- [issue-0002-mcp-bridge-hardening-and-security.md](issue-0002-mcp-bridge-hardening-and-security.md)
- [issue-0003-code-execution-sandbox-tool.md](issue-0003-code-execution-sandbox-tool.md)
- [issue-0004-agent-capability-gaps-roadmap.md](issue-0004-agent-capability-gaps-roadmap.md)
