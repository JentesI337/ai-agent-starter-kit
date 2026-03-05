# FIXROADTOGOLD — Review Findings

> Changeset-Review 2026-03-05. Codenahe Belege mit Datei + Zeilenverweis.

---

## HOCH — Architektur-Probleme

### F-1  Dreifach-duplizierte Error-Taxonomie (DRY-Verstoß)

Dieselben Regex-Patterns für Error-Klassifikation existieren **dreimal** im Codebase:

**Kopie 1 — `agent.py` Zeile 2795–2838:**

```python
# agent.py  (class-level attribute)
_RETRY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"timeout|ECONNRESET|ECONNREFUSED|connection refused|connection reset"
        r"|503 service unavailable|502 bad gateway|429 too many"
        r"|temporary|temporarily|try again|busy|rate.?limit",
        re.IGNORECASE,
    ), "transient"),
    (re.compile(
        r"command not found|not recognized as|is not recognized"
        r"|ModuleNotFoundError|No module named|ImportError"
        r"|'(\w+)' is not installed",
        re.IGNORECASE,
    ), "missing_dependency"),
    # … 3 weitere identische Blöcke
]
```

**Kopie 2 — `tool_retry_strategy.py` Zeile 40–96:**

```python
# tool_retry_strategy.py
_ERROR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"timeout|ECONNRESET|ECONNREFUSED|connection refused|connection reset"
        r"|503 service unavailable|502 bad gateway|429 too many"
        r"|temporary|temporarily|try again|busy|rate.?limit",
        re.IGNORECASE,
    ), "transient"),
    # … identisch + zusätzlich "crash"-Kategorie
]
```

**Kopie 3 — `tool_outcome_verifier.py` Zeile 29–93:**

```python
# tool_outcome_verifier.py
_COMMAND_ERROR_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(
        r"command not found|not recognized as|is not recognized"
        r"|'(\w+)' is not installed|No such file or directory.*bin/"
        r"|ModuleNotFoundError|No module named|ImportError",
        re.IGNORECASE,
    ), "missing_dependency", "Command or dependency not available"),
    # … identisch, nur 3-Tupel statt 2-Tupel
]
```

**Außerdem** hat `agent.py` eine eigene Methode `_classify_tool_error()` (Zeile 2840), die exakt dasselbe tut wie `ToolRetryStrategy.classify_error()` — Dead Code, da `_classify_tool_error` nirgends aufgerufen wird.

**Fix:** Ein gemeinsames `error_taxonomy.py`-Modul mit einer kanonischen Pattern-Liste. Alle drei Konsumenten importieren von dort.

---

### F-2  Class-Level-Attribute verursachen I/O beim Modul-Import

```python
# agent.py Zeile 2843–2844  (auf Class-Ebene, NICHT in __init__)
_retry_strategy = ToolRetryStrategy()
_platform = detect_platform()
```

`detect_platform()` führt ~20× `shutil.which()` aus (Shell, Package-Manager, Runtimes):

```python
# platform_info.py Zeile 105–125
def _detect_package_managers() -> tuple[str, ...]:
    candidates = [
        "pip", "pip3", "npm", "yarn", "pnpm", "cargo", "go", "gem",
        "apt", "apt-get", "brew", "choco", "winget", "scoop",
        "dnf", "yum", "pacman",
    ]
    for cmd in candidates:
        if shutil.which(cmd):     # <-- I/O bei jedem Import von agent.py
            found.append(cmd)
```

Da `_platform` ein **Class-Attribute** ist, wird dieser I/O-Block beim *Import* von `agent.py` ausgeführt — nicht erst bei Instanziierung. Das ist ein Seiteneffekt in Tests und beim Startup.

**Fix:** Verschieben in `__init__`:
```python
def __init__(self, ...):
    self._retry_strategy = ToolRetryStrategy()
    self._platform = detect_platform()
```

---

