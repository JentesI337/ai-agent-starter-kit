# VIEW-12 — Config & Budget Dashboard

> Gesamtübersicht aller aktiven Konfigurationseinstellungen, Laufzeit-Budgets und Override-Highlights für den aktuellen Run.

---

## 1. Warum brauchen wir diesen View?

Der Agent hat **50+ konfigurierbare Einstellungen** (über `config.py` und
Environment-Variablen), die das Verhalten jeder Pipeline-Phase beeinflussen.
Aktuell muss man die `.env`-Datei oder den Server-Log lesen, um zu verstehen,
mit welchen Einstellungen der Agent arbeitet.

Zusätzlich gibt es **drei Budgets**, die zur Laufzeit verbraucht werden:

1. **LLM-Call-Budget** — max 8 Calls pro Run (typisch 3–8)
2. **Tool-Call-Budget** — max 8 Tool-Calls pro Run (`RUN_TOOL_CALL_CAP`)
3. **Zeit-Budget** — max 90s pro Tool-Ausführung (`RUN_TOOL_TIME_CAP_SECONDS`)

**Ohne diesen View** ist es unmöglich zu erkennen, ob ein Setting vom Default
abweicht (Override), und wie weit die Budgets bereits verbraucht sind.

### Konkretes Szenario

Ein Nutzer hat `REFLECTION_ENABLED=False` in seiner `.env` gesetzt und
wundert sich, warum die Antwortqualität schlecht ist.  Im Config Dashboard
sieht er sofort:

```
Reflection:  reflection_enabled = False  ⚠ OVERRIDE (Default: True)
```

Oder: Der Agent hat 7 von 8 Tool-Calls verbraucht und der 8. Call steht an.
Das Budget-Panel zeigt:

```
Tool-Call-Budget:  ███████░  7/8  (87.5%)  ⚠ FAST ERSCHÖPFT
```

---

## 2. Datenquellen

### 2.1 Konfigurationsgruppen (aus `config.py`)

**Core (3 Settings):**

| Setting | Default | Env Var | Auswirkung |
|---------|---------|---------|-----------|
| `local_model` | `llama3.3:70b-instruct-q4_K_M` | `LOCAL_MODEL` | Primäres lokales Modell |
| `api_model` | `minimax-m2:cloud` | `API_MODEL` | API-Fallback-Modell |
| `max_user_message_length` | 8 000 | `MAX_USER_MESSAGE_LENGTH` | Guardrail: Maximale Nachrichtenlänge |

**Reflection (5 Settings):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `reflection_enabled` | `True` | `REFLECTION_ENABLED` |
| `reflection_threshold` | 0.6 | `REFLECTION_THRESHOLD` |
| `reflection_factual_grounding_hard_min` | 0.4 | `REFLECTION_FACTUAL_GROUNDING_HARD_MIN` |
| `reflection_tool_results_max_chars` | 8 000 | `REFLECTION_TOOL_RESULTS_MAX_CHARS` |
| `reflection_plan_max_chars` | 2 000 | `REFLECTION_PLAN_MAX_CHARS` |

**Tool Execution (5 Settings):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `run_tool_call_cap` | 8 | `RUN_TOOL_CALL_CAP` |
| `run_tool_time_cap_seconds` | 90.0 | `RUN_TOOL_TIME_CAP_SECONDS` |
| `tool_result_max_chars` | 6 000 | `TOOL_RESULT_MAX_CHARS` |
| `tool_result_smart_truncate_enabled` | `True` | `TOOL_RESULT_SMART_TRUNCATE_ENABLED` |
| `tool_result_context_guard_enabled` | `True` | `TOOL_RESULT_CONTEXT_GUARD_ENABLED` |

**Replanning (3 Settings):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `run_max_replan_iterations` | 1 | `RUN_MAX_REPLAN_ITERATIONS` |
| `run_empty_tool_replan_max_attempts` | 1 | `RUN_EMPTY_TOOL_REPLAN_MAX_ATTEMPTS` |
| `run_error_tool_replan_max_attempts` | 1 | `RUN_ERROR_TOOL_REPLAN_MAX_ATTEMPTS` |

**Loop Detection (7 Settings):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `tool_loop_warn_threshold` | 2 | `TOOL_LOOP_WARN_THRESHOLD` |
| `tool_loop_critical_threshold` | 3 | `TOOL_LOOP_CRITICAL_THRESHOLD` |
| `tool_loop_circuit_breaker_threshold` | 6 | `TOOL_LOOP_CIRCUIT_BREAKER_THRESHOLD` |
| `tool_loop_detector_generic_repeat_enabled` | `True` | `TOOL_LOOP_DETECTOR_GENERIC_REPEAT_ENABLED` |
| `tool_loop_detector_ping_pong_enabled` | `True` | `TOOL_LOOP_DETECTOR_PING_PONG_ENABLED` |
| `tool_loop_detector_poll_no_progress_enabled` | `True` | `TOOL_LOOP_DETECTOR_POLL_NO_PROGRESS_ENABLED` |
| `tool_loop_poll_no_progress_threshold` | 3 | `TOOL_LOOP_POLL_NO_PROGRESS_THRESHOLD` |

