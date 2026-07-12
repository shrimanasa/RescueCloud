#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/backups"
BUCKET_NAME="rescuecloud-backups"
TIMESTAMP="$(date +'%Y-%m-%d_%H-%M-%S')"
BACKUP_NAME="rescuecloud_${TIMESTAMP}.sql"
BACKUP_FILE="$BACKUP_DIR/$BACKUP_NAME"
HASH_FILE="${BACKUP_FILE}.sha256"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

mkdir -p "$BACKUP_DIR"

echo "Creating PostgreSQL backup..."

docker exec rescuecloud-db \
  pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  > "$BACKUP_FILE"

echo "Creating SHA-256 checksum..."

(
  cd "$BACKUP_DIR"
  shasum -a 256 "$BACKUP_NAME" > "${BACKUP_NAME}.sha256"
)

echo "Uploading backup to MinIO..."

docker run --rm \
  --network container:rescuecloud-minio \
  -v "$BACKUP_DIR:/backups:ro" \
  -e MC_USER="$MINIO_ROOT_USER" \
  -e MC_PASSWORD="$MINIO_ROOT_PASSWORD" \
  --entrypoint /bin/sh \
  minio/mc \
  -c '
    mc alias set local http://127.0.0.1:9000 "$MC_USER" "$MC_PASSWORD" >/dev/null
    mc mb --ignore-existing local/rescuecloud-backups >/dev/null
    mc cp "/backups/'"$BACKUP_NAME"'" local/rescuecloud-backups/
    mc cp "/backups/'"$BACKUP_NAME"'.sha256" local/rescuecloud-backups/
  '

echo "Backup created and uploaded: $BACKUP_FILE"
echo "SHA-256 created and uploaded: $HASH_FILE"
