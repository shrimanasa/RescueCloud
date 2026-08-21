import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { network } from "hardhat";

describe("BackupLedger", async function () {
  const { viem } = await network.create();

  it("Registers a backup and verifies its SHA-256 hash", async function () {
    const ledger = await viem.deployContract("BackupLedger");

    await ledger.write.registerBackup([
      "rescuecloud_10-00.sql",
      1000n,
      "hash-1000",
      1108n,
      37724n,
      "minio://rescuecloud-backups/rescuecloud_10-00.sql",
    ]);

    assert.equal(await ledger.read.getBackupCount(), 1n);

    assert.equal(
      await ledger.read.verifyBackupHash([
        "rescuecloud_10-00.sql",
        "hash-1000",
      ]),
      true,
    );

    assert.equal(
      await ledger.read.verifyBackupHash([
        "rescuecloud_10-00.sql",
        "tampered-hash",
      ]),
      false,
    );
  });

  it("Selects the latest eligible backup before compromise time", async function () {
    const ledger = await viem.deployContract("BackupLedger");

    await ledger.write.registerBackup([
      "backup_10-00.sql",
      1000n,
      "hash-1000",
      1108n,
      37724n,
      "minio://backup_10-00.sql",
    ]);

    await ledger.write.registerBackup([
      "backup_10-20.sql",
      2000n,
      "hash-2000",
      1108n,
      37724n,
      "minio://backup_10-20.sql",
    ]);

    await ledger.write.registerBackup([
      "backup_10-40.sql",
      3000n,
      "hash-3000",
      1108n,
      37724n,
      "minio://backup_10-40.sql",
    ]);

    const selected =
      await ledger.read.findLatestEligibleBefore([2500n]);

    assert.equal(selected.backupName, "backup_10-20.sql");
    assert.equal(selected.backupTimestamp, 2000n);
  });

  it("Rejects a backup and excludes it from recovery selection", async function () {
    const ledger = await viem.deployContract("BackupLedger");

    await ledger.write.registerBackup([
      "backup_10-00.sql",
      1000n,
      "hash-1000",
      1108n,
      37724n,
      "minio://backup_10-00.sql",
    ]);

    await ledger.write.registerBackup([
      "backup_10-20.sql",
      2000n,
      "hash-2000",
      1108n,
      37724n,
      "minio://backup_10-20.sql",
    ]);

    await ledger.write.rejectBackup([
      "backup_10-20.sql",
      "Created after estimated compromise time",
    ]);

    const selected =
      await ledger.read.findLatestEligibleBefore([2500n]);

    assert.equal(selected.backupName, "backup_10-00.sql");

    const rejected =
      await ledger.read.getBackup(["backup_10-20.sql"]);

    assert.equal(rejected.status, 1);
    assert.equal(
      rejected.rejectionReason,
      "Created after estimated compromise time",
    );
  });

  it("Marks a selected recovery point as restored", async function () {
    const ledger = await viem.deployContract("BackupLedger");

    await ledger.write.registerBackup([
      "backup_10-20.sql",
      2000n,
      "hash-2000",
      1108n,
      37724n,
      "minio://backup_10-20.sql",
    ]);

    await ledger.write.selectRecoveryPoint([
      "backup_10-20.sql",
    ]);

    let backup =
      await ledger.read.getBackup(["backup_10-20.sql"]);

    assert.equal(backup.status, 2);

    await ledger.write.markBackupRestored([
      "backup_10-20.sql",
    ]);

    backup =
      await ledger.read.getBackup(["backup_10-20.sql"]);

    assert.equal(backup.status, 3);
  });
});
