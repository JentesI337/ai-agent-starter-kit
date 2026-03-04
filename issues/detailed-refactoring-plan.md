# Detailed Refactoring Plan — Reasoning Pipeline / Orchestrierung / Fine-Tuning
**Ziel: 11/10 — maximale Production-Performance ohne architektonische Schulden**

Stand: 2026-03-04 | Scope: Backend (`backend/app/`)

---

## Executive Summary

Drei eigenständige Upgrade-Tracks, die **parallel** entwickelt werden können (keine zirkulären Abhängigkeiten):

| Track | Ticket | Kern-Lücke heute | Zielzustand |
|---|---|---|---|
| T1 | Reasoning Pipeline | Keyword-Heuristiken, kein semantisches Gedächtnis | LLM-basierte Task-Klassifizierung + SQLite-RAG |
| T2 | Orchestrierung | Statische Modellprofile, kein Live-Health | Dynamische Kalibrierung + Circuit Breaker |
| T3 | Fine-Tuning / Performance | Kein Feedback-Loop, keine empirischen Parameter | Reflection→Optimierung-Cycle + A/B-Framework |

**Kein Big-Bang-Refactoring:** Alle drei Tracks folgen demselben Muster: neuer Service hinter einem Feature-Flag, Fallback auf das bisherige Verhalten, schrittweise Aktivierung.

---

## Track T1: Reasoning Pipeline — 7,5 → 11/10

### T1.1 Problem: Keyword-Heuristiken in `_requires_hard_research_structure` und `_resolve_task_type`

**Symptoms im Code heute:**

```python
# synthesizer_agent.py – fragil und wartungsintensiv
has_structured_section_markers = (
    "architektur-risiken" in normalized
    and "performance-hotspots" in normalized
    # ...fest kodierte deutsche Strings
)

# intent_detector.py – kombiniert regex + keyword soup
has_command_intent = bool(re.match(r"^\s*(please\s+)?(run|execute|start|launch)\b", lowered))
```

**Lösung: `TaskClassifier` — LLM-backed, cachebasiert, fail-safe**

**Neue Datei:** `backend/app/services/task_classifier.py`

```python
# KONZEPT (kein vollständiger Code, sondern Designvertrag)

@dataclass(frozen=True)
class TaskClassification:
    task_type: str          # "general" | "implementation" | "research" | "orchestration" |
                            #  "hard_research" | "command" | "trivial"
    confidence: float       # 0.0–1.0
    reasoning: str          # kurze LLM-Begründung für Auditierbarkeit
    fallback_used: bool     # True wenn LLM-Call fehlschlug und Keyword-Fallback griff

class TaskClassifier:
    """
    Ersetzt alle verstreuten Keyword-Checks in:
    - synthesizer_agent._resolve_task_type()
    - synthesizer_agent._requires_hard_research_structure()
    - intent_detector.IntentDetector.detect()
    - planner_agent._requires_hard_research_structure()

    Design-Prinzipien:
    - LLM-Call NUR wenn confidence durch Heuristik < threshold
    - Ergebnis wird in InMemory-LRU-Cache (max_items konfigurierbar) gespeichert
    - Immer Fallback auf bestehende Keyword-Logik bei LlmClientError
    - Niemals blocking im kritischen Pfad: fire-and-forget Cache-Warmup
    """

    def classify(self, user_message: str, tool_results: str | None) -> TaskClassification:
        ...

    async def classify_async(self, user_message: str, tool_results: str | None) -> TaskClassification:
        ...
```

**Migrations-Strategie für `synthesizer_agent.py`:**

```python
# VORHER
def _resolve_task_type(self, payload: SynthesizerInput) -> str:
    hinted = (payload.task_type or "").strip().lower()
    if hinted in {"hard_research", "research", ...}:
        return hinted
    # ... lange Keyword-Kaskade

# NACHHER
def _resolve_task_type(self, payload: SynthesizerInput) -> str:
    hinted = (payload.task_type or "").strip().lower()
    if hinted in VALID_TASK_TYPE_HINTS:   # unveränderter Hint-Bypass
        return hinted

    if self._task_classifier is not None and settings.task_classifier_enabled:
        classification = self._task_classifier.classify(
            payload.user_message, payload.tool_results
        )
        if classification.confidence >= settings.task_classifier_min_confidence:
            return classification.task_type
        # Confidence zu niedrig → Fallback auf Keyword-Logik

    return self._resolve_task_type_keyword_fallback(payload)  # bisherige Logik
```

**Config-Erweiterung in `config.py`:**

```python
task_classifier_enabled: bool = _parse_bool_env("TASK_CLASSIFIER_ENABLED", default=False)
task_classifier_min_confidence: float = float(os.getenv("TASK_CLASSIFIER_MIN_CONFIDENCE", "0.7"))
task_classifier_cache_max_items: int = int(os.getenv("TASK_CLASSIFIER_CACHE_MAX_ITEMS", "256"))
```

---

### T1.2 Problem: Kein semantisches Gedächtnis / RAG

**Symptoms:** `LongTermMemoryStore` (SQLite) speichert `FailureEntry`, `EpisodicEntry`, `SemanticEntry` — aber beim Planen wird nur `ContextReducer` (token-based) genutzt, nie semantisches Retrieval.

**Lösung: `SemanticContextRetriever` — SQLite FTS5 als Arme-Leute-RAG**