**Command Safety (3 Settings):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `command_allowlist_enabled` | `True` | `COMMAND_ALLOWLIST_ENABLED` |
| `command_allowlist` | 37 Einträge | `COMMAND_ALLOWLIST` |
| `command_allowlist_extra` | `[]` | `COMMAND_ALLOWLIST_EXTRA` |

**Model Scoring (4 Settings):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `model_score_weight_health` | 100.0 | `MODEL_SCORE_WEIGHT_HEALTH` |
| `model_score_weight_latency` | 0.01 | `MODEL_SCORE_WEIGHT_LATENCY` |
| `model_score_weight_cost` | 10.0 | `MODEL_SCORE_WEIGHT_COST` |
| `model_score_runtime_bonus` | 6.0 | `MODEL_SCORE_RUNTIME_BONUS` |

**Distillation (1 Setting):**

| Setting | Default | Env Var |
|---------|---------|---------|
| `session_distillation_enabled` | `True` | `SESSION_DISTILLATION_ENABLED` |

### 2.2 Benötigte neue Backend-Events

| Event | Payload | Zweck |
|-------|---------|-------|
| `config_snapshot` | `{ settings: [{ key, value, default_value, env_var, is_overridden, group }] }` | Vollständiger Konfigurationsabzug bei Run-Start (nur wenn `debug_mode=True`) |
| `budget_update` | `{ budgets: { llm_calls: { used, cap }, tool_calls: { used, cap }, time_seconds: { elapsed, cap } } }` | Budget-Update bei jedem Verbrauch |
| `budget_warning` | `{ budget_type, used, cap, percent }` | Warnung bei ≥ 75% Budget-Verbrauch |
| `budget_exceeded` | `{ budget_type, used, cap }` | Budget erschöpft |

---

