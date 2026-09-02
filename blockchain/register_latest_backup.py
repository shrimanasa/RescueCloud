from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"

load_dotenv(PROJECT_DIR / ".env")


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def backup_timestamp(backup_name: str) -> int:
    value = backup_name.removeprefix("rescuecloud_").removesuffix(".sql")

    parsed = datetime.strptime(
        value,
        "%Y-%m-%d_%H-%M-%S",
    ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

    return int(parsed.timestamp())


def get_record_counts() -> tuple[int, int]:
    connection = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM synthea_patients;")
            patient_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM synthea_conditions;")
            condition_count = cursor.fetchone()[0]

        return patient_count, condition_count

    finally:
        connection.close()


latest_backup = max(
    BACKUP_DIR.glob("rescuecloud_*.sql"),
    key=lambda path: path.stat().st_mtime,
)

artifact_path = (
    PROJECT_DIR
    / "blockchain"
    / "artifacts"
    / "contracts"
    / "BackupLedger.sol"
    / "BackupLedger.json"
)

artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

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

backup_name = latest_backup.name
timestamp = backup_timestamp(backup_name)
sha256_hash = calculate_sha256(latest_backup)
patient_count, condition_count = get_record_counts()
storage_location = f"minio://rescuecloud-backups/{backup_name}"

sender = web3.eth.accounts[0]

transaction_hash = contract.functions.registerBackup(
    backup_name,
    timestamp,
    sha256_hash,
    patient_count,
    condition_count,
    storage_location,
).transact({"from": sender})

receipt = web3.eth.wait_for_transaction_receipt(
    transaction_hash
)

print("Backup registered on blockchain.")
print("Backup:", backup_name)
print("SHA-256:", sha256_hash)
print("Patients:", patient_count)
print("Conditions:", condition_count)
print("Storage:", storage_location)
print("Block number:", receipt.blockNumber)
print("Transaction:", transaction_hash.hex())
print(
    "Registered backups:",
    contract.functions.getBackupCount().call(),
)