SQLite hat seit Version 3.36 eingebautes FTS5 (Full-Text-Search) — kein neuer Dependency required.

**Neue Datei:** `backend/app/services/semantic_context_retriever.py`

```python
# KONZEPT

@dataclass(frozen=True)
class RetrievedContext:
    source: str           # "failure_journal" | "episodic" | "semantic"
    content: str
    relevance_score: float
    entry_id: str

class SemanticContextRetriever:
    """
    Nutzt SQLite FTS5 über denselben DB-Path wie LongTermMemoryStore.
    Keine neuen Abhängigkeiten. Kein Vektorspeicher nötig für v1.

    Schema-Erweiterung in LongTermMemoryStore:
        CREATE VIRTUAL TABLE IF NOT EXISTS failure_fts
        USING fts5(id UNINDEXED, task_description, root_cause, solution, content=failure_journal);

        CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts
        USING fts5(id UNINDEXED, summary, content=episodic);

    Retrieval:
        SELECT f.*, bm25(failure_fts) as score
        FROM failure_fts
        JOIN failure_journal f ON f.id = failure_fts.id
        WHERE failure_fts MATCH ?
        ORDER BY bm25(failure_fts)
        LIMIT 5;
    """

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        sources: tuple[str, ...] = ("failure_journal", "episodic"),
    ) -> list[RetrievedContext]:
        ...
```

**Integration in `HeadAgent.run()`:**

```python
# In agent.py — nach memory_update, vor planner_step
if settings.semantic_retrieval_enabled:
    retrieved = self._semantic_retriever.retrieve(
        user_message,
        top_k=settings.semantic_retrieval_top_k,
    )
    if retrieved:
        # Als Block in reduced_context einbinden, aber Budgetgrenze respektieren
        semantic_context = self._format_retrieved_context(retrieved)
        reduced_context = self._prepend_semantic_context(
            reduced_context, semantic_context,
            budget_chars=settings.semantic_retrieval_max_chars,
        )
```

**Config-Erweiterung:**

```python
semantic_retrieval_enabled: bool = _parse_bool_env("SEMANTIC_RETRIEVAL_ENABLED", default=False)
semantic_retrieval_top_k: int = int(os.getenv("SEMANTIC_RETRIEVAL_TOP_K", "5"))
semantic_retrieval_max_chars: int = int(os.getenv("SEMANTIC_RETRIEVAL_MAX_CHARS", "2000"))
```

---

### T1.3 Problem: `VerificationService.verify_plan_semantically` — Word-Overlap mit threshold=0.15

**Problem:** `coverage < 0.15` ist zu niedrig; prüft nur Wortmenge, nicht Semantik; Stoppwortliste veraltet und undokumentiert.

**Lösung: Inkrementelle Verbesserung ohne neuen LLM-Call**

```python
# VORHER
coverage < 0.15  # → warning

# NACHHER: zwei Schwellen + explizite Raison
PLAN_COVERAGE_WARN_THRESHOLD = 0.25   # aus settings, konfigurierbar
PLAN_COVERAGE_FAIL_THRESHOLD = 0.10   # frühzeitiger Hard-Fail

# Stoppwortliste aus Datei laden (app/data/stopwords_de_en.txt)
# → wartbar, versionierbar, testbar
```

```python
# config.py
plan_coverage_warn_threshold: float = float(os.getenv("PLAN_COVERAGE_WARN_THRESHOLD", "0.25"))
plan_coverage_fail_threshold: float = float(os.getenv("PLAN_COVERAGE_FAIL_THRESHOLD", "0.10"))
```

---

### T1.4 Problem: `ReflectionService.threshold` statisch bei 0.6

**Lösung: Task-type-sensitiver Threshold**

```python
# reflection_service.py
REFLECTION_THRESHOLDS_BY_TASK_TYPE: dict[str, float] = {
    "hard_research":    0.75,   # höchster Anspruch: Quellen müssen belegbar sein
    "research":         0.70,
    "implementation":   0.65,   # Code muss funktional sein
    "orchestration":    0.60,
    "general":          0.55,
    "trivial":          0.40,   # kleine Antworten haben naturgemäß niedrigere Scores
}

async def reflect(self, ..., task_type: str | None = None) -> ReflectionVerdict:
    effective_threshold = REFLECTION_THRESHOLDS_BY_TASK_TYPE.get(
        task_type or "general",
        self.threshold,  # konfigurierbarer Fallback
    )
    # ... Verdikt mit effective_threshold berechnen
```

---

### T1 — Akzeptanzkriterien

- [ ] `TaskClassifier` hat 100% Unit-Test-Coverage; bei `LlmClientError` muss immer Keyword-Fallback greifen (Test: mock LlmClient raises → Classification.fallback_used=True)
- [ ] `SemanticContextRetriever` gibt leere Liste zurück wenn FTS5-Tabelle nicht existiert (graceful degradation)
- [ ] Kein neuer Pip-Package-Dependency für T1.1–T1.4 (nur stdlib + vorhandene Deps)
- [ ] Feature-Flags (`task_classifier_enabled`, `semantic_retrieval_enabled`) default=False; Tests müssen auch im deaktivierten Modus grünen
- [ ] `ReflectionService.reflect()` behält bisherige Signatur; `task_type`-Parameter ist optional mit Default-Fallback
- [ ] `_requires_hard_research_structure` bleibt als statische Methode für Rückwärtskompatibilität erhalten, delegiert intern an `TaskClassifier` wenn enabled
- [ ] Alle bestehenden Tests in `test_synthesizer_agent.py`, `test_planner_agent.py`, `test_reflection_service.py` weiterhin grün