### F-3  Harte Import-Kaskade in `learning_loop.py`

```python
# learning_loop.py Zeile 33–35
from app.services.adaptive_tool_selector import AdaptiveToolSelector
from app.services.execution_pattern_detector import ExecutionPatternDetector, PatternAlert
from app.services.tool_knowledge_base import ToolKnowledgeBase
```

Diese drei Top-Level-Imports verursachen eine transitive Abhängigkeitskette:

```
tool_execution_manager.py
  └─ learning_loop.py
       ├─ adaptive_tool_selector.py
       ├─ execution_pattern_detector.py
       └─ tool_knowledge_base.py
```

Fehlschlag in *einer* dieser Dateien bricht den gesamten Import-Graph. `LearningLoop` instanziiert alle drei im `__init__`:

```python
# learning_loop.py Zeile 56–58
self._selector = selector or AdaptiveToolSelector()     # eager
self._kb = kb or ToolKnowledgeBase()                    # eager
self._detector = detector or ExecutionPatternDetector()  # eager
```

**Fix:** Lazy imports innerhalb von `__init__` oder Interface-Protokolle statt konkreter Klassen.

---

## MITTEL — Code Smells

### F-4  Thread-Safety-Lücke in `ToolTelemetry`

`span.close()` wird **außerhalb** des Locks aufgerufen:

```python
# tool_telemetry.py Zeile 143–158
def end_span(self, span: ToolSpan, *, status, ...):
    span.close(             # <-- mutable Mutation OHNE Lock
        status=status,
        error_category=error_category,
        ...
    )
    with self._lock:        # <-- Lock erst NACH der Mutation
        st = self._stats[span.tool]
        st.calls += 1
        ...
```

`ToolSpan` ist ein **mutable** Dataclass. Zwei parallele Tasks, die denselben Span schließen, verursachen eine Race Condition auf `end_ns`, `status`, etc.

**Fix:** `span.close()` innerhalb des `with self._lock:`-Blocks verschieben, oder `ToolSpan.close()` atomar machen.

---

### F-5  Telemetry-Span bleibt offen bei `CancelledError`

```python
# tool_execution_manager.py Zeile 1327–1331
_tel_span = self._telemetry.start_span(
    tool=tool, call_id=call_id, args=dict(evaluated_args),
)

try:                        # <-- Span wird hier geöffnet
    tool_started = monotonic()
    ...
    # end_span nur in success/error branches
```

`end_span` wird nur in den expliziten `except ToolExecutionError` und im Success-Branch aufgerufen. Ein `asyncio.CancelledError` oder unerwarteter `BaseException` verlässt den Block ohne den Span zu schließen → offener Span in der Telemetrie-Liste.

**Fix:** `end_span` in einem `finally`-Block:
```python
try:
    ...
except ToolExecutionError:
    self._telemetry.end_span(_tel_span, status="error", ...)
else:
    self._telemetry.end_span(_tel_span, status="ok", ...)
finally:
    if _tel_span.is_open:
        self._telemetry.end_span(_tel_span, status="cancelled")
```

---

### F-6  `exit_code`-Parameter in `ToolOutcomeVerifier` ist toter Code

```python
# tool_outcome_verifier.py Zeile 113–118
def verify(self, *, tool, result, args=None, exit_code: int | None = None):
    # exit_code wird NIRGENDS direkt ausgewertet
    ...
```

Der Parameter wird akzeptiert, aber nie gelesen. In `_verify_run_command` wird stattdessen der Exit-Code per Regex aus dem Ergebnis-Text geparst:

```python
# tool_outcome_verifier.py Zeile 208–215
exit_match = re.search(r"exit code[:\s]+(\d+)", lower)
if exit_match:
    code = int(exit_match.group(1))
```

Der Aufrufer `tool_execution_manager.py` übergibt `exit_code` nie:

