# VIEW-09 — Reply Shaping & Diff

> Transparente Darstellung aller Transformationen zwischen LLM-Rohausgabe und finaler Nutzerantwort, inkl. Evidence-Gates und Suppressions.

---

## 1. Warum brauchen wir diesen View?

Zwischen der rohen Synthese-Antwort und dem, was der Nutzer tatsächlich sieht,
liegen **bis zu 9 Transformationsschritte**.  Jeder Schritt kann die Antwort
verändern, kürzen oder komplett unterdrücken.  Ohne diesen View ist es
**unmöglich** nachzuvollziehen, warum:

- Bestimmte Textpassagen verschwunden sind
- Die Antwort komplett unterdrückt wurde (Suppression)
- Ein Hinweis "Implementation evidence missing" eingefügt wurde
- Doppelte "Done"-Zeilen entfernt wurden
- TOOL_CALL-Blöcke herausgefiltert wurden

### Konkretes Szenario

1. Synthesis generiert 800 Zeichen Antwort
2. Evidence Gate erkennt: Code-Task aber kein Code → Warning eingefügt
3. Reply Shaper entfernt `[TOOL_CALL]...[/TOOL_CALL]` Block (120 Zeichen)
4. Reply Shaper entfernt 3 duplizierte "Done"-Zeilen
5. Reply Shaper kollabiert 4 Leerzeilen auf 2
6. Finale Antwort: 650 Zeichen

**Der Nutzer sieht nur die 650-Zeichen-Antwort.**  Die fehlenden 150 Zeichen
sind nicht nachvollziehbar.  Noch schlimmer bei Suppression: Die Antwort
verschwindet komplett und der Nutzer weiß nicht warum.

---

## 2. Datenquellen

### 2.1 Evidence Gates (Phase 7, Schritt 1)

| Gate | Event | Payload |
|------|-------|---------|
| Implementation Evidence | `implementation_evidence_missing` | `{ task_type }` |
| Orchestration Evidence | `orchestration_evidence_missing` | `{ task_type }` |
| All Tools Failed | `all_tools_failed_gate_applied` | `{ failed_tool_count }` |

### 2.2 Reply Shaping (Phase 7, Schritt 2)

| Event | Payload | Details |
|-------|---------|---------|
| `reply_shaping_started` | `{ input_chars, input_lines }` | Eingabe-Dimensionen |
| `reply_shaping_completed` | `{ output_chars, was_suppressed, suppression_reason, dedup_lines_removed, removed_tokens, transformations_applied }` | Ergebnis der Shaping-Pipeline |
| `reply_suppressed` | `{ reason, original_chars }` | Wenn die Antwort komplett unterdrückt wurde |

### 2.3 Benötigte neue Backend-Events

| Event | Payload | Zweck |
|-------|---------|-------|
| `reply_shaping_step` | `{ step_index, step_name, input_chars, output_chars, chars_removed, details }` | Pro Transformationsschritt ein Event für maximale Transparenz |
| `reply_shaping_diff` | `{ before_text, after_text }` | Volltext vor und nach Reply Shaping (nur wenn `debug_mode=True`) |
| `evidence_gate_evaluated` | `{ gate_name, triggered, detail }` | Pro Gate ein Event, auch wenn NICHT getriggert (zeigt dass Gate geprüft wurde) |

### 2.4 Die 6 Reply-Shaping-Transformationen

| # | Transformation | Regex/Logik | Potenzielle Wirkung |
|---|---------------|-------------|---------------------|
| 1 | Token Removal | `NO_REPLY`, `ANNOUNCE_SKIP` | Antwort wird leer wenn nur Token |
| 2 | TOOL_CALL Block | `r"\[TOOL_CALL\].*?\[/TOOL_CALL\]"` | Entfernt interne Tool-Referenzen |
| 3 | Tool-Hash Syntax | `r"^\s*\{\s*tool\s*=>[^\n]*\}\s*$"` | Entfernt Tool-Hash-Zeilen |
| 4 | Newline Collapse | 3+ `\n` → 2× `\n` | Kosmetisch, selten problematisch |
| 5 | Deduplication | Konsekutive "done/completed + tool" Zeilen | Entfernt redundante Bestätigungen |
| 6 | Suppression Check | Nur Boilerplate nach Tools? | **Gesamte Antwort wird unterdrückt** |

---

