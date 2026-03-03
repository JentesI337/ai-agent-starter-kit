# Intelligence Layer Refactoring Plan: 3/10 → 11/10

**Ziel:** Den Agent von einem "Dateisystem-Manipulator mit Retry-Logik" zu einem universellen Problem-Löser transformieren.  
**Grundprinzip:** Die exzellente Infrastruktur (Recovery, Fallback, Policy, Loop-Detection) bleibt unangetastet. Wir bauen die Intelligenz-Schicht **darauf**.

---

## Übersicht: 10 Refactoring-Blöcke

| # | Block | Neue Problem-Klassen | Aufwand | Dateien betroffen |
|---|-------|----------------------|---------|-------------------|
| 1 | **Chain-of-Thought System Prompts** | Bessere Antwortqualität bei ALLEN Aufgaben | 2-4h | `config.py` |
| 2 | **Reflection Loop** | Selbstkorrektur bei ALLEN Aufgaben | 1-2 Tage | `agent.py`, `synthesizer_agent.py`, `verification_service.py`, `agent_contract.py` |
| 3 | **Web Search Tool** | Jede Recherche-Aufgabe | 1-2 Tage | `tools.py`, `tool_registry.py`, `tool_catalog.py`, neues Modul |
| 4 | **HTTP Request Tool (POST/PUT/DELETE)** | API-Integration, Cloud-Services | 4-8h | `tools.py`, `tool_registry.py`, `tool_catalog.py` |
| 5 | **Hierarchische Planung & Root-Cause Replan** | Komplexe Multi-Step-Probleme | 2-3 Tage | `agent.py`, `planner_agent.py`, neues Modul |
| 6 | **Clarification Protocol** | Ambige Anfragen richtig lösen | 1-2 Tage | `agent.py`, `ws_handler.py`, `intent_detector.py` |
| 7 | **Cross-Session Memory & Failure Journal** | Lernen aus Fehlern, Erfahrung nutzen | 2-3 Tage | `memory.py`, `agent.py`, neues Modul |
| 8 | **RAG mit Embeddings** | Eigene Dokumente intelligent durchsuchen | 2-3 Tage | `skills/retrieval.py`, neues Modul |
| 9 | **MCP Tool Bridge** | Exponentielles Tool-Wachstum | 3-5 Tage | `tool_registry.py`, neues Modul |
| 10 | **Code Execution Sandbox & Vision** | Mathematik, Datenanalyse, Bild-Analyse | 3-5 Tage | `tools.py`, `tool_registry.py`, neues Modul |

---

## Block 1: Chain-of-Thought System Prompts

### Problem (IST)
Die System-Prompts sind minimal und enthalten keine Reasoning-Instruktionen:
```python
# config.py Zeile 116-118
head_agent_system_prompt = "You are a neutral head agent. Be concise, factual, and adapt naturally to user intent."
head_agent_plan_prompt = "You are a neutral head agent. Return a minimal, context-appropriate plan only when needed."
```
Der Agent "denkt" nicht — er antwortet einfach.

### Lösung (SOLL)
Strukturierte Chain-of-Thought-Instruktionen in allen System-Prompts.

### Exakte Änderungen

**Datei: `backend/app/config.py` Zeilen 116-178**

```python
# VORHER (Zeile 116):
head_agent_system_prompt: str = _resolve_prompt(
    "You are a neutral head agent. Be concise, factual, and adapt naturally to user intent.",
    "HEAD_AGENT_SYSTEM_PROMPT",
    "AGENT_SYSTEM_PROMPT",
)

# NACHHER:
head_agent_system_prompt: str = _resolve_prompt(
    (
        "You are a highly capable autonomous agent. "
        "For every user request, follow this internal reasoning protocol:\n"
        "1. UNDERSTAND: Restate the user's goal in one sentence. Identify ambiguity.\n"
        "2. DECOMPOSE: Break complex problems into 2-5 independent sub-problems.\n"
        "3. PLAN: For each sub-problem, identify which tools or knowledge you need.\n"
        "4. EXECUTE: Work through sub-problems systematically.\n"
        "5. VERIFY: After generating your answer, check: Does this actually solve the stated goal?\n"
        "6. REFINE: If the answer is incomplete or could be wrong, state what's uncertain.\n\n"
        "Principles:\n"
        "- Think step-by-step before acting.\n"
        "- When uncertain, state your confidence level.\n"
        "- If you lack information, explain what you'd need to find out.\n"
        "- Prefer depth over breadth — a thorough answer to the right question beats a shallow answer to many.\n"
        "- Be concise in output but thorough in reasoning."
    ),
    "HEAD_AGENT_SYSTEM_PROMPT",
    "AGENT_SYSTEM_PROMPT",
)
```

```python
# VORHER (Zeile 122):
head_agent_plan_prompt: str = _resolve_prompt(
    "You are a neutral head agent. Return a minimal, context-appropriate plan only when needed.",
    ...
)

# NACHHER:
head_agent_plan_prompt: str = _resolve_prompt(
    (
        "You are a planning agent. Your job is to create execution plans.\n\n"
        "Planning protocol:\n"
        "1. CLASSIFY the request: Is this trivial (greeting, yes/no), moderate (single task), or complex (multi-step)?\n"
        "2. For TRIVIAL: Return 'direct_answer' — no tools needed.\n"
        "3. For MODERATE: Return 1-3 actionable steps with specific tool calls.\n"
        "4. For COMPLEX: Return a dependency graph:\n"
        "   - Which steps can run in parallel?\n"
        "   - Which steps depend on results from earlier steps?\n"
        "   - What's the fallback if a step fails?\n\n"
        "Each step must specify:\n"
        "- WHAT to do (concrete action)\n"
        "- WHY (how it serves the goal)\n"
        "- TOOL (which tool to use, or 'none')\n"
        "- DEPENDS_ON (which earlier step, or 'none')\n\n"
        "If the request is ambiguous, add a 'CLARIFICATION_NEEDED' flag with what you'd ask the user."
    ),
    ...
)
```

```python
# VORHER (Zeile 132):
head_agent_final_prompt: str = _resolve_prompt(
    "You are a neutral head agent. Return a concise, directly helpful final answer.",
    ...
)

# NACHHER:
head_agent_final_prompt: str = _resolve_prompt(
    (
        "You are a synthesis agent generating the final answer.\n\n"
        "Before writing your answer, internally verify:\n"
        "1. Does the answer address the user's ACTUAL question (not a related one)?\n"
        "2. Is every factual claim grounded in tool outputs or stated knowledge?\n"
        "3. Are there gaps? If yes, explicitly state them.\n"
        "4. Could the answer be misunderstood? If yes, add clarification.\n\n"
        "Output rules:\n"
        "- Lead with the most important information.\n"
        "- For coding tasks: include runnable code, not pseudo-code.\n"
        "- For research: cite your sources (from tool outputs).\n"
        "- For analysis: show your reasoning chain.\n"
        "- End with concrete next steps the user can take.\n"
        "- If tool outputs contradicted your initial assumption, say so."
    ),
    ...
)
```

Analog für `coder_agent_*` und `agent_*` Prompts.

### Test-Strategie
- Bestehende Tests bleiben grün (Prompts sind überschreibbar via Env-Vars)
- Neuer Test: `test_cot_system_prompts.py` — prüft dass Default-Prompts die Schlüsselwörter enthalten
- Benchmark: Gleiche 20 Aufgaben vorher/nachher, Qualitäts-Score vergleichen

---

## Block 2: Reflection Loop

### Problem (IST)
```python
# contracts/agent_contract.py Zeile 13-14
class AgentConstraints(BaseModel):
    reflection_passes: int = Field(ge=0, le=10)  # <- IMMER 0!

# agents/planner_agent.py Zeile 20
constraints = AgentConstraints(..., reflection_passes=0)  # <- NIE genutzt

# agents/synthesizer_agent.py Zeile 27
constraints = AgentConstraints(..., reflection_passes=0)  # <- NIE genutzt
```
Das Feld `reflection_passes` existiert, wird aber **nirgendwo abgefragt oder ausgeführt**.

