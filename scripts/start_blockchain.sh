#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="$PROJECT_DIR/blockchain/state"
STATE_FILE="$STATE_DIR/anvil-state.json"
LOG_FILE="$STATE_DIR/anvil.log"
PID_FILE="$STATE_DIR/anvil.pid"
RPC_URL="http://127.0.0.1:8545"

mkdir -p "$STATE_DIR"

if curl -s \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
  "$RPC_URL" >/dev/null 2>&1; then
    echo "Blockchain is already running."
    python3 "$PROJECT_DIR/blockchain/read_ledger.py"
    exit 0
fi

if ! command -v anvil >/dev/null 2>&1; then
    echo "ERROR: Anvil is not installed or not available in PATH."
    echo "Run: source ~/.zshenv"
    exit 1
fi

echo "Starting persistent RescueCloud blockchain..."

if [[ -f "$STATE_FILE" ]]; then
    nohup anvil \
      --host 0.0.0.0 \
      --port 8545 \
      --chain-id 31337 \
      --state "$STATE_FILE" \
      > "$LOG_FILE" 2>&1 &
else
    nohup anvil \
      --host 0.0.0.0 \
      --port 8545 \
      --chain-id 31337 \
      --dump-state "$STATE_FILE" \
      > "$LOG_FILE" 2>&1 &
fi

echo $! > "$PID_FILE"

for _ in {1..15}; do
    if curl -s \
      -X POST \
      -H "Content-Type: application/json" \
      --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
      "$RPC_URL" >/dev/null 2>&1; then
        echo "Blockchain started successfully."
        python3 "$PROJECT_DIR/blockchain/read_ledger.py"
        exit 0
    fi

    sleep 1
done

echo "ERROR: Blockchain did not start."
echo "Check: $LOG_FILE"
exit 1
