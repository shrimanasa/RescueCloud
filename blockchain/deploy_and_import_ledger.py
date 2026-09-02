from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv, set_key
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_DIR / ".env"
EXPORT_FILE = PROJECT_DIR / "blockchain/state/ledger_export.json"
ARTIFACT_FILE = (
    PROJECT_DIR
    / "blockchain/artifacts/contracts"
    / "BackupLedger.sol/BackupLedger.json"
)

load_dotenv(ENV_FILE)

web3 = Web3(
    Web3.HTTPProvider(
        os.getenv(
            "BLOCKCHAIN_RPC_URL",
            "http://127.0.0.1:8545",
        )
    )
)

if not web3.is_connected():
    raise RuntimeError("Anvil blockchain is not running.")

artifact = json.loads(
    ARTIFACT_FILE.read_text(encoding="utf-8")
)

export = json.loads(
    EXPORT_FILE.read_text(encoding="utf-8")
)

account = web3.eth.accounts[0]

Contract = web3.eth.contract(
    abi=artifact["abi"],
    bytecode=artifact["bytecode"],
)

print("Deploying BackupLedger to Anvil...")

transaction_hash = Contract.constructor().transact(
    {"from": account}
)

receipt = web3.eth.wait_for_transaction_receipt(
    transaction_hash
)

address = receipt.contractAddress

contract = web3.eth.contract(
    address=address,
    abi=artifact["abi"],
)

print("Contract deployed:", address)
print("Importing", export["backup_count"], "backups...")

for index, backup in enumerate(export["backups"], start=1):
    transaction = contract.functions.registerBackup(
        backup["name"],
        backup["timestamp"],
        backup["sha256"],
        backup["patient_count"],
        backup["condition_count"],
        backup["storage_location"],
    ).transact({"from": account})

    web3.eth.wait_for_transaction_receipt(transaction)

    status = backup["status"]

    if status == 1:
        transaction = contract.functions.rejectBackup(
            backup["name"],
            backup["rejection_reason"]
            or "Rejected in previous ledger",
        ).transact({"from": account})

        web3.eth.wait_for_transaction_receipt(transaction)

    elif status == 2:
        transaction = contract.functions.selectRecoveryPoint(
            backup["name"]
        ).transact({"from": account})

        web3.eth.wait_for_transaction_receipt(transaction)

    elif status == 3:
        transaction = contract.functions.selectRecoveryPoint(
            backup["name"]
        ).transact({"from": account})

        web3.eth.wait_for_transaction_receipt(transaction)

        transaction = contract.functions.markBackupRestored(
            backup["name"]
        ).transact({"from": account})

        web3.eth.wait_for_transaction_receipt(transaction)

    print(
        f"[{index}/{export['backup_count']}]",
        backup["name"],
    )

set_key(
    str(ENV_FILE),
    "BLOCKCHAIN_RPC_URL",
    "http://127.0.0.1:8545",
)

set_key(
    str(ENV_FILE),
    "BACKUP_LEDGER_ADDRESS",
    address,
)

count = contract.functions.getBackupCount().call()

print()
print("Ledger import completed.")
print("Contract address:", address)
print("Imported backups:", count)
print(".env updated.")
