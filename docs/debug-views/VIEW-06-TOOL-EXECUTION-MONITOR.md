# VIEW-06 — Tool Execution Monitor

> Detailliertes Echtzeit-Monitoring jeder einzelnen Tool-Ausführung mit Policy-Gates und Loop-Detection.

---

## 1. Warum brauchen wir diesen View?

Die Tool-Execution-Phase ist die **komplexeste und fehleranfälligste** Phase
der gesamten Pipeline.  Hier geschehen die meisten Probleme:

- **Tool-Auswahl falsch** — Agent wählt `run_command` statt `grep_search`
- **Argumente falsch** — falscher Pfad, falsche Syntax
- **Policy-Block** — Tool wurde durch die Tool-Policy gesperrt
- **Command-Safety** — Befehl wurde aus Sicherheitsgründen blockiert
- **Timeout** — Tool-Ausführung hat das Zeitlimit überschritten
- **Loop-Detection** — Agent ruft dasselbe Tool wiederholt auf (Degenerate Loop)
- **Budget-Erschöpfung** — Maximale Anzahl Tool-Calls erreicht

**Ohne diesen View** hat der Nutzer **null Einblick** in die Gründe für
fehlgeschlagene, blockierte oder langsame Tool-Ausführungen.  Er sieht nur
"Tool: read_file — ✓ OK" aber nicht die Details.

### Konkretes Szenario

Der Agent ruft `run_command` mit `npm install` auf → Policy-Gate pausiert →
Nutzer approvet → Command wird ausgeführt → Timeout nach 90s → Agent replant
mit `write_file` (Fallback).  **Jeder dieser 5 Schritte** muss sichtbar sein.

---

## 2. Datenquellen

### 2.1 Tool-Ausführungsdaten

| Datenpunkt | Event | Details |
|------------|-------|---------|
| Tool gestartet | `tool_started` | `{ tool, index, args }` |
| Tool abgeschlossen | `tool_completed` | `{ tool, index, status, result_chars, duration_ms }` |
| Tool fehlgeschlagen | `tool_failed` | `{ tool, index, error, duration_ms }` |
| Tool blockiert (Policy) | `tool_blocked` | `{ tool, index, reason }` |
| Tool-Detailinfo | `tool_execution_detail` | `{ tool, args, resultPreview, durationMs, exitCode, blocked, timestamp }` |
| Budget überschritten | `tool_budget_exceeded` | `{ tool, current_count, cap }` |

### 2.2 Loop-Detection

| Datenpunkt | Event | Details |
|------------|-------|---------|
| Generischer Repeat | `tool_loop_generic_repeat_warn` / `_critical` | `{ tool, args_hash, repeat_count }` |
| Ping-Pong | `tool_loop_ping_pong_warn` / `_critical` | `{ tools: [A, B], count }` |
| Poll-No-Progress | `tool_loop_poll_no_progress` | `{ tool, identical_results, threshold }` |
| Circuit Breaker | `tool_loop_circuit_breaker` | `{ tool, total_repeats, threshold }` |

### 2.3 Policy-Gating

| Datenpunkt | Event | Details |
|------------|-------|---------|
| Policy-Approval benötigt | `policy_approval_required` | `{ tool, resource, approval_id }` |
| Policy-Entscheidung | `policy_approval_updated` | `{ approval_id, status, decision }` |
| Policy-Override | `policy_override_decision` | `{ tool, decision, reason }` |

### 2.4 Command-Safety

| Datenpunkt | Event | Details |
|------------|-------|---------|
| Allowlist-Check | **Fehlt** — `tool_started` sollte Allowlist-Status enthalten |
| Safety-Pattern-Block | `tool_blocked` | `{ tool, reason: "safety_pattern", pattern }` |

### 2.5 Replanning

| Datenpunkt | Event | Details |
|------------|-------|---------|
| Replan gestartet | `replanning_started` | `{ reason, attempt }` |
| Replan abgeschlossen | `replanning_completed` | `{ new_plan_text }` |
| Replan erschöpft | `replanning_exhausted` | `{ attempts, max_attempts }` |

### 2.6 Benötigte neue Backend-Events

| Event-Stage | Details | Wann |
|-------------|---------|------|
| `tool_safety_check` | `{ tool, command, allowlist_match, safety_patterns_checked, result }` | Vor `run_command`/`code_execute` Ausführung |
| `tool_loop_state` | `{ detectors: { generic: { count }, ping_pong: { active }, poll: { count } }, budget: { used, cap } }` | Nach jeder Tool-Ausführung — aggregierter Loop-State |

