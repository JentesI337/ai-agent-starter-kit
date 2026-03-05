# Reasoning Pipeline — Deep Quality Assessment

**Datum:** 2026-03-05  
**Scope:** Vollständige Codebasis des Reasoning-Pipelines  
**Basis:** Live-Analyse aller zentralen Service-Dateien sowie Abgleich mit vorherigem Audit (2026-03-04)

---

## 1. Pipeline-Überblick

Die Pipeline folgt einem 4-Phasen-Modell:

```
User Message
    │
    ▼
[1] Intent/Guard Layer
    IntentDetector · AmbiguityDetector · GuardrailCheck
    │
    ▼
[2] Plan Step
    PlannerAgent (LLM) → PlanText
    │
    ▼
[3] Tool Selection + Execution Loop
    ToolSelectorAgent (LLM) → ActionParser → ActionAugmenter
    → ToolArgValidator → PolicyApprovalService → ToolExecutionManager
    → ToolCallGatekeeper (circuit breaker)
    │  ↑ (max iterations, replan-on-empty)
    ▼
[4] Synthesis + Verification
    SynthesizerAgent (LLM) → VerificationService → ReflectionService
    → ReplyShaper → Response
    │
    ▼
[5] Fallback / Recovery (parallel)
    PipelineRunner → FallbackStateMachine → ModelHealthTracker
```

---

## 2. Fixierte Bugs (Audit 2026-03-04) — Verifikation

Der folgende Abschnitt dokumentiert den aktuellen Fix-Status der 14 Bugs aus dem Voraudit.

| # | Beschreibung | Status | Nachweis |
|---|---|---|---|
| 1 | Race Condition in `create()` Idempotenz | ✅ BEHOBEN | Scan + Insert jetzt in einem einzigen `async with self._lock` Block |
| 2 | `allow_session` genehmigt alle Tools | ✅ BEHOBEN | Key jetzt `session_id::tool_name`, kein blanket Set mehr |
| 3 | `clear_session_overrides` bereinigt nicht `_allow_always_rules` | ⚠️ TEILWEISE | Siehe Abschnitt 3.1 |
| 4 | `wait_for_decision` ignoriert `cancelled`/`expired` | ✅ BEHOBEN | Early-return prüft jetzt `{"approved","denied","cancelled"}` |
| 5 | Circuit Breaker unbounded counter | ✅ BEHOBEN | `repeat_signature_hits` wird per `sum()` über Window neu berechnet |
| 6 | `is_shell_command` False-Positive bei `/` und `\` | ✅ BEHOBEN | Check entfernt; jetzt: Shell-Operator-Zeichen + first-token lookup |
| 7 | Preamble-Text vor erstem Tool-Block verloren | ✅ BEHOBEN | Explizite Präambel-Erhaltung vor `matches[0].start()` |
| 8 | `_TOOL_BLOCK_PATTERN` benötigt Trailing Newline | ✅ BEHOBEN | Regex jetzt `\n?` (optional) |
| 9 | `verify_tool_result` naive Substring-Erkennung | ⚠️ TEILWEISE | Siehe Abschnitt 3.2 |
| 10 | `parse()` lehnt valides JSON mit Extra-Feldern ab | ✅ BEHOBEN | Nur noch `parsed.get("actions", [])` statt Strict-Key-Check |
| 11 | `is_web_research_task` Substring False-Positives | ✅ BEHOBEN | Word-Boundary-Regex (`\b...\b`) |
| 12 | `looks_like_coding_request` Substring False-Positives | ✅ BEHOBEN | Word-Boundary-Regex für ambige Keywords |
| 13 | `_extract_json_payload` greedy Regex | ✅ BEHOBEN | Non-greedy `\{[\s\S]*?\}` |
| 14 | `_normalize_scope` silent promotion zu global | ✅ BEHOBEN | `_validate_scope()` wirft `ValueError` bei ungültigem Scope |

**Fix-Quote: 12/14 vollständig, 2/14 teilweise behoben**

---

## 3. Offene / Teilweise behobene Bugs

### 3.1 Bug 3 (HIGH) — `clear_session_overrides` bereinigt `_allow_always_rules` nicht

**Datei:** `backend/app/services/policy_approval_service.py`  
**Status:** ⚠️ OFFEN (Session-Allow-All korrekt fixiert, Disk-backed Rules nicht)

Der Fix für Bug 2 hat `_session_allow_all` korrekt auf Tool-granulare Keys umgestellt. `clear_session_overrides()` entfernt diese Keys jetzt korrekt. **Aber:** Wenn ein Nutzer während einer Session `allow_always` mit scope `session_tool` oder `session_tool_resource` wählt, werden diese Regeln in `_allow_always_rules` eingetragen (und auf Disk persistiert). `clear_session_overrides()` bereinigt nur `_session_allow_all`, nicht `_allow_always_rules`.

```python
# AKTUELL — nur _session_allow_all wird bereinigt:
async def clear_session_overrides(self, session_id: str | None) -> None:
    ...
    async with self._lock:
        keys_to_remove = {key for key in self._session_allow_all if key.startswith(prefix)}
        self._session_allow_all -= keys_to_remove
        # FEHLT: _allow_always_rules mit session_id-gebundenem scope entfernen
