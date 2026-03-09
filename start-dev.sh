#!/usr/bin/env bash
set -euo pipefail

LLM_PORT="${LLM_PORT:-11434}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-4200}"
RUNTIME_MODE="${RUNTIME_MODE:-}"
API_MODEL_CHOICE="${API_MODEL_CHOICE:-${API_MODEL:-}}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLEANUP_SCRIPT="$ROOT_DIR/clean-dev.sh"
if [[ -f "$CLEANUP_SCRIPT" ]]; then
  echo
  echo "==> Cleaning stale dev processes"
  LLM_PORT="$LLM_PORT" BACKEND_PORT="$BACKEND_PORT" FRONTEND_PORT="$FRONTEND_PORT" INCLUDE_LLM=0 bash "$CLEANUP_SCRIPT"
fi

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
  echo "2) api (cloud model selection)"
  read -r -p "Enter 1 or 2: " choice
  if [[ "$choice" == "2" ]]; then
    echo "api"
  else
    echo "local"
  fi
}

is_supported_api_model() {
  local model="$1"
  [[ "$model" == "minimax-m2:cloud" || "$model" == "gpt-oss:20b-cloud" || "$model" == "qwen3-coder:480b-cloud" ]]
}

resolve_api_model() {
  local current_model="$1"

  if [[ -n "$API_MODEL_CHOICE" ]]; then
    if is_supported_api_model "$API_MODEL_CHOICE"; then
      echo "$API_MODEL_CHOICE"
      return
    fi
    echo "Unsupported API_MODEL_CHOICE/API_MODEL value: $API_MODEL_CHOICE" >&2
    echo "Supported values: minimax-m2:cloud, gpt-oss:20b-cloud, qwen3-coder:480b-cloud" >&2
    exit 1
  fi

  local default_model="minimax-m2:cloud"
  if is_supported_api_model "$current_model"; then
    default_model="$current_model"
  fi

  echo "Select API model:" >&2
  echo "1) minimax-m2:cloud (small - very low cost)" >&2
  echo "2) gpt-oss:20b-cloud (mid - mid cost)" >&2
  echo "3) qwen3-coder:480b-cloud (high - high cost)" >&2
  echo "Press Enter for default: $default_model" >&2

  local choice
  read -r -p "Enter 1, 2 or 3: " choice
  case "$choice" in
    1)
      echo "minimax-m2:cloud"
      ;;
    2)
      echo "gpt-oss:20b-cloud"
      ;;
    3)
      echo "qwen3-coder:480b-cloud"
      ;;
    "")
      echo "$default_model"
      ;;
    *)
      echo "Invalid choice. Using default: $default_model" >&2
      echo "$default_model"
      ;;
  esac
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

ensure_cloud_login() {
  local ollama_bin="$1"
  local model="$2"

  if [[ "${model,,}" != *":cloud" ]]; then
    return
  fi

  step "Checking Ollama Cloud login"
  local out rc
  out="$("$ollama_bin" whoami 2>&1)"
  rc=$?

  if [[ "$rc" -ne 0 ]]; then
    if [[ "$out" == *"unknown command"* ]]; then
      echo "Ollama version has no 'whoami'; running 'ollama signin' to ensure cloud login." >&2
      if ! "$ollama_bin" signin; then
        echo "Cloud login failed. Complete 'ollama signin' successfully and rerun start-dev." >&2
        exit 1
      fi
      return
    fi

    echo "Cloud login missing. Running 'ollama signin'..." >&2
    if ! "$ollama_bin" signin; then
      echo "Cloud login failed. Complete 'ollama signin' successfully and rerun start-dev." >&2
      exit 1
    fi
  fi
}