---

## 3. UI-Struktur

### 3.1 Tool-Karten (pro Ausführung)

```
┌─ Tool #1 ────────────────────────────────────────┐
│  🔧 read_file                    ✓ OK  · 45ms    │
│                                                   │
│  Args:                                            │
│  { "path": "/workspace/src/main.py" }             │
│                                                   │
│  Result Preview:                                  │
│  import os                                        │
│  from fastapi import FastAPI...                    │
│  [4200 chars total]                               │
│                                                   │
│  Policy: ✓ Allowed · Safety: N/A (kein Command)   │
└───────────────────────────────────────────────────┘

┌─ Tool #2 ────────────────── ⚠ POLICY GATE ───────┐
│  🔧 run_command              ⏳ Awaiting Approval  │
│                                                   │
│  Args:                                            │
│  { "command": "npm install express" }              │
│                                                   │
│  Safety Pipeline:                                 │
│  ├─ Allowlist: ✓ npm in allowlist                 │
│  ├─ Patterns: ✓ No blocked patterns               │
│  └─ Policy:   ⏳ Waiting for user decision         │
│                                                   │
│  [Approve]  [Deny]  [Allow for session]           │
└───────────────────────────────────────────────────┘
```

### 3.2 Loop-Detection-Panel

```
┌─ Loop Detection ─────────────────────────────────┐
│                                                   │
│  Generic Repeat:   2/3 ⚠ (read_file × 2)        │
│  ▓▓▓▓▓▓▓▓░░░░      warn threshold               │
│                                                   │
│  Ping-Pong:        inactive ✓                     │
│  Poll-No-Progress: 0/3 ✓                          │
│  Circuit Breaker:  0/6 ✓                          │
│                                                   │
│  Budget: 3 / 8 calls used                         │
│  ▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░  37.5%               │
│                                                   │
│  Time: 12.4 / 90.0s                              │
│  ▓▓▓▓░░░░░░░░░░░░░░░░░░░░   13.8%               │
└───────────────────────────────────────────────────┘
```

### 3.3 Replan-Timeline

```
┌─ Replan History ─────────────────────────────────┐
│                                                   │
│  [Original Plan] ──✕ empty results───→ [Replan 1] │
│                                                   │
│  Reason: "No tool output from step 2"             │
│  Attempt: 1 / 3                                   │
└───────────────────────────────────────────────────┘
```

---

## 4. Dos

- Jedes Tool als **eigene Karte** darstellen (nicht als Tabellenzeile) — Karten erlauben
  mehr Detail-Platz
- **Result-Preview** collapsible (default collapsed, expandable per Click)
- **Args als formatiertes JSON** (syntax-highlighted, mono font)
- **Policy-Gate** visuell prominent hervorheben (gelber Border, Aktions-Buttons)
- **Loop-Detection** als separates Panel mit Echtzeit-Countern
- **Budget-Verbrauch** als Progress-Bar (calls und Zeit)
- **Safety-Pipeline** als Checklist innerhalb der Tool-Karte (nur für `run_command`/`code_execute`)
- Fehlgeschlagene Tools rot markieren, blockierte gelb, erfolgreiche grün
- **Timing pro Tool** als Badge oben rechts auf der Karte

## 5. Don'ts

- **Nicht** als flache Tabelle — der bestehende Tool-Table im Prompt-Inspector reicht dafür;
  dieser View braucht **Karten mit Details**
- **Keine** Tool-Ergebnisse ungekürzt anzeigen — immer Preview (500 chars max, vom Backend)
- **Nicht** die Policy-Approval-Buttons duplizieren wenn sie im Chat bereits existieren
  — **aber** den Status (pending/approved/denied) muss hier sichtbar sein
- **Keine** Loop-Detection-Schwellenwerte clientseitig berechnen — Backend-Daten verwenden
- **Nicht** die Args unformatiert dumpen — immer JSON-Format mit Highlighting
- **Keinen** full Result-Text anzeigen — nur `resultPreview` (500 chars, Backend-seitig)
- **Keine** Animation auf den Loop-Detection-Countern die den UI-Thread blockiert

---

## 6. Akzeptanzkriterien

