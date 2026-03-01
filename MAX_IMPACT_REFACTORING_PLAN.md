# Max-Impact Refactoring Plan (OpenClaw-inspiriert)

Stand: 2026-03-01  
Scope: `backend/` (Runtime, Orchestrierung, Contracts, Tool-Governance)

## 1) Ziel: größtmöglicher Nutzen statt maximaler Umbau

Dieser Plan priorisiert **messbaren Produktnutzen** (Zuverlässigkeit, Steuerbarkeit, Sicherheit, Skalierbarkeit) vor „großem Rewrite“.

**North Star:**
- stabilere Multi-Agent-Läufe,
- klarere Agency-Typen (Orchestrator vs Worker),
- reproduzierbare Tool-Policies,
- weniger Incident-/Debug-Aufwand,
- kontrollierte Erweiterbarkeit für neue Agenten/Workflows.

---

## 2) Hebel mit höchstem ROI (Impact x Machbarkeit)

## Hebel A — Spawn/Agency explizit machen (sehr hoher Impact, niedriger-mittlerer Aufwand)
**Problem heute:** Subruns sind technisch vorhanden, aber nicht als klarer Agency-Typ mit `agent_id` + `mode` modelliert.  
**Ziel:** `subrun_spawn` bekommt explizite Steuerung für Ziel-Agent und Modus (`run|session`), inkl. sauberer Validation.

**Konkrete Änderungen:**
- WS/Control-Input um Felder erweitern: `agent_id`, `mode`, optional `runtime`.
- `SubrunLane.spawn(...)` um Ziel-Orchestrator/Agent ergänzen.
- Default-Verhalten rückwärtskompatibel halten (`agent_id` fallback auf anfragenden Agent).

**Erwarteter Nutzen:**
- weniger Fehlrouting,
- klarere Delegationsflüsse,
- Basis für orchestrator/leaf-Trennung ohne Architekturbruch.

---

## Hebel B — Session-Graph Runtime „light“ (sehr hoher Impact, mittlerer Aufwand)
**Problem heute:** Parent/Child-Relationen sind da, aber nicht als vollwertiger, extern auswertbarer Graph-Vertrag nutzbar.  
**Ziel:** Session-/Run-Graph als First-Class Runtime-Metadaten (parent/root/depth/mode/agent).

**Konkrete Änderungen:**
- Metadaten-Schema für Run-/Subrun-Beziehungen vereinheitlichen.
- Standardisierte Read-APIs erweitern (`runs.get`, `runs.list`, `sessions.status`) um Graph-Felder.
- Sichtbarkeits-Scopes konsistent auf Graph anwenden (`self/tree/agent/all`).

**Erwarteter Nutzen:**
- deutlich bessere Debugbarkeit,
- reproduzierbare A2A-Orchestrierung,
- weniger Sonderlogik pro Endpoint.

---

## Hebel C — Tool-Policy-Matrix (sehr hoher Impact, mittlerer Aufwand)
**Problem heute:** policy-merge existiert, aber Layering ist noch begrenzt (global/preset/request).  
**Ziel:** deterministische Policy-Kette: `global -> profile -> preset -> provider/model -> agent/depth -> request`.

**Konkrete Änderungen:**
- ein zentraler Resolver statt verteilter Merge-Logik.
- Depth-spezifische Regeln (z. B. leaf darf nicht weiter spawnen).
- Preview-/Explain-Endpoint ausbauen (final allow/deny + Herleitung).

**Erwarteter Nutzen:**
- weniger Sicherheitslücken,
- konsistentes Verhalten über Modelle/Provider,
- schnellere Ursachenanalyse bei „Tool blocked/unexpected allow“.

---

## Hebel D — Wait/Lifecycle-Härtung (hoher Impact, niedriger Aufwand)
**Problem heute:** Wait/Status sind gut, aber noch nicht vollständig OpenClaw-nah in Telemetrie-Semantik.  
**Ziel:** harte Run-Statusmaschine mit eindeutigen Zeitstempeln und terminalen Zuständen.