```

**Fix:**
```python
async def clear_session_overrides(self, session_id: str | None) -> None:
    normalized_session_id = (session_id or "").strip()
    if not normalized_session_id:
        return
    prefix = f"{normalized_session_id}::"
    async with self._lock:
        keys_to_remove = {key for key in self._session_allow_all if key.startswith(prefix)}
        self._session_allow_all -= keys_to_remove
        # Auch session-scoped allow_always rules entfernen und neu persistieren:
        before = len(self._allow_always_rules)
        self._allow_always_rules = [
            rule for rule in self._allow_always_rules
            if not (
                rule.get("scope") in {"session_tool", "session_tool_resource"}
                and rule.get("session_id") == normalized_session_id
            )
        ]
        if len(self._allow_always_rules) != before:
            self._persist_allow_always_rules()
```

---

### 3.2 Bug 9 (MEDIUM) — `verify_tool_result` bleibt fehleranfällig

**Datei:** `backend/app/services/verification_service.py`  
**Status:** ⚠️ VERBESSERT, aber nicht robust

Der Fix hat `" error"` zu `"] error"` und `" ok"` zu `"] ok"` geändert — das reduziert Falsch-Positive deutlich. Aber:

- **Falsch-Negativ-Risiko:** Tool-Ergebnisse, die Fehler ohne das `[tool_name]`-Format melden (z. B. reine Textzeilen ohne Header), werden weiterhin nicht erkannt.
- **Falsch-Positiv-Risiko:** `"error handling is ok"` enthält sowohl `"] error"` als Teil eines JSON-Dumps als auch `"] ok"` und kann die Warnung noch unterdrücken.

**Empfehlung:** Auf strukturierten Status-Header-Parsing ausweichen (`[toolname]\nstatus: error`) statt Substringsuche, oder die Prüfung ganz in die aufrufende Schicht verlagern.

---

### 3.3 CB-1 (CRITICAL) — Leere Action-Liste `{"actions":[]}` — Fix ist fragil

**Datei:** `backend/app/agent.py`, `_extract_actions()` (Zeile 2322)  
**Status:** ⚠️ TEILWEISE BEHOBEN

Der Fix versucht zu erkennen, ob das LLM exakt `{"actions":[]}` zurückgegeben hat:

```python
def _extract_actions(self, raw: str) -> tuple[list[dict], str | None]:
    actions, parse_error = self._action_parser.parse(raw)
    if parse_error is None and not actions and str(raw or "").strip():
        candidate = self._extract_json_candidate(raw)
        if candidate:
            try:
                parsed_candidate = json.loads(candidate)
                if isinstance(parsed_candidate, dict) and parsed_candidate.get("actions") == []:
                    return actions, None
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        parse_error = "invalid_tool_json"
    return actions, parse_error