### T1 — Dos & Don'ts

**DO:**
- `TaskClassifier` immer mit eigenem LLM-Client-Instance (kein Sharing mit HeadAgent), um Circuit-Breaker-Isolation zu wahren
- FTS5-Schema-Migration als separates `migrate_fts_schema()` in `LongTermMemoryStore`, aufrufbar aus `startup_tasks.py`
- Alle neuen Config-Keys mit `# since T1` kommentieren
- `classification.reasoning` in Lifecycle-Events einbetten (`stage="task_classified"`)

**DON'T:**
- Kein Vektorspeicher (ChromaDB, pgvector o.ä.) als Dependency — SQLite FTS5 reicht für v1 und hat zero Infrastrukturkosten
- Nicht `_resolve_task_type` auf LLM-Only umstellen; Hint-Bypass (`hinted in VALID_TASK_TYPE_HINTS`) muss absoluten Vorrang behalten
- Kein blocking LLM-Call in `_requires_hard_research_structure` — der wird synchron aus `execute()` aufgerufen; dort nur Cache-Lookup
- Nicht Stoppwortliste im Code hardcoden; externe Datei `app/data/stopwords_de_en.txt` mit Test-Assertion auf Existenz

---

## Track T2: Orchestrierung — 8,0 → 11/10

### T2.1 Problem: `ModelRegistry` mit komplett statischen Profilen

**Problem-Code in `model_registry.py`:**

```python
ModelCapabilityProfile(
    model_id=settings.local_model,
    health_score=0.92,           # Schätzung, nie gemessen
    expected_latency_ms=950,     # Schätzung
    cost_score=0.15,             # willkürlich
)
```

Das `PipelineRunner._resolve_adaptive_inference()` entscheidet über Modellwechsel basierend auf diesen Werten — falsche Schätzungen führen zu falschen Downgrades.

**Lösung: `ModelHealthTracker` — misst Latenz im laufenden Betrieb**

**Neue Datei:** `backend/app/services/model_health_tracker.py`

```python
# KONZEPT

@dataclass
class ModelHealthSample:
    model_id: str
    latency_ms: int
    success: bool
    timestamp_utc: str
    request_id: str

@dataclass
class ModelHealthSnapshot:
    model_id: str
    p50_latency_ms: int
    p95_latency_ms: int
    health_score: float          # = success_rate_last_n_calls
    sample_count: int
    last_updated: str
    is_stale: bool               # True wenn kein Sample in den letzten X Sekunden

class ModelHealthTracker:
    """
    Schreibt nach jedem agent.run()-Call ein ModelHealthSample (Latenz + Erfolg).
    Hält in-memory einen Ring-Buffer (konfigurierbare Größe).
    Persistiert aggregierten Snapshot in state_store (JSON).

    Integration:
    - FallbackStateMachine._run_single_attempt() → nach LlmClientError: record(success=False)
    - FallbackStateMachine._run_single_attempt() → nach Erfolg: record(success=True, latency_ms=...)
    - ModelRegistry.resolve() prüft zuerst ModelHealthTracker-Snapshot, überschreibt health_score
      und expected_latency_ms mit gemessenen Werten wenn sample_count >= min_samples
    """

    def record(self, *, model_id: str, latency_ms: int, success: bool, request_id: str) -> None: ...

    def snapshot(self, model_id: str) -> ModelHealthSnapshot | None: ...

    def apply_to_profile(self, profile: ModelCapabilityProfile) -> ModelCapabilityProfile:
        """Gibt neues Profil zurück mit gemessenen Werten (immutable)."""
        snap = self.snapshot(profile.model_id)
        if snap is None or snap.is_stale or snap.sample_count < self._min_samples:
            return profile
        return profile.model_copy(update={
            "health_score": snap.health_score,
            "expected_latency_ms": snap.p50_latency_ms,
        })
```

**Modifikation in `ModelRouter.route()`:**

```python
# model_routing/router.py — NACHHER
def route(self, ...) -> ModelRouteDecision:
    ...
    # NEU: gemessene Profile überschreiben statische
    if self._health_tracker:
        profile = self._health_tracker.apply_to_profile(profile)
    return ModelRouteDecision(primary_model=primary, fallback_models=fallbacks, profile=profile, scores=scores)
```

**Config:**

```python
model_health_tracker_enabled: bool = _parse_bool_env("MODEL_HEALTH_TRACKER_ENABLED", default=False)
model_health_tracker_ring_buffer_size: int = int(os.getenv("MODEL_HEALTH_TRACKER_RING_BUFFER_SIZE", "50"))
model_health_tracker_min_samples: int = int(os.getenv("MODEL_HEALTH_TRACKER_MIN_SAMPLES", "10"))
model_health_tracker_stale_after_seconds: int = int(os.getenv("MODEL_HEALTH_TRACKER_STALE_AFTER_SECONDS", "300"))
```

---

### T2.2 Problem: Kein Circuit Breaker — Recovery reagiert nur reaktiv

**Aktuell:** `FallbackStateMachine` retried bei jedem Fehler, bis `max_attempts` erschöpft ist — auch wenn ein Modell seit 10 Minuten 100% Fehlerrate hat.

