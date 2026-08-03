#!/bin/bash
# base_backup.sh — RescueCloud Base Backup Generator for PITR
# Performs a full binary base backup using pg_basebackup,
# computes SHA-256, uploads to MinIO, and registers in backup_ledger.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP="$(date -u +'%Y-%m-%d_%H-%M-%S')"
BACKUP_NAME="base_${TIMESTAMP}.tar.gz"
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

# -------------------------------------------------------------------
# 1. pg_basebackup
# -------------------------------------------------------------------
echo "[1/4] Creating PostgreSQL binary base backup (PITR foundation)..."

docker exec rescuecloud-db \
  pg_basebackup \
  -U "$POSTGRES_USER" \
  -D - \
  -Ft \
  -X fetch \
  > "$BACKUP_FILE"

# -------------------------------------------------------------------
# 2. SHA-256 checksum
# -------------------------------------------------------------------
echo "[2/4] Computing SHA-256 checksum..."

(
  cd "$BACKUP_DIR"
  shasum -a 256 "$BACKUP_NAME" > "${BACKUP_NAME}.sha256"
)

SHA256_HEX="$(awk '{print $1}' "$HASH_FILE")"
SIZE_BYTES="$(wc -c < "$BACKUP_FILE" | tr -d ' ')"

echo "  File    : $BACKUP_NAME"
echo "  SHA-256 : $SHA256_HEX"
echo "  Size    : ${SIZE_BYTES} bytes"

# -------------------------------------------------------------------
# 3. Upload to MinIO
# -------------------------------------------------------------------
echo "[3/4] Uploading base backup to MinIO..."

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

# -------------------------------------------------------------------
# 4. Register in backup_ledger (Postgres)
# -------------------------------------------------------------------
echo "[4/4] Registering base backup in backup_ledger..."

STORAGE_PATH="minio://rescuecloud-backups/${BACKUP_NAME}"

docker exec rescuecloud-db psql \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "INSERT INTO backup_ledger (filename, backup_type, sha256, size_bytes, storage_path, verified, notes)
      VALUES ('${BACKUP_NAME}', 'base', '${SHA256_HEX}', ${SIZE_BYTES}, '${STORAGE_PATH}', TRUE, 'PITR Base Backup');"

echo ""
echo "=== Base Backup complete ==="
echo "  File    : $BACKUP_FILE"
echo "  SHA-256 : $SHA256_HEX"
echo "  Ledger  : base backup registered for PITR"