```

**Problem:** Wenn `_action_parser.parse()` bereits `([], None)` zurückgibt (kein Error, leere Liste), ist der Fix-Pfad korrekt. Aber die Bedingung `if parse_error is None and not actions` greift auch, wenn der Parser zwar keine Aktionen, aber auch keinen Fehler zurückgibt (z. B. valides `{"actions":[], "reasoning":"..."}`). In diesem Fall wird der aufwändige JSON-Reparse-Pfad nochmals durchlaufen, obwohl `parse()` schon erfolgreich war.

**Robusterer Fix:**
```python
def _extract_actions(self, raw: str) -> tuple[list[dict], str | None]:
    actions, parse_error = self._action_parser.parse(raw)
    # parse_error=None + leere Liste = gültiges "keine Aktion"-Signal, niemals als Fehler werten
    if parse_error is None:
        return actions, None
    # Echter Parse-Fehler: Repair-Pfad
    return actions, parse_error
```

---

### 3.4 CB-2 (HIGH) — Stale Failure-Retriever beim Deaktivieren von LTM

**Datei:** `backend/app/agent.py`, `_refresh_long_term_memory_store()` (Zeile 376)  
**Status:** ❌ NICHT BEHOBEN

In den beiden frühen `return`-Pfaden wird `self._failure_retriever = None` gesetzt, aber `planner_agent._failure_retriever` **nicht** zurückgesetzt:

```python
def _refresh_long_term_memory_store(self) -> None:
    if not bool(settings.long_term_memory_enabled):
        self._failure_retriever = None
        return    # ← planner_agent._failure_retriever zeigt noch auf alten Store

    configured_path = ...
    if not configured_path:
        self._failure_retriever = None
        return    # ← selbes Problem
```

Nur der Exception-Catch-Pfad setzt `planner_agent._failure_retriever = None` korrekt.

**Fix:**
```python
def _refresh_long_term_memory_store(self) -> None:
    def _clear_all() -> None:
        self._long_term_memory = None
        self._long_term_memory_db_path = None
        self._reflection_feedback_store = None
        self._failure_retriever = None
        if hasattr(self, "planner_agent"):
            self.planner_agent._failure_retriever = None

    if not bool(settings.long_term_memory_enabled):
        _clear_all()
        return

    configured_path = str(getattr(settings, "long_term_memory_db_path", "") or "").strip()
    if not configured_path:
        _clear_all()
        return
    # ... Rest unverändert
```

---

### 3.5 CB-3 (HIGH) — Calibration-Empfehlung bei identischem `current == recommended`

**Datei:** `backend/app/services/benchmark_calibration.py`, `_recommend_from_recovery_metrics()`  
**Status:** ⚠️ TEILWEISE BEHOBEN

Wenn `best_strategy` kein `"fallback_retry"` enthält, bleiben `current = 1.0` und `recommended = 1.0`. Es wird aber trotzdem ein `CalibrationRecommendation`-Objekt erzeugt und zurückgegeben — mit `current_value == recommended_value`, was eine irreführende Empfehlung darstellt.

```python
# Aktuelle Logik — Empfehlung wird auch bei current==recommended erzeugt:
current = 1.0
recommended = 1.0
if "fallback_retry" in best_strategy:
    current = float(settings.model_score_runtime_bonus)
    recommended = min(20.0, current + 1.0)

return [CalibrationRecommendation(...)]  # ← immer, egal ob delta vorhanden
```

**Fix:**
```python
if "fallback_retry" not in best_strategy:
    return []  # kein qualifizierter Hit → keine Empfehlung
current = float(settings.model_score_runtime_bonus)
recommended = min(20.0, current + 1.0)
if abs(current - recommended) < 1e-6:
    return []  # kein Delta
return [CalibrationRecommendation(...)]
```

---

## 4. Neu gefundene Bugs

### 4.1 N-1 (HIGH) — `configure_runtime()` Concurrency-Guard ist nicht funktionsfähig

**Datei:** `backend/app/agent.py`, Zeilen 208–209 und 348–368  
**Severity:** HIGH

`_configure_lock` wird erstellt und mit dem Kommentar `# H-6: guards configure_runtime vs concurrent run()` versehen. Weder `run()` prüft jedoch `_reconfiguring` vor der Ausführung, noch wird `_configure_lock` irgendwo `await`-ed. Die Implementierung des Guards ist eine Stub ohne Wirkung.

**Konsequenz:** Ein `configure_runtime()`-Aufruf mit einem neuen LLM-Endpunkt während eines laufenden `run()` ersetzt den Client atomisch auf Objekt-Ebene (Python-Zuweisung), kann aber mid-flight eine laufende Synthese mit dem alten `client` stören, sofern der Synthesizer einen Referenz-Cache hält.

