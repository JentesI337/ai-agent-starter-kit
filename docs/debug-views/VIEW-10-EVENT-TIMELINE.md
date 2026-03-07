# VIEW-10 — Event Timeline

> Chronologischer Echtzeit-Stream **aller** Lifecycle-Events eines Runs als filterbare, durchsuchbare Timeline.

---

## 1. Warum brauchen wir diesen View?

Die anderen Views (VIEW-01 bis VIEW-09) zeigen **aggregierte Informationen**
pro Phase.  Aber manchmal muss man die **rohen Events in ihrer exakten
Reihenfolge** sehen, um Timing-Probleme, fehlende Events oder unerwartete
Sequenzen zu debuggen.

Die Pipeline emittiert **40+ Lifecycle-Event-Typen**.  Ein typischer Run
erzeugt **15–30 Events** in ~10–25 Sekunden.  Der Event Timeline View ist
das **Gesamtprotokoll** — die Blackbox-Aufnahme des Runs.

### Konkretes Szenario

Ein Nutzer meldet: "Die Antwort kam nach 25 Sekunden, obwohl nur ein
einfacher Grep nötig war."

Im Event Timeline sieht der Entwickler:
```
0.00s  run_started
0.12s  guardrails_passed
0.15s  tool_policy_resolved
0.18s  toolchain_checked
0.20s  memory_updated
0.25s  context_segmented (planning)
0.30s  planning_started
3.80s  planning_completed           ← 3.5s für Planning, OK
3.82s  context_segmented (tool)
3.85s  [tool_selection]
6.20s  [tool_completed: grep_search]  ← 2.4s für Grep, OK
6.25s  [replanning_started]           ← WARUM REPLAN?
6.30s  [context_segmented (tool)]
9.80s  [replanning_completed]         ← 3.5s für Replan
9.85s  [tool_completed: read_file]    ← Zusätzlicher Read nach Replan
12.0s  context_segmented (synthesis)
12.1s  [synthesis - streaming]
18.0s  reflection_completed           ← 6s für Synthesis+Reflection
18.1s  reply_shaping_completed
18.2s  run_completed
```

**Problem sofort sichtbar:** Unnötiges Replanning bei Zeile 6.25s.

---

## 2. Datenquellen

### 2.1 Vollständiger Event-Katalog (40+ Events)

**Initialisierung (6):**
`run_started`, `guardrails_passed`, `tool_policy_resolved`,
`toolchain_checked`, `orphaned_tool_calls_repaired`,
`session_history_sanitized`

**Memory & Context (4):**
`memory_updated`, `context_reduced`, `context_segmented` (×3)

**Planning (5):**
`clarification_auto_resolved`, `clarification_needed`,
`planning_started`, `planning_completed`,
`verification_plan`, `verification_plan_semantic`

**Tool Loop (5):**
`terminal_wait_started`, `terminal_wait_completed`,
`replanning_started`, `replanning_completed`, `replanning_exhausted`,
`tool_selection_empty`

**Tool Execution (6):**
`tool_started`, `tool_completed`, `tool_failed`, `tool_blocked`,
`tool_execution_detail`, `tool_budget_exceeded`

**Loop Detection (6):**
`tool_loop_generic_repeat_warn`, `tool_loop_generic_repeat_critical`,
`tool_loop_ping_pong_warn`, `tool_loop_ping_pong_critical`,
`tool_loop_poll_no_progress`, `tool_loop_circuit_breaker`

**Verification (2):**
`verification_tool_result`, `verification_final`

**Early Exits (3):**
`response_emitted`, `run_interrupted`, `web_research_sources_unavailable`

**Synthesis (1):**
`tool_result_context_guard_applied`

**Reflection (3):**
`reflection_completed`, `reflection_failed`, `reflection_skipped`

**Gates & Shaping (5):**
`implementation_evidence_missing`, `orchestration_evidence_missing`,
`reply_shaping_started`, `reply_shaping_completed`,
`all_tools_failed_gate_applied`, `reply_suppressed`

**Hooks & MCP (4):**
`hook_invoked`, `hook_timeout`, `hook_skipped`, `hook_failed`,
`mcp_tools_initialized`, `mcp_tools_failed`

**Completion (2):**
`run_completed`, `policy_override_decision`

### 2.2 Event-Struktur

Jedes Event hat diese Grundstruktur:
```typescript
interface LifecycleEvent {
  type: string;               // Event-Name
  timestamp: string;          // ISO-8601
  request_id: string;         // Run-ID
  payload: Record<string, unknown>;  // Event-spezifische Daten
}
```

### 2.3 Benötigte neue Backend-Events

Keine neuen Events nötig — dieser View nutzt **alle existierenden Events**.

Optionale Erweiterung:
| Event | Payload | Zweck |
|-------|---------|-------|
| `phase_transition` | `{ from_phase, to_phase, elapsed_ms }` | Expliziter Marker für Phasenübergänge (aktuell implizit) |

---

