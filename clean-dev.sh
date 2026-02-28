#!/usr/bin/env bash
set -euo pipefail

LLM_PORT="${LLM_PORT:-11434}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-4200}"
INCLUDE_LLM="${INCLUDE_LLM:-0}"

step() {
  echo
  echo "==> $1"
}

port_open() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1
    return
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" | tail -n +2 | grep -q .
    return
  fi

  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    return
  fi

  timeout 1 bash -c "</dev/tcp/127.0.0.1/$port" >/dev/null 2>&1
}

pids_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$port" -sTCP:LISTEN -n -P | sort -u
    return
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :$port" | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u
    return
  fi
}

stop_port_process() {
  local port="$1"
  local service="$2"

  if ! port_open "$port"; then
    echo "No listener on port $port for $service"
    return
  fi

  local pids
  pids="$(pids_on_port "$port" || true)"
  if [[ -z "$pids" ]]; then
    echo "No killable process found on port $port for $service"
    return
  fi

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    echo "Stopping $service listener on port $port (PID=$pid)"
    kill "$pid" >/dev/null 2>&1 || true
  done <<< "$pids"

  for _ in {1..12}; do
    if ! port_open "$port"; then
      echo "$service port $port is now free"
      return
    fi
    sleep 0.25
  done

  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    kill -9 "$pid" >/dev/null 2>&1 || true
  done <<< "$pids"

  if port_open "$port"; then
    echo "Warning: Port $port may still be in use for $service" >&2
  else
    echo "$service port $port is now free"
  fi
}

step "Cleaning development ports"
stop_port_process "$BACKEND_PORT" "backend"
stop_port_process "$FRONTEND_PORT" "frontend"

if [[ "$INCLUDE_LLM" == "1" ]]; then
  stop_port_process "$LLM_PORT" "llm"
fi

echo "Cleanup complete"
