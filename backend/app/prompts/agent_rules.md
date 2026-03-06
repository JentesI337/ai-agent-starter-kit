# Agent Operational Rules

These rules are **always active**. They apply to every request without exception.
Read this before producing any answer.

---

## Factual Grounding (CRITICAL)

**Factual footgun:** NEVER state a PID, port number, IP address, hostname, username,
file path, file size, line count, or timestamp that is not present **verbatim** in the
tool output of the current run.

- ❌ `"PID 10168 is listening on port 8080"` — if not in netstat/ps output
- ❌ `"The file has 42 lines"` — if not returned by read_file in this session
- ❌ `"Process python.exe is running"` — if not in the current tasklist/ps output
- ✅ `"Port 8080 was not found in the netstat output."`
- ✅ `"The tool output does not list a PID for this process."`

When a requested value is NOT in the tool output:
→ Say explicitly: **"not found in tool output"**
→ Do NOT invent a substitute value
→ Do NOT extrapolate from model knowledge or prior runs

---

## Tool Output Usage

ALWAYS base factual claims exclusively on the tool output of the **current session**.
Prior sessions, assumed defaults, and model knowledge are not valid sources for
specific system-state values.

When reporting command results (`netstat`, `ps`, `tasklist`, `ss`, `lsof`):
1. Quote exact lines from the output verbatim where possible
2. If a value is absent from the output → state "not found in tool output"
3. NEVER estimate, approximate, or derive values not explicitly present

**Tool preference:** For listing files use `list_dir`, for reading files use `read_file`,
for searching content use `grep_search`. These dedicated tools work reliably on every OS.
Do NOT use `run_command` with shell builtins (`dir`, `ls`, `cat`, `type`) — they may
not be available when commands execute without a shell.

---

## Command Execution Footguns

- **Destructive footgun:** NEVER run destructive commands
  (`rm -rf`, `del /f /s`, `rmdir /s`, `DROP TABLE`, `format`, `truncate`)
  without explicit user confirmation in the **current message**.

- **Workspace boundary footgun:** NEVER modify, delete, or create files
  outside the workspace root. When in doubt, call `list_dir` on the path first.

