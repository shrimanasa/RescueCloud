from __future__ import annotations

import csv
import os
import subprocess
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
RESULTS_FILE = PROJECT_DIR / "results/research_metrics.csv"
OUTPUT_FILE = PROJECT_DIR / "results/baseline_latest_backup.csv"

CONTAINER_NAME = "rescuecloud-baseline-db"
DATABASE_NAME = "rescuecloud_baseline"
DATABASE_PORT = 5434

load_dotenv(PROJECT_DIR / ".env")


with RESULTS_FILE.open(newline="", encoding="utf-8") as file:
    experiments = list(csv.DictReader(file))

if not experiments:
    raise RuntimeError("No research experiment results were found.")

latest_experiment = experiments[-1]
backup_name = latest_experiment["rejected_backup"]
backup_file = PROJECT_DIR / "backups" / backup_name

if not backup_file.exists():
    raise FileNotFoundError(
        f"Post-attack backup not found: {backup_file}"
    )

print("Baseline strategy: Restore newest available backup")
print("Selected backup:", backup_name)

subprocess.run(
    ["docker", "rm", "-f", CONTAINER_NAME],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

subprocess.run(
    [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        "--network",
        "rescuecloud-network",
        "-p",
        f"{DATABASE_PORT}:5432",
        "-e",
        f"POSTGRES_USER={os.environ['POSTGRES_USER']}",
        "-e",
        f"POSTGRES_PASSWORD={os.environ['POSTGRES_PASSWORD']}",
        "-e",
        f"POSTGRES_DB={DATABASE_NAME}",
        "postgres:16",
    ],
    check=True,
    stdout=subprocess.DEVNULL,
)

print("Waiting for baseline database...")

for _ in range(30):
    ready = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER_NAME,
            "pg_isready",
            "-U",
            os.environ["POSTGRES_USER"],
            "-d",
            DATABASE_NAME,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if ready.returncode == 0:
        break

    time.sleep(2)
else:
    raise RuntimeError("Baseline database did not start.")

print("Restoring newest post-attack backup...")

start = time.perf_counter()

with backup_file.open("rb") as sql_file:
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER_NAME,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            os.environ["POSTGRES_USER"],
            "-d",
            DATABASE_NAME,
        ],
        stdin=sql_file,
        check=True,
        stdout=subprocess.DEVNULL,
    )

restore_seconds = time.perf_counter() - start

connection = psycopg2.connect(
    host="127.0.0.1",
    port=DATABASE_PORT,
    database=DATABASE_NAME,
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_regclass('public.mock_attack_marker');"
        )
        marker_exists = cursor.fetchone()[0] is not None

        cursor.execute(
            "SELECT COUNT(*) FROM synthea_patients;"
        )
        patients = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM synthea_conditions;"
        )
        conditions = cursor.fetchone()[0]

finally:
    connection.close()

clean_recovery = not marker_exists

result = {
    "run_id": latest_experiment["run_id"],
    "strategy": "latest_backup_baseline",
    "selected_backup": backup_name,
    "restore_seconds": round(restore_seconds, 6),
    "recovered_patients": patients,
    "recovered_conditions": conditions,
    "attack_marker_exists": marker_exists,
    "clean_recovery": clean_recovery,
}

write_header = not OUTPUT_FILE.exists()

with OUTPUT_FILE.open(
    "a",
    newline="",
    encoding="utf-8",
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=result.keys(),
    )

    if write_header:
        writer.writeheader()

    writer.writerow(result)

print()
print("Recovered patients:", patients)
print("Recovered conditions:", conditions)
print("Attack marker exists:", marker_exists)
print("Clean recovery:", clean_recovery)
print("Restore time:", round(restore_seconds, 4), "seconds")
print("Results saved:", OUTPUT_FILE)

if marker_exists:
    print(
        "\nBASELINE FAILED: The newest backup retained "
        "the compromise marker."
    )
    print(
        "RESCUECLOUD ADVANTAGE: It selected the latest "
        "verified pre-attack backup."
    )
