import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

rpc_url = os.environ["BLOCKCHAIN_RPC_URL"]
contract_address = os.environ["BACKUP_LEDGER_ADDRESS"]

artifact_path = (
    PROJECT_DIR
    / "blockchain"
    / "artifacts"
    / "contracts"
    / "BackupLedger.sol"
    / "BackupLedger.json"
)

artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

web3 = Web3(Web3.HTTPProvider(rpc_url))

if not web3.is_connected():
    raise RuntimeError("Could not connect to the Hardhat blockchain.")

contract = web3.eth.contract(
    address=Web3.to_checksum_address(contract_address),
    abi=artifact["abi"],
)

backup_count = contract.functions.getBackupCount().call()

print("Blockchain connected:", web3.is_connected())
print("Chain ID:", web3.eth.chain_id)
print("Contract address:", contract_address)
print("Registered backups:", backup_count)


# ---------------------------------------------------------------------------
# Read ledger usage
# ---------------------------------------------------------------------------
# python3 blockchain/read_ledger.py           # print all records
# python3 blockchain/read_ledger.py --limit 5 # print last 5 records
# python3 blockchain/read_ledger.py --verify  # check each hash against backup files


# ---------------------------------------------------------------------------
# Interpreting ledger entries
# ---------------------------------------------------------------------------
# is_valid: True if the backup SHA-256 matches when re-verified against the file
# is_valid: False if the file has been modified, deleted, or never existed
# A False is_valid entry is a red flag indicating potential tampering.
# Alert the security team immediately if any entry shows is_valid = False.
