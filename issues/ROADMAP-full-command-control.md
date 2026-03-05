# Roadmap: Full Command Control — Autonomous Tool Discovery & Execution

> **Ziel:** Der Agent kann *jedes* denkbare Kommando autonom finden, installieren, ausführen, verifizieren und daraus lernen — egal ob `npm`, `pip`, `cargo`, `dotnet`, `kubectl`, `ffmpeg`, `imagemagick`, `pandoc` oder ein bisher unbekanntes CLI-Tool.

---

## Status Quo — Was wir haben

| Baustein | Status | File |
|---|---|---|
| **ToolSpec** (Schema) | ✅ Vorhanden | `services/tool_registry.py` — frozen dataclass mit `name`, `capabilities`, `parameters`, `timeout`, `max_retries` |
| **ToolRegistry** (Catalog) | ✅ Vorhanden | 18 statische Tools + MCP-Bridge für dynamische Specs |
| **ToolExecutor** (Runtime) | ✅ Vorhanden | `tools.py` — `AgentTooling` mit `run_command`, sandbox, web, FS |
| **ToolPolicy** (Safety) | ✅ Vorhanden | `tool_policy.py` + 22 destructive-command-Regex-Patterns + allowlist |
| **ToolRetry** | ⚠️ Rudimentär | 1-Shot-Retry nur für web_fetch 404; kein generisches Framework |
| **ToolOutcomeVerifier** | ⚠️ Rudimentär | `verify_tool_result` = naives Substring-Matching (`" error"` / `"[ok]"`) |
| **ToolTelemetry** | ⚠️ Events only | ~30 Lifecycle-Events, aber keine Aggregation/Persistenz/Dashboards |
| **ToolDiscovery** (auto-find) | ❌ Fehlt | Agent kann keine unbekannten Tools/Packages autonom finden + installieren |
| **ToolDependencyGraph** | ❌ Fehlt | Kein formales DAG-Modell für Tool-Abhängigkeiten |
| **AdaptiveToolSelection** | ❌ Fehlt | Kein Feedback-Loop von Outcomes → Selection-Heuristik |

---

## Das Szenario, das alles triggert

```
User: "Kannst du diesen Text als PDF visualisieren?"

Agent denkt:
  1. Ich brauche ein Tool das Text → PDF konvertiert
  2. Habe ich eins? → Nein
  3. Was gibt es? → pandoc, wkhtmltopdf, puppeteer, weasyprint...
  4. Welches passt am besten? → pandoc (leichtgewichtig, CLI)
  5. Ist es installiert? → `which pandoc` → Nein
  6. Kann ich es installieren? → Policy prüfen → Ja, mit User-Confirm
  7. Installation → `apt install pandoc` / `choco install pandoc` / `brew install pandoc`
  8. Ausführen → `pandoc input.md -o output.pdf`
  9. Hat es funktioniert? → Datei existiert? Größe > 0? PDF-Header gültig?
  10. Nein? → Alternativen probieren (weasyprint, wkhtmltopdf)
  11. Ja? → Ergebnis liefern + Wissen speichern für nächstes Mal
```

**Das ist Full Command Control.** Jeder dieser 11 Schritte braucht eine eigene Architektur-Schicht.

---

## Architektur: Die 8 Säulen

```
┌─────────────────────────────────────────────────────────┐
│                    USER REQUEST                         │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  1. ToolIntentResolver                                  │
│     "Was will der User?" → Required Capabilities        │
│     + Semantic Mapping: "PDF erzeugen" → capability:    │
│       document_conversion                               │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  2. ToolDiscoveryEngine                                 │
│     "Welches Tool kann das?" → Kandidaten-Liste         │
│     Sources: Registry, Knowledge-Base, Web-Search,      │
│              Package-Managers, LLM-Reasoning            │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  3. ToolProvisioner                                     │
│     "Ist es da? Wenn nein, installieren."               │
│     Checks: which/where, version, compatibility         │
│     Actions: install, configure, verify-install          │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  4. ToolExecutor (enhanced)                             │
│     "Ausführen mit Isolation + Timeout + Streaming"     │
│     Sandbox, Resource Limits, Process Management        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  5. ToolRetryOrchestrator                               │
│     "Fehlgeschlagen? Warum? Was jetzt?"                 │
│     Reason-aware: parse error → select strategy         │
│     Backoff, Alternative Tools, Parameter Mutation       │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  6. ToolOutcomeVerifier                                 │
│     "Hat es funktioniert? Semantisch korrekt?"          │
│     File-exists, Content-type, Size, Diff, LLM-Judge    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  7. ToolTelemetry                                       │
│     "Was ist passiert? Wie lange? Was hat es gekostet?"  │
│     Traces, Metrics, Cost, Audit-Log                    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  8. ToolMemory (Learning Loop)                          │
│     "Für nächstes Mal merken"                           │
│     Success patterns, failure patterns, preferred tools  │
└─────────────────────────────────────────────────────────┘
```

