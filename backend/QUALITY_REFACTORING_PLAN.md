# Quality-Driven Refactoring Plan

**Erstellt:** 2. März 2026  
**Basis:** Unverfälschtes Deep Quality Review & Audit (ohne architecture.md-Referenz)  
**Codestand:** 16.210 LOC Produktion, 9.812 LOC Tests, 363 Tests grün  

---

## Zusammenfassung

| # | Prio | Maßnahme | Aufwand | Risiko |
|---|------|----------|---------|--------|
| 1 | KRITISCH | agent.py aufbrechen — Request-Context-Objekt | 3–5 Tage | Hoch |
| 2 | KRITISCH | Action-Parser: Markdown-Fence-Stripping | 1–2 Stunden | Niedrig |
| 3 | HOCH | LlmClient: Langlebiger Connection-Pool | 0,5–1 Tag | Mittel |
| 4 | HOCH | Synchrone I/O → asyncio.to_thread() | 1–2 Tage | Mittel |
| 5 | HOCH | Multi-Turn Tool-Loop | 2–3 Tage | Hoch |
| 6 | HOCH | api_auth_required Default → true | 1 Stunde | Niedrig |
| 7 | MITTEL | Command-Allowlist: Shell-Argument-Validierung | 0,5–1 Tag | Mittel |
| 8 | MITTEL | Hardcoded Werte → Settings | 1 Tag | Niedrig |
| 9 | MITTEL | Dead Code eliminieren | 0,5 Tag | Niedrig |
| 10 | NIEDRIG | Tool-Definitionen konsolidieren | 0,5 Tag | Niedrig |

---

## 1. [KRITISCH] agent.py aufbrechen — Request-Scoped Context-Objekt

### Problem

`app/agent.py` ist mit **1.341 Zeilen** die größte Datei der Codebase und vereint mindestens 6 Verantwortlichkeiten. In `_execute_tools()` (ab Zeile 825) werden **8 Proxy-Closures** definiert, die lediglich `session_id`, `request_id` und `send_event` binden:

```
_emit_lifecycle_proxy           Zeile 826
_emit_tool_selection_empty_proxy  Zeile 835
_invoke_hooks_proxy             Zeile 844
_request_policy_override_proxy  Zeile 853
_approve_blocked_process_tools_if_needed_proxy  Zeile 862
_augment_actions_if_needed_proxy  Zeile 871
_invoke_spawn_subrun_tool_proxy Zeile 892
_memory_add_proxy               Zeile 901
```

Diese Proxies werden zusammen mit **30+ weiteren Callables** als einzelne Argumente an `ToolExecutionManager.execute()` übergeben — de facto manuelle Verdrahtung statt Dependency Injection.

### Ursache

Es fehlt ein Request-Scoped Context-Objekt, das die pro-Request-Werte (`session_id`, `request_id`, `send_event`, `model`, `allowed_tools`) kapselt und den Sub-Systemen bereitstellt.

### Implementierungsempfehlung

**Schritt 1: `RunContext`-Dataclass einführen**

```python
# app/run_context.py (NEU)
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class RunContext:
    session_id: str
    request_id: str
    send_event: Callable[[dict], Awaitable[None]]
    model: str | None
    allowed_tools: set[str]
    agent_name: str
    client_model: str
```

**Schritt 2: `ToolExecutionManager.execute()` auf `RunContext` umstellen**

Statt 30+ Einzelparameter akzeptiert `execute()` ein `RunContext`-Objekt plus die weiterhin nötigen Strategie-Callables. Die 8 Proxy-Closures entfallen komplett, weil `RunContext` die gebundenen Werte bereits enthält.

**Schritt 3: Eigenständige Module extrahieren**

| Verantwortung | Zieldatei | Betrifft Methoden |
|---------------|-----------|-------------------|
| Tool-Policy-Auflösung | `app/services/tool_policy_resolver.py` | `_resolve_effective_allowed_tools()`, `_validate_tool_policy()`, `_build_tool_policy_resolution_details()`, `_normalize_tool_set()`, `_unknown_tool_names()` |
| Tool-Ausführung & Retry | `app/services/tool_invoker.py` | `_invoke_tool()`, `_run_tool_with_policy()`, `_is_retryable_tool_error()`, `_evaluate_action()` |
| Skills-Integration | `app/skills/run_integration.py` | `_resolve_skills_enabled_for_request()`, `_matches_canary_rule()`, `_empty_skills_snapshot()` |
| Reply-Postprocessing | bleibt in `app/services/reply_shaper.py` | `_shape_final_response()`, `_sanitize_final_response()` |

