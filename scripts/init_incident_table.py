from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")


connection = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    database=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS security_incidents (
                incident_id BIGSERIAL PRIMARY KEY,

                run_id VARCHAR(50) UNIQUE,

                attack_type VARCHAR(100) NOT NULL,
                prediction VARCHAR(50) NOT NULL,
                anomaly_score DOUBLE PRECISION,

                detected_at TIMESTAMPTZ NOT NULL,
                estimated_compromise_at TIMESTAMPTZ NOT NULL,

                rejected_backup TEXT,
                selected_backup TEXT,

                detection_latency_seconds DOUBLE PRECISION,
                backup_selection_seconds DOUBLE PRECISION,
                hash_verification_seconds DOUBLE PRECISION,
                restore_seconds DOUBLE PRECISION,
                rpo_seconds DOUBLE PRECISION,
                rto_seconds DOUBLE PRECISION,

                blockchain_transaction_hash TEXT,

                recovered_patients INTEGER,
                recovered_conditions INTEGER,

                attack_marker_absent BOOLEAN DEFAULT FALSE,
                recovery_success BOOLEAN DEFAULT FALSE,

                recovery_status VARCHAR(30)
                    DEFAULT 'detected'
                    CHECK (
                        recovery_status IN (
                            'detected',
                            'selecting',
                            'selected',
                            'restoring',
                            'restored',
                            'failed'
                        )
                    ),

                error_message TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_security_incidents_detected_at
            ON security_incidents (detected_at DESC);
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_security_incidents_status
            ON security_incidents (recovery_status);
            """
        )

        connection.commit()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'security_incidents';
            """
        )

        column_count = cursor.fetchone()[0]

        print("security_incidents table is ready.")
        print("Columns created:", column_count)

finally:
    connection.close()
