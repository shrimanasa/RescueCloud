#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
DOWNLOAD_DIR="$PROJECT_DIR/recovery-download"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

mkdir -p "$DOWNLOAD_DIR"

echo "Downloading backups from MinIO..."

docker run --rm \
  --network container:rescuecloud-minio \
  -v "$DOWNLOAD_DIR:/downloads" \
  -e MC_USER="$MINIO_ROOT_USER" \
  -e MC_PASSWORD="$MINIO_ROOT_PASSWORD" \
  --entrypoint /bin/sh \
  minio/mc \
  -c '
    mc alias set local http://127.0.0.1:9000 "$MC_USER" "$MC_PASSWORD" >/dev/null
    mc mirror --overwrite local/rescuecloud-backups /downloads
  '

LATEST="$(
  find "$DOWNLOAD_DIR" \
    -type f \
    -name 'rescuecloud_*.sql' \
    | sort \
    | tail -n 1
)"

if [[ -z "$LATEST" ]]; then
  echo "ERROR: No backup was downloaded."
  exit 1
fi

if [[ ! -f "${LATEST}.sha256" ]]; then
  echo "ERROR: Checksum for the latest backup was not downloaded."
  exit 1
fi

echo "Latest backup downloaded: $LATEST"
echo "Checksum downloaded: ${LATEST}.sha256"
