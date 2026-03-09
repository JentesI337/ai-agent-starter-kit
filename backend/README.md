# Backend (Head Agent)

## Setup (Windows)

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Setup (Linux/macOS)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

`WORKSPACE_ROOT` can be relative (`.`) or absolute. Relative paths are resolved from the `backend` folder.

`ORCHESTRATOR_STATE_DIR` controls where external run state JSON files are persisted (default: `backend/state_store`).

`MEMORY_RESET_ON_STARTUP` and `ORCHESTRATOR_STATE_RESET_ON_STARTUP` are environment-aware by default:
- development: `true`
- production: `false`

Quick operational checks are documented in `SMOKE_RUNBOOK.md`.

## Test & Coverage Gate

- Root helper scripts `start-test.ps1` / `start-test.sh` now run backend tests with coverage gates enabled.
- Global minimum coverage: `70%`.
- Critical module minimum coverage uses the default profile from `scripts/check_coverage_thresholds.py` (`--use-default-thresholds`):
	- `backend/app/services/tool_call_gatekeeper.py` >= `90%`
	- `backend/app/tools.py` >= `80%`
	- `backend/app/agent.py` >= `60%`
	- `backend/app/orchestrator/pipeline_runner.py` >= `65%`
	- `backend/app/services/tool_arg_validator.py` >= `95%`

Direct run from `backend`:

```powershell
./.venv/Scripts/python.exe -m pytest tests -q --cov=app --cov-report=term-missing --cov-report=json:coverage.json --cov-fail-under=70
./.venv/Scripts/python.exe scripts/check_coverage_thresholds.py --coverage-json coverage.json --global-min 70 --use-default-thresholds
```

Eval-Gates (Golden-Suite + KPI-Schwellen):

```powershell
./.venv/Scripts/python.exe scripts/run_eval_gates.py
```

Manifest (versioniert):
- `backend/monitoring/eval_golden_suite.json`
- enthält aktuell `30` repräsentative Flows über `success|replan|tool_loop|invalid_final`

Optional explizit mit Suite-Pfad:

```powershell
./.venv/Scripts/python.exe scripts/run_eval_gates.py --suite-path backend/monitoring/eval_golden_suite.json
```

Default-Gates:
- `overall_success_rate >= 1.0`
- `replan_success_rate >= 1.0`
- `tool_loop_success_rate >= 1.0`
- `invalid_final_rate <= 0.0`

Override über Umgebungsvariablen:
- `EVAL_GATE_OVERALL_SUCCESS_RATE_MIN`
- `EVAL_GATE_REPLAN_SUCCESS_RATE_MIN`
- `EVAL_GATE_TOOL_LOOP_SUCCESS_RATE_MIN`
- `EVAL_GATE_INVALID_FINAL_RATE_MAX`

WebSocket test stability:
- Use `receive_json_with_timeout` from `backend/tests/async_test_guards.py` in websocket tests.
- Avoid direct `ws.receive_json()` calls in loops, because lifecycle/event volume can change and block indefinitely.
- Recommended pytest flags for WS-focused runs:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ws_handler.py tests/test_backend_e2e.py -q -o faulthandler_timeout=20 --maxfail=1
```

## WebSocket

- Endpoint: `ws://localhost:8000/ws/agent`
- Send JSON:

```json
{
	"type": "user_message",
	"content": "Build me an API agent",
	"agent_id": "head-agent",
	"preset": "research",
	"model": "llama3.3:70b-instruct-q4_K_M",
	"session_id": "optional-stable-session-id"
}
```

Available agent IDs: `head-agent`, `coder-agent`, and `review-agent`.

Available presets:
- `research`
- `review`

Fetch preset policies via `GET /api/presets`.

Preset behavior:
- Preset tool policy is merged with request `tool_policy`.
- If `head-agent` is requested and preset is `review`, routing is delegated to `review-agent`.

The server streams progress messages (`status`, `agent_step`, `token`, `final`, `error`, `lifecycle`).

Runtime switch messages:

```json
{
	"type": "runtime_switch_request",
	"runtime_target": "local"
}
```

```json
{
	"type": "runtime_switch_request",
	"runtime_target": "api"
}
```

Runtime targets/models:
- local: `LOCAL_MODEL` (default biggest local 70B)
- api: `API_MODEL` defaults to `minimax-m2:cloud` and supports `gpt-oss:20b-cloud`, `qwen3-coder:480b-cloud`
- optional: `API_SUPPORTED_MODELS` can define the supported API cloud-model list for backend status/config
- optional: `OLLAMA_BIN` can be set if `ollama` is not on PATH.