**Fix-Skizze:**
```python
async def run(self, ...):
    async with self._configure_lock:
        if self._reconfiguring:
            raise RuntimeError("Agent wird gerade rekonfiguriert.")
    ...

def configure_runtime(self, base_url: str, model: str) -> None:
    # Für synchrone Methode: Sicherstellen, dass kein laufender run() existiert.
    # Alternativ: configure_runtime als async machen und Lock acquiren.
```

---

### 4.2 N-2 (MEDIUM) — `_refresh_long_term_memory_store()` bei jedem `run()`-Aufruf

**Datei:** `backend/app/agent.py`, Zeile 456  
**Severity:** MEDIUM (Performance)

`run()` beginnt mit `self._refresh_long_term_memory_store()`. Diese Methode liest `settings`, vergleicht den DB-Pfad und kehrt früh zurück, wenn keine Änderung vorliegt. Bei hohem Durchsatz (viele parallele Sessions) führt das zu redundanten Settings-Lookups und Pfad-Vergleichen bei jedem Request — auch wenn LTM seit dem Start nie geändert wurde.

**Empfehlung:** Einen statischen `bool`-Flag `_ltm_configured` einführen, der erst bei einer settings-Änderung oder explizitem `reconfigure()`-Aufruf invalidiert wird.

---

### 4.3 N-3 (MEDIUM) — LLM-Retry nutzt lineares Backoff, kein exponentielles

**Datei:** `backend/app/llm_client.py`, Zeilen 14–16 und ~117  
**Severity:** MEDIUM

```python
RETRY_DELAY_SECONDS = 0.8
# Wird verwendet als:
await asyncio.sleep(RETRY_DELAY_SECONDS * attempt)  # linear: 0.8s, 1.6s, 2.4s
```

Bei Rate-Limit-Antworten (HTTP 429) schlägt exponentielles Backoff mit Jitter deutlich besser an als lineares. Mit dem aktuellen Schema können bei 3 parallelen Sessions 9 Retry-Requests direkt hintereinander ausgelöst werden.

**Empfehlung:**
```python
import random
delay = min(RETRY_DELAY_SECONDS * (2 ** (attempt - 1)), 30.0)
delay += random.uniform(0, delay * 0.2)  # 20% Jitter
await asyncio.sleep(delay)
```

---

### 4.4 N-4 (LOW) — `ModelHealthTracker.all_snapshots()` Exception silent swallowed

**Datei:** `backend/app/services/benchmark_calibration.py`, Zeile ~75  
**Severity:** LOW

```python
try:
    snapshots = list(tracker.all_snapshots())
except Exception:
    snapshots = []
```

Ein echter Fehler im Health-Tracker (z. B. korrupte Daten, geschlossene DB) wird stumm ignoriert. Das Calibration-Ergebnis liefert dann `[]` ohne irgendeine Warnung. Da Kalibrierung ohne Daten auch keine Empfehlungen erzeugt, ist dies low-severity, aber schwer debuggbar.

**Empfehlung:** Exception minimal loggen: `logger.debug("health_tracker.all_snapshots failed", exc_info=True)`.

---

## 5. Gesamtbewertung der Pipeline-Qualität

### 5.1 Stärken

| Bereich | Bewertung | Begründung |
|---|---|---|
| **Fallback/Recovery** | ★★★★★ | `FallbackStateMachine` mit konfigurierbaren Strategien, Backoff, Signal-Priorität, persistierter Strategie-Feedback-Schleife — sehr reif |
| **Model Routing** | ★★★★☆ | `ModelRouter` mit Health-Gewichtung, Adaptive Inference Budget, Context-Window-Guard — solide |
| **Tool-Loop Protection** | ★★★★☆ | `ToolCallGatekeeper` mit Ping-Pong-Detektion, Poll-No-Progress, Circuit-Breaker nach Fix 5 — funktionsfähig |
| **Policy/Approval** | ★★★★☆ | Nach Fixes 1/2/4 signifikant verbessert; Disk-Persistenz und `_validate_scope` robuster als zuvor |
| **Intent Classification** | ★★★☆☆ | Fixes 6/11/12 beheben die gröbsten False-Positives; strukturelle Schwäche: alles noch regelbasiert, kein semantisches Scoring |
| **Context Budget** | ★★★★☆ | `ToolResultContextGuard` nach Fixes 7/8 korrekt; `ContextReducer` konfigurierbar |
| **LLM Client** | ★★★☆☆ | Retry vorhanden, aber lineares Backoff (N-3); keine Circuit-Breaker-Integration im Client selbst |
| **Reflection/Verification** | ★★★☆☆ | `ReflectionService` LLM-getrieben und konfigurierbar mit Hard-Min; `verify_tool_result` bleibt regelbasiert fragil |