### Besonderheiten

- `CoderAgent` und `ReviewAgent` (Zeile 1478–1484) sind reine `HeadAgent`-Subklassen mit nur `name`/`role`-Overrides. Nach Extraktion kann geprüft werden, ob sie als Factory-Funktion statt Klasse besser aufgehoben sind.
- `HeadCodingAgent = HeadAgent` (Zeile 1484) ist ein toter Alias — nur noch von `test_tool_selection_offline_eval.py` (24 Stellen) genutzt. Die Tests sollten direkt `HeadAgent` verwenden.
- Die `_HeadToolSelectorRuntime`-Klasse (Zeile 77–95) hält eine WeakRef auf den HeadAgent. Beim Aufbrechen muss die Ownership-Semantik erhalten bleiben.

### Testbarkeitsgewinn

Aktuell ist `HeadAgent` praktisch nur über E2E-Tests testbar, weil der Konstruktor sofort `AgentTooling`, `MemoryStore`, `LlmClient` und `SkillsService` instanziiert. Mit `RunContext` + extrahierten Modulen wird Unit-Testing der einzelnen Pipelines möglich.

### Gate-Kriterium

Alle 363 bestehenden Tests bleiben grün. `agent.py` reduziert sich auf < 500 LOC.

---

## 2. [KRITISCH] Action-Parser: Markdown-Fence-Stripping

### Problem

`app/services/action_parser.py` Zeile 10–12:
```python
def parse(self, raw: str) -> tuple[list[dict], str | None]:
    text = raw.strip()
    parsed = json.loads(text)
```

`json.loads()` wird direkt auf den LLM-Output angewendet. LLMs wrappen JSON-Output jedoch häufig in Markdown-Code-Fences:

````
```json
{"actions": [{"tool": "read_file", "args": {"path": "main.py"}}]}
```
````

Dieser Fall führt **immer** zu `"LLM JSON could not be decoded"` und löst den Repair-Pfad aus — ein unnötiger Second-Pass-LLM-Call der ~0,8–2s Latenz und Token-Kosten verursacht.

### Implementierungsempfehlung

In `parse()` **vor** `json.loads()` Markdown-Fences strippen:

```python
def parse(self, raw: str) -> tuple[list[dict], str | None]:
    text = self._strip_markdown_fences(raw.strip())
    try:
        parsed = json.loads(text)
    # ...

@staticmethod
def _strip_markdown_fences(text: str) -> str:
    """Remove ```json...``` or ```...``` wrappers around JSON content."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    # Entferne erste Zeile (```json / ```) und letzte Zeile (```)
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
```

### Besonderheiten

- `extract_json_candidate()` (Zeile 52–58) findet JSON-Blöcke in Freitext als Fallback, hat aber ein **3.000-Zeichen-Limit**. Bei großen `write_file`-Content-Args wird JSON abgeschnitten. Das Limit sollte auf `settings.tool_result_max_chars` (Default 6.000) angehoben oder entfernt werden.
- Der `repair()`-Prompt (Zeile 34) enthält eine **hardcodierte Tool-Liste**. Diese sollte aus `TOOL_NAME_SET` generiert werden statt manuell gepflegt.

### Test

```python
def test_parse_strips_markdown_fence():
    parser = ActionParser()
    raw = '```json\n{"actions": [{"tool": "read_file", "args": {"path": "x"}}]}\n```'
    actions, error = parser.parse(raw)
    assert error is None
    assert len(actions) == 1
    assert actions[0]["tool"] == "read_file"