Lifecycle `stage` examples:
- `request_received`
- `request_dispatched`
- `run_started`
- `guardrails_passed`
- `memory_updated`
- `planning_started`, `planning_completed`
- `tool_selection_started`, `tool_selection_completed`
- `tool_started`, `tool_completed`, `tool_failed`
- `streaming_started`, `streaming_completed`
- `run_completed`, `request_completed`
- `model_route_selected`, `model_fallback_retry`
- `skills_discovered`, `skills_truncated`, `skills_skipped_canary`

## Skills Engine (Feature-Flag + Canary)

The backend includes a modular skills system (`app/skills/*`) that can enrich tool-selection context with discovered/eligible skills.

Key environment variables:
- `SKILLS_ENGINE_ENABLED` (default: `false`)
- `SKILLS_CANARY_ENABLED` (default: `false`)
- `SKILLS_CANARY_AGENT_IDS` (csv, default: `head-agent`)
- `SKILLS_CANARY_MODEL_PROFILES` (csv, default: `*`)
- `SKILLS_DIR` (default: `<workspace>/skills`)
- `SKILLS_MAX_DISCOVERED` (default: `150`)
- `SKILLS_MAX_PROMPT_CHARS` (default: `30000`)

Behavior:
- If `SKILLS_ENGINE_ENABLED=false`, skills are fully disabled.
- If `SKILLS_ENGINE_ENABLED=true` and `SKILLS_CANARY_ENABLED=false`, skills are globally enabled.
- If both are `true`, skills are enabled only when both canary matchers pass:
	- agent role matches `SKILLS_CANARY_AGENT_IDS`
	- model id/profile matches `SKILLS_CANARY_MODEL_PROFILES`
- When blocked by canary, lifecycle emits `skills_skipped_canary`.

## Skills Control-Plane

Available endpoints:
- `POST /api/control/skills.list`
- `POST /api/control/skills.preview`
- `POST /api/control/skills.check`
- `POST /api/control/skills.sync`

`skills.sync` modes and safety:
- `apply=false` => dry-run plan only
- `apply=true` => execute sync
- optional `clean_target=true` => also plan stale target skill-dir deletions
- with `clean_target=true` and `apply=true`, `confirm_clean_target=true` is required
- target dir must be inside `WORKSPACE_ROOT`

`skills.sync` response includes audit fields:
- `audit.started_at`
- `audit.duration_ms`
- counters for planned/apply/delete (`planned_count`, `planned_delete_count`, `applied_count`, `applied_delete_count`)

## Current agent capabilities

- Memory context per session (`session_id`) with rolling window, persisted in `MEMORY_PERSIST_DIR`.
- Persisted session files are automatically trimmed to `MEMORY_MAX_ITEMS` entries.
- External run state persistence in `ORCHESTRATOR_STATE_DIR` with per-run JSON and summary snapshots.
- Tooling: `list_dir`, `read_file`, `write_file`, `run_command`, `code_execute`, `apply_patch`, `file_search`, `grep_search`, `list_code_usages`, `get_changed_files`, `start_background_command`, `get_background_output`, `kill_background_process`, `web_fetch`, `browser_navigate`, `browser_screenshot`, `browser_click`, `browser_fill`, `browser_evaluate`, `browser_close`, `rag_ingest`, `rag_query`, `rag_collections`.
- `code_execute` runs Python/JavaScript snippets with timeout, output limits, temporary jail execution, network disabled by default, and policy checks for obvious filesystem escape patterns.
- Execution model: Plan -> Execute tools -> Review/final response.
- Guardrails: empty/oversized input and invalid model/session values are blocked and returned as `error` events.
- Tool selection is validated; malformed JSON or invalid actions are reported as lifecycle/error events (no silent fallback).

## Optional Features (Feature-Toggles)

Each optional feature can be enabled/disabled via environment variables. Disabled features remove their tools from the active tool catalog.

### Code Interpreter (Persistent REPL)

Persistent Python/JavaScript sessions with timeout, memory limits, and sandboxed execution.

```
REPL_ENABLED=true              # default: true
REPL_TIMEOUT_SECONDS=30
REPL_MAX_MEMORY_MB=256
REPL_MAX_SESSIONS=8
REPL_MAX_OUTPUT_CHARS=50000
REPL_SANDBOX_DIR=repl_sandbox
```

Tools: `code_execute`, `code_reset`

### Browser Control (Playwright)

Headless Chromium browser pool for web automation (navigate, screenshot, click, fill, evaluate).

```
BROWSER_ENABLED=true           # default: true
BROWSER_MAX_CONTEXTS=4
BROWSER_NAVIGATION_TIMEOUT_MS=30000
BROWSER_CONTEXT_TTL_SECONDS=300
BROWSER_MAX_PAGE_TEXT_CHARS=50000
```

