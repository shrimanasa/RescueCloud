from __future__ import annotations

import csv
import os
import subprocess
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
METRICS_FILE = PROJECT_DIR / "results/research_metrics.csv"
OUTPUT_FILE = PROJECT_DIR / "results/baseline_batch.csv"

CONTAINER = "rescuecloud-baseline-db"
DATABASE = "rescuecloud_baseline"
PORT = 5434

load_dotenv(PROJECT_DIR / ".env")


def remove_container() -> None:
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_database() -> None:
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "--network",
            "rescuecloud-network",
            "-p",
            f"{PORT}:5432",
            "-e",
            f"POSTGRES_USER={os.environ['POSTGRES_USER']}",
            "-e",
            f"POSTGRES_PASSWORD={os.environ['POSTGRES_PASSWORD']}",
            "-e",
            f"POSTGRES_DB={DATABASE}",
            "postgres:16",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    for _ in range(30):
        ready = subprocess.run(
            [
                "docker",
                "exec",
                CONTAINER,
                "pg_isready",
                "-U",
                os.environ["POSTGRES_USER"],
                "-d",
                DATABASE,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if ready.returncode == 0:
            return

        time.sleep(1)

    raise RuntimeError("Baseline database did not start.")


def restore_backup(backup_file: Path) -> float:
    start = time.perf_counter()

    with backup_file.open("rb") as sql_file:
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                os.environ["POSTGRES_USER"],
                "-d",
                DATABASE,
            ],
            stdin=sql_file,
            check=True,
            stdout=subprocess.DEVNULL,
        )

    return time.perf_counter() - start


def validate_database() -> tuple[int, int, bool]:
    connection = psycopg2.connect(
        host="127.0.0.1",
        port=PORT,
        database=DATABASE,
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM synthea_patients;"
            )
            patients = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM synthea_conditions;"
            )
            conditions = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT to_regclass(
                    'public.mock_attack_marker'
                );
                """
            )
            marker_exists = cursor.fetchone()[0] is not None

    finally:
        connection.close()

    return patients, conditions, marker_exists


with METRICS_FILE.open(
    newline="",
    encoding="utf-8",
) as file:
    experiments = list(csv.DictReader(file))

results = []

for index, experiment in enumerate(experiments, start=1):
    backup_name = experiment["rejected_backup"]
    backup_file = PROJECT_DIR / "backups" / backup_name

    print(
        f"\nBaseline experiment {index}/{len(experiments)}"
    )
    print("Backup:", backup_name)

    if not backup_file.exists():
        print("Skipped: backup file not found.")
        continue

    remove_container()
    start_database()

    restore_seconds = restore_backup(backup_file)
    patients, conditions, marker_exists = validate_database()

    clean_recovery = not marker_exists

    result = {
        "run_id": experiment["run_id"],
        "strategy": "latest_backup",
        "selected_backup": backup_name,
        "restore_only_seconds": round(
            restore_seconds,
            6,
        ),
        "recovered_patients": patients,
        "recovered_conditions": conditions,
        "attack_marker_exists": marker_exists,
        "clean_recovery": clean_recovery,
    }

    results.append(result)

    print("Restore time:", round(restore_seconds, 4))
    print("Attack marker exists:", marker_exists)
    print("Clean recovery:", clean_recovery)

remove_container()

if not results:
    raise RuntimeError("No baseline experiments completed.")

with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=results[0].keys(),
    )
    writer.writeheader()
    writer.writerows(results)

clean_count = sum(
    result["clean_recovery"]
    for result in results
)

clean_rate = clean_count / len(results) * 100

print("\n========== BASELINE SUMMARY ==========")
print("Experiments:", len(results))
print("Clean recoveries:", clean_count)
print("Clean recovery rate:", round(clean_rate, 2), "%")
print("Results:", OUTPUT_FILE)
print("======================================")
