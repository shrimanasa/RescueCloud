from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python3 select_clean_backup.py "
        "<compromise-time ISO format>"
    )

compromise_time = datetime.fromisoformat(sys.argv[1])

if compromise_time.tzinfo is None:
    raise SystemExit(
        "Compromise time must include timezone, "
        "for example: 2026-07-13T14:30:00+05:30"
    )

compromise_timestamp = int(compromise_time.timestamp())

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
    raise RuntimeError("Hardhat blockchain is not running.")

contract = web3.eth.contract(
    address=Web3.to_checksum_address(
        os.environ["BACKUP_LEDGER_ADDRESS"]
    ),
    abi=artifact["abi"],
)

sender = web3.eth.accounts[0]
backup_count = contract.functions.getBackupCount().call()

print("Estimated compromise time:", compromise_time.isoformat())
print("Blockchain backups:", backup_count)
print()

for index in range(backup_count):
    backup_name = contract.functions.getBackupNameAt(index).call()
    record = contract.functions.getBackup(backup_name).call()

    backup_timestamp = record[1]
    status = record[6]

    if (
        backup_timestamp >= compromise_timestamp
        and status in (0, 2, 3)
    ):
        transaction = contract.functions.rejectBackup(
            backup_name,
            "Backup created during or after compromise window",
        ).transact({"from": sender})

        web3.eth.wait_for_transaction_receipt(transaction)

        print("Rejected:", backup_name)

selected = contract.functions.findLatestEligibleBefore(
    compromise_timestamp
).call()

selected_name = selected[0]

transaction = contract.functions.selectRecoveryPoint(
    selected_name
).transact({"from": sender})

receipt = web3.eth.wait_for_transaction_receipt(transaction)

print()
print("Selected clean recovery point:", selected_name)
print("Backup timestamp:", selected[1])
print("Blockchain block:", receipt.blockNumber)
print("Status: Selected")
