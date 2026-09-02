#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/backups"
RECOVERY_DB_NAME="rescuecloud_recovered"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

LATEST_BACKUP="$(ls -t "$BACKUP_DIR"/rescuecloud_*.sql 2>/dev/null | head -n 1 || true)"

if [[ -z "$LATEST_BACKUP" ]]; then
  echo "ERROR: No backup file found."
  exit 1
fi

HASH_FILE="${LATEST_BACKUP}.sha256"

if [[ ! -f "$HASH_FILE" ]]; then
  echo "ERROR: SHA-256 file not found."
  exit 1
fi

echo "Verifying backup..."
shasum -a 256 -c "$HASH_FILE"
echo "STATUS: Backup is clean and safe."

echo "Removing previous recovery environment..."
docker rm -f rescuecloud-recovery-backend >/dev/null 2>&1 || true
docker rm -f rescuecloud-recovery-db >/dev/null 2>&1 || true

docker network inspect rescuecloud-network >/dev/null 2>&1 || \
  docker network create rescuecloud-network >/dev/null

echo "Creating a fresh recovery database..."

docker run \
  --name rescuecloud-recovery-db \
  --network rescuecloud-network \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB="$RECOVERY_DB_NAME" \
  -p 5433:5432 \
  -d postgres:16 >/dev/null

echo "Waiting for PostgreSQL..."

until docker exec rescuecloud-recovery-db \
  pg_isready -U "$POSTGRES_USER" -d "$RECOVERY_DB_NAME" >/dev/null 2>&1
do
  sleep 2
done

echo "Restoring: $LATEST_BACKUP"

docker exec -i rescuecloud-recovery-db \
  psql \
  -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$RECOVERY_DB_NAME" \
  < "$LATEST_BACKUP" >/dev/null

echo "Recovery completed."

docker exec rescuecloud-recovery-db \
  psql -U "$POSTGRES_USER" -d "$RECOVERY_DB_NAME" \
  -c "SELECT
        (SELECT COUNT(*) FROM synthea_patients) AS restored_patients,
        (SELECT COUNT(*) FROM synthea_conditions) AS restored_conditions;"

echo "Building the recovery backend..."

docker build \
  -t rescuecloud-backend \
  "$PROJECT_DIR/backend" >/dev/null

docker run -d \
  --name rescuecloud-recovery-backend \
  --network rescuecloud-network \
  -p 8002:8000 \
  -e DB_HOST=rescuecloud-recovery-db \
  -e DB_PORT=5432 \
  -e DB_NAME="$RECOVERY_DB_NAME" \
  -e DB_USER="$POSTGRES_USER" \
  -e DB_PASSWORD="$POSTGRES_PASSWORD" \
  rescuecloud-backend >/dev/null

echo "Waiting for recovery API..."

for attempt in {1..30}
do
  if curl -fsS http://127.0.0.1:8002/health >/dev/null 2>&1; then
    echo "Recovery API is healthy."
    echo "Recovery API: http://127.0.0.1:8002/patients"
    exit 0
  fi

  sleep 2
done

echo "ERROR: Recovery API did not start."
docker logs rescuecloud-recovery-backend
exit 1