```python
# tool_execution_manager.py Zeile 1394
outcome = self._outcome_verifier.verify(
    tool=tool, result=clipped, args=evaluated_args,
    # exit_code fehlt
)
```

**Fix:** Entweder `exit_code` an den Aufrufer weiterreichen und in `_verify_run_command` direkt nutzen, oder den Parameter entfernen.

---

### F-7  `_verify_write_tool` — Side-Effect im Verifier

```python
# tool_outcome_verifier.py Zeile 261–269
if args and tool == "write_file":
    target_path = args.get("file_path") or args.get("path") or args.get("filename")
    if isinstance(target_path, str) and os.path.isabs(target_path):
        if not os.path.isfile(target_path):     # <-- Dateisystem-I/O
            return OutcomeVerdict(
                status="suspicious",
                reason=f"write_file reported success but file not found: {target_path}",
```

Ein "Verifier" sollte deterministisch sein. `os.path.isfile()` ist ein Side-Effect und hat Race Conditions (Datei existiert zwischen Write und Verify, async-Execution, anderes CWD).

---

### F-8  Unused imports: `field` in zwei Dateien

```python
# tool_outcome_verifier.py Zeile 12
from dataclasses import dataclass, field   # `field` wird NICHT benutzt

# platform_info.py Zeile 14
from dataclasses import dataclass, field   # `field` wird NICHT benutzt
```

Beide `OutcomeVerdict` und `PlatformInfo` nutzen nur einfache Default-Werte, kein `field()`.

---

### F-9  `run_command` in `_TRANSIENT_RETRY_TOOLS` markiert

```python
# tool_registry.py Zeile 102–107
_TRANSIENT_RETRY_TOOLS: frozenset[str] = frozenset({
    "run_command",          # <-- Hat SIDE EFFECTS (schreibt Dateien, installiert Pakete)
    "web_fetch", "web_search", "http_request",
    "list_dir", "read_file", "file_search", "grep_search",
    ...
})
```

Der Kommentar darüber sagt: *"Tools that are safe to retry on transient errors (no side effects or idempotent)"*. `run_command` ist **nicht** idempotent — ein `npm install` oder `rm -rf` wird bei Retry erneut ausgeführt. Trotzdem bekommt es `retry_class="transient"` und mindestens 2 Retries.

---

## NIEDRIG — Stilistik / Härten

### F-10  `TOOL_PROFILES` nicht mit `ToolRegistry` synchronisiert

```python
# tool_policy.py Zeile 121–188
TOOL_PROFILES: dict[str, frozenset[str]] = {
    "full": frozenset({
        "list_dir", "read_file", "write_file", "run_command",
        "code_execute", "apply_patch", ...
        # Was ist mit MCP-Tools? Dynamischen Tools?
    }),
}
```

`TOOL_PROFILES["full"]` ist eine statische Liste. Wenn neue Tools per `ToolRegistry.register()` oder MCP-Discovery hinzukommen, fehlen sie im `"full"`-Profil. Kein Sync-Mechanismus vorhanden.

---

### F-11  Strings statt Enums/Literals für `retry_class`, `status`, `strategy`

```python
# tool_retry_strategy.py Zeile 19
strategy: str  # "backoff" | "escalate" | "replan" | "skip"

# tool_retry_strategy.py Zeile 138
if retry_class == "none":       # Typo "None" oder "NONE" → lautloser Fallback
```

Kein `Literal` oder `Enum` — Tippfehler in `retry_class` (z.B. `"transIent"`) führen lautlos zum catch-all-Pfad.

**Fix:** `Literal["transient", "timeout", "none"]` oder `StrEnum`.

---

### F-12  `go` als Package-Manager UND Runtime gelistet

```python
# platform_info.py Zeile 113
candidates = ["pip", ..., "go", ...]       # _detect_package_managers

# platform_info.py Zeile 133
candidates = [("go", "go"), ...]           # _detect_runtimes
```

