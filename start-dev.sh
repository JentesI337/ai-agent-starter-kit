#!/usr/bin/env bash
set -euo pipefail

LLM_PORT="${LLM_PORT:-11434}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-4200}"
RUNTIME_MODE="${RUNTIME_MODE:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step() {
  echo
  echo "==> $1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

resolve_runtime_mode() {
  if [[ "$RUNTIME_MODE" == "local" || "$RUNTIME_MODE" == "api" ]]; then
    echo "$RUNTIME_MODE"
    return
  fi

  echo "Select runtime mode:"
  echo "1) local (70B)"
  echo "2) api (qwen2.5:7b-instruct)"
  read -r -p "Enter 1 or 2: " choice
  if [[ "$choice" == "2" ]]; then
    echo "api"
  else
    echo "local"
  fi
}

warn_root_venv_conflict() {
  local root_venv="$ROOT_DIR/.venv"
  local backend_venv="$ROOT_DIR/backend/.venv"
  if [[ -d "$root_venv" && "$root_venv" != "$backend_venv" ]]; then
    echo "Warning: Found root .venv at $root_venv. Startup uses backend/.venv only." >&2
  fi
}

ensure_root_or_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    return
  fi
  if ! has_cmd sudo; then
    echo "Need root or sudo privileges for package installation." >&2
    exit 1
  fi
}

install_packages() {
  local pkgs=("$@")
  ensure_root_or_sudo

  if has_cmd apt-get; then
    sudo apt-get update
    sudo apt-get install -y "${pkgs[@]}"
    return
  fi

  if has_cmd dnf; then
    sudo dnf install -y "${pkgs[@]}"
    return
  fi

  if has_cmd pacman; then
    sudo pacman -Sy --noconfirm "${pkgs[@]}"
    return
  fi

  if has_cmd zypper; then
    sudo zypper --non-interactive install "${pkgs[@]}"
    return
  fi

  echo "Unsupported package manager. Install dependencies manually and rerun." >&2
  exit 1
}

ensure_ollama() {
  local ollama_path=""
  ollama_path="$(command -v ollama || true)"
  if [[ -n "$ollama_path" ]]; then
    echo "$ollama_path"
    return
  fi

  if has_cmd ollama; then
    command -v ollama
    return
  fi

  step "Ollama not found, trying install script"
  curl -fsSL https://ollama.com/install.sh | sh

  ollama_path="$(command -v ollama || true)"
  if [[ -z "$ollama_path" && -x "/usr/local/bin/ollama" ]]; then
    ollama_path="/usr/local/bin/ollama"
  fi

  if [[ -z "$ollama_path" ]]; then
    echo "Ollama install failed. Install from https://ollama.com and rerun." >&2
    exit 1
  fi

  echo "$ollama_path"
}

port_open() {
  local port="$1"
  if has_cmd ss; then
    if ss -ltn "sport = :$port" | tail -n +2 | grep -q .; then
      echo "1"
      return
    fi
    echo "0"
    return
  fi

  if has_cmd lsof; then
    if lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
      echo "1"
      return
    fi
    echo "0"
    return
  fi

  if has_cmd nc; then
    if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
      echo "1"
      return
    fi
    echo "0"
    return
  fi

  if timeout 1 bash -c "</dev/tcp/127.0.0.1/$port" >/dev/null 2>&1; then
    echo "1"
  else
    echo "0"
  fi
}

require_port_free() {
  local port="$1"
  local service="$2"
  if [[ "$(port_open "$port")" == "1" ]]; then
    echo "Port conflict: $service cannot start because port $port is already in use." >&2
    echo "Use a different port via environment variables and rerun." >&2
    exit 1
  fi
}

ensure_ollama_endpoint_on_port() {
  local port="$1"
  if ! curl -fsS "http://127.0.0.1:$port/api/tags" >/dev/null 2>&1; then
    echo "Port $port is open but Ollama API is not responding there." >&2
    echo "Set LLM_PORT to the correct Ollama port and rerun." >&2
    exit 1
  fi
}

ensure_ollama_running() {
  local port="$1"
  local ollama_bin="$2"
  if [[ "$(port_open "$port")" == "1" ]]; then
    ensure_ollama_endpoint_on_port "$port"
    echo "Ollama already running on port $port"
    return
  fi

  step "Starting Ollama on port $port"
  OLLAMA_HOST="127.0.0.1:$port" nohup "$ollama_bin" serve >/tmp/ollama.log 2>&1 &

  for _ in {1..15}; do
    sleep 1
    if [[ "$(port_open "$port")" == "1" ]]; then
      ensure_ollama_endpoint_on_port "$port"
      echo "Ollama started on port $port"
      return
    fi
  done

  echo "Ollama did not start on port $port" >&2
  exit 1
}

