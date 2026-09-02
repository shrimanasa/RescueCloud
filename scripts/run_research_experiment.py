from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg2
from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"
RESULTS_DIR = PROJECT_DIR / "results"

RESULTS_DIR.mkdir(exist_ok=True)

load_dotenv(PROJECT_DIR / ".env")


def run(command: list[str]) -> float:
    start = time.perf_counter()

    subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=True,
    )

    return time.perf_counter() - start


def database_connection(port: int = 5432):
    database_name = (
        os.environ["POSTGRES_DB"]
        if port == 5432
        else "rescuecloud_recovered"
    )

    return psycopg2.connect(
        host="127.0.0.1",
        port=port,
        database=database_name,
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def remove_attack_marker() -> None:
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
                    "Controlled RescueCloud research experiment.",
                ),
            )


def detect_mock_attack() -> tuple[dict, float, datetime]:
    events = [
        {
            "role": "doctor",
            "action": "view_record",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": 10,
            "records_accessed": 4,
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 0,
            "session_duration_min": 18,
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        },
        {
            "role": "nurse",
            "action": "update_record",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": 14,
            "records_accessed": 6,
            "records_modified": 2,
            "records_deleted": 0,
            "export_size_mb": 0,
            "session_duration_min": 22,
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        },
        {
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
        },
    ]

    total_latency = 0.0

    for index, payload in enumerate(events, start=1):
        event_time = datetime.now().astimezone().replace(
            microsecond=0
        )

        request = Request(
            "http://127.0.0.1:8001/anomaly/predict",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.perf_counter()

        with urlopen(request, timeout=60) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        latency = time.perf_counter() - start
        total_latency += latency

        print(
            "Audit event",
            index,
            ":",
            result["prediction"],
            "| score:",
            result["decision_score"],
        )

        if result["is_anomaly"]:
            return result, total_latency, event_time

        time.sleep(1)

    raise RuntimeError(
        "No anomaly was detected in the audit-event sequence."
    )


def latest_backup() -> Path:
    return max(
        BACKUP_DIR.glob("rescuecloud_*.sql"),
        key=lambda file: file.stat().st_mtime,
    )


def backup_timestamp(backup_file: Path) -> datetime:
    value = backup_file.stem.removeprefix(
        "rescuecloud_"
    )

    parsed = datetime.strptime(
        value,
        "%Y-%m-%d_%H-%M-%S",
    )

    return parsed.replace(
        tzinfo=datetime.now().astimezone().tzinfo
    )


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def blockchain_contract(web3: Web3):
    artifact_path = (
        PROJECT_DIR
        / "blockchain"
        / "artifacts"
        / "contracts"
        / "BackupLedger.sol"
        / "BackupLedger.json"
    )

    artifact = json.loads(
        artifact_path.read_text(encoding="utf-8")
    )

    return web3.eth.contract(
        address=Web3.to_checksum_address(
            os.environ["BACKUP_LEDGER_ADDRESS"]
        ),
        abi=artifact["abi"],
    )


def verify_blockchain_hash(
    contract,
    backup_file: Path,
) -> tuple[bool, float]:
    local_hash = calculate_sha256(backup_file)

    start = time.perf_counter()

    verified = contract.functions.verifyBackupHash(
        backup_file.name,
        local_hash,
    ).call()

    elapsed = time.perf_counter() - start

    return verified, elapsed


def verify_recovery() -> tuple[int, int, bool]:
    with database_connection(port=5433) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regclass(
                    'public.mock_attack_marker'
                );
                """
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

    return patients, conditions, marker_exists


def save_metrics(metrics: dict) -> None:
    csv_path = RESULTS_DIR / "research_metrics.csv"

    write_header = not csv_path.exists()

    with csv_path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(metrics.keys()),
        )

        if write_header:
            writer.writeheader()

        writer.writerow(metrics)

    json_path = RESULTS_DIR / (
        f"experiment_{metrics['run_id']}.json"
    )

    json_path.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    print("\nMetrics CSV:", csv_path)
    print("Experiment JSON:", json_path)



def save_incident(
    metrics: dict,
    blockchain_transaction_hash: str | None = None,
) -> None:
    connection = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )

    recovery_success = bool(
        metrics["recovery_success"]
    )

    try:
        with connection.cursor() as cursor:
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
                    blockchain_transaction_hash,
                    recovered_patients,
                    recovered_conditions,
                    attack_marker_absent,
                    recovery_success,
                    recovery_status
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s
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
                    blockchain_transaction_hash =
                        EXCLUDED.blockchain_transaction_hash,
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
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (
                    metrics["run_id"],
                    "controlled_mass_data_export",
                    metrics["prediction"],
                    float(metrics["decision_score"]),
                    metrics["compromise_time"],
                    metrics["compromise_time"],
                    metrics["rejected_backup"],
                    metrics["clean_backup"],
                    float(
                        metrics[
                            "detection_latency_seconds"
                        ]
                    ),
                    float(
                        metrics[
                            "backup_selection_seconds"
                        ]
                    ),
                    float(
                        metrics[
                            "hash_verification_seconds"
                        ]
                    ),
                    float(metrics["restore_seconds"]),
                    float(metrics["rpo_seconds"]),
                    float(metrics["rto_seconds"]),
                    blockchain_transaction_hash,
                    int(metrics["recovered_patients"]),
                    int(metrics["recovered_conditions"]),
                    bool(metrics["attack_marker_absent"]),
                    recovery_success,
                    (
                        "restored"
                        if recovery_success
                        else "failed"
                    ),
                ),
            )

        connection.commit()

    finally:
        connection.close()

    print("Incident saved to security_incidents.")


def read_recovery_transaction_hash() -> str | None:
    transaction_file = (
        RESULTS_DIR / "last_recovery_transaction.json"
    )

    if not transaction_file.exists():
        return None

    data = json.loads(
        transaction_file.read_text(encoding="utf-8")
    )

    value = data.get("transaction_hash")
    return str(value) if value else None

web3 = Web3(
    Web3.HTTPProvider(
        os.environ["BLOCKCHAIN_RPC_URL"]
    )
)

if not web3.is_connected():
    raise RuntimeError(
        "Hardhat blockchain is not running."
    )

contract = blockchain_contract(web3)

run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

print("\nCleaning previous attack marker...")
remove_attack_marker()

print("\n1. Creating clean pre-attack backup...")
run(["bash", "scripts/backup.sh"])
clean_backup = latest_backup()

time.sleep(2)

recovery_start = time.perf_counter()

print("\n2. Analysing audit-event sequence...")
prediction, detection_latency, compromise_time = (
    detect_mock_attack()
)

print(
    "Automatically estimated compromise time:",
    compromise_time.isoformat(),
)

print("Prediction:", prediction["prediction"])
print("Decision score:", prediction["decision_score"])
print(
    "Detection latency:",
    round(detection_latency, 4),
    "seconds",
)

if not prediction["is_anomaly"]:
    raise RuntimeError(
        "Isolation Forest did not detect the attack."
    )

print("\n3. Adding controlled compromise marker...")
create_attack_marker(compromise_time)

time.sleep(2)

print("\n4. Creating post-attack backup...")
run(["bash", "scripts/backup.sh"])
post_attack_backup = latest_backup()

print("\n5. Selecting latest clean backup...")
selection_time = run([
    "python3",
    "blockchain/select_clean_backup.py",
    compromise_time.isoformat(),
])

print(
    "Selection time:",
    round(selection_time, 4),
    "seconds",
)

print("\n6. Verifying clean backup against blockchain...")
hash_verified, hash_verification_time = (
    verify_blockchain_hash(
        contract,
        clean_backup,
    )
)

print("Blockchain hash verified:", hash_verified)
print(
    "Hash-verification time:",
    round(hash_verification_time, 4),
    "seconds",
)

if not hash_verified:
    raise RuntimeError(
        "Blockchain hash verification failed."
    )

print("\n7. Restoring selected clean backup...")
restore_time = run([
    "python3",
    "blockchain/recover_selected_backup.py",
])

recovery_transaction_hash = read_recovery_transaction_hash()

rto = time.perf_counter() - recovery_start

print("\n8. Validating recovered database...")
patients, conditions, marker_exists = (
    verify_recovery()
)

recovery_success = (
    patients == 1108
    and conditions == 37724
    and not marker_exists
)

rpo = (
    compromise_time
    - backup_timestamp(clean_backup)
).total_seconds()

metrics = {
    "run_id": run_id,
    "compromise_time": compromise_time.isoformat(),
    "clean_backup": clean_backup.name,
    "rejected_backup": post_attack_backup.name,
    "prediction": prediction["prediction"],
    "decision_score": prediction["decision_score"],
    "detection_latency_seconds": round(
        detection_latency,
        6,
    ),
    "backup_selection_seconds": round(
        selection_time,
        6,
    ),
    "hash_verification_seconds": round(
        hash_verification_time,
        6,
    ),
    "restore_seconds": round(
        restore_time,
        6,
    ),
    "rpo_seconds": round(rpo, 3),
    "rto_seconds": round(rto, 3),
    "recovered_patients": patients,
    "recovered_conditions": conditions,
    "attack_marker_absent": not marker_exists,
    "recovery_success": recovery_success,
}

remove_attack_marker()
save_metrics(metrics)
save_incident(metrics, recovery_transaction_hash)

print("\n========== EXPERIMENT RESULTS ==========")

for key, value in metrics.items():
    print(f"{key}: {value}")

print("========================================")

if not recovery_success:
    raise RuntimeError(
        "Recovery validation failed."
    )

print("\nRESEARCH EXPERIMENT COMPLETED SUCCESSFULLY")
