# Refactoring Guide — Backend

**Datum:** 2026-03-05  
**Basis:** [QUALITY_ASSESSMENT_BACKEND_PROMPT.md](QUALITY_ASSESSMENT_BACKEND_PROMPT.md) §31 Priorisierter Maßnahmenplan  
**Scope:** 10 Maßnahmen über 3 Sprints

---

## Inhaltsverzeichnis

1. [N-1: configure_runtime() Guard](#n-1-configure_runtime-guard)
2. [N-3: LLM-Client exponentielles Backoff + Jitter](#n-3-llm-client-backoff)
3. [TD-6: Coverage-Pipeline aktivieren](#td-6-coverage-pipeline)
4. [N-2: LTM-Refresh-Flag statt per-run Check](#n-2-ltm-refresh-flag)
5. [N-4: Exception-Logging in benchmark_calibration](#n-4-exception-logging)
6. [verify_tool_result strukturiertes Parsing](#verify-tool-result-parsing)
7. [TD-1: agent.py Pipeline-Extraktion](#td-1-agent-refactoring)
8. [TD-5: ws_handler.py Aufteilung](#td-5-ws-handler-split)
9. [TD-2: config.py Sub-Model-Gruppierung](#td-2-config-submodels)
10. [TD-3: Token-Schätzung durch tiktoken ersetzen](#td-3-tiktoken)

---

## Sprint 1 — Korrektheit & Sicherheit (Woche 1)

---

### N-1: configure_runtime() Guard

**Problem:** `_configure_lock` (asyncio.Lock) existiert, wird aber nie in `run()` oder `configure_runtime()` tatsächlich acquired. Der Guard beruht nur auf dem synchronen `_active_run_count`-Zähler und dem `_reconfiguring`-Flag — beides ist nicht Thread-/Task-safe bei concurrent awaits.

**Ist-Zustand** ([agent.py](backend/app/agent.py#L347-L377)):

```python
def configure_runtime(self, base_url: str, model: str) -> None:
    # H-6: guard — reject reconfiguration while run() calls are in flight
    if self._active_run_count > 0:
        raise RuntimeError(
            f"configure_runtime() abgewiesen: {self._active_run_count} aktive(r) "
            "run()-Aufruf/Aufrufe. Bitte warten und erneut versuchen."
        )
    self._reconfiguring = True
    try:
        self.client = LlmClient(base_url=base_url, model=model)
        # ... ReflectionService + Sub-Agent reconfiguration ...
    finally:
        self._reconfiguring = False
```

Und in `run()` ([agent.py](backend/app/agent.py#L456-L478)):

```python
async def run(self, user_message: str, send_event: SendEvent, session_id: str, ...):
    self._refresh_long_term_memory_store()
    # H-6: guard — refuse to start if configure_runtime() is mid-flight
    if self._reconfiguring:
        raise RuntimeError(
            "run() abgewiesen: Agent wird gerade rekonfiguriert. Bitte erneut versuchen."
        )
    self._active_run_count += 1
    # ... pipeline ...
    # finally:
    #     self._active_run_count -= 1
```

**Soll-Zustand:**

```python
async def configure_runtime(self, base_url: str, model: str) -> None:
    async with self._configure_lock:
        if self._active_run_count > 0:
            raise RuntimeError(
                f"configure_runtime() abgewiesen: {self._active_run_count} aktive(r) "
                "run()-Aufruf/Aufrufe. Bitte warten und erneut versuchen."
            )
        self._reconfiguring = True
        try:
            self.client = LlmClient(base_url=base_url, model=model)
            self._reflection_service = (
                ReflectionService(...)
                if settings.reflection_enabled
                else None
            )
            self.planner_agent.configure_runtime(base_url=base_url, model=model)
            self.synthesizer_agent.configure_runtime(base_url=base_url, model=model)
        finally:
            self._reconfiguring = False


async def run(self, user_message: str, send_event: SendEvent, ...):
    self._refresh_long_term_memory_store()
    async with self._configure_lock:
        if self._reconfiguring:
            raise RuntimeError(
                "run() abgewiesen: Agent wird gerade rekonfiguriert."
            )
        self._active_run_count += 1
    try:
        # ... pipeline ...
    finally:
        self._active_run_count -= 1
```

#### Dos

- `configure_runtime()` auf `async def` umstellen, damit `async with self._configure_lock` möglich ist
- Lock nur **kurz** halten: in `run()` nur um den Counter-Increment herum, nicht um die gesamte Pipeline
- Alle Aufrufer von `configure_runtime()` aktualisieren (z.B. `ws_handler.py`, REST-Endpunkte) auf `await agent.configure_runtime(...)`

#### Don'ts

- **NICHT** die gesamte `run()`-Pipeline innerhalb des Locks ausführen — das serialisiert alle Requests
- **NICHT** den `_active_run_count` ohne Lock inkrementieren und separat prüfen — das erzeugt TOCTOU-Races
- **NICHT** `threading.Lock` verwenden — der Code ist async, nur `asyncio.Lock` ist korrekt

#### Akzeptanzkriterien

- [ ] `configure_runtime()` ist `async def` und verwendet `async with self._configure_lock`
- [ ] `run()` acquired `_configure_lock` nur für den Guard-Check + Counter-Increment (≤ 5 Zeilen)
- [ ] Alle Aufrufer von `configure_runtime()` verwenden `await`
- [ ] Bestehender Test `test_agent_runtime_reconfigure.py` läuft grün
- [ ] Neuer Test: 2 concurrent `run()` Aufrufe + 1 `configure_runtime()` → `RuntimeError` wird geworfen
- [ ] Neuer Test: `configure_runtime()` nach Abschluss aller `run()`-Aufrufe → Erfolg

---

### N-3: LLM-Client exponentielles Backoff + Jitter

**Problem:** Der Backoff war ursprünglich linear. Es wurde bereits korrigiert, aber die Implementierung sollte verifiziert und abgesichert werden.

**Ist-Zustand** ([llm_client.py](backend/app/llm_client.py#L1-L29)):

```python
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 0.8
RETRY_MAX_DELAY_SECONDS = 30.0


def _retry_delay(attempt: int) -> float:
    """Exponentielles Backoff: base * 2^(attempt-1), gekappt auf max, +20%-Jitter."""
    delay = min(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_DELAY_SECONDS)
    delay += random.uniform(0.0, delay * 0.2)
    return delay
```

Retry-Schleife ([llm_client.py](backend/app/llm_client.py#L111-L130)):

```python
for attempt in range(1, MAX_RETRIES + 1):
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                body = await response.aread()
                body_text = body.decode(errors='ignore')
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                    await asyncio.sleep(_retry_delay(attempt))
                    continue
                raise LlmClientError(...)
```

**Status:** Die Formel ist korrekt exponentiell. Verbleibende Verbesserung: den `httpx.AsyncClient` **außerhalb** der Retry-Schleife erstellen, um Connection-Pooling zu nutzen.

**Soll-Zustand:**

```python
for attempt in range(1, MAX_RETRIES + 1):
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # ... request ...
    except httpx.TimeoutException:
        if attempt < MAX_RETRIES:
            await asyncio.sleep(_retry_delay(attempt))
            continue
        raise
```

Besser noch — Client außerhalb:

```python
async with httpx.AsyncClient(timeout=120) as client:
    for attempt in range(1, MAX_RETRIES + 1):
        async with client.stream("POST", url, ...) as response:
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                await asyncio.sleep(_retry_delay(attempt))
                continue
            # ... normal processing ...
```

#### Dos

- `httpx.AsyncClient` einmal erstellen und über alle Retry-Attempts wiederverwenden
- Auch `httpx.TimeoutException` / `httpx.HTTPError` in die Retry-Logik aufnehmen
- Beide Streams (OpenAI-kompatibel + Ollama-native) konsistent behandeln

#### Don'ts

- **NICHT** `random.uniform` durch `time.sleep` ersetzen — der Code ist async
- **NICHT** Jitter auf `> 50%` setzen — das verfälscht die Backoff-Kurve
- **NICHT** `MAX_RETRIES` global hochsetzen ohne Rate-Limit-Budget zu prüfen

#### Akzeptanzkriterien

- [ ] `_retry_delay()` erzeugt für Attempt 1/2/3: ~0.8s / ~1.6s / ~3.2s (±20% Jitter)
- [ ] `httpx.AsyncClient` wird pro Aufruf nur einmal instantiiert, nicht pro Retry-Attempt
- [ ] Beide Stream-Methoden (`_stream_chat_completion`, `_stream_chat_completion_ollama`) verwenden identische Retry-Logik
- [ ] Bestehende Tests in `test_llm_client.py` (falls vorhanden) laufen grün
- [ ] Unit-Test: Mock-Server antwortet 3× 429 → Client wirft `LlmClientError` nach 3 Attempts
- [ ] Unit-Test: Mock-Server antwortet 1× 429, dann 200 → Client gibt Token-Stream zurück

---

### TD-6: Coverage-Pipeline aktivieren

**Problem:** `coverage.json` existiert, ist aber leer — kein persistierter Nachweis der Testabdeckung.

**Ist-Zustand:** `backend/coverage.json` ist eine leere Datei.

**Soll-Zustand:** `pytest` mit `--cov` Flag in CI-/Dev-Pipeline aktivieren.

```powershell
# In start-test.ps1 / pytest.ini:
python -m pytest --cov=app --cov-report=json:coverage.json --cov-report=term-missing backend/tests/
```

Oder in [pytest.ini](pytest.ini):

```ini
[pytest]
addopts = --cov=app --cov-report=json:backend/coverage.json --cov-report=term-missing
```

#### Dos

- Coverage-Gates aus `TEST_BASELINE.md` als `--cov-fail-under=70` setzen
- JSON-Report für CI-Parsing generieren

#### Don'ts

- **NICHT** Coverage-Reporting in Produktions-Code einbauen
- **NICHT** `coverage.json` in `.gitignore` eintragen — es ist der persistierte Nachweis

#### Akzeptanzkriterien

- [ ] `python -m pytest` generiert automatisch `backend/coverage.json` mit echten Daten
- [ ] Coverage ≥ 70% global (Gate aus `TEST_BASELINE.md`)
- [ ] `coverage.json` enthält mindestens `totals.percent_covered`

---

## Sprint 2 — Performance & Stabilität (Woche 2)

---

### N-2: LTM-Refresh-Flag statt per-run Check

**Problem:** `_refresh_long_term_memory_store()` wird bei **jedem** `run()`-Aufruf ausgeführt. Bei hohem Durchsatz entsteht unnötiger Overhead durch wiederholte Path-Checks und Early-Return-Logik.

**Ist-Zustand** ([agent.py](backend/app/agent.py#L382-L425)):

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
        if self._long_term_memory is None and self._failure_retriever is None:
            return
        _clear_all()
        return

    configured_path = str(getattr(settings, "long_term_memory_db_path", "") or "").strip()
    if not configured_path:
        if self._long_term_memory is None and self._failure_retriever is None:
            return
        _clear_all()
        return

    if self._long_term_memory is not None and self._long_term_memory_db_path == configured_path:
        return

    try:
        self._long_term_memory = LongTermMemoryStore(configured_path)
        # ...
    except Exception:
        _clear_all()
```

**Soll-Zustand:**

```python
def _refresh_long_term_memory_store(self, *, force: bool = False) -> None:
    """Refresh LTM stores. Skips if already up-to-date unless force=True."""
    if not force and self._ltm_refresh_done:
        return
    # ... existing logic ...
    self._ltm_refresh_done = True
```

Dann in `__init__`:

```python
self._ltm_refresh_done = False
self._refresh_long_term_memory_store()
```

Und in `run()`:

```python
# Nur bei Settings-Änderung oder erstem Aufruf:
if not self._ltm_refresh_done:
    self._refresh_long_term_memory_store()
```

Und in `configure_runtime()`:

```python
self._ltm_refresh_done = False  # Force re-check on next run
```

#### Dos

- `_ltm_refresh_done`-Flag als Instanz-Variable einführen
- Flag bei `configure_runtime()` zurücksetzen, damit Setting-Änderungen wirken
- Flag bei Feature-Toggle-Änderung über REST-API zurücksetzen

#### Don'ts

- **NICHT** den Refresh komplett entfernen — er muss bei Configuration-Changes weiterhin ausgeführt werden
- **NICHT** den Refresh in einen Background-Task verschieben — die Initialisierung muss synchron vor dem ersten LLM-Aufruf abgeschlossen sein

#### Akzeptanzkriterien

- [ ] `_refresh_long_term_memory_store()` wird bei aufeinanderfolgenden `run()`-Aufrufen ohne Config-Änderung nur einmal ausgeführt
- [ ] Nach `configure_runtime()` wird der nächste `run()` den Refresh erneut durchführen
- [ ] Alle LTM-Tests (`test_long_term_memory.py`, `test_failure_journal.py`) laufen grün
- [ ] Feature-Toggle via REST erzwingt Refresh beim nächsten `run()`

---

### N-4: Exception-Logging in benchmark_calibration

**Problem:** `all_snapshots()` Exception wird zwar jetzt mit `exc_info=True` geloggt, aber der `_recommend_from_recovery_metrics`-Pfad schluckt Exceptions weiterhin still.

**Ist-Zustand** ([benchmark_calibration.py](backend/app/services/benchmark_calibration.py#L71-L130)):

```python
def _recommend_from_model_health(self) -> list[CalibrationRecommendation]:
    tracker = self._model_health_tracker
    if tracker is None:
        return []

    snapshots = []
    try:
        snapshots = list(tracker.all_snapshots())
    except Exception:
        logger.debug("ModelHealthTracker.all_snapshots() failed", exc_info=True)
        snapshots = []
    # ...

def _recommend_from_recovery_metrics(self) -> list[CalibrationRecommendation]:
    metrics_path = self._recovery_metrics_path
    if metrics_path is None or not metrics_path.exists():
        return []

    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception:
        return []   # ← Silent swallow
```

**Soll-Zustand:**

```python
def _recommend_from_recovery_metrics(self) -> list[CalibrationRecommendation]:
    metrics_path = self._recovery_metrics_path
    if metrics_path is None or not metrics_path.exists():
        return []

    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug(
            "Recovery metrics file unreadable path=%s", metrics_path, exc_info=True
        )
        return []
```

#### Dos

- `logger.debug(..., exc_info=True)` verwenden — konsistent mit dem `all_snapshots()`-Pfad
- Pfad in die Log-Message aufnehmen für schnelle Diagnose

#### Don'ts

- **NICHT** auf `logger.warning` hochstufen — das sind erwartbare Situationen (leere Datei, keine Metrics)
- **NICHT** die Exception re-raisen — das bricht die Kalibrierungs-Pipeline

#### Akzeptanzkriterien

- [ ] Alle `except Exception: return []` in `benchmark_calibration.py` haben `logger.debug(..., exc_info=True)`
- [ ] Keine silent `return []` ohne Logging verbleibt
- [ ] Bestehende Tests laufen grün

---

### verify_tool_result strukturiertes Parsing

**Problem:** `verify_tool_result()` nutzt Regex-Muster für Error/OK-Erkennung. Das ist fragil bei unerwarteten Formaten.

**Ist-Zustand** ([verification_service.py](backend/app/services/verification_service.py#L120-L195)):

```python
_ERROR_PATTERN = re.compile(
    r"^(?:status\s*:\s*(?:error|failed)|\[error\]|\[[^\]]+\]\s*error(?:\b|$))",
    re.IGNORECASE | re.MULTILINE,
)
_OK_PATTERN = re.compile(
    r"^(?:status\s*:\s*ok|\[ok\]|\[[^\]]+\]\s*ok(?:\b|$))",
    re.IGNORECASE | re.MULTILINE,
)

def verify_tool_result(self, *, plan_text: str, tool_results: str) -> VerificationResult:
    normalized_results = (tool_results or "").strip()
    if not normalized_results:
        return VerificationResult(status="warning", reason="empty_tool_results", ...)

    has_error = bool(self._ERROR_PATTERN.search(normalized_results))
    has_ok = bool(self._OK_PATTERN.search(normalized_results))
    if has_error and not has_ok:
        return VerificationResult(status="warning", reason="tool_results_error_only", ...)

    return VerificationResult(status="ok", reason="tool_results_usable", ...)
```

**Soll-Zustand:**

```python
@dataclass(frozen=True)
class ToolResultSignals:
    error_count: int
    ok_count: int
    structured_blocks: int  # Anzahl erkannter [tool_name] Blöcke

def _extract_tool_result_signals(self, tool_results: str) -> ToolResultSignals:
    """Parse tool results into structured signals."""
    blocks = re.findall(r"^\[([^\]]+)\]", tool_results, re.MULTILINE)
    error_count = len(self._ERROR_PATTERN.findall(tool_results))
    ok_count = len(self._OK_PATTERN.findall(tool_results))
    return ToolResultSignals(
        error_count=error_count,
        ok_count=ok_count,
        structured_blocks=len(blocks),
    )

def verify_tool_result(self, *, plan_text: str, tool_results: str) -> VerificationResult:
    normalized_results = (tool_results or "").strip()
    if not normalized_results:
        return VerificationResult(status="warning", reason="empty_tool_results", ...)

    signals = self._extract_tool_result_signals(normalized_results)

    if signals.error_count > 0 and signals.ok_count == 0:
        return VerificationResult(
            status="warning",
            reason="tool_results_error_only",
            details={
                "error_count": signals.error_count,
                "structured_blocks": signals.structured_blocks,
                "plan_chars": len(plan_text or ""),
                "tool_result_chars": len(normalized_results),
            },
        )

    return VerificationResult(
        status="ok",
        reason="tool_results_usable",
        details={
            "error_count": signals.error_count,
            "ok_count": signals.ok_count,
            "structured_blocks": signals.structured_blocks,
            "plan_chars": len(plan_text or ""),
            "tool_result_chars": len(normalized_results),
        },
    )
```

#### Dos

- Signale in ein Dataclass extrahieren für Testbarkeit
- `findall` statt `search` verwenden, um Mengenangaben zu erhalten
- Details-Dict um `error_count`, `ok_count`, `structured_blocks` erweitern

#### Don'ts

- **NICHT** die Regex-Muster komplett ersetzen — sie sind nach Bug-3.2 korrekt zeilenverankert
- **NICHT** LLM-basierte Verifikation hier einführen — das gehört in den `ReflectionService`
- **NICHT** `verify_tool_result` als breaking Change umbauen — die Signatur bleibt `(plan_text, tool_results) → VerificationResult`

#### Akzeptanzkriterien

- [ ] `ToolResultSignals` Dataclass existiert und ist importierbar
- [ ] `verify_tool_result()` gibt `error_count` und `ok_count` in `details` zurück
- [ ] Alle bestehenden Tests in `test_verification_service.py` laufen grün
- [ ] Neuer Test: Ergebnisse mit gemischten Error/OK-Blöcken erzeugen korrekte Counts

---

## Sprint 3 — Wartbarkeit (Wochen 3–4)

---

### TD-1: agent.py Pipeline-Extraktion

**Problem:** `agent.py` hat 2924 Zeilen. Die `run()`-Methode allein umfasst ~1000 Zeilen mit eingebetteten Pipeline-Steps.

**Ist-Zustand:** Alles in einer Datei:

```
backend/app/agent.py (2924 Zeilen)
├── HeadAgent.__init__()          ~180 Zeilen
├── HeadAgent.run()               ~1000 Zeilen (!)
│   ├── Guardrails               ~15 Zeilen
│   ├── Tool Policy Resolution   ~25 Zeilen
│   ├── Toolchain Check          ~12 Zeilen
│   ├── Memory Update            ~35 Zeilen
│   ├── Context Reduction        ~65 Zeilen
│   ├── Clarification Protocol   ~60 Zeilen
│   ├── Planning + Verification  ~70 Zeilen
│   ├── Replan Loop              ~120 Zeilen
│   ├── Tool Result Verification ~20 Zeilen
│   ├── Blocked/Interrupted      ~100 Zeilen
│   ├── Web Research Fallback    ~50 Zeilen
│   ├── Context Guard            ~25 Zeilen
│   ├── Synthesis                ~30 Zeilen
│   ├── Reflection Loop          ~90 Zeilen
│   ├── Evidence Gates           ~35 Zeilen
│   ├── Reply Shaping            ~40 Zeilen
│   ├── Orchestration Evidence   ~30 Zeilen
│   ├── Final Verification      ~30 Zeilen
│   ├── Final Emit              ~60 Zeilen
│   └── Exception + Finally     ~60 Zeilen
├── _execute_tools()              ~100 Zeilen (Proxy-Closures)
├── Helper-Methoden               ~1600 Zeilen
```

**Soll-Zustand: Neue Modulstruktur:**

```
backend/app/
├── agent.py                     (~500 Zeilen — nur Klasse + run() als Dispatcher)
├── pipeline/
│   ├── __init__.py
│   ├── types.py                 (RunContext Dataclass)
│   ├── guardrails_step.py       (~40 Zeilen)
│   ├── policy_step.py           (~50 Zeilen)
│   ├── memory_step.py           (~60 Zeilen)
│   ├── planning_step.py         (~100 Zeilen)
│   ├── tool_loop_step.py        (~200 Zeilen)
│   ├── synthesis_step.py        (~80 Zeilen)
│   ├── reflection_step.py       (~120 Zeilen)
│   ├── reply_shaping_step.py    (~80 Zeilen)
│   ├── verification_step.py     (~60 Zeilen)
│   └── finalization_step.py     (~80 Zeilen)
```

**Realer Code-Beispiel — Extraktion des Guardrails-Steps:**

Vorher in `run()` ([agent.py](backend/app/agent.py#L494-L510)):

```python
        try:
            self._validate_guardrails(user_message=user_message, session_id=session_id, model=model)
            self._validate_tool_policy(tool_policy)
            await self._emit_lifecycle(
                send_event,
                stage="guardrails_passed",
                request_id=request_id,
                session_id=session_id,
            )
```

Nachher in `pipeline/guardrails_step.py`:

```python
from __future__ import annotations
from app.pipeline.types import RunContext


async def execute_guardrails(ctx: RunContext) -> None:
    """Validate input guardrails and tool policy."""
    ctx.agent._validate_guardrails(
        user_message=ctx.user_message,
        session_id=ctx.session_id,
        model=ctx.model,
    )
    ctx.agent._validate_tool_policy(ctx.tool_policy)
    await ctx.emit_lifecycle(stage="guardrails_passed")
```

**RunContext Dataclass** (`pipeline/types.py`):

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from app.agent import HeadAgent

SendEvent = Callable[[dict], Awaitable[None]]


@dataclass
class RunContext:
    agent: HeadAgent
    user_message: str
    send_event: SendEvent
    session_id: str
    request_id: str
    model: str | None
    tool_policy: dict | None
    prompt_mode: str | None
    should_steer_interrupt: Callable[[], bool] | None

    # Mutable pipeline state
    plan_text: str = ""
    tool_results: str = ""
    final_text: str = ""
    status: str = "failed"
    error_text: str | None = None
    effective_allowed_tools: set[str] = field(default_factory=set)
    effective_prompt_mode: str = "full"
    budgets: dict[str, int] = field(default_factory=dict)
    memory_items: list = field(default_factory=list)
    memory_lines: list[str] = field(default_factory=list)
    synthesis_task_type: str = "general"

    async def emit_lifecycle(self, stage: str, details: dict | None = None) -> None:
        await self.agent._emit_lifecycle(
            self.send_event,
            stage=stage,
            request_id=self.request_id,
            session_id=self.session_id,
            details=details,
        )
```

**Refactored `run()` in agent.py:**

```python
async def run(self, user_message: str, send_event: SendEvent, ...) -> str:
    ctx = RunContext(
        agent=self, user_message=user_message, send_event=send_event,
        session_id=session_id, request_id=request_id, model=model,
        tool_policy=tool_policy, prompt_mode=prompt_mode,
        should_steer_interrupt=should_steer_interrupt,
    )
    self._refresh_long_term_memory_store()
    if self._reconfiguring:
        raise RuntimeError("run() abgewiesen: Agent wird gerade rekonfiguriert.")
    self._active_run_count += 1
    try:
        await execute_guardrails(ctx)
        await execute_policy_resolution(ctx)
        await execute_memory_update(ctx)
        await execute_planning(ctx)
        await execute_tool_loop(ctx)
        await execute_synthesis(ctx)
        await execute_reflection(ctx)
        await execute_reply_shaping(ctx)
        await execute_verification(ctx)
        await execute_finalization(ctx)
        ctx.status = "completed"
        return ctx.final_text
    except Exception as exc:
        ctx.error_text = str(exc)
        raise
    finally:
        self._active_run_count -= 1
```

#### Dos

- `RunContext` als einziges State-Objekt durch die Pipeline reichen
- Jeder Step bekommt **nur** `ctx: RunContext` als Argument
- Steps als **Module-Level-Funktionen** (nicht Klassen) — einfach, testbar, kein Overhead
- `TYPE_CHECKING`-Guard für `HeadAgent`-Import verwenden, um Circular-Imports zu vermeiden
- Step-für-Step extrahieren, nach jedem einzelnen Step Tests laufen lassen

#### Don'ts

- **NICHT** alle Steps gleichzeitig extrahieren — einen nach dem anderen, mit grüner Test-Suite dazwischen
- **NICHT** `RunContext` als God-Object designen — nur Pipeline-State, keine Business-Logic
- **NICHT** die Step-Executor-Klassen (`PlannerStepExecutor`, etc.) ersetzen — sie bleiben als Sub-Agent-Wrapper bestehen
- **NICHT** die Signatur von `HeadAgent.run()` ändern — sie ist das öffentliche API
- **NICHT** Helper-Methoden aus `HeadAgent` parallel verschieben — erst die `run()`-Pipeline, dann in einem zweiten Schritt die Helpers

#### Akzeptanzkriterien

- [ ] `agent.py` hat ≤ 800 Zeilen (aktuell 2924)
- [ ] `backend/app/pipeline/` existiert mit mindestens 8 Step-Modulen
- [ ] `RunContext` Dataclass ist in `pipeline/types.py` definiert
- [ ] Jeder Step hat mindestens einen Unit-Test
- [ ] Alle 82 bestehenden Test-Dateien laufen grün
- [ ] `run()` liest sich als lineare Abfolge von Step-Aufrufen (≤ 40 Zeilen im Try-Block)
- [ ] Keine Circular-Imports

---

### TD-5: ws_handler.py Aufteilung

**Problem:** `ws_handler.py` hat 1428 Zeilen. Message-Dispatch, Event-Emission, Lifecycle-Tracking und Disconnect-Handling sind in einer Funktion verschachtelt.

**Ist-Zustand** — alles in `handle_ws_agent()`:

Protocol-Interfaces ([ws_handler.py](backend/app/ws_handler.py#L36-L80)):

```python
class RuntimeManagerLike(Protocol):
    def get_state(self) -> RuntimeStateLike: ...
    async def switch_runtime(self, ...) -> RuntimeStateLike: ...
    async def ensure_model_ready(self, ...) -> str: ...

class StateStoreLike(Protocol):
    def init_run(self, ...) -> None: ...
    def set_task_status(self, ...) -> None: ...

class AgentLike(Protocol):
    name: str
    def configure_runtime(self, ...) -> None: ...
```

Message-Dispatch-Loop ([ws_handler.py](backend/app/ws_handler.py#L624-L700)):

```python
try:
    while True:
        request_id = str(uuid.uuid4())
        session_id = connection_session_id
        try:
            raw = await websocket.receive_text()
            inbound_type = peek_ws_inbound_type(raw)
            if inbound_type not in SUPPORTED_WS_INBOUND_TYPES:
                envelope = WsInboundEnvelope.model_validate_json(raw)
                # ... unsupported type handling ...
                continue

            data = parse_ws_inbound_message(raw)
            session_id = data.session_id or connection_session_id

            if data.type == "policy_decision":
                # ... policy handling ...
                continue
```

Error-Dispatch ([ws_handler.py](backend/app/ws_handler.py#L1300-L1420)):

```python
        except (WebSocketDisconnect, ClientDisconnectedError):
            deps.logger.info("ws_disconnected session_id=%s", session_id)
            break
        except PolicyApprovalCancelledError as exc:
            # ... 8 Zeilen ...
        except GuardrailViolation as exc:
            # ... 12 Zeilen ...
        except ToolExecutionError as exc:
            # ... 12 Zeilen ...
        except RuntimeSwitchError as exc:
            # ... 12 Zeilen ...
        except LlmClientError as exc:
            # ... 12 Zeilen ...
        except Exception as exc:
            # ... 15 Zeilen ...
```

**Soll-Zustand: Neue Modulstruktur:**

```
backend/app/
├── ws_handler.py                  (~250 Zeilen — Einstiegspunkt + Message-Loop)
├── ws/
│   ├── __init__.py
│   ├── types.py                   (WsConnectionContext Dataclass)
│   ├── event_emitter.py           (~80 Zeilen — send_event, send_lifecycle)
│   ├── message_router.py          (~200 Zeilen — Inbound-Type-Dispatch)
│   ├── error_handler.py           (~120 Zeilen — Exception→Event-Mapping)
│   ├── lifecycle_manager.py       (~100 Zeilen — session_workers, cleanup)
│   └── policy_handler.py          (~60 Zeilen — policy_decision Flow)
```

**Beispiel-Extraktion — Error-Handler:**

```python
# ws/error_handler.py
from __future__ import annotations
from app.errors import (
    ClientDisconnectedError, GuardrailViolation,
    LlmClientError, PolicyApprovalCancelledError,
    RuntimeSwitchError, ToolExecutionError,
)
from app.orchestrator.events import classify_error
from app.ws.types import WsConnectionContext


_ERROR_MAP: dict[type, tuple[str, str]] = {
    PolicyApprovalCancelledError: ("request_cancelled", "policy_approval_cancelled"),
    GuardrailViolation: ("request_failed_guardrail", "Guardrail blocked request"),
    ToolExecutionError: ("request_failed_toolchain", "Toolchain error"),
    RuntimeSwitchError: ("runtime_switch_failed", "Runtime switch error"),
    LlmClientError: ("request_failed_llm", "LLM error"),
}


async def handle_request_error(ctx: WsConnectionContext, exc: Exception) -> bool:
    """Handle request-level exceptions. Returns True if loop should break."""
    if isinstance(exc, (WebSocketDisconnect, ClientDisconnectedError)):
        ctx.deps.logger.info("ws_disconnected session_id=%s", ctx.session_id)
        return True  # break loop

    for exc_type, (stage, prefix) in _ERROR_MAP.items():
        if isinstance(exc, exc_type):
            ctx.deps.state_mark_failed_safe(run_id=ctx.request_id, error=str(exc))
            await ctx.send_event({
                "type": "error" if exc_type != PolicyApprovalCancelledError else "status",
                "agent": ctx.deps.agent.name,
                "message": f"{prefix}: {exc}" if prefix != "policy_approval_cancelled" else str(exc),
                "error_category": classify_error(exc),
            })
            await ctx.send_lifecycle(stage=stage, details={"error": str(exc)})
            return False

    # Fallback: unknown exception
    ctx.deps.state_mark_failed_safe(run_id=ctx.request_id, error=str(exc))
    ctx.deps.logger.exception("ws_unhandled_error request_id=%s", ctx.request_id)
    await ctx.send_event({
        "type": "error",
        "agent": ctx.deps.agent.name,
        "message": f"Request error: {exc}",
        "error_category": classify_error(exc),
    })
    return False
```

#### Dos

- `WsConnectionContext` als State-Container für die WebSocket-Verbindung einführen
- Protocol-Interfaces (`RuntimeManagerLike`, etc.) in `ws/types.py` verschieben
- Jeden except-Block in eine `handle_*`-Funktion extrahieren
- Die Haupt-Schleife in `ws_handler.py` bleibt als dünner Dispatcher

#### Don'ts

- **NICHT** die Signatur von `handle_ws_agent()` ändern — sie wird von `main.py` aufgerufen
- **NICHT** WebSocket-State (`pending_clarifications`, `session_workers`, etc.) in die Module verstreuen — alles gehört in `WsConnectionContext`
- **NICHT** die Protocol-Interfaces in Concrete-Klassen umwandeln — Protocol ermöglicht Dependency-Inversion ohne Vererbung
- **NICHT** die `send_event`-Closure aufbrechen — sie hält den `sequence_number`-State

#### Akzeptanzkriterien

- [ ] `ws_handler.py` hat ≤ 400 Zeilen
- [ ] `backend/app/ws/` existiert mit mindestens 4 Modulen
- [ ] `WsConnectionContext` ist in `ws/types.py` definiert
- [ ] `handle_ws_agent()` Signatur ist unverändert
- [ ] Alle bestehenden WS-Tests laufen grün
- [ ] Error-Handling ist in `ws/error_handler.py` konsolidiert

---

### TD-2: config.py Sub-Model-Gruppierung

**Problem:** `config.py` hat 1148 Zeilen mit ~200+ flachen Feldern in einer einzigen `Settings`-Klasse. Navigation und Zuordnung sind schwierig.

**Ist-Zustand** ([config.py](backend/app/config.py#L400-L480)):

```python
class Settings(BaseModel):
    # ... 400 Zeilen davor ...
    workspace_root: str = _resolve_workspace_root(os.getenv("WORKSPACE_ROOT"))
    memory_max_items: int = int(os.getenv("MEMORY_MAX_ITEMS", "30"))
    memory_persist_dir: str = _resolve_path_from_workspace(...)
    memory_reset_on_startup: bool = _parse_bool_env("MEMORY_RESET_ON_STARTUP", ...)
    orchestrator_state_dir: str = _resolve_path_from_workspace(...)
    orchestrator_state_backend: str = os.getenv("ORCHESTRATOR_STATE_BACKEND", "file")
    custom_agents_dir: str = _resolve_path_from_workspace(...)
    skills_dir: str = _resolve_path_from_workspace(...)
    skills_engine_enabled: bool = _parse_bool_env("SKILLS_ENGINE_ENABLED", False)
    skills_canary_enabled: bool = _parse_bool_env("SKILLS_CANARY_ENABLED", False)
    skills_canary_agent_ids: list[str] = _parse_csv_env(...)
    skills_canary_model_profiles: list[str] = _parse_csv_env(...)
    skills_mandatory_selection: bool = _parse_bool_env("SKILLS_MANDATORY_SELECTION", False)
    skills_max_discovered: int = int(os.getenv("SKILLS_MAX_DISCOVERED", "150"))
    skills_max_prompt_chars: int = int(os.getenv("SKILLS_MAX_PROMPT_CHARS", "30000"))
    # ... 600+ weitere Zeilen ...
```

**Soll-Zustand:** Gruppierung in Sub-Models:

```python
class MemorySettings(BaseModel):
    max_items: int = int(os.getenv("MEMORY_MAX_ITEMS", "30"))
    persist_dir: str = ...
    reset_on_startup: bool = ...

class SkillsSettings(BaseModel):
    engine_enabled: bool = _parse_bool_env("SKILLS_ENGINE_ENABLED", False)
    canary_enabled: bool = _parse_bool_env("SKILLS_CANARY_ENABLED", False)
    canary_agent_ids: list[str] = ...
    max_discovered: int = 150
    max_prompt_chars: int = 30000

class OrchestratorSettings(BaseModel):
    state_dir: str = ...
    state_backend: str = "file"
    state_reset_on_startup: bool = ...

class LlmSettings(BaseModel):
    base_url: str = ...
    model: str = ...
    timeout: int = 120
    max_retries: int = 3

class Settings(BaseModel):
    memory: MemorySettings = MemorySettings()
    skills: SkillsSettings = SkillsSettings()
    orchestrator: OrchestratorSettings = OrchestratorSettings()
    llm: LlmSettings = LlmSettings()
    # ... globale Felder ...
```

**Migration:** Alias-Properties für Rückwärtskompatibilität:

```python
class Settings(BaseModel):
    memory: MemorySettings = MemorySettings()

    @property
    def memory_max_items(self) -> int:
        """Backward-compatible alias. Prefer settings.memory.max_items."""
        return self.memory.max_items

    @property
    def memory_persist_dir(self) -> str:
        return self.memory.persist_dir
```

#### Dos

- Sub-Models als `BaseModel` definieren, nicht als `dataclass` — konsistent mit Pydantic-Settings
- Rückwärtskompatible `@property`-Aliase für alle bestehenden Zugriffe einführen
- Sub-Model-Gruppen an semantischen Grenzen ausrichten: `memory`, `skills`, `orchestrator`, `llm`, `security`, `pipeline`, `reflection`, `benchmark`
- Schrittweise migrieren: erst Sub-Models einführen, dann Consumer umstellen, dann Aliase entfernen

#### Don'ts

- **NICHT** alle Consumer gleichzeitig umstellen — das erzeugt einen Mega-Commit
- **NICHT** die Env-Var-Namen ändern — `MEMORY_MAX_ITEMS` bleibt `MEMORY_MAX_ITEMS`
- **NICHT** `model_config` per Sub-Model konfigurieren — die globale `.env`-Loading-Strategie muss konsistent bleiben
- **NICHT** Validatoren aus der Hauptklasse in Sub-Models verschieben, wenn sie Cross-Field-Dependencies haben

#### Akzeptanzkriterien

- [ ] Mindestens 4 Sub-Model-Gruppen existieren (`MemorySettings`, `SkillsSettings`, `OrchestratorSettings`, `LlmSettings`)
- [ ] Jedes Sub-Model hat < 30 Felder
- [ ] Alle bestehenden `settings.xxx`-Zugriffe funktionieren weiterhin über `@property`-Aliase
- [ ] `test_config_validation.py` läuft grün
- [ ] `config.py` hat ≤ 1200 Zeilen (durch Sub-Model-Auslagerung in separate Dateien sinkt es auf ~600)

---

### TD-3: Token-Schätzung durch tiktoken ersetzen

**Problem:** Die Token-Schätzung nutzt Regex-basiertes Wort-Counting, das bei CJK, Emoji und Code-Blöcken ungenau ist.

**Ist-Zustand** ([context_reducer.py](backend/app/state/context_reducer.py#L1-L35)):

```python
class ContextReducer:
    TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.TOKEN_PATTERN.findall(text))
```

Und als separate Utility ([tools_handlers.py](backend/app/handlers/tools_handlers.py#L339-L345)):

```python
def _estimate_tokens_from_chars(chars: int) -> int:
    if chars <= 0:
        return 0
    return max(1, int(round(chars / 4.0)))
```

**Problem-Analyse:**
- `r"\w+|[^\w\s]"` zählt jedes CJK-Zeichen als eigenes Wort, aber GPT-Tokenizer teilen anders
- Emoji-Sequenzen werden als einzelne Matches gezählt
- Code mit vielen Symbolen (`{`, `}`, `(`, `)`) wird massiv überschätzt

**Soll-Zustand:**

```python
# backend/app/services/token_estimator.py
from __future__ import annotations

import logging
import re
from typing import Protocol

logger = logging.getLogger(__name__)

_FALLBACK_PATTERN = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)


class TokenEstimator(Protocol):
    def count(self, text: str) -> int: ...


class TiktokenEstimator:
    """tiktoken-based estimator. Falls back to regex if tiktoken is unavailable."""

    def __init__(self, model: str = "gpt-4"):
        try:
            import tiktoken
            self._enc = tiktoken.encoding_for_model(model)
            self._available = True
        except Exception:
            logger.info("tiktoken unavailable, falling back to regex estimator")
            self._enc = None
            self._available = False

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._available and self._enc is not None:
            return len(self._enc.encode(text))
        return len(_FALLBACK_PATTERN.findall(text))


class RegexEstimator:
    """Regex-based fallback (current implementation)."""

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(_FALLBACK_PATTERN.findall(text))
```

Dann in `ContextReducer`:

```python
from app.services.token_estimator import TiktokenEstimator, TokenEstimator

class ContextReducer:
    def __init__(self, estimator: TokenEstimator | None = None):
        self._estimator = estimator or TiktokenEstimator()

    def estimate_tokens(self, text: str) -> int:
        return self._estimator.count(text)
```

#### Dos

- `tiktoken` als **optionale** Dependency in `requirements.txt` deklarieren (mit Fallback)
- Protocol-basierte `TokenEstimator`-Abstraction einführen
- Graceful Fallback: wenn `tiktoken` nicht installiert ist, Regex-Variante nutzen
- `_estimate_tokens_from_chars()` in `tools_handlers.py` ebenfalls auf den Estimator umstellen

#### Don'ts

- **NICHT** `tiktoken` als harte Dependency erzwingen — Ollama-Nutzer haben ggf. keine OpenAI-Packages
- **NICHT** den Estimator pro Token-Schätzung instantiieren — einmal im `ContextReducer.__init__` ist genug
- **NICHT** den Encoding-Name hartcodieren — Model abhängig machen oder konfigurierbar

#### Akzeptanzkriterien

- [ ] `backend/app/services/token_estimator.py` existiert mit `TiktokenEstimator` und `RegexEstimator`
- [ ] `ContextReducer` akzeptiert einen optionalen `TokenEstimator` im Constructor
- [ ] Bei fehlendem `tiktoken` Package: Fallback auf Regex ohne Exception
- [ ] Test: CJK-Text (`"你好世界"`) liefert mit tiktoken ~4 Tokens, mit Regex ~4 Matches (beide akzeptabel)
- [ ] Test: Langer Code-Block liefert mit tiktoken eine Abweichung von < 20% zu echtem OpenAI-Token-Count
- [ ] `tiktoken` ist in `requirements.txt` als optionale Dependency (`tiktoken>=0.5.0; python_version>="3.9"`)
- [ ] Alle bestehenden Tests laufen grün mit und ohne `tiktoken` installiert

---

## Zusammenfassung

| # | Maßnahme | Sprint | Aufwand | Impact | Risiko |
|---|---------|--------|---------|--------|--------|
| 1 | N-1: configure_runtime() Guard | 1 | 1h | HIGH | NIEDRIG — isolierte Änderung |
| 2 | N-3: LLM-Client Backoff (bereits exponentiell — Client-Pooling) | 1 | 30min | MEDIUM | NIEDRIG |
| 3 | TD-6: Coverage-Pipeline | 1 | 10min | LOW | KEINE |
| 4 | N-2: LTM-Refresh-Flag | 2 | 30min | MEDIUM | NIEDRIG |
| 5 | N-4: Exception-Logging | 2 | 10min | LOW | KEINE |
| 6 | verify_tool_result Parsing | 2 | 1h | MEDIUM | NIEDRIG — abwärtskompatibel |
| 7 | TD-1: agent.py Pipeline-Extraktion | 3 | 4h | MEDIUM | MITTEL — viele abhängige Tests |
| 8 | TD-5: ws_handler.py Aufteilung | 3 | 3h | LOW | MITTEL |
| 9 | TD-2: config.py Sub-Models | 3 | 2h | LOW | NIEDRIG — @property-Aliase |
| 10 | TD-3: tiktoken Integration | 3 | 2h | LOW | NIEDRIG — Fallback vorhanden |

**Gesamtaufwand:** ~14h über 4 Wochen

---

*Generiert am 2026-03-05. Alle Code-Beispiele stammen aus der Live-Codebase, keine Annahmen.*
