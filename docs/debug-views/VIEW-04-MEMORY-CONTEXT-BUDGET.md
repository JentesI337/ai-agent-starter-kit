# VIEW-04 — Memory & Context Budget Inspector

> Vollständige Einsicht in den Konversationsspeicher und die Token-Budget-Allokation.

---

## 1. Warum brauchen wir diesen View?

Memory und Context-Budgeting sind die **unsichtbarsten** Teile der Pipeline.
Der Nutzer hat aktuell **kein Verständnis** dafür:

- **Welche Memory-Einträge** werden für den aktuellen Request geladen?
- **Wie viel Token-Budget** wird für welchen Zweck reserviert (System-Prompt vs.
  Tool-Outputs vs. Memory vs. Workspace-Snapshot)?
- **Wurde der Context gekürzt** und wenn ja, um wie viel?
- **Wurden Orphaned-Tool-Calls repariert?** (wichtiger Debugging-Hinweis)
- **Wurden Patterns redaktiert?** (Bearer-Tokens, API-Keys)

**Ohne diesen View** kann der Nutzer nicht nachvollziehen, warum der Agent
bestimmte Konversationsgeschichte "vergessen" hat oder warum ein Tool-Output
abgeschnitten wurde.

### Konkretes Szenario

Der Nutzer schickt mehrere Nachrichten, die auf Tool-Ergebnissen aufbauen.
In Nachricht #7 "vergisst" der Agent das Ergebnis aus Nachricht #3.
**Grund:** Die Memory-Deque hat nur 20 Einträge und ältere wurden verdrängt.
Ohne den Memory-View ist das nicht debugbar.

---

## 2. Datenquellen

### 2.1 Memory-Daten

| Datenpunkt | Source | Event |
|------------|--------|-------|
| Session-History (aktuelle Deque) | `MemoryStore.get(session_id)` | **Fehlt** — muss als Event exponiert werden |
| Memory-Reparaturen | `repair_orphaned_tool_calls()` | `orphaned_tool_calls_repaired` mit `{ count }` |
| History-Sanitization | `sanitize_session_history()` | `session_history_sanitized` mit `{ removed_count }` |
| Neuer User-Eintrag | `add(session_id, "user", msg)` | `memory_updated` |
| Deque-Kapazität | `max_items_per_session` (default 20) | Config-Wert |

### 2.2 Context-Budget-Daten

Aus dem **dreifach emittierten** `context_segmented` Event:

```json
{
  "phase": "planning|tool|synthesis",
  "budget_tokens": 4096,
  "used_tokens": 2800,
  "segments": {
    "system_prompt": { "tokens_est": 512, "chars": 2048, "share_pct": 18 },
    "user_payload":  { "tokens_est": 256, "chars": 1024, "share_pct": 9 },
    "memory":        { "tokens_est": 800, "chars": 3200, "share_pct": 29 },
    "tool_results":  { "tokens_est": 1100, "chars": 4400, "share_pct": 39 }
  }
}
```

### 2.3 Context-Reduktion

| Datenpunkt | Event |
|------------|-------|
| Context wurde reduziert | `context_reduced` mit `{ original_tokens, reduced_tokens, strategy }` |
| Redaktion sensitiver Daten | **Fehlt** — muss als Event exponiert werden |

### 2.4 Benötigte neue Backend-Events

| Event-Stage | Details | Wann |
|-------------|---------|------|
| `memory_snapshot` | `{ session_id, entries: [{ role, content_preview, timestamp }], total_entries, max_capacity }` | Nach `add()` — zeigt aktuelle Deque (content gekürzt auf 200 chars) |
| `context_redaction_applied` | `{ pattern_type, count, positions }` | Wenn sensitive Patterns redaktiert wurden |

---

## 3. UI-Struktur

### 3.1 Memory-Sektion

```
┌─ Session Memory ─────────────────────────────────┐
│ Session: sess-456 · 14 / 20 Einträge             │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░  70% belegt                │
│                                                   │
│ #14  user     "Erstelle mir eine REST API..."     │
│ #13  assistant "Hier ist die Implementierung..."  │
│ #12  user     "Welche Dateien gibt es?"           │
│ #11  assistant "Im Verzeichnis /src befinden..."  │
│ #10  tool     [read_file] /src/main.py            │
│  ...                                              │
│ #1   user     "Hallo, ich brauche Hilfe bei..."   │
│                                                   │
│ ⚠ 2 orphaned tool calls repariert                │
│ ⚠ 1 malformed entry sanitized                    │
└───────────────────────────────────────────────────┘
```

- Neueste oben, älteste unten
- `content_preview` auf 200 chars (vom Backend gekürzt)
- Role-Badge farbig: user=blau, assistant=grün, tool=orange
- Kapazitäts-Balken oben (X / 20)
- Warnungen für Reparaturen/Sanitization

### 3.2 Context-Budget-Donut (3× — pro Phase)

```
┌─ Context Budget ─────────────────────────────────┐
│                                                   │
│  Planning            Tool Selection    Synthesis  │
│                                                   │
│   ┌──────┐            ┌──────┐        ┌──────┐   │
│   │ 68%  │            │ 82%  │        │ 91%  │   │
│   │ used │            │ used │        │ used │   │
│   └──────┘            └──────┘        └──────┘   │
│                                                   │
│  System:  512 tok    System:  512     System: 512 │
│  User:    256 tok    User:    256     User:   256 │
│  Memory:  800 tok    Memory:  800     Memory: 800 │
│  Tools:     0 tok    Tools: 1100     Tools: 1100 │
│  ─────────────       ─────────────   ────────────│
│  Total: 1568/4096    Total: 2668/4096 3668/4096  │
│                                                   │
│  ⚠ Context reduced: 5200 → 4096 tokens (21%)    │
└───────────────────────────────────────────────────┘
```