Die `VerificationService` prüft nur strukturell (Länge, Leerheit) — nie semantisch:
```python
# services/verification_service.py Zeile 20-35
def verify_plan(self, *, user_message, plan_text):
    if not normalized_plan: return "failed"
    if len(normalized_plan) < 20: return "warning"
    return "ok"  # <- Das ist KEINE Verifikation
```

### Lösung (SOLL)

#### 2a. Reflection-fähige VerificationService

**Neue Datei: `backend/app/services/reflection_service.py`**

```python
"""
ReflectionService — LLM-basierte Selbstevaluation und Korrektur.

Wird nach Synthesis aufgerufen. Bewertet die Antwort anhand von:
1. Goal Alignment: Beantwortet die Antwort die tatsächliche Frage?
2. Completeness: Fehlen wichtige Aspekte?
3. Factual Grounding: Sind Aussagen durch Tool-Outputs gestützt?
4. Actionability: Kann der User mit der Antwort etwas anfangen?

Gibt ein ReflectionVerdict zurück mit Score und optionaler Korrektur.
"""

@dataclass(frozen=True)
class ReflectionVerdict:
    score: float                    # 0.0-1.0
    goal_alignment: float           # Beantwortet es die Frage?
    completeness: float             # Fehlt etwas?
    factual_grounding: float        # Durch Daten gestützt?
    issues: list[str]               # Identifizierte Probleme
    suggested_fix: str | None       # LLM-generierte Korrektur
    should_retry: bool              # Score < threshold?

class ReflectionService:
    def __init__(self, client: LlmClient, threshold: float = 0.6):
        self.client = client
        self.threshold = threshold

    async def reflect(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
        model: str | None = None,
    ) -> ReflectionVerdict:
        """
        Sendet den Kontext + die finale Antwort an das LLM mit einem
        Evaluations-Prompt. Parsed das Ergebnis als strukturiertes Verdict.
        """
        reflection_prompt = self._build_reflection_prompt(
            user_message=user_message,
            plan_text=plan_text,
            tool_results=tool_results,
            final_answer=final_answer,
        )
        raw_verdict = await self.client.complete_chat(
            system_prompt="You are a quality assurance agent. Evaluate answers critically and objectively.",
            user_message=reflection_prompt,
            model=model,
            temperature=0.1,
        )
        return self._parse_verdict(raw_verdict)

    def _build_reflection_prompt(self, **kwargs) -> str:
        return (
            "Evaluate this response. Return JSON with these fields:\n"
            '{"goal_alignment": 0.0-1.0, "completeness": 0.0-1.0, '
            '"factual_grounding": 0.0-1.0, "issues": ["..."], '
            '"suggested_fix": "..." or null}\n\n'
            f"User question: {kwargs['user_message']}\n"
            f"Plan: {kwargs['plan_text'][:500]}\n"
            f"Tool outputs: {kwargs['tool_results'][:1000]}\n"
            f"Final answer: {kwargs['final_answer']}"
        )

    def _parse_verdict(self, raw: str) -> ReflectionVerdict:
        # JSON-Parsing mit Fallback auf Regex-Extraktion
        ...
```

#### 2b. Integration in HeadAgent Pipeline

**Datei: `backend/app/agent.py` — nach Synthesis (ca. Zeile 850)**

```python
# VORHER (Zeile ~845-855):
final_text = await self.synthesize_step_executor.execute(...)
shape_result = self._shape_final_response(final_text, tool_results)

# NACHHER:
final_text = await self.synthesize_step_executor.execute(...)

# --- REFLECTION LOOP ---
reflection_passes = self.synthesizer_agent.constraints.reflection_passes
if reflection_passes > 0 and self._reflection_service is not None:
    for reflection_pass in range(reflection_passes):
        verdict = await self._reflection_service.reflect(
            user_message=user_message,
            plan_text=plan_text,
            tool_results=tool_results or "",
            final_answer=final_text,
            model=model,
        )
        await self._emit_lifecycle(
            send_event,
            stage="reflection_completed",
            request_id=request_id,
            session_id=session_id,
            details={
                "pass": reflection_pass + 1,
                "score": verdict.score,
                "goal_alignment": verdict.goal_alignment,
                "completeness": verdict.completeness,
                "issues": verdict.issues[:3],
                "should_retry": verdict.should_retry,
            },
        )
        if not verdict.should_retry:
            break
        # Re-Synthesize mit Reflection-Feedback
        final_text = await self.synthesize_step_executor.execute(
            SynthesizerInput(
                user_message=user_message,
                plan_text=plan_text,
                tool_results=(tool_results or "") + f"\n\n[REFLECTION FEEDBACK]\n{chr(10).join(verdict.issues)}",
                reduced_context=final_context.rendered,
                prompt_mode=effective_prompt_mode,
                task_type=synthesis_task_type,
            ),
            session_id, request_id, send_event, model,
        )

shape_result = self._shape_final_response(final_text, tool_results)
```

#### 2c. Constraints aktivieren

**Datei: `backend/app/agents/synthesizer_agent.py` Zeile 27**

```python
# VORHER:
constraints = AgentConstraints(..., reflection_passes=0)

# NACHHER:
constraints = AgentConstraints(..., reflection_passes=1)
```

#### 2d. Semantische Verification

**Datei: `backend/app/services/verification_service.py` — erweitern**

```python
# NEUE Methode hinzufügen:
def verify_plan_semantically(
    self, *, user_message: str, plan_text: str
) -> VerificationResult:
    """Prüft ob der Plan die User-Anfrage tatsächlich adressiert."""
    user_words = set(user_message.lower().split())
    plan_words = set(plan_text.lower().split())

    # Mindestens 20% der signifikanten User-Wörter sollten im Plan vorkommen
    stopwords = {"the", "a", "is", "in", "to", "and", "or", "of", "for", "it", "my", "me",
                 "ich", "ein", "der", "die", "das", "und", "oder", "für", "ist", "mir"}
    significant_user_words = user_words - stopwords
    if not significant_user_words:
        return VerificationResult(status="ok", reason="no_significant_words", details={})

    overlap = significant_user_words & plan_words
    coverage = len(overlap) / len(significant_user_words)

    if coverage < 0.15:
        return VerificationResult(
            status="warning",
            reason="plan_may_miss_user_intent",
            details={"coverage": round(coverage, 2), "missing": list(significant_user_words - plan_words)[:5]},
        )
    return VerificationResult(status="ok", reason="plan_covers_intent", details={"coverage": round(coverage, 2)})
```

### Abhängigkeiten
- Benötigt `LlmClient` Instanz (bereits verfügbar im `HeadAgent`)
- Benötigt neues Settings-Feld: `REFLECTION_ENABLED` (default: `true`), `REFLECTION_THRESHOLD` (default: `0.6`)

### Test-Strategie
- Unit-Test: `test_reflection_service.py` — Mock-LLM-Responses, Verdict-Parsing
- Integration: `test_reflection_loop.py` — Prüft dass bei niedrigem Score Re-Synthesis stattfindet
- Regression: Alle bestehenden E2E-Tests müssen grün bleiben (reflection_passes=0 deaktiviert den Loop)

---

## Block 3: Web Search Tool

### Problem (IST)
`web_fetch` kann nur bekannte URLs abrufen. Es gibt **kein Such-Tool**:
```python
# tools.py — web_fetch nur GET auf bekannte URL
async def _web_fetch(self, url: str, ...) -> str:
    # Kann NUR text von einer URL holen die der LLM schon kennen muss
```
Ohne Suche ist der Agent bei jeder Recherche-Aufgabe blind.

### Lösung (SOLL)

**Neue Datei: `backend/app/services/web_search.py`**