## 3. UI-Struktur

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  CONFIG & BUDGET DASHBOARD                                      │
│  31 settings  |  3 overrides  |  Run: abc-1234                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───── Budgets (Live) ─────────────────────────────────────┐   │
│  │                                                          │   │
│  │  LLM Calls     ████████████░░░░  5/8    (62.5%)          │   │
│  │  Tool Calls    ███████████████░  7/8    (87.5%)  ⚠       │   │
│  │  Time Budget   ██████░░░░░░░░░░  34/90s (37.8%)          │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌───── Configuration ──────────────────────────────────────┐   │
│  │                                                          │   │
│  │  Filter: [All ▾]  [Show Overrides Only ☐]               │   │
│  │                                                          │   │
│  │  ── Core ──────────────────────────────────────────────  │   │
│  │  local_model             llama3.3:70b-instr...   default │   │
│  │  api_model               minimax-m2:cloud        default │   │
│  │  max_user_message_length 8000                    default │   │
│  │                                                          │   │
│  │  ── Reflection ────────────────────────────────────────  │   │
│  │  reflection_enabled      False    ⚠ OVERRIDE  (def: True│   │
│  │  reflection_threshold    0.6                     default │   │
│  │  reflection_factual_...  0.4                     default │   │
│  │  reflection_tool_res...  8000                    default │   │
│  │  reflection_plan_max...  2000                    default │   │
│  │                                                          │   │
│  │  ── Tool Execution ────────────────────────────────────  │   │
│  │  run_tool_call_cap       12       ⚠ OVERRIDE  (def: 8)  │   │
│  │  run_tool_time_cap_s     90.0                    default │   │
│  │  tool_result_max_chars   6000                    default │   │
│  │  tool_result_smart_tr... True                    default │   │
│  │  tool_result_context_... True                    default │   │
│  │                                                          │   │
│  │  ── Replanning ────────────────────────────────────────  │   │
│  │  run_max_replan_iter...  1                       default │   │
│  │  run_empty_tool_repl...  1                       default │   │
│  │  run_error_tool_repl...  1                       default │   │
│  │                                                          │   │
│  │  ── Loop Detection ────────────────────────────────────  │   │
│  │  tool_loop_warn_thre...  2                       default │   │
│  │  tool_loop_critical_...  3                       default │   │
│  │  tool_loop_circuit_b...  6                       default │   │
│  │  ...detector_enabled     True (×3)               default │   │
│  │                                                          │   │
│  │  ── Command Safety ────────────────────────────────────  │   │
│  │  command_allowlist_en... True                    default │   │
│  │  command_allowlist       37 entries  [details ▾]         │   │
│  │  command_allowlist_extra  ["deno"]  ⚠ OVERRIDE  (def: [])│   │
│  │                                                          │   │
│  │  ── Model Scoring ─────────────────────────────────────  │   │
│  │  model_score_weight_...  100.0                   default │   │
│  │  model_score_weight_...  0.01                    default │   │
│  │  model_score_weight_...  10.0                    default │   │
│  │  model_score_runtime_... 6.0                     default │   │
│  │                                                          │   │
│  │  ── Distillation ──────────────────────────────────────  │   │
│  │  session_distill_en...   True                    default │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Komponenten

| Komponente | Beschreibung |
|------------|-------------|
| **Budget Bars** (×3) | Horizontale Fortschrittsbalken für LLM-Calls, Tool-Calls, Zeit |
| **Budget Warning Icon** | ⚠ bei ≥ 75%, ⛔ bei 100% |
| **Config Table** | Gruppierte Tabelle aller Settings mit Spalten: Name, Value, Override-Status |
| **Group Headers** | Collapsible Gruppen-Header (Core, Reflection, Tool Execution, ...) |
| **Override Badge** | Oranges "OVERRIDE" Badge + Default-Wert in Klammern für abweichende Settings |
| **Filter Dropdown** | Filter nach Gruppe (Core, Reflection, ...) |
| **Override-Only Toggle** | Checkbox zum Anzeigen nur der überschriebenen Settings |
| **Allowlist Expander** | Click auf "37 entries" expandiert die vollständige Allowlist |
| **Env Var Tooltip** | Hover über Setting-Name zeigt den korrespondierenden Env-Var-Namen |

### 3.3 Interaktionen

| Aktion | Verhalten |
|--------|-----------|
| Gruppen-Header klicken | Collapsiert/expandiert die Gruppe |
| Override-Only Toggle | Zeigt nur Settings mit Override (filtert Default-Settings heraus) |
| Filter-Dropdown | Zeigt nur Settings der gewählten Gruppe |
| Hover über Setting-Name | Tooltip mit Env-Var-Name und Beschreibung |
| Click auf Allowlist "details" | Expandiert die 37+ Einträge als scrollbare Liste |
| Budget-Bar Animation | Live-Update bei Budget-Changes (CSS-Transition) |

---

## 4. Dos

- ✅ **Overrides maximal prominent machen** — Der wichtigste Zweck: sofort sehen, was vom Default abweicht
- ✅ **Default-Wert bei Override anzeigen** — "False ⚠ OVERRIDE (Default: True)" damit der Nutzer den Unterschied sofort erkennt
- ✅ **Budgets als Live-Balken** — Aktualisieren sich bei jedem neuen Event (LLM-Call, Tool-Call)
- ✅ **Budget-Warnungen bei ≥ 75%** — Orange Warnung, bevor das Budget erschöpft ist
- ✅ **Gruppierung nach Thema** — Settings logisch gruppieren, nicht alphabetisch
- ✅ **Env-Var-Name im Tooltip** — Der Nutzer muss wissen, welche Env-Variable er setzen muss, um das Setting zu ändern
- ✅ **Override-Count im Summary** — "31 settings | 3 overrides" gibt sofortige Übersicht
- ✅ **Collapsible Gruppen** — Default: Gruppen mit Overrides expandiert, andere kollabiert
- ✅ **Allowlist als eigene Expansion** — 37 Einträge nicht inline in der Tabelle, sondern expandierbar

## 5. Don'ts

- ❌ **Keine Editierbarkeit** — Settings sind read-only im Dashboard.  Änderungen nur über `.env` oder Env-Variablen
- ❌ **Nicht alle Settings als Flat-Liste** — Ohne Gruppierung sind 50+ Settings unübersichtlich
- ❌ **Keine Empfehlungen aussprechen** — Nicht "Sie sollten reflection_enabled auf True setzen".  Nur transparent zeigen
- ❌ **Keine Secrets anzeigen** — Wenn Settings API-Keys enthalten: Maskieren (`sk-****1234`)
- ❌ **Keine Budget-Prognosen** — Nicht "Bei aktuellem Verbrauch reichen die Calls noch für ~2 Steps".  Nur Ist-Zustand
- ❌ **Kein Reset-Button** — Settings können nicht zur Laufzeit zurückgesetzt werden
- ❌ **Keine Config-Diff über Runs hinweg** — Nur die Konfiguration des aktuellen Runs
- ❌ **Boolean-Settings nicht als 0/1** — Immer als "True"/"False" anzeigen, nicht als Zahlen

---

## 6. Akzeptanzkriterien

### 6.1 Funktional

| # | Kriterium | Prüfung |
|---|-----------|---------|
| F1 | Alle Settings aus `config.py` werden angezeigt (≥ 31 Settings) | Anzahl in Summary Bar prüfen |
| F2 | Override-Badge erscheint bei jedem Setting, das vom Default abweicht | Env-Variable setzen → Override prüfen |
| F3 | Override zeigt Default-Wert in Klammern | "False ⚠ OVERRIDE (Default: True)" |
| F4 | Gruppen sind korrekt zugeordnet (8 Gruppen) | Jede Gruppe prüfen |
| F5 | Override-Only Toggle filtert korrekt | Toggle aktivieren → nur Overrides sichtbar |
| F6 | Gruppen-Header sind collapsible | Click-Test |
| F7 | LLM-Call-Budget zeigt korrekten Verbrauch | Mit LLM-Call-Count aus anderen Views vergleichen |
| F8 | Tool-Call-Budget zeigt korrekten Verbrauch | Mit Tool-Count aus VIEW-06 vergleichen |
| F9 | Budget-Warning erscheint bei ≥ 75% | 6 von 8 Tool-Calls provozieren |
| F10 | Allowlist-Expansion zeigt alle 37+ Einträge | Click auf "details" |
| F11 | Env-Var-Tooltip zeigt korrekten Variablennamen | Hover über jedes Setting |
| F12 | Budget-Bars updaten live bei neuen Events | Run mit mehreren Tool-Calls beobachten |

### 6.2 Visuell

| # | Kriterium | Prüfung |
|---|-----------|---------|
| V1 | Override-Badge visuell prominent (orange/gelb) | Visuell prüfen |
| V2 | Budget-Bars: Grün < 50%, Gelb 50–74%, Orange 75–99%, Rot = 100% | Screenshots bei verschiedenen Ständen |
| V3 | Settings mit Default-Wert visuell gedämpft vs. Override | Visuell prüfen |
| V4 | Gruppen-Header klar als Trenner erkennbar | Visuell prüfen |
| V5 | Budget-Bar-Transition flüssig (CSS-Animation) | Live beobachten |

### 6.3 Backend-Voraussetzungen

| # | Kriterium | Prüfung |
|---|-----------|---------|
| B1 | `config_snapshot` Event bei Run-Start mit allen Settings + Defaults + Override-Status | WebSocket-Monitor |
| B2 | `budget_update` Event bei jeder Budget-Änderung | WebSocket-Monitor |
| B3 | `budget_warning` Event bei ≥ 75% | WebSocket-Monitor |
| B4 | `budget_exceeded` Event bei 100% | Budget erschöpfen und prüfen |
| B5 | Keine API-Keys / Secrets in `config_snapshot` Payload | Payload-Review |

### 6.4 Accessibility

| # | Kriterium | Prüfung |
|---|-----------|---------|
| A1 | Budget-Bars haben `role="progressbar"` mit `aria-valuenow`, `aria-valuemin`, `aria-valuemax` | Accessibility Audit |
| A2 | Override-Badge hat `aria-label` (z.B. "Overridden setting, default value: True") | Screen-Reader-Test |
| A3 | Gruppen-Header haben `aria-expanded` State | Accessibility Audit |
| A4 | Tabelle hat korrekte `<th>` und `scope` Attribute | HTML-Validierung |
| A5 | Tooltip-Inhalte auch per Tastatur erreichbar (nicht nur Hover) | Keyboard-Test |

---

## 7. Abhängigkeiten

| Abhängigkeit | Typ | Status |
|-------------|-----|--------|
| `config.py` → `AppSettings` | Backend | ✅ Existiert |
| `config_snapshot` Event | Backend | ⬜ Neu |
| `budget_update` Event | Backend | ⬜ Neu |
| `budget_warning` Event | Backend | ⬜ Neu |
| `budget_exceeded` Event | Backend | ⬜ Neu |
| VIEW-06 Tool Execution Monitor | Cross-Link (Tool-Budget) | 📋 Spec exists |
| VIEW-07 LLM Call Inspector | Cross-Link (LLM-Budget) | 📋 Spec exists |

---

## 8. Status

| Meilenstein | Status |
|------------|--------|
| Spec fertig | ✅ |
| Backend-Events definiert | ✅ (in diesem Dokument) |
| Backend-Events implementiert | ⬜ |
| Frontend-Komponente | ⬜ Neu zu erstellen |
| Integration & Test | ⬜ |
