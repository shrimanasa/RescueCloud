#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$PROJECT_DIR/blockchain/state/anvil.pid"
STATE_FILE="$PROJECT_DIR/blockchain/state/anvil-state.json"

if [[ ! -f "$PID_FILE" ]]; then
    echo "No blockchain PID file was found."
    exit 0
fi

PID="$(cat "$PID_FILE")"

if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping blockchain and saving state..."
    kill -INT "$PID"

    for _ in {1..15}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi

        sleep 1
    done
else
    echo "Blockchain process is not running."
fi

rm -f "$PID_FILE"

if [[ -s "$STATE_FILE" ]]; then
    echo "Blockchain state saved:"
    ls -lh "$STATE_FILE"
else
    echo "WARNING: Blockchain state file is missing or empty."
fi
