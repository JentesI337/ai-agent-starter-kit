# AI Agent Starter Kit

Starter project with:
- Python head agent (`backend`)
- Angular UI (`frontend`)
- WebSocket streaming updates from agent to UI

## One-command startup (root)

Windows (PowerShell):

```powershell
./start-dev.ps1
```

Manual cleanup (free backend/frontend ports):

```powershell
./clean-dev.ps1
```

Linux/macOS:

```bash
chmod +x ./start-dev.sh
./start-dev.sh
```

Manual cleanup (free backend/frontend ports):

```bash
chmod +x ./clean-dev.sh
./clean-dev.sh
```

Optional ports:

- Windows: `./start-dev.ps1 -LlmPort 11434 -BackendPort 8000 -FrontendPort 4200`
- Linux/macOS: `LLM_PORT=11434 BACKEND_PORT=8000 FRONTEND_PORT=4200 ./start-dev.sh`

Runtime mode selection:

- Interactive prompt on startup (`local` or `api`)
- Windows non-interactive: `./start-dev.ps1 -RuntimeMode local` or `./start-dev.ps1 -RuntimeMode api`
- Linux/macOS non-interactive: `RUNTIME_MODE=local ./start-dev.sh` or `RUNTIME_MODE=api ./start-dev.sh`

API runtime uses local Ollama API with cloud model naming:
- Startup persists `API_BASE_URL=http://localhost:11434/api` in `backend/.env` for `api` mode
- Startup persists `API_MODEL=minimax-m2:cloud` for `api` mode
- No additional credential setup is required in-app

What the scripts do:
- check/install Ollama for all runtime modes and persist CLI path to backend `.env` (`OLLAMA_BIN`)
- ensure local Ollama server is running for `local` runtime (and adjust `LLM_BASE_URL`)
- install Python + backend deps, then run backend
- install Node.js/npm, install frontend deps, build frontend, run frontend

Ollama install flow (used by runtime switching):
- Windows install command: `irm https://ollama.com/install.ps1 | iex`
- Linux install command: `curl -fsSL https://ollama.com/install.sh | sh`

Startup safeguards:
- Linux package-manager fallback supports `apt`, `dnf`, `pacman`, `zypper`.
- Script fails fast on port conflicts for backend/frontend ports.
- Startup scripts run `clean-dev` automatically before startup to clear stale backend/frontend listeners.
- If LLM port is already open, script verifies that Ollama API is actually on that port.
- Startup scripts always use `backend/.venv` as the canonical Python environment (root `.venv` is ignored with warning).
- Runtime switch backend also supports explicit Ollama binary override via `backend/.env` -> `OLLAMA_BIN`.

## Backend tests (E2E)

Windows (PowerShell):

```powershell
./start-test.ps1
```

Linux/macOS:

```bash
chmod +x ./start-test.sh
./start-test.sh
```

Optional fast rerun (skip install):
- Windows: `./start-test.ps1 -SkipInstall`
- Linux/macOS: `SKIP_INSTALL=1 ./start-test.sh`

## 1) Start backend (Windows)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

## 1b) Start backend (Linux/macOS)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Configure `.env` for your local Llama 70B endpoint (OpenAI-compatible API):
- `LLM_BASE_URL` (example: `http://localhost:11434/v1`)
- `LLM_MODEL`

## 2) Start frontend (Windows/Linux/macOS)

```powershell
cd frontend
npm install
npm start
```

Open `http://localhost:4200`.

## Features

- `Chat` page:
  - sends `user_message` to `ws://localhost:8000/ws/agent`
  - includes minimal `agent` and `model` selection
  - runtime switch (`local` 70B / `api` minimax-m2:cloud) with persisted preference
  - auto-reconnects websocket if connection drops
  - receives live events: `status`, `agent_step`, `token`, `final`, `error`
- `Agents` page:
  - loads agents from `GET http://localhost:8000/api/agents`

Backend head agent pipeline:
- session memory context store
- tools (`list_dir`, `read_file`, `write_file`, `run_command`)
- simple Plan -> Execute -> Review flow
- guardrail validation with frontend-visible error events

## Goal support

This gives you a running UI + head coding agent foundation so the head agent can be used to design/build more agents and evolve their configurations.