**Konkrete Änderungen:**
- `agent.wait`-ähnliche Payloads standardisieren: `status`, `started_at`, `ended_at`, `error`, `run_status`.
- Lifecycle-Ereignisse normalisieren (accepted/started/completed/failed/timeout/cancelled).
- Idempotenz-Replay sauber ausweisen.

**Erwarteter Nutzen:**
- robustere Client-Integrationen,
- weniger race conditions,
- bessere Automatisierbarkeit.

---

## Hebel E — Announce/Delivery Robustheit (hoher Impact, niedriger-mittlerer Aufwand)
**Problem heute:** Announce existiert, ist aber anfällig bei transienten Fehlern/Restarts.  
**Ziel:** idempotente, retry-fähige Zustellung mit klaren Outcomes.

**Konkrete Änderungen:**
- idempotency key pro Announce,
- kurzer retry/backoff-Mechanismus,
- eindeutige Statusfelder: `announced|announce_retrying|announce_failed`.

**Erwarteter Nutzen:**
- weniger „silent failures“,
- höhere Zuverlässigkeit bei langen Subruns.

---

## Hebel F — Loop-/Budget-Guards (hoher Impact, mittlerer Aufwand)
**Problem heute:** Guardrails sind vorhanden, aber kein systematischer pre-tool-call Loop-Breaker mit Budget-Matrix.  
**Ziel:** deterministische Kosten-/Schleifenkontrolle.

**Konkrete Änderungen:**
- Tool-Call-History + Repetition-Detektor,
- Budgets pro Run/Subrun: max tool calls, max runtime, optional token cap,
- Lifecycle-Warnungen und harte Blockade-Schwellen.

**Erwarteter Nutzen:**
- Kostenkontrolle,
- weniger Endlosschleifen,
- stabilere Produktion.

---

## Hebel G — Observability by default (hoher Impact, niedriger Aufwand)
**Problem heute:** Viele Events existieren, aber KPI-Sicht ist nicht durchgängig aggregiert.  
**Ziel:** ein standardisierter Betriebsblick auf Qualität, Kosten, Stabilität.

**Konkrete Änderungen:**
- strukturierte Run- und Subrun-KPIs pro Request.
- zentrale Counter für routing_reason, policy_reject, timeout, retry, announce_outcome.
- Monitoring-Schema um Betriebsmetriken ergänzen.

**Erwarteter Nutzen:**
- schnelle Trendanalyse,
- faktenbasierte Priorisierung,
- bessere Release-Sicherheit.

---

## 3) Metriken (Baseline → Target)

Vor Start: 7–14 Tage Baseline messen, dann Zielwerte nach Phase 2 und Phase 4.

1. **Run Success Rate** = completed / started  
   - Ziel: +10 bis +25%
2. **Subrun Completion Rate**  
   - Ziel: +15 bis +35%
3. **Policy Incident Rate** (unerwartet blocked/allowed)  
   - Ziel: -30 bis -60%
4. **Mean Time To Debug (MTTD)** pro Incident  
   - Ziel: -40 bis -70%
5. **Timeout/Cancel Rate**  
   - Ziel: -20 bis -40%
6. **Announce Delivery Success**  
   - Ziel: >98%
7. **Cost Waste Rate** (abgebrochene/looped Runs)  
   - Ziel: -20 bis -50%

---

## 4) Roadmap in Phasen (maximaler Nutzen bei kontrolliertem Risiko)

## Phase 0 (1 Woche) — Messbarkeit + Contract-Freeze
**Deliverables:**
- Event-/Status-Schema schriftlich fixieren.
- KPI-Erfassung einbauen.
- Baseline-Report erzeugen.

**Done wenn:** KPI-Dashboard/JSON-Report reproduzierbar vorhanden.

---