```

### Gate-Kriterium

Bestehende `test_action_parser.py`-Tests grün + neuer Fence-Test.

---

## 3. [HOCH] LlmClient: Langlebiger Connection-Pool

### Problem

`app/llm_client.py` erstellt in **5 Methoden** jeweils pro Retry-Attempt einen neuen `httpx.AsyncClient`:

```
Zeile 103: async with httpx.AsyncClient(timeout=120) as client:  # stream_chat_completion
Zeile 170: async with httpx.AsyncClient(timeout=120) as client:  # _stream_chat_completion_ollama
Zeile 244: async with httpx.AsyncClient(timeout=120) as client:  # complete_chat
Zeile 330: async with httpx.AsyncClient(timeout=120) as client:  # _complete_chat_ollama
Zeile 413: async with httpx.AsyncClient(timeout=120) as client:  # complete_chat_with_tools
```

Jeder Aufruf erzeugt einen neuen TCP-Handshake. Bei einem typischen Agent-Run (Planning + Tool-Selection + Synthesize = 3+ LLM-Calls, ggf. mit Retries) sind das **9–15 unnötige TCP-Verbindungsaufbauten**.

### Implementierungsempfehlung

```python
class LlmClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url
        self.model = model
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                    keepalive_expiry=30.0,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
```

### Besonderheiten

- **Lifecycle-Integration:** `close()` muss im FastAPI-Lifespan-Shutdown aufgerufen werden. `app/startup_tasks.py` oder `app/app_state.py` ist der richtige Ort.
- **`configure_runtime()` erzeugt einen neuen `LlmClient`** (`agent.py` Zeile 259). Bei Runtime-Switch muss der alte Client geschlossen werden bevor ein neuer Pool erstellt wird.
- **Retry-Delay:** Aktuell lineares Backoff (`0.8 * attempt`). Sollte auf exponentielles Backoff mit Jitter umgestellt werden: `base * 2^attempt + random(0, base)` — wichtig bei 429-Rate-Limiting.
- **`MAX_RETRIES = 3` und `RETRY_DELAY_SECONDS = 0.8`** sind Modul-Konstanten (Zeile 15–16). Diese sollten als Teil von Punkt 8 in `Settings` ausgelagert werden.

### Gate-Kriterium

`test_llm_client.py` grün. Keine regredierten Timeouts in E2E-Tests.

---

## 4. [HOCH] Synchrone I/O → asyncio.to_thread()

### Problem

Drei Module führen blockierende File-I/O im asyncio Event-Loop aus:

| Modul | Methode | Zeile | Art |
|-------|---------|-------|-----|
| `app/memory.py` | `_append_to_disk()` | 83 | Synchroner File-Append |
| `app/memory.py` | `_trim_file()` | 98 | Read-Modify-Write gesamte Datei |
| `app/memory.py` | `_load_from_disk()` | 61 | Synchroner File-Read |
| `app/state/state_store.py` | `_replace_with_retry()` | 268 | Synchroner Write + `time.sleep()` (Zeile 277) |
| `app/state/state_store.py` | `append_event()` | — | Read-Modify-Write der gesamten Run-JSON |
| `app/orchestrator/pipeline_runner.py` | `_persist_recovery_metrics()` | — | Synchroner JSON-Write |

### Implementierungsempfehlung

**Variante A (minimal-invasiv): Wrapper mit `asyncio.to_thread()`**

```python
# In MemoryStore:
async def add_async(self, session_id: str, role: str, content: str) -> None:
    await asyncio.to_thread(self.add, session_id, role, content)
```

Caller in `HeadAgent.run()` ändern auf `await self.memory.add_async(...)`.

**Variante B (strukturell besser): Async Interface mit sync Implementierung**

```python
class AsyncMemoryStore:
    def __init__(self, sync_store: MemoryStore):
        self._sync = sync_store

    async def add(self, session_id: str, role: str, content: str) -> None:
        await asyncio.to_thread(self._sync.add, session_id, role, content)

    async def get_items(self, session_id: str) -> list[MemoryItem]:
        return await asyncio.to_thread(self._sync.get_items, session_id)
