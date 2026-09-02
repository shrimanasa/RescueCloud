from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg2
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")


def run(command: list[str]) -> None:
    subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=True,
    )


def database_connection(port: int = 5432):
    return psycopg2.connect(
        host="127.0.0.1",
        port=port,
        database=(
            os.environ["POSTGRES_DB"]
            if port == 5432
            else "rescuecloud_recovered"
        ),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def remove_old_marker() -> None:
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DROP TABLE IF EXISTS mock_attack_marker;"
            )


def create_attack_marker(
    compromise_time: datetime,
) -> None:
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE mock_attack_marker (
                    marker_id BIGSERIAL PRIMARY KEY,
                    compromise_time TIMESTAMPTZ NOT NULL,
                    attack_type TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                """
            )

            cursor.execute(
                """
                INSERT INTO mock_attack_marker (
                    compromise_time,
                    attack_type,
                    details
                )
                VALUES (%s, %s, %s);
                """,
                (
                    compromise_time,
                    "mass_data_export",
                    (
                        "Controlled RescueCloud mock attack. "
                        "No real patient records were deleted."
                    ),
                ),
            )


def predict_attack() -> dict:
    activity = {
        "role": "admin",
        "action": "export_data",
        "status": "success",
        "failed_logins": 12,
        "requests_per_minute": 180,
        "records_accessed": 2500,
        "records_modified": 0,
        "records_deleted": 0,
        "export_size_mb": 950,
        "session_duration_min": 15,
        "off_hours_access": 1,
        "new_ip_address": 1,
        "privilege_change": 0,
    }

    request = Request(
        "http://127.0.0.1:8001/anomaly/predict",
        data=json.dumps(activity).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_clean_recovery() -> None:
    with database_connection(port=5433) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regclass(
                    'public.mock_attack_marker'
                );
                """
            )

            marker_table = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM synthea_patients;"
            )
            patients = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM synthea_conditions;"
            )
            conditions = cursor.fetchone()[0]

    if marker_table is not None:
        raise RuntimeError(
            "Recovered database still contains the attack marker."
        )

    print("Attack marker in recovered database: NOT FOUND")
    print("Recovered patients:", patients)
    print("Recovered conditions:", conditions)


print("Cleaning previous mock-attack markers...")
remove_old_marker()

print("\n1. Creating clean pre-attack backup...")
run(["bash", "scripts/backup.sh"])

time.sleep(2)

compromise_time = datetime.now().astimezone().replace(
    microsecond=0
)

print("\n2. Simulating suspicious activity...")
prediction = predict_attack()

print("Prediction:", prediction["prediction"])
print("Decision score:", prediction["decision_score"])

if not prediction["is_anomaly"]:
    raise RuntimeError(
        "Mock attack was not detected by Isolation Forest."
    )

print("\n3. Recording controlled compromise marker...")
create_attack_marker(compromise_time)

time.sleep(2)

print("\n4. Creating post-attack backup...")
run(["bash", "scripts/backup.sh"])

print("\n5. Selecting the latest clean recovery point...")
run([
    "python3",
    "blockchain/select_clean_backup.py",
    compromise_time.isoformat(),
])

print("\n6. Restoring blockchain-selected clean backup...")
run([
    "python3",
    "blockchain/recover_selected_backup.py",
])

print("\n7. Verifying that compromise data was removed...")
verify_clean_recovery()

print("\n8. Cleaning the marker from the main demo database...")
remove_old_marker()

print("\nMOCK ATTACK AND CLEAN RECOVERY COMPLETED")
print("Compromise time:", compromise_time.isoformat())
print("Recovery API: http://127.0.0.1:8002/patients")