## Phase 1 (1–2 Wochen) — Low-Risk High-Impact Kern
**Deliverables:**
- `subrun_spawn` mit `agent_id` + `mode` (backward-compatible).
- Orchestrator-Auswahl pro Spawn.
- Wait/Lifecycle-Payloads vereinheitlicht.

**Done wenn:**
- bestehende E2E-Tests grün,
- neue Tests für agent-select + mode + wait-status grün,
- keine Regression im Legacy-Flow.

### Phase-1 Umsetzungsstand (2026-03-01)

**Implementiert im Scope:**
- `subrun_spawn` akzeptiert optional `agent_id` und `mode` (`run|session`) mit rückwärtskompatiblen Defaults.
- `SubrunLane.spawn(...)` unterstützt pro Spawn die Auswahl von Ziel-Agent und Ziel-Orchestrator.
- `mode=session` nutzt die Parent-Session weiter; `mode=run` erzeugt wie bisher eine Child-Session.
- `run.wait` / `agent.wait` geben vereinheitlichte Status-/Zeitfelder aus (`status`, `runStatus`, `run_status`, `startedAt`, `endedAt`, plus snake_case-Äquivalente).
- Lifecycle-Events enthalten konsistenten Laufstatus und Zeitstempel in den relevanten Stages.

**Validierung:**
- `tests/test_backend_e2e.py` + `tests/test_control_plane_contracts.py`: **79 passed**.
- `tests/test_subrun_lane.py` + `tests/test_subrun_visibility_scope.py`: **7 passed**.

**Verbesserung gegenüber vorher:**
- Delegation/Spawn ist expliziter und weniger fehleranfällig (Agent + Modus klar im Contract).
- Wait-/Lifecycle-Responses sind für Clients konsistenter und leichter zu automatisieren.
- Bestehende Flows bleiben kompatibel, da Defaults unverändert funktionieren.

**Verbleibende Restrisiken (bewusst außerhalb Phase 1):**
- Noch keine vollständige depth-/rollenbasierte Policy-Matrix (`orchestrator` vs `leaf`) — folgt in Phase 2.
- Noch keine vollständige Session-Graph-Auswertung über alle Read-Endpunkte — folgt in Hebel B.

---

## Phase 2 (1–2 Wochen) — Policy-Matrix + Depth-Regeln
**Deliverables:**
- zentraler Policy-Resolver,
- depth-basierte Restrictions (orchestrator vs leaf),
- erweiterte Policy-Preview/Explain.

**Done wenn:**
- policy-Entscheidung deterministisch (Snapshot-Tests),
- leaf-spawn blockiert, orchestrator-spawn erlaubt (je nach Config).

### Phase-2 Vorbereitung (MVP, klein & testbar)

**Ziel für den ersten PR-Schnitt:**
- Kein Full-Refactor, sondern nur Resolver-Kern + minimale Depth-Regel für Spawn.

**Task 1 — Zentralen Resolver extrahieren**
- Implementiere einen einzigen Resolver-Einstieg mit fester Reihenfolge:
   `global -> profile -> preset -> provider/model -> agent/depth -> request`.
- Nutze bestehende Tool-Policy-Bausteine weiter; keine API-Umbenennungen.
- Liefere eine interne Explain-Struktur (`layers`, `final_allow`, `final_deny`).

**Task 2 — Depth-Regel minimal einführen**
- Ergänze eine konfigurierbare Regel: `leaf` darf keine weiteren `subrun_spawn` auslösen.
- Default auf „kompatibel“ (Feature-Flag oder Default-Allow), damit Legacy-Flows nicht brechen.
- Bei Blockade: deterministische Fehlermeldung + Lifecycle-Stage für Auswertung.

**Task 3 — Policy-Preview/Explain minimal erweitern**
- Preview-Endpunkt gibt finalen Effekt plus Layer-Herkunft aus.
- Bei Konflikten (`allow` vs `deny`) gilt klar dokumentierter Vorrang (`deny` gewinnt).

