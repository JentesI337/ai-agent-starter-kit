# VIEW-11 — Model Routing Panel

> Transparente Darstellung der Model-Auswahl: Scoring-Formel, Capability-Profile, Fallback-Chain und aktuelle Gesundheitswerte.

---

## 1. Warum brauchen wir diesen View?

Der Agent wählt bei jedem Run ein LLM-Modell basierend auf einer
**Scoring-Formel** und **Capability-Profilen**.  Diese Entscheidung ist
aktuell komplett unsichtbar — der Nutzer sieht nur den Namen des gewählten
Modells, aber nicht:

- **Warum** dieses Modell gewählt wurde
- Welche **Alternativen** verfügbar waren und wie sie bewertet wurden
- Ob ein **Fallback** aktiv ist (z.B. weil das bevorzugte Modell offline ist)
- Welche **Capability-Limits** das gewählte Modell hat (max_context, reasoning_depth, reflection_passes)
- Wie sich die **Health-Werte** der Modelle über Zeit verhalten

### Konkretes Szenario

User sendet eine komplexe Research-Anfrage.  Der Agent wählt `llama3.3:70b`
(local) statt `qwen3-coder:480b-cloud`, obwohl letzteres viel bessere
Capabilities hat.  Grund: Das Cloud-Modell hat Latency 2000ms und die
Scoring-Formel gewichtet den `runtime_bonus` des lokalen Modells stark.

**Ohne VIEW-11** fragt sich der Nutzer: "Warum wurde nicht das bessere
Modell genommen?" und hat keine Möglichkeit, die Entscheidung nachzuvollziehen.

---

## 2. Datenquellen

### 2.1 Bestehende Daten

| Datenpunkt | Quelle | Details |
|------------|--------|---------|
| Model-ID | Run-Parameter / `DebugSnapshot` | Welches Modell gewählt wurde |
| Model Registry | `model_routing/model_registry.py` | Capability-Profile aller registrierten Modelle |
| Scoring-Gewichte | `config.py` → `AppSettings` | `model_score_weight_health`, `_latency`, `_cost`, `_runtime_bonus` |

### 2.2 Model-Capability-Profile (aus ModelRegistry)

| Model | max_context | reasoning_depth | reflection_passes | Typ |
|-------|-------------|-----------------|-------------------|-----|
| `llama3.3:70b-instruct-q4_K_M` | 8 000 | 2 | 0 | local |
| `minimax-m2:cloud` | 16 000 | 2 | 0 | api |
| `gpt-oss:20b-cloud` | 24 000 | 3 | 1 | api |
| `qwen3-coder:480b-cloud` | 64 000 | 4 | 2 | api |

### 2.3 Scoring-Formel

```
score = health × weight_health
      − latency / (1 / weight_latency)
      − cost × weight_cost
      + runtime_bonus (if model matches current runtime)
```

**Default-Gewichte:**

| Gewicht | Default | Env Var |
|---------|---------|---------|
| `model_score_weight_health` | 100.0 | `MODEL_SCORE_WEIGHT_HEALTH` |
| `model_score_weight_latency` | 0.01 | `MODEL_SCORE_WEIGHT_LATENCY` |
| `model_score_weight_cost` | 10.0 | `MODEL_SCORE_WEIGHT_COST` |
| `model_score_runtime_bonus` | 6.0 | `MODEL_SCORE_RUNTIME_BONUS` |

### 2.4 Benötigte neue Backend-Events

| Event | Payload | Zweck |
|-------|---------|-------|
| `model_routing_decision` | `{ selected_model, reason, override, scores: [{ model, score, health, latency, cost, runtime_bonus, breakdown }] }` | Vollständige Scoring-Details für alle Kandidaten |
| `model_health_snapshot` | `{ models: [{ model, health, last_check, latency_avg_ms, error_rate }] }` | Gesundheitswerte aller Modelle zum Zeitpunkt der Entscheidung |
| `model_override_applied` | `{ requested_model, original_selection, override_reason }` | Wenn der User ein Modell explizit angefordert hat und das Routing überschrieben wurde |

---

