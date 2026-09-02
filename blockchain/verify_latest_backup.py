from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

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

backup_name = latest_backup.name
local_hash = calculate_sha256(latest_backup)

record = contract.functions.getBackup(
    backup_name
).call()

verified = contract.functions.verifyBackupHash(
    backup_name,
    local_hash,
).call()

status_names = [
    "Eligible",
    "Rejected",
    "Selected",
    "Restored",
]

print("Backup:", record[0])
print("Blockchain timestamp:", record[1])
print("Blockchain SHA-256:", record[2])
print("Local SHA-256:", local_hash)
print("Patients:", record[3])
print("Conditions:", record[4])
print("Storage:", record[5])
print("Status:", status_names[record[6]])
print("Hash verified:", verified)

if not verified:
    raise SystemExit(
        "ALERT: Backup does not match the blockchain record."
    )

print("STATUS: Backup is authentic and untampered.")