---

## Level 1 — Foundation: Reason-Aware Retry + Structured Outcomes

> **Impact: Sofort höhere Zuverlässigkeit für bestehende 18 Tools**

### 1.1 `ToolRetryStrategy` — Reason-Aware Retry Engine

**Problem:** Aktuell nur 1-Shot-Retry für web_fetch 404. Kein Verständnis *warum* etwas fehlschlägt.

```python
@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    strategy: str           # "backoff" | "mutate_args" | "alternative_tool" | "escalate"
    delay_seconds: float
    mutated_args: dict[str, Any] | None
    alternative_tool: str | None
    reason: str

class ToolRetryStrategy:
    """Analysiert Fehler und entscheidet die optimale Retry-Strategie."""

    # Error-Pattern → Strategy Mapping
    RETRY_PATTERNS: list[tuple[re.Pattern, str, str]] = [
        # Transient errors → exponential backoff
        (re.compile(r"connection refused|timeout|ECONNRESET|503|429", re.I),
         "backoff", "transient_network"),

        # Missing dependency → install + retry
        (re.compile(r"command not found|not recognized|'(\w+)' is not", re.I),
         "install_and_retry", "missing_command"),

        # Permission errors → escalate or alternative
        (re.compile(r"permission denied|access denied|EACCES", re.I),
         "escalate", "permission_denied"),

        # Wrong arguments → mutate args
        (re.compile(r"invalid option|unknown flag|unrecognized argument", re.I),
         "mutate_args", "invalid_args"),

        # Package not found → try alternative package manager
        (re.compile(r"no such package|package .+ not found|E: Unable to locate", re.I),
         "alternative_tool", "package_not_found"),

        # File not found → check path + retry
        (re.compile(r"no such file|ENOENT|FileNotFoundError", re.I),
         "mutate_args", "file_not_found"),
    ]

    def classify_error(self, stderr: str, exit_code: int) -> RetryDecision:
        ...

    def with_backoff(self, attempt: int, base_delay: float = 1.0) -> float:
        """Exponential backoff: 1s, 2s, 4s, max 30s"""
        return min(base_delay * (2 ** attempt), 30.0)
```

**Key Pattern: Error Taxonomy Tree**
```
ToolError
├── TransientError        → retry with backoff
│   ├── NetworkTimeout
│   ├── RateLimited (429)
│   └── ServiceUnavailable (503)
├── MissingDependency     → discover + install + retry
│   ├── CommandNotFound
│   ├── ModuleNotFound
│   └── LibraryMissing
├── PermissionError       → escalate to user
├── InvalidArguments      → mutate args + retry
│   ├── UnknownFlag
│   ├── WrongType
│   └── MissingRequired
├── ResourceError         → wait or reduce scope
│   ├── DiskFull
│   ├── OutOfMemory
│   └── PortInUse
└── SemanticError         → try alternative tool
    ├── UnsupportedFormat
    ├── VersionMismatch
    └── IncompatiblePlatform
```

### 1.2 `ToolOutcomeVerifier` — Expected-Effect Checks

**Problem:** `verify_tool_result` prüft nur ob `" error"` im Output steht. Keine semantische Prüfung.