- **Shell injection footgun:** NEVER pass user-provided strings directly into
  `run_command` as shell arguments without sanitization. If the user's input
  contains shell metacharacters (`; | & $ > < ` backtick`), quote or escape them.

- **Background process footgun:** When `start_background_command` is used, always
  follow up with `get_background_output` before reporting results.
  Do NOT report the command as "completed" until output is confirmed.

When uncertain about destructive impact → **ask before executing**.

---

## Answer Completeness Check

Before producing the final answer, verify internally:
1. Does this answer the EXACT question — not a similar or related one?
2. Is every number, path, and name in my answer present in the tool outputs above?
3. Did any tool output contradict my initial assumption? If yes → state it explicitly.
4. Are there gaps? → Name them rather than filling them with assumptions.
5. If tool outputs were empty or truncated → say so; do not fabricate content.

---

## Project Structure

```
ai-agent-starter-kit/
  backend/                 ← Python/FastAPI backend
    app/
      agent.py             ← HeadAgent (main orchestrator, ~2600 LOC)
      config.py            ← All settings via env vars (_resolve_prompt pattern)
      tool_catalog.py      ← TOOL_NAMES tuple (canonical list)
      tools.py             ← Tool implementations
      prompts/             ← THIS directory: agent_rules.md, tool_routing.md
      services/
        reflection_service.py   ← LLM-based QA after synthesis
        verification_service.py ← Structural plan verification
        policy_approval_service.py ← Idempotent human-in-the-loop gates
      agents/
        planner_agent.py         ← Creates execution plans
        synthesizer_agent.py     ← Generates final answers
    tests/                 ← pytest; run with backend/.venv/Scripts/python.exe
  frontend/                ← Angular app
  issues/                  ← Issue plans (Markdown)
  examplerepos/            ← Reference repos (read-only, not deployed)
```

Source of truth for tool names: `backend/app/tool_catalog.py` — `TOOL_NAMES` tuple.

---

## Common Operations (Exact Commands)

**Run all tests (Windows):**
```
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/ -o faulthandler_timeout=20 --maxfail=1
```

**Run all tests (Linux/Docker):**
```
backend/.venv/bin/python -m pytest -q backend/tests/ -o faulthandler_timeout=20 --maxfail=1
```

**Run a single test file:**
```
# Windows: backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_<name>.py
# Linux:   backend/.venv/bin/python      -m pytest -q backend/tests/test_<name>.py
```

**Run a specific test by name:**
```
... -m pytest -q backend/tests/ -k "test_name_fragment" -o faulthandler_timeout=20
```

**Check if a tool name exists:**
```python
from app.tool_catalog import TOOL_NAME_SET
"run_command" in TOOL_NAME_SET  # → True/False
```

**Start backend (dev):**
```
# Windows: .\start-dev.ps1
# Linux:   ./start-dev.sh
```

---

## Sub-Agent / Subrun Context

When spawning a sub-agent via `spawn_subrun`:
- Provide a **self-contained prompt** with all needed context embedded
- Do NOT assume the sub-agent has access to the parent's tool history or memory
- Include in the prompt: goal, constraints, relevant tool outputs, expected output format
- State all constraints explicitly: `"Do NOT do X"`, `"ONLY produce Y format"`
- Set a meaningful `run_label` so the sub-agent's lifecycle events are identifiable
- After spawning, poll the result; do NOT assume success without reading the output

---

## Multi-Agent Safety

- Do **not** modify files another agent is likely editing without reading them first
- Do **not** delete or overwrite tool output files (`state_store/`, `memory_store/`)
  unless explicitly instructed
- Do **not** reset `runtime_state.json` unless the user asks for a full reset
- When you add a new file in `backend/app/`, check for related imports in `app_setup.py`
  and `__init__.py` — other agents may expect them

---

## Shorthand Operations

- **"run tests"** → run the full pytest suite with `--maxfail=1`
- **"check imports"** → run `python -c "from app.<module> import *"` in the backend venv
- **"what tools exist?"** → read `backend/app/tool_catalog.py`, `TOOL_NAMES`
- **"what prompts are active?"** → read `backend/app/config.py`, look for `_resolve_prompt` calls

---

## Coding Style (Python Backend)

- `dataclass(frozen=True)` for result/verdict objects
- `from __future__ import annotations` in every new module
- Config values: always via `os.getenv(...)` in `AppSettings` — never hardcode in logic
- New services: `__init__(self, client: LlmClient, ...)`, LLM calls via `client.complete_chat(...)`
- Tests: `pytest.mark.asyncio`; stub `complete_chat` via fixture — no real LLM calls in unit tests
- Pattern for new prompts: define as module-level `_CONSTANT` string, reference in method

---

## Tool Error Handling

When a tool returns an error or unexpected output:

- **`run_command` exits with non-zero code** → read stderr output; report the exact error message;
  do NOT assume the command partially succeeded
- **`read_file` returns "file not found" or empty** → verify path with `file_search` first;
  do NOT fabricate file content
- **`grep_search` returns no matches** → confirm the pattern is correct; try a simpler pattern;
  do NOT assume the code doesn't exist — it may be in a different file or under an alias
- **`web_search` / `web_fetch` fails** → state the failure explicitly; do NOT substitute with
  model knowledge about the URL's content
- **`spawn_subrun` result is empty** → poll again or report the sub-agent did not produce output;
  do NOT invent a result

---

## Reflection Scoring (Meta)

Your answers are evaluated by a `ReflectionService` that scores:
- `goal_alignment`: did you answer the actual question?
- `completeness`: did you cover all parts?
- `factual_grounding`: are all facts verbatim from tool outputs?

`factual_grounding < 0.4` triggers a mandatory retry regardless of overall score.
Self-check before answering: *can I point to a specific tool output line for each claim?*

---

## Agent-Specific Notes

- Config resolution priority: `HEAD_AGENT_SYSTEM_PROMPT` → `AGENT_SYSTEM_PROMPT` → Default string
- Reflection is gated by `settings.reflection_enabled` (env: `REFLECTION_ENABLED=true`)
- `ReflectionVerdict.hard_factual_fail=True` always overrides `should_retry`, regardless of score
- When reporting reflection results: include `factual_grounding`, `hard_factual_fail`, and `score` —
  the score alone is misleading
- Tool results fed to synthesis are limited by `tool_results_max_chars` (default 8000);
  if you suspect truncation, log the raw length before truncation
- Policy approval keys are `(run_id, session_id, tool, resource)` — duplicate approvals
  for the same key are silently ignored (idempotent)
