# Backend (Head Agent)

## Setup (Windows)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Setup (Linux/macOS)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

`WORKSPACE_ROOT` can be relative (`.`) or absolute. Relative paths are resolved from the `backend` folder.

`ORCHESTRATOR_STATE_DIR` controls where external run state JSON files are persisted (default: `backend/state_store`).

## WebSocket

- Endpoint: `ws://localhost:8000/ws/agent`
- Send JSON:

```json
{
	"type": "user_message",
	"content": "Build me an API agent",
	"agent_id": "head-coder",
	"model": "llama3.3:70b-instruct-q4_K_M",
	"session_id": "optional-stable-session-id"
}
```

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
- api: `API_MODEL` defaults to `minimax-m2:cloud` (configurable via env)
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

## Current agent capabilities

- Memory context per session (`session_id`) with rolling window, persisted in `MEMORY_PERSIST_DIR`.
- Persisted session files are automatically trimmed to `MEMORY_MAX_ITEMS` entries.
- External run state persistence in `ORCHESTRATOR_STATE_DIR` with per-run JSON and summary snapshots.
- Tooling: `list_dir`, `read_file`, `write_file`, `run_command`.
- Execution model: Plan -> Execute tools -> Review/final response.
- Guardrails: empty/oversized input and invalid model/session values are blocked and returned as `error` events.
- Tool selection is validated; malformed JSON or invalid actions are reported as lifecycle/error events (no silent fallback).

## Refactoring status

- Contract layer introduced (`app/contracts`).
- Head agent is consumed through adapter (`app/agents/head_coder_adapter.py`).
- Transport delegates execution via orchestrator interface (`app/interfaces/orchestrator_api.py`).
- Deterministic pipeline runner scaffold added (`app/orchestrator/pipeline_runner.py`).
- Hard context-budget reduction per step added (`app/state/context_reducer.py`).
- Model capability profiles and registry added (`app/model_routing`).
- Centralized model router with fallback chain added (`app/model_routing/router.py`) and executed in orchestrator runner.
- Head flow split into contract agents (`planner`, `tool_selector`, `synthesizer`) orchestrated deterministically in `HeadCodingAgent`.