```python
@dataclass(frozen=True)
class OutcomeExpectation:
    """Was wir nach der Tool-Ausführung erwarten."""
    file_exists: str | None = None           # Pfad der existieren sollte
    file_min_size: int | None = None         # Min. Bytes
    file_content_type: str | None = None     # "application/pdf", "image/png"
    stdout_contains: str | None = None       # Erwarteter Output-Substring
    stdout_regex: str | None = None          # Regex für Output
    exit_code: int = 0                       # Erwarteter Exit-Code
    env_var_set: str | None = None           # Env-Variable die gesetzt sein sollte
    process_running: str | None = None       # Prozessname der laufen sollte
    custom_check: str | None = None          # LLM-basierte semantische Prüfung

class ToolOutcomeVerifier:
    """Prüft ob eine Tool-Ausführung den erwarteten Effekt hatte."""

    async def verify(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        exit_code: int,
        expectation: OutcomeExpectation,
        workspace_root: str,
    ) -> OutcomeVerdict:
        checks: list[CheckResult] = []

        if expectation.file_exists:
            path = resolve_path(expectation.file_exists, workspace_root)
            exists = os.path.isfile(path)
            size = os.path.getsize(path) if exists else 0
            checks.append(CheckResult(
                check="file_exists",
                passed=exists and (expectation.file_min_size is None or size >= expectation.file_min_size),
                detail=f"exists={exists}, size={size}",
            ))

        if expectation.exit_code is not None:
            checks.append(CheckResult(
                check="exit_code",
                passed=exit_code == expectation.exit_code,
                detail=f"expected={expectation.exit_code}, actual={exit_code}",
            ))

        if expectation.stdout_regex:
            match = re.search(expectation.stdout_regex, result)
            checks.append(CheckResult(
                check="stdout_regex",
                passed=match is not None,
                detail=f"pattern={expectation.stdout_regex}, matched={match is not None}",
            ))

        # ... weitere Checks

        passed = all(c.passed for c in checks)
        return OutcomeVerdict(passed=passed, checks=checks)
```

### 1.3 `ToolTelemetry` — Structured Events + Metrics

**Problem:** Events werden emittiert aber nirgends aggregiert. Kein Tracing.

```python
@dataclass
class ToolSpan:
    """Ein einzelner Tool-Ausführungs-Span im Trace."""
    span_id: str
    parent_span_id: str | None
    tool_name: str
    args_hash: str
    start_time: float
    end_time: float | None = None
    exit_code: int | None = None
    retry_count: int = 0
    outcome: str = "pending"            # "success" | "failed" | "retried" | "skipped"
    error_class: str | None = None      # Aus Error Taxonomy
    tokens_consumed: int = 0
    cost_estimate_usd: float = 0.0

class ToolTelemetry:
    """Aggregiert Tool-Execution-Metriken für Observability."""

    def __init__(self, store: TelemetryStore):
        self._store = store
        self._active_spans: dict[str, ToolSpan] = {}

    def start_span(self, tool_name: str, args: dict, parent: str | None = None) -> str: ...
    def end_span(self, span_id: str, outcome: str, exit_code: int | None = None) -> None: ...
    def record_retry(self, span_id: str, reason: str) -> None: ...

    def get_tool_stats(self) -> dict[str, ToolStats]:
        """Aggregierte Stats pro Tool: success_rate, avg_duration, retry_rate."""
        ...

    def get_session_trace(self, session_id: str) -> list[ToolSpan]:
        """Alle Spans einer Session als Trace-Baum."""
        ...
```

**Deliverables Level 1:**
- [ ] `ToolRetryStrategy` mit Error-Taxonomy + Backoff
- [ ] `ToolOutcomeVerifier` mit Expected-Effect-Checks
- [ ] `ToolTelemetry` mit Span-Tracing
- [ ] Integration in `ToolExecutionManager` Execute-Loop
- [ ] Tests für alle Error-Patterns

---

## Level 2 — Discovery: Autonomous Tool Finding

> **Impact: Agent kann unbekannte Tools finden und vorschlagen**

### 2.1 `ToolDiscoveryEngine` — Multi-Source Tool Finder

Das Herzstück von "Full Command Control". Der Agent findet Tools die er noch nicht kennt.

