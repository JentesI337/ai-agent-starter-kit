#!/usr/bin/env bash
set -euo pipefail

SKIP_INSTALL="${SKIP_INSTALL:-0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

step() {
  echo
  echo "==> $1"
}

step "Preparing backend test environment"
cd "$BACKEND_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 not found. Install Python 3.11+ and rerun." >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

if [[ "$SKIP_INSTALL" != "1" ]]; then
  step "Installing backend + test dependencies"
  ./.venv/bin/python -m pip install --upgrade pip
  ./.venv/bin/python -m pip install -r requirements.txt -r requirements-test.txt
fi

step "Running backend end-to-end tests"
OLLAMA_BIN=python ./.venv/bin/python -m pytest tests -q