```python
"""
WebSearchService — Abstraktion über Such-APIs.

Unterstützte Backends (über Env-Var WEB_SEARCH_PROVIDER):
- "searxng"  → Selbstgehostetes SearXNG (default, keine API-Key nötig)
- "tavily"   → Tavily Search API (API-Key nötig)
- "brave"    → Brave Search API (API-Key nötig)
- "duckduckgo" → DuckDuckGo Instant Answer API (kein API-Key)

Jedes Backend gibt eine standardisierte WebSearchResult-Liste zurück.
"""

@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    source: str          # "organic", "answer_box", "knowledge_panel"
    relevance_score: float

@dataclass(frozen=True)
class WebSearchResponse:
    query: str
    results: list[WebSearchResult]
    total_results: int
    search_time_ms: float
    provider: str

class WebSearchService:
    def __init__(self, provider: str, api_key: str | None, base_url: str | None):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url

    async def search(self, query: str, *, max_results: int = 5) -> WebSearchResponse:
        if self.provider == "searxng":
            return await self._search_searxng(query, max_results)
        elif self.provider == "tavily":
            return await self._search_tavily(query, max_results)
        elif self.provider == "brave":
            return await self._search_brave(query, max_results)
        elif self.provider == "duckduckgo":
            return await self._search_duckduckgo(query, max_results)
        raise ValueError(f"Unknown search provider: {self.provider}")

    async def _search_searxng(self, query, max_results):
        """GET {base_url}/search?q={query}&format=json&engines=google,bing&pageno=1"""
        ...

    async def _search_tavily(self, query, max_results):
        """POST https://api.tavily.com/search mit API-Key Header"""
        ...

    async def _search_brave(self, query, max_results):
        """GET https://api.search.brave.com/res/v1/web/search?q={query}"""
        ...

    async def _search_duckduckgo(self, query, max_results):
        """GET https://api.duckduckgo.com/?q={query}&format=json"""
        ...
```

**Datei: `backend/app/tools.py` — Neues Tool registrieren**

```python
# Neue Methode in AgentTooling (ca. Zeile 600):
async def web_search(self, query: str, max_results: int = 5) -> str:
    """Sucht im Web nach der gegebenen Query. Gibt Titel, URL und Snippet zurück."""
    service = WebSearchService(
        provider=settings.web_search_provider,
        api_key=settings.web_search_api_key,
        base_url=settings.web_search_base_url,
    )
    response = await service.search(query, max_results=max_results)
    lines = [f"Web search results for: {query}\n"]
    for i, result in enumerate(response.results, 1):
        lines.append(f"{i}. [{result.title}]({result.url})")
        lines.append(f"   {result.snippet}")
        lines.append("")
    return "\n".join(lines)
```

**Datei: `backend/app/services/tool_registry.py` — ToolSpec hinzufügen**

```python
# In _default_tool_specs() (ca. Zeile 380):
"web_search": ToolSpec(
    name="web_search",
    required_args=("query",),
    optional_args=("max_results",),
    timeout_seconds=15.0,
    max_retries=1,
    description="Search the web for information. Returns titles, URLs and snippets. Use this FIRST when the user asks about current events, facts, documentation, or anything you're unsure about.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "description": "The search query"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Max results to return (default 5)"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    capabilities=("web_retrieval", "knowledge_retrieval", "source_grounding", "research"),
),
```

**Datei: `backend/app/tool_catalog.py` — Katalog erweitern**

```python
# TOOL_NAMES erweitern:
TOOL_NAMES = (..., "web_search")
TOOL_NAME_ALIASES["websearch"] = "web_search"
TOOL_NAME_ALIASES["search_web"] = "web_search"
TOOL_NAME_ALIASES["search"] = "web_search"
```

**Datei: `backend/app/config.py` — Neue Settings**

```python
# Neue Config-Felder (ca. Zeile 400):
web_search_provider: str = os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo").strip().lower()
web_search_api_key: str = os.getenv("WEB_SEARCH_API_KEY", "")
web_search_base_url: str = os.getenv("WEB_SEARCH_BASE_URL", "")
web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
```

### Auto-Search Augmentation (Bonus)

**Datei: `backend/app/services/action_augmenter.py` — erweitern**

Wenn der IntentDetector `is_web_research_task` erkennt UND keine `web_search`-Action vom LLM gewählt wurde → automatisch `web_search` mit extrahierter Query injizieren. Gleiche Logik wie die bestehende `web_fetch`-Augmentation.

### Test-Strategie
- Unit-Test: `test_web_search_service.py` — Mock HTTP-Responses für jeden Provider
- Integration: `test_web_search_tool.py` — AgentTooling.web_search() mit Mock-Service
- E2E: `test_backend_e2e.py` — "Was ist die Hauptstadt von Frankreich?" → web_search wird aufgerufen
- Smoke: Manuell mit echtem DuckDuckGo-Backend

---

## Block 4: HTTP Request Tool (POST/PUT/DELETE)

### Problem (IST)
```python
# tools.py Zeile ~490 — web_fetch ist NUR GET
async def _web_fetch(self, url: str, ...) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, ...)  # ← NUR GET!
```

### Lösung (SOLL)

**Datei: `backend/app/tools.py` — Neues Tool**

```python
async def http_request(
    self,
    url: str,
    method: str = "GET",
    headers: str | None = None,       # JSON-String
    body: str | None = None,           # JSON-String oder Raw-Body
    content_type: str = "application/json",
    max_chars: int = 100000,
) -> str:
    """
    Führt einen HTTP-Request mit beliebiger Methode aus.
    Unterstützt GET, POST, PUT, PATCH, DELETE.
    Headers und Body werden als JSON-Strings übergeben.
    SSRF-Schutz greift wie bei web_fetch.
    """
    # 1. SSRF-Validierung (bestehende _validate_url_ssrf Methode nutzen)
    # 2. Method-Validierung (nur GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)
    # 3. Headers aus JSON parsen
    # 4. Body aus JSON parsen oder als Raw-String verwenden
    # 5. Request ausführen mit httpx
    # 6. Response formatieren: Status + Headers + Body (truncated)
```

**Datei: `backend/app/services/tool_registry.py` — ToolSpec**

```python
"http_request": ToolSpec(
    name="http_request",
    required_args=("url",),
    optional_args=("method", "headers", "body", "content_type", "max_chars"),
    timeout_seconds=30.0,
    max_retries=1,
    description="Make an HTTP request with any method (GET/POST/PUT/PATCH/DELETE). Use for API calls, webhooks, and web services.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "minLength": 1},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]},
            "headers": {"type": "string", "description": "JSON object of HTTP headers"},
            "body": {"type": "string", "description": "Request body (JSON string or raw text)"},
            "content_type": {"type": "string"},
            "max_chars": {"type": "integer", "minimum": 1},
        },
        "required": ["url"],
        "additionalProperties": False,
    },
    capabilities=("web_retrieval", "api_integration", "webhook_execution"),
),
```

### Sicherheit
- SSRF-Schutz: Wiederverwendung von `_validate_url_ssrf()` aus bestehender `web_fetch`-Implementierung
- Body-Size-Limit: Max 1MB Request-Body
- Response-Size-Limit: Max `max_chars` Zeichen in Response
- **Neues Tool-Policy-Preset**: `http_request` wird standardmäßig in `review`-Preset gesperrt
- `COMMAND_SAFETY_PATTERNS` analog für gefährliche URLs (Metadata-Endpoints, localhost)

### Test-Strategie
- Unit-Test: Mock-HTTP-Server, alle Methoden testen
- SSRF-Test: Versuche auf localhost/metadata-Endpoints → blocked
- Policy-Test: `review-agent` darf `http_request` nicht nutzen

---

## Block 5: Hierarchische Planung & Root-Cause Replan

### Problem (IST)