```python
class ToolDiscoveryEngine:
    """Findet Tools für eine gegebene Capability aus mehreren Quellen."""

    def __init__(
        self,
        *,
        knowledge_base: ToolKnowledgeBase,
        web_searcher: WebSearchProvider,
        llm_client: LLMClient,
        package_managers: list[PackageManagerAdapter],
    ):
        ...

    async def discover(
        self,
        *,
        capability_needed: str,           # "convert_markdown_to_pdf"
        context: str,                     # User-Request + bisheriger Plan
        platform: PlatformInfo,           # OS, arch, available package managers
        constraints: DiscoveryConstraints, # max_search_time, prefer_lightweight, etc.
    ) -> list[ToolCandidate]:
        """
        Discovery-Pipeline:
        1. Local Knowledge-Base check (Cached solutions)
        2. LLM-Reasoning (Was weiß das Modell über passende Tools?)
        3. Package-Manager search (npm search, pip search, apt search)
        4. Web-Search fallback (für exotische Tools)
        5. Ranking + Dedup
        """
        candidates: list[ToolCandidate] = []

        # Phase 1: Knowledge Base (< 1ms)
        cached = await self._knowledge_base.find_tools_for_capability(capability_needed)
        candidates.extend(cached)

        # Phase 2: LLM Reasoning (~ 1-3s)
        if not candidates or not any(c.confidence > 0.8 for c in candidates):
            llm_suggestions = await self._llm_suggest_tools(capability_needed, context, platform)
            candidates.extend(llm_suggestions)

        # Phase 3: Package Manager Search (~ 2-5s)
        if not candidates or not any(c.confidence > 0.7 for c in candidates):
            for pm in self._package_managers:
                if pm.is_available():
                    pm_results = await pm.search(capability_needed)
                    candidates.extend(pm_results)

        # Phase 4: Web Search Fallback (~ 3-8s)
        if not candidates:
            web_results = await self._web_search_for_tools(capability_needed, platform)
            candidates.extend(web_results)

        # Deduplizieren + Ranken
        return self._rank_and_dedupe(candidates, platform, constraints)
```

### 2.2 `ToolKnowledgeBase` — Gewusst-Wie-Speicher

```python
class ToolKnowledgeBase:
    """
    Persistenter Wissensspeicher: "Für Aufgabe X nutze Tool Y mit Argumenten Z."

    Lernt aus jeder erfolgreichen Tool-Ausführung.
    """

    # Schema für Knowledge-Einträge
    @dataclass
    class ToolKnowledge:
        capability: str              # "convert_markdown_to_pdf"
        tool_command: str            # "pandoc"
        install_command: str         # "apt install pandoc" / "choco install pandoc"
        usage_pattern: str           # "pandoc {input} -o {output}"
        platform: str                # "linux" | "darwin" | "win32"
        package_manager: str         # "apt" | "brew" | "choco" | "npm" | "pip"
        success_count: int           # Wie oft hat das funktioniert
        failure_count: int
        last_used: datetime
        avg_duration_seconds: float
        confidence: float            # success_count / (success_count + failure_count)
        tags: list[str]              # ["pdf", "document", "conversion"]

    async def learn_from_outcome(self, execution: ToolSpan, verdict: OutcomeVerdict) -> None:
        """Nach jeder Ausführung: Wissen aktualisieren."""
        ...

    async def find_tools_for_capability(self, capability: str) -> list[ToolCandidate]:
        """Semantische Suche nach bekannten Lösungen."""
        ...
```

### 2.3 `PackageManagerAdapter` — Unified Package Manager Interface

```python
class PackageManagerAdapter(Protocol):
    """Einheitliches Interface für beliebige Package-Manager."""

    def name(self) -> str: ...                           # "npm", "pip", "apt", "brew", "choco"
    def is_available(self) -> bool: ...                   # `which npm` → True/False
    async def search(self, query: str) -> list[ToolCandidate]: ...
    async def install(self, package: str) -> InstallResult: ...
    async def is_installed(self, package: str) -> bool: ...
    async def get_version(self, package: str) -> str | None: ...
    async def uninstall(self, package: str) -> bool: ...

# Konkrete Adapter
class NpmAdapter(PackageManagerAdapter): ...
class PipAdapter(PackageManagerAdapter): ...
class AptAdapter(PackageManagerAdapter): ...
class BrewAdapter(PackageManagerAdapter): ...
class ChocoAdapter(PackageManagerAdapter): ...
class CargoAdapter(PackageManagerAdapter): ...
class WingetAdapter(PackageManagerAdapter): ...
```

### 2.4 `PlatformInfo` — OS/Environment Detection

