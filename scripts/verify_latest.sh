#!/bin/bash

LATEST_BACKUP=$(ls -t "$HOME"/RescueCloud/backups/rescuecloud_*.sql | head -n 1)
HASH_FILE="$LATEST_BACKUP.sha256"

if [ ! -f "$HASH_FILE" ]; then
  echo "ERROR: SHA-256 file not found."
  exit 1
fi

if shasum -a 256 -c "$HASH_FILE"; then
  echo "STATUS: Backup is clean and safe."
else
  echo "STATUS: Backup is corrupted or modified."
  exit 1
fi