**Lösung: `CircuitBreakerRegistry` — open/half-open/closed per Modell-ID**

**Neue Datei:** `backend/app/services/circuit_breaker.py`

```python
# KONZEPT

class CircuitState(str, Enum):
    CLOSED = "closed"       # normal
    OPEN = "open"           # kein Traffic
    HALF_OPEN = "half_open" # 1 Probe-Request

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5          # Fehler in failure_window_seconds → OPEN
    failure_window_seconds: int = 60
    recovery_timeout_seconds: int = 120 # Zeit in OPEN bevor → HALF_OPEN
    success_threshold: int = 2          # Erfolge in HALF_OPEN → CLOSED

class CircuitBreaker:
    def record_success(self, model_id: str) -> None: ...
    def record_failure(self, model_id: str) -> None: ...
    def get_state(self, model_id: str) -> CircuitState: ...
    def allow_request(self, model_id: str) -> bool:
        """False wenn OPEN; True wenn CLOSED oder HALF_OPEN."""
```

**Integration in `FallbackStateMachine`:**

```python
# fallback_state_machine.py — _run_single_attempt() Anfang
if self._circuit_breaker and not self._circuit_breaker.allow_request(current_model):
    # Direkt zum nächsten Fallback-Modell, ohne LLM-Call
    raise LlmClientError(f"Circuit breaker OPEN for model {current_model}")
```

```python
# fallback_state_machine.py — nach erfolgreichem LLM-Call
if self._circuit_breaker:
    self._circuit_breaker.record_success(current_model)
```

**Config:**

```python
circuit_breaker_enabled: bool = _parse_bool_env("CIRCUIT_BREAKER_ENABLED", default=False)
circuit_breaker_failure_threshold: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
circuit_breaker_failure_window_seconds: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_WINDOW_SECONDS", "60"))
circuit_breaker_recovery_timeout_seconds: int = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS", "120"))
```

---

### T2.3 Problem: `_classify_failover_reason` via String-Matching auf Error-Messages

**Problem-Code:**

```python
def _classify_failover_reason(self, message: str) -> str:
    text = (message or "").lower()
    if "compaction" in text and ("failed" in text or "timeout" in text ...):
        return "compaction_failure"
    # ... weitere String-Matches
```

Wenn ein LLM-Provider seine Error-Messages ändert, fallen Matches still durch.

**Lösung: Explizite Exception-Hierarchie + Typed Error-Codes**

```python
# errors.py — neue Subklassen mit typed reason
class LlmClientError(Exception):
    """Basisklasse — reason bleibt string für Abwärtskompatibilität."""

class LlmContextOverflowError(LlmClientError):
    reason: str = "context_overflow"

class LlmCompactionFailureError(LlmClientError):
    reason: str = "compaction_failure"

class LlmRateLimitError(LlmClientError):
    reason: str = "rate_limited"

class LlmModelNotFoundError(LlmClientError):
    reason: str = "model_not_found"

class LlmTimeoutError(LlmClientError):
    reason: str = "timeout"
```

```python
# pipeline_runner.py — NACHHER (Typed Exception zuerst, String-Fallback bleibt)
def _classify_failover_reason(self, exc: Exception) -> str:
    if hasattr(exc, "reason"):          # Typed Exception → direkt auslesen
        return str(exc.reason)
    # Fallback auf bisheriges String-Matching für nicht-typisierte Fehler
    return self._classify_failover_reason_from_string(str(exc))
```

---

### T2.4 Problem: Scoring-Formel willkürlich kalibriert

```python
# router.py — HEUTE
return (
    profile.health_score * 100.0
    - (profile.expected_latency_ms / 100.0)
    - (profile.cost_score * 10.0)
    + runtime_bonus       # 6.0
    + reasoning_bonus     # variiert
)
```

Die konstanten Gewichte (`100.0`, `10.0`, `6.0`) sind nicht empirisch bestimmt.

**Lösung: Gewichte konfigurierbar + dokumentiert**

```python
# config.py
model_score_weight_health: float = float(os.getenv("MODEL_SCORE_WEIGHT_HEALTH", "100.0"))
model_score_weight_latency: float = float(os.getenv("MODEL_SCORE_WEIGHT_LATENCY", "0.01"))  # per ms
model_score_weight_cost: float = float(os.getenv("MODEL_SCORE_WEIGHT_COST", "10.0"))
model_score_runtime_bonus: float = float(os.getenv("MODEL_SCORE_RUNTIME_BONUS", "6.0"))
```

```python
# router.py — NACHHER
return (
    profile.health_score * settings.model_score_weight_health
    - (profile.expected_latency_ms * settings.model_score_weight_latency)
    - (profile.cost_score * settings.model_score_weight_cost)
    + runtime_bonus
    + reasoning_bonus
)
```

Das ermöglicht empirische Kalibrierung durch Benchmark-Replay ohne Code-Änderung.

---

### T2 — Akzeptanzkriterien