Der Planner ist ein **Single-Shot-LLM-Call** der 2-5 Bullets erzeugt:
```python
# agents/planner_agent.py Zeile 54-59
planner_instructions = (
    "Create a short execution plan (2-5 bullets) for the user's request.\n"
    "If the request is simple (greeting, small talk, or direct question), keep the plan minimal.\n"
    "If the request is technical or coding-related, include actionable implementation steps."
)
```

Der Replan-Mechanismus ist blind — er wiederholt einfach den gleichen Call mit etwas mehr Kontext:
```python
# agent.py Zeile ~610-625
plan_text = await self.plan_step_executor.execute(
    PlannerInput(
        user_message=user_message,
        reduced_context=replan_context.rendered,   # <- Etwas mehr Kontext, aber keine Analyse
        prompt_mode="minimal",
    ),
    model,
)
```

### Lösung (SOLL)

#### 5a. Strukturierter Plan mit Abhängigkeitsgraph

**Neue Datei: `backend/app/services/plan_graph.py`**

```python
"""
PlanGraph — Strukturierte Aufgaben-Dekomposition mit Abhängigkeiten.

Ersetzt den unstrukturierten "2-5 Bullets"-Plan durch einen gerichteten
azyklischen Graphen (DAG) von Schritten mit:
- step_id: Eindeutige ID
- action: Was tun
- tool: Welches Tool (oder 'none', 'llm_reasoning')
- depends_on: Liste von step_ids
- fallback: Was tun wenn dieser Schritt fehlschlägt
- status: pending | running | completed | failed | skipped
"""

@dataclass
class PlanStep:
    step_id: str
    action: str
    tool: str | None
    depends_on: list[str]
    fallback: str | None
    status: str = "pending"
    result: str | None = None
    error: str | None = None

@dataclass
class PlanGraph:
    goal: str
    complexity: str        # "trivial", "moderate", "complex"
    steps: list[PlanStep]
    clarification_needed: str | None = None

    def ready_steps(self) -> list[PlanStep]:
        """Gibt alle Schritte zurück deren Abhängigkeiten erfüllt sind."""
        completed_ids = {s.step_id for s in self.steps if s.status == "completed"}
        return [
            s for s in self.steps
            if s.status == "pending"
            and all(dep in completed_ids for dep in s.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    def failed_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "failed"]
```

#### 5b. PlannerAgent mit Dekomposition

**Datei: `backend/app/agents/planner_agent.py` — erweitern**

```python
# Neue Methode:
async def execute_structured(self, payload: PlannerInput, model: str | None = None) -> PlanGraph:
    """
    Erstellt einen strukturierten Plan als Graph.
    Bei trivialen Anfragen: 1 Schritt.
    Bei komplexen Anfragen: DAG mit Abhängigkeiten und Fallbacks.
    """
    structured_instructions = (
        "Analyze this request and create a structured execution plan.\n"
        "Return JSON with this schema:\n"
        '{"goal": "...", "complexity": "trivial|moderate|complex", '
        '"steps": [{"step_id": "s1", "action": "...", "tool": "...|none", '
        '"depends_on": [], "fallback": "..."|null}], '
        '"clarification_needed": "..."|null}\n\n'
        "Rules:\n"
        "- trivial requests (greetings, simple questions): 1 step, tool='none'\n"
        "- moderate requests: 1-3 steps with specific tools\n"
        "- complex requests: 3-7 steps with dependency graph\n"
        "- Always include fallback strategies for steps that might fail\n"
        "- Mark steps that can run in parallel (no dependencies between them)"
    )
    # LLM-Call + JSON-Parsing → PlanGraph
    ...
```

#### 5c. Root-Cause Replan

**Datei: `backend/app/agent.py` — Replan-Logik ersetzen (Zeile ~580-630)**

```python
# VORHER: Blinder Replan
plan_text = await self.plan_step_executor.execute(PlannerInput(...), model)

# NACHHER: Root-Cause-Analyse vor Replan
root_cause_prompt = (
    f"The previous plan failed. Analyze WHY and create a better plan.\n\n"
    f"Original user request: {user_message}\n"
    f"Previous plan: {plan_text}\n"
    f"Tool results (including errors): {tool_results}\n\n"
    f"Your analysis must include:\n"
    f"1. ROOT CAUSE: Why did the previous plan fail? (wrong tool? wrong arguments? missing info?)\n"
    f"2. LESSON LEARNED: What should we avoid in the new plan?\n"
    f"3. NEW PLAN: A revised plan that addresses the root cause.\n"
)

replan_input = PlannerInput(
    user_message=root_cause_prompt,
    reduced_context=replan_context.rendered,
    prompt_mode="minimal" if effective_prompt_mode == "full" else effective_prompt_mode,
)
plan_text = await self.plan_step_executor.execute(replan_input, model)
```

#### 5d. Config-Integration

**Datei: `backend/app/config.py`**

```python
# Neue Settings:
structured_planning_enabled: bool = _parse_bool_env("STRUCTURED_PLANNING_ENABLED", False)
plan_max_steps: int = int(os.getenv("PLAN_MAX_STEPS", "7"))
plan_root_cause_replan_enabled: bool = _parse_bool_env("PLAN_ROOT_CAUSE_REPLAN_ENABLED", True)
```

### Test-Strategie
- Unit-Tests: `test_plan_graph.py` — DAG-Operationen (ready_steps, is_complete, failed_steps)
- Unit-Tests: `test_planner_structured.py` — Mock-LLM-Responses → PlanGraph-Parsing
- Integration: `test_root_cause_replan.py` — Simulierte Tool-Fehler → Root-Cause-Analyse im Replan

---

## Block 6: Clarification Protocol

### Problem (IST)
Bei Ambiguität rät der Agent statt zu fragen:
```python
# services/intent_detector.py Zeile 53-58
if not has_command_intent:
    return IntentGateDecision(
        detected_intent=None,
        confidence=0.15,
        gate_action="proceed",  # ← Einfach weitermachen!
        metadata={"extracted_command": None, "missing_slots": ()},
    )
```

### Lösung (SOLL)

#### 6a. Ambiguity Detector

**Neue Datei: `backend/app/services/ambiguity_detector.py`**

```python
"""
AmbiguityDetector — Erkennt mehrdeutige oder unvollständige Anfragen.

Heuristiken:
1. Sehr kurze Nachrichten (<5 Wörter) ohne klaren Intent
2. Multiple mögliche Interpretationen (z.B. "fix it" ohne Kontext)
3. Fehlende Parameter (z.B. "deploy" — wohin?)
4. Konfliktierende Anfragen (z.B. "erstelle und lösche die Datei")
"""

@dataclass(frozen=True)
class AmbiguityAssessment:
    is_ambiguous: bool
    confidence: float            # Wie sicher sind wir in unserer Interpretation
    ambiguity_type: str | None   # "vague", "incomplete", "conflicting", "multi_intent"
    clarification_question: str | None
    default_interpretation: str | None  # Was wir tun würden wenn wir nicht fragen

class AmbiguityDetector:
    def assess(self, user_message: str, memory_context: str | None = None) -> AmbiguityAssessment:
        text = (user_message or "").strip()
        word_count = len(text.split())

        # Heuristik 1: Zu kurz
        if word_count < 3 and not self._is_simple_command(text):
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.3,
                ambiguity_type="vague",
                clarification_question=f'Your request "{text}" is quite short. Could you provide more details about what you need?',
                default_interpretation=None,
            )

        # Heuristik 2: Pronomen ohne Referenz
        if self._has_unresolved_pronouns(text, memory_context):
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.4,
                ambiguity_type="incomplete",
                clarification_question="What specifically are you referring to?",
                default_interpretation=None,
            )

        # Heuristik 3: Multiple Intents
        intents = self._count_intents(text)
        if intents > 2:
            return AmbiguityAssessment(
                is_ambiguous=True,
                confidence=0.5,
                ambiguity_type="multi_intent",
                clarification_question="You seem to be asking about multiple things. Which should I prioritize?",
                default_interpretation=None,
            )

        return AmbiguityAssessment(is_ambiguous=False, confidence=0.8, ...)

    def _is_simple_command(self, text: str) -> bool:
        """ls, dir, help, etc."""
        ...

    def _has_unresolved_pronouns(self, text: str, context: str | None) -> bool:
        """'fix it', 'update that' ohne vorherigen Kontext"""
        pronouns = {"it", "this", "that", "those", "them", "es", "das", "dies"}
        words = set(text.lower().split())
        has_pronoun = bool(pronouns & words)
        has_context = bool(context and len(context) > 50)
        return has_pronoun and not has_context

    def _count_intents(self, text: str) -> int:
        """Zählt separate Handlungsanweisungen"""
        ...
```