Dieselbe Binary erscheint in `package_managers` und `installed_runtimes`. Semantisch fragwürdig — `go` ist ein Runtime/Build-Tool, kein Package-Manager (obwohl `go install` existiert).

---

### F-13  PII-Phone-Regex kann False Positives erzeugen

```python
# tool_result_context_guard.py Zeile 39–43
(re.compile(
    r"(?<!\d)(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)",
), "<REDACTED_PHONE>"),
```

Matcht jede Folge `XXXXXXXXXX` (10 Ziffern) in Logs, z.B. Dateigrößen, Timestamps, Memory-Adressen. Keine Kontextprüfung.

---

### F-14  `learning_loop.on_tool_outcome()` — stilles Verwerfen von `pitfall`

```python
# learning_loop.py Zeile 89
pitfall=pitfall if not success else "",     # Aufrufer-Wert wird ignoriert
```

Wenn der Aufrufer `pitfall="something"` mit `success=True` übergibt, wird der Wert stillschweigend verworfen. Das ist möglicherweise gewollt, aber der Aufrufer in `tool_execution_manager.py` übergibt `pitfall` nur bei Fehlern — Inkonsistenz zumindest konzeptionell.

---

### F-15  `install_hint` nie vom Aufrufer befüllt

```python
# learning_loop.py Zeile 72
install_hint: str = "",     # nie von tool_execution_manager.py gesetzt
```

```python
# tool_execution_manager.py Zeile 1431 (success) + 1706 (error)
self._learning_loop.on_tool_outcome(
    tool=tool,
    success=...,
    duration_ms=...,
    capability=...,
    args=dict(evaluated_args),
    # install_hint fehlt immer
)
```

Toter Parameter im aktuellen Nutzungskontext.

---

### F-16  Breaking Behaviour Change nicht als BREAKING markiert

```python
# test_head_agent_replan_policy.py Zeile 13
# D-11: mixed OK + ERROR → partial_error (was "usable" before D-11)
assert agent._classify_tool_results_state(
    "[read_file] OK\n[run_command] ERROR: blocked"
) == "partial_error"
```

Der alte Rückgabewert war `"usable"`, jetzt ist es `"partial_error"`. Externe Integrationen oder Monitoring, das auf `"usable"` filtert, brechen stillschweigend. Kein BREAKING-Tag im Commit.

---

## Zusammenfassung nach Priorität

| Prio | ID | Kurzbeschreibung |
|------|----|------------------|
| HOCH | F-1 | 3× duplizierte Error-Taxonomie + Dead Code `_classify_tool_error` |
| HOCH | F-2 | `detect_platform()` I/O bei Modul-Import (Class-Level-Attribut) |
| HOCH | F-3 | Harte Import-Kaskade in `learning_loop.py` |
| MITTEL | F-4 | Thread-Safety-Lücke: `span.close()` ohne Lock |
| MITTEL | F-5 | Telemetrie-Span bleibt bei CancelledError offen |
| MITTEL | F-6 | `exit_code`-Parameter nie ausgewertet (toter Code) |
| MITTEL | F-7 | Dateisystem-I/O in Verifier (Side-Effect) |
| MITTEL | F-8 | Unused import `field` in 2 Dateien |
| MITTEL | F-9 | `run_command` als "safe to retry" markiert — hat Side Effects |
| NIEDRIG | F-10 | `TOOL_PROFILES` nicht mit dynamischer Registry sync'd |
| NIEDRIG | F-11 | Strings statt Enums/Literals — typo-anfällig |
| NIEDRIG | F-12 | `go` doppelt in Package-Managers + Runtimes |
| NIEDRIG | F-13 | Phone-Regex false-positive-anfällig |
| NIEDRIG | F-14 | `pitfall` still verworfen bei `success=True` |
| NIEDRIG | F-15 | `install_hint` toter Parameter |
| NIEDRIG | F-16 | Breaking Behaviour Change ohne BREAKING-Tag |