## 3. UI-Struktur

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  EVENT TIMELINE                                 28 events       │
│  Duration: 18.2s  |  Run: abc-1234  |  Agent: head-agent        │
├─────────────────────────────────────────────────────────────────┤
│  Filter: [All ▾]  Phase: [All ▾]  Search: [________________]   │
│  Severity: [●Info ●Warn ●Error]                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TIME     PHASE      EVENT                    DETAILS           │
│  ─────    ─────      ─────                    ───────           │
│                                                                 │
│  ── Phase 0: Routing ──────────────────────────────────────     │
│                                                                 │
│  0.00s    routing    ● run_started             agent=head-agent │
│  0.12s    routing    ● guardrails_passed       5/5 checks OK    │
│  0.15s    routing    ● tool_policy_resolved    policy=default   │
│  0.18s    routing    ● toolchain_checked       18 tools ready   │
│                                                                 │
│  ── Phase 2: Memory & Context ─────────────────────────────     │
│                                                                 │
│  0.20s    memory     ● memory_updated          items=12/20      │
│  0.25s    context    ● context_segmented       phase=planning   │
│                        budget=4096, used=2800 (68%)             │
│                                                                 │
│  ── Phase 3: Planning ─────────────────────────────────────     │
│                                                                 │
│  0.30s    planning   ● planning_started                         │
│  3.80s    planning   ● planning_completed      3.5s, 3 steps   │
│  3.81s    planning   ● verification_plan       status=pass      │
│                                                                 │
│  ── Phase 4: Tool Loop ────────────────────────────────────     │
│                                                                 │
│  3.82s    tool       ● context_segmented       phase=tool       │
│  3.85s    tool       ● tool_started            grep_search      │
│  6.20s    tool       ● tool_completed          grep_search 2.4s │
│  6.25s    tool       ⚠ replanning_started      reason=empty     │
│                           ↑ 3 results war leer                  │
│  9.80s    tool       ● replanning_completed    2 new steps      │
│  ...                                                            │
│                                                                 │
│  ── Phase 8: Response ─────────────────────────────────────     │
│                                                                 │
│  18.1s    response   ● reply_shaping_completed −172 chars       │
│  18.2s    response   ● run_completed           total=18.2s      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Komponenten

| Komponente | Beschreibung |
|------------|-------------|
| **Summary Bar** | Gesamtzahl Events, Gesamtdauer, Run-ID, Agent |
| **Filter Bar** | Dropdown für Event-Typ, Phase-Filter, Freitext-Suche, Severity-Toggle |
| **Phase Dividers** | Horizontale Trenner zwischen Pipeline-Phasen mit Phase-Name |
| **Event Row** | Einzelne Zeile: Timestamp, Phase-Badge, Severity-Icon, Event-Name, Detail-Summary |
| **Event Detail Popover** | Click auf Event-Row expandiert die vollständige Payload als JSON |
| **Time Column** | Relative Zeit seit `run_started` (nicht absolute ISO-Zeitstempel) |
| **Duration Markers** | Bei Events mit Dauer (z.B. `planning_completed`): Inline-Dauer-Badge |
| **Severity Icons** | ● Info (blau), ⚠ Warn (gelb), ❌ Error (rot) |
| **Auto-Scroll Toggle** | Button zum Aktivieren/Deaktivieren von Auto-Scroll bei neuen Events |
| **Export Button** | Download der Event-Timeline als JSON |

### 3.3 Interaktionen

| Aktion | Verhalten |
|--------|-----------|
| Click auf Event-Row | Expandiert Detail-Popover mit vollständiger JSON-Payload |
| Phase-Filter | Zeigt nur Events der ausgewählten Phase(n) |
| Event-Typ-Filter | Dropdown mit allen Event-Typen, Mehrfachauswahl |
| Freitext-Suche | Filtert Events deren Name oder Payload-Text den Suchbegriff enthält |
| Severity-Toggle | 3 Toggles (Info/Warn/Error), default: alle aktiv |
| Auto-Scroll | An: Timeline scrollt automatisch zum neuesten Event.  Aus: manuelle Navigation |
| Export | Downloadet alle Events des Runs als JSON-Array |
| Click auf Timestamp | Kopiert relative + absolute Zeit in Zwischenablage |

---

## 4. Dos

- ✅ **Relative Timestamps verwenden** — "3.80s" ist nützlicher als "2026-03-06T14:23:03.800Z"
- ✅ **Phase-Divider einfügen** — Visuelle Trennung zwischen Pipeline-Phasen
- ✅ **Event-Details on-demand** — Payload erst bei Click zeigen, nicht inline (zu viel Noise)
- ✅ **Severity korrekt zuordnen** — Warn für loop-detection, replanning.  Error für failed, blocked, circuit_breaker.  Info für alles andere
- ✅ **Auto-Scroll für Live-Runs** — Neue Events sollen sofort sichtbar sein, wenn der Run noch läuft
- ✅ **Phase-Farben konsistent** — Gleiche Farben wie VIEW-01 Pipeline Overview
- ✅ **Duration als Inline-Badge** — Bei Events die eine Dauer haben (z.B. `planning_completed: 3.5s`)
- ✅ **Suchbegriff highlighten** — Wenn der Nutzer sucht, den Treffer in der Event-Zeile markieren
- ✅ **Export-Funktion** — Die Timeline als JSON exportieren für externe Analyse