#### 6b. Integration in HeadAgent

**Datei: `backend/app/agent.py` — vor Planning (ca. Zeile 410)**

```python
# NACHHER: Ambiguity-Check vor Planning
if settings.clarification_protocol_enabled:
    ambiguity = self._ambiguity_detector.assess(user_message, plan_context.rendered)
    if ambiguity.is_ambiguous and ambiguity.confidence < 0.5:
        await self._emit_lifecycle(
            send_event,
            stage="clarification_needed",
            request_id=request_id,
            session_id=session_id,
            details={
                "ambiguity_type": ambiguity.ambiguity_type,
                "confidence": ambiguity.confidence,
                "question": ambiguity.clarification_question,
            },
        )
        await send_event({
            "type": "clarification_needed",
            "agent": self.name,
            "message": ambiguity.clarification_question,
            "default_interpretation": ambiguity.default_interpretation,
        })
        # Pipeline stoppt hier — wartet auf User-Antwort via WebSocket
        return ambiguity.clarification_question
```

#### 6c. WebSocket-Handler-Update

**Datei: `backend/app/ws_handler.py` — `clarification_response` Message-Type**

```python
# Neuer Message-Type:
elif msg_type == "clarification_response":
    # User hat auf Rückfrage geantwortet
    # Original-Anfrage + Klarstellung zusammenführen
    original_message = session_state.get("pending_clarification_message")
    clarification = data.get("content", "")
    combined = f"{original_message}\n\nClarification: {clarification}"
    # Pipeline mit combined Message neu starten
```

### Config

```python
clarification_protocol_enabled: bool = _parse_bool_env("CLARIFICATION_PROTOCOL_ENABLED", True)
clarification_confidence_threshold: float = float(os.getenv("CLARIFICATION_CONFIDENCE_THRESHOLD", "0.5"))
```

### Test-Strategie
- Unit-Test: `test_ambiguity_detector.py` — Diverse ambige/klare Inputs
- E2E: `test_clarification_protocol.py` — WebSocket-Flow: ambige Nachricht → Rückfrage → Antwort → finaler Output

---

## Block 7: Cross-Session Memory & Failure Journal

### Problem (IST)
```python
# memory.py — GESAMTE Implementierung
class MemoryStore:
    def __init__(self, max_items_per_session: int = 20):  # ← Ringpuffer, 20 Items
        self._store: dict[str, Deque[MemoryItem]] = {}     # ← Pro Session isoliert
        # KEIN cross-session Zugriff
        # KEIN Lernen aus Fehlern
        # KEINE Wissensdestillation
```

### Lösung (SOLL)

#### 7a. Long-Term Memory Store

**Neue Datei: `backend/app/services/long_term_memory.py`**

```python
"""
LongTermMemoryStore — Persistentes Wissens- und Erfahrungs-Gedächtnis.

Drei Speicher-Bereiche:
1. EPISODIC: Was wurde in welcher Session gemacht? (Session-Zusammenfassungen)
2. SEMANTIC: Destillierte Fakten (z.B. "User bevorzugt Python 3.12 + Poetry")
3. FAILURE_JOURNAL: Fehler + Root-Cause + Lösung (durchsuchbar)

Speicher-Backend: SQLite (bereits als Option in state_store.py vorhanden)
"""

@dataclass
class EpisodicEntry:
    session_id: str
    timestamp: str
    summary: str           # LLM-generierte 2-3 Satz Zusammenfassung
    key_actions: list[str] # Was wurde getan
    outcome: str           # success/failed/partial
    tags: list[str]        # Themen-Tags für Retrieval

@dataclass
class SemanticEntry:
    key: str               # z.B. "user.preferred_language"
    value: str             # z.B. "Python"
    confidence: float      # 0.0-1.0
    source_sessions: list[str]  # Aus welchen Sessions stammt das Wissen
    last_updated: str

@dataclass
class FailureEntry:
    failure_id: str
    timestamp: str
    task_description: str
    error_type: str        # "tool_error", "plan_failure", "wrong_answer", "timeout"
    root_cause: str
    solution: str          # Was hat funktioniert
    prevention: str        # Wie vermeiden
    tags: list[str]

class LongTermMemoryStore:
    def __init__(self, db_path: str):
        self._db = sqlite3.connect(db_path)
        self._ensure_schema()

    def add_episodic(self, entry: EpisodicEntry) -> None: ...
    def add_semantic(self, entry: SemanticEntry) -> None: ...
    def add_failure(self, entry: FailureEntry) -> None: ...

    def search_episodic(self, query: str, limit: int = 5) -> list[EpisodicEntry]:
        """FTS5-basierte Volltextsuche über Session-Zusammenfassungen."""
        ...

    def search_failures(self, task_description: str, limit: int = 3) -> list[FailureEntry]:
        """Findet ähnliche vergangene Fehler. Nutzt SQLite FTS5."""
        ...

    def get_semantic(self, key: str) -> SemanticEntry | None: ...
    def get_all_semantic(self) -> list[SemanticEntry]: ...

    def _ensure_schema(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS episodic (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                timestamp TEXT,
                summary TEXT,
                key_actions TEXT,
                outcome TEXT,
                tags TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
                summary, key_actions, tags, content=episodic, content_rowid=rowid
            );
            CREATE TABLE IF NOT EXISTS semantic (
                key TEXT PRIMARY KEY,
                value TEXT,
                confidence REAL,
                source_sessions TEXT,
                last_updated TEXT
            );
            CREATE TABLE IF NOT EXISTS failure_journal (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                task_description TEXT,
                error_type TEXT,
                root_cause TEXT,
                solution TEXT,
                prevention TEXT,
                tags TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS failure_fts USING fts5(
                task_description, root_cause, solution, tags,
                content=failure_journal, content_rowid=rowid
            );
        """)
```

#### 7b. Session-End-Hook: Wissen destillieren

**Datei: `backend/app/agent.py` — im `finally`-Block der `run()` Methode (Zeile ~940)**

```python
# Im finally-Block von HeadAgent.run():
if status == "completed" and self._long_term_memory is not None:
    try:
        await self._distill_session_knowledge(
            session_id=session_id,
            user_message=user_message,
            plan_text=plan_text,
            tool_results=tool_results,
            final_text=final_text,
            model=model,
        )
    except Exception:
        pass  # Nicht-kritisch, darf nicht die Response blockieren
```

```python
async def _distill_session_knowledge(self, *, session_id, user_message, plan_text, tool_results, final_text, model):
    """Generiert nach jedem Run eine Session-Zusammenfassung und speichert sie."""
    distillation_prompt = (
        "Summarize this interaction in 2-3 sentences.\n"
        "Extract key facts about the user's preferences/project.\n"
        "Return JSON: {\"summary\": \"...\", \"key_facts\": [{\"key\": \"...\", \"value\": \"...\"}], "
        "\"tags\": [\"...\"]}\n\n"
        f"User: {user_message[:500]}\n"
        f"Plan: {plan_text[:300]}\n"
        f"Result: {final_text[:500]}"
    )
    raw = await self.client.complete_chat("You distill knowledge.", distillation_prompt, model=model, temperature=0.1)
    parsed = json.loads(raw)  # + Fehlerbehandlung
    self._long_term_memory.add_episodic(EpisodicEntry(
        session_id=session_id,
        summary=parsed["summary"],
        key_actions=[],
        outcome="success",
        tags=parsed.get("tags", []),
    ))
    for fact in parsed.get("key_facts", []):
        self._long_term_memory.add_semantic(SemanticEntry(
            key=fact["key"], value=fact["value"], confidence=0.7, source_sessions=[session_id],
        ))
```