ensure_python() {
  if has_cmd python3.12; then
    return
  fi

  step "python3.12 not found, trying package-manager install"
  install_packages python3.12 python3.12-venv python3.12-pip || true

  if ! has_cmd python3.12; then
    echo "Python 3.12 install failed. Install Python 3.12 and rerun." >&2
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

run_pip_step() {
  local python_bin="$1"
  local step_name="$2"
  shift 2

  local attempt
  for attempt in 1 2 3; do
    echo "Pip step '$step_name' (attempt $attempt/3)"
    if "$python_bin" -m pip --disable-pip-version-check --no-input "$@"; then
      return 0
    fi

    if [[ "$attempt" != "3" ]]; then
      sleep 2
    fi
  done

  echo "Backend dependency install failed during '$step_name'." >&2
  echo "If you see 'Operation cancelled by user', rerun after checking network/proxy and Python permissions." >&2
  exit 1
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

get_env_or_default() {
  local file="$1"
  local name="$2"
  local default_value="$3"
  local value

  value="$(grep -E "^${name}=" "$file" 2>/dev/null | cut -d= -f2- || true)"
  if [[ -z "$value" ]]; then
    echo "$default_value"
    return
  fi
  echo "$value"
}

model_installed() {
  local ollama_bin="$1"
  local model="$2"
  "$ollama_bin" list 2>/dev/null | grep -Fq "$model"
}

ensure_selected_model_installed() {
  local ollama_bin="$1"
  local model="$2"
  local runtime_mode="$3"

  step "Ensuring model is installed: $model"
  if model_installed "$ollama_bin" "$model"; then
    echo "Model already installed: $model"
    return
  fi

  echo "Model not found locally. Pulling: $model"
  local pull_output
  pull_output="$($ollama_bin pull "$model" 2>&1)"
  local pull_rc=$?
  if [[ -n "$pull_output" ]]; then
    echo "$pull_output"
  fi

  if [[ "$pull_rc" -ne 0 ]]; then
    local lower
    lower="${pull_output,,}"
    if [[ "$lower" == *"file does not exist"* || "$lower" == *"not found"* ]]; then
      if [[ "$runtime_mode" == "api" ]]; then
        echo "API model '$model' is currently not available from this Ollama registry/version. You are logged in, but the model ID is not resolvable. Verify the exact cloud model name for your account and update API_MODEL." >&2
      else
        echo "Local model '$model' is not available in the configured Ollama registry. Verify model name and rerun start-dev." >&2
      fi
      exit 1
    fi

    if [[ "$runtime_mode" == "api" ]]; then
      echo "Could not install API model '$model'. Cloud login may be missing or the model may be unavailable. Check ollama signin status and model identifier, then rerun start-dev." >&2
    else
      echo "Could not install local model '$model'. Check model name/network and rerun start-dev." >&2
    fi
    exit 1
  fi
}

ensure_selected_model_runnable() {
  local port="$1"
  local model="$2"
  local runtime_mode="$3"

  step "Validating model execution: $model"
  local payload
  payload="$(printf '{"model":"%s","prompt":"ping","stream":false}' "$model")"
  if ! curl -fsS "http://127.0.0.1:$port/api/generate" \
    -H "Content-Type: application/json" \
    -X POST \
    --max-time 240 \
    -d "$payload" >/dev/null; then
    if [[ "$runtime_mode" == "api" ]]; then
      echo "API model '$model' is not runnable. Ensure you're logged in via 'ollama signin' and have an active Pro plan." >&2
    else
      echo "Local model '$model' is not runnable. Verify model availability and Ollama status." >&2
    fi
    exit 1
  fi

  echo "Model is runnable: $model"
}

set_runtime_state() {
  local mode="$1"
  local env_file="$ROOT_DIR/backend/.env"
  local state_file="$ROOT_DIR/backend/runtime_state.json"

  local local_model api_model api_base_url llm_base_url
  local_model="$(grep -E '^LOCAL_MODEL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  api_model="$(grep -E '^API_MODEL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  api_base_url="$(grep -E '^API_BASE_URL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  llm_base_url="$(grep -E '^LLM_BASE_URL=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"

  [[ -z "$local_model" ]] && local_model="llama3.3:70b-instruct-q4_K_M"
  [[ -z "$api_model" ]] && api_model="minimax-m2:cloud"
  [[ -z "$api_base_url" ]] && api_base_url="http://localhost:$LLM_PORT/api"
  [[ -z "$llm_base_url" ]] && llm_base_url="http://localhost:$LLM_PORT/v1"

  # Read feature flags from .env
  local ltm_enabled distill_enabled fj_enabled vision_enabled
  ltm_enabled="$(grep -E '^LONG_TERM_MEMORY_ENABLED=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  distill_enabled="$(grep -E '^SESSION_DISTILLATION_ENABLED=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  fj_enabled="$(grep -E '^FAILURE_JOURNAL_ENABLED=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  vision_enabled="$(grep -E '^VISION_ENABLED=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
  [[ -z "$ltm_enabled" ]] && ltm_enabled="true"
  [[ -z "$distill_enabled" ]] && distill_enabled="true"
  [[ -z "$fj_enabled" ]] && fj_enabled="true"
  [[ -z "$vision_enabled" ]] && vision_enabled="false"

  # BUG-FIX: API mode must use LLM_BASE_URL (/v1, OpenAI-compatible) so that
  # function calling is enabled.  Previously this used api_base_url (/api,
  # native Ollama) which disabled function calling.
  if [[ "$mode" == "api" ]]; then
    cat > "$state_file" <<JSON
{
  "runtime": "api",
  "base_url": "$llm_base_url",
  "model": "$api_model",
  "features": {
    "long_term_memory_enabled": $ltm_enabled,
    "session_distillation_enabled": $distill_enabled,
    "failure_journal_enabled": $fj_enabled,
    "vision_enabled": $vision_enabled
  }
}
JSON
  else
    cat > "$state_file" <<JSON
{
  "runtime": "local",
  "base_url": "$llm_base_url",
  "model": "$local_model",
  "features": {
    "long_term_memory_enabled": $ltm_enabled,
    "session_distillation_enabled": $distill_enabled,
    "failure_journal_enabled": $fj_enabled,
    "vision_enabled": $vision_enabled
  }
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
  step "API runtime selected - using local Ollama API with selected cloud model"
  ensure_ollama_running "$LLM_PORT" "$OLLAMA_BIN_PATH"
fi

step "Installing backend (python + deps)"
ensure_python
ensure_backend_env
upsert_env_var "$ROOT_DIR/backend/.env" "OLLAMA_BIN" "$OLLAMA_BIN_PATH"
if [[ "$selected_runtime" == "api" ]]; then
  existing_api_model="$(get_env_or_default "$ROOT_DIR/backend/.env" "API_MODEL" "minimax-m2:cloud")"
  selected_api_model="$(resolve_api_model "$existing_api_model")"
  upsert_env_var "$ROOT_DIR/backend/.env" "API_BASE_URL" "http://localhost:$LLM_PORT/api"
  upsert_env_var "$ROOT_DIR/backend/.env" "API_MODEL" "$selected_api_model"
fi

local_model="$(get_env_or_default "$ROOT_DIR/backend/.env" "LOCAL_MODEL" "llama3.3:70b-instruct-q4_K_M")"
api_model="$(get_env_or_default "$ROOT_DIR/backend/.env" "API_MODEL" "minimax-m2:cloud")"
if [[ "$selected_runtime" == "api" ]]; then
  selected_model="$api_model"
else
  selected_model="$local_model"
fi

if [[ "$selected_runtime" == "api" ]]; then
  ensure_cloud_login "$OLLAMA_BIN_PATH" "$selected_model"
fi
ensure_selected_model_installed "$OLLAMA_BIN_PATH" "$selected_model" "$selected_runtime"
ensure_selected_model_runnable "$LLM_PORT" "$selected_model" "$selected_runtime"

set_runtime_state "$selected_runtime"
cd "$ROOT_DIR/backend"

if [[ -x ".venv/bin/python" ]]; then
  venv_version="$(./.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$venv_version" != "3.12" ]]; then
    step "Recreating backend/.venv (found Python $venv_version, expected 3.12)"
    rm -rf .venv
  fi
fi

if [[ ! -d ".venv" ]]; then
  python3.12 -m venv .venv
fi

run_pip_step "./.venv/bin/python" "upgrade-pip" install --upgrade pip
run_pip_step "./.venv/bin/python" "install-requirements" install -r requirements.txt

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