### Funktional

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| F-01 | Jede Tool-Ausführung wird als separate Karte dargestellt | Visuell: Karte pro `tool_completed`/`tool_execution_detail` |
| F-02 | Karte zeigt: Tool-Name, Args (JSON), Result-Preview, Duration, Status | Visuell: 5 Datenpunkte pro Karte |
| F-03 | Policy-Gate-Status wird auf der Karte angezeigt (allowed/pending/denied) | E2E: `run_command` → Policy-Event |
| F-04 | Safety-Pipeline wird für `run_command`/`code_execute` angezeigt | Visuell: Allowlist + Pattern-Check |
| F-05 | Loop-Detection-Panel zeigt alle 4 Detektoren mit aktuellen Werten | Visuell: 4 Zeilen mit Thresholds |
| F-06 | Call-Budget-Verbrauch als Progress-Bar (X/8) | Visuell: Balken |
| F-07 | Zeit-Budget-Verbrauch als Progress-Bar (Xs/90s) | Visuell: Balken |
| F-08 | Replan-Events werden als Timeline gezeigt | Visuell: `replanning_started`/`completed`/`exhausted` |
| F-09 | Blockierte Tools sind als solche markiert (gelb/rot) | Visuell: Farbe + Label |
| F-10 | Result-Preview ist collapsible (default collapsed) | Visuell: Click → expand |
| F-11 | Karten erscheinen live bei laufender Tool-Ausführung | E2E: Tool-Events → neue Karte |

### Visuell

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| V-01 | Karten statt Tabelle für einzelne Tools | Code-Review |
| V-02 | Erfolg=grün, Warnung=gelb, Fehler=rot, Blockiert=gelb konsistent | Visuell |
| V-03 | JSON-Args syntax-highlighted | Visuell: Farbige JSON-Keys |
| V-04 | Progress-Bars für Budget nur CSS (kein Canvas) | Code-Review |

### Backend-Voraussetzungen

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| B-01 | `tool_started`, `tool_completed`, `tool_failed`, `tool_blocked` Events vorhanden | Backend-Log |
| B-02 | `tool_execution_detail` mit `args` und `resultPreview` | Backend-Log |
| B-03 | `tool_safety_check` Event (NEU) für Safety-Pipeline-Details | Backend-Event |
| B-04 | `tool_loop_state` Event (NEU) für aggregierte Loop-Detection | Backend-Event |
| B-05 | Loop-Detection-Events (4 Detektoren) | Backend-Log |
| B-06 | `tool_budget_exceeded` Event bei Budget-Überschreitung | Backend-Log |

### Performance

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| P-01 | Max 8 Tool-Karten gleichzeitig (durch Call-Cap) — kein Virtualisierung nötig | Design |
| P-02 | JSON-Highlighting darf UI nicht blockieren (async pipe oder Web Worker) | Für große Args |
| P-03 | Karten-Erscheinen in <100ms nach Event | Visuell: kein spürbares Delay |

### Accessibility

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| A-01 | Tool-Karten als `article` mit `aria-label` ("Tool read_file, Status OK") | Code-Review |
| A-02 | Expand/Collapse für Result-Preview mit `aria-expanded` | Code-Review |
| A-03 | Progress-Bars mit `role="progressbar"`, `aria-valuenow`/`aria-valuemax` | Code-Review |
| A-04 | Status-Farben nicht als einziges Unterscheidungsmerkmal (+ Text/Icon) | Visuell |

---

## 7. Abhängigkeiten

- `DebugSnapshot.toolExecutions` — bestehende Daten
- **Backend-Änderung:** `tool_safety_check` Event, `tool_loop_state` Event
- `DebugSnapshot` — neue Felder: `loopDetectionState`, `toolBudgetUsed`, `toolTimeBudgetMs`
- `applyDebugEvent()` — neue Cases: `tool_safety_check`, `tool_loop_state`, `tool_budget_exceeded`
- Policy-Approval-Daten aus `AgentStateService.approvals$`
- Bestehende Events `tool_started`, `tool_completed`, `tool_failed`, `tool_blocked` müssen
  mit `tool_execution_detail` zusammengeführt werden (Deduplizierung!)

## 8. Status

**Teilweise existent** als Tool-Table im Prompt-Inspector — aber nur als
flache Tabelle mit 5 Spalten.  Dieser View erfordert eine komplett neue
Karten basierte Darstellung mit Loop-Detection, Safety-Pipeline und
Budget-Monitoring — deutlich mehr als der aktuelle Table.