```python
@dataclass(frozen=True)
class PlatformInfo:
    os: str                          # "win32" | "linux" | "darwin"
    arch: str                        # "x64" | "arm64"
    shell: str                       # "powershell" | "bash" | "zsh"
    available_package_managers: tuple[str, ...]  # ("npm", "pip", "choco")
    installed_runtimes: dict[str, str]           # {"node": "20.11", "python": "3.12"}
    docker_available: bool
    wsl_available: bool              # Windows only

    @classmethod
    async def detect(cls) -> PlatformInfo:
        """Auto-detect platform capabilities."""
        ...
```

**Deliverables Level 2:**
- [ ] `ToolDiscoveryEngine` mit 4-Phasen-Pipeline
- [ ] `ToolKnowledgeBase` (SQLite-backed)
- [ ] `PackageManagerAdapter` für npm, pip, apt/brew/choco
- [ ] `PlatformInfo` auto-detection
- [ ] Integration in Planner: "Tool nicht gefunden → Discovery triggern"

---

## Level 3 — Provisioning: Autonomous Install + Configure

> **Impact: Agent installiert fehlende Tools selbständig**

### 3.1 `ToolProvisioner` — Install + Verify Pipeline

```python
class ToolProvisioner:
    """
    Autonome Installation von Tools.
    
    Ablauf:
    1. Prüfe ob Tool schon installiert
    2. Finde passenden Package-Manager
    3. Policy-Check: Darf ich installieren?
    4. Installiere
    5. Verifiziere Installation
    6. Registriere in Knowledge-Base
    """

    async def ensure_available(
        self,
        *,
        tool_name: str,
        install_hint: str | None = None,
        platform: PlatformInfo,
        policy: ProvisioningPolicy,
    ) -> ProvisionResult:

        # 1. Schon da?
        if await self._is_available(tool_name):
            return ProvisionResult(status="already_available", tool=tool_name)

        # 2. Package-Manager finden
        install_plan = await self._resolve_install_plan(tool_name, install_hint, platform)
        if not install_plan:
            return ProvisionResult(status="no_install_path", tool=tool_name)

        # 3. Policy check
        if not policy.allows_install(install_plan):
            if policy.mode == "ask_user":
                approved = await self._request_user_approval(install_plan)
                if not approved:
                    return ProvisionResult(status="user_denied", tool=tool_name)
            else:
                return ProvisionResult(status="policy_denied", tool=tool_name)

        # 4. Install
        result = await self._execute_install(install_plan)

        # 5. Verify
        if result.success:
            available = await self._is_available(tool_name)
            if not available:
                # Installation reported success but tool not found
                # Try alternative install methods
                return await self._try_alternatives(tool_name, platform, policy)

        return result
```

### 3.2 `ProvisioningPolicy` — Governance für Installationen

```python
@dataclass(frozen=True)
class ProvisioningPolicy:
    mode: str                    # "auto" | "ask_user" | "deny"
    allowed_package_managers: frozenset[str]  # ("npm", "pip")
    blocked_packages: frozenset[str]          # ("rm-rf-star",)
    max_install_size_mb: int                  # 500
    require_version_pin: bool                 # True = nur spezifische Versionen
    allowed_scopes: frozenset[str]            # ("user", "project") — kein "global"
    sandbox_install: bool                     # True = installiere in venv/node_modules
```

**Key Design Pattern: Install Sandboxing**
```
Jede Installation läuft in einem isolierten Scope:
- Python: venv im Workspace
- Node: lokale node_modules
- System: Nur wenn Policy erlaubt + User bestätigt
- Docker: Fallback für alles andere

Niemals blind `sudo apt install X`!
```

**Deliverables Level 3:**
- [ ] `ToolProvisioner` mit Install-Verify Pipeline
- [ ] `ProvisioningPolicy` Governance
- [ ] Sandbox-Install-Strategien (venv, node_modules, Docker)
- [ ] User-Approval-Flow über WebSocket
- [ ] Rollback-Capability (deinstallieren wenn etwas kaputt geht)

---

## Level 4 — Intelligence: Adaptive Selection + Learning Loop

> **Impact: Agent wird mit jeder Ausführung schlauer**

### 4.1 `AdaptiveToolSelector` — Feedback-Driven Selection

