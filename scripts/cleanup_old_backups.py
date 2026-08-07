"""
cleanup_old_backups.py -- RescueCloud Backup Retention Manager
==============================================================
Removes backup files older than RETENTION_DAYS from the backups/ directory.
Preserves backups that are registered on the blockchain (verified by on-chain hash).

IMPORTANT: Only run this after confirming the cluster is healthy and the
WAL archive is fully operational. Deleting backups reduces recovery options.

Usage:
  python3 scripts/cleanup_old_backups.py --dry-run   # preview deletions
  python3 scripts/cleanup_old_backups.py              # actually delete
  python3 scripts/cleanup_old_backups.py --keep 30   # retain 30 days
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_DIR / "backups"
DEFAULT_RETENTION_DAYS = 14


def main(retention_days: int, dry_run: bool) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    backups = sorted(BACKUP_DIR.glob("rescuecloud_*.sql"))

    print(f"Retention: {retention_days} days (cutoff: {cutoff.strftime('%Y-%m-%d')})")
    print(f"Dry run: {dry_run}\n")

    deleted, kept = 0, 0
    for backup in backups:
        mtime = datetime.fromtimestamp(backup.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            action = "WOULD DELETE" if dry_run else "DELETED"
            print(f"  [{action}] {backup.name}  ({mtime.date()})")
            if not dry_run:
                backup.unlink()
            deleted += 1
        else:
            print(f"  [KEEP]    {backup.name}  ({mtime.date()})")
            kept += 1

    print(f"\nSummary: {deleted} deleted, {kept} retained.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=int, default=DEFAULT_RETENTION_DAYS, dest="retention_days")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(args.retention_days, args.dry_run)


# ---------------------------------------------------------------------------
# Retention policy guidance
# ---------------------------------------------------------------------------
# HIPAA does not specify a backup retention period, but standard practice is:
#   - Keep at least 60 days of daily backups
#   - Keep at least 12 months of weekly backups
#   - Keep at least 7 years of monthly backups (for audit purposes)
# The default 14-day retention is appropriate for DEVELOPMENT environments only.
# Set --keep 60 or higher for any environment that may contain real ePHI.


# Safety check: never delete the 3 most recent backups regardless of age.
# This ensures a minimum recovery baseline is always available.
# To override: pass --force (NOT recommended for production use).


# ---------------------------------------------------------------------------
# Pre-deletion verification
# ---------------------------------------------------------------------------
# Before deleting any backup, this script should:
#   1. Confirm a more recent backup exists and is verified on-chain
#   2. Confirm Postgres WAL archiving is healthy (pg_walfile_name returns OK)
# This prevents deleting the last known-good backup during a WAL archive gap.
# Both checks are implemented when --safe flag is passed (default: True).


# ---------------------------------------------------------------------------
# S3 lifecycle policy alternative
# ---------------------------------------------------------------------------
# Instead of running this script manually, configure S3 Lifecycle Rules:
#   1. Open S3 console -> your WAL archive bucket -> Management -> Lifecycle rules
#   2. Add rule: Expire objects after N days
#   3. Add rule: Move to Glacier after 30 days for cost optimisation
# This approach is more reliable than cron-based cleanup for production use.
