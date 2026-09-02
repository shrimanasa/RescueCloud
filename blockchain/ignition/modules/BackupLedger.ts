import { buildModule } from "@nomicfoundation/hardhat-ignition/modules";

export default buildModule("BackupLedgerModule", (m) => {
  const backupLedger = m.contract("BackupLedger");

  return { backupLedger };
});