- 3 nebeneinander stehende Donut-Charts (CSS-only, keine SVG/Canvas)
- Oder Stacked-Bar-Charts mit 4 Segmenten pro Phase
- Legende gemeinsam für alle drei
- Warning wenn `context_reduced` Event vorliegt

### 3.3 Redaction-Sektion (nur sichtbar wenn Redaktionen erfolgten)

```
┌─ Redactions ─────────────────────────────────────┐
│ 🔒 2 sensitive patterns redacted                  │
│    • Bearer token (position 1240)                 │
│    • API key pattern (position 3891)              │
└───────────────────────────────────────────────────┘
```

---

## 4. Dos

- Memory-Einträge mit Scrollbar anzeigen (maxHeight: 300px, overflow-y: auto)
- Content **nur als Preview** (200 chars, Backend-seitig gekürzt) — kein Full-Content
- Budget-Aufteilung als **Stacked Horizontal Bar** oder **Donut** — nicht als Tabelle
- Drei Phasen (Planning, Tool, Synthesis) nebeneinander vergleichbar machen
- `context_segmented` Events sammeln und nach `phase` gruppieren
- Warnungen für Orphaned-Tool-Calls und Sanitization prominent anzeigen
- Kapazitäts-Balken für Memory-Deque (X/20)
- Redaktions-Hinweise zeigen (Anzahl, nicht den redaktierten Content!)

## 5. Don'ts

- **Niemals** den vollen Memory-Content anzeigen — nur Preview (200 chars)
- **Niemals** redaktierte Daten anzeigen (Bearer-Tokens etc.) — nur Anzahl + Typ
- **Keine** SVG- oder Canvas-Charts — reine CSS-Lösungen (Balken, Donut per `conic-gradient`)
- **Nicht** die drei `context_segmented` Events als separate Views — in einem View nebeneinander
- **Keine** Editier-Möglichkeit für Memory — read-only
- **Nicht** die Deque-Reihenfolge umdrehen ohne klare Kennzeichnung (neueste oben)

---

## 6. Akzeptanzkriterien

### Funktional

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| F-01 | Memory-Einträge werden als scrollbare Liste angezeigt | Visuell: Liste mit Role + Preview |
| F-02 | Kapazitäts-Anzeige (X/20) ist korrekt | Vergleich mit Backend-State |
| F-03 | Orphaned-Tool-Call-Reparaturen werden als Warnung angezeigt | E2E: `orphaned_tool_calls_repaired` Event |
| F-04 | Context-Budget wird für alle 3 Phasen angezeigt | Visuell: 3 Charts nach `context_segmented` Events |
| F-05 | Jedes Segment zeigt Token-Zahl und Prozentanteil | Visuell: 4 Segmente pro Phase |
| F-06 | Context-Reduktion wird als Warnung angezeigt | E2E: `context_reduced` Event mit Before/After |
| F-07 | Redaktions-Hinweis bei sensitiven Patterns | E2E: `context_redaction_applied` Event |
| F-08 | Budget-Überlauf wird visuell hervorgehoben (rot) | Visuell: wenn used > budget |

### Visuell

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| V-01 | Stacked-Bar-Chart oder Donut nur CSS (kein Canvas) | Code-Review |
| V-02 | Role-Badges farblich konsistent (user=blau, assistant=grün, tool=orange) | Visuell |
| V-03 | Responsive: bei schmalem Screen stapeln sich die 3 Budget-Charts vertikal | Resize-Test |
| V-04 | Memory-Liste scrollbar mit max-height | CSS-Prüfung |

### Backend-Voraussetzungen

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| B-01 | `memory_snapshot` Event mit Entry-Previews (200 chars max) | Backend-Event prüfen |
| B-02 | `context_segmented` Event hat alle 4 Segment-Details | Backend-Event prüfen |
| B-03 | `context_redaction_applied` Event (ohne redaktierten Content!) | Backend-Event prüfen |
| B-04 | `context_reduced` Event mit original/reduced Token-Zahlen | Backend-Event prüfen |

### Accessibility

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| A-01 | Memory-Liste als `role="list"` | Code-Review |
| A-02 | Charts mit `aria-label` die Proportionen beschreibt | Screen-Reader Test |
| A-03 | Warnungen mit `role="alert"` | Code-Review |

---

## 7. Abhängigkeiten

- **Backend-Änderung erforderlich:** `memory_snapshot` Event, `context_redaction_applied` Event
- `DebugSnapshot` — neue Felder: `memoryEntries`, `contextBudgets` (Map<phase, SegmentBreakdown>),
  `contextReductions`, `redactionCount`
- `applyDebugEvent()` — neue Cases: `memory_snapshot`, `context_segmented`, `context_reduced`,
  `context_redaction_applied`
- Existing Events `memory_updated`, `orphaned_tool_calls_repaired`, `session_history_sanitized`
  müssen bereits korrekt verarbeitet werden

## 8. Status

**Existiert nicht.** Komplett neuer View.  Backend-Änderungen erforderlich.
`context_segmented` Event existiert im Backend, aber wird vom Frontend noch
nicht in der UI visualisiert.