#### 7c. Failure Journal — Automatische Fehlerprotokollierung

**Datei: `backend/app/agent.py` — im `except`-Block der `run()` Methode (Zeile ~935)**

```python
except Exception as exc:
    error_text = str(exc)
    if self._long_term_memory is not None:
        try:
            self._long_term_memory.add_failure(FailureEntry(
                failure_id=request_id,
                task_description=user_message[:500],
                error_type=type(exc).__name__,
                root_cause=error_text[:500],
                solution="",   # Wird beim nächsten Erfolg nachgetragen
                prevention="", # Wird bei Reflection ausgefüllt
                tags=[],
            ))
        except Exception:
            pass
    raise
```

#### 7d. Memory-Context in Prompt injizieren

**Datei: `backend/app/agent.py` — vor Planning (ca. Zeile 380)**

```python
# Relevante Erfahrungen aus Long-Term Memory laden
ltm_context = ""
if self._long_term_memory is not None:
    similar_failures = self._long_term_memory.search_failures(user_message, limit=2)
    if similar_failures:
        ltm_context += "\n[Past failures with similar tasks]\n"
        for f in similar_failures:
            ltm_context += f"- Task: {f.task_description[:100]} → Error: {f.root_cause[:100]} → Fix: {f.solution[:100]}\n"

    semantic_facts = self._long_term_memory.get_all_semantic()
    if semantic_facts:
        ltm_context += "\n[Known user preferences]\n"
        for s in semantic_facts[:10]:
            ltm_context += f"- {s.key}: {s.value}\n"

# In ContextReducer einbauen:
plan_context = self.context_reducer.reduce(
    budget_tokens=budgets["plan"],
    user_message=user_message,
    memory_lines=memory_lines,
    tool_outputs=[],
    snapshot_lines=[ltm_context] if ltm_context else None,  # ← NEU
)
```

### Config

```python
long_term_memory_enabled: bool = _parse_bool_env("LONG_TERM_MEMORY_ENABLED", True)
long_term_memory_db_path: str = _resolve_path_from_workspace(
    os.getenv("LONG_TERM_MEMORY_DB_PATH"), workspace_root, "memory_store/long_term.db"
)
session_distillation_enabled: bool = _parse_bool_env("SESSION_DISTILLATION_ENABLED", True)
failure_journal_enabled: bool = _parse_bool_env("FAILURE_JOURNAL_ENABLED", True)
```

### Test-Strategie
- Unit-Test: `test_long_term_memory.py` — CRUD + FTS5-Suche + Schema-Migration
- Integration: `test_session_distillation.py` — Mock-LLM → Wissens-Extraktion
- Integration: `test_failure_journal.py` — Simulierter Fehler → Journal-Eintrag → Retrieval bei ähnlicher Aufgabe
- Regression: Bestehende Tests unverändert (LTM ist opt-out über Env-Var)

---

## Block 8: RAG mit Embeddings

### Problem (IST)
```python
# skills/retrieval.py — Jaccard-Ähnlichkeit, keine Embeddings
class ReliableRetrievalService:
    def _jaccard_score(self, query_tokens: set[str], doc_tokens: set[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0
        intersection = query_tokens & doc_tokens
        union = query_tokens | doc_tokens
        return len(intersection) / len(union)
```
Nur Keyword-Matching. "Wie erstelle ich einen REST-Server?" findet nicht "FastAPI HTTP endpoint setup".

### Lösung (SOLL)

#### 8a. Embedding Service

**Neue Datei: `backend/app/services/embedding_service.py`**

```python
"""
EmbeddingService — Generiert Vektoren für semantische Suche.

Backends:
- "openai"   → OpenAI Embeddings API (text-embedding-3-small)
- "ollama"   → Lokale Ollama Embeddings (nomic-embed-text, mxbai-embed-large)
- "sentence-transformers" → Lokale HuggingFace Modelle

Embeddings werden in SQLite-vec oder einem einfachen NumPy-basierten
Vektor-Index gespeichert für Nearest-Neighbor-Suche.
"""

class EmbeddingService:
    def __init__(self, provider: str, base_url: str, model: str, api_key: str | None = None):
        self.provider = provider
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "ollama":
            return await self._embed_ollama(texts)
        elif self.provider == "openai":
            return await self._embed_openai(texts)
        raise ValueError(f"Unknown embedding provider: {self.provider}")

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """POST /api/embeddings mit model + prompt"""
        results = []
        async with httpx.AsyncClient() as client:
            for text in texts:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0,
                )
                resp.raise_for_status()
                results.append(resp.json()["embedding"])
        return results

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """POST /v1/embeddings mit model + input (batch)"""
        ...
```

#### 8b. Vector Store

**Neue Datei: `backend/app/services/vector_store.py`**

```python
"""
SimpleVectorStore — SQLite-basierter Vektor-Store.

Speichert Dokument-Chunks mit Embeddings.
Nearest-Neighbor-Suche via Cosine-Similarity.
Kein NumPy-Dependency — reine Python-Implementierung für Portabilität.
"""

@dataclass
class VectorDocument:
    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, str]

class SimpleVectorStore:
    def __init__(self, db_path: str):
        self._db = sqlite3.connect(db_path)
        self._ensure_schema()

    def upsert(self, doc: VectorDocument) -> None:
        """Dokument mit Embedding speichern/aktualisieren."""
        ...

    def search(self, query_embedding: list[float], *, top_k: int = 5) -> list[tuple[VectorDocument, float]]:
        """Cosine-Similarity-Suche. Gibt (doc, score) Paare zurück."""
        ...

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x ** 2 for x in a) ** 0.5
        norm_b = sum(x ** 2 for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
```

#### 8c. RAG-Integration im Planer

**Datei: `backend/app/agent.py` — vor Planning**

```python
# RAG-Kontext holen
rag_context = ""
if self._rag_service is not None:
    rag_results = await self._rag_service.retrieve(user_message, top_k=3)
    if rag_results:
        rag_context = "\n[Relevant knowledge from indexed documents]\n"
        for doc, score in rag_results:
            rag_context += f"- [{score:.2f}] {doc.content[:300]}\n"
```

#### 8d. Dokument-Indexierung

**Neue Datei: `backend/app/services/document_indexer.py`**

```python
"""
DocumentIndexer — Indexiert Dateien aus dem Workspace für RAG.

Unterstützte Formate: .md, .txt, .py, .ts, .js, .json, .yaml
Chunking-Strategie: 
- Markdown: Heading-basiert (ein Chunk pro ## Section)
- Code: Funktion/Klasse-basiert (regex-basierte Erkennung)
- Text: Fixed-size mit Overlap (512 Tokens, 50 Token Overlap)

Wird bei Start und bei Dateiänderungen getriggert.
"""

class DocumentIndexer:
    def __init__(self, embedding_service: EmbeddingService, vector_store: SimpleVectorStore):
        self.embedding = embedding_service
        self.store = vector_store

    async def index_workspace(self, workspace_root: str, patterns: list[str] = None):
        """Indexiert alle relevanten Dateien im Workspace."""
        ...

    async def index_file(self, file_path: str):
        """Indexiert eine einzelne Datei."""
        ...

    def _chunk_markdown(self, content: str) -> list[str]: ...
    def _chunk_code(self, content: str, language: str) -> list[str]: ...
    def _chunk_text(self, content: str, max_tokens: int = 512, overlap: int = 50) -> list[str]: ...
```

