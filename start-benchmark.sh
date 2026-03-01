#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
LEVELS="${LEVELS:-easy,mid,hard}"
RUNS_PER_CASE="${RUNS_PER_CASE:-1}"
SCENARIO_FILE="${SCENARIO_FILE:-}"
MODEL="${MODEL:-}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"
NO_AUTO_START_BACKEND="${NO_AUTO_START_BACKEND:-0}"
NO_FAIL_ON_ERROR="${NO_FAIL_ON_ERROR:-0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
REQUIRED_PYTHON="3.12"
BACKEND_PID=""
BACKEND_STARTED_HERE=0

step() {
  echo
  echo "==> $1"
}

backend_health() {
  curl -sSf "$BASE_URL/api/runtime/status" >/dev/null 2>&1
}

cleanup() {
  if [[ "$BACKEND_STARTED_HERE" == "1" && -n "$BACKEND_PID" ]]; then
    if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
      step "Stopping backend server started by benchmark script"
      kill "$BACKEND_PID" >/dev/null 2>&1 || true
      wait "$BACKEND_PID" 2>/dev/null || true
    fi
  fi
}
trap cleanup EXIT

step "Preparing backend benchmark environment"
cd "$BACKEND_DIR"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Python 3.12 is required. Install python3.12 and rerun." >&2
  exit 1
fi

if [[ -x "$VENV_PYTHON" ]]; then
  venv_version="$($VENV_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$venv_version" != "$REQUIRED_PYTHON" ]]; then
    step "Recreating backend/.venv (found Python $venv_version, expected $REQUIRED_PYTHON)"
    rm -rf .venv
  fi
fi

if [[ ! -d ".venv" ]]; then
  python3.12 -m venv .venv
fi

if [[ "$SKIP_INSTALL" != "1" ]]; then
  step "Installing backend dependencies"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r requirements.txt
fi

if ! backend_health; then
  if [[ "$NO_AUTO_START_BACKEND" == "1" ]]; then
    echo "Backend is not reachable at $BASE_URL and auto-start is disabled." >&2
    exit 1
  fi

  host="$(python3.12 - <<'PY'
from urllib.parse import urlparse
import os
url = urlparse(os.environ['BASE_URL'])
print(url.hostname or '127.0.0.1')
PY
)"
  port="$(python3.12 - <<'PY'
from urllib.parse import urlparse
import os
url = urlparse(os.environ['BASE_URL'])
if url.port:
    print(url.port)
else:
    print(443 if url.scheme == 'https' else 80)
PY
)"

  step "Starting backend server at ${host}:${port}"
  "$VENV_PYTHON" -m uvicorn app.main:app --host "$host" --port "$port" >/tmp/agent-benchmark-backend.log 2>&1 &
  BACKEND_PID=$!
  BACKEND_STARTED_HERE=1

  deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    if backend_health; then
      break
    fi
    sleep 0.5
  done

  if ! backend_health; then
    echo "Backend did not become healthy at $BASE_URL within 30 seconds." >&2
    exit 1
  fi
fi

step "Running benchmark suite (levels=$LEVELS runsPerCase=$RUNS_PER_CASE)"
cmd=("$VENV_PYTHON" "benchmarks/run_benchmark.py" "--base-url" "$BASE_URL" "--levels" "$LEVELS" "--runs-per-case" "$RUNS_PER_CASE")

if [[ -n "$MODEL" ]]; then
  cmd+=("--model" "$MODEL")
fi

if [[ -n "$SCENARIO_FILE" ]]; then
  cmd+=("--scenario-file" "$SCENARIO_FILE")
fi

if [[ "$NO_FAIL_ON_ERROR" == "1" ]]; then
  cmd+=("--no-fail-on-error")
fi

"${cmd[@]}"