```

### Besonderheiten

- `_replace_with_retry()` (state_store.py Zeile 268) enthält `time.sleep(delay)` mit Delays von `0.005, 0.02, 0.05` Sekunden — diese blockieren den Event-Loop direkt. Mindestens diese Sleeps müssen auf `await asyncio.sleep()` umgestellt werden.
- `MemoryStore._trim_file()` liest und schreibt die **gesamte JSONL-Datei** bei jedem Append wenn `max_items` überschritten — bei langen Sessions (>30 Items) mit jedem Tool-Call. Optimierung: Append-only mit periodischem Trim statt pro-Write.
- Variante A kann schrittweise ausgerollt werden ohne das bestehende synchrone Interface zu brechen.

### Gate-Kriterium

`test_memory_store_thread_safety.py` und `test_state_store_*` grün. Keine neuen `time.sleep()`-Aufrufe im async-Pfad.

---

## 5. [HOCH] Multi-Turn Tool-Loop

### Problem

Das aktuelle System macht genau **einen** LLM-Call für Tool-Selektion → führt die ausgewählten Actions aus → geht zur Synthese. Es gibt keinen Mechanismus, nach Tool-Ergebnissen **erneut Tools zu selektieren**.

Die einzige Pseudo-Iteration ist das Re-Planning (`max_replan_iterations`, agent.py Zeile 413), das den gesamten Plan-Cycle neu startet — aber nicht gezielt weitere Tools basierend auf bisherigen Ergebnissen auswählt.

Bei komplexen Aufgaben ("Analysiere alle Python-Dateien und fasse die Ergebnisse zusammen") ist das Tool-Call-Cap von **8** schnell erreicht, ohne dass der Agent iterativ nachsteuern kann.

### Implementierungsempfehlung

**Inner Tool-Selection Loop in `ToolExecutionManager.run_tool_loop()`:**

```python
async def run_tool_loop(self, ...) -> str:
    results: list[str] = []
    total_iterations = 0
    max_iterations = config.max_tool_iterations  # NEU: Default 3

    while total_iterations < max_iterations:
        total_iterations += 1

        # Bestehende Actions ausführen
        iteration_results = await self._execute_action_batch(actions, ...)
        results.extend(iteration_results)

        # Prüfe ob weitere Tool-Calls nötig
        if not self._needs_followup(iteration_results, user_message):
            break

        # Re-Selection mit bisherigen Ergebnissen als Kontext
        followup_prompt = self._build_followup_prompt(
            user_message, plan_text, "\n".join(results)
        )
        actions = await self.select_actions_with_repair(
            tool_selector_prompt=followup_prompt, ...
        )
        if not actions:
            break

    return "\n\n".join(results)
```

### Besonderheiten

- **Budget-Guards bleiben aktiv:** `tool_call_cap` und `tool_time_cap_seconds` gelten global über alle Iterationen — kein Risiko für endlose Loops.
- **Loop-Detector bleibt aktiv:** Der bestehende `ToolCallGatekeeper` erkennt Wiederholungen auch über Iterations-Grenzen hinweg.
- `_needs_followup()` sollte konservativ starten: Nur bei expliziten Hinweisen im Tool-Output (z.B. "more results available", truncated output) eine Folge-Iteration triggern.
- Neue Settings: `TOOL_MAX_ITERATIONS` (Default: 3), `TOOL_FOLLOWUP_ENABLED` (Default: false) — Feature-Flag für schrittweisen Rollout.

### Risiko

Hoch — verändert das Kernverhalten der Agent-Pipeline. Erfordert:
1. Feature-Flag (Default off)
2. Separate Benchmark-Szenarien für Multi-Turn
3. Canary-Rollout über `TOOL_FOLLOWUP_ENABLED`

### Gate-Kriterium

Feature-Flag off: Alle 363 Tests grün, identisches Verhalten. Feature-Flag on: Neue Tests für Multi-Turn-Szenarien.

---

## 6. [HOCH] api_auth_required Default → true

### Problem

`app/config.py` Zeile 513:
```python
api_auth_required: bool = _parse_bool_env("API_AUTH_REQUIRED", False)
```

Standardmäßig ist keine Authentifizierung für den API-Runtime-Modus erforderlich. Bei einem Deployment ohne explizite Konfiguration ist das Backend offen erreichbar.

### Implementierungsempfehlung

```python
# api_auth_required ist True wenn APP_ENV != "development"
api_auth_required: bool = _parse_bool_env(
    "API_AUTH_REQUIRED",
    default=os.getenv("APP_ENV", "development").strip().lower() != "development",
)
```

### Besonderheiten

- **Abwärtskompatibilität:** Lokale Entwickler, die `APP_ENV` nicht setzen (Default: `"development"`), bleiben unbeeinträchtigt.
- **CI-Tests:** Laufen standardmäßig ohne API-Runtime — kein Impact auf die Testsuite.
- `ensure_api_runtime_authenticated()` in `runtime_manager.py` prüft `API_AUTH_TOKEN` bzw. `OLLAMA_API_KEY` — bei fehlendem Token gibt es einen expliziten Fehlerpfad. Dieser sollte getestet werden.
- **Dokumentation:** README und Deployment-Docs müssen aktualisiert werden.

### Gate-Kriterium

`test_runtime_manager_auth.py` grün. Kein Impact auf Tests mit `APP_ENV=development`.

---

## 7. [MITTEL] Command-Allowlist: Shell-Argument-Validierung

### Problem

`app/tools.py` Zeile 488–524: Die `_build_command_allowlist()` lädt erlaubte Kommandos aus `settings.command_allowlist`. Standardmäßig enthält diese Liste Shells wie `bash`, `sh`, `powershell`, `cmd`.

Die `_enforce_command_allowlist()` prüft nur den **Leader** (erstes Wort des Commands):
```python
leader = self._extract_command_leader(command)
if leader not in self._command_allowlist:
    raise ToolExecutionError(...)