## 5. Don'ts

- ❌ **Keine absolute Timestamps als Default** — ISO-Zeitstempel nur im Detail-Popover
- ❌ **Nicht alle Payloads inline anzeigen** — `context_segmented` allein hat 6+ Felder — zu viel für die Zeile
- ❌ **Keine eigene Event-Aggregation** — Das ist die Rohansicht.  Aggregation gehört in die anderen Views
- ❌ **Keine Event-Bearbeitung** — Read-only, Events können nicht gelöscht oder modifiziert werden
- ❌ **Kein Infinite Scrolling über Runs hinweg** — Nur Events des aktuellen Runs
- ❌ **Nicht alle 40+ Event-Typen als einzelne Filter-Buttons** — Dropdown mit Mehrfachauswahl statt 40 Toggles
- ❌ **Keine virtualisierte Liste für < 50 Events** — Standard-DOM reicht, Virtualizing erst ab 100+ Events
- ❌ **Nicht die WebSocket-Control-Messages zeigen** — Nur Lifecycle-Events, keine `ping`, `pong`, `ack`

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

| # | Kriterium | Prüfung |
|---|-----------|---------|
| F1 | Alle Lifecycle-Events eines Runs erscheinen in der Timeline | Test-Run → Event-Count im Summary mit Backend-Logs vergleichen |
| F2 | Events sind chronologisch sortiert mit korrekten relativen Timestamps | Erste Event = 0.00s, letzte = `run_completed` Dauer |
| F3 | Phase-Dividers erscheinen an den richtigen Stellen | Visuell prüfen |
| F4 | Click auf Event-Row zeigt vollständige JSON-Payload | Click-Test mit `context_segmented` (viele Felder) |
| F5 | Phase-Filter filtert korrekt (nur Events der gewählten Phase) | Jede Phase einzeln testen |
| F6 | Freitext-Suche filtert Events und highlightet Treffer | Suche nach "grep" → nur Tool-Events mit grep sichtbar |
| F7 | Severity-Toggle filtert korrekt | Nur Warn → nur loop/replan Events sichtbar |
| F8 | Auto-Scroll funktioniert bei Live-Runs | Run starten, Events beobachten |
| F9 | Export downloadet korrektes JSON (Array aller Events) | Download und manuell prüfen |
| F10 | Events erscheinen in Echtzeit (< 100ms nach WebSocket-Empfang) | Timing messen |

### 6.2 Visuell

| # | Kriterium | Prüfung |
|---|-----------|---------|
| V1 | Phase-Farben konsistent mit VIEW-01 | Farbvergleich |
| V2 | Severity-Icons klar unterscheidbar (Info/Warn/Error) | Visuell prüfen |
| V3 | Expandierte Detail-Popover hat JSON-Syntax-Highlighting | JSON mit verschachtelten Objekten testen |
| V4 | Timeline scrollbar ohne horizontale Scrollbar | Responsive Test |
| V5 | Phase-Dividers visuell klar als Trenner erkennbar | Visuell prüfen |

### 6.3 Performance

| # | Kriterium | Prüfung |
|---|-----------|---------|
| P1 | Timeline rendert 30 Events in < 100ms | Performance Profiling |
| P2 | Filter/Suche reagiert in < 50ms | Input-Latenz messen |
| P3 | Auto-Scroll verursacht kein Jitter bei schneller Event-Folge | Stress-Test mit vielen Events |

### 6.4 Accessibility

| # | Kriterium | Prüfung |
|---|-----------|---------|
| A1 | Event-Rows sind per Tastatur navigierbar (Up/Down, Enter zum Expandieren) | Keyboard-Test |
| A2 | Severity hat `aria-label` (z.B. "Warning event") | Screen-Reader-Test |
| A3 | Phase-Dividers haben `role="separator"` mit `aria-label` | Accessibility Audit |
| A4 | Auto-Scroll-Toggle hat `aria-pressed` State | Accessibility Audit |
| A5 | Filter-Dropdowns haben korrekte `aria-expanded` States | Accessibility Audit |

---

## 7. Abhängigkeiten

| Abhängigkeit | Typ | Status |
|-------------|-----|--------|
| Alle bestehenden Lifecycle-Events | Backend | ✅ Existieren (40+) |
| `LifecycleEvent` Interface | Frontend | ✅ Vorhanden im AgentStateService |
| `phase_transition` Event (optional) | Backend | ⬜ Optional |
| EventLogComponent (bestehend) | Frontend | 🔄 Basis-View existiert |
| VIEW-01 Pipeline Overview | Farb-Konsistenz | ✅ Spec exists |

---

## 8. Status

| Meilenstein | Status |
|------------|--------|
| Spec fertig | ✅ |
| Backend-Events | ✅ Alle vorhanden (kein neues Event nötig) |
| Frontend-Komponente | 🔄 EventLogComponent als Basis |
| Filter/Suche | ⬜ Zu implementieren |
| Export | ⬜ Zu implementieren |
| Integration & Test | ⬜ |