ensure_python() {
  if has_cmd python3; then
    return
  fi

  step "python3 not found, trying package-manager install"
  install_packages python3 python3-venv python3-pip

  if ! has_cmd python3; then
    echo "Python install failed. Install Python 3.11+ and rerun." >&2
    exit 1
  fi
}

ensure_node() {
  if has_cmd node && has_cmd npm; then
    return
  fi

  step "Node.js/npm not found, trying package-manager install"
  if has_cmd apt-get; then
    ensure_root_or_sudo
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
  elif has_cmd dnf; then
    install_packages nodejs npm
  elif has_cmd pacman; then
    install_packages nodejs npm
  elif has_cmd zypper; then
    install_packages nodejs npm
  else
    echo "Unsupported package manager for Node.js install." >&2
    exit 1
  fi

  if ! has_cmd node || ! has_cmd npm; then
    echo "Node.js install failed. Install Node.js LTS and rerun." >&2
    exit 1
  fi
}

ensure_backend_env() {
  local env_file="$ROOT_DIR/backend/.env"
  local env_example="$ROOT_DIR/backend/.env.example"

  if [[ ! -f "$env_file" ]]; then
    cp "$env_example" "$env_file"
  fi

  if grep -q '^LLM_BASE_URL=' "$env_file"; then
    sed -i.bak "s|^LLM_BASE_URL=.*|LLM_BASE_URL=http://localhost:$LLM_PORT/v1|" "$env_file"
  else
    echo "LLM_BASE_URL=http://localhost:$LLM_PORT/v1" >> "$env_file"
  fi
  rm -f "$env_file.bak"
}

upsert_env_var() {
  local file="$1"
  local name="$2"
  local value="$3"
  if grep -q "^${name}=" "$file"; then
    sed -i.bak "s|^${name}=.*|${name}=${value}|" "$file"
  else
    echo "${name}=${value}" >> "$file"
  fi
  rm -f "$file.bak"
}

set_runtime_state() {
  local mode="$1"
  local env_file="$ROOT_DIR/backend/.env"
  local state_file="$ROOT_DIR/backend/runtime_state.json"

  local local_model api_model api_base_url llm_base_url api_key llm_key
  local_model="$(grep -E '^LOCAL_MODEL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  api_model="$(grep -E '^API_MODEL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  api_base_url="$(grep -E '^API_BASE_URL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  llm_base_url="$(grep -E '^LLM_BASE_URL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  api_key="$(grep -E '^LLAMA_API_KEY=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  llm_key="$(grep -E '^LLM_API_KEY=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"

  [[ -z "$local_model" ]] && local_model="llama3.3:70b-instruct-q4_K_M"
  [[ -z "$api_model" ]] && api_model="qwen2.5:7b-instruct"
  [[ -z "$api_base_url" ]] && api_base_url="http://localhost:$LLM_PORT/v1"
  [[ -z "$llm_base_url" ]] && llm_base_url="http://localhost:$LLM_PORT/v1"

  if [[ "$mode" == "api" ]]; then
    cat > "$state_file" <<JSON
{
  "runtime": "api",
  "base_url": "$api_base_url",
  "model": "$api_model",
  "api_key": "$api_key"
}
JSON
  else
    [[ -z "$llm_key" ]] && llm_key="not-needed"
    cat > "$state_file" <<JSON
{
  "runtime": "local",
  "base_url": "$llm_base_url",
  "model": "$local_model",
  "api_key": "$llm_key"
}
JSON
  fi
}

step "Selecting runtime"
selected_runtime="$(resolve_runtime_mode)"
echo "Selected runtime: $selected_runtime"
warn_root_venv_conflict
step "Checking Ollama"
OLLAMA_BIN_PATH="$(ensure_ollama)"

if [[ "$selected_runtime" == "local" ]]; then
  ensure_ollama_running "$LLM_PORT" "$OLLAMA_BIN_PATH"
else
  step "API runtime selected - using local Ollama gateway with API model"
fi

step "Installing backend (python + deps)"
ensure_python
ensure_backend_env
upsert_env_var "$ROOT_DIR/backend/.env" "OLLAMA_BIN" "$OLLAMA_BIN_PATH"
set_runtime_state "$selected_runtime"
cd "$ROOT_DIR/backend"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

step "Running backend"
require_port_free "$BACKEND_PORT" "backend"
nohup ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" >/tmp/agent-backend.log 2>&1 &

step "Installing frontend (node + deps)"
ensure_node
cd "$ROOT_DIR/frontend"
npm install

step "Building frontend"
npm run build

step "Running frontend"
require_port_free "$FRONTEND_PORT" "frontend"
npm start -- --port "$FRONTEND_PORT"
