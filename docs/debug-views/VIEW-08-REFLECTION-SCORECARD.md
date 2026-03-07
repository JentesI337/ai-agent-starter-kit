# VIEW-08 — Reflection Scorecard

> Detaillierte Darstellung der LLM-basierten Qualitätsbewertung mit Scores, Thresholds, Retry-Logik und Verbesserungs-Diff.

---

## 1. Warum brauchen wir diesen View?

Die Reflection-Phase ist die **Qualitätssicherung** der gesamten Pipeline.
Hier entscheidet ein separater LLM-Call, ob die generierte Antwort gut genug
ist oder ob ein Retry erforderlich ist.  Aktuell ist dieser Prozess **komplett
unsichtbar** — der Nutzer sieht nur die finale Antwort, aber nicht:

- Wie hoch die Qualitäts-Scores waren
- Ob ein Retry stattgefunden hat
- Was sich zwischen der ersten und zweiten Synthese geändert hat
- Warum die Reflection übersprungen wurde (triviale Aufgabe? Deaktiviert?)
- Ob ein Hard-Factual-Fail vorlag (factual_grounding < 0.4)

### Konkretes Szenario

User fragt: "Wie funktioniert das Auth-System in diesem Projekt?"

1. Synthesis generiert Antwort → Reflection bewertet:
   - `goal_alignment: 0.82` ✅
   - `completeness: 0.71` ✅
   - `factual_grounding: 0.35` ❌ (Hard-Fail: unter 0.4)
2. Retry wird getriggert mit Feedback: "Factual claims not backed by tool output"
3. Re-Synthesis fügt konkrete Dateiverweise ein → Score steigt auf 0.72
4. **Der Nutzer sieht nur die finale Antwort, aber nicht diesen ganzen Prozess**

---

## 2. Datenquellen

### 2.1 Bestehende Events

| Event | Payload | Details |
|-------|---------|---------|
| `reflection_completed` | `{ score, dimensions: { goal_alignment, completeness, factual_grounding }, threshold, should_retry, issues, suggested_fix, task_type }` | Hauptdatenquelle — enthält alle Bewertungsdetails |
| `reflection_skipped` | `{ reason }` | Warum wurde Reflection übersprungen |
| `reflection_failed` | `{ error }` | Fehler während Reflection |

### 2.2 Benötigte neue Backend-Events

| Event | Payload | Zweck |
|-------|---------|-------|
| `reflection_retry_started` | `{ attempt, feedback_text_chars, issues_count }` | Marker für den Beginn des Retry-Cycles |
| `reflection_retry_completed` | `{ attempt, new_score, new_dimensions, improved }` | Ergebnis des Retry-Cycles |
| `reflection_sanitization_applied` | `{ patterns_neutralized: number, plan_chars_capped: boolean, tool_results_chars_capped: boolean }` | Zeigt an, welche Sanitization-Maßnahmen vor der Reflection angewendet wurden |

### 2.3 Konfigurationswerte (aus `config.py`)

| Setting | Default | Relevanz |
|---------|---------|----------|
| `reflection_enabled` | `True` | Ob Reflection aktiv ist |
| `reflection_threshold` | 0.6 | Default-Threshold (wird per task_type überschrieben) |
| `reflection_factual_grounding_hard_min` | 0.4 | Hard-Fail-Grenze |
| `reflection_tool_results_max_chars` | 8000 | Sanitization-Limit |
| `reflection_plan_max_chars` | 2000 | Sanitization-Limit |

### 2.4 Thresholds nach Task-Type

| Task Type | Threshold | Kontext |
|-----------|-----------|---------|
| `hard_research` | 0.75 | Höchste Anforderung |
| `research` | 0.70 | |
| `implementation` | 0.65 | |
| `orchestration` | 0.60 | |
| `orchestration_failed` | 0.55 | |
| `orchestration_pending` | 0.55 | |
| `trivial` | 0.40 | |
| `general` | 0.35 | Niedrigste — Prose ohne Tool-Grounding |

---

