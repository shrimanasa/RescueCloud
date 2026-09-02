from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
RESULTS_FILE = PROJECT_DIR / "results" / "research_metrics.csv"

load_dotenv(PROJECT_DIR / ".env")


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


connection = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    database=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

with RESULTS_FILE.open(newline="", encoding="utf-8") as file:
    experiments = list(csv.DictReader(file))

inserted = 0
updated = 0

try:
    with connection.cursor() as cursor:
        for experiment in experiments:
            compromise_time = datetime.fromisoformat(
                experiment["compromise_time"]
            )

            recovery_success = as_bool(
                experiment["recovery_success"]
            )

            cursor.execute(
                """
                INSERT INTO security_incidents (
                    run_id,
                    attack_type,
                    prediction,
                    anomaly_score,
                    detected_at,
                    estimated_compromise_at,
                    rejected_backup,
                    selected_backup,
                    detection_latency_seconds,
                    backup_selection_seconds,
                    hash_verification_seconds,
                    restore_seconds,
                    rpo_seconds,
                    rto_seconds,
                    recovered_patients,
                    recovered_conditions,
                    attack_marker_absent,
                    recovery_success,
                    recovery_status
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (run_id)
                DO UPDATE SET
                    prediction = EXCLUDED.prediction,
                    anomaly_score = EXCLUDED.anomaly_score,
                    rejected_backup = EXCLUDED.rejected_backup,
                    selected_backup = EXCLUDED.selected_backup,
                    detection_latency_seconds =
                        EXCLUDED.detection_latency_seconds,
                    backup_selection_seconds =
                        EXCLUDED.backup_selection_seconds,
                    hash_verification_seconds =
                        EXCLUDED.hash_verification_seconds,
                    restore_seconds = EXCLUDED.restore_seconds,
                    rpo_seconds = EXCLUDED.rpo_seconds,
                    rto_seconds = EXCLUDED.rto_seconds,
                    recovered_patients =
                        EXCLUDED.recovered_patients,
                    recovered_conditions =
                        EXCLUDED.recovered_conditions,
                    attack_marker_absent =
                        EXCLUDED.attack_marker_absent,
                    recovery_success =
                        EXCLUDED.recovery_success,
                    recovery_status =
                        EXCLUDED.recovery_status,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING xmax = 0;
                """,
                (
                    experiment["run_id"],
                    "controlled_mass_data_export",
                    experiment["prediction"],
                    float(experiment["decision_score"]),
                    compromise_time,
                    compromise_time,
                    experiment["rejected_backup"],
                    experiment["clean_backup"],
                    float(
                        experiment[
                            "detection_latency_seconds"
                        ]
                    ),
                    float(
                        experiment[
                            "backup_selection_seconds"
                        ]
                    ),
                    float(
                        experiment[
                            "hash_verification_seconds"
                        ]
                    ),
                    float(experiment["restore_seconds"]),
                    float(experiment["rpo_seconds"]),
                    float(experiment["rto_seconds"]),
                    int(experiment["recovered_patients"]),
                    int(experiment["recovered_conditions"]),
                    as_bool(
                        experiment["attack_marker_absent"]
                    ),
                    recovery_success,
                    (
                        "restored"
                        if recovery_success
                        else "failed"
                    ),
                ),
            )

            was_inserted = cursor.fetchone()[0]

            if was_inserted:
                inserted += 1
            else:
                updated += 1

    connection.commit()

finally:
    connection.close()

print("Incident history imported.")
print("Inserted:", inserted)
print("Updated:", updated)
print("Total experiments:", len(experiments))