- [ ] `ModelHealthTracker.apply_to_profile()` gibt immer eine immutable neue Instanz zurück; Originalprofile aus `ModelRegistry` werden nicht mutiert
- [ ] `CircuitBreaker.allow_request()` gibt bei `HALF_OPEN` genau **einen** Request durch (thread-safe mit asyncio.Lock oder äquivalent)
- [ ] `_classify_failover_reason` muss bei unbekannter Exception immer `"unknown"` zurückgeben, niemals Exception werfen
- [ ] Unit-Tests für `CircuitBreaker`: Zustandsübergänge `closed→open`, `open→half_open`, `half_open→closed`, `half_open→open` explizit getestet
- [ ] `ModelHealthTracker` Ring-Buffer: nach `ring_buffer_size+1` Samples enthält Buffer noch genau `ring_buffer_size` Einträge
- [ ] Alle Scoring-Gewichte haben `.env`-Dokumentation in `README.md` (oder `backend/.env.example`)
- [ ] `test_pipeline_runner_recovery.py` und `test_fallback_state_machine.py` weiterhin grün
- [ ] Beim Start in `startup_tasks.py`: wenn `model_health_tracker_enabled=True`, wird persistierter Snapshot geladen (keine cold-start-Regression)

### T2 — Dos & Don'ts

**DO:**
- `ModelHealthTracker` als Singleton-Service in `RuntimeComponents` registrieren (analog zu `orchestrator_api`)
- `CircuitBreaker`-Zustandsübergänge als Lifecycle-Events emittieren (`stage="circuit_breaker_state_changed"`)
- Messung der Latenz mit `time.monotonic()`, nicht `time.time()` (nicht wall-clock-sensitiv)
- `ModelHealthSnapshot.is_stale` auswerten: wenn stale → nicht in Scoring einbeziehen (fallback auf statische Profile)

**DON'T:**
- **Kein** circuit-breaker-Zustand in SQLite persistieren — rein in-memory; nach Neustart closed (fresh start ist sicherer)
- Circuit Breaker **nicht** für `GuardrailViolation`-Fehler öffnen — diese sind anwendungsseitig, nicht modellseitig
- `ModelHealthTracker` **nicht** threadsafe via GIL-Annahme implementieren — async-safe mit `asyncio.Lock` da codebase async-first
- Scoring-Gewichte **nicht** als Teil des Profil-Schemas speichern — sie gehören in `Settings`, nicht in `ModelCapabilityProfile`

---

## Track T3: Fine-Tuning / Performance — 5,0 → 11/10

### T3.1 Problem: ReflectionService diagnostiziert, optimiert aber nichts

**Aktuell:** `ReflectionVerdict` wird emittiert als Lifecycle-Event, aber nicht persistiert und nicht für future prompts genutzt.

**Lösung: `ReflectionFeedbackStore` + Closed-Loop in `SynthesizerAgent`**

**Neue Datei:** `backend/app/services/reflection_feedback_store.py`

```python
# KONZEPT

@dataclass(frozen=True)
class ReflectionRecord:
    record_id: str
    session_id: str
    request_id: str
    task_type: str
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    model_id: str
    prompt_variant: str | None   # für A/B-Tracking
    retry_triggered: bool
    timestamp_utc: str

class ReflectionFeedbackStore:
    """
    SQLite-Tabelle 'reflection_feedback' in der bestehenden LTM-DB.
    Kein neuer DB-File nötig.

    Aggregation:
    - get_avg_scores_by_task_type() → dict[str, dict[str, float]]
    - get_weak_task_types(threshold=0.65) → list[str]
    - get_retry_rate_by_model() → dict[str, float]
    """

    def store(self, record: ReflectionRecord) -> None: ...

    def get_avg_scores_by_task_type(
        self,
        *,
        last_n: int = 100,
    ) -> dict[str, dict[str, float]]: ...

    def get_retry_rate_by_model(self, *, last_n: int = 100) -> dict[str, float]: ...
```

**Schema-Addition in `LongTermMemoryStore._ensure_schema()`:**

```sql
CREATE TABLE IF NOT EXISTS reflection_feedback (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    request_id  TEXT NOT NULL,
    task_type   TEXT NOT NULL,
    score       REAL NOT NULL,
    goal_alignment    REAL,
    completeness      REAL,
    factual_grounding REAL,
    issues      TEXT,           -- JSON-Array als String
    suggested_fix TEXT,
    model_id    TEXT,
    prompt_variant TEXT,
    retry_triggered INTEGER,
    timestamp   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rf_task_type ON reflection_feedback(task_type);
CREATE INDEX IF NOT EXISTS idx_rf_model     ON reflection_feedback(model_id);
```

**Closed Loop in `agent.py`:**

```python
# agent.py — in run() nach synthesis_step, wenn reflection_enabled
if reflection_verdict is not None and self._reflection_feedback_store:
    self._reflection_feedback_store.store(ReflectionRecord(
        record_id=f"{request_id}-reflection",
        session_id=session_id,
        request_id=request_id,
        task_type=synthesis_task_type,
        score=reflection_verdict.score,
        goal_alignment=reflection_verdict.goal_alignment,
        completeness=reflection_verdict.completeness,
        factual_grounding=reflection_verdict.factual_grounding,
        issues=reflection_verdict.issues,
        suggested_fix=reflection_verdict.suggested_fix,
        model_id=model or settings.llm_model,
        prompt_variant=None,   # ab T3.3 befüllt
        retry_triggered=reflection_verdict.should_retry,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
    ))
```

---

### T3.2 Problem: Statische Temperature — keine Task-Type-Sensitivität

**Problem:** `SynthesizerAgent.constraints.temperature = 0.3` ist für alle Task-Types gleich.

- Bei `hard_research`: zu hoch → mehr Varianz → mehr halluzinierte Details
- Bei `trivial`/`general`: zu niedrig → zu deterministisch → unlebendig