## 3. UI-Struktur

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  MODEL ROUTING PANEL                                            │
│  Selected: llama3.3:70b-instruct-q4_K_M (local)                │
│  Reason: highest_score (no override)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───── Model Comparison ───────────────────────────────────┐   │
│  │                                                          │   │
│  │  Model                     Score   Health  Latency  Cost │   │
│  │  ──────────────────────    ─────   ──────  ───────  ──── │   │
│  │  ★ llama3.3:70b (local)   96.4    0.98    45ms     0.0  │   │
│  │    minimax-m2:cloud       88.2    0.95    320ms    0.02  │   │
│  │    gpt-oss:20b-cloud      72.1    0.80    890ms    0.05  │   │
│  │    qwen3-coder:480b       65.3    0.70    2100ms   0.12  │   │
│  │                                                          │   │
│  │  ★ = Selected model                                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Score Breakdown (Selected) ─────────────────────────┐   │
│  │                                                          │   │
│  │  health × 100.0    = 0.98 × 100.0  = +98.0              │   │
│  │  latency × 0.01    = 45 × 0.01     = −0.45              │   │
│  │  cost × 10.0       = 0.0 × 10.0    = −0.0               │   │
│  │  runtime_bonus      = +6.0 (local runtime active)        │   │
│  │  ──────────────────────────────────                      │   │
│  │  TOTAL              = 103.55        (displayed: 96.4*)   │   │
│  │                                                          │   │
│  │  * Normalisiert auf 0–100 Skala                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Capability Profiles ────────────────────────────────┐   │
│  │                                                          │   │
│  │  ★ llama3.3:70b                                          │   │
│  │  ├─ max_context:      8 000 tokens                       │   │
│  │  ├─ reasoning_depth:  2                                  │   │
│  │  ├─ reflection_passes: 0            ⚠ Keine Reflection   │   │
│  │  └─ type:             local (Ollama)                     │   │
│  │                                                          │   │
│  │  [Show all models ▾]                                     │   │
│  │                                                          │   │
│  │  minimax-m2:cloud                                        │   │
│  │  ├─ max_context:      16 000 tokens                      │   │
│  │  ├─ reasoning_depth:  2                                  │   │
│  │  ├─ reflection_passes: 0                                 │   │
│  │  └─ type:             api                                │   │
│  │                                                          │   │
│  │  ... (collapsed)                                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Override Info (wenn aktiv) ─────────────────────────┐   │
│  │                                                          │   │
│  │  ⚙ Model Override aktiv                                  │   │
│  │  Angefordert: qwen3-coder:480b-cloud                     │   │
│  │  Ursprüngliche Auswahl wäre: llama3.3:70b                │   │
│  │  Override-Quelle: Envelope → model field                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Komponenten

| Komponente | Beschreibung |
|------------|-------------|
| **Selected Model Badge** | Prominente Anzeige des gewählten Modells mit Typ-Icon (local/cloud) |
| **Model Comparison Table** | Sortierbare Tabelle aller Kandidaten mit Score, Health, Latency, Cost |
| **Score Breakdown** | Detaillierte Formel-Auflösung für das gewählte Modell |
| **Capability Profile Cards** | Pro Modell: max_context, reasoning_depth, reflection_passes, type |
| **Override Banner** | Angezeigt wenn ein User-Override aktiv ist |
| **Health Indicators** | Farbige Punkte (Grün ≥ 0.8, Gelb 0.5–0.8, Rot < 0.5) |
| **Latency Bar** | Horizontaler Balken für relative Latenz-Vergleiche |
| **Scoring Weights** | Zeigt die aktiven Gewichte der Scoring-Formel |

---

## 4. Dos

- ✅ **Scoring-Formel transparent machen** — Jeder Faktor einzeln aufschlüsseln, damit der Nutzer die Berechnung nachvollziehen kann
- ✅ **Alle Kandidaten zeigen** — Nicht nur das gewählte Modell, sondern alle mit ihren Scores (Ranking)
- ✅ **Override prominent markieren** — Wenn der Nutzer ein Modell explizit angefordert hat, ist das anders als automatische Auswahl
- ✅ **Capability-Limits warnen** — Wenn das gewählte Modell `reflection_passes=0` hat, eine ⚠-Warnung zeigen
- ✅ **Health farbig kodieren** — Grün/Gelb/Rot für sofortige visuelle Einschätzung
- ✅ **Gewichte anzeigen** — Die Scoring-Gewichte sind konfigurierbar; zeigen welche aktuell aktiv sind
- ✅ **Runtime-Bonus erklären** — Warum bekommt das lokale Modell +6.0 Bonus? Weil es im aktiven Runtime läuft
- ✅ **Sortierbare Tabelle** — Default: nach Score absteigend.  Klickbar nach jeder Spalte sortieren

## 5. Don'ts

