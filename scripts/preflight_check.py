from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import psycopg2
from dotenv import load_dotenv
from web3 import Web3


PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"

load_dotenv(PROJECT_DIR / ".env")

failures: list[str] = []
warnings: list[str] = []


def result(name: str, success: bool, message: str) -> None:
    symbol = "✅" if success else "❌"
    print(f"{symbol} {name}: {message}")

    if not success:
        failures.append(name)


def warning(name: str, message: str) -> None:
    print(f"⚠️  {name}: {message}")
    warnings.append(name)


def check_http(name: str, url: str, required: bool = True) -> None:
    try:
        with urlopen(url, timeout=5) as response:
            success = 200 <= response.status < 400

        if required:
            result(name, success, f"HTTP {response.status}")
        elif success:
            result(name, True, f"HTTP {response.status}")

    except Exception as error:
        if required:
            result(name, False, str(error))
        else:
            warning(name, "Not currently running")


def sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


print("\n========== RESCUECLOUD PREFLIGHT CHECK ==========\n")

required_variables = [
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "BLOCKCHAIN_RPC_URL",
    "BACKUP_LEDGER_ADDRESS",
]

missing_variables = [
    variable
    for variable in required_variables
    if not os.getenv(variable)
]

result(
    "Environment",
    not missing_variables,
    (
        "Required variables loaded"
        if not missing_variables
        else f"Missing: {', '.join(missing_variables)}"
    ),
)

try:
    connection = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5,
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM synthea_patients;")
        patients = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synthea_conditions;")
        conditions = cursor.fetchone()[0]

    connection.close()

    result(
        "PostgreSQL",
        True,
        f"{patients} patients, {conditions} conditions",
    )

except Exception as error:
    result("PostgreSQL", False, str(error))

check_http(
    "Backend API",
    "http://127.0.0.1:8001/health",
)

check_http(
    "MinIO",
    "http://127.0.0.1:9000/minio/health/live",
)

check_http(
    "Frontend",
    "http://127.0.0.1:3000",
)

check_http(
    "Recovery API",
    "http://127.0.0.1:8002/health",
    required=False,
)

try:
    web3 = Web3(
        Web3.HTTPProvider(
            os.environ["BLOCKCHAIN_RPC_URL"],
            request_kwargs={"timeout": 5},
        )
    )

    connected = web3.is_connected()

    result(
        "Blockchain RPC",
        connected,
        (
            f"Connected, chain ID {web3.eth.chain_id}"
            if connected
            else "Unable to connect"
        ),
    )

    if connected:
        address = Web3.to_checksum_address(
            os.environ["BACKUP_LEDGER_ADDRESS"]
        )

        code = web3.eth.get_code(address)

        result(
            "BackupLedger contract",
            code not in (b"", b"\x00"),
            address,
        )

except Exception as error:
    result("Blockchain", False, str(error))

backups = list(BACKUP_DIR.glob("rescuecloud_*.sql"))

if not backups:
    result("Local backups", False, "No SQL backups found")

else:
    latest = max(backups, key=lambda path: path.stat().st_mtime)
    checksum_file = Path(f"{latest}.sha256")

    result(
        "Latest backup",
        True,
        f"{latest.name} ({latest.stat().st_size / 1024 / 1024:.2f} MB)",
    )

    if not checksum_file.exists():
        result(
            "Backup checksum",
            False,
            f"Missing {checksum_file.name}",
        )

    else:
        expected_hash = (
            checksum_file.read_text(encoding="utf-8")
            .strip()
            .split()[0]
        )

        actual_hash = sha256(latest)

        result(
            "Backup checksum",
            actual_hash == expected_hash,
            (
                "SHA-256 verified"
                if actual_hash == expected_hash
                else "Hash mismatch — possible corruption or tampering"
            ),
        )

print("\n=================================================")

if failures:
    print("\nPREFLIGHT FAILED")
    print("Fix these services before running recovery:")
    for failure in failures:
        print(f" - {failure}")

    raise SystemExit(1)

print("\nPREFLIGHT PASSED")
print("RescueCloud is ready for backup and recovery operations.")

if warnings:
    print(
        "\nOptional services unavailable:",
        ", ".join(warnings),
    )
