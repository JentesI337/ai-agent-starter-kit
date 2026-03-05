# Toolsplan — Full Command Control Implementation

> **Ziel:** Ein Agent der *jedes* denkbare Kommando autonom finden, installieren, ausführen,
> verifizieren, daraus lernen und bei Fehlern intelligent reagieren kann.
>
> **Autor:** AI-Agent-Starter-Kit Team
> **Stand:** 05.03.2026
> **Scope:** End-to-End von `ToolRetryStrategy` bis `SelfHealingLoop`

---

## Inhaltsverzeichnis

1. [Problemdefinition](#1-problemdefinition)
2. [Ist-Zustand: Stärken & Schwächen](#2-ist-zustand)
3. [Ziel-Zustand: Full Command Control](#3-ziel-zustand)
4. [Architektur-Entscheidungen](#4-architektur-entscheidungen)
5. [Level 1: Retry + Outcome + Telemetry](#5-level-1)
6. [Level 2: Discovery + Knowledge](#6-level-2)
7. [Level 3: Provisioning + Governance](#7-level-3)
8. [Level 4: Adaptive Intelligence](#8-level-4)
9. [Level 5: Full Autonomy](#9-level-5)
10. [Akzeptanzkriterien (global)](#10-akzeptanzkriterien)
11. [DOs — Was wir richtig machen müssen](#11-dos)
12. [DON'Ts — Was wir auf keinen Fall tun dürfen](#12-donts)
13. [Risiken & Mitigations](#13-risiken)
14. [Testing-Strategie](#14-testing-strategie)
15. [Migration & Backwards Compatibility](#15-migration)
16. [Metriken für Erfolg](#16-metriken)

---

## 1. Problemdefinition

### Das Kernproblem

Der Agent hat **18 statische Tools** und kann damit gut arbeiten. Aber sobald eine Aufgabe
ein *externes* Tool braucht (pandoc, ffmpeg, imagemagick, jq, terraform, kubectl, ...), passiert:

```
User: "Konvertiere diese Markdown-Datei in ein PDF"

Agent:
  → run_command("pandoc README.md -o output.pdf")
  → Error: "'pandoc' is not recognized as an internal or external command"
  → Agent gibt auf: "pandoc ist nicht installiert. Bitte installiere es manuell."
```

**Das ist inakzeptabel.** Ein autonomer Agent muss:
1. Erkennen dass ein Tool fehlt
2. Alternativen kennen oder finden
3. Das passende Tool installieren (mit Erlaubnis)
4. Den Befehl korrekt ausführen
5. Prüfen ob das Ergebnis stimmt
6. Bei Fehlern intelligent reagieren (nicht einfach aufgeben)
7. Für nächstes Mal merken was funktioniert hat

### Was "Full Command Control" bedeutet

| Situation | Heute | Ziel |
|---|---|---|
| Unbekanntes Tool | Agent gibt auf | Agent sucht, installiert, nutzt es |
| Command schlägt fehl | 1-Shot-Retry oder Aufgabe | Fehler klassifizieren → richtige Strategie wählen |
| Tool liefert Müll | Wird nicht erkannt | Semantische Outcome-Prüfung |
| Gleichen Fehler nochmal | Kein Gedächtnis | Knowledge-Base mit bewährten Lösungen |
| Komplexe Tool-Ketten | Nicht möglich | Tool-Chain-Planning (A → B → C) |
| Kein Tool passt | Aufgabe | Script on-the-fly generieren |

---

## 2. Ist-Zustand

### Was gut ist (und bleiben muss)

| Komponente | Was sie leistet | Qualität |
|---|---|---|
| `ToolRegistry` + `ToolSpec` | Typisiertes Schema mit Capabilities, Timeouts, JSON-Schema | ⭐⭐⭐⭐⭐ |
| `ToolCallGatekeeper` | 3 Loop-Detection-Strategien + Circuit-Breaker | ⭐⭐⭐⭐⭐ |
| `ToolArgValidator` | Per-Tool-Validierung vor Execution | ⭐⭐⭐⭐ |
| `AgentTooling` Command-Safety | 22 Regex-Patterns + Semantic-Analysis + Allowlist | ⭐⭐⭐⭐⭐ |
| `SSRF-Protection` | DNS-Pinning, IP-Validation, Hostname-Blocking | ⭐⭐⭐⭐⭐ |
| `ToolExecutionManager` Orchestration | Capability-Preselection, Budget-Tracking, Result-Transformation | ⭐⭐⭐⭐ |
| `Lifecycle-Events` | ~30 Events im Execute-Flow | ⭐⭐⭐ (aber: keine Aggregation) |

### Was fehlt oder schwach ist

| Lücke | Schwere | Detail |
|---|---|---|
| **Error-Taxonomie** | 🔴 Kritisch | `ToolExecutionError` ist monolithisch. Kein Typ-System für Fehlerklassen. Retry-Logic muss String-Matching auf `error_code` machen. |
| **Retry-Framework** | 🔴 Kritisch | Nur web_fetch 404 hat speziellen Retry. `run_command` "command not found" → kein Retry, kein Install-Versuch Backoff, keine Argument-Mutation. |
| **Outcome-Verification** | 🔴 Kritisch | `verify_tool_result()` = Substring-Matching auf `" error"`. False-Positives bei "error handling code", keine Exit-Code-Prüfung, keine File-Checks. |
| **Telemetry/Tracing** | 🟡 Wichtig | Events werden emittiert (`emit_lifecycle`) aber: kein Span-System, keine Aggregation, keine Persistenz, kein Dashboard. |
| **Tool-Discovery** | 🔴 Kritisch | Agent kann keine unbekannten Tools finden. Null Capability. |
| **Auto-Installation** | 🔴 Kritisch | Agent kann nichts installieren. Kein Package-Manager-Interface. |
| **Learning Loop** | 🟡 Wichtig | `failure_journal` existiert (LTM), aber kein positives Lernen ("pandoc hat funktioniert"). |
| **`ToolExecutionResult`** | 🟡 Wichtig | Dataclass existiert, wird aber nie returned. `execute()` gibt raw `str` zurück. Structured Return fehlt. |

### Call-Chain (Status Quo)

```
HeadAgent.run()
  → _execute_planner_step()           → plan_text
  → _execute_tool_step()
    → _execute_tools()
      → ToolExecutionManager.execute()
        → _infer_required_capabilities()
        → _apply_capability_preselection()
        → build_tool_selector_prompt()
        → select_actions_with_repair()
        → apply_action_pipeline()
        → run_tool_loop()
          ┌─── FOR EACH action ───┐
          │ prepare_action()       │
          │ budget_check()         │
          │ gatekeeper.before()    │◄── Loop-Detection
          │ build_execution_policy │
          │ run_tool_with_policy() │◄── HIER PASSIERT DER RETRY
          │   └─ _invoke_tool()    │
          │       └─ AgentTooling  │◄── HIER PASSIERT DIE EXECUTION
          │ transform_result()     │
          │ memory_add()           │
          │ gatekeeper.after()     │
          └────────────────────────┘
  → _classify_tool_results_state()    → "usable" | "error_only" | "empty"
  → optional replan (max 1x)
  → _execute_synthesize_step()        → final_text
```

**Kernbeobachtung:** Die Retry-Logic sitzt in `HeadAgent._run_tool_with_policy()` —
ein Callback der an `ToolExecutionManager` übergeben wird. Das ist ein **Anti-Pattern**
weil die Retry-Intelligenz im Agent statt im Execution-Layer lebt.

---

## 3. Ziel-Zustand

### Ziel-Architektur: 8 Säulen

```
            ┌─────────────────────────────────────────┐
            │            USER REQUEST                  │
            └──────────────────┬──────────────────────┘
                               │
  ┌────────────────────────────▼───────────────────────────┐
  │  ToolIntentResolver                                     │
  │  "convert markdown to pdf" → cap: document_conversion   │
  └────────────────────────────┬───────────────────────────┘
                               │
  ┌────────────────────────────▼───────────────────────────┐
  │  ToolDiscoveryEngine                                    │
  │  cap: document_conversion → [pandoc, weasyprint, ...]   │
  │  Sources: KnowledgeBase → LLM → PackageManager → Web   │
  └────────────────────────────┬───────────────────────────┘
                               │
  ┌────────────────────────────▼───────────────────────────┐
  │  AdaptiveToolSelector                                   │
  │  [pandoc: 0.95, weasyprint: 0.72] → pandoc              │  ◄── L4
  │  Scoring: success_rate + speed + platform + preference  │
  └────────────────────────────┬───────────────────────────┘
                               │
  ┌────────────────────────────▼───────────────────────────┐
  │  ToolProvisioner                                        │
  │  which pandoc → ❌ → choco install pandoc → ✅           │  ◄── L3
  │  Policy: ask_user | auto | deny                        │
  └────────────────────────────┬───────────────────────────┘
                               │
  ┌────────────────────────────▼───────────────────────────┐
  │  ToolExecutor (enhanced run_tool_loop)                  │
  │  pandoc input.md -o output.pdf                          │
  │  + Timeout + Isolation + Resource-Limits                │
  └────────────────────────────┬───────────────────────────┘
                               │
  ┌────────────────────────────▼───────────────────────────┐
  │  ToolOutcomeVerifier                                    │  ◄── L1
  │  file_exists(output.pdf)? ✅  size > 0? ✅               │
  │  content_type = application/pdf? ✅                      │
  └──────────┬─────────────────────────────┬──────────────┘
             │ PASS                         │ FAIL
             ▼                              ▼
  ┌──────────────────┐       ┌──────────────────────────────┐
  │  ToolTelemetry   │       │  ToolRetryStrategy           │  ◄── L1
  │  Record success  │       │  classify_error → strategy   │
  │  Update KnowBase │       │  backoff | mutate | alt_tool │
  └──────────────────┘       │  | escalate | install        │
                              └──────────────┬──────────────┘
                                             │
                              ┌──────────────▼──────────────┐
                              │  SelfHealingLoop             │  ◄── L5
                              │  Root-cause → Recovery-Plan  │
                              │  → Retry → Eskalation        │
                              └──────────────────────────────┘
```

---

## 4. Architektur-Entscheidungen

### AD-01: Error-Taxonomie als Enum-Hierarchy, nicht als Klassen-Hierarchy

**Entscheidung:** Fehler werden über `ErrorClass` (Enum) + `ErrorDetail` (dataclass) typisiert,
nicht über Exception-Subklassen.

**Begründung:**
- `ToolExecutionError` bleibt der einzige Exception-Typ (keine Breaking-Change)
- Error-Klassifikation passiert im `ToolRetryStrategy` *nach* dem Catch, nicht *durch* den Typ
- Erlaubt dynamische Erweiterung ohne neue Exception-Klassen
- Retry-Logik entscheidet anhand von `ErrorClass`, nicht anhand von `isinstance()`

```python
class ErrorClass(str, Enum):
    TRANSIENT_NETWORK = "transient_network"
    MISSING_COMMAND = "missing_command"
    MISSING_MODULE = "missing_module"
    PERMISSION_DENIED = "permission_denied"
    INVALID_ARGS = "invalid_args"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    UNSUPPORTED_FORMAT = "unsupported_format"
    VERSION_MISMATCH = "version_mismatch"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
```

### AD-02: Retry-Logic aus Agent in ToolExecutionManager verlagern

**Entscheidung:** `ToolRetryStrategy` wird im `ToolExecutionManager.run_tool_loop()` aufgerufen,
nicht als Callback im `HeadAgent`.

**Begründung:**
- Retry-Logik gehört in den Execution-Layer, nicht in den Orchestration-Layer
- `HeadAgent._run_tool_with_policy()` bleibt als Dispatch aber ohne Retry-Intelligenz
- Separation of Concerns: Agent entscheidet *was*, Executor entscheidet *wie*

### AD-03: KnowledgeBase als SQLite, nicht als JSON

**Entscheidung:** `ToolKnowledgeBase` nutzt SQLite (wie bereits `LongTermMemoryStore`).

**Begründung:**
- Schema-Evolution mit ALTER TABLE statt JSON-Migration
- Full-Text-Search für Capability-Matching
- Concurrent-Access-sicher (multi-session)
- Konsistenz mit LTM-Pattern im Projekt

### AD-04: PackageManagerAdapter als Protocol, nicht als ABC

**Entscheidung:** `PackageManagerAdapter` ist ein `typing.Protocol`, keine abstrakte Basisklasse.

**Begründung:**
- Structural Subtyping — Adapter müssen nicht explizit erben
- Einfacher zu testen (Duck-Typing-kompatibel)
- Konsistenz mit `ToolProvider` Protocol-Pattern im Projekt

### AD-05: Discovery + Provisioning = Opt-In per Policy

**Entscheidung:** Automatische Tool-Installation ist per Default `"ask_user"`, nicht `"auto"`.

**Begründung:**
- Sicherheit > Bequemlichkeit
- User muss explizit zustimmen bevor der Agent `npm install` oder `pip install` laufen lässt
- `"auto"` nur für sandboxed Environments (venv, node_modules im Workspace)

### AD-06: Telemetry als lokales SQLite, nicht als externer Service

**Entscheidung:** `ToolTelemetry` persistiert Spans in SQLite, exportiert optional zu OpenTelemetry.

**Begründung:**
- Keine externe Dependency für Grundfunktion
- SQLite reicht für Single-Agent-Analyse
- OpenTelemetry-Export als optionale Erweiterung

### AD-07: Outcome-Verification als Middleware, nicht als Post-Processing

**Entscheidung:** `ToolOutcomeVerifier` läuft *innerhalb* des `run_tool_loop()` nach jeder
Tool-Ausführung, nicht danach im Agent.

**Begründung:**
- Verifier-Ergebnis beeinflusst Retry-Entscheidung direkt
- Kein zweiter Durchlauf nötig um Fehler zu erkennen
- Enger Loop: Execute → Verify → Retry/Accept

### AD-08: Progressive Rollout durch Feature-Flags

**Entscheidung:** Jede neue Komponente hat ein Feature-Flag in `Settings`.

**Begründung:**
- Rollback ohne Code-Änderung möglich
- A/B-Testing zwischen altem und neuem Verhalten
- Keine Big-Bang-Migration

---

## 5. Level 1: Retry + Outcome + Telemetry

> **Timeline: 1-2 Wochen**
> **Impact: Sofortige Zuverlässigkeit für bestehende 18 Tools**
> **Risiko: Niedrig (additiv, kein Breaking Change)**

### 5.1 `ToolRetryStrategy` — Reason-Aware Retry Engine

**File:** `backend/app/services/tool_retry_strategy.py`

#### Was es tut
Analysiert `ToolExecutionError` + stdout/stderr semantisch und entscheidet über die optimale
Retry-Strategie. Kein blindes Wiederholen.

#### Kern-Datenmodelle

```python
class ErrorClass(str, Enum):
    """Typisierte Fehlerklassen für Retry-Entscheidungen."""
    TRANSIENT_NETWORK = "transient_network"      # Timeout, Connection-Reset, 503, 429
    MISSING_COMMAND = "missing_command"           # 'X' is not recognized / command not found
    MISSING_MODULE = "missing_module"             # ModuleNotFoundError / Cannot find module
    PERMISSION_DENIED = "permission_denied"       # Permission denied / Access denied / EACCES
    INVALID_ARGS = "invalid_args"                 # Invalid option / Unknown flag
    RESOURCE_EXHAUSTED = "resource_exhausted"     # Disk full / OOM / Port in use
    UNSUPPORTED_FORMAT = "unsupported_format"     # Unsupported / Can't decode
    VERSION_MISMATCH = "version_mismatch"         # Requires version X.Y / Incompatible
    COMMAND_POLICY = "command_policy"             # Command Policy Violation (Allowlist)
    TIMEOUT = "timeout"                           # asyncio.TimeoutError
    UNKNOWN = "unknown"                           # Catch-all

class RetryStrategy(str, Enum):
    """Was nach einem Fehler zu tun ist."""
    BACKOFF = "backoff"                          # Gleicher Command, warten, nochmal
    MUTATE_ARGS = "mutate_args"                  # Argumente anpassen (z.B. anderen Flag)
    ALTERNATIVE_TOOL = "alternative_tool"        # Anderes Tool probieren
    INSTALL_AND_RETRY = "install_and_retry"      # Tool installieren, dann nochmal
    ESCALATE = "escalate"                        # User fragen / aufgeben
    NO_RETRY = "no_retry"                        # Kein Retry sinnvoll

@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    strategy: RetryStrategy
    error_class: ErrorClass
    delay_seconds: float                         # 0.0 bei sofortigem Retry
    max_attempts: int                            # Wie oft maximal retrien
    suggestion: str                              # Menschenlesbare Erklärung
    mutated_args: dict[str, Any] | None = None   # Bei MUTATE_ARGS
    alternative_tool: str | None = None          # Bei ALTERNATIVE_TOOL
    install_hint: str | None = None              # Bei INSTALL_AND_RETRY
```

#### Klassifikations-Regeln (Error-Pattern → Strategy)

```python
CLASSIFICATION_RULES: list[tuple[Pattern, ErrorClass, RetryStrategy]] = [
    # --- Transient (Backoff) ---
    (r"connection refused|ECONNREFUSED",           TRANSIENT_NETWORK,  BACKOFF),
    (r"timeout|timed out|ETIMEDOUT",               TRANSIENT_NETWORK,  BACKOFF),
    (r"ECONNRESET|connection reset",               TRANSIENT_NETWORK,  BACKOFF),
    (r"503|service unavailable",                   TRANSIENT_NETWORK,  BACKOFF),
    (r"429|too many requests|rate.?limit",          TRANSIENT_NETWORK,  BACKOFF),

    # --- Missing Command (Install + Retry) ---
    (r"command not found",                          MISSING_COMMAND,    INSTALL_AND_RETRY),
    (r"is not recognized as an? .*command",         MISSING_COMMAND,    INSTALL_AND_RETRY),
    (r"not found in PATH",                          MISSING_COMMAND,    INSTALL_AND_RETRY),
    (r"No such file or directory.*exec",            MISSING_COMMAND,    INSTALL_AND_RETRY),
    (r"The term '.*' is not recognized",            MISSING_COMMAND,    INSTALL_AND_RETRY),

    # --- Missing Module (Install + Retry) ---
    (r"ModuleNotFoundError|No module named",        MISSING_MODULE,     INSTALL_AND_RETRY),
    (r"Cannot find module|MODULE_NOT_FOUND",        MISSING_MODULE,     INSTALL_AND_RETRY),
    (r"ImportError:.*No module",                    MISSING_MODULE,     INSTALL_AND_RETRY),

    # --- Permission (Escalate) ---
    (r"permission denied|EACCES|Access is denied",  PERMISSION_DENIED,  ESCALATE),
    (r"requires? (?:admin|root|elevation)",         PERMISSION_DENIED,  ESCALATE),

    # --- Invalid Args (Mutate) ---
    (r"invalid option|unknown flag|unrecognized",   INVALID_ARGS,       MUTATE_ARGS),
    (r"unexpected argument|bad argument",           INVALID_ARGS,       MUTATE_ARGS),
    (r"usage:|Usage:",                              INVALID_ARGS,       MUTATE_ARGS),

    # --- Resource (Escalate) ---
    (r"No space left|disk full|ENOSPC",             RESOURCE_EXHAUSTED, ESCALATE),
    (r"out of memory|OOM|MemoryError",              RESOURCE_EXHAUSTED, ESCALATE),
    (r"address already in use|EADDRINUSE",          RESOURCE_EXHAUSTED, MUTATE_ARGS),

    # --- Format/Version (Alternative) ---
    (r"unsupported|can't decode|unknown format",    UNSUPPORTED_FORMAT, ALTERNATIVE_TOOL),
    (r"requires version|incompatible|version.*mismatch", VERSION_MISMATCH, ALTERNATIVE_TOOL),
]
```

#### Backoff-Berechnung

```
Attempt 0: sofort
Attempt 1: 1.0s
Attempt 2: 2.0s
Attempt 3: 4.0s
Max: 30s

Formel: min(base_delay * 2^attempt, 30.0)
Jitter: ±20% (verhindert Thundering-Herd)
```

#### Akzeptanzkriterien L1.1

| # | Kriterium | Messbar |
|---|---|---|
| AK-1.1.1 | `classify_error()` erkennt mindestens 15 verschiedene Error-Patterns korrekt | Unit-Test mit 15+ Fixtures |
| AK-1.1.2 | Jede `ErrorClass` hat mindestens 2 Regex-Patterns | Coverage-Check |
| AK-1.1.3 | `RetryDecision` wird für jeden `ErrorClass`-Wert korrekt erzeugt | Exhaustive-Enum-Test |
| AK-1.1.4 | Backoff-Berechnung produziert korrekte Delays mit Jitter | Property-based Test |
| AK-1.1.5 | `UNKNOWN` Error-Class wird für unbekannte Patterns zurückgegeben, nie ein Crash | Fuzz-Test mit 100 Random-Strings |
| AK-1.1.6 | Integration in `run_tool_loop()` ohne Breaking-Change zu bestehenden Tests | Alle existierenden Tests grün |
| AK-1.1.7 | Feature-Flag `tool_retry_strategy_enabled` (default: True) in Settings | Settings-Test |
| AK-1.1.8 | Lifecycle-Events: `tool_retry_classified`, `tool_retry_decision`, `tool_retry_executed` | Event-Test |

---

### 5.2 `ToolOutcomeVerifier` — Expected-Effect Checks

**File:** `backend/app/services/tool_outcome_verifier.py`

#### Was es tut
Prüft nach jeder Tool-Ausführung ob das *erwartete Ergebnis* tatsächlich eingetreten ist.
Geht weit über "enthält der Output 'error'?" hinaus.

#### Kern-Datenmodelle

```python
@dataclass(frozen=True)
class OutcomeExpectation:
    """Was wir nach einer Tool-Ausführung erwarten."""
    exit_code: int | None = 0
    file_created: str | None = None
    file_min_size_bytes: int | None = None
    file_content_starts_with: bytes | None = None    # Magic-Bytes: PDF = b"%PDF"
    stdout_contains: str | None = None
    stdout_not_contains: str | None = None
    stderr_empty: bool = False
    dir_not_empty: str | None = None
    process_started: str | None = None

@dataclass(frozen=True)
class OutcomeCheck:
    name: str                  # "file_exists", "exit_code", "magic_bytes"
    passed: bool
    expected: str
    actual: str

@dataclass(frozen=True)
class OutcomeVerdict:
    passed: bool
    confidence: float          # 0.0 - 1.0
    checks: tuple[OutcomeCheck, ...]
    suggestion: str | None     # "File was created but is empty — re-run with verbose flag"
```

#### Automatische Expectation-Inferenz

Der Verifier *inferiert* Expectations aus Tool-Name + Args, ohne dass sie manuell definiert
werden müssen:

```python
EXPECTATION_RULES = {
    # Tool + Arg-Pattern → automatische Expectation
    "write_file": lambda args: OutcomeExpectation(
        file_created=args.get("path"),
        file_min_size_bytes=1,
    ),
    "run_command": {
        # Wenn Command "pandoc ... -o X.pdf" enthält
        r"-o\s+(\S+\.pdf)": lambda m: OutcomeExpectation(
            file_created=m.group(1),
            file_content_starts_with=b"%PDF",
        ),
        # Wenn Command "npm install" enthält
        r"npm install": lambda m: OutcomeExpectation(
            exit_code=0,
            dir_not_empty="node_modules",
        ),
        # Wenn Command "pytest" enthält
        r"pytest|python -m pytest": lambda m: OutcomeExpectation(
            exit_code=0,
            stdout_contains="passed",
        ),
        # Default für run_command
        "__default__": lambda args: OutcomeExpectation(exit_code=0),
    },
    "apply_patch": lambda args: OutcomeExpectation(
        # Datei muss nach Patch den neuen Inhalt haben
        file_created=args.get("path"),
        file_min_size_bytes=1,
    ),
}
```

#### Akzeptanzkriterien L1.2

| # | Kriterium | Messbar |
|---|---|---|
| AK-1.2.1 | `verify()` prüft Exit-Code korrekt (0 = pass, non-0 = fail) | Unit-Test |
| AK-1.2.2 | File-Existence-Check funktioniert für absolute + relative Pfade | Unit-Test mit temp-Files |
| AK-1.2.3 | Magic-Bytes-Check erkennt PDF (`%PDF`), PNG (`\x89PNG`), ZIP (`PK`) | Unit-Test mit echten Dateien |
| AK-1.2.4 | Auto-Inferenz generiert korrekte Expectations für `write_file`, `run_command`, `apply_patch` | Unit-Test |
| AK-1.2.5 | `OutcomeVerdict.confidence` ist 1.0 bei allen Checks passed, < 1.0 proportional | Arithmetik-Test |
| AK-1.2.6 | Ersetzt den naiven `verify_tool_result()` in `VerificationService` | Integration-Test |
| AK-1.2.7 | Keine False-Positives: "error handling" im Output wird nicht als Fehler klassifiziert | Regression-Test (dokumentierter Bug) |
| AK-1.2.8 | Feature-Flag `tool_outcome_verifier_enabled` (default: True) | Settings-Test |
| AK-1.2.9 | Verdict wird an `ToolRetryStrategy` weitergegeben wenn `passed=False` | Integration-Test |

---

### 5.3 `ToolTelemetry` — Structured Tracing + Metrics

**File:** `backend/app/services/tool_telemetry.py`

#### Was es tut
Ersetzt die lose `emit_lifecycle`-Events durch ein strukturiertes Span-basiertes Tracing-System.
Jeder Tool-Call wird ein Span mit Start/End, Outcome, Duration, Parent-Child-Beziehungen.

#### Kern-Datenmodelle

```python
@dataclass
class ToolSpan:
    span_id: str                           # UUID
    parent_span_id: str | None             # Für nested Tools (z.B. Subrun)
    session_id: str
    request_id: str
    tool_name: str
    args_fingerprint: str                  # SHA256 der normalisierten Args
    start_time: float                      # monotonic()
    end_time: float | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    outcome: str = "pending"               # "success" | "failed" | "retried" | "skipped" | "timeout"
    error_class: str | None = None
    retry_count: int = 0
    result_size_bytes: int = 0
    truncated: bool = False

@dataclass(frozen=True)
class ToolStats:
    """Aggregierte Statistik pro Tool."""
    tool_name: str
    total_calls: int
    success_count: int
    failure_count: int
    timeout_count: int
    retry_count: int
    avg_duration_seconds: float
    p95_duration_seconds: float
    success_rate: float                    # success_count / total_calls
    most_common_error: str | None
```

#### Akzeptanzkriterien L1.3

| # | Kriterium | Messbar |
|---|---|---|
| AK-1.3.1 | Jeder Tool-Call erzeugt genau einen `ToolSpan` mit Start + End | Unit-Test |
| AK-1.3.2 | Spans werden in SQLite persistiert (Table: `tool_spans`) | DB-Schema-Test |
| AK-1.3.3 | `get_tool_stats()` berechnet korrekte Aggregate (count, rate, avg_duration) | Arithmetik-Test |
| AK-1.3.4 | Parent-Child-Spans funktionieren für `spawn_subrun` | Integration-Test |
| AK-1.3.5 | Span-Overhead < 1ms pro Tool-Call (keine spürbare Verlangsamung) | Performance-Benchmark |
| AK-1.3.6 | Feature-Flag `tool_telemetry_enabled` (default: True) | Settings-Test |
| AK-1.3.7 | `ToolStats` sind über API/WebSocket abrufbar | Endpoint-Test |
| AK-1.3.8 | Spans älter als 7 Tage werden automatisch bereinigt | TTL-Test |

---

## 6. Level 2: Discovery + Knowledge

> **Timeline: 2-3 Wochen**
> **Impact: Agent kann unbekannte Tools finden und kennt bewährte Lösungen**
> **Risiko: Mittel (neuer I/O: Web-Search, Package-Manager-Calls)**

### 6.1 `ToolKnowledgeBase` — Lernender Wissensspeicher

**File:** `backend/app/services/tool_knowledge_base.py`

#### Was es tut
Persistenter Speicher der lernt: "Für Aufgabe X auf Plattform Y hat Tool Z mit Argumenten W
funktioniert." Wird nach jeder Execution aktualisiert (positiv UND negativ).

#### SQLite-Schema

```sql
CREATE TABLE tool_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,              -- "convert_markdown_to_pdf"
    tool_command TEXT NOT NULL,            -- "pandoc"
    install_command TEXT,                  -- "choco install pandoc"
    usage_pattern TEXT,                    -- "pandoc {input} -o {output}.pdf"
    platform TEXT NOT NULL,               -- "win32" | "linux" | "darwin"
    package_manager TEXT,                 -- "choco" | "apt" | "brew" | "npm"
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_used_at TEXT,                     -- ISO timestamp
    avg_duration_seconds REAL,
    tags TEXT,                             -- JSON array: ["pdf", "document"]
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_capability ON tool_knowledge(capability);
CREATE INDEX idx_platform ON tool_knowledge(platform);
```

#### Akzeptanzkriterien L2.1

| # | Kriterium | Messbar |
|---|---|---|
| AK-2.1.1 | `learn_from_success()` incrementiert `success_count` und aktualisiert `avg_duration` | Unit-Test |
| AK-2.1.2 | `learn_from_failure()` incrementiert `failure_count` | Unit-Test |
| AK-2.1.3 | `find_for_capability()` gibt Ergebnisse sortiert nach `confidence` zurück | Unit-Test |
| AK-2.1.4 | Confidence = `success_count / (success_count + failure_count)`, min 5 samples | Formel-Test |
| AK-2.1.5 | Plattform-Filter: nur Einträge für aktuelles OS werden zurückgegeben | Filter-Test |
| AK-2.1.6 | Concurrent-Access: 2 Sessions können gleichzeitig schreiben ohne Race-Condition | Concurrency-Test |
| AK-2.1.7 | Knowledge-Base überlebt Agent-Restart (SQLite-Datei in `memory_store/`) | Persistence-Test |

---

### 6.2 `ToolDiscoveryEngine` — Multi-Source Tool Finder

**File:** `backend/app/services/tool_discovery_engine.py`

#### 4-Phasen-Pipeline

```
Phase 1: KnowledgeBase Lookup (< 1ms)
    → Haben wir für "convert_markdown_to_pdf" schon eine bewährte Lösung?
    → Ja + confidence > 0.8 → Return sofort

Phase 2: LLM-Reasoning (1-3s)
    → "Welche CLI-Tools konvertieren Markdown zu PDF?"
    → LLM antwortet: pandoc, wkhtmltopdf, weasyprint, ...
    → Für jedes: Installationsbefehl + Usage-Pattern generieren

Phase 3: Package-Manager-Search (2-5s, parallel)
    → npm search "markdown pdf"
    → pip search "markdown pdf"
    → choco search "pandoc" / apt search "pandoc" / brew search "pandoc"

Phase 4: Web-Search Fallback (3-8s)
    → Nur wenn Phase 1-3 nichts liefern
    → web_search("best CLI tool to convert markdown to pdf {platform}")
    → Ergebnisse parsen + LLM-assist
```

#### Akzeptanzkriterien L2.2

| # | Kriterium | Messbar |
|---|---|---|
| AK-2.2.1 | Discovery liefert mindestens 1 Kandidaten für jede der 10 Test-Capabilities | Smoke-Test |
| AK-2.2.2 | KnowledgeBase-Hit (Phase 1) returnt in < 10ms | Performance-Test |
| AK-2.2.3 | LLM-Phase generiert valide `install_command` + `usage_pattern` für jeden Kandidaten | Output-Validation |
| AK-2.2.4 | Gesamt-Discovery-Time < 15s (mit Web-Fallback) | Timeout-Test |
| AK-2.2.5 | Deduplizierung: "pandoc" erscheint nicht 3x in der Ergebnisliste | Dedup-Test |
| AK-2.2.6 | Feature-Flag `tool_discovery_enabled` (default: False — opt-in!) | Settings-Test |
| AK-2.2.7 | Discovery-Ergebnisse werden in KnowledgeBase gespeichert für nächstes Mal | Persistence-Test |

---

### 6.3 `PackageManagerAdapter` — Unified Interface

**File:** `backend/app/services/package_manager_adapter.py`

#### Implementierungen (Phase 1: die 3 wichtigsten)

| Adapter | Plattform | Befehle |
|---|---|---|
| `NpmAdapter` | Alle | `npm list -g --json`, `npm install -g`, `npx --yes` |
| `PipAdapter` | Alle | `pip list --format=json`, `pip install --user`, `pipx run` |
| `SystemAdapter` | Per OS | Win: `choco`/`winget`, Mac: `brew`, Linux: `apt`/`dnf` |

#### Akzeptanzkriterien L2.3

| # | Kriterium | Messbar |
|---|---|---|
| AK-2.3.1 | `is_available()` erkennt ob ein Package-Manager installiert ist | Unit-Test (mocked `which`) |
| AK-2.3.2 | `search()` gibt strukturierte Ergebnisse zurück (name, version, description) | Integration-Test |
| AK-2.3.3 | `install()` respektiert Scope: `--user` / `--save-dev` / workspace-lokal | Contract-Test |
| AK-2.3.4 | `is_installed()` prüft ob ein Package schon installiert ist | Unit-Test |
| AK-2.3.5 | Timeout von 30s für jeden PM-Befehl | Timeout-Test |
| AK-2.3.6 | Fehler bei PM-Befehlen werden strukturiert zurückgegeben, kein Crash | Error-Handling-Test |

---

### 6.4 `PlatformInfo` — Environment Detection

**File:** `backend/app/services/platform_info.py`

#### Akzeptanzkriterien L2.4

| # | Kriterium | Messbar |
|---|---|---|
| AK-2.4.1 | `detect()` erkennt OS (`win32`/`linux`/`darwin`) korrekt | Plattform-Test |
| AK-2.4.2 | `detect()` findet installierte Runtimes (python, node, java) mit Versionen | Integration-Test |
| AK-2.4.3 | `detect()` findet verfügbare Package-Manager | Integration-Test |
| AK-2.4.4 | Ergebnis ist `frozen` (immutable) und cacheable | Dataclass-Test |
| AK-2.4.5 | Wiederholte Calls innerhalb einer Session werden gecacht (< 1ms) | Performance-Test |

---

## 7. Level 3: Provisioning + Governance

> **Timeline: 2 Wochen**
> **Impact: Agent installiert fehlende Tools selbständig**
> **Risiko: Hoch (System-Modifikation — braucht robuste Policy)**

### 7.1 `ToolProvisioner` — Install + Verify Pipeline

**File:** `backend/app/services/tool_provisioner.py`

#### Flow

```
ensure_available("pandoc")
  │
  ├─ 1. is_installed? ──── YES ──→ Return(already_available)
  │                   └── NO
  │
  ├─ 2. resolve_install_plan()
  │     ├─ KnowledgeBase: "pandoc installiert man via choco install pandoc"
  │     ├─ LLM: "Auf Windows ist der beste Weg: choco install pandoc"
  │     └─ Result: InstallPlan(pm="choco", package="pandoc", command="choco install pandoc -y")
  │
  ├─ 3. policy_check()
  │     ├─ mode == "deny" ──→ Return(policy_denied)
  │     ├─ mode == "auto" AND sandbox ──→ Continue
  │     └─ mode == "ask_user" ──→ WebSocket-Event "install_approval_request"
  │                               └─ User: "Ja" / "Nein"
  │
  ├─ 4. execute_install()
  │     ├─ run_command("choco install pandoc -y")
  │     └─ timeout: 120s (Installationen dauern)
  │
  ├─ 5. verify_install()
  │     ├─ which pandoc → /path/to/pandoc ✅
  │     ├─ pandoc --version → "pandoc 3.1.12" ✅
  │     └─ Return(installed, version="3.1.12")
  │
  └─ 6. FAIL? → try_alternative()
        ├─ Nächster PM probieren (winget install pandoc)
        └─ Nächster Kandidat probieren (wkhtmltopdf)
```

### 7.2 `ProvisioningPolicy` — Governance

**File:** `backend/app/services/provisioning_policy.py`

#### Policy-Level

| Level | `mode` | Wann |
|---|---|---|
| **Strict** | `deny` | Produktions-Environments, CI/CD |
| **Interactive** | `ask_user` | Normaler Betrieb (default) |
| **Sandboxed Auto** | `auto_sandboxed` | Nur in venv/node_modules/Docker |
| **Full Auto** | `auto` | Explizit opt-in, nur dev-Environments |

#### Akzeptanzkriterien L3

| # | Kriterium | Messbar |
|---|---|---|
| AK-3.1 | Default-Policy ist `ask_user`, niemals `auto` | Config-Test |
| AK-3.2 | Blocked-Packages-Liste enthält mindestens: `rm-rf*`, `malware*`, `crypto-miner*` | Blocklist-Test |
| AK-3.3 | User-Approval über WebSocket funktioniert (Request → Response → Continue/Abort) | E2E-Test |
| AK-3.4 | Install-Timeout von 120s wird eingehalten | Timeout-Test |
| AK-3.5 | Nach Installation: `which <tool>` bestätigt Verfügbarkeit | Verify-Test |
| AK-3.6 | Fehlgeschlagene Installation führt zu sauberem Error (kein halb-installierter Zustand) | Cleanup-Test |
| AK-3.7 | Sandbox-Install: pip nutzt `--target` / venv, npm nutzt lokale `node_modules` | Isolation-Test |
| AK-3.8 | Audit-Log: Jede Installation wird in `ToolTelemetry` + KnowledgeBase protokolliert | Audit-Test |
| AK-3.9 | Rollback: `uninstall()` entfernt das installierte Package wieder | Cleanup-Test |
| AK-3.10 | Feature-Flag `tool_provisioning_enabled` (default: False — explicit opt-in!) | Settings-Test |

---

## 8. Level 4: Adaptive Intelligence

> **Timeline: 1-2 Wochen**
> **Impact: Agent wird mit jeder Ausführung schlauer**
> **Risiko: Niedrig (nutzt nur bestehende Daten)**

### 8.1 `AdaptiveToolSelector` — Gewichtetes Scoring

**File:** `backend/app/services/adaptive_tool_selector.py`

#### Scoring-Formel

```
score = (
    success_rate       * 0.35    +     # Historische Erfolgsrate
    speed_score        * 0.20    +     # Schneller = besser
    platform_score     * 0.15    +     # Passt zur aktuellen Plattform?
    recency_score      * 0.15    +     # Kürzlich benutzt = bevorzugt
    install_ease_score * 0.15          # Leicht installierbar?
)
```

#### Akzeptanzkriterien L4.1

| # | Kriterium | Messbar |
|---|---|---|
| AK-4.1.1 | Bei gleichen Kandidaten wird der mit höherer `success_rate` gewählt | Determinismus-Test |
| AK-4.1.2 | Neues Tool (keine History) bekommt `success_rate = 0.5` (neutral) | Default-Test |
| AK-4.1.3 | Scoring ist deterministisch (gleiche Inputs → gleiches Ergebnis) | Idempotenz-Test |
| AK-4.1.4 | Feature-Flag `adaptive_tool_selection_enabled` (default: False) | Settings-Test |

### 8.2 `ToolChainPlanner` — Multi-Step Orchestration

**File:** `backend/app/services/tool_chain_planner.py`

#### Konvertierungs-Graph

```
text/markdown ──pandoc──→ application/pdf
text/markdown ──pandoc──→ text/html
text/html ──wkhtmltopdf──→ application/pdf
text/html ──chrome──→ application/pdf
application/pdf ──ImageMagick──→ image/png
image/* ──ImageMagick──→ image/*
video/* ──ffmpeg──→ image/* (frame extraction)
video/* ──ffmpeg──→ audio/*
```

#### Akzeptanzkriterien L4.2

| # | Kriterium | Messbar |
|---|---|---|
| AK-4.2.1 | Shortest-Path findet markdown→pdf in 1 Step (pandoc direkt) | Graph-Test |
| AK-4.2.2 | Shortest-Path findet markdown→png in 2 Steps (pandoc→ImageMagick) | Graph-Test |
| AK-4.2.3 | Kein Path = "unsupported conversion" (nicht endlose Suche) | Negative-Test |
| AK-4.2.4 | Feature-Flag `tool_chain_planning_enabled` (default: False) | Settings-Test |

### 8.3 `ExecutionPatternDetector` — Anti-Patterns

**File:** `backend/app/services/execution_pattern_detector.py`

#### Erkannte Anti-Patterns

| Pattern | Erkennung | Aktion |
|---|---|---|
| **Brute-Force Install** | 3+ verschiedene PM-Befehle in Folge | Merke welcher funktioniert |
| **Version Roulette** | 3+ verschiedene Versionen probiert | Suggest LTS/stable |
| **Path Thrashing** | 5+ `read_file` auf verschiedene Pfade für gleiche Datei | Suggest `file_search` zuerst |
| **Retry Without Change** | 3+ identische Commands | Stop + analyze statt retry |
| **NPM/NPX Confusion** | `npm <tool>` fails → should be `npx <tool>` | Auto-Suggest npx |
| **Global Install Overuse** | `npm install -g` wenn lokal reicht | Suggest `--save-dev` |

#### Akzeptanzkriterien L4.3

| # | Kriterium | Messbar |
|---|---|---|
| AK-4.3.1 | Jedes der 6 Anti-Patterns wird in synthetischen Traces erkannt | Detection-Test |
| AK-4.3.2 | Suggestion-Text ist menschenlesbar und actionable | Review |
| AK-4.3.3 | Detection fügt sich in bestehenden `ToolCallGatekeeper`-Flow ein | Integration-Test |
| AK-4.3.4 | Feature-Flag `execution_pattern_detection_enabled` (default: True) | Settings-Test |

---

## 9. Level 5: Full Autonomy

> **Timeline: 3-4 Wochen**
> **Impact: Agent handelt vollständig autonom**
> **Risiko: Hoch (LLM-generierter Code wird ausgeführt)**

### 9.1 `ToolSynthesizer` — Ad-hoc Script Generation

**File:** `backend/app/services/tool_synthesizer.py`

#### Wann wird es aktiviert?
Nur wenn:
1. Kein bestehendes Tool die Aufgabe erfüllt UND
2. Discovery + Provisioning keinen Kandidaten liefern UND
3. Die Aufgabe in einem Script lösbar ist

#### Sicherheitsmodell

```
LLM generiert Script
       │
       ▼
┌──────────────┐    BLOCKED: Network-Access ohne Erlaubnis
│ Safety Scan  │    BLOCKED: File-Deletion außerhalb Workspace
│ (statisch)   │    BLOCKED: Env-Variable manipulation
│              │    BLOCKED: Process spawning (fork-bomb)
│              │    BLOCKED: Crypto/Mining patterns
└──────┬───────┘
       │ PASSED
       ▼
┌──────────────┐
│ Sandbox Exec │    Isoliert: eigenes temp-dir, timeout, resource-limits
│ (CodeSandbox)│    Kein Zugriff auf: home-dir, system-dirs, andere Projekte
└──────┬───────┘
       │
       ▼
   Verify Outcome
```

### 9.2 `SelfHealingLoop` — Autonomous Error Recovery

**File:** `backend/app/services/self_healing_loop.py`

#### Flow

```
Alle Retries erschöpft
       │
       ▼
Analysiere Error-History
  ├─ "pandoc command not found" (3x)
  ├─ "choco install failed" (1x)
  └─ "winget install failed" (1x)
       │
       ▼
LLM Root-Cause Analysis:
  "Pandoc ist nicht über Standard-Package-Manager verfügbar.
   Alternatives: Download von GitHub Releases, Docker-Image, WSL."
       │
       ▼
Recovery-Plan generieren:
  1. Prüfe ob Docker verfügbar
  2. docker pull pandoc/core
  3. docker run -v {workspace}:/data pandoc/core input.md -o output.pdf
       │
       ▼
Retry mit Recovery-Plan
```

#### Akzeptanzkriterien L5

| # | Kriterium | Messbar |
|---|---|---|
| AK-5.1 | Synthesizer generiert ein lauffähiges Python-Script für "resize all images in folder" | E2E-Test |
| AK-5.2 | Safety-Scan blockiert Scripts mit `os.remove()` außerhalb Workspace | Security-Test |
| AK-5.3 | Sandbox-Timeout von 30s wird eingehalten | Timeout-Test |
| AK-5.4 | SelfHealingLoop findet Docker-Fallback wenn native Installation fehlschlägt | E2E-Test |
| AK-5.5 | Max 3 Recovery-Versuche bevor Eskalation an User | Circuit-Breaker-Test |
| AK-5.6 | Feature-Flags: `tool_synthesizer_enabled`, `self_healing_enabled` (default: False) | Settings-Test |

---

## 10. Akzeptanzkriterien (global)

### Muss-Kriterien (alle Level)

| # | Kriterium | Wie messen |
|---|---|---|
| G-01 | **Keine Breaking Changes** — Alle bestehenden 714+ Tests bleiben grün | `pytest --tb=short` = 0 failures |
| G-02 | **Feature-Flags** — Jede neue Komponente hat ein eigenes Flag in Settings | Code-Review |
| G-03 | **Lifecycle-Events** — Jede neue Komponente emittiert mindestens 3 Events | Event-Audit |
| G-04 | **Test-Coverage** — Jede neue Datei hat ≥ 90% Line-Coverage | `pytest --cov` |
| G-05 | **Keine neuen Dependencies** — Nur stdlib + bereits vorhandene Packages | `requirements.txt` Diff |
| G-06 | **Performance** — Kein Tool-Call darf durch neue Layer > 50ms langsamer werden | Benchmark vor/nach |
| G-07 | **Graceful Degradation** — Wenn eine neue Komponente fehlschlägt, funktioniert der Agent wie vorher | Kill-Switch-Test |
| G-08 | **Keine Secrets in Logs** — Telemetry darf keine API-Keys, Passwords, Tokens loggen | Redaction-Test |
| G-09 | **Error-Messages auf Deutsch UND Englisch** — Internationalizable Strings | I18n-Ready |
| G-10 | **Idempotenz** — Gleicher Input → gleiches Ergebnis (außer bei explizitem Randomness wie Jitter) | Property-Test |

### End-to-End Smoke-Tests (Abnahme je Level)

| Test-Szenario | Level | Expected Behavior |
|---|---|---|
| `run_command("unknown_tool --help")` → Error klassifiziert als `MISSING_COMMAND` | L1 | RetryDecision mit `INSTALL_AND_RETRY` |
| Agent versucht `npm install` → Node nicht installiert → Retry mit Erklärung | L1 | Graceful Error + Suggestion |
| `run_command("pytest")` → exit_code=1, stdout hat "1 failed" → Outcome: FAIL | L1 | OutcomeVerdict.passed = False |
| User: "Konvertiere README.md zu PDF" → Agent findet pandoc über KnowledgeBase | L2 | ToolCandidate mit usage_pattern |
| User: "Lade dieses Video als MP3 runter" → Discovery findet yt-dlp/ffmpeg | L2 | Mindestens 1 Kandidat |
| Agent installiert pandoc in Sandbox → verify → nutzt es | L3 | Full Pipeline Green |
| Agent hat pandoc 5x erfolgreich benutzt → bei nächster PDF-Aufgabe sofort pandoc gewählt | L4 | AdaptiveSelector score > 0.9 |
| Kein Tool passt → Agent generiert Python-Script → Sandbox → Ergebnis | L5 | SynthesizedTool.verdict.passed |

---

## 11. DOs — Was wir richtig machen müssen

### DO-01: Separation of Concerns einhalten
```
✅ ToolRetryStrategy KLASSIFIZIERT Fehler — führt NICHT aus
✅ ToolOutcomeVerifier PRÜFT Ergebnisse — entscheidet NICHT über Retry
✅ ToolExecutionManager ORCHESTRIERT — kennt KEINE Tool-Details
✅ ToolDiscoveryEngine FINDET Tools — installiert sie NICHT
✅ ToolProvisioner INSTALLIERT — entscheidet NICHT ob er darf

Jede Komponente hat EINE Verantwortung.
```

### DO-02: Fehler sind Daten, keine Ausnahmen
```
✅ Jeder Fehler wird klassifiziert bevor eine Aktion erfolgt
✅ Error-Pattern-Matching passiert EINMAL zentral (ToolRetryStrategy)
✅ RetryDecision ist ein immutable Datenobjekt, kein Control-Flow
✅ Fehlerhistorie wird gespeichert (Telemetry + KnowledgeBase)
```

### DO-03: Defense in Depth für Installationen
```
✅ Layer 1: ProvisioningPolicy (darf ich überhaupt?)
✅ Layer 2: Blocked-Packages-Liste (ist das Package sicher?)
✅ Layer 3: Sandbox-Installation (nur im Workspace, nie global)
✅ Layer 4: Verify nach Installation (hat es funktioniert?)
✅ Layer 5: Rollback bei Problemen (kann ich rückgängig machen?)
```

### DO-04: Progressive Enhancement
```
✅ Level 1 funktioniert OHNE Level 2-5
✅ Level 2 funktioniert OHNE Level 3-5
✅ Jedes Level ist ein eigenständiger Wert-Sprung
✅ Feature-Flags erlauben selektives Aktivieren
✅ Kein Big-Bang — inkrementelles Rollout
```

### DO-05: Testen was schiefgehen KANN, nicht nur was funktioniert
```
✅ Negative Tests: "Was passiert wenn npm NICHT installiert ist?"
✅ Timeout Tests: "Was passiert wenn die Installation 5 Minuten dauert?"
✅ Concurrent Tests: "Was passiert wenn 2 Sessions gleichzeitig installieren?"
✅ Adversarial Tests: "Was passiert wenn der LLM ein bösartiges Script generiert?"
✅ Regression Tests: Jeder gefundene Bug wird ein permanenter Test
```

### DO-06: Observability first
```
✅ Bevor du eine Komponente baust: definiere ihre Events
✅ Jeder Zustandsübergang wird ein Event
✅ Jede Entscheidung wird begründet und geloggt
✅ Telemetry ist nicht optional, sie ist die Grundlage für Debugging
```

### DO-07: Immutable Datenmodelle
```
✅ Alle Decision-Objekte sind frozen dataclasses
✅ Keine Mutation nach Erstellung
✅ Thread-Safe by Design
✅ Serialisierbar für Persistenz und WebSocket-Events
```

### DO-08: Fail fast, recover smart
```
✅ Timeout bei JEDER externen Operation (Command, Install, Web-Search)
✅ Circuit-Breaker bei wiederholten Failures
✅ Graceful Degradation: Wenn Discovery fehlschlägt → Agent arbeitet wie vorher
✅ Niemals endlos retrien: Max-Attempts sind IMMER definiert
```

### DO-09: User im Loop bei kritischen Entscheidungen
```
✅ Installation: User muss bestätigen (außer sandboxed)
✅ Unbekanntes Tool: User wird informiert was der Agent vorhat
✅ Fehlgeschlagene Recovery: User bekommt klare Fehlermeldung + nächste Schritte
✅ WebSocket-Events für Echtzeit-Feedback
```

### DO-10: Knowledge-Base als First-Class-Citizen
```
✅ Jede erfolgreiche Execution füttert die Knowledge-Base
✅ Jede fehlgeschlagene Execution füttert die Knowledge-Base
✅ Knowledge-Base ist die ERSTE Quelle bei Discovery (< 1ms)
✅ Knowledge-Base hat Confidence-Score (nicht blind vertrauen)
✅ Knowledge-Base ist Platform-aware (Win vs Mac vs Linux)
```

---

## 12. DON'Ts — Was wir auf keinen Fall tun dürfen

### DON'T-01: Niemals blind global installieren
```
❌ npm install -g random-package        ← VERBOTEN ohne Policy
❌ pip install random-package            ← VERBOTEN (nutze --user oder venv)
❌ sudo apt install random-package       ← NIEMALS sudo automatisch
❌ choco install random-package          ← NUR mit User-Bestätigung

✅ npm install --save-dev random-package  ← Lokal im Projekt
✅ pip install --target .venv/lib ...     ← In virtuellem Environment
✅ npx --yes random-package              ← Temporär, kein Install
```

### DON'T-02: Niemals LLM-generierten Code ohne Safety-Check ausführen
```
❌ Agent generiert Script → sofort ausführen
✅ Agent generiert Script → Safety-Scan → Sandbox → Verify → Result

Safety-Scan muss prüfen:
- Keine Datei-Löschung außerhalb Workspace
- Keine Network-Requests ohne expliziten Bedarf
- Keine Process-Spawning-Schleifen (Fork-Bomb)
- Keine Environment-Variable-Manipulation
- Keine Crypto/Mining-Patterns
- Keine Credential-Harvesting-Patterns
```

### DON'T-03: Niemals Package-Manager-Output als Beweis akzeptieren
```
❌ "choco install pandoc" sagt "success" → also ist pandoc installiert
✅ "choco install pandoc" sagt "success" → `which pandoc` → tatsächlich da? → Version korrekt?

Package-Manager lügen. Verify IMMER nach Installation.
```

### DON'T-04: Niemals Error-Messages parsen ohne Fallback
```
❌ if "command not found" in stderr:     ← Was wenn die Fehlermeldung auf Deutsch ist?
✅ if error_class == ErrorClass.MISSING_COMMAND:    ← Taxonomie mit multiple Patterns
✅ Fallback: ErrorClass.UNKNOWN wenn nichts matcht   ← Niemals crashen
```

### DON'T-05: Niemals die Retry-Anzahl unbegrenzt lassen
```
❌ while not success: retry()            ← Infinite Loop
✅ for attempt in range(max_retries):    ← Definierte Grenze
✅ Circuit-Breaker nach N Failures       ← Hard-Stop

Max-Retries pro Error-Class:
- TRANSIENT_NETWORK: 3 (mit Backoff)
- MISSING_COMMAND: 1 (install + retry)
- PERMISSION_DENIED: 0 (sofort eskalieren)
- INVALID_ARGS: 2 (mutate + retry)
- UNKNOWN: 1 (einmal probieren, dann eskalieren)
```

### DON'T-06: Niemals Discovery und Installation mischen
```
❌ discover() findet Tool UND installiert es gleich   ← Separation of Concerns
✅ discover() → Kandidaten                            ← Reine Information
✅ select() → Besten Kandidaten wählen                ← Reine Entscheidung
✅ provision() → Installieren mit Policy              ← Separate Aktion
```

### DON'T-07: Niemals ungetestete Regex-Patterns deployen
```
❌ Neues Error-Pattern ohne Unit-Test hinzufügen
✅ Jedes Pattern hat mindestens 2 positive + 1 negative Test-Case
✅ Fuzz-Test mit 100 Random-Strings → kein Crash, kein False-Positive

Error-Regex sind SECURITY-RELEVANT weil sie Retry-Entscheidungen steuern.
```

### DON'T-08: Niemals Telemetry-Daten als Source-of-Truth nutzen
```
❌ "Telemetry sagt pandoc hat 95% Success-Rate, also immer pandoc nehmen"
✅ Telemetry für Beobachtbarkeit + Debugging
✅ KnowledgeBase für Entscheidungen (mit Confidence + min-Samples)

Telemetry ≠ KnowledgeBase. Verschiedene Zwecke, verschiedene Stores.
```

### DON'T-09: Niemals Platform-Detection cachen über Session-Grenzen
```
❌ Platform-Info einmal beim Start → für immer gecacht
✅ Platform-Info pro Session cachen (User könnte WSL starten, Docker installieren, ...)
✅ Package-Manager-Verfügbarkeit bei jedem Provisioning-Call prüfen
```

### DON'T-10: Niemals den User übergehen
```
❌ "Ich habe pandoc, ffmpeg und imagemagick installiert."  ← Nachträglich informieren
✅ "Ich möchte pandoc installieren (choco install pandoc). Erlaubst du das?"
✅ "Installation von pandoc fehlgeschlagen. Soll ich weasyprint versuchen?"
✅ "Ich habe 3 Alternativen gefunden: [pandoc, weasyprint, chrome]. Welche bevorzugst du?"
```

### DON'T-11: Niemals eine Komponente ohne Feature-Flag deployen
```
❌ Neue Retry-Logik direkt aktiv für alle User
✅ tool_retry_strategy_enabled = True (Default ON weil safe)
✅ tool_discovery_enabled = False (Default OFF weil neues Verhalten)
✅ tool_provisioning_enabled = False (Default OFF weil system-modifizierend)
```

### DON'T-12: Niemals Retry und Replan verwechseln
```
❌ Tool schlägt fehl → neuen Plan machen    ← Replan ist teuer (LLM-Call)
✅ Tool schlägt fehl → Fehler klassifizieren → Retry-Strategie wählen
✅ Retry erschöpft → DANN erst Replan erwägen
✅ Replan nur wenn die Aufgabe ANDERS angegangen werden muss

Retry = gleiche Aufgabe, andere Ausführung
Replan = andere Aufgabe, anderer Ansatz
```

### DON'T-13: Niemals synchrone Blockierung bei Installationen
```
❌ await install("pandoc")  ← UI friert ein für 2 Minuten
✅ Start install → Progress-Events über WebSocket → Completion-Event
✅ UI zeigt: "Installing pandoc... [████████░░] 80%"
✅ User kann Cancel drücken → kill install process
```

### DON'T-14: Niemals das Workspace-Backup vergessen
```
❌ Agent installiert npm package → node_modules/ ist 500MB → Disk voll
✅ VOR Installation: Freien Speicher prüfen
✅ VOR Installation: package.json / requirements.txt sichern
✅ Bei Fehler: Restore auf vorherigen Stand
```

---

## 13. Risiken & Mitigations

| # | Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | LLM schlägt bösartiges Package vor | Mittel | Hoch | Blocked-Packages-Liste + Safety-Scan + User-Approval |
| R-02 | Installation bricht Workspace | Niedrig | Hoch | Environment-Snapshot + Rollback + Sandbox |
| R-03 | Retry-Loop frisst Token-Budget | Mittel | Mittel | Max-Retries + Circuit-Breaker + Budget-Tracking in Telemetry |
| R-04 | Error-Regex matcht False-Positive | Mittel | Mittel | Exhaustive Tests + Fuzz-Tests + gradual Rollout via Feature-Flag |
| R-05 | Discovery findet nur veraltete Tools | Niedrig | Niedrig | Recency-Score in KnowledgeBase + regelmäßige Web-Search |
| R-06 | Race-Condition bei concurrent Install | Niedrig | Mittel | File-Lock auf Install-Prozess + Atomic-Write in KnowledgeBase |
| R-07 | Platform-Detection ist falsch (WSL vs Native) | Niedrig | Mittel | Multi-Signal-Detection + User-Override in Settings |
| R-08 | Telemetry-DB wächst unbegrenzt | Mittel | Niedrig | TTL (7 Tage) + Max-Size-Check + Auto-Vacuum |
| R-09 | User klickt "Ja" ohne zu lesen | Hoch | Mittel | Klare Beschreibung WAS installiert wird + Umfang + Reversibilität |
| R-10 | SelfHealingLoop läuft in Endlosschleife | Niedrig | Hoch | Max 3 Recovery-Versuche, dann Hard-Stop + Eskalation |

---

## 14. Testing-Strategie

### Test-Pyramide

```
        ╱ E2E Tests (5-10 pro Level) ╲
       ╱   "User sagt X, Agent tut Y"  ╲
      ╱─────────────────────────────────╲
     ╱  Integration Tests (10-20 pro      ╲
    ╱    Level) "Komponente A + B zusammen" ╲
   ╱─────────────────────────────────────────╲
  ╱     Unit Tests (30-50 pro Level)           ╲
 ╱       "Eine Funktion, ein Verhalten"         ╲
╱───────────────────────────────────────────────╲
         Property Tests (10 pro Level)
     "Für alle Inputs X gilt Eigenschaft Y"
```

### Test-Konventionen

```python
# Datei-Naming
tests/test_tool_retry_strategy.py
tests/test_tool_outcome_verifier.py
tests/test_tool_telemetry.py
tests/test_tool_knowledge_base.py
tests/test_tool_discovery_engine.py
tests/test_package_manager_adapter.py
tests/test_tool_provisioner.py
tests/test_adaptive_tool_selector.py

# Test-Naming: test_{was}_{szenario}_{erwartung}
def test_classify_error_command_not_found_returns_missing_command(): ...
def test_classify_error_random_string_returns_unknown(): ...
def test_verify_outcome_file_exists_passes_when_file_present(): ...
def test_verify_outcome_file_exists_fails_when_file_missing(): ...

# Keine Mocks für Datenmodelle — echte frozen Dataclasses nutzen
# Mocks nur für: LLM-Calls, File-System, Subprocess, Network
```

### Kritische Test-Szenarien

| Szenario | Typ | Was wird getestet |
|---|---|---|
| `stderr = "pandoc: command not found"` → `MISSING_COMMAND` | Unit | Error-Klassifikation |
| `stderr = "error in error handling"` → NICHT als Error klassifiziert | Unit | False-Positive-Schutz |
| `exit_code=0, file missing` → Verdict FAIL | Unit | Outcome-Verification |
| `exit_code=1, file exists, size>0` → Verdict PASS (Warnings in stderr sind ok) | Unit | Toleranz für stderr-Noise |
| 100 Random-Strings → kein Crash in `classify_error()` | Property | Robustheit |
| Concurrent `learn_from_success()` → DB konsistent | Integration | Thread-Safety |
| Discovery mit `tool_discovery_enabled=False` → Bypass | Integration | Feature-Flag |
| Install → Verify fail → Rollback → Clean state | E2E | Provisioning-Pipeline |
| Agent findet pandoc in KnowledgeBase → kein Web-Search | E2E | Performance-Optimierung |

---

## 15. Migration & Backwards Compatibility

### Phase 1: Additive (Level 1)
```
- Neue Dateien hinzufügen (kein bestehender Code geändert)
- Feature-Flags auf True (safe weil nur bessere Klassifikation)
- Bestehender `_run_tool_with_policy` ruft zusätzlich RetryStrategy auf
- Bestehender `verify_tool_result` wird NICHT gelöscht, nur ergänzt
```

### Phase 2: Integration (Level 2-3)
```
- ToolExecutionManager bekommt optionale Discovery/Provisioner-Injection
- Wenn nicht injected → Verhalten identisch zu heute
- Neue WebSocket-Events für Install-Approval (bestehendes WS unberührt)
- KnowledgeBase-SQLite neben bestehender LTM-SQLite
```

### Phase 3: Enhancement (Level 4-5)
```
- AdaptiveToolSelector ersetzt Standard-Selection nur wenn Flag aktiv
- SelfHealingLoop wird nur aktiviert wenn alle Retries erschöpft UND Flag aktiv
- ToolSynthesizer nutzt bestehende CodeSandbox (kein neuer Executor)
```

### Rollback-Plan
```
Jedes Level kann sofort deaktiviert werden:
  tool_retry_strategy_enabled: false
  tool_outcome_verifier_enabled: false
  tool_telemetry_enabled: false
  tool_discovery_enabled: false
  tool_provisioning_enabled: false
  adaptive_tool_selection_enabled: false
  tool_chain_planning_enabled: false
  execution_pattern_detection_enabled: false
  tool_synthesizer_enabled: false
  self_healing_enabled: false

→ Agent verhält sich exakt wie vor der Änderung.
```

---

## 16. Metriken für Erfolg

### Quantitative Metriken

| Metrik | Baseline (heute) | Ziel L1 | Ziel L2-3 | Ziel L4-5 |
|---|---|---|---|---|
| **Error-Recovery-Rate** (% der Fehler die automatisch behoben werden) | ~5% (nur web_fetch 404) | 30% | 60% | 85% |
| **Outcome-Verification-Accuracy** (% korrekte Verdicts) | ~40% (Substring-Matching) | 90% | 95% | 98% |
| **First-Attempt-Success-Rate** (% Tools die beim 1. Mal klappen) | ~70% | 75% | 85% | 92% |
| **Mean-Time-to-Tool** (Sekunden bis ein unbekanntes Tool nutzbar ist) | ∞ (gibt auf) | ∞ | 15s | 8s |
| **User-Escalation-Rate** (% wo User eingreifen muss) | ~20% | 15% | 8% | 3% |
| **False-Positive-Error-Rate** (% Fehler die fälschlich als Fehler klassifiziert werden) | ~15% | < 3% | < 2% | < 1% |

### Qualitative Metriken

| Metrik | Wie messen |
|---|---|
| **User-Trust** — Vertraut der User dem Agent bei Installationen? | Post-Install-Survey / Approval-Rate |
| **Agent-Autonomie** — Kann der Agent eine komplexe Aufgabe OHNE User-Input lösen? | E2E-Benchmark mit 20 Szenarien |
| **Knowledge-Retention** — Wiederholt der Agent Fehler die er schon gelöst hat? | KnowledgeBase-Hit-Rate über Sessions |
| **Graceful-Degradation** — Wie verhält sich der Agent bei Flag-Deaktivierung? | A/B-Test: Flags on vs. off |

---

## Anhang A: Feature-Flag-Übersicht

| Flag | Default | Level | Risiko bei ON |
|---|---|---|---|
| `tool_retry_strategy_enabled` | `True` | L1 | Keins (nur bessere Klassifikation) |
| `tool_outcome_verifier_enabled` | `True` | L1 | Keins (nur bessere Prüfung) |
| `tool_telemetry_enabled` | `True` | L1 | Minimal (SQLite-Write pro Tool-Call) |
| `tool_discovery_enabled` | `False` | L2 | Mittel (LLM + Web-Search Calls) |
| `tool_provisioning_enabled` | `False` | L3 | Hoch (System-Modifikation) |
| `provisioning_policy_mode` | `"ask_user"` | L3 | Governance-Entscheidung |
| `adaptive_tool_selection_enabled` | `False` | L4 | Niedrig (nur Scoring-Änderung) |
| `tool_chain_planning_enabled` | `False` | L4 | Niedrig (nur Planning) |
| `execution_pattern_detection_enabled` | `True` | L4 | Keins (nur Detection + Warn) |
| `tool_synthesizer_enabled` | `False` | L5 | Hoch (LLM-Code wird ausgeführt) |
| `self_healing_enabled` | `False` | L5 | Mittel (autonome Recovery) |

## Anhang B: File-Mapping

```
backend/app/services/
├── tool_retry_strategy.py            # L1 — 300-400 LOC
├── tool_outcome_verifier.py          # L1 — 250-350 LOC
├── tool_telemetry.py                 # L1 — 200-300 LOC
├── tool_knowledge_base.py            # L2 — 200-300 LOC
├── tool_discovery_engine.py          # L2 — 400-500 LOC
├── package_manager_adapter.py        # L2 — 300-400 LOC
├── platform_info.py                  # L2 — 100-150 LOC
├── tool_provisioner.py               # L3 — 300-400 LOC
├── provisioning_policy.py            # L3 — 100-150 LOC
├── adaptive_tool_selector.py         # L4 — 150-200 LOC
├── tool_chain_planner.py             # L4 — 200-300 LOC
├── execution_pattern_detector.py     # L4 — 200-300 LOC
├── tool_synthesizer.py               # L5 — 300-400 LOC
├── self_healing_loop.py              # L5 — 300-400 LOC
└── tool_ecosystem_map.py             # L5 — 150-200 LOC

backend/tests/
├── test_tool_retry_strategy.py       # 40-60 Tests
├── test_tool_outcome_verifier.py     # 30-50 Tests
├── test_tool_telemetry.py            # 20-30 Tests
├── test_tool_knowledge_base.py       # 20-30 Tests
├── test_tool_discovery_engine.py     # 20-30 Tests
├── test_package_manager_adapter.py   # 15-25 Tests
├── test_platform_info.py            # 10-15 Tests
├── test_tool_provisioner.py          # 20-30 Tests
├── test_provisioning_policy.py       # 10-15 Tests
├── test_adaptive_tool_selector.py    # 15-20 Tests
├── test_tool_chain_planner.py        # 15-20 Tests
├── test_execution_pattern_detector.py # 15-20 Tests
├── test_tool_synthesizer.py          # 20-30 Tests
└── test_self_healing_loop.py         # 15-20 Tests

Gesamt neuer Code: ~3.500-5.000 LOC Produktion + ~3.000-4.000 LOC Tests
```

## Anhang C: Dependency-Graph

```
                    ToolExecutionManager (bestehend)
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ToolRetryStrategy   ToolOutcome    ToolTelemetry
         (L1)          Verifier(L1)      (L1)
              │              │              │
              └──────┬───────┘              │
                     │                      │
              ToolDiscoveryEngine ──────────┘
                   (L2)
              ┌────┤
              │    │
    ToolKnowledge  PackageManager   PlatformInfo
    Base (L2)      Adapter (L2)       (L2)
              │         │
              └────┬────┘
                   │
             ToolProvisioner ──── ProvisioningPolicy
                  (L3)                 (L3)
                   │
          AdaptiveToolSelector
                  (L4)
              ┌────┤
              │    │
    ToolChain  ExecutionPattern
    Planner    Detector
     (L4)       (L4)
                   │
              ┌────┴────┐
              │         │
        ToolSynthe   SelfHealing
        sizer(L5)    Loop(L5)
              │
        ToolEcosystem
        Map(L5)
```

Jede Ebene hängt NUR von der darunter ab. Keine Zyklen. Jedes Level ist eigenständig deployable.
