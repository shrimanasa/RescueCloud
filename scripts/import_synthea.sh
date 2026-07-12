#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
PATIENTS_FILE="$PROJECT_DIR/data/synthea/csv/patients.csv"
CONDITIONS_FILE="$PROJECT_DIR/data/synthea/csv/conditions.csv"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found."
  exit 1
fi

if [[ ! -f "$PATIENTS_FILE" || ! -f "$CONDITIONS_FILE" ]]; then
  echo "ERROR: Synthea CSV files were not found."
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

echo "Copying Synthea files into PostgreSQL container..."

docker cp "$PATIENTS_FILE" rescuecloud-db:/tmp/patients.csv
docker cp "$CONDITIONS_FILE" rescuecloud-db:/tmp/conditions.csv

echo "Importing Synthea dataset..."

docker exec -i rescuecloud-db \
  psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" <<'SQL'

TRUNCATE TABLE synthea_conditions RESTART IDENTITY;
TRUNCATE TABLE synthea_patients CASCADE;

COPY synthea_patients (
    id,
    birthdate,
    deathdate,
    ssn,
    drivers,
    passport,
    prefix,
    first_name,
    middle_name,
    last_name,
    suffix,
    maiden,
    marital,
    race,
    ethnicity,
    gender,
    birthplace,
    address,
    city,
    state,
    county,
    fips,
    zip,
    latitude,
    longitude,
    healthcare_expenses,
    healthcare_coverage,
    income
)
FROM '/tmp/patients.csv'
WITH (FORMAT csv, HEADER true);

COPY synthea_conditions (
    start_date,
    stop_date,
    patient_id,
    encounter_id,
    system,
    code,
    description
)
FROM '/tmp/conditions.csv'
WITH (FORMAT csv, HEADER true);

SELECT
    (SELECT COUNT(*) FROM synthea_patients) AS total_patients,
    (SELECT COUNT(*) FROM synthea_conditions) AS total_conditions;

SQL

echo "Synthea import completed."