```python
class AdaptiveToolSelector:
    """
    Wählt Tools nicht nur nach Capabilities, sondern nach
    historischer Erfolgsrate, Geschwindigkeit und User-Präferenz.
    """

    async def select_best_tool(
        self,
        *,
        capability: str,
        candidates: list[ToolCandidate],
        context: SelectionContext,
    ) -> ToolCandidate:
        """
        Ranking-Faktoren:
        1. Historical success_rate (40%)
        2. Average execution time (20%)
        3. Platform compatibility (15%)
        4. User preference history (15%)
        5. Recency of last success (10%)
        """
        scored = []
        for candidate in candidates:
            stats = await self._knowledge_base.get_stats(candidate.tool_command)
            score = (
                (stats.success_rate * 0.40) +
                (self._time_score(stats.avg_duration) * 0.20) +
                (self._platform_score(candidate, context.platform) * 0.15) +
                (self._preference_score(candidate, context.user_prefs) * 0.15) +
                (self._recency_score(stats.last_success) * 0.10)
            )
            scored.append((score, candidate))

        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[0][1]
```

### 4.2 `ToolChainPlanner` — Multi-Step Tool Orchestration

Manche Aufgaben brauchen eine *Kette* von Tools:

```python
class ToolChainPlanner:
    """
    Plant Tool-Ketten für komplexe Aufgaben.

    Beispiel: "Konvertiere dieses LaTeX zu einem Bild"
    → Chain: [latex → pdf (pdflatex), pdf → png (ImageMagick convert)]
    """

    async def plan_chain(
        self,
        *,
        input_type: str,       # "text/latex"
        output_type: str,      # "image/png"
        context: str,
    ) -> ToolChain:
        """
        Findet den kürzesten Pfad im Format-Konvertierungs-Graph:

        text/markdown → text/html → application/pdf → image/png
                    ↘ application/pdf ↗
        """
        graph = await self._build_conversion_graph()
        path = self._shortest_path(graph, input_type, output_type)
        return ToolChain(steps=[
            ToolChainStep(
                tool=edge.tool,
                input_type=edge.source,
                output_type=edge.target,
            )
            for edge in path
        ])
```

### 4.3 `ExecutionPatternDetector` — Anti-Pattern Erkennung

```python
class ExecutionPatternDetector:
    """
    Erkennt problematische Ausführungs-Muster und schlägt Verbesserungen vor.
    
    Patterns:
    - "Brute Force Install": Agent probiert 5 Package-Manager nacheinander
      → Merke welcher funktioniert hat für nächstes Mal
    - "Version Roulette": Agent probiert random Versionen
      → Schlage LTS/stable vor
    - "Path Thrashing": Agent sucht eine Datei in 10 verschiedenen Pfaden
      → Nutze file_search zuerst
    - "Retry Without Change": Gleicher Command wird 3x probiert
      → Erkenne + stoppe + analysiere
    """
```

**Deliverables Level 4:**
- [ ] `AdaptiveToolSelector` mit gewichtetem Scoring
- [ ] `ToolChainPlanner` für Multi-Step Konvertierungen
- [ ] `ExecutionPatternDetector` Anti-Patterns
- [ ] Learning Loop: Outcomes → KnowledgeBase → bessere Selection

---

## Level 5 — Mastery: Full Autonomy + Self-Healing

> **Impact: Agent handelt vollständig autonom bei beliebigen Aufgaben**

### 5.1 `ToolSynthesizer` — Dynamische Tool-Erstellung

Wenn kein bestehendes Tool passt, *erstellt* der Agent eins:

```python
class ToolSynthesizer:
    """
    Erstellt ad-hoc Scripts/Tools wenn kein bestehendes Tool die Aufgabe erfüllt.

    Beispiel: User will "alle Bilder in einem Ordner auf 50% skalieren"
    → Kein single CLI-Command macht das
    → Agent generiert ein Python-Script:
       from PIL import Image; [resize for f in glob("*.png")]
    → Führt es in Sandbox aus
    → Verifiziert Ergebnis
    """

    async def synthesize(
        self,
        *,
        task_description: str,
        available_runtimes: list[str],    # ["python", "node", "bash"]
        workspace_root: str,
        constraints: SynthesisConstraints,
    ) -> SynthesizedTool:
        # 1. LLM generiert Script
        script = await self._generate_script(task_description, available_runtimes)
        # 2. Safety-Check: kein rm -rf, kein network access wenn nicht nötig
        safety = await self._safety_check(script)
        # 3. Sandbox-Execution
        result = await self._execute_in_sandbox(script)
        # 4. Outcome-Verification
        verdict = await self._verify_outcome(result, task_description)
        return SynthesizedTool(script=script, result=result, verdict=verdict)
```