## 3. UI-Struktur

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  REFLECTION SCORECARD                                           │
│  Task Type: implementation        Threshold: 0.65               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───── Overall Score ──────────────────────────────────────┐   │
│  │                                                          │   │
│  │   ████████████████████████░░░░░░  0.72 / 1.0    ✅ PASS  │   │
│  │                            ▲                             │   │
│  │                         Threshold: 0.65                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Dimension Scores ───────────────────────────────────┐   │
│  │                                                          │   │
│  │  Goal Alignment     ██████████████████████░░░  0.82  ✅   │   │
│  │  Completeness       ████████████████░░░░░░░░░  0.71  ✅   │   │
│  │  Factual Grounding  ████████████████████░░░░░  0.63  ✅   │   │
│  │                                                          │   │
│  │  ── Hard-Fail Line: 0.4 ──                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Threshold Context ──────────────────────────────────┐   │
│  │                                                          │   │
│  │  Task Type: implementation → Threshold: 0.65             │   │
│  │                                                          │   │
│  │  ┌─────────────────────────────────────────────────┐     │   │
│  │  │ trivial  general  orch  impl  research  hard_r  │     │   │
│  │  │  0.40     0.35    0.60  0.65▲  0.70     0.75    │     │   │
│  │  └─────────────────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Retry History (wenn vorhanden) ─────────────────────┐   │
│  │                                                          │   │
│  │  Attempt #1:  Score 0.58 → RETRY (factual_grounding=0.35│   │
│  │    Issues: "Claims about auth flow not backed by tool    │   │
│  │             output from read_file"                       │   │
│  │    Fix: "Re-examine auth.py and cite specific lines"     │   │
│  │                                                          │   │
│  │  Attempt #2:  Score 0.72 → PASS ✅                       │   │
│  │    Improvement: +0.14 overall, +0.28 factual_grounding   │   │
│  │                                                          │   │
│  │  [Show Diff: Synthesis #1 vs #2]                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Sanitization Details ───────────────────────────────┐   │
│  │  Plan text: 1 800 / 2 000 chars (uncapped)               │   │
│  │  Tool results: 8 000 / 8 000 chars (capped ⚠)            │   │
│  │  Injection patterns neutralized: 2                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Spezial-Zustände

```
┌─────────────────────────────────────────────────────────────────┐
│  REFLECTION SCORECARD                                           │
│                                                                 │
│  ┌───── Reflection Skipped ─────────────────────────────────┐   │
│  │                                                          │   │
│  │  ⏭ Reflection wurde übersprungen                         │   │
│  │  Grund: Triviale Aufgabe (Begrüßung)                     │   │
│  │                                                          │   │
│  │  Bedingungen für Skip:                                   │   │
│  │  • reflection_enabled = True ✅                           │   │
│  │  • reflection_passes = 0 ← (kein Pass konfiguriert)      │   │
│  │  • final_text.length = 3 chars (< 8 Minimum)            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Komponenten

| Komponente | Beschreibung |
|------------|-------------|
| **Task-Type Badge** | Farbiges Badge mit dem erkannten Task-Type |
| **Overall Score Bar** | Horizontaler Fortschrittsbalken mit Threshold-Marker und Pass/Fail-Icon |
| **Dimension Bars** (×3) | Drei horizontale Balken für goal_alignment, completeness, factual_grounding |
| **Hard-Fail Indicator** | Roter Marker bei factual_grounding < 0.4 |
| **Threshold Ruler** | Horizontale Skala aller 7 Task-Type-Thresholds mit Highlight des aktiven |
| **Retry Timeline** | Vertikale Timeline der Retry-Attempts mit Scores und Issues |
| **Diff Button** | Öffnet Side-by-Side-Diff zwischen Synthesis-Versionen |
| **Sanitization Panel** | Collapsible Panel mit Sanitization-Details |
| **Skip Explanation** | Angezeigt statt Scores, wenn Reflection übersprungen wurde |

---

## 4. Dos

- ✅ **Score-Interpretation visuell machen** — Farben: Grün ≥ Threshold, Gelb < Threshold aber ≥ Hard-Fail, Rot < Hard-Fail
- ✅ **Threshold-Kontext zeigen** — Der Nutzer muss verstehen, WARUM der Threshold bei 0.65 liegt (weil Task-Type = implementation)
- ✅ **Alle Retry-Attempts anzeigen** — Mit Score-Deltas, Issues und Suggested Fixes
- ✅ **Diff anbieten** — Wenn ein Retry stattfand, ist der Diff zwischen den Synthese-Versionen extrem wertvoll
- ✅ **Skip-Grund erklären** — Wenn Reflection übersprungen wurde, die Bedingungen auflisten
- ✅ **Hard-Fail prominent markieren** — factual_grounding < 0.4 ist ein kritischer Fehler, der sofort Retry triggert
- ✅ **Sanitization transparent machen** — Zeigen, ob Plan oder Tool-Results gekürzt wurden (dies kann Scores beeinflussen)
- ✅ **Issues als zitierbare Texte anzeigen** — Die Reflection-Issues sind die wertvollsten Debugging-Infos

## 5. Don'ts

- ❌ **Keine editierbaren Scores** — Scores sind read-only, der Nutzer kann sie nicht überschreiben
- ❌ **Keine Gesamt-Score-Formel offenlegen** — Die gewichtete Kombination ist ein Implementierungsdetail, nur die Einzeldimensionen zeigen
- ❌ **Nicht den vollständigen Reflection-Prompt zeigen** — Das gehört in VIEW-07 LLM Call Inspector
- ❌ **Keine Score-Historie über Runs hinweg** — Nur der aktuelle Run wird bewertet
- ❌ **Keine Benchmark-Vergleiche** — Scores sind kontextabhängig und nicht über verschiedene Requests vergleichbar
- ❌ **Nicht die Injection-Pattern-Details zeigen** — Nur die Anzahl neutralisierter Patterns, nicht die Patterns selbst (Sicherheit)
- ❌ **Keine Dezimalstellen > 2** — Scores auf 2 Dezimalstellen runden (0.72, nicht 0.71843)

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

| # | Kriterium | Prüfung |
|---|-----------|---------|
| F1 | Overall Score als Fortschrittsbalken mit korrektem Wert | Score manuell mit Event-Payload vergleichen |
| F2 | Drei Dimension-Scores korrekt angezeigt (goal_alignment, completeness, factual_grounding) | Werte mit Backend-Event abgleichen |
| F3 | Threshold-Marker auf dem Overall-Balken korrekt positioniert | Position = threshold × Balkenbreite |
| F4 | Pass/Fail-Icon basiert auf: score ≥ threshold UND factual_grounding ≥ 0.4 | Edge Cases testen |
| F5 | Task-Type Badge zeigt korrekten Typ und korrespondierenden Threshold | Verschiedene Task-Types provozieren |
| F6 | Threshold Ruler zeigt alle 7 Thresholds mit korrekter Markierung | Visuell prüfen |
| F7 | Retry Timeline zeigt alle Attempts mit Score-Deltas | Reflection-Retry provozieren |
| F8 | Diff-Button öffnet Vergleich zwischen Synthesis #1 und #2 | Retry provozieren und Diff prüfen |
| F9 | Skip-Zustand zeigt Grund und Bedingungen | Triviale Anfrage senden |
| F10 | Sanitization Panel zeigt korrekte Werte (chars capped, patterns neutralized) | Langen Request mit vielen Tool-Results senden |

### 6.2 Visuell

| # | Kriterium | Prüfung |
|---|-----------|---------|
| V1 | Score-Balken: Grün (≥ threshold), Gelb (< threshold, ≥ 0.4), Rot (< 0.4) | Screenshots bei verschiedenen Scores |
| V2 | Hard-Fail-Linie bei 0.4 ist als gestrichelte rote Linie sichtbar | Visuell prüfen |
| V3 | Retry Timeline hat klare visuelle Progression (Attempt 1 → 2) | Visuell prüfen |
| V4 | Keine UI-Elemente sichtbar, wenn Reflection übersprungen wurde (außer Skip-Erklärung) | Skip-Zustand testen |

### 6.3 Backend-Voraussetzungen

| # | Kriterium | Prüfung |
|---|-----------|---------|
| B1 | `reflection_completed` Event enthält alle 3 Dimension-Scores | WebSocket-Monitor |
| B2 | `reflection_completed` Event enthält `task_type` und `threshold` | WebSocket-Monitor |
| B3 | `reflection_completed` Event enthält `issues` und `suggested_fix` bei should_retry=true | Retry provozieren |
| B4 | `reflection_retry_completed` Event wird nach Re-Synthesis emittiert | WebSocket-Monitor |

### 6.4 Accessibility

| # | Kriterium | Prüfung |
|---|-----------|---------|
| A1 | Score-Balken haben `aria-valuenow`, `aria-valuemin`, `aria-valuemax` | Accessibility Audit |
| A2 | Pass/Fail Status hat `aria-label` (z.B. "Reflection passed with score 0.72") | Screen-Reader-Test |
| A3 | Farbige Indikatoren haben zusätzliche Text/Icon-Unterscheidung (nicht nur Farbe) | Farbenblindheit-Simulation |

---

## 7. Abhängigkeiten

| Abhängigkeit | Typ | Status |
|-------------|-----|--------|
| `reflection_completed` Event | Backend | ✅ Existiert |
| `reflection_skipped` Event | Backend | ✅ Existiert |
| `reflection_retry_started` Event | Backend | ⬜ Neu |
| `reflection_retry_completed` Event | Backend | ⬜ Neu |
| `reflection_sanitization_applied` Event | Backend | ⬜ Neu |
| VIEW-07 LLM Call Inspector | Cross-Link | 📋 Spec exists |
| VIEW-09 Reply Shaping Diff | Diff-Daten teilen | 📋 Spec planned |

---

## 8. Status

| Meilenstein | Status |
|------------|--------|
| Spec fertig | ✅ |
| Backend-Events definiert | ✅ (in diesem Dokument) |
| Backend-Events implementiert | ⬜ |
| Frontend-Komponente | ⬜ Neu zu erstellen |
| Integration & Test | ⬜ |