### 5.2 Kritische Pipeline-Schwachstellen nach Priorität

```
PRIORITY 1 — Korrektheitslücken (Produktionsblocker)
──────────────────────────────────────────────────────
[CB-1] _extract_actions: leere Action-Liste fragil behandelt        → unnötige Repair-Loops
[CB-2] _refresh_long_term_memory: Stale failure_retriever möglich   → falsche Plan-Guidance
[3.1]  clear_session_overrides: disk-backed session rules bleiben   → Policy-Bypass nach Session-Ende

PRIORITY 2 — Logikfehler / Sicherheit
──────────────────────────────────────
[N-1]  configure_runtime guard ist non-functional                   → unsafe mid-run reconfiguration
[CB-3] Calibration emittiert no-op Empfehlungen                     → fehlerhafte env_patch outputs

PRIORITY 3 — Stabilität / Robustheit
──────────────────────────────────────
[3.2]  verify_tool_result Substring-Logik bleibt fehleranfällig     → falsche Retry-Trigger
[N-3]  LLM-Retry lineares Backoff                                   → rate-limit Compounding
[N-2]  _refresh_ltm bei jedem run()                                 → unnötiger Overhead
[N-4]  all_snapshots() Exception silent swallowed                   → unsichtbare Kalibrierungs-Fehler
```

---

## 6. Empfohlene Fix-Reihenfolge

```
Sprint 1 — Korrektheit (alle blockierend für stabilen Betrieb):

  1. CB-2 fix: _clear_all()-Helper in _refresh_long_term_memory_store()     ~30 min
  2. CB-1 fix: _extract_actions — leere Liste direkt durchlassen            ~20 min
  3. Bug 3.1 fix: clear_session_overrides + _allow_always_rules purge       ~30 min

Sprint 2 — Sicherheit & Policy:

  4. N-1 fix: configure_runtime Guard implementieren (async oder Flag-Check) ~1h
  5. CB-3 fix: Calibration no-op Empfehlung guard                           ~20 min

Sprint 3 — Stabilität:

  6. N-3 fix: Exponentielles Backoff + Jitter im LLM Client                 ~30 min
  7. Bug 3.2: verify_tool_result auf strukturiertes Parsing umstellen        ~1h
  8. N-2: LTM-Refresh-Flag für Performance                                  ~30 min
  9. N-4: Exception-Logging in benchmark_calibration                         ~10 min
```

---

## 7. Fazit

Die Pipeline hat durch die Fixes des Voraudits deutliche Qualitätsgewinne erzielt — insbesondere in den Bereichen Policy-Enforcement, Intent-Klassifikation und Tool-Loop-Protection. Die **Recovery/Fallback-Schicht** ist architektonisch ausgezeichnet und produktionsreif.

Die verbleibenden **3 Priority-1-Bugs** (CB-1, CB-2, Bug 3.1) sind alle kleine, isolierte Fixes (~80 Zeilen gesamt), die aber wesentliche Korrektheitseigenschaften beeinflussen: deterministische Plan-Guidance, konsistentes Policy-Verhalten über Session-Grenzen hinweg und zuverlässige Tool-Selection-Signalisierung.

Nach Abschluss von Sprint 1 kann die Pipeline als **stabil und konsistent** bezeichnet werden. Die Gesamtqualität des Reasoning-Designs — insbesondere die Trennung in PlannnerAgent / ToolSelectorAgent / SynthesizerAgent mit dediziertem Orchestrator — ist solide und erweiterbar.