```

Problem: Ein Agent-Call `bash` (ohne Argumente) öffnet eine interaktive Shell. Obwohl `find_command_safety_violation()` (Zeile 527) Shell-Chaining blockt, ist das nur für **inline** Commands wirksam — eine interaktive Shell-Session umgeht alle Guards.

### Implementierungsempfehlung

```python
SHELL_LEADERS = {"bash", "sh", "zsh", "fish", "powershell", "pwsh", "cmd"}

def _enforce_command_allowlist(self, command: str) -> None:
    if not self._command_allowlist_enabled:
        return

    leader = self._extract_command_leader(command)
    # ...bestehende blocked_leaders Prüfung...

    # Shell-Commands erfordern Inline-Argumente
    if leader in SHELL_LEADERS:
        parts = command.strip().split(None, 1)
        if len(parts) < 2:
            raise ToolExecutionError(
                f"Interactive shell '{leader}' is blocked. "
                "Provide the command inline (e.g., 'bash -c \"echo hello\"')."
            )
        # Validiere auch den inline-Befehl
        inline_cmd = parts[1]
        if inline_cmd.strip().startswith("-"):
            # Erlaubt: bash -c "...", powershell -Command "..."
            pass
        else:
            self._enforce_command_safety(command=inline_cmd, leader=leader)
```

### Besonderheiten

- `COMMAND_SAFETY_PATTERNS` (Zeile 24–41) enthält bereits `\|\|?|&&|;|\`|\$\(` — damit ist `bash -c "rm -rf / && echo done"` bereits geblockt.
- Die Allowlist unterstützt `COMMAND_ALLOWLIST_EXTRA` für Development — Shells sollten **nicht** über Extra hinzufügbar sein, sondern über eine separate `COMMAND_SHELL_ALLOWLIST` gesteuert werden.
- `python -c` ist explizit geblockt (Pattern Zeile 35), aber `node -e`, `ruby -e`, `perl -e` fehlen.

### Gate-Kriterium

`test_tools_command_security.py` grün + neue Tests für interaktive Shell-Blockierung.

---

## 8. [MITTEL] Hardcoded Werte → Settings

### Problem

Zahlreiche Werte sind als Literale im Code statt in `app/config.py` definiert:

| Wert | Datei | Zeile | Beschreibung |
|------|-------|-------|-------------|
| `timeout=120` | llm_client.py | 103, 170, 244, 330, 413 | LLM-Request-Timeout |
| `MAX_RETRIES = 3` | llm_client.py | 15 | Retry-Count |
| `RETRY_DELAY_SECONDS = 0.8` | llm_client.py | 16 | Retry-Delay |
| `1800` chars | context_reducer.py | 75–76 | Item-Truncation-Limit |
| `budget * 5` | context_reducer.py | 32 | Token-zu-Char-Ratio |
| `0.45, 0.35, 0.15, 0.25` | context_reducer.py | 33–38 | Budget-Proportionen |
| `3000` chars | action_parser.py | 58 | JSON-Candidate-Limit |
| `12` entries | tool_call_gatekeeper.py | — | Signature-History-Limit |
| `60` entries | tool_call_gatekeeper.py | — | Outcome-History-Limit |
| Tool-Timeouts (5–20s) | tool_registry.py | — | Per-Tool-Timeout |

### Implementierungsempfehlung

Neue Settings-Felder in `app/config.py`:

```python
# LLM Client
llm_request_timeout_seconds: float = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120"))
llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
llm_retry_base_delay_seconds: float = float(os.getenv("LLM_RETRY_BASE_DELAY_SECONDS", "0.8"))

# Context Reducer
context_reducer_item_max_chars: int = int(os.getenv("CONTEXT_REDUCER_ITEM_MAX_CHARS", "1800"))
context_reducer_token_char_ratio: int = int(os.getenv("CONTEXT_REDUCER_TOKEN_CHAR_RATIO", "5"))

# Action Parser
action_parser_json_candidate_max_chars: int = int(os.getenv("ACTION_PARSER_JSON_CANDIDATE_MAX_CHARS", "6000"))
```

