# VIEW-05 — Plan Inspector

> Detaillierte Ansicht des KI-generierten Ausführungsplans mit Schritt-Abhängigkeiten.

---

## 1. Warum brauchen wir diesen View?

Die Planning-Phase ist der Moment, in dem der Agent **entscheidet**, was er tun
wird.  Diese Entscheidung ist fundamental:

- **Klassifikation** — Hat der Agent den Request als `trivial`, `moderate` oder
  `complex` eingestuft?
- **Schritte** — Welche konkreten Schritte hat er geplant?
- **Tool-Zuordnung** — Welches Tool wird pro Schritt gewählt?
- **Abhängigkeiten** — Welche Schritte hängen voneinander ab?
- **Verification** — Hat die Plan-Verifikation Probleme gefunden?

**Ohne diesen View** sieht der Nutzer nur das Endergebnis und kann nicht
nachvollziehen, ob der Agent den falschen Ansatz gewählt hat (z.B. zu wenige
Schritte, falsche Tool-Wahl, fehlende Abhängigkeiten).

### Konkretes Szenario

Der Nutzer fragt "Refactor die Auth-Middleware" — der Agent plant nur 1 Schritt
(read_file) statt einer vollständigen Refactoring-Sequenz (read → analyze →
write → test).  **Nur mit dem Plan-View** wäre sofort sichtbar gewesen, dass
der Plan unvollständig ist.

---

## 2. Datenquellen

### 2.1 Plan-Daten

| Datenpunkt | Source | Event |
|------------|--------|-------|
| Plan-Text (Rohtext) | LLM-Output der Planning-Phase | `debug_prompt_sent` (phase=`planning`) + `debug_llm_response` (phase=`planning`) |
| Klassifikation (trivial/moderate/complex) | Im Plan-Text enthalten | Parsing des Plan-Texts |
| Einzelne Schritte | Im Plan-Text strukturiert | Parsing des Plan-Texts |
| Verification-Ergebnis | `VerificationService.verify_plan()` | `verification_plan` mit `{ status, reason, details }` |
| Semantische Verification | Zweite Verification-Runde | `verification_plan_semantic` |

### 2.2 Plan-Schritt-Struktur (aus dem Plan-Text)

Jeder Schritt im Plan folgt diesem Format:

```
Step N: [Beschreibung]
- WHAT: [Konkrete Aktion]
- WHY: [Begründung]
- TOOL: [Tool-Name oder "none"]
- DEPENDS_ON: [Step-Nummer oder "none"]
```

### 2.3 Benötigte neue Backend-Events

| Event-Stage | Details | Wann |
|-------------|---------|------|
| `plan_parsed` | `{ classification, steps: [{ index, what, why, tool, depends_on }], fallback_steps }` | Nach Plan-Parsing — strukturierte Daten statt nur Rohtext |

---

## 3. UI-Struktur

### 3.1 Klassifikation-Badge

```
┌─ Request Classification ─────────────────────────┐
│  ■ MODERATE                                       │
│  3 Schritte · 2 Tools · 1 Abhängigkeit            │
└───────────────────────────────────────────────────┘
```

Badge-Farbe:
- `trivial` = grau/dim
- `moderate` = blau
- `complex` = orange

### 3.2 Schritt-Tabelle

```
┌─ Execution Plan ─────────────────────────────────┐
│                                                   │
│  Step  What                  Tool        Dep.     │
│  ─────────────────────────────────────────────── │
│  1     Lese aktuelle Auth    read_file    —       │
│  2     Analysiere Middleware grep_search  1       │
│  3     Schreibe Refactoring  write_file   2       │
│                                                   │
│  Fallback:                                        │
│  3b    write_file statt run_command (Timeout)     │
└───────────────────────────────────────────────────┘
```

### 3.3 Abhängigkeits-Graph (Mini-DAG)

```
  [1: read_file] ──→ [2: grep_search] ──→ [3: write_file]
```

- Horizontaler Mini-Graph mit Pfeilen
- Parallele Schritte (gleiche Dependency-Tiefe) vertikal gestapelt
- Abgeschlossene Schritte = grün, laufend = blau-pulsierend, offen = grau

### 3.4 Verification-Sektion

```
┌─ Plan Verification ──────────────────────────────┐
│  Structural: ✓ Valid (all steps have tools)       │
│  Semantic:   ✓ Valid (steps cover user intent)    │
│                                                   │
│  — oder bei Problemen —                           │
│                                                   │
│  Structural: ⚠ Warning                           │
│  "Step 2 has no tool assigned"                    │
│  Semantic:   ✕ Failed                             │
│  "Plan does not address file writing"             │
└───────────────────────────────────────────────────┘
```

### 3.5 Rohtext-Toggle

- Button "Show raw plan text" → expandiert den LLM-Rohtext
- Default: strukturierte Ansicht (parsed)
- Syntax-highlighted (Markdown)

---

## 4. Dos