### 5.2 `SelfHealingLoop` — Autonomous Error Recovery

```python
class SelfHealingLoop:
    """
    Wenn alles andere fehlschlägt:
    1. Analysiere Error-History des aktuellen Tasks
    2. Identifiziere Root-Cause via LLM
    3. Generiere Recovery-Plan
    4. Führe Recovery aus
    5. Retry original Task

    Strategien:
    - Environment Repair: PATH fixen, missing DLLs installieren
    - Dependency Resolution: Transitive Dependencies auflösen
    - Configuration Fix: Config-Dateien anpassen
    - Workaround: Alternativen Ansatz wählen
    - Graceful Degradation: Teilresultat liefern mit Erklärung
    """
```

### 5.3 `ToolEcosystemMap` — Runtime Capability Graph

```python
class ToolEcosystemMap:
    """
    Kennt das gesamte Tool-Ökosystem und dessen Zusammenhänge:

    Node.js Ecosystem:
      Package Managers: npm, yarn, pnpm, bun
      Global Tools: npx (runner), tsx (ts runner), eslint, prettier
      Build Tools: webpack, vite, esbuild, rollup
      Test Tools: jest, vitest, mocha, playwright

    Python Ecosystem:
      Package Managers: pip, poetry, pipx, conda, uv
      Virtual Envs: venv, virtualenv, conda
      Global Tools: black, ruff, mypy, pytest
      Build Tools: setuptools, flit, hatch

    System Tools by OS:
      win32: choco, winget, scoop
      darwin: brew, port
      linux: apt, dnf, pacman, snap
    """
```

**Deliverables Level 5:**
- [ ] `ToolSynthesizer` für ad-hoc Script-Generation
- [ ] `SelfHealingLoop` für autonome Error-Recovery
- [ ] `ToolEcosystemMap` als Graph-Datenstruktur
- [ ] End-to-End "Zero-Knowledge" Test: Agent löst Aufgabe mit komplett unbekanntem Tool

---

## Smart Design Patterns

### Pattern 1: Probe-Before-Execute
```
Vor jedem `run_command`:
1. `which <tool>` / `Get-Command <tool>`     → Ist es installiert?
2. `<tool> --version`                         → Welche Version?
3. `<tool> --help`                            → Welche Flags?
4. Erst dann: `<tool> <args>`                 → Ausführen

Kosten: 3 extra Commands. Gewinn: Kein blindes Scheitern.
```

### Pattern 2: Fallback-Chain (Try-Alternatives)
```python
FALLBACK_CHAINS = {
    "pdf_generation": [
        ("pandoc", "pandoc {input} -o {output}.pdf"),
        ("wkhtmltopdf", "wkhtmltopdf {input} {output}.pdf"),
        ("weasyprint", "weasyprint {input} {output}.pdf"),
        ("chrome", "chrome --headless --print-to-pdf={output}.pdf {input}"),
    ],
    "image_resize": [
        ("magick", "magick {input} -resize {size} {output}"),
        ("ffmpeg", "ffmpeg -i {input} -vf scale={size} {output}"),
        ("sharp", "npx sharp-cli resize {size} -i {input} -o {output}"),
    ],
    "json_query": [
        ("jq", "jq '{query}' {input}"),
        ("python", "python -c \"import json; ...\""),
        ("node", "node -e \"...\""),
    ],
}
```

### Pattern 3: Environment Snapshot + Rollback
```python
class EnvironmentSnapshot:
    """Vor jeder Installation: Snapshot des Environments."""
    path_entries: list[str]
    installed_packages: dict[str, str]    # name → version
    env_vars: dict[str, str]
    timestamp: datetime

    async def rollback(self) -> None:
        """Stelle den vorherigen Zustand wieder her."""
```

### Pattern 4: Progressive Confidence
```
Confidence-Level für Tool-Discovery:

0.9+ → Knowledge-Base Match (schon mal erfolgreich gemacht)
0.7+ → LLM-Reasoning + bekannter Package-Manager
0.5+ → Web-Search-Ergebnis + plausible Argumente
0.3+ → Educated Guess basierend auf Tool-Name
0.0  → Kein Plan → SelfHealingLoop aktivieren
```

