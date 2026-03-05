#!/usr/bin/env bash
set -euo pipefail

SKIP_INSTALL="${SKIP_INSTALL:-0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
REQUIRED_PYTHON="3.12"

step() {
  echo
  echo "==> $1"
}

step "Preparing backend test environment"
cd "$BACKEND_DIR"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Python 3.12 is required. Install python3.12 and rerun." >&2
  exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
  venv_version="$(./.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$venv_version" != "$REQUIRED_PYTHON" ]]; then
    step "Recreating backend/.venv (found Python $venv_version, expected $REQUIRED_PYTHON)"
    rm -rf .venv
  fi
fi

if [[ ! -d ".venv" ]]; then
  python3.12 -m venv .venv
fi

if [[ "$SKIP_INSTALL" != "1" ]]; then
  step "Installing backend + test dependencies"
  ./.venv/bin/python -m pip install --upgrade pip
  ./.venv/bin/python -m pip install -r requirements.txt -r requirements-test.txt
fi

step "Running backend end-to-end tests"
if [[ -n "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="$ROOT_DIR:$PYTHONPATH"
else
  export PYTHONPATH="$ROOT_DIR"
fi

OLLAMA_BIN=python ./.venv/bin/python -m pytest tests -q \
  --cov=app \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  --cov-fail-under=70

./.venv/bin/python scripts/check_coverage_thresholds.py \
  --coverage-json coverage.json \
  --global-min 70 \
  --use-default-thresholds
