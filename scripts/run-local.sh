#!/usr/bin/env bash
# Start or stop the API, the web app, and the mock JIRA as local processes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUNTIME_DIR="$REPO_ROOT/.runtime"
API_PID="$RUNTIME_DIR/api.pid"
WEB_PID="$RUNTIME_DIR/web.pid"
JIRA_PID="$RUNTIME_DIR/mock-jira.pid"

stop_quietly() {
  for pid_file in "$API_PID" "$WEB_PID" "$JIRA_PID"; do
    if [[ -f "$pid_file" ]]; then
      kill "$(cat "$pid_file")" 2>/dev/null || true
      rm -f "$pid_file"
    fi
  done
  pkill -f "uvicorn qa_dashboard.main:app" 2>/dev/null || true
  pkill -f "uvicorn mock_jira:app" 2>/dev/null || true
  pkill -f "vite --host 0.0.0.0 --port 5174" 2>/dev/null || true
}

start() {
  mkdir -p "$RUNTIME_DIR"
  stop_quietly

  (
    cd apps/api
    QA_DATABASE_URL="sqlite+pysqlite:///$REPO_ROOT/qa_dashboard.db" \
    uv run uvicorn qa_dashboard.main:app --host 127.0.0.1 --port 8001 \
      >"$RUNTIME_DIR/api.log" 2>&1 &
    echo $! >"$API_PID"
  )
  (
    cd apps/web
    npm run dev >"$RUNTIME_DIR/web.log" 2>&1 &
    echo $! >"$WEB_PID"
  )
  (
    # The mock JIRA shares the API's Python environment.
    cd apps/api
    uv run uvicorn mock_jira:app --app-dir ../mock-jira --host 127.0.0.1 --port 8002 \
      >"$RUNTIME_DIR/mock-jira.log" 2>&1 &
    echo $! >"$JIRA_PID"
  )

  for _ in $(seq 1 60); do
    if curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1 \
      && curl -fsS http://127.0.0.1:8002/health >/dev/null 2>&1; then
      echo "API        http://127.0.0.1:8001   (log: .runtime/api.log)"
      echo "Web        http://127.0.0.1:5174   (log: .runtime/web.log)"
      echo "Mock JIRA  http://127.0.0.1:8002   (log: .runtime/mock-jira.log)"
      if ! (cd apps/api && uv run python ../../scripts/manage_users.py has-users) >/dev/null 2>&1; then
        echo
        echo "No accounts yet. Create one to sign in: make user-add NAME=<your-name>"
      fi
      exit 0
    fi
    sleep 1
  done
  echo "ERROR: a service did not become healthy. See .runtime/*.log" >&2
  exit 1
}

case "${1:-start}" in
  start) start ;;
  stop) stop_quietly; echo "Stopped." ;;
  *) echo "Usage: $0 [start|stop]" >&2; exit 2 ;;
esac