**Task 4 — Zieltests für den ersten Schnitt**
- Snapshot-Tests für deterministische Resolver-Entscheidung.
- Contract-Test: gleicher Input => gleiche Explain-Ausgabe.
- E2E-Test: Leaf-Spawn wird geblockt, Orchestrator-Spawn bleibt (gemäß Config) erlaubt.

**Phase-2 Gate (vor Ausbau):**
- Alle bestehenden E2E/Control-Plane-Tests weiterhin grün.
- Neue Resolver-/Depth-Tests grün.
- Keine Contract-Breaks in bestehenden Endpunkten.

### Phase-2 Fortschritt (2026-03-01)

**Status:** **Phase 2 abgeschlossen**.

**Geliefert:**
- Zentraler Policy-Resolver mit fester Layer-Reihenfolge und Explain-Herleitung.
- Minimale Depth-Regel (leaf darf nicht spawnen) als kompatibles Flag (`default: aus`).
- Depth-Regel auf Spawn-Pfade harmonisiert (zentrale Enforcement-Logik in `SubrunLane.spawn(...)`, nicht nur WS-spezifisch).
- Policy-Preview Explain erweitert um explizite Konfliktauflösung (`deny_overrides_allow`).
- Snapshot-nahe Determinismus-Tests für Layer/Explain/Conflict-Resolution ergänzt.

**Testnachweis (lokal):**
- `tests/test_subrun_lane.py`
- `tests/test_backend_e2e.py`
- `tests/test_control_plane_contracts.py`
- `tests/test_subrun_visibility_scope.py`
- Gesamtlauf (relevante Suiten): **91 passed**

**Resthinweis (optional):**
- Dedizierte Snapshot-Dateien (statt inline Assertions), falls Team standardisiert auf Snapshot-Testing umstellt.

---

## Phase 3 (1 Woche) — Announce-Robustheit + Idempotenz
**Deliverables:**
- announce idempotency key,
- retry/backoff,
- explizite announce lifecycle states.

**Done wenn:** künstliche Transient-Fehler führen nicht mehr zu stillen Drops.

### Phase-3 Start (2026-03-01)

**Bereits umgesetzt:**
- Announce-Zustände auf explizite Bezeichnungen umgestellt:
   `announced`, `announce_retrying`, `announce_failed`.
- Rückwärtskompatibilität erhalten über `legacy_status` (`sent`, `retrying`, `dead_letter`).
- Explizite Delivery-Status auch in externen Payloads sichtbar gemacht:
   - `subrun_announce` enthält `announce_status` + `announce_legacy_status`.
   - `/api/subruns/{run_id}` liefert `announce_delivery.status` + `announce_delivery.legacy_status`.
- Contract-/E2E-Tests für neue Felder und Retry-Statuspfade ergänzt und grün.

**Nächster sinnvoller Schritt in Phase 3:**
- Optional: Phase-3 formal auf „done“ setzen und nur noch Monitoring/Runbook ergänzen (kein weiterer Core-Code nötig).

---

## Phase 4 (1–2 Wochen) — Loop/Budget-Hardening
**Deliverables:**
- loop detection warn/critical,
- Run/Subrun budget guards,
- klare Fehlerklassen + Telemetrie.

**Done wenn:** definierte Loop-Szenarien deterministisch gebrochen werden.

### Phase-4 Fortschritt (2026-03-01)

**Status:** **Phase 4 abgeschlossen**.

**Geliefert:**
- Loop/Budget-Guards in der Agent-Ausführung aktiv (`tool_loop_warn`, `tool_loop_blocked`, `tool_budget_exceeded`).
- `runs.audit` um explizite `guardrail_summary` erweitert (inkl. letzter `tool_audit_summary`-Details).
- Contract-Tests für Guardrail-Telemetrie ergänzt.

