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
