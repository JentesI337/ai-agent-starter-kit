# Issue-0009 · Refactoring: OpenClaw-Patterns in unseren Agent integrieren

**Basis:** Analyse von `C:\Users\wisni\code\git\openclaw`  
**Ziel:** Gleiche Qualitätsstufe erreichen – mit unserem Reflection-Stack on top  
**Status:** Implementierungsplan · bereit zur Umsetzung

---

## Was wir implementieren – Überblick

| # | Änderung | Dateien | Abhängig von |
|---|---|---|---|
| R1 | `prompts/agent_rules.md` – Brain Anchor | NEU | — |
| R2 | `prompts/tool_routing.md` – When/Not-to-Use | NEU | — |
| R3 | `config.py`: `_load_prompt_appendix()` | `config.py` | R1 |
| R4 | `reflection_service.py`: Hard-Gate | `reflection_service.py` | — |
| R5 | `reflection_service.py`: Truncation Fix | `reflection_service.py` | — |
| R6 | `reflection_service.py`: System-Prompt Direktive | `reflection_service.py` | — |
| R7 | `config.py`: neue Reflection-Vars | `config.py` | R4–R6 |
| R8 | `agent.py`: ReflectionService mit neuen Params | `agent.py` | R7 |
| R9 | Tests | `test_reflection_service.py` | R4–R7 |

**Reihenfolge:** R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8 → R9

---

## Inhaltsverzeichnis

