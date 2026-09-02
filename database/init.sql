CREATE TABLE IF NOT EXISTS synthea_patients (
    id UUID PRIMARY KEY,
    birthdate DATE,
    deathdate DATE,
    ssn TEXT,
    drivers TEXT,
    passport TEXT,
    prefix TEXT,
    first_name TEXT,
    middle_name TEXT,
    last_name TEXT,
    suffix TEXT,
    maiden TEXT,
    marital TEXT,
    race TEXT,
    ethnicity TEXT,
    gender TEXT,
    birthplace TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    county TEXT,
    fips TEXT,
    zip TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    healthcare_expenses NUMERIC(14,2),
    healthcare_coverage NUMERIC(14,2),
    income NUMERIC(14,2)
);

CREATE TABLE IF NOT EXISTS synthea_conditions (
    condition_id BIGSERIAL PRIMARY KEY,
    start_date DATE,
    stop_date DATE,
    patient_id UUID REFERENCES synthea_patients(id) ON DELETE CASCADE,
    encounter_id UUID,
    system TEXT,
    code TEXT,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_conditions_patient_id
ON synthea_conditions(patient_id);

CREATE INDEX IF NOT EXISTS idx_conditions_start_date
ON synthea_conditions(start_date);

-- -----------------------------------------------------------------------
-- Backup Integrity Ledger
-- Tracks every backup produced by backup.sh.
-- smart_recover.py queries this table with:
--   WHERE created_at < :compromise_time ORDER BY created_at DESC
-- to find the best restore point without parsing filename strings.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backup_ledger (
    id            BIGSERIAL PRIMARY KEY,
    filename      TEXT        NOT NULL,
    backup_type   TEXT        NOT NULL DEFAULT 'snapshot',
    sha256        CHAR(64)    NOT NULL,
    size_bytes    BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified      BOOLEAN     NOT NULL DEFAULT TRUE,
    storage_path  TEXT,
    wal_start     TEXT,
    wal_stop      TEXT,
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_backup_ledger_created_at
ON backup_ledger(created_at DESC);