### Besonderheiten

- `ToolSpec`-Klasse in `tool_registry.py` hat ein `description`-Feld (Zeile 14) und ein `parameters`-Feld (Zeile 15) die **nie gesetzt werden**. Bei der Konfigurationsarbeit sollten diese entweder befüllt oder entfernt werden.
- Die Budget-Proportionen (`0.45/0.35/0.15/0.25` → Summe > 1.0) in `context_reducer.py` sind beabsichtigt (Überlappung durch späteres Truncation), aber nicht dokumentiert. Kommentar oder Validierung hinzufügen.
- Die bestehenden 504 Zeilen in `config.py` (~90 Settings) sind bereits umfangreich. Gruppierung per Region-Kommentare oder Pydantic-Submodels überlegen.

### Gate-Kriterium

Alle Tests grün. Keine Verhaltensänderung (gleiche Defaults).

---

## 9. [MITTEL] Dead Code eliminieren

### Inventar

| Element | Datei | Zeile | Nutzung |
|---------|-------|-------|---------|
| `is_weather_lookup_task()` | intent_detector.py | 243 | Wird von `agent.py` über `_is_weather_lookup_task` an `ToolExecutionManager` durchgereicht, dort in `run_tool_loop()` Zeile 807 als OR-Bedingung neben `is_web_research_task` verwendet. **Nicht dead — aber schlecht benannt und mit `is_web_research_task` zusammenlegbar.** |
| `HeadCodingAgent = HeadAgent` | agent.py | 1484 | Nur von `test_tool_selection_offline_eval.py` (24 Stellen) genutzt |
| `tool_policy` Parameter | planner_agent.py `run()` | — | Akzeptiert, nie gelesen |
| `tool_policy` Parameter | synthesizer_agent.py `run()` | — | Akzeptiert, nie gelesen |
| `user_message` Parameter | reply_shaper.py `shape()` | — | `_ = user_message` sofort verworfen |
| `ToolSpec.description` | tool_registry.py | 14 | Immer leer |
| `ToolSpec.parameters` | tool_registry.py | 15 | Immer `None` |
| `HeadCoderInput/Output` | contracts/schemas.py | — | Reine Alias-Klassen ohne eigene Felder |

### Implementierungsempfehlung

**Phase A — Sichere Entfernungen (kein Caller betroffen):**
1. `tool_policy` aus `PlannerAgent.run()` und `SynthesizerAgent.run()` entfernen (erfordert Anpassung in `AgentContract`-Interface oder Default-Parameter)
2. `user_message` aus `ReplyShaper.shape()` entfernen
3. `ToolSpec.description` und `ToolSpec.parameters` entfernen (oder mit echten Werten befüllen für Punkt 10)

**Phase B — Alias-Migration:**
1. `HeadCodingAgent` → Tests auf `HeadAgent` umstellen (24 Ersetzungen in `test_tool_selection_offline_eval.py`)
2. `HeadCoderInput/Output` → imports auf `AgentInput`/`HeadAgentOutput` umstellen
3. Aliases für 1 Release beibehalten mit `DeprecationWarning`, dann entfernen

**Phase C — Refactoring:**
1. `is_weather_lookup_task()` mit `is_web_research_task()` zusammenlegen zu einer generischen `requires_web_fetch()` Methode
2. Die 6+ Alias-Methoden in `IntentDetector` (`detect_intent_gate` → `detect`, `looks_like_shell_command` → `is_shell_command`, etc.) konsolidieren

### Besonderheiten

- **Korrektur zur initialen Analyse:** `is_weather_lookup_task()` ist **kein toter Code** — es wird in `tool_execution_manager.py` Zeile 807 als Retry-Bedingung für `web_fetch` 404-Fehler verwendet:
  ```python
  if tool == "web_fetch" and should_retry_web_fetch_on_404(exc)
      and (is_web_research_task(user_message) or is_weather_lookup_task(user_message)):
  ```
  Es ist aber ein **Benennungs- und Kohäsionsproblem** — beide Funktionen prüfen ob Web-Zugriff gewünscht ist und sollten konsolidiert werden.

