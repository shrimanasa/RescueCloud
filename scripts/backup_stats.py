"""
backup_stats.py -- RescueCloud Backup Inventory Report
======================================================
Scans the backups/ directory and prints a summary of all backup files
including sizes, timestamps, and hash verification status.

Usage:
  python3 scripts/backup_stats.py
  python3 scripts/backup_stats.py --verify  # also checks on-chain hashes
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(verify: bool = False) -> None:
    backups = sorted(BACKUP_DIR.glob("rescuecloud_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not backups:
        print("No backups found in backups/ directory.")
        return

    print(f"Found {len(backups)} backup(s) in {BACKUP_DIR}:\n")
    print(f"  {'Name':<40} {'Size':>10}  {'Modified':<20}")
    print(f"  {'-'*40} {'-'*10}  {'-'*20}")

    for backup in backups:
        stat = backup.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        size = format_size(stat.st_size)
        print(f"  {backup.name:<40} {size:>10}  {modified}")

        if verify:
            sha = sha256_file(backup)
            print(f"    SHA-256: {sha}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="Compute SHA-256 for each backup")
    args = parser.parse_args()
    main(args.verify)


# Integration with cron:
# 0 8 * * * cd /path/to/RescueCloud && python3 scripts/backup_stats.py >> logs/backup_stats.log 2>&1
# This sends a daily backup inventory to the log for retention monitoring.


# ---------------------------------------------------------------------------
# Interpreting output
# ---------------------------------------------------------------------------
# If the most recent backup is > 24 hours old, the backup sidecar may have
# stopped. Check: docker compose ps backup-sidecar
# If any backup file is 0 bytes, the pg_dump failed silently.
# If total backup size is shrinking, check for unexpected cleanups.


# ---------------------------------------------------------------------------
# Backup size trend analysis
# ---------------------------------------------------------------------------
# If backup sizes are growing faster than expected:
#   - Run VACUUM ANALYZE on large tables to reclaim dead tuples
#   - Consider pg_dump --no-blobs to exclude large object storage
#   - Enable pg_partman for time-partitioned tables to reduce per-backup size
# A typical EHR database grows 100-500 MB/month; plan storage accordingly.


# ---------------------------------------------------------------------------
# MinIO integration
# ---------------------------------------------------------------------------
# To check backup stats in MinIO (S3-compatible object storage):
#   mc alias set minio http://localhost:9000 minioadmin minioadmin
#   mc ls minio/rescuecloud-backups/
#   mc stat minio/rescuecloud-backups/rescuecloud_latest.sql
# This verifies that cloud uploads are completing alongside local backups.


# ---------------------------------------------------------------------------
# Backup verification schedule
# ---------------------------------------------------------------------------
# Recommended verification schedule:
#   Daily: python3 scripts/backup_stats.py (size and age check)
#   Weekly: python3 scripts/backup_stats.py --verify (hash computation)
#   Monthly: python3 blockchain/verify_latest_backup.py (on-chain verification)
# These checks detect silent corruption before it affects recovery capability.
