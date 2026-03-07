# VIEW-07 — LLM Call Inspector

> Chronologische Übersicht **aller** LLM-Aufrufe eines Runs mit vollständigem Prompt-/Response-Inhalt, Timing und Token-Kosten.

---

## 1. Warum brauchen wir diesen View?

Jeder Request durchläuft **3–8 LLM-Aufrufe** (siehe LLM Call Budget).
Der aktuelle Prompt Inspector zeigt die Aufrufe pro Tab (Plan/Tool/Synth/Reflect),
aber **nicht** den chronologischen Gesamtfluss und **nicht** die Beziehungen
zwischen den Aufrufen (z.B. "Repair wurde getriggert, weil Tool-Selection
kein valides JSON lieferte").

### Konkretes Szenario

1. Planning-Call → Plan mit 4 Steps
2. Tool-Selection-Call → malformed JSON
3. **Repair-Call** → repariertes JSON
4. Tool-Execution (kein LLM-Call, aber Kontext für #5)
5. Replan-Call → aktualisierter Plan
6. Synthesis-Call → Antwort (streaming)
7. Reflection-Call → Score 0.58 (unter Threshold 0.65)
8. Re-Synthesis-Call → verbesserte Antwort

**Ohne VIEW-07** sieht der Nutzer nur die Ergebnisse der einzelnen Phasen,
aber nicht **warum** ein Repair oder Replan passiert ist und was sich
zwischen den Calls verändert hat.

---

## 2. Datenquellen

### 2.1 Bestehende Events & Daten

| Datenpunkt | Quelle | Details |
|------------|--------|---------|
| System Prompt | `DebugSnapshot.llmCalls[].systemPrompt` | Volltext des System-Prompts |
| User Prompt | `DebugSnapshot.llmCalls[].userPrompt` | Volltext des User-Prompts |
| Raw Response | `DebugSnapshot.llmCalls[].rawResponse` | Ungefilterte LLM-Antwort |
| Model | `DebugSnapshot.llmCalls[].model` | Genutztes Modell |
| Latency | `DebugSnapshot.llmCalls[].latencyMs` | Dauer in Millisekunden |
| Token-Schätzung | `DebugSnapshot.llmCalls[].estimatedTokens` | Geschätzte Token-Anzahl |
| Phase | `DebugSnapshot.llmCalls[].phase` | `plan`, `tool`, `repair`, `replan`, `synthesis`, `reflection`, `re-synthesis`, `distillation` |
| Timestamp | `DebugSnapshot.llmCalls[].timestamp` | ISO-Zeitstempel |

### 2.2 Benötigte neue Backend-Events

| Event | Payload | Zweck |
|-------|---------|-------|
| `llm_call_started` | `{ call_index, phase, model, system_prompt_chars, user_prompt_chars, temperature, max_context }` | Marker für Call-Beginn, zeigt Konfigurationswerte |
| `llm_call_completed` | `{ call_index, phase, model, latency_ms, estimated_tokens, response_chars, parsed_ok, trigger_reason }` | Marker für Call-Ende, enthält `trigger_reason` (z.B. `"initial"`, `"json_repair"`, `"replan_empty_result"`, `"reflection_retry"`) |
| `llm_prompt_snapshot` | `{ call_index, phase, system_prompt, user_prompt, raw_response }` | Vollständiger Prompt-Inhalt (nur wenn `debug_mode=True`) |

### 2.3 Bestehende nutzbare Events

| Event | Relevanz |
|-------|----------|
| `planning_started` / `planning_completed` | Rahmen für Call #1 |
| `replanning_started` / `replanning_completed` | Markiert Replan-Call |
| `reflection_completed` / `reflection_skipped` | Enthält Score-Details |
| `context_segmented` (×3) | Budget-Snapshot pro Phase |

---

## 3. UI-Struktur

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM CALL INSPECTOR                              Σ 5 calls     │
│  Total: 14.2s  |  ~8 400 tokens  |  Model: llama3.3:70b        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ ① PLANNING ─────────────────────────────────────────── ▾ ─┐ │
│  │  Model: llama3.3:70b   Latency: 3.2s   ~1 800 tok          │ │
│  │  Trigger: initial                                           │ │
│  │  ┌──────────────────────────────────────────────────────┐   │ │
│  │  │  [System Prompt ▾]  [User Prompt ▾]  [Response ▾]   │   │ │
│  │  │                                                      │   │ │
│  │  │  ──── System Prompt (2 048 chars) ────               │   │ │
│  │  │  You are a planning agent...                         │   │ │
│  │  │  ... (scrollbar)                                     │   │ │
│  │  └──────────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                        │                                        │
│                        ▼ (Pfeil: Datenfluss)                    │
│                                                                 │
│  ┌─ ② TOOL SELECTION ──────────────────────────────────── ▾ ─┐ │
│  │  Model: llama3.3:70b   Latency: 2.8s   ~1 200 tok          │ │
│  │  Trigger: initial                                           │ │
│  │  ⚠ JSON Parse Failed → Repair triggered                    │ │
│  │  ┌──────────────────────────────────────────────────────┐   │ │
│  │  │  [System Prompt ▾]  [User Prompt ▾]  [Response ▾]   │   │ │
│  │  └──────────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                        │                                        │
│                        ▼                                        │
│                                                                 │
│  ┌─ ③ REPAIR ──────────────────────────────────────────── ▾ ─┐ │
│  │  Model: llama3.3:70b   Latency: 1.1s   ~600 tok            │ │
│  │  Trigger: json_repair (malformed output from call #2)       │ │
│  │  ┌──────────────────────────────────────────────────────┐   │ │
│  │  │  [System Prompt ▾]  [User Prompt ▾]  [Response ▾]   │   │ │
│  │  └──────────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                        │                                        │
│                       ...                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Komponenten

| Komponente | Beschreibung |
|------------|-------------|
| **Summary Bar** | Gesamtzahl Calls, Gesamtdauer, Gesamttokens, dominantes Modell |
| **Call Card** (pro LLM-Call) | Collapsible Card mit Phase-Badge, Model, Latenz, Token-Schätzung, Trigger-Reason |
| **Prompt Tabs** | 3 Tabs innerhalb jeder Card: System Prompt, User Prompt, Response |
| **Flow Arrows** | CSS-Pfeile zwischen den Cards, die den Datenfluss visualisieren |
| **Error Banner** | Innerhalb einer Card, wenn Parse-Fehler / Repair getriggert wurde |
| **Copy Button** | Pro Tab-Inhalt, kopiert den Volltext in die Zwischenablage |
| **Token Budget Indicator** | Kleiner Fortschrittsbalken: verbrauchte vs. verfügbare Tokens |

### 3.3 Interaktionen

| Aktion | Verhalten |
|--------|-----------|
| Card kollabieren/expandieren | Click auf Card-Header toggled Inhalt |
| Tab wechseln | Click auf System/User/Response Tab zeigt jeweiligen Inhalt  |
| Copy | Button kopiert aktuellen Tab-Inhalt |
| Diff-Toggle (optional) | Zwischen zwei Calls derselben Phase (z.B. Synthesis vs. Re-Synthesis) wird ein Diff angezeigt |
| Filter by Phase | Dropdown filtert auf bestimmte Phasen (z.B. nur Repair-Calls) |
| Search | Text-Suche innerhalb aller Prompts/Responses |

---

## 4. Dos

- ✅ **Chronologisch sortieren** — Calls immer in zeitlicher Reihenfolge anzeigen, mit laufender Nummer
- ✅ **Trigger-Reason prominent zeigen** — Warum wurde dieser Call ausgelöst?  Ist er ein Repair?  Ein Retry nach Reflection?
- ✅ **Flow-Arrows** — Visuelle Verbindung zwischen den Cards, damit der Nutzer den Fluss versteht
- ✅ **Collapsible Cards** — Default: nur Header sichtbar, Inhalt on-demand
- ✅ **Syntax Highlighting** — Prompts und Responses mit Monospace-Font und ggf. Markdown-Rendering
- ✅ **Lazy Content Loading** — Prompt-Inhalte erst laden, wenn die Card expandiert wird (können sehr lang sein)
- ✅ **Phase-spezifische Farben** — Gleiche Farben wie in VIEW-01 Pipeline Overview für Konsistenz
- ✅ **Token-Budget-Kontext** — Zeige für jeden Call: "Dieser Call verbraucht ~1800 von 8000 verfügbaren Context-Tokens"
- ✅ **Diff zwischen verwandten Calls** — Synthesis vs. Re-Synthesis als Diff anbieten, damit der Nutzer sieht, was die Reflection verbessert hat

## 5. Don'ts

- ❌ **Keine Live-Streaming-Ansicht** — Der Inspector zeigt abgeschlossene Calls, kein Token-by-Token-Streaming
- ❌ **Keine Prompt-Bearbeitung** — Read-Only View.  Prompts sind nicht editierbar
- ❌ **Keine automatische Expansion** — Alle Cards default zugeklappt, damit der View bei 8+ Calls nicht überwältigend wird
- ❌ **Keine Token-Schätzung selbst berechnen** — Nur Backend-berechnete Werte anzeigen, keine Frontend-Tokenizer
- ❌ **Keine Sensible-Data-Anzeige** — Wenn Prompts Passwörter/Keys enthalten, sind diese bereits vom Backend redacted.  Nicht nochmal filtern, aber auch nicht de-redacten
- ❌ **Keine API-Keys in Prompt-Dumps** — Der Prompt-Snapshot darf keine echten Service-Credentials enthalten
- ❌ **Nicht alle Content-Längen gleichzeitig rendern** — Bei 8 Calls × 3 Tabs = 24 potenzielle Textblöcke.  Nur den sichtbaren rendern
- ❌ **Kein eigener Scroll-Container pro Prompt** — Stattdessen max-height mit "Show more" Button

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

| # | Kriterium | Prüfung |
|---|-----------|---------|
| F1 | Alle LLM-Calls eines Runs werden chronologisch als Cards angezeigt | Test-Run mit 5+ Calls → alle sichtbar |
| F2 | Jede Card zeigt: Phase-Badge, Model, Latenz (ms), Token-Schätzung, Trigger-Reason | Visuell prüfen |
| F3 | System Prompt, User Prompt, Response sind als Tabs pro Card verfügbar | Tab-Wechsel funktioniert |
| F4 | Copy-Button kopiert Tab-Inhalt korrekt in Zwischenablage | Paste-Test |
| F5 | Summary Bar zeigt korrekte Aggregate (Σ Calls, Σ Zeit, Σ Tokens) | Manuell nachrechnen |
| F6 | Filter-Dropdown filtert auf Phase (plan, tool, repair, replan, synthesis, reflection, re-synthesis, distillation) | Jede Phase einzeln testen |
| F7 | Cards sind collapsible, Default: alle zugeklappt | Click-Test |
| F8 | Bei Repair-Calls: Error-Banner mit Erklärung sichtbar | Provozieren mit malformed Output |
| F9 | Flow-Arrows zwischen Cards sind korrekt gerendert | Visuell prüfen |
| F10 | Diff-Toggle zwischen Synthesis und Re-Synthesis funktioniert (wenn beide existieren) | Reflection-Retry provozieren |

### 6.2 Visuell

| # | Kriterium | Prüfung |
|---|-----------|---------|
| V1 | Phase-Badge-Farben konsistent mit VIEW-01 Pipeline Overview | Farbvergleich |
| V2 | Prompt-Inhalte in Monospace-Font mit Word-Wrap | Visuell prüfen |
| V3 | Kein horizontales Scrollen bei langen Prompts | Browser-Test |
| V4 | Cards mit max-width, zentriert im Container | Responsive Test |
| V5 | Dark-Mode-kompatibel (falls vorhanden) | Theme-Wechsel |

### 6.3 Backend-Voraussetzungen

| # | Kriterium | Prüfung |
|---|-----------|---------|
| B1 | `llm_call_started` Event wird bei jedem LLM-Call emittiert (nur wenn `debug_mode=True`) | WebSocket-Monitor |
| B2 | `llm_call_completed` Event enthält `trigger_reason` | WebSocket-Monitor |
| B3 | `llm_prompt_snapshot` Event enthält vollständige Prompts (nur wenn `debug_mode=True`) | WebSocket-Monitor |
| B4 | Prompts enthalten keine unredacted Secrets | Log-Review |

### 6.4 Performance

| # | Kriterium | Prüfung |
|---|-----------|---------|
| P1 | View rendert innerhalb 200ms, auch bei 8 Calls | Performance Profiling |
| P2 | Collapsed Cards rendern keine Prompt-Inhalte | DOM-Inspektion |
| P3 | Prompts > 10.000 Zeichen werden virtuell gescrollt oder mit "Show more" limitiert | Test mit langem Prompt |

### 6.5 Accessibility

| # | Kriterium | Prüfung |
|---|-----------|---------|
| A1 | Cards sind per Tastatur navigierbar (Enter/Space zum Toggler) | Keyboard-Test |
| A2 | Phase-Badge hat `aria-label` (z.B. "Phase: Planning") | Screen-Reader-Test |
| A3 | Tabs haben `role="tablist"` / `role="tab"` / `role="tabpanel"` | Accessibility Audit |

---

## 7. Abhängigkeiten

| Abhängigkeit | Typ | Status |
|-------------|-----|--------|
| VIEW-01 Pipeline Overview | Farb-Konsistenz | ✅ Spec exists |
| `DebugSnapshot.llmCalls[]` | Frontend-Modell | ✅ Vorhanden |
| `llm_call_started` Event | Backend | ⬜ Neu zu implementieren |
| `llm_call_completed` Event | Backend | ⬜ Neu zu implementieren |
| `llm_prompt_snapshot` Event | Backend | ⬜ Neu zu implementieren |
| Prompt Inspector (bestehend) | Refactoring | 🔄 Aktueller View wird zu VIEW-07 erweitert |

---

## 8. Status

| Meilenstein | Status |
|------------|--------|
| Spec fertig | ✅ |
| Backend-Events definiert | ✅ (in diesem Dokument) |
| Backend-Events implementiert | ⬜ |
| Frontend-Komponente | 🔄 Bestehender Prompt Inspector als Basis |
| Integration & Test | ⬜ |
