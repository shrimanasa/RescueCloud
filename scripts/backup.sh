#!/bin/bash
# backup.sh — RescueCloud automated backup
# Produces a pg_dump, computes SHA-256, uploads to MinIO,
# and registers metadata in the backup_ledger Postgres table.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}">/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/backups"
BUCKET_NAME="rescuecloud-backups"
TIMESTAMP="$(date -u +'%Y-%m-%d_%H-%M-%S')"
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

# -------------------------------------------------------------------
# 1. pg_dump
# -------------------------------------------------------------------
echo "[1/5] Creating PostgreSQL backup..."

docker exec rescuecloud-db \
  pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  > "$BACKUP_FILE"

# -------------------------------------------------------------------
# 2. SHA-256 checksum
# -------------------------------------------------------------------
echo "[2/5] Computing SHA-256 checksum..."

(
  cd "$BACKUP_DIR"
  shasum -a 256 "$BACKUP_NAME" > "${BACKUP_NAME}.sha256"
)

SHA256_HEX="$(awk '{print $1}' "$HASH_FILE")"
SIZE_BYTES="$(wc -c < "$BACKUP_FILE" | tr -d ' ')"

echo "  File : $BACKUP_NAME"
echo "  SHA256: $SHA256_HEX"
echo "  Size  : ${SIZE_BYTES} bytes"

# -------------------------------------------------------------------
# 3. Upload to MinIO (cloud copy)
# -------------------------------------------------------------------
echo "[3/5] Uploading to MinIO..."

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
# 4. Register in backup_ledger (Postgres metadata table)
#    This is what smart_recover.py queries via SQL:
#      WHERE created_at < :compromise_time ORDER BY created_at DESC
# -------------------------------------------------------------------
echo "[4/5] Registering backup in backup_ledger..."

STORAGE_PATH="minio://rescuecloud-backups/${BACKUP_NAME}"

docker exec rescuecloud-db psql \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -c "INSERT INTO backup_ledger (filename, sha256, size_bytes, storage_path, verified)
      VALUES ('${BACKUP_NAME}', '${SHA256_HEX}', ${SIZE_BYTES}, '${STORAGE_PATH}', TRUE);"

echo "  Registered in backup_ledger."

# -------------------------------------------------------------------
# 5. Register hash in integrity ledger (blockchain/local log)
# -------------------------------------------------------------------
echo "[5/5] Registering SHA-256 in integrity ledger..."

python3 "$PROJECT_DIR/blockchain/register_backup.py" "$BACKUP_FILE"

echo ""
echo "=== Backup complete ==="
echo "  File    : $BACKUP_FILE"
echo "  Checksum: $HASH_FILE"
echo "  SHA-256 : $SHA256_HEX"
echo "  Ledger  : backup_ledger (row inserted)"
