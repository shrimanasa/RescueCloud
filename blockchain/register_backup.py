from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2
from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def extract_timestamp(backup_name: str) -> int:
    value = backup_name.removeprefix(
        "rescuecloud_"
    ).removesuffix(".sql")

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
            cursor.execute(
                "SELECT COUNT(*) FROM synthea_patients;"
            )
            patient_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM synthea_conditions;"
            )
            condition_count = cursor.fetchone()[0]

        return patient_count, condition_count

    finally:
        connection.close()


if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python3 register_backup.py <backup.sql>"
    )

backup_file = Path(sys.argv[1]).resolve()

if not backup_file.exists():
    raise FileNotFoundError(
        f"Backup not found: {backup_file}"
    )

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
    Web3.HTTPProvider(
        os.environ["BLOCKCHAIN_RPC_URL"]
    )
)

if not web3.is_connected():
    raise RuntimeError(
        "Hardhat blockchain is not running."
    )

contract = web3.eth.contract(
    address=Web3.to_checksum_address(
        os.environ["BACKUP_LEDGER_ADDRESS"]
    ),
    abi=artifact["abi"],
)

backup_name = backup_file.name

registered_names = [
    contract.functions.getBackupNameAt(index).call()
    for index in range(
        contract.functions.getBackupCount().call()
    )
]

if backup_name in registered_names:
    print(
        f"Blockchain record already exists: {backup_name}"
    )
    raise SystemExit(0)

sha256_hash = calculate_sha256(backup_file)
timestamp = extract_timestamp(backup_name)
patient_count, condition_count = get_record_counts()

storage_location = (
    f"minio://rescuecloud-backups/{backup_name}"
)

transaction_hash = contract.functions.registerBackup(
    backup_name,
    timestamp,
    sha256_hash,
    patient_count,
    condition_count,
    storage_location,
).transact(
    {"from": web3.eth.accounts[0]}
)

receipt = web3.eth.wait_for_transaction_receipt(
    transaction_hash
)

print("Backup registered on blockchain.")
print("Backup:", backup_name)
print("Block number:", receipt.blockNumber)
print("Transaction:", transaction_hash.hex())
print(
    "Registered backups:",
    contract.functions.getBackupCount().call(),
)
