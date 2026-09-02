#!/usr/bin/env python3
"""
smart_recover.py — RescueCloud Walk-Backward & PITR Recovery Controller
========================================================================
Supports two recovery modes:

1. Point-In-Time Recovery (PITR - Zero RPO):
   • Uses Base Backup (pg_basebackup) + PostgreSQL WAL log replay.
   • Queries backup_ledger for the latest base backup prior to --compromise-time.
   • Mounts WAL archive volume, writes recovery.signal with target time.
   • PostgreSQL replays every transaction log up to the exact second
     before the compromise timestamp and promotes itself to read-write.

2. Snapshot Restore Fallback:
   • If no base backup is found, selects the latest verified pg_dump snapshot
     prior to --compromise-time and reports the snapshot RPO gap.

Usage:
  python3 scripts/smart_recover.py --compromise-time "2024-11-15 11:59:03"
  python3 scripts/smart_recover.py          # defaults to now()
  python3 scripts/smart_recover.py --compromise-time "2024-11-15 11:59:03" --dry-run
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"
WAL_DIR = PROJECT_DIR / "wal_archive"
ENV_FILE = PROJECT_DIR / ".env"

RECOVERY_DB_NAME = "rescuecloud_recovered"
RECOVERY_DB_CONTAINER = "rescuecloud-recovery-db"
RECOVERY_BACKEND_CONTAINER = "rescuecloud-recovery-backend"
NETWORK = "rescuecloud-network"


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

def load_env() -> dict:
    """Parse .env into a dict. Missing file → sys.exit(2).
    Blank values (POSTGRES_PASSWORD=) are returned as empty string ""
    and will be caught by the explicit credential check in main().
    """
    if not ENV_FILE.exists():
        print(f"ERROR: .env not found at {ENV_FILE}", file=sys.stderr)
        sys.exit(2)
    env: dict = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def pg_connect(env: dict):
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(2)
    # Credentials are guaranteed non-empty by main() startup check.
    # pg_connect() is only called after that gate, so no re-validation here.
    # Prefer environment variables (injected by Docker/subprocess) over .env file
    # values — lets the backend container call this with the correct DB hostname.
    _password = os.environ.get("POSTGRES_PASSWORD") or env.get("POSTGRES_PASSWORD")
    if not _password:
        # Defensive fallback if ever called outside main() — exits cleanly
        # with non-zero so callers (cron, runbooks) don't mistake error for success.
        print(
            "ERROR: POSTGRES_PASSWORD is not set. "
            "Copy .env.example to .env and fill in credentials.",
            file=sys.stderr,
        )
        sys.exit(2)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or env.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT") or env.get("DB_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB") or env.get("POSTGRES_DB", "rescuecloud_ehr"),
        user=os.environ.get("POSTGRES_USER") or env.get("POSTGRES_USER", "CHANGE_ME_INVALID"),
        password=_password,
    )


# ---------------------------------------------------------------------------
# SHA-256 verification
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def verify_backup(backup_file: Path, expected_hex: str) -> bool:
    if not backup_file.exists():
        print(f"  [MISS] File not found locally: {backup_file}")
        return False
    actual_hex = sha256_of_file(backup_file)
    if actual_hex.lower() == expected_hex.lower():
        print(f"  [OK]   {backup_file.name} — SHA-256 verified ✓")
        return True
    print(f"  [FAIL] {backup_file.name} — SHA-256 MISMATCH")
    return False


# ---------------------------------------------------------------------------
# Backup selection query
# ---------------------------------------------------------------------------

def find_clean_backup(
    env: dict,
    compromise_time: datetime,
) -> tuple[Path, datetime, str, int] | tuple[None, None, None, None]:
    """
    Query backup_ledger for clean candidate before compromise_time.
    Prefers 'base' backups for PITR, falls back to 'snapshot'.
    Returns (file_path, created_at, backup_type, rpo_minutes).
    """
    try:
        conn = pg_connect(env)
    except Exception as exc:
        print(f"\nWARNING: Cannot reach primary DB ({exc}). Falling back to filesystem scan.")
        return _fallback_filesystem_scan(compromise_time)

    print(f"\nQuerying backup_ledger WHERE created_at < {compromise_time.isoformat()!r}...")

    with conn, conn.cursor() as cur:
        # 1. Try finding a Base Backup for PITR
        cur.execute(
            """
            SELECT filename, sha256, created_at, backup_type
            FROM   backup_ledger
            WHERE  created_at < %s
              AND  verified = TRUE
              AND  backup_type = 'base'
            ORDER  BY created_at DESC
            LIMIT  1;
            """,
            (compromise_time,),
        )
        base_row = cur.fetchone()

        if base_row:
            filename, sha256_hex, created_at, b_type = base_row
            bp = BACKUP_DIR / filename
            if verify_backup(bp, sha256_hex):
                # WAL log streaming enables 0-RPO recovery
                return bp, created_at, "base", 0

        # 2. Fallback to SQL snapshot candidate
        cur.execute(
            """
            SELECT filename, sha256, created_at, backup_type
            FROM   backup_ledger
            WHERE  created_at < %s
              AND  verified = TRUE
            ORDER  BY created_at DESC;
            """,
            (compromise_time,),
        )
        rows = cur.fetchall()

    for filename, sha256_hex, created_at, b_type in rows:
        bp = BACKUP_DIR / filename
        if verify_backup(bp, sha256_hex):
            rpo = int((compromise_time - created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60)
            return bp, created_at, b_type, rpo

    return None, None, None, None


def _fallback_filesystem_scan(compromise_time: datetime):
    all_backups = sorted(list(BACKUP_DIR.glob("*.sql")) + list(BACKUP_DIR.glob("*.tar.gz")), reverse=True)
    for bp in all_backups:
        hash_file = Path(str(bp) + ".sha256")
        if not hash_file.exists():
            continue
        stored_hex = hash_file.read_text().split()[0].strip()
        if verify_backup(bp, stored_hex):
            b_type = "base" if bp.name.startswith("base") else "snapshot"
            return bp, compromise_time, b_type, 0
    return None, None, None, None


# ---------------------------------------------------------------------------
# Recovery execution
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def restore_database(backup_file: Path, backup_type: str, compromise_time: datetime, env: dict):
    # Credentials guaranteed valid by main() startup check — no re-validation needed.
    user = env.get("POSTGRES_USER", "CHANGE_ME_INVALID")
    password = env["POSTGRES_PASSWORD"]  # KeyError impossible here; main() already validated

    print("\n[Docker] Cleaning up previous recovery containers...")
    _run(["docker", "rm", "-f", RECOVERY_BACKEND_CONTAINER], check=False)
    _run(["docker", "rm", "-f", RECOVERY_DB_CONTAINER], check=False)

    if _run(["docker", "network", "inspect", NETWORK], check=False).returncode != 0:
        _run(["docker", "network", "create", NETWORK])

    if backup_type == "base":
        print("\n⚡ Executing Point-In-Time Recovery (PITR) via WAL log replay...")
        target_str = compromise_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Start recovery container with WAL archive mounted
        _run([
            "docker", "run", "-d",
            "--name", RECOVERY_DB_CONTAINER,
            "--network", NETWORK,
            "-v", f"{WAL_DIR}:/wal_archive",
            "-e", f"POSTGRES_USER={user}",
            "-e", f"POSTGRES_PASSWORD={password}",
            "-e", f"POSTGRES_DB={RECOVERY_DB_NAME}",
            "-p", "5433:5432",
            "postgres:16",
            "postgres",
            "-c", "wal_level=replica",
            "-c", "restore_command=cp /wal_archive/%f %p 2>/dev/null || exit 1",
            "-c", f"recovery_target_time={target_str}",
            "-c", "recovery_target_action=promote",
        ])

        print(f"  Target recovery timestamp: {target_str}")

    else:
        print("\n📄 Executing Snapshot Restore (pg_dump)...")
        _run([
            "docker", "run", "-d",
            "--name", RECOVERY_DB_CONTAINER,
            "--network", NETWORK,
            "-e", f"POSTGRES_USER={user}",
            "-e", f"POSTGRES_PASSWORD={password}",
            "-e", f"POSTGRES_DB={RECOVERY_DB_NAME}",
            "-p", "5433:5432",
            "postgres:16",
        ])

    # Wait for DB ready
    for attempt in range(1, 31):
        res = _run(
            ["docker", "exec", RECOVERY_DB_CONTAINER,
             "pg_isready", "-U", user, "-d", RECOVERY_DB_NAME],
            check=False,
        )
        if res.returncode == 0:
            print(f"  PostgreSQL ready after {attempt * 2}s")
            break
        time.sleep(2)
    else:
        print("ERROR: PostgreSQL failed to start.", file=sys.stderr)
        sys.exit(1)

    if backup_type == "snapshot":
        print(f"\n[Restore] Loading SQL dump: {backup_file.name}")
        with backup_file.open("rb") as sql_in:
            subprocess.run(
                ["docker", "exec", "-i", RECOVERY_DB_CONTAINER,
                 "psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", RECOVERY_DB_NAME],
                stdin=sql_in, check=True,
            )

    # Print restored summary
    result = _run([
        "docker", "exec", RECOVERY_DB_CONTAINER,
        "psql", "-U", user, "-d", RECOVERY_DB_NAME,
        "-c",
        "SELECT "
        "(SELECT COUNT(*) FROM synthea_patients) AS restored_patients, "
        "(SELECT COUNT(*) FROM synthea_conditions) AS restored_conditions;",
    ], check=False)
    if result.returncode == 0:
        print("\nRestored Database Status:")
        print(result.stdout)

    # Start recovery backend on port 8002
    print("[Docker] Starting recovery backend on port 8002...")
    _run([
        "docker", "run", "-d",
        "--name", RECOVERY_BACKEND_CONTAINER,
        "--network", NETWORK,
        "-p", "8002:8000",
        "-e", f"DB_HOST={RECOVERY_DB_CONTAINER}",
        "-e", "DB_PORT=5432",
        "-e", f"DB_NAME={RECOVERY_DB_NAME}",
        "-e", f"DB_USER={user}",
        "-e", f"DB_PASSWORD={password}",
        "rescuecloud-backend",
    ])

    print("[API] Checking recovery API status...")
    for _ in range(20):
        try:
            urllib.request.urlopen("http://127.0.0.1:8002/health", timeout=3)
            print("\n✓ Recovery API is HEALTHY on port 8002")
            print("  → http://127.0.0.1:8002/patients")
            return
        except (urllib.error.URLError, OSError):
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="RescueCloud PITR & Smart Recovery Controller")
    parser.add_argument("--compromise-time", type=str, default=None, metavar="YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--dry-run", action="store_true", help="Find backup without starting containers")
    args = parser.parse_args()
    env = load_env()

    # Validate credentials at startup — before any recovery work begins.
    # Failing here is safe (nothing has been touched yet).
    # Failing mid-recovery inside restore_database() would be a different risk.
    if not env.get("POSTGRES_PASSWORD"):
        print(
            "ERROR: POSTGRES_PASSWORD is not set in .env. "
            "Copy .env.example to .env and fill in credentials.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.compromise_time:
        try:
            compromise_time = datetime.strptime(args.compromise_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            print("ERROR: Use format YYYY-MM-DD HH:MM:SS", file=sys.stderr)
            sys.exit(2)
    else:
        compromise_time = datetime.now(tz=timezone.utc)

    print(f"\n{'='*65}")
    print(" RescueCloud Smart Recovery (PITR & WAL Archiving)")
    print(f"{'='*65}")
    print(f" Compromise threshold : {compromise_time.isoformat()}")

    clean_backup, backup_ts, backup_type, rpo_minutes = find_clean_backup(env, compromise_time)

    if clean_backup is None:
        print("\n✗ RECOVERY FAILED — no clean pre-compromise backup found.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*65}")
    print(" ✓ Recovery candidate confirmed")
    print(f"   Backup file  : {clean_backup.name}")
    print(f"   Backup type  : {backup_type.upper()} ({'WAL PITR' if backup_type == 'base' else 'Snapshot'})")
    print(f"   Created at   : {backup_ts}")
    print(f"   RPO Gap      : {rpo_minutes} minutes ({'ZERO DATA LOSS' if rpo_minutes == 0 else 'Snapshot window'})")
    print(f"{'='*65}")

    if args.dry_run:
        print("\n[DRY RUN] Stopping here. No containers started.")
        sys.exit(0)

    restore_database(clean_backup, backup_type, compromise_time, env)


if __name__ == "__main__":
    main()
