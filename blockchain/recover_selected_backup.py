from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

import psycopg2
from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"
RECOVERY_DB = "rescuecloud_recovered"

load_dotenv(PROJECT_DIR / ".env")


def run(command: list[str], **kwargs):
    return subprocess.run(
        command,
        check=True,
        text=True,
        **kwargs,
    )


def sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


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

web3 = Web3(
    Web3.HTTPProvider(os.environ["BLOCKCHAIN_RPC_URL"])
)

if not web3.is_connected():
    raise RuntimeError("Hardhat blockchain is not running.")

contract = web3.eth.contract(
    address=Web3.to_checksum_address(
        os.environ["BACKUP_LEDGER_ADDRESS"]
    ),
    abi=artifact["abi"],
)

selected_records = []

backup_count = contract.functions.getBackupCount().call()

for index in range(backup_count):
    name = contract.functions.getBackupNameAt(index).call()
    record = contract.functions.getBackup(name).call()

    if record[6] == 2:  # Selected
        selected_records.append(record)

if not selected_records:
    raise RuntimeError(
        "No blockchain-selected recovery point was found."
    )

selected = max(
    selected_records,
    key=lambda record: record[1],
)

backup_name = selected[0]
expected_hash = selected[2]
expected_patients = selected[3]
expected_conditions = selected[4]

backup_file = BACKUP_DIR / backup_name

if not backup_file.exists():
    raise FileNotFoundError(
        f"Selected backup file not found: {backup_file}"
    )

local_hash = sha256(backup_file)

verified = contract.functions.verifyBackupHash(
    backup_name,
    local_hash,
).call()

if not verified or local_hash != expected_hash:
    raise RuntimeError(
        "Selected backup failed blockchain hash verification."
    )

print("Blockchain-selected backup:", backup_name)
print("Hash verification: PASSED")
print("Creating fresh recovery environment...")

subprocess.run(
    ["docker", "rm", "-f", "rescuecloud-recovery-backend"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

subprocess.run(
    ["docker", "rm", "-f", "rescuecloud-recovery-db"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

network_check = subprocess.run(
    ["docker", "network", "inspect", "rescuecloud-network"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

if network_check.returncode != 0:
    run([
        "docker",
        "network",
        "create",
        "rescuecloud-network",
    ])

run([
    "docker",
    "run",
    "-d",
    "--name",
    "rescuecloud-recovery-db",
    "--network",
    "rescuecloud-network",
    "-p",
    "5433:5432",
    "-e",
    f"POSTGRES_USER={os.environ['POSTGRES_USER']}",
    "-e",
    f"POSTGRES_PASSWORD={os.environ['POSTGRES_PASSWORD']}",
    "-e",
    f"POSTGRES_DB={RECOVERY_DB}",
    "postgres:16",
], stdout=subprocess.DEVNULL)

print("Waiting for recovery database...")

for _ in range(30):
    ready = subprocess.run(
        [
            "docker",
            "exec",
            "rescuecloud-recovery-db",
            "pg_isready",
            "-U",
            os.environ["POSTGRES_USER"],
            "-d",
            RECOVERY_DB,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if ready.returncode == 0:
        break

    time.sleep(2)
else:
    raise RuntimeError("Recovery PostgreSQL did not start.")

print("Restoring selected clean backup...")

with backup_file.open("rb") as sql_file:
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "rescuecloud-recovery-db",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            os.environ["POSTGRES_USER"],
            "-d",
            RECOVERY_DB,
        ],
        stdin=sql_file,
        check=True,
        stdout=subprocess.DEVNULL,
    )

connection = psycopg2.connect(
    host="127.0.0.1",
    port=5433,
    database=RECOVERY_DB,
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)

try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM synthea_patients;"
        )
        restored_patients = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM synthea_conditions;"
        )
        restored_conditions = cursor.fetchone()[0]

finally:
    connection.close()

if restored_patients != expected_patients:
    raise RuntimeError("Recovered patient count mismatch.")

if restored_conditions != expected_conditions:
    raise RuntimeError("Recovered condition count mismatch.")

print("Recovered patients:", restored_patients)
print("Recovered conditions:", restored_conditions)

run([
    "docker",
    "build",
    "-t",
    "rescuecloud-backend",
    str(PROJECT_DIR / "backend"),
], stdout=subprocess.DEVNULL)

run([
    "docker",
    "run",
    "-d",
    "--name",
    "rescuecloud-recovery-backend",
    "--network",
    "rescuecloud-network",
    "-p",
    "8002:8000",
    "-e",
    "DB_HOST=rescuecloud-recovery-db",
    "-e",
    "DB_PORT=5432",
    "-e",
    f"DB_NAME={RECOVERY_DB}",
    "-e",
    f"DB_USER={os.environ['POSTGRES_USER']}",
    "-e",
    f"DB_PASSWORD={os.environ['POSTGRES_PASSWORD']}",
    "rescuecloud-backend",
], stdout=subprocess.DEVNULL)

print("Waiting for recovery API...")

for _ in range(30):
    try:
        with urlopen(
            "http://127.0.0.1:8002/health",
            timeout=3,
        ) as response:
            if response.status == 200:
                break
    except Exception:
        time.sleep(2)
else:
    raise RuntimeError("Recovery API did not become healthy.")

transaction = contract.functions.markBackupRestored(
    backup_name
).transact(
    {"from": web3.eth.accounts[0]}
)

receipt = web3.eth.wait_for_transaction_receipt(
    transaction
)

transaction_hash = transaction.hex()

if not transaction_hash.startswith("0x"):
    transaction_hash = "0x" + transaction_hash

results_dir = PROJECT_DIR / "results"
results_dir.mkdir(exist_ok=True)

transaction_file = (
    results_dir / "last_recovery_transaction.json"
)

transaction_file.write_text(
    json.dumps(
        {
            "backup_name": backup_name,
            "transaction_hash": transaction_hash,
            "block_number": receipt.blockNumber,
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("Recovery API: http://127.0.0.1:8002/patients")
print("Blockchain status: Restored")
print("Blockchain block:", receipt.blockNumber)
print("CLEAN RECOVERY COMPLETED SUCCESSFULLY")