**Lösung: `DynamicTemperatureResolver`**

**Neue Datei:** `backend/app/services/dynamic_temperature.py`

```python
# KONZEPT

TEMPERATURE_BY_TASK_TYPE: dict[str, float] = {
    "hard_research":    0.1,    # maximale Faktentreue
    "research":         0.15,
    "implementation":   0.15,   # Code-Korrektheit > Kreativität
    "orchestration":    0.2,
    "general":          0.3,    # ausgewogen
    "trivial":          0.4,    # flüssiger, natürlicher Ton
}

class DynamicTemperatureResolver:
    def __init__(self, base_temperature: float, overrides: dict[str, float] | None = None):
        self._base = base_temperature
        self._overrides = {**TEMPERATURE_BY_TASK_TYPE, **(overrides or {})}

    def resolve(self, task_type: str | None, *, reasoning_level: str | None = None) -> float:
        base = self._overrides.get(task_type or "general", self._base)
        if reasoning_level in {"high", "ultrathink"}:
            return max(0.05, base - 0.05)   # noch deterministischer bei deep reasoning
        if reasoning_level == "low":
            return min(0.5, base + 0.05)    # etwas freier bei schnellen Antworten
        return base
```

**Integration in `SynthesizerAgent.execute()`:**

```python
# synthesizer_agent.py
task_type = self._resolve_task_type(payload)
effective_temperature = self._temperature_resolver.resolve(
    task_type=task_type,
    reasoning_level=getattr(payload, "reasoning_level", None),
)
raw_answer = await self.client.complete_chat(
    system_prompt=self.system_prompt,
    user_prompt=prompt,
    model=model,
    temperature=effective_temperature,   # statt self.constraints.temperature
)
```

**Config:**

```python
dynamic_temperature_enabled: bool = _parse_bool_env("DYNAMIC_TEMPERATURE_ENABLED", default=False)
# Einzelne Overrides als Mapping: "hard_research:0.05,implementation:0.10"
dynamic_temperature_overrides: dict[str, float] = _parse_float_mapping_env(
    os.getenv("DYNAMIC_TEMPERATURE_OVERRIDES")
)
```

---

### T3.3 Problem: Kein A/B-Framework für Prompt-Varianten

**Ziel:** Prompt-Änderungen empirisch validieren statt zu raten.

**Neue Datei:** `backend/app/services/prompt_ab_registry.py`

```python
# KONZEPT

@dataclass(frozen=True)
class PromptVariant:
    variant_id: str    # z.B. "synthesizer_v2_research"
    prompt_text: str
    weight: float      # Sampling-Wahrscheinlichkeit (0.0–1.0); alle Varianten einer Gruppe summieren zu 1.0

class PromptAbRegistry:
    """
    Lädt Varianten aus einer JSON-Datei (kein Neustart nötig bei Hot-Reload).
    Wählt per deterministischem Hash(session_id + variant_group) → reproducible per session.

    Format: backend/data/prompt_variants.json
    {
      "synthesizer_research": [
        {"variant_id": "v1_baseline", "prompt_text": "...", "weight": 0.5},
        {"variant_id": "v2_cot",      "prompt_text": "...", "weight": 0.5}
      ]
    }
    """

    def select(self, group: str, session_id: str) -> PromptVariant | None:
        """
        Gibt None zurück wenn keine Varianten konfiguriert → Fallback auf Settings-Prompt.
        Hash-basierung stellt sicher: dieselbe session_id bekommt immer dieselbe Variante.
        """
        ...
```

**Integration in `SynthesizerAgent`:**

```python
# synthesizer_agent.py — _build_final_prompt()
if self._ab_registry and settings.prompt_ab_enabled:
    variant = self._ab_registry.select(
        group=f"synthesizer_{task_type}",
        session_id=payload.session_id,
    )
    if variant:
        prompt_variant_id = variant.variant_id
        final_instructions = variant.prompt_text
    else:
        prompt_variant_id = None
        final_instructions = self.system_prompt  # Baseline
```

---

### T3.4 Problem: Benchmark-Ergebnisse werden nicht für automatische Kalibrierung genutzt

**Aktuell:** `backend/monitoring/eval_golden_suite.json` und `backend/benchmarks/` produzieren Artefakte, die manuell interpretiert werden müssen.

**Lösung: `BenchmarkCalibrationService` — extrahiert Kalibrierungs-Empfehlungen aus Benchmark-Runs**

**Neue Datei:** `backend/app/services/benchmark_calibration.py`

```python
# KONZEPT

@dataclass(frozen=True)
class CalibrationRecommendation:
    parameter: str          # z.B. "model_score_weight_health"
    current_value: float
    recommended_value: float
    confidence: float       # 0.0–1.0 basierend auf Datenmenge
    evidence: str           # kurze Begründung

class BenchmarkCalibrationService:
    """
    Analysiert:
    - ReflectionFeedbackStore: avg scores by task_type → Empfehlung für threshold-Anpassung
    - ModelHealthTracker: p95-Latenzen vs. statische Profile → Empfehlung für Gewichte
    - FallbackStateMachine recovery_metrics: welche Strategien gewinnen → Empfehlung für priority_steps

    Ausgabe:
    - Liste von CalibrationRecommendation (für menschliche Review)
    - Optional: direkt als .env-Patch-Vorschlag (nur mit CALIBRATION_AUTOWRITE=false default)
    """

    def analyze(self) -> list[CalibrationRecommendation]: ...

    def export_env_patch(self, recommendations: list[CalibrationRecommendation]) -> str:
        """Gibt .env-Fragment zurück (NIEMALS automatisch schreiben — nur anzeigen)."""
        ...
```