- ❌ **Keine Model-Auswahl erlauben** — Dieser View ist read-only.  Model-Auswahl geht über die Chat-Oberfläche (Envelope `model` field)
- ❌ **Keine Scoring-Gewichte editierbar** — Gewichte werden über Environment-Variablen konfiguriert, nicht über die UI
- ❌ **Keine Health-Historie über Runs hinweg** — Nur der Snapshot zum Zeitpunkt der Entscheidung
- ❌ **Keine Model-Benchmarks** — Keine LLM-Leaderboard-Daten.  Nur die internen Scoring-Daten
- ❌ **Nicht die Modell-Parameter zeigen** — Temperatur, Top-P etc. gehören zum LLM Call Inspector (VIEW-07), nicht hierher
- ❌ **Keine "empfohlene Modell"-Anzeige** — Keine eigenmächtige Empfehlung, nur transparente Darstellung der Entscheidung
- ❌ **Keine Latenz-Prognosen** — Nur die tatsächlich gemessene/bekannte Latenz, keine Schätzungen

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

| # | Kriterium | Prüfung |
|---|-----------|---------|
| F1 | Gewähltes Modell wird korrekt mit ★-Markierung angezeigt | Run-Parameter vergleichen |
| F2 | Alle registrierten Modelle erscheinen in der Comparison-Tabelle | ModelRegistry-Einträge zählen |
| F3 | Scores sind korrekt berechnet (Formel manuell nachrechnen) | Score Breakdown mit Formel vergleichen |
| F4 | Score Breakdown zeigt jeden einzelnen Faktor mit Berechnung | Visuell prüfen |
| F5 | Tabelle ist nach jeder Spalte sortierbar | Click-Test auf jede Spaltenüberschrift |
| F6 | Capability Profiles zeigen alle Felder (max_context, reasoning_depth, reflection_passes, type) | Alle Modelle durchklicken |
| F7 | Override-Banner erscheint wenn `model` im Envelope gesetzt ist | Test mit explizitem Model-Override |
| F8 | Health-Indikatoren zeigen korrekte Farbe (Grün/Gelb/Rot) | Edge Cases bei 0.8 und 0.5 testen |
| F9 | Runtime-Bonus wird nur für das Modell vergeben, das im aktiven Runtime läuft | Verschiedene Runtimes testen |
| F10 | Scoring-Gewichte stimmen mit `config.py` / Environment-Variablen überein | Werte vergleichen |

### 6.2 Visuell

| # | Kriterium | Prüfung |
|---|-----------|---------|
| V1 | Gewähltes Modell visuell hervorgehoben (★ + Hintergrund) | Visuell prüfen |
| V2 | Health-Farben klar unterscheidbar (mindestens 3 Stufen) | Farbenblindheit-Simulation |
| V3 | Latency-Werte rechtsbündig formatiert mit Einheit (ms) | Visuell prüfen |
| V4 | Score Breakdown als saubere Rechnung formatiert (ähnlich Kassenbon) | Visuell prüfen |

### 6.3 Backend-Voraussetzungen

| # | Kriterium | Prüfung |
|---|-----------|---------|
| B1 | `model_routing_decision` Event enthält Scores für alle Kandidaten | WebSocket-Monitor |
| B2 | `model_routing_decision` Event enthält Scoring-Breakdown pro Modell | WebSocket-Monitor |
| B3 | `model_health_snapshot` Event enthält Health-Werte | WebSocket-Monitor |
| B4 | `model_override_applied` Event wird bei explizitem Override emittiert | Test mit Envelope-Override |

### 6.4 Accessibility

| # | Kriterium | Prüfung |
|---|-----------|---------|
| A1 | Tabelle hat korrekte `<th>`, `scope`, `aria-sort` Attribute | Accessibility Audit |
| A2 | ★-Markierung hat `aria-label="Selected model"` | Screen-Reader-Test |
| A3 | Health-Farben haben zusätzlichen Text (z.B. "healthy", "degraded", "unhealthy") | Accessibility Audit |
| A4 | Score Breakdown ist als `<dl>` (Definition List) semantisch korrekt | HTML-Validierung |

---

## 7. Abhängigkeiten

| Abhängigkeit | Typ | Status |
|-------------|-----|--------|
| `ModelRegistry` | Backend | ✅ Existiert |
| Config: Scoring-Gewichte | Backend | ✅ Existiert |
| `model_routing_decision` Event | Backend | ⬜ Neu |
| `model_health_snapshot` Event | Backend | ⬜ Neu |
| `model_override_applied` Event | Backend | ⬜ Neu |
| VIEW-07 LLM Call Inspector | Cross-Link (Model pro Call) | 📋 Spec exists |

---

## 8. Status

| Meilenstein | Status |
|------------|--------|
| Spec fertig | ✅ |
| Backend-Events definiert | ✅ (in diesem Dokument) |
| Backend-Events implementiert | ⬜ |
| Frontend-Komponente | ⬜ Neu zu erstellen |
| Integration & Test | ⬜ |