## 3. UI-Struktur

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  REPLY SHAPING & DIFF                                           │
│  Input: 823 chars → Output: 651 chars  (−172 chars, −20.9%)     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───── Evidence Gates ─────────────────────────────────────┐   │
│  │                                                          │   │
│  │  ✅ Implementation Evidence    — not triggered            │   │
│  │  ✅ Orchestration Evidence     — not triggered            │   │
│  │  ⚠️ All-Tools-Failed Gate     — TRIGGERED                │   │
│  │     → Failure notice prepended to answer                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Shaping Pipeline ───────────────────────────────────┐   │
│  │                                                          │   │
│  │  Step  Description              Removed    Status        │   │
│  │  ───── ────────────────────────  ─────────  ──────       │   │
│  │  1     Token removal            0 chars    ✅ No-op      │   │
│  │  2     TOOL_CALL block removal  120 chars  ⚠ Modified    │   │
│  │  3     Tool-hash syntax         0 chars    ✅ No-op      │   │
│  │  4     Newline collapse         8 chars    ⚠ Modified    │   │
│  │  5     Deduplication            3 lines    ⚠ Modified    │   │
│  │  6     Suppression check        —          ✅ Not suppr. │   │
│  │                                                          │   │
│  │  Total removed: 172 chars, 3 dedup lines                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Text Diff ──────────────────────────────────────────┐   │
│  │                                                          │   │
│  │  [Unified ▾]  [Side-by-Side]  [Before Only]  [After Only]│   │
│  │                                                          │   │
│  │  --- Before Reply Shaping                                │   │
│  │  +++ After Reply Shaping                                 │   │
│  │                                                          │   │
│  │    Here is the analysis of the auth system:              │   │
│  │  - [TOOL_CALL]read_file auth.py[/TOOL_CALL]             │   │
│  │  - Done. Read auth.py successfully.                      │   │
│  │  - Done. Read auth.py successfully.                      │   │
│  │  - Done. Read auth.py successfully.                      │   │
│  │    The authentication flow works as follows...           │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Spezial-Zustand: Suppression

