#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$PROJECT_DIR/results/orchestrator.pid"
LOG_FILE="$PROJECT_DIR/results/orchestrator.log"

mkdir -p "$PROJECT_DIR/results"

if curl -s http://127.0.0.1:8003/health >/dev/null 2>&1; then
    echo "Recovery orchestrator is already running."
    exit 0
fi

cd "$PROJECT_DIR"

nohup python3 -m uvicorn orchestrator.demo_api:app \
  --host 0.0.0.0 \
  --port 8003 \
  > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

for _ in {1..15}; do
    if curl -s http://127.0.0.1:8003/health >/dev/null 2>&1; then
        echo "Recovery orchestrator started."
        echo "API: http://127.0.0.1:8003"
        exit 0
    fi

    sleep 1
done

echo "ERROR: Recovery orchestrator did not start."
echo "Check: $LOG_FILE"
exit 1