**Testnachweis (lokal):**
- `tests/test_control_plane_contracts.py`
- `tests/test_backend_e2e.py`
- `tests/test_subrun_lane.py`
- `tests/test_subrun_visibility_scope.py`
- Gesamtlauf (relevante Suiten): **92 passed**

**Nachgelagerte Architektur-Neubewertung:**
- siehe `ARCHITECTURE_REASSESSMENT_2026-03-01.md`.

---

## Phase 5 (optional, 2+ Wochen) — Größerer Architekturzug
Nur wenn KPI-Ziele aus Phase 1–4 nicht reichen.

**Optionen:**
- formale Workflow-Definition (DAG/JSON),
- stärker OpenClaw-nahe Control Plane (methodenbasiert),
- Skill/Capability-Layer als eigene Runtime-Schicht.

---

## 5) Konkrete Arbeitsbereiche im aktuellen Code

- `backend/app/main.py` — routing, ws contract, run/wait, subrun entrypoints
- `backend/app/orchestrator/subrun_lane.py` — spawn semantics, status, visibility, announce
- `backend/app/models.py` — inbound/outbound schema extensions
- `backend/app/config.py` — neue defaults/limits/policy knobs
- `backend/app/state/*` — persistente Run-/Graph-Metadaten
- `backend/tests/test_backend_e2e.py` — End-to-End Contracts
- `backend/tests/test_control_plane_contracts.py` — control-plane Semantik

---

## 6) Risiken und Gegenmaßnahmen

1. **Regressionen im bestehenden Chat-Flow**  
   - Gegenmaßnahme: strikte Backward-Compatibility + Feature Flags.
2. **Policy-Komplexität explodiert**  
   - Gegenmaßnahme: ein zentraler Resolver + Explain-Ausgabe + Snapshot-Tests.
3. **Mehr Event-Lärm statt Klarheit**  
   - Gegenmaßnahme: standardisierte Event-Typen + kompakte KPI-Aggregation.
4. **Zu großer Scope in einem Sprint**  
   - Gegenmaßnahme: harte Phasen-Gates (nur mit Messziel-Freigabe weiter).

---

## 7) Empfohlene Priorisierung (wenn Ressourcen knapp)

1. Phase 1 komplett
2. Phase 2 Kern (Resolver + depth deny für leaf)
3. Phase 3 (announce idempotency/retry)
4. Phase 4 (mindestens warn-level loop detection)

Damit erreicht ihr den größten Nutzeneffekt ohne Big-Bang-Refactor.

---

## 8) Ready-to-paste Prompt für neue Session

```text
Arbeite auf Basis von MAX_IMPACT_REFACTORING_PLAN.md.
Ziel: Implementiere Phase 1 (Low-Risk High-Impact Kern) in kleinen, testbaren Schritten.
Scope strikt begrenzen auf:
1) subrun_spawn: optional agent_id + mode (run|session), backward-compatible defaults
2) SubrunLane: Orchestrator/Agent-Auswahl pro Spawn
3) run/wait/lifecycle payloads vereinheitlichen (status + timestamps)

Anforderungen:
- Keine großen Umstrukturierungen außerhalb dieses Scopes.
- Bestehende API-Verträge nicht brechen.
- Gezielte Tests ergänzen/aktualisieren (E2E + Control-Plane), alle relevanten Tests grün.
- Nach jedem Schritt kurz begründen, was sich verbessert hat und welche Risiken verbleiben.
```

---

## 9) Entscheidungskriterium „weiter refactoren oder stoppen?“

Nach Phase 2 prüfen:
- Sind ≥70% der Zielverbesserungen bei Success Rate, MTTD, Policy Incidents erreicht?  
  - **Ja:** Stabilisieren, kein großer Umbau nötig.  
  - **Nein:** Phase 5 vorbereiten (größerer Architekturzug).

Dieses Kriterium verhindert Over-Engineering und hält den Nutzenfokus hoch.