**Exposition als Debug-Endpoint:**

```python
# runtime_debug_endpoints.py — neuer Endpoint
@router.get("/debug/calibration-recommendations")
async def calibration_recommendations():
    svc = BenchmarkCalibrationService(...)
    return {"recommendations": svc.analyze()}
```

---

### T3.5 Problem: Failure-Journal nicht aktiv im Planer genutzt

**Aktuell:** `LongTermMemoryStore.add_failure()` wird beim Scheitern aufgerufen (gut), aber beim Planen wird nicht danach gesucht.

**Lösung: In `PlannerAgent.execute()` ähnliche Failure-Patterns injecten**

```python
# planner_agent.py — execute()
if self._failure_retriever and settings.failure_context_enabled:
    similar_failures = self._failure_retriever.retrieve(
        user_message, sources=("failure_journal",), top_k=3
    )
    if similar_failures:
        sections["failure_context"] = self._format_failure_context(similar_failures)
        # → PromptKernelBuilder fügt 'failure_context'-Section ein
        # → Planer kann bekannte Fehler proaktiv umgehen
```

---

### T3 — Akzeptanzkriterien

- [ ] `ReflectionFeedbackStore.store()` nie blockend; bei SQLite-Fehler: log warning, nie Exception propagieren
- [ ] `DynamicTemperatureResolver.resolve()` immer im Bereich [0.0, 1.0]; bei unbekanntem task_type → base_temperature
- [ ] `PromptAbRegistry.select()` ist deterministisch: gleiche `(group, session_id)` → immer gleiche Variante (Property-Based-Test mit Hypothesis oder manuell mit 100 runs)
- [ ] `BenchmarkCalibrationService.export_env_patch()` schreibt **niemals** direkt in eine Datei — nur return-value
- [ ] Neue SQLite-Tabelle `reflection_feedback` wird bei `_ensure_schema()` idempotent erstellt (kein DROP, kein Datenverlust)
- [ ] `dynamic_temperature_enabled=False` default → kein Verhalten-Unterschied für bestehende Tests
- [ ] `prompt_ab_enabled=False` default → `SynthesizerAgent` nutzt unverändertet `self.system_prompt`
- [ ] `test_synthesizer_agent.py`: mindestens 2 neue Tests: (a) dynamic temperature ändert sich je task_type, (b) A/B-select ist deterministisch per session_id
- [ ] `ReflectionFeedbackStore`: Integration-Test mit in-memory SQLite (`":memory:"`)

### T3 — Dos & Don'ts

**DO:**
- `ReflectionFeedbackStore` in dieselbe SQLite-DB wie `LongTermMemoryStore` legen (gleicher `db_path`) — **ein** DB-File, kein Zoo
- `DynamicTemperatureResolver` als Injectable in `SynthesizerAgent.__init__()` übergeben — kein globales Singleton, testbar durch Mock
- `PromptAbRegistry` Hot-Reload: beim nächsten `select()`-Aufruf die JSON-Datei re-lesen wenn `mtime` sich geändert hat
- `BenchmarkCalibrationService` immer mit mindestens `min_samples=20` Guard: unter 20 Samples keine Empfehlung für Gewichte

**DON'T:**
- Temperature-Overrides **nicht** pro-Model konfigurieren — nur pro Task-Type; sonst explodiert Konfigurationsraum
- A/B-Varianten **nicht** request-by-request rotieren (round-robin) — muss session-stabil sein, sonst verfälschte Comparison
- Benchmark-Kalibrierung **nicht** automatisch in `settings` schreiben — immer menschliche Review-Schleife
- `ReflectionFeedbackStore` **nicht** retroaktiv mit Schätzwerten befüllen — nur echter Produktivbetrieb liefert valide Daten

---

## Übergreifende Architektur-Entscheidungen

### Neue Service-Abhängigkeiten im Dependency-Graphen

```
RuntimeComponents (app_setup.py)
    ├── LongTermMemoryStore          (bestehend)
    │   └── ReflectionFeedbackStore  (T3.1 — gleiche DB)
    │   └── SemanticContextRetriever (T1.2 — FTS5 über gleiche DB)
    ├── ModelHealthTracker           (T2.1 — neu, in-memory + JSON-persist)
    │   └── ModelRouter              (nutzt ModelHealthTracker.apply_to_profile)
    ├── CircuitBreakerRegistry       (T2.2 — neu, rein in-memory)
    │   └── FallbackStateMachine     (nutzt CircuitBreaker.allow_request)
    ├── TaskClassifier               (T1.1 — neu, eigener LlmClient)
    │   └── SynthesizerAgent
    │   └── PlannerAgent
    ├── DynamicTemperatureResolver   (T3.2 — neu, kein Dep)
    │   └── SynthesizerAgent
    └── PromptAbRegistry             (T3.3 — neu, JSON-Datei)
        └── SynthesizerAgent
        └── PlannerAgent
```

Alle neuen Services sind **optional** und hinter Feature-Flags geschützt. Bei `enabled=False` verhält sich das System exakt wie heute.

---

### Rollout-Reihenfolge (empfohlen)

