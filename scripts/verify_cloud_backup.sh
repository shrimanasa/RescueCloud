#!/bin/bash
set -euo pipefail

DOWNLOAD_DIR="$HOME/RescueCloud/recovery-download"

LATEST=$(find "$DOWNLOAD_DIR" \
  -type f \
  -name 'rescuecloud_[0-9]*.sql' |
  sort |
  tail -n 1)

if [ -z "$LATEST" ]; then
  echo "ERROR: No downloaded cloud backup found."
  exit 1
fi

HASH_FILE="$LATEST.sha256"

if [ ! -f "$HASH_FILE" ]; then
  echo "ERROR: Matching SHA-256 file not found."
  exit 1
fi

EXPECTED_LINE=$(cat "$HASH_FILE")
EXPECTED_HASH=${EXPECTED_LINE%% *}

ACTUAL_LINE=$(shasum -a 256 "$LATEST")
ACTUAL_HASH=${ACTUAL_LINE%% *}

if [ "$EXPECTED_HASH" = "$ACTUAL_HASH" ]; then
  echo "STATUS: Cloud backup is clean and verified."
  echo "Backup: $(basename "$LATEST")"
else
  echo "STATUS: Cloud backup is corrupted or modified."
  exit 1
fi
