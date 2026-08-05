#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
DOWNLOAD_DIR="$PROJECT_DIR/recovery-download"
RECOVERY_DB_NAME="rescuecloud_recovered"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

echo "Downloading backups from cloud storage..."
bash "$PROJECT_DIR/scripts/download_latest.sh"

LATEST="$(ls "$DOWNLOAD_DIR"/rescuecloud_*.sql 2>/dev/null | sort | tail -n 1)"

if [[ -z "${LATEST:-}" ]]; then
  echo "ERROR: No downloaded backup found."
  exit 1
fi

HASH_FILE="${LATEST}.sha256"

if [[ ! -f "$HASH_FILE" ]]; then
  echo "ERROR: Checksum file not found."
  exit 1
fi

echo "Verifying downloaded backup..."

EXPECTED_HASH="$(awk '{print $1}' "$HASH_FILE")"
ACTUAL_HASH="$(shasum -a 256 "$LATEST" | awk '{print $1}')"

if [[ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]]; then
  echo "ERROR: Backup verification failed."
  exit 1
fi

echo "STATUS: Cloud backup is clean and safe."

docker rm -f rescuecloud-recovery-backend >/dev/null 2>&1 || true
docker rm -f rescuecloud-recovery-db >/dev/null 2>&1 || true

docker network inspect rescuecloud-network >/dev/null 2>&1 || \
  docker network create rescuecloud-network >/dev/null

echo "Creating fresh recovery database..."

docker run -d \
  --name rescuecloud-recovery-db \
  --network rescuecloud-network \
  -p 5433:5432 \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB="$RECOVERY_DB_NAME" \
  postgres:16 >/dev/null

echo "Waiting for recovery database..."

until docker exec rescuecloud-recovery-db \
  pg_isready -U "$POSTGRES_USER" -d "$RECOVERY_DB_NAME" >/dev/null 2>&1
do
  sleep 2
done

echo "Restoring verified cloud backup..."

docker exec -i rescuecloud-recovery-db \
  psql \
  -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$RECOVERY_DB_NAME" \
  < "$LATEST" >/dev/null

echo "Cloud recovery completed successfully."

docker exec rescuecloud-recovery-db \
  psql -U "$POSTGRES_USER" -d "$RECOVERY_DB_NAME" \
  -c "SELECT
        (SELECT COUNT(*) FROM synthea_patients) AS restored_patients,
        (SELECT COUNT(*) FROM synthea_conditions) AS restored_conditions;"

echo "Starting recovery backend..."

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
exit 1