### Pattern 5: Execution Contracts
```python
@dataclass(frozen=True)
class ExecutionContract:
    """
    Jede Tool-Ausführung hat einen Vertrag:
    - Preconditions: Was muss vorher gelten?
    - Postconditions: Was muss nachher gelten?
    - Invariants: Was darf sich nicht ändern?
    """
    preconditions: list[Condition]     # [FileExists("input.md")]
    postconditions: list[Condition]    # [FileExists("output.pdf"), FileSizeGt("output.pdf", 0)]
    invariants: list[Condition]        # [DirUnchanged("node_modules")]
    timeout: float
    max_retries: int
    rollback_on_failure: bool
```

---

## Implementation Priority Matrix

```
                    HIGH IMPACT
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
    │  L3: Provisioner  │  L1: RetryStrategy│
    │  L2: Discovery    │  L1: Outcome      │
    │                   │      Verifier     │
    │   HIGH EFFORT     │   LOW EFFORT      │
    │                   │                   │
    ├───────────────────┼───────────────────┤
    │                   │                   │
    │  L5: Synthesizer  │  L1: Telemetry    │
    │  L5: SelfHealing  │  L4: Pattern      │
    │                   │      Detector     │
    │                   │                   │
    │                   │                   │
    └───────────────────┼───────────────────┘
                        │
                    LOW IMPACT
```

**Empfohlene Reihenfolge:**
1. **L1 RetryStrategy + OutcomeVerifier** (1-2 Wochen) → Sofortige Zuverlässigkeit
2. **L1 Telemetry** (1 Woche) → Sichtbarkeit
3. **L2 Discovery + KnowledgeBase** (2-3 Wochen) → Der Game-Changer
4. **L3 Provisioner + Policy** (2 Wochen) → Autonomie
5. **L4 Adaptive Selection** (1-2 Wochen) → Intelligenz
6. **L5 Synthesizer + SelfHealing** (3-4 Wochen) → Vollautonomy

**Geschätzte Gesamtzeit: 10-14 Wochen für Full Command Control.**

---

## Wie sich das anfühlt wenn es fertig ist

```
User: "Erstelle ein Thumbnail von diesem Video"

Agent (intern):
  ├─ IntentResolver: capability_needed = "video_thumbnail_extraction"
  ├─ Discovery: KnowledgeBase → ffmpeg (confidence 0.95, 47 successes)
  ├─ Provisioner: `which ffmpeg` → ✅ already installed (v6.1)
  ├─ Executor: `ffmpeg -i video.mp4 -ss 00:00:05 -frames:v 1 thumb.jpg`
  ├─ OutcomeVerifier:
  │   ├─ file_exists("thumb.jpg") → ✅
  │   ├─ file_size > 1000 → ✅ (45KB)
  │   └─ content_type = "image/jpeg" → ✅
  ├─ Telemetry: 1.2s, exit_code=0, success
  └─ Memory: Updated ffmpeg success_count → 48

Agent: "Hier ist das Thumbnail: thumb.jpg (45KB, 1280x720)"
```

Kein User musste sagen welches Tool. Kein User musste installieren. Kein User musste Flags nachschlagen. **Full Command Control.**

---

## File Mapping (wo die neuen Module leben)

```
backend/app/services/
├── tool_retry_strategy.py          # L1 — Error Taxonomy + Retry Logic
├── tool_outcome_verifier.py        # L1 — Expected-Effect Checks
├── tool_telemetry.py               # L1 — Span Tracing + Metrics
├── tool_discovery_engine.py        # L2 — Multi-Source Tool Finder
├── tool_knowledge_base.py          # L2 — Persistent Learning Store
├── package_manager_adapter.py      # L2 — Unified PM Interface
├── platform_info.py                # L2 — OS/Environment Detection
├── tool_provisioner.py             # L3 — Install + Verify Pipeline
├── provisioning_policy.py          # L3 — Governance für Installationen
├── adaptive_tool_selector.py       # L4 — Feedback-Driven Selection
├── tool_chain_planner.py           # L4 — Multi-Step Orchestration
├── execution_pattern_detector.py   # L4 — Anti-Pattern Erkennung
├── tool_synthesizer.py             # L5 — Ad-hoc Script Generation
├── self_healing_loop.py            # L5 — Autonomous Error Recovery
└── tool_ecosystem_map.py           # L5 — Runtime Capability Graph
```
