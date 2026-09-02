from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = PROJECT_DIR / "blockchain/state/ledger_export.json"

load_dotenv(PROJECT_DIR / ".env")

artifact_path = (
    PROJECT_DIR
    / "blockchain/artifacts/contracts/BackupLedger.sol/BackupLedger.json"
)

artifact = json.loads(
    artifact_path.read_text(encoding="utf-8")
)

web3 = Web3(
    Web3.HTTPProvider(os.environ["BLOCKCHAIN_RPC_URL"])
)

if not web3.is_connected():
    raise RuntimeError(
        "Current Hardhat blockchain is not running."
    )

contract_address = Web3.to_checksum_address(
    os.environ["BACKUP_LEDGER_ADDRESS"]
)

if web3.eth.get_code(contract_address) in (b"", b"\x00"):
    raise RuntimeError(
        "BackupLedger contract was not found at the configured address."
    )

contract = web3.eth.contract(
    address=contract_address,
    abi=artifact["abi"],
)

backup_count = contract.functions.getBackupCount().call()
backups = []

for index in range(backup_count):
    backup_name = contract.functions.getBackupNameAt(index).call()
    record = contract.functions.getBackup(backup_name).call()

    backups.append(
        {
            "name": record[0],
            "timestamp": int(record[1]),
            "sha256": record[2],
            "patient_count": int(record[3]),
            "condition_count": int(record[4]),
            "storage_location": record[5],
            "status": int(record[6]),
            "rejection_reason": record[7],
            "exists": bool(record[8]),
        }
    )

export = {
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "source_chain_id": web3.eth.chain_id,
    "source_contract_address": contract_address,
    "backup_count": backup_count,
    "backups": backups,
}

OUTPUT_FILE.write_text(
    json.dumps(export, indent=2),
    encoding="utf-8",
)

print("Blockchain ledger exported successfully.")
print("Backups exported:", backup_count)
print("Saved to:", OUTPUT_FILE)