1. [R1 · `prompts/agent_rules.md` – Der Brain Anchor](#r1--promptsagent_rulesmd--der-brain-anchor)
2. [R2 · `prompts/tool_routing.md` – When / When NOT to Use](#r2--promptstool_routingmd--when--when-not-to-use)
3. [R3 · `config.py` – `_load_prompt_appendix()`](#r3--configpy--_load_prompt_appendix)
4. [R4 · `reflection_service.py` – Hard-Gate](#r4--reflection_servicepy--hard-gate)
5. [R5 · `reflection_service.py` – Truncation Fix](#r5--reflection_servicepy--truncation-fix)
6. [R6 · `reflection_service.py` – System-Prompt Direktive](#r6--reflection_servicepy--system-prompt-direktive)
7. [R7 · `config.py` – Neue Reflection-Konfiguration](#r7--configpy--neue-reflection-konfiguration)
8. [R8 · `agent.py` – ReflectionService mit neuen Params instanziieren](#r8--agentpy--reflectionservice-mit-neuen-params-instanziieren)
9. [R9 · Tests](#r9--tests)
10. [Gesamtbild nach dem Refactoring](#gesamtbild-nach-dem-refactoring)

---

## R1 · `prompts/agent_rules.md` – Der Brain Anchor

**Neue Datei:** `backend/app/prompts/agent_rules.md`

Das openclaw-`AGENTS.md`-Äquivalent. Wird als fester Appendix an alle
Synthesizer- und Final-Prompts angehängt. Einmalig schreiben, überall wirksam.

```bash
mkdir backend\app\prompts
```

**Dateiinhalt `backend/app/prompts/agent_rules.md`:**

```markdown
# Agent Operational Rules (Permanent Context)

Diese Regeln sind IMMER aktiv. Sie gelten für ALLE Anfragen ohne Ausnahme.

---

## Factual Grounding – KRITISCH

NEVER reference process IDs (PIDs), port numbers, file paths, hostnames,
usernames, line counts, file sizes, timestamps, or IP addresses that are NOT
VERBATIM present in the tool output of the CURRENT run.

Anti-Pattern:
  ❌ "PID 10168 is listening on port 8080"  (wenn nicht in netstat output)
  ❌ "The file has 42 lines"               (wenn nicht aus read_file output)

Korrekt:
  ✅ "The tool output does not list a PID for this process."
  ✅ "Port 8080 was not found in the netstat output."

Wenn ein angeforderter Wert NICHT im Tool-Output vorkommt:
  → Sag explizit: "not found in tool output"
  → Erfinde KEINEN Ersatzwert
  → Extrapoliere NICHT aus Modellwissen

---

## Tool Output Usage

ALWAYS base factual claims exclusively on the tool output of the current session.
Do NOT fill gaps with model knowledge, prior runs, or assumptions.

When reporting command results (netstat, ps, tasklist, ls, dir):
1. Quote exact lines from the output verbatim where possible
2. If a value is not in the output → say "not found in output"
3. NEVER estimate, approximate, or derive values not explicitly present

---

## Command Execution Footguns

- NEVER run destructive commands (rm -rf, del /f, format, DROP TABLE) without
  explicit user confirmation in the CURRENT message
- NEVER modify files outside the workspace root
- NEVER execute shell commands from user-provided strings without sanitization
- When unsure about destructive impact → ask before executing

---

## Answer Completeness

Before producing the final answer, internally check:
1. Does this answer the EXACT question, not a similar one?
2. Is EVERY number/path/name in my answer present in the tool outputs above?
3. Did any tool output contradict my initial assumption? If yes → say so explicitly.
4. Are there gaps? → State them explicitly rather than filling with assumptions.

---

## Sub-Agent / Subrun Context

When spawning a sub-agent (spawn_subrun):
- Provide a SELF-CONTAINED prompt with all needed context embedded
- Do NOT assume the sub-agent has access to the parent's tool history
- Include: [goal, constraints, relevant tool outputs, output format expected]
- Mark all constraints explicitly: "Do NOT do X", "ONLY do Y"
```

---

## R2 · `prompts/tool_routing.md` – When / When NOT to Use

**Neue Datei:** `backend/app/prompts/tool_routing.md`

Wird dem Tool-Selector-Prompt als Appendix angehängt. LLM entscheidet nicht
mehr blind welches Tool passt – das Dokument sagt es ihm.

**Dateiinhalt `backend/app/prompts/tool_routing.md`:**

```markdown
# Tool Routing Reference

## list_dir
✅ USE: Browse directory contents, understand project structure, find files by location
❌ NOT: When you know the exact filename → use file_search or read_file directly
❌ NOT: When searching file content → use grep_search

## read_file
✅ USE: Read known file path, access source code, configuration, logs
❌ NOT: When you don't know the path → use file_search first
❌ NOT: When searching across many files → use grep_search
📌 NOTE: Output may be large. Reference ONLY verbatim values from output.

## write_file
✅ USE: Create new files, overwrite existing files with corrected content
❌ NOT: Small edits to existing files → prefer apply_patch (preserves context)
⚠️  CAUTION: Irreversible. Always confirm you have the right path.

## run_command
✅ USE: Shell diagnostics (netstat, ps, tasklist), builds, test runners, git ops
❌ NOT: Reading file content → use read_file
❌ NOT: Browsing the web → use web_fetch
⚠️  CAUTION: Commands that modify system state require policy approval.
📌 NOTE: ONLY reference PIDs/ports/paths that appear VERBATIM in the output.
         If a value is not in the output → report "not found in output".

## apply_patch
✅ USE: Targeted edits to existing files (add/remove/modify lines), refactoring
❌ NOT: When creating a new file (no existing content to patch) → use write_file
❌ NOT: When the file needs to be fully rewritten → use write_file

## file_search
✅ USE: Find files by name pattern when path is unknown
❌ NOT: Searching file content → use grep_search
❌ NOT: You already know the exact path → use read_file directly

## grep_search
✅ USE: Find where a symbol/string/pattern is used across files
❌ NOT: You need file structure → use list_dir
❌ NOT: You want to read a specific file → use read_file

## list_code_usages
✅ USE: Find all callers/references to a function, class, variable
❌ NOT: General text search → use grep_search
❌ NOT: Finding file by name → use file_search

## web_search
✅ USE: Current events, package versions, documentation lookup, error messages
❌ NOT: Local file content → use read_file/grep_search
❌ NOT: You have a direct URL → use web_fetch

## web_fetch
✅ USE: Read specific URL (docs, API specs, raw GitHub files)
❌ NOT: You need to find the URL first → use web_search first

## http_request
✅ USE: Call REST APIs with specific headers/body/method (not browser-like)
❌ NOT: Simple URL fetch without auth → use web_fetch

## spawn_subrun
✅ USE: Delegate a self-contained, long-running sub-task to a separate agent
❌ NOT: Simple single-tool operations → use the tool directly
⚠️  ALWAYS provide a fully self-contained prompt (goal + constraints + context)
```

---

## R3 · `config.py` – `_load_prompt_appendix()`

**Datei:** `backend/app/config.py`  
**Zweck:** Lädt die neuen Markdown-Dateien und hängt sie an die jeweiligen Prompts
an – ohne die bestehenden Prompt-Strings zu ändern.

### Schritt 1: Hilfsfunktion einfügen

Einfügen **nach** der `_resolve_prompt`-Funktion, **vor** `class AppSettings`:

```python
# backend/app/config.py – nach _resolve_prompt(), vor class AppSettings

import pathlib as _pathlib


def _load_prompt_appendix(filename: str, fallback: str = "") -> str:
    """Load a Markdown prompt file from app/prompts/. Returns fallback if missing."""
    base = _pathlib.Path(__file__).parent / "prompts" / filename
    try:
        return "\n\n" + base.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback


_AGENT_RULES_APPENDIX: str = _load_prompt_appendix("agent_rules.md")
_TOOL_ROUTING_APPENDIX: str = _load_prompt_appendix("tool_routing.md")
```

### Schritt 2: `head_agent_final_prompt` erweitern (Zeile ~232)

```python
# ALT:
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
        "HEAD_AGENT_FINAL_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_FINAL_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )

# NEU:
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
            + _AGENT_RULES_APPENDIX
        ),
        "HEAD_AGENT_FINAL_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
        "AGENT_FINAL_PROMPT",
        "AGENT_SYSTEM_PROMPT",
    )
```

### Schritt 3: `head_agent_tool_selector_prompt` erweitern (Zeile ~212)

```python
# ALT:
    head_agent_tool_selector_prompt: str = _resolve_prompt(
        "You select tools for user tasks. Strictly follow output format requirements.",
        "HEAD_AGENT_TOOL_SELECTOR_PROMPT",
        "AGENT_TOOL_SELECTOR_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
    )

# NEU:
    head_agent_tool_selector_prompt: str = _resolve_prompt(
        "You select tools for user tasks. Strictly follow output format requirements."
        + _TOOL_ROUTING_APPENDIX,
        "HEAD_AGENT_TOOL_SELECTOR_PROMPT",
        "AGENT_TOOL_SELECTOR_PROMPT",
        "HEAD_AGENT_SYSTEM_PROMPT",
    )
```

**Gleiche Änderung** analog für `agent_final_prompt` und `agent_tool_selector_prompt`
(die generischen Fallback-Prompts weiter unten in `config.py`).

---

## R4 · `reflection_service.py` – Hard-Gate

**Datei:** `backend/app/services/reflection_service.py`

**Problem:** `should_retry = score < self.threshold` – ein `factual_grounding=0.3`
wird durch `goal_alignment=0.9` + `completeness=0.9` ausgeglichen → score=0.7 → kein Retry.
Das ist falsch: niedrige factual_grounding muss immer Retry erzwingen.

### Schritt 1: `ReflectionVerdict` – neues Feld

```python
# ALT (Zeile 10):
@dataclass(frozen=True)
class ReflectionVerdict:
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    should_retry: bool

# NEU:
@dataclass(frozen=True)
class ReflectionVerdict:
    score: float
    goal_alignment: float
    completeness: float
    factual_grounding: float
    issues: list[str]
    suggested_fix: str | None
    should_retry: bool
    hard_factual_fail: bool = False  # True wenn factual_grounding < hard_min
```

### Schritt 2: `__init__` – neuer Parameter

```python
# ALT (Zeile 21):
class ReflectionService:
    def __init__(self, client: LlmClient, threshold: float = 0.6):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))

# NEU:
class ReflectionService:
    def __init__(
        self,
        client: LlmClient,
        threshold: float = 0.6,
        factual_grounding_hard_min: float = 0.4,
    ):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.factual_grounding_hard_min = max(0.0, min(1.0, float(factual_grounding_hard_min)))
```

### Schritt 3: `_parse_verdict()` – Hard-Gate Logik (letzte return-Anweisung)

```python
# ALT:
        return ReflectionVerdict(
            score=score,
            goal_alignment=goal_alignment,
            completeness=completeness,
            factual_grounding=factual_grounding,
            issues=issues,
            suggested_fix=suggested_fix,
            should_retry=score < self.threshold,
        )

# NEU:
        hard_factual_fail = factual_grounding < self.factual_grounding_hard_min
        return ReflectionVerdict(
            score=score,
            goal_alignment=goal_alignment,
            completeness=completeness,
            factual_grounding=factual_grounding,
            issues=issues,
            suggested_fix=suggested_fix,
            should_retry=(score < self.threshold) or hard_factual_fail,
            hard_factual_fail=hard_factual_fail,
        )
```

**Warum:** score=(0.9+0.9+0.3)/3=0.7 ≥ 0.6 → alter Code: `should_retry=False` (Bug).
Neuer Code: `hard_factual_fail=True` → `should_retry=True`, unabhängig vom score.

---

## R5 · `reflection_service.py` – Truncation Fix

**Problem A:** `tool_results[:1000]` schneidet kritische PIDs/Ports ab.
**Problem B:** `plan_text[:500]` zu kurz für mehrstufige Pläne.

### Schritt 1: `__init__` um Limits erweitern

```python
# NEU __init__ (vollständig, R4 + R5 kombiniert):
class ReflectionService:
    def __init__(
        self,
        client: LlmClient,
        threshold: float = 0.6,
        factual_grounding_hard_min: float = 0.4,
        tool_results_max_chars: int = 8000,
        plan_max_chars: int = 2000,
    ):
        self.client = client
        self.threshold = max(0.0, min(1.0, float(threshold)))
        self.factual_grounding_hard_min = max(0.0, min(1.0, float(factual_grounding_hard_min)))
        self.tool_results_max_chars = max(500, int(tool_results_max_chars))
        self.plan_max_chars = max(200, int(plan_max_chars))
```

### Schritt 2: `_build_reflection_prompt()` – konfigurierbare Limits

```python
# ALT:
    def _build_reflection_prompt(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
    ) -> str:
        return (
            "Evaluate this response. Return JSON with these fields:\n"
            '{"goal_alignment": 0.0-1.0, "completeness": 0.0-1.0, '
            '"factual_grounding": 0.0-1.0, "issues": ["..."], '
            '"suggested_fix": "..." or null}\n\n'
            f"User question: {user_message}\n"
            f"Plan: {plan_text[:500]}\n"
            f"Tool outputs: {tool_results[:1000]}\n"
            f"Final answer: {final_answer}"
        )

# NEU:
    def _build_reflection_prompt(
        self,
        *,
        user_message: str,
        plan_text: str,
        tool_results: str,
        final_answer: str,
    ) -> str:
        return (
            "Evaluate this response. Return JSON with these fields:\n"
            '{"goal_alignment": 0.0-1.0, "completeness": 0.0-1.0, '
            '"factual_grounding": 0.0-1.0, "issues": ["..."], '
            '"suggested_fix": "..." or null}\n\n'
            f"User question: {user_message}\n"
            f"Plan: {plan_text[:self.plan_max_chars]}\n"
            f"Tool outputs: {tool_results[:self.tool_results_max_chars]}\n"
            f"Final answer: {final_answer}"
        )
```

---

## R6 · `reflection_service.py` – System-Prompt Direktive

**Problem:** Aktueller System-Prompt:
```
"You are a quality assurance agent. Evaluate answers critically and objectively."
```
Gibt dem LLM keinerlei Anweisung wie `factual_grounding` zu bewerten ist.
Das ist der direkte openclaw-Ansatz: **den Fehler benennen und als Kontext verankern.**

### Modul-Level Konstante (nach den Imports, vor der Klasse)

```python
# NEU – nach den Imports, vor class ReflectionService:

_REFLECTION_SYSTEM_PROMPT = (
    "You are a quality assurance agent. Evaluate answers critically and objectively.\n\n"
    "## CRITICAL: Factual Grounding Scoring\n"
    "Score factual_grounding BELOW 0.4 if ANY of the following is true:\n"
    "  - The answer references a PID, port, IP, hostname, filename, line count,\n"
    "    file size, or timestamp that does NOT appear verbatim in the tool outputs\n"
    "  - The answer extrapolates, estimates, or derives numerical values not\n"
    "    explicitly present in the provided tool output\n"
    "  - The answer states facts about system state (processes, network, files)\n"
    "    that cannot be verified from the tool outputs above\n\n"
    "Score factual_grounding 0.0-0.2 if invented/hallucinated values are present.\n"
    "Score factual_grounding 0.8-1.0 ONLY if every factual claim maps verbatim to\n"
    "the provided tool output.\n\n"
    "## Completeness\n"
    "Score completeness based on whether all parts of the user's question are addressed.\n\n"
    "## Goal Alignment\n"
    "Score goal_alignment based on whether the answer solves the user's actual intent,\n"
    "not just the literal question."
)
```

### `reflect()` – Verweis auf Konstante

```python
# ALT (in reflect()):
        raw_verdict = await self.client.complete_chat(
            system_prompt="You are a quality assurance agent. Evaluate answers critically and objectively.",
            user_prompt=reflection_prompt,
            model=model,
            temperature=0.1,
        )

# NEU:
        raw_verdict = await self.client.complete_chat(
            system_prompt=_REFLECTION_SYSTEM_PROMPT,
            user_prompt=reflection_prompt,
            model=model,
            temperature=0.1,
        )
```

---

## R7 · `config.py` – Neue Reflection-Konfiguration

**Datei:** `backend/app/config.py`

Drei neue Env-Vars in `AppSettings`, die in R8 an `ReflectionService()` weitergegeben
werden.

```python
# ALT (ca. Zeile 640):
    reflection_enabled: bool = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
    reflection_threshold: float = float(os.getenv("REFLECTION_THRESHOLD", "0.6"))

# NEU:
    reflection_enabled: bool = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
    reflection_threshold: float = float(os.getenv("REFLECTION_THRESHOLD", "0.6"))
    reflection_factual_grounding_hard_min: float = float(
        os.getenv("REFLECTION_FACTUAL_GROUNDING_HARD_MIN", "0.4")
    )
    reflection_tool_results_max_chars: int = int(
        os.getenv("REFLECTION_TOOL_RESULTS_MAX_CHARS", "8000")
    )
    reflection_plan_max_chars: int = int(
        os.getenv("REFLECTION_PLAN_MAX_CHARS", "2000")
    )
```

---

## R8 · `agent.py` – ReflectionService mit neuen Params instanziieren

**Datei:** `backend/app/agent.py`

`ReflectionService()` wird an zwei Stellen instanziiert. Beide finden:

```bash
grep -n "ReflectionService(client=" backend/app/agent.py
```

```python
# ALT (beide Stellen, Zeile ~181 und ~317):
    ReflectionService(client=self.client, threshold=settings.reflection_threshold)

# NEU (beide Stellen identisch):
    ReflectionService(
        client=self.client,
        threshold=settings.reflection_threshold,
        factual_grounding_hard_min=settings.reflection_factual_grounding_hard_min,
        tool_results_max_chars=settings.reflection_tool_results_max_chars,
        plan_max_chars=settings.reflection_plan_max_chars,
    )
```

---

## R9 · Tests

**Datei:** `backend/tests/test_reflection_service.py`

Bestehende Tests bleiben grün. Die folgenden Tests ans Ende der Datei anfügen.

### Benötigter `fake_client` Fixture

Falls noch nicht vorhanden (in `conftest.py` oder am Anfang der Testdatei):

```python
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def fake_client():
    client = MagicMock()
    client.response = ""
    client.last_system_prompt = None

    async def _complete_chat(system_prompt, user_prompt, model=None, temperature=0.1):
        client.last_system_prompt = system_prompt
        return client.response

    client.complete_chat = _complete_chat
    return client
```

### Tests für R4 – Hard-Gate

```python
@pytest.mark.asyncio
async def test_hard_gate_triggers_retry_when_fg_below_min(fake_client):
    """factual_grounding 0.3 < hard_min 0.4 → should_retry=True despite high score."""
    fake_client.response = (
        '{"goal_alignment": 0.9, "completeness": 0.9, "factual_grounding": 0.3, '
        '"issues": ["hallucinated PID"], "suggested_fix": null}'
    )
    svc = ReflectionService(client=fake_client, threshold=0.6, factual_grounding_hard_min=0.4)
    verdict = await svc.reflect(
        user_message="check process",
        plan_text="run netstat",
        tool_results="no output",
        final_answer="PID 1234 is listening on port 8080",
    )
    assert verdict.hard_factual_fail is True
    assert verdict.should_retry is True
    # score = (0.9+0.9+0.3)/3 = 0.7 >= 0.6 → ohne Hard-Gate wäre should_retry=False
    assert verdict.score == pytest.approx(0.7, abs=0.01)


@pytest.mark.asyncio
async def test_hard_gate_not_triggered_when_fg_at_min(fake_client):
    """factual_grounding == hard_min → hard_factual_fail=False."""
    fake_client.response = (
        '{"goal_alignment": 0.8, "completeness": 0.8, "factual_grounding": 0.4, '
        '"issues": [], "suggested_fix": null}'
    )
    svc = ReflectionService(client=fake_client, threshold=0.6, factual_grounding_hard_min=0.4)
    verdict = await svc.reflect(
        user_message="q", plan_text="p", tool_results="t", final_answer="a"
    )
    assert verdict.hard_factual_fail is False


@pytest.mark.asyncio
async def test_hard_factual_fail_field_exists_on_verdict(fake_client):
    """hard_factual_fail muss als Feld in ReflectionVerdict existieren."""
    fake_client.response = (
        '{"goal_alignment": 1.0, "completeness": 1.0, "factual_grounding": 1.0, '
        '"issues": [], "suggested_fix": null}'
    )
    svc = ReflectionService(client=fake_client)
    verdict = await svc.reflect(
        user_message="q", plan_text="p", tool_results="t", final_answer="a"
    )
    assert hasattr(verdict, "hard_factual_fail")
    assert verdict.hard_factual_fail is False
```

### Tests für R5 – Truncation

```python
def test_prompt_uses_configurable_tool_results_limit():
    """tool_results_max_chars=200 → prompt enthält genau 200 Zeichen der tool_results."""
    from unittest.mock import MagicMock
    svc = ReflectionService(client=MagicMock(), tool_results_max_chars=200)
    long_output = "x" * 5000
    prompt = svc._build_reflection_prompt(
        user_message="q", plan_text="p", tool_results=long_output, final_answer="a"
    )
    assert "x" * 200 in prompt
    assert "x" * 201 not in prompt


def test_prompt_uses_configurable_plan_limit():
    """plan_max_chars=100 → prompt enthält genau 100 Zeichen des Plans."""
    from unittest.mock import MagicMock
    svc = ReflectionService(client=MagicMock(), plan_max_chars=100)
    long_plan = "p" * 5000
    prompt = svc._build_reflection_prompt(
        user_message="q", plan_text=long_plan, tool_results="t", final_answer="a"
    )
    assert "p" * 100 in prompt
    assert "p" * 101 not in prompt


def test_default_tool_results_limit_is_8000():
    from unittest.mock import MagicMock
    svc = ReflectionService(client=MagicMock())
    assert svc.tool_results_max_chars == 8000
```

### Tests für R6 – System-Prompt Direktive

```python
def test_reflection_system_prompt_contains_factual_grounding_directive():
    """_REFLECTION_SYSTEM_PROMPT muss die Zero-Tolerance-Direktive enthalten."""
    from app.services.reflection_service import _REFLECTION_SYSTEM_PROMPT
    assert "factual_grounding" in _REFLECTION_SYSTEM_PROMPT.lower()
    assert "0.4" in _REFLECTION_SYSTEM_PROMPT
    assert "verbatim" in _REFLECTION_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_reflect_passes_directive_system_prompt(fake_client):
    """reflect() muss _REFLECTION_SYSTEM_PROMPT als system_prompt übergeben."""
    from app.services.reflection_service import _REFLECTION_SYSTEM_PROMPT
    fake_client.response = (
        '{"goal_alignment": 0.8, "completeness": 0.8, "factual_grounding": 0.8, '
        '"issues": [], "suggested_fix": null}'
    )
    svc = ReflectionService(client=fake_client)
    await svc.reflect(user_message="q", plan_text="p", tool_results="t", final_answer="a")
    assert fake_client.last_system_prompt == _REFLECTION_SYSTEM_PROMPT
```

### Tests ausführen

```bash
# Nur Reflection-Tests:
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_reflection_service.py -o faulthandler_timeout=20

# Alle Tests (Smoke):
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/ -o faulthandler_timeout=20 --maxfail=1
```

---

## Gesamtbild nach dem Refactoring

```
backend/
  app/
    prompts/                          ← NEU (R1, R2)
      agent_rules.md                  ← Brain Anchor (Factual Footguns, Command Safety)
      tool_routing.md                 ← When / When NOT to Use pro Tool
    config.py                         ← R3: _load_prompt_appendix()
                                      ← R7: 3 neue Reflection-Vars
    services/
      reflection_service.py           ← R4: Hard-Gate + hard_factual_fail
                                      ← R5: 8000/2000-Limits statt 1000/500
                                      ← R6: _REFLECTION_SYSTEM_PROMPT Konstante
    agent.py                          ← R8: ReflectionService mit 5 Parametern
  tests/
    test_reflection_service.py        ← R9: 7 neue Tests
```

### Qualitätsverbesserungen im Vergleich zu vorher

| Dimension | Vorher | Nachher |
|---|---|---|
| Factual Halluzination | `score=0.7 → should_retry=False` (Bug) | `hard_factual_fail=True → should_retry=True` |
| Tool-Result-Kontext | 1.000 Zeichen – PIDs abgeschnitten | 8.000 Zeichen – vollständige Ausgaben |
| Plan-Kontext | 500 Zeichen | 2.000 Zeichen |
| Reflection-Anweisung | Generischer QA-Prompt | Zero-Tolerance-Direktive für numerische Werte |
| Tool-Routing | LLM entscheidet blind | `tool_routing.md` sagt: "When NOT to use" |
| Synthesizer-Kontext | Nur Python-Prompt-String | + Persistent-injizierte `agent_rules.md` |
| Sub-Agent Prompts | Kein Standard | `agent_rules.md` definiert Self-Contained-Anforderung |

### Die drei Qualitätsschichten nach dem Refactoring

```
openclaw:   Qualität durch Dokumentation → Fehler werden verhindert
Unser Agent: Qualität durch Feedback-Loops → Fehler werden detektiert und korrigiert

Nach diesem Refactoring:
  Schicht 1: agent_rules.md verhindert Fehler (openclaw-Prinzip)
  Schicht 2: Reflection System-Prompt schärft Erkennung
  Schicht 3: Hard-Gate korrigiert was durch die Schichten 1+2 durchkommt
```

Das ist strukturell besser als openclaw: openclaw hat nur Schicht 1.
Wir haben Schicht 1 + 2 + 3.