Additional setup:

```bash
pip install playwright
playwright install chromium
```

Tools: `browser_navigate`, `browser_screenshot`, `browser_click`, `browser_fill`, `browser_evaluate`, `browser_close`

### RAG Engine (ChromaDB + Embeddings)

Document ingestion, chunking, vector storage, and semantic retrieval.

```
RAG_ENABLED=false              # default: false
RAG_EMBEDDING_PROVIDER=ollama  # ollama | openai
RAG_EMBEDDING_MODEL=nomic-embed-text
RAG_EMBEDDING_BASE_URL=http://localhost:11434
RAG_EMBEDDING_API_KEY=
RAG_PERSIST_DIR=rag_store
RAG_MAX_CHUNKS_PER_COLLECTION=10000
RAG_DEFAULT_TOP_K=5
```

Additional setup:

```bash
pip install chromadb
# Optional for PDF ingestion:
pip install pymupdf
```

Tools: `rag_ingest`, `rag_query`, `rag_collections`

## Custom Flows (Create, Select, Run)

- Create custom agents via `POST /api/custom-agents` with:
	- `name`, `base_agent_id` (`head-agent`, `coder-agent`, or `review-agent`), `workflow_steps[]`
- List current custom agents via `GET /api/custom-agents`.
- Use custom agent id through websocket `agent_id` in `/ws/agent` messages.
- Remove custom agents via `DELETE /api/custom-agents/{id}`.

Custom agent definitions are stored in `CUSTOM_AGENTS_DIR` (default: `backend/custom_agents`).

## Optional real API E2E tests (small/large model + subrun)

Real API E2E tests now run by default in the backend suite (strict mode, no auto-skip).

Enable and run:

```powershell
$env:OLLAMA_CLOUD_API_BASE_URL="http://localhost:11434/api"
$env:OLLAMA_CLOUD_MODEL_SMALL="minimax-m2:cloud"
$env:OLLAMA_CLOUD_MODEL_LARGE="qwen3-coder:480b-cloud"
pytest backend/tests/test_backend_e2e_real_api.py -q
```

Optional timeout tuning:
- `REAL_API_E2E_WAIT_TIMEOUT_MS` (default: `120000`)

Emergency opt-out (explicit only):
- `SKIP_REAL_OLLAMA_API_E2E=1`

## Agent Benchmarking (easy/mid/hard)

Repository-Root Startskripte:
- Windows: `./start-benchmark.ps1`
- Linux/macOS: `./start-benchmark.sh`

Direkt im Backend:

```powershell
cd backend
./.venv/Scripts/python.exe benchmarks/run_benchmark.py --base-url http://127.0.0.1:8000 --levels easy,mid,hard --runs-per-case 1
```

Benchmark-Szenarien liegen in:
- `benchmarks/scenarios/default.json`

Szenario-Override über Root-Startskript (Windows Beispiel):
- `./start-benchmark.ps1 -ScenarioFile backend/benchmarks/scenarios/default.json`

Output-Artefakte:
- `monitoring/benchmarks/<timestamp-uuid>/summary.md`
- `monitoring/benchmarks/<timestamp-uuid>/results.json`
- `monitoring/benchmarks/<timestamp-uuid>/*.events.jsonl`

Bewertung v2:
- Cases mit `gate=true` bestimmen den Exit-Code des Benchmarks.
- Cases mit `gate=false` sind diagnostisch und fließen nur in die Gesamtstatistik ein.

Strategie-Dokument:
- `BENCHMARK_STRATEGY.md`

GitHub Actions (manual):
- Workflow: `.github/workflows/backend-real-api-e2e.yml`
- Trigger via `workflow_dispatch` and set:
	- `api_base_url`
	- `small_model`
	- `large_model`
	- `wait_timeout_ms`
- The workflow enables `RUN_REAL_OLLAMA_API_E2E=1` and executes `backend/tests/test_backend_e2e_real_api.py`.

## Refactoring status

- Contract layer introduced (`app/contracts`).
- Head agent is consumed through adapter (`app/agents/head_agent_adapter.py`).
- Transport delegates execution via orchestrator interface (`app/interfaces/orchestrator_api.py`).
- Deterministic pipeline runner scaffold added (`app/orchestrator/pipeline_runner.py`).
- Hard context-budget reduction per step added (`app/state/context_reducer.py`).
- Model capability profiles and registry added (`app/model_routing`).
- Centralized model router with fallback chain added (`app/model_routing/router.py`) and executed in orchestrator runner.
- Head flow split into contract agents (`planner`, `tool_selector`, `synthesizer`) orchestrated deterministically in `HeadAgent`.