```
┌─────────────────────────────────────────────────────────────────┐
│  REPLY SHAPING & DIFF                                           │
│  ⛔ ANTWORT UNTERDRÜCKT                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───── Suppression Details ────────────────────────────────┐   │
│  │                                                          │   │
│  │  ⛔ Die Antwort wurde vollständig unterdrückt             │   │
│  │                                                          │   │
│  │  Grund: "Only boilerplate acknowledgment after tool      │   │
│  │          execution — no substantive content"             │   │
│  │                                                          │   │
│  │  Originaler Text (823 chars):                            │   │
│  │  ┌──────────────────────────────────────────────────┐    │   │
│  │  │ Done. I've read the file.                        │    │   │
│  │  │ Done. I've listed the directory.                 │    │   │
│  │  │ The task has been completed successfully.        │    │   │
│  │  └──────────────────────────────────────────────────┘    │   │
│  │                                                          │   │
│  │  → Alle 823 Zeichen waren Boilerplate                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Komponenten

| Komponente | Beschreibung |
|------------|-------------|
| **Summary Bar** | Input-/Output-Zeichenzahl mit prozentualer Differenz |
| **Evidence Gate Checklist** | 3 Gates als Checkliste mit Status (passed/triggered) |
| **Shaping Pipeline Table** | 6-Zeilen-Tabelle mit Step #, Description, Removed, Status |
| **Text Diff** | Unified/Side-by-Side Diff zwischen Vor- und Nach-Shaping |
| **Diff Mode Toggle** | 4 Ansichtsmodi: Unified, Side-by-Side, Before Only, After Only |
| **Suppression Alert** | Prominente Warnung bei vollständiger Unterdrückung |
| **Removed Tokens List** | Liste der entfernten Spezial-Tokens (NO_REPLY, ANNOUNCE_SKIP) |

---

## 4. Dos

- ✅ **Jeden Schritt einzeln dokumentieren** — Auch No-op-Schritte zeigen ("Token removal: 0 chars removed"), damit der Nutzer sieht, dass geprüft wurde
- ✅ **Diff visuell hervorheben** — Entfernte Zeilen rot, hinzugefügte grün (Standard-Diff-Farben)
- ✅ **Suppression maximal prominent machen** — Wenn die Antwort unterdrückt wurde, ist das die wichtigste Information des gesamten Runs
- ✅ **Originalen Text bei Suppression zeigen** — Der Nutzer muss sehen, was unterdrückt wurde, um zu verstehen warum
- ✅ **Evidence Gates separat von Reply Shaping zeigen** — Es sind konzeptuell verschiedene Phasen (Prüfung vs. Transformation)
- ✅ **Prozentualen Verlust in Summary Bar zeigen** — "−20.9%" gibt sofort ein Gefühl für die Intensität der Änderungen
- ✅ **Dedup-Count anzeigen** — "3 lines removed" ist wertvoller als nur "Modified"

## 5. Don'ts

- ❌ **Keine Regex-Patterns anzeigen** — Die internen Regex-Muster der Shaping-Pipeline sind Implementierungsdetails
- ❌ **Kein Live-Editing der Antwort** — Der View ist read-only, der Nutzer kann die Antwort nicht manuell nachbearbeiten
- ❌ **Nicht den gesamten Vor-/Nach-Text immer laden** — Text erst bei Diff-Tab-Auswahl rendern (können 10.000+ Zeichen sein)
- ❌ **Keine eigene Diff-Engine schreiben** — Bestehende Library nutzen (z.B. `diff-match-patch` oder `jsdiff`)
- ❌ **Nicht die Section-Contract-Validierung hier zeigen** — Das gehört zum Synthesis-Kontext, nicht zum Reply Shaping
- ❌ **Suppression nicht als Fehler darstellen** — Suppression ist erwünschtes Verhalten (Boilerplate-Filter).  Neutral informieren, nicht alarmieren
- ❌ **Keine Diff bei trivialem Request** — Wenn Input = Output (0 Änderungen), zeige "No modifications" statt leerem Diff

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

| # | Kriterium | Prüfung |
|---|-----------|---------|
| F1 | Summary Bar zeigt korrekte Input/Output-Zeichenzahl und Prozent | Manuell nachrechnen |
| F2 | Alle 3 Evidence Gates werden angezeigt (auch wenn nicht getriggert) | Verschiedene Task-Types testen |
| F3 | Alle 6 Shaping-Steps werden in der Pipeline-Tabelle angezeigt | Request mit TOOL_CALL-Blocks senden |
| F4 | Diff zeigt korrekte Unterschiede zwischen Vor- und Nach-Shaping | Diff manuell verifizieren |
| F5 | 4 Diff-Modi funktionieren (Unified, Side-by-Side, Before, After) | Alle Modi durchklicken |
| F6 | Suppression-Zustand zeigt Grund und Originaltext | Boilerplate-Only-Antwort provozieren |
| F7 | Dedup-Count zeigt korrekte Anzahl entfernter Zeilen | Event-Payload prüfen |
| F8 | Entfernte Tokens (NO_REPLY, ANNOUNCE_SKIP) werden aufgelistet | Speziellen Token provozieren |
| F9 | Bei 0 Änderungen: "No modifications applied" statt leerem Diff | Triviale Anfrage senden |
| F10 | Evidence Gate "all_tools_failed" zeigt Prepend-Notice | Alle Tools zum Scheitern bringen |

### 6.2 Visuell

| # | Kriterium | Prüfung |
|---|-----------|---------|
| V1 | Diff-Farben: Rot für Entferntes, Grün für Hinzugefügtes | Visuell prüfen |
| V2 | Suppression-Alert visuell prominent (Hintergrundfarbe, Icon) | Visuell prüfen |
| V3 | No-op-Steps visuell gedämpft (Grau) vs. Modified-Steps (gelb/orange) | Visuell prüfen |
| V4 | Monospace-Font für Diff-Inhalte | Visuell prüfen |

### 6.3 Backend-Voraussetzungen

| # | Kriterium | Prüfung |
|---|-----------|---------|
| B1 | `reply_shaping_completed` Event enthält `dedup_lines_removed` und `removed_tokens` | WebSocket-Monitor |
| B2 | `reply_shaping_step` Events werden pro Schritt emittiert (nur wenn `debug_mode=True`) | WebSocket-Monitor |
| B3 | `reply_shaping_diff` Event enthält Vor-/Nach-Text (nur wenn `debug_mode=True`) | WebSocket-Monitor |
| B4 | `evidence_gate_evaluated` Events für alle 3 Gates | WebSocket-Monitor |

### 6.4 Accessibility

| # | Kriterium | Prüfung |
|---|-----------|---------|
| A1 | Diff-Farben haben zusätzliche Markierungen (+/−) für Farbenblinde | Farbenblindheit-Simulation |
| A2 | Suppression-Alert hat `role="alert"` | Accessibility Audit |
| A3 | Pipeline-Tabelle hat korrekte `<th>` und `scope` Attribute | Accessibility Audit |

---

## 7. Abhängigkeiten

| Abhängigkeit | Typ | Status |
|-------------|-----|--------|
| `reply_shaping_started` Event | Backend | ✅ Existiert |
| `reply_shaping_completed` Event | Backend | ✅ Existiert |
| `reply_suppressed` Event | Backend | ✅ Existiert |
| `implementation_evidence_missing` Event | Backend | ✅ Existiert |
| `orchestration_evidence_missing` Event | Backend | ✅ Existiert |
| `all_tools_failed_gate_applied` Event | Backend | ✅ Existiert |
| `reply_shaping_step` Event | Backend | ⬜ Neu |
| `reply_shaping_diff` Event | Backend | ⬜ Neu |
| `evidence_gate_evaluated` Event | Backend | ⬜ Neu |
| Diff-Library (z.B. `diff-match-patch`) | npm Dependency | ⬜ Zu evaluieren |
| VIEW-08 Reflection Scorecard | Cross-Link (Scores) | 📋 Spec exists |

---

## 8. Status

| Meilenstein | Status |
|------------|--------|
| Spec fertig | ✅ |
| Backend-Events definiert | ✅ (in diesem Dokument) |
| Backend-Events implementiert | ⬜ |
| Frontend-Komponente | ⬜ Neu zu erstellen |
| Diff-Library evaluiert | ⬜ |
| Integration & Test | ⬜ |