```
Phase 1 (kein LLM-Overhead):
  T2.3  Typed Exception Hierarchy
  T2.4  Scoring-Gewichte konfigurierbar
  T1.3  VerificationService Schwellen konfigurierbar
  T1.4  ReflectionService task-type-sensitiver Threshold

Phase 2 (neuer State, kein LLM):
  T3.1  ReflectionFeedbackStore (SQLite, rein writes)
  T2.1  ModelHealthTracker (in-memory Ring-Buffer)
  T1.2  SemanticContextRetriever (SQLite FTS5 Schema)

Phase 3 (neue LLM-Calls, Feature-Flag=False default):
  T1.1  TaskClassifier (LLM-backed, cachebasiert)
  T2.2  CircuitBreaker (nach Health-Tracker Daten)
  T3.2  DynamicTemperature
  T3.5  Failure-Context im Planer

Phase 4 (A/B + Calibration):
  T3.3  PromptAbRegistry
  T3.4  BenchmarkCalibrationService
```

---

### Show-Stopper-Checkliste (Vor Go-Live)

Diese Punkte MÜSSEN vor Production-Deployment grün sein:

- [ ] Circuit Breaker: `open → half_open`-Übergang ist thread-safe (keine Race Condition bei gleichzeitigen Requests)
- [ ] ModelHealthTracker: Ring-Buffer ist thread-safe (async Lock, nicht GIL-Verlass)
- [ ] ReflectionFeedbackStore: SQLite `WAL`-Mode aktiviert (verhindert Reader-Writer-Deadlock bei async Nutzung)
- [ ] TaskClassifier: bei LlmClientError **immer** Keyword-Fallback — niemals Exception nach oben propagieren
- [ ] PromptAbRegistry: bei fehlender/invalider JSON-Datei → kein Crash, alle Gruppen → None → Settings-Prompt
- [ ] SemanticContextRetriever: bei SQLite FTS5-Fehler → leere Liste, nie Exception
- [ ] DynamicTemperature: clamp auf [0.02, 0.99] da manche Provider temperature=0 oder >1 ablehnen
- [ ] BenchmarkCalibrationService: export_env_patch existiert kein File-IO

---

## Neue Testpflichten

| Datei | Mind. neue Tests |
|---|---|
| `test_task_classifier.py` | LLM-Call erfolg, LLM-Fehler→Fallback, Cache-Hit, Confidence-Schwelle |
| `test_semantic_context_retriever.py` | FTS5 hit, FTS5 miss, leere DB, fehlende Tabelle |
| `test_model_health_tracker.py` | Ring-Buffer-Rotation, Stale-Detection, apply_to_profile immutability |
| `test_circuit_breaker.py` | closed→open, open→half_open, half_open→closed, half_open→open, thread-safety |
| `test_reflection_feedback_store.py` | store(), get_avg_scores, get_retry_rate, SQLite-Fehler→warning-no-raise |
| `test_dynamic_temperature.py` | alle task_types, reasoning_level-Einfluss, clamping |
| `test_prompt_ab_registry.py` | Determinismus (100 runs), fehlende Datei, gewichtete Auswahl |

---

## Summary-Tabelle

| # | Track | Neue Dateien | Modifizierte Dateien | Feature-Flag | Prio |
|---|---|---|---|---|---|
| T1.1 | TaskClassifier | `services/task_classifier.py` | `agents/synthesizer_agent.py`, `agents/planner_agent.py`, `services/intent_detector.py` | `task_classifier_enabled` | P2 |
| T1.2 | SemanticContextRetriever | `services/semantic_context_retriever.py` | `services/long_term_memory.py`, `agent.py` | `semantic_retrieval_enabled` | P2 |
| T1.3 | VerificationService Schwellen | — | `services/verification_service.py`, `config.py` | — | P1 |
| T1.4 | ReflectionService Threshold | — | `services/reflection_service.py`, `config.py` | — | P1 |
| T2.1 | ModelHealthTracker | `services/model_health_tracker.py` | `model_routing/router.py`, `orchestrator/fallback_state_machine.py` | `model_health_tracker_enabled` | P2 |
| T2.2 | CircuitBreaker | `services/circuit_breaker.py` | `orchestrator/fallback_state_machine.py` | `circuit_breaker_enabled` | P2 |
| T2.3 | Typed Exceptions | — | `errors.py`, `orchestrator/pipeline_runner.py`, `llm_client.py` | — | P1 |
| T2.4 | Scoring-Gewichte konfigurierbar | — | `model_routing/router.py`, `config.py` | — | P1 |
| T3.1 | ReflectionFeedbackStore | `services/reflection_feedback_store.py` | `services/long_term_memory.py`, `agent.py` | `reflection_feedback_enabled` | P2 |
| T3.2 | DynamicTemperature | `services/dynamic_temperature.py` | `agents/synthesizer_agent.py`, `config.py` | `dynamic_temperature_enabled` | P2 |
| T3.3 | PromptAbRegistry | `services/prompt_ab_registry.py` | `agents/synthesizer_agent.py`, `agents/planner_agent.py` | `prompt_ab_enabled` | P3 |
| T3.4 | BenchmarkCalibration | `services/benchmark_calibration.py` | `runtime_debug_endpoints.py` | — | P3 |
| T3.5 | Failure-Context im Planer | — | `agents/planner_agent.py`, `agent.py` | `failure_context_enabled` | P3 |