- Plan-Text **parsen** und strukturiert anzeigen (nicht nur Rohtext-Dump)
- Abhängigkeits-Graph als einfachen horizontalen Flow (CSS Flexbox, keine Graph-Library)
- Classification-Badge groß und prominent (erste Info die der Nutzer sieht)
- Fallback-Steps klar als solche markieren (gestrichelte Border, Label "Fallback")
- Tool-Namen als farbige Badges (gleiche Farbe wie im Tool Catalog)
- Verification-Ergebnis mit klarem ✓/⚠/✕ Status
- Raw-Text als optionaler Expand — nicht die Default-Ansicht
- WHAT und WHY als separate Spalten/Zeilen (nicht zusammengemischt)

## 5. Don'ts

- **Nicht** nur den Rohtext anzeigen — strukturiertes Parsing ist Pflicht
- **Keine** Third-Party-Graph-Library für den DAG — CSS Flexbox reicht für max. 8 Schritte
- **Nicht** die Verification-Ergebnisse weglassen (auch wenn "Valid") — immer anzeigen
- **Keine** Edit-Möglichkeit für den Plan — read-only
- **Nicht** den System-Prompt der Planning-Phase hier anzeigen (gehört in den LLM-Inspector)
- **Keine** Schritt-Nummerierung die bei 0 anfängt — immer bei 1 (wie im LLM-Output)
- **Nicht** `depends_on: none` als Abhängigkeit darstellen — nur echte Abhängigkeiten visualisieren

---

## 6. Akzeptanzkriterien

### Funktional

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| F-01 | Request-Klassifikation wird als Badge angezeigt (trivial/moderate/complex) | Visuell nach Planning-Event |
| F-02 | Alle Plan-Schritte werden als Tabelle dargestellt | Visuell: Zeile pro Schritt |
| F-03 | Jeder Schritt zeigt: WHAT, WHY, TOOL, DEPENDS_ON | Visuell: 4 Datenpunkte pro Zeile |
| F-04 | Abhängigkeits-Graph zeigt korrekte Verbindungen | Visuell: Pfeile von Abhängigkeiten |
| F-05 | Fallback-Steps sind klar als Fallback gekennzeichnet | Visuell: gestrichelte Border + Label |
| F-06 | Verification-Ergebnis (structural + semantic) wird angezeigt | Visuell nach `verification_plan`/`_semantic` Events |
| F-07 | Rohtext per Toggle erreichbar | Visuell: Button → Expand |
| F-08 | Parallele Schritte (gleiche Dependency-Ebene) werden nebeneinander dargestellt | Visuell im DAG |
| F-09 | Summary-Zeile zeigt Schritt-Anzahl, Tool-Anzahl, Abhängigkeits-Anzahl | Visuell unter Badge |

### Visuell

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| V-01 | DAG horizontal gerendert mit CSS (keine Bibliothek) | Code-Review |
| V-02 | Classification-Badge farblich differenziert | Visuell: 3 verschiedene Farben |
| V-03 | Tool-Namen als farbige Badges | Visuell |
| V-04 | Verification ✓/⚠/✕ mit passenden Farben | Visuell: grün/gelb/rot |

### Backend-Voraussetzungen

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| B-01 | `plan_parsed` Event mit strukturierten Schritt-Daten | Backend-Event oder Frontend-Parsing |
| B-02 | `verification_plan` Event mit `status` und `reason` | Backend-Event prüfen |
| B-03 | `verification_plan_semantic` Event | Backend-Event prüfen |
| B-04 | `debug_prompt_sent` (phase=planning) liefert den System-Prompt | Existing Event prüfen |
| B-05 | `debug_llm_response` (phase=planning) liefert den Roh-Plan-Text | Existing Event prüfen |

### Accessibility

| # | Kriterium | Verifikation |
|---|-----------|-------------|
| A-01 | Plan-Tabelle als `<table>` mit `<thead>`/`<tbody>` | Code-Review |
| A-02 | DAG-Knoten focusbar per Keyboard | Manuell: Tab-Reihenfolge |
| A-03 | Classification-Badge mit `aria-label` | Screen-Reader Test |
| A-04 | Toggle-Button korrekt beschriftet ("Rohtext anzeigen"/"Rohtext verbergen") | ARIA |

---

## 7. Abhängigkeiten

- LLM-Call-Daten aus `DebugSnapshot.llmCalls` (phase=`planning`)
- `verification_plan` und `verification_plan_semantic` Events müssen vom Backend gesendet werden
- **Optional:** `plan_parsed` Backend-Event für strukturierte Daten — **Alternative:**
  Frontend-seitiges Parsing des Plan-Texts (fragiler, aber kein Backend-Change nötig)
- `AgentStateService.applyDebugEvent()` — neue Cases für `verification_plan`,
  `plan_parsed`

## 8. Status

**Existiert nicht.** Komplett neuer View.  Plan-Text ist bereits als LLM-Call
im Inspector sichtbar, aber nicht strukturiert/parsed.  Backend sendet
bereits `verification_plan` Events — müssen nur im Frontend angezeigt werden.
