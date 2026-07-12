# Backup and Recovery Process

RescueCloud creates PostgreSQL backups using pg_dump.

Backup workflow:

1. Export the RescueCloud PostgreSQL database.
2. Create a timestamped SQL backup file.
3. Generate a SHA-256 checksum.
4. Upload the SQL file and checksum to MinIO.
5. Keep backup versions for later recovery.

Before restoration, RescueCloud calculates the checksum again and compares it with the stored SHA-256 value.

If the values match, the backup is considered clean and safe.

Recovery workflow:

1. Select the latest backup.
2. Verify its SHA-256 checksum.
3. Remove the previous recovery environment.
4. Create a fresh PostgreSQL recovery container.
5. Restore the verified SQL backup.
6. Confirm restored patient and condition counts.
7. Start the recovery FastAPI backend.
8. Run a health check.

A successful recovery should contain:

- 1,108 restored patients
- 37,724 restored conditions

Local recovery command:

bash scripts/recover_latest.sh

Cloud-storage recovery command:

bash scripts/recover_from_cloud.sh