### Config

```python
rag_enabled: bool = _parse_bool_env("RAG_ENABLED", False)  # Opt-in weil Embedding-Service nötig
rag_embedding_provider: str = os.getenv("RAG_EMBEDDING_PROVIDER", "ollama")
rag_embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "nomic-embed-text")
rag_embedding_base_url: str = os.getenv("RAG_EMBEDDING_BASE_URL", "http://localhost:11434")
rag_vector_db_path: str = _resolve_path_from_workspace(
    os.getenv("RAG_VECTOR_DB_PATH"), workspace_root, "memory_store/vectors.db"
)
rag_index_patterns: list[str] = _parse_csv_env(os.getenv("RAG_INDEX_PATTERNS", "**/*.md,**/*.txt,**/*.py"), ["**/*.md"])
```

### Test-Strategie
- Unit-Test: `test_vector_store.py` — Upsert + Cosine-Suche + Edge-Cases
- Unit-Test: `test_document_indexer.py` — Chunking-Strategien für verschiedene Formate
- Integration: `test_rag_pipeline.py` — Datei indexieren → Query → relevante Chunks zurückbekommen
- Perf-Test: 100 Dokumente indexieren, Search-Latenz < 100ms

---

## Block 9: MCP Tool Bridge

### Problem (IST)
Tools sind fest in `tool_registry.py` codiert (14 Stück). Jedes neue Tool erfordert Code-Änderungen in 3 Dateien.

### Lösung (SOLL)

**Neue Datei: `backend/app/services/mcp_bridge.py`**

```python
"""
McpBridge — Model Context Protocol Client.

Verbindet sich mit MCP-Servern und macht deren Tools als Agent-Tools verfügbar.

MCP-Protokoll (Spezifikation: https://modelcontextprotocol.io):
1. Client sendet "initialize" → Server antwortet mit Capabilities
2. Client sendet "tools/list" → Server antwortet mit Tool-Definitionen
3. Client sendet "tools/call" → Server führt Tool aus, antwortet mit Ergebnis

Unterstützte Transports:
- stdio: Server wird als Subprocess gestartet, kommuniziert über stdin/stdout
- sse: Server ist HTTP-Endpoint mit Server-Sent Events
- streamable-http: HTTP-basiertes Streaming (neueste MCP-Version)

Jeder MCP-Server wird als MCP-Tool-Quelle registriert und seine Tools
werden dynamisch in das ToolRegistry eingehängt.
"""

@dataclass
class McpServerConfig:
    name: str
    transport: str         # "stdio" | "sse" | "streamable-http"
    command: str | None     # Für stdio: Befehl zum Starten
    args: list[str]        # Für stdio: Argumente
    url: str | None        # Für sse/streamable-http: Server-URL
    env: dict[str, str]    # Environment-Variablen für den Server

@dataclass
class McpToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str

class McpBridge:
    def __init__(self, servers: list[McpServerConfig]):
        self._servers = {s.name: s for s in servers}
        self._connections: dict[str, McpConnection] = {}
        self._discovered_tools: dict[str, McpToolDefinition] = {}

    async def initialize(self) -> None:
        """Verbindet sich mit allen konfigurierten MCP-Servern und discovert Tools."""
        for name, config in self._servers.items():
            conn = await self._connect(config)
            self._connections[name] = conn
            tools = await conn.list_tools()
            for tool in tools:
                self._discovered_tools[f"mcp_{name}_{tool.name}"] = tool

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Ruft ein MCP-Tool auf und gibt das Ergebnis als String zurück."""
        tool_def = self._discovered_tools[tool_name]
        conn = self._connections[tool_def.server_name]
        result = await conn.call_tool(tool_def.name, arguments)
        return self._format_result(result)

    def get_tool_specs(self) -> list[ToolSpec]:
        """Konvertiert MCP-Tool-Definitionen in ToolSpec-Objekte für das ToolRegistry."""
        specs = []
        for name, tool_def in self._discovered_tools.items():
            specs.append(ToolSpec(
                name=name,
                required_args=tuple(tool_def.input_schema.get("required", [])),
                optional_args=(),
                timeout_seconds=30.0,
                max_retries=0,
                description=tool_def.description,
                parameters=tool_def.input_schema,
                capabilities=("mcp_tool", "dynamic_tool"),
            ))
        return specs

    async def _connect(self, config: McpServerConfig) -> McpConnection:
        if config.transport == "stdio":
            return await StdioMcpConnection.connect(config.command, config.args, config.env)
        elif config.transport == "sse":
            return await SseMcpConnection.connect(config.url)
        elif config.transport == "streamable-http":
            return await StreamableHttpMcpConnection.connect(config.url)
        raise ValueError(f"Unknown MCP transport: {config.transport}")
```

#### Integration in ToolRegistry

**Datei: `backend/app/services/tool_registry.py` — ToolRegistryFactory.build()**

```python
# In ToolRegistryFactory.build() — nach statischen Tools:
if mcp_bridge is not None:
    for spec in mcp_bridge.get_tool_specs():
        registry.register(spec, dispatcher=mcp_bridge.call_tool)
```

#### Integration in HeadAgent

**Datei: `backend/app/agent.py` — __init__()**

```python
# In __init__:
self._mcp_bridge: McpBridge | None = None
if settings.mcp_servers:
    self._mcp_bridge = McpBridge(settings.mcp_servers)
```

```python
# In configure_runtime oder startup:
if self._mcp_bridge:
    await self._mcp_bridge.initialize()
    for spec in self._mcp_bridge.get_tool_specs():
        self.tool_registry.register(spec, dispatcher=lambda args, **kw: self._mcp_bridge.call_tool(spec.name, args))
```

### Config

```python
# config.py — MCP-Server Konfiguration
mcp_enabled: bool = _parse_bool_env("MCP_ENABLED", False)
mcp_servers_config: str = os.getenv("MCP_SERVERS_CONFIG", "")  # JSON oder Dateipfad
# Beispiel: [{"name": "filesystem", "transport": "stdio", "command": "npx", "args": ["@modelcontextprotocol/server-filesystem", "/workspace"]}]

@property
def mcp_servers(self) -> list[McpServerConfig]:
    """Parsed MCP-Server-Konfiguration aus Env-Var oder JSON-Datei."""
    ...
```

### Test-Strategie
- Unit-Test: `test_mcp_bridge.py` — Mock-MCP-Server (stdio-basiert), Tool-Discovery, Tool-Call
- Integration: `test_mcp_tool_registry.py` — MCP-Tools werden als ToolSpecs registriert
- E2E: `test_mcp_e2e.py` — Echter MCP-Server (z.B. filesystem), Agent nutzt MCP-Tool

---

## Block 10: Code Execution Sandbox & Vision

### Problem (IST)
- `run_command` führt direkt auf dem Host aus — kein Sandbox
- Kein Vision/Multimodal — Agent kann keine Bilder analysieren

### Lösung (SOLL)

#### 10a. Code Sandbox Tool

**Neue Datei: `backend/app/services/code_sandbox.py`**

```python
"""
CodeSandbox — Sichere Code-Ausführung in isolierter Umgebung.

Strategien (nach Verfügbarkeit):
1. Docker: Startet einen Container, führt Code aus, gibt Output zurück
2. Process-Isolation: subprocess mit Ressourcen-Limits (keine Network-Zugriff)
3. Direct: Fallback — wie run_command aber mit strikteren Safety-Checks

Unterstützte Sprachen: Python, JavaScript/Node.js, Shell
"""

class CodeSandbox:
    def __init__(self, strategy: str = "process"):
        self.strategy = strategy

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        max_output_chars: int = 10000,
    ) -> CodeExecutionResult:
        if self.strategy == "docker":
            return await self._execute_docker(code, language, timeout, max_output_chars)
        elif self.strategy == "process":
            return await self._execute_process(code, language, timeout, max_output_chars)
        return await self._execute_direct(code, language, timeout, max_output_chars)

    async def _execute_process(self, code, language, timeout, max_output_chars):
        """
        Erstellt temp-Datei, führt mit subprocess aus.
        - Python: python -u temp.py
        - Node: node temp.js
        - Keine Network-Zugriff (NETWORK_DISABLED env var)
        - Timeout-Enforcement
        - Output-Truncation
        """
        ...
```