### Gate-Kriterium

Alle 363 Tests grün. Keine neuen `DeprecationWarning`-Emissionen in Test-Output.

---

## 10. [NIEDRIG] Tool-Definitionen konsolidieren

### Problem

Tool-Namen und -Metadata existieren an **zwei unabhängigen Stellen**:

1. `app/tool_catalog.py`: `TOOL_NAMES` (Tuple), `TOOL_NAME_SET` (Set), `TOOL_NAME_ALIASES` (Dict)
2. `app/services/tool_registry.py`: `_default_tool_specs()` definiert `ToolSpec` pro Tool mit `required_args`, `optional_args`, Timeout, Retries

Es gibt **keine Validierung**, dass beide Listen synchron sind. Ein neues Tool in `tool_catalog.py` ohne `ToolSpec` in `tool_registry.py` (oder umgekehrt) verursacht einen Runtime-Fehler erst bei der ersten Nutzung.

### Implementierungsempfehlung

**Single Source of Truth in `tool_catalog.py`:**

```python
# app/tool_catalog.py (erweitert)
from dataclasses import dataclass

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    required_args: tuple[str, ...]
    optional_args: tuple[str, ...] = ()
    timeout_seconds: float = 10.0
    max_retries: int = 0
    aliases: tuple[str, ...] = ()

TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition("list_dir", required_args=(), optional_args=("path",), timeout_seconds=6.0),
    ToolDefinition("read_file", required_args=("path",), timeout_seconds=8.0),
    ToolDefinition("write_file", required_args=("path", "content"), timeout_seconds=10.0,
                   aliases=("writefile", "createfile", "create_file")),
    # ...
)

# Abgeleitete Lookups (Backwards-Compatible)
TOOL_NAMES = tuple(t.name for t in TOOL_DEFINITIONS)
TOOL_NAME_SET = frozenset(TOOL_NAMES)
TOOL_NAME_ALIASES = {
    alias: defn.name
    for defn in TOOL_DEFINITIONS
    for alias in defn.aliases
}
```

`ToolRegistryFactory.build()` liest dann aus `TOOL_DEFINITIONS` statt eigene Specs hart zu kodieren.

### Besonderheiten

- `HeadAgent._validate_tool_registry_dispatch()` (agent.py Zeile 1249) validiert bereits, dass jedes registrierte Tool eine `AgentTooling`-Methode und einen `ToolArgValidator` hat. Diese Validierung bleibt erhalten und wird durch die Konsolidierung robuster.
- Die `repair()`-Methode in `action_parser.py` enthält eine **hardcodierte Tool-Liste** im Prompt (Zeile 34). Nach Konsolidierung sollte diese aus `TOOL_NAMES` generiert werden:
  ```python
  tool_list = "|".join(TOOL_NAMES)
  ```

### Gate-Kriterium

Alle Tests grün. `_validate_tool_registry_dispatch()` erkennt Diskrepanzen weiterhin.

---

## Ausführungsreihenfolge

```
Woche 1:  #2 (Action-Parser, 1–2h) → #6 (Auth-Default, 1h) → #9 Phase A (Dead Params, 2h)
Woche 2:  #3 (Connection-Pool, 1 Tag) → #8 (Settings, 1 Tag)
Woche 3:  #4 (Async I/O, 1–2 Tage) → #7 (Shell-Validation, 0,5 Tag)
Woche 4–5: #1 (agent.py aufbrechen, 3–5 Tage)
Woche 6:  #10 (Tool-Konsolidierung, 0,5 Tag) → #9 Phase B+C (Aliases, 0,5 Tag)
Woche 7+: #5 (Multi-Turn, 2–3 Tage, Feature-Flag)
```

**Prinzip:** Kleine, sichere Änderungen zuerst (2, 6, 9A), dann infrastrukturelle Verbesserungen (3, 8, 4, 7), dann die große Zerlegung (1) auf Basis der stabilisierten Infrastruktur, abschließend Feature-Arbeit (5).

---

## Regressions-Strategie

- Jede Änderung einzeln committen mit `pytest -q` als Gate
- Für #1 (agent.py): Branch mit täglichem Merge auf Stand der Testsuite
- Für #5 (Multi-Turn): Separate Benchmark-Szenarien, nicht in Regressionssuite
- Coverage-Gate bleibt aktiv: Global ≥ 70%, `pipeline_runner.py` ≥ 80%