**Neue ToolSpec:**

```python
"code_execute": ToolSpec(
    name="code_execute",
    required_args=("code",),
    optional_args=("language", "timeout"),
    timeout_seconds=45.0,
    max_retries=0,
    description="Execute code in a sandboxed environment. Use for calculations, data processing, testing code snippets. Supported: python, javascript.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "minLength": 1, "description": "The code to execute"},
            "language": {"type": "string", "enum": ["python", "javascript"], "description": "Programming language (default: python)"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Execution timeout in seconds"},
        },
        "required": ["code"],
        "additionalProperties": False,
    },
    capabilities=("code_execution", "calculation", "data_analysis", "testing"),
),
```

#### 10b. Vision Tool (Basis)

**Neue Datei: `backend/app/services/vision_service.py`**

```python
"""
VisionService — Bild-Analyse über multimodale LLM-APIs.

Unterstützte Backends:
- Ollama Multimodal (llava, bakllava)
- OpenAI GPT-4V
- Google Gemini Vision

Input: Base64-kodiertes Bild + Text-Prompt
Output: Text-Beschreibung/Analyse
"""

class VisionService:
    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str = "Describe this image in detail.",
        max_tokens: int = 1000,
    ) -> str:
        """Sendet Bild + Prompt an multimodales LLM, gibt Text-Antwort zurück."""
        ...
```

**Neue ToolSpec:**

```python
"analyze_image": ToolSpec(
    name="analyze_image",
    required_args=("image_path",),
    optional_args=("prompt",),
    timeout_seconds=30.0,
    max_retries=0,
    description="Analyze an image file using vision AI. Describe contents, extract text (OCR), identify UI elements.",
    parameters={
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "minLength": 1, "description": "Path to the image file"},
            "prompt": {"type": "string", "description": "Specific question about the image (default: general description)"},
        },
        "required": ["image_path"],
        "additionalProperties": False,
    },
    capabilities=("vision", "image_analysis", "ocr", "ui_testing"),
),
```

### Config

```python
code_sandbox_strategy: str = os.getenv("CODE_SANDBOX_STRATEGY", "process")  # "docker", "process", "direct"
code_sandbox_timeout: int = int(os.getenv("CODE_SANDBOX_TIMEOUT", "30"))
vision_enabled: bool = _parse_bool_env("VISION_ENABLED", False)
vision_model: str = os.getenv("VISION_MODEL", "llava:13b")
```

### Test-Strategie
- Unit-Test: `test_code_sandbox.py` — Python/JS Code-Ausführung, Timeout, Output-Limits
- Security-Test: `test_sandbox_isolation.py` — Netzwerk-Zugriff blocked, Dateisystem-Zugriff limited
- Unit-Test: `test_vision_service.py` — Mock-Vision-API, Bild-Analyse-Response-Parsing

---

## Implementierungs-Reihenfolge (Timeline)

```
Woche 1: Block 1 (CoT Prompts) + Block 3 (Web Search) + Block 4 (HTTP Request)
         → Sofortiger Impact auf Recherche- und API-Aufgaben
         → Keine Breaking Changes, alle bestehenden Tests bleiben grün

Woche 2: Block 2 (Reflection) + Block 5 (Hierarchische Planung)
         → Agent wird "nachdenklicher" und plant besser
         → Opt-in via Config, bestehende Pipeline bleibt Fallback

Woche 3: Block 6 (Clarification) + Block 7 (Long-Term Memory)
         → Agent fragt nach + lernt aus Fehlern
         → Neue WebSocket-Events, Frontend-Änderungen nötig

Woche 4: Block 8 (RAG) + Block 9 (MCP Bridge)
         → Semantische Suche + dynamische Tool-Erweiterung
         → Abhängig von Embedding-Service (Ollama nomic-embed-text)

Woche 5: Block 10 (Sandbox + Vision)
         → Code-Execution + Bild-Analyse
         → Optional, abhängig von Docker/Vision-Model-Verfügbarkeit

Woche 6: Integration Testing + Benchmark
         → Alle Blöcke zusammen testen
         → Benchmark-Suite mit 50 Aufgaben über alle Kategorien
```

## Feature-Flag-Matrix (Rückwärtskompatibilität)

| Feature | Env-Var | Default | Abhängigkeit |
|---------|---------|---------|-------------|
| CoT Prompts | `HEAD_AGENT_SYSTEM_PROMPT` (Override) | Neue Defaults aktiv | — |
| Reflection | `REFLECTION_ENABLED` | `true` | LLM-Client |
| Web Search | `WEB_SEARCH_PROVIDER` | `duckduckgo` | — |
| HTTP Request | (immer verfügbar) | Tool aktiv | — |
| Structured Planning | `STRUCTURED_PLANNING_ENABLED` | `false` | — |
| Root-Cause Replan | `PLAN_ROOT_CAUSE_REPLAN_ENABLED` | `true` | — |
| Clarification | `CLARIFICATION_PROTOCOL_ENABLED` | `true` | — |
| Long-Term Memory | `LONG_TERM_MEMORY_ENABLED` | `true` | SQLite |
| Failure Journal | `FAILURE_JOURNAL_ENABLED` | `true` | SQLite |
| RAG | `RAG_ENABLED` | `false` | Embedding-Service |
| MCP Bridge | `MCP_ENABLED` | `false` | MCP-Server-Config |
| Code Sandbox | `CODE_SANDBOX_STRATEGY` | `process` | — |
| Vision | `VISION_ENABLED` | `false` | Vision-Model |

## Erwarteter Impact auf Problem-Lösungs-Fähigkeit

| Problem-Kategorie | VORHER (3/10) | NACHHER (11/10) | Welcher Block |
|---|---|---|---|
| **Fakten-Recherche** | Kann nur bekannte URLs abrufen | Web-Suche + Quellenvergleich | 3, 1 |
| **API-Integration** | Nur GET | Alle HTTP-Methoden + Auth | 4 |
| **Code-Debugging** | Liest Code, rät Lösung | Sandbox: Code ausführen, testen, verifizieren | 10a |
| **Komplexe Analyse** | Single-Shot-Plan, oft oberflächlich | Hierarchischer Plan + Reflection-Loop | 5, 2 |
| **Unklare Anfragen** | Rät oder gibt leere Ergebnisse | Fragt nach | 6 |
| **Wiederholte Fehler** | Gleicher Fehler jedes Mal neu | Failure Journal: erinnert sich | 7 |
| **Eigene Doku durchsuchen** | Keyword-Jaccard-Matching | Semantische Embedding-Suche | 8 |
| **Neue Tools integrieren** | 3 Dateien manuell ändern | MCP-Server starten → Tools automatisch verfügbar | 9 |
| **Mathematik/Berechnung** | LLM muss im Kopf rechnen | Code-Sandbox: echte Berechnung | 10a |
| **Screenshot-Analyse** | Unmöglich | Vision-Tool: Bild beschreiben, OCR | 10b |
| **Antwort-Qualität** | Keine Selbstkontrolle | Reflection: "Ist das richtig?" + Re-Synthesis | 2 |
| **Kontext-Verständnis** | 20-Item Ringpuffer, Session-isoliert | Cross-Session-Wissen, User-Preferences | 7 |

---

*Erstellt: 2026-03-03 | Basiert auf vollständiger Code-Analyse aller 50+ Kern-Dateien im Backend*
