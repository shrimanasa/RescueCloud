// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract BackupLedger {
    enum BackupStatus {
        Eligible,
        Rejected,
        Selected,
        Restored
    }

    struct BackupRecord {
        string backupName;
        uint256 backupTimestamp;
        string sha256Hash;
        uint256 patientCount;
        uint256 conditionCount;
        string storageLocation;
        BackupStatus status;
        string rejectionReason;
        bool exists;
    }

    address public immutable owner;

    mapping(bytes32 => BackupRecord) private backups;
    bytes32[] private backupKeys;

    event BackupRegistered(
        bytes32 indexed backupKey,
        string backupName,
        uint256 backupTimestamp,
        string sha256Hash
    );

    event BackupRejected(
        bytes32 indexed backupKey,
        string backupName,
        string reason
    );

    event RecoveryPointSelected(
        bytes32 indexed backupKey,
        string backupName
    );

    event BackupRestored(
        bytes32 indexed backupKey,
        string backupName
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Only ledger owner can perform this action");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function backupKey(
        string memory backupName
    ) public pure returns (bytes32) {
        return keccak256(bytes(backupName));
    }

    function registerBackup(
        string calldata backupName,
        uint256 backupTimestamp,
        string calldata sha256Hash,
        uint256 patientCount,
        uint256 conditionCount,
        string calldata storageLocation
    ) external onlyOwner {
        require(bytes(backupName).length > 0, "Backup name is required");
        require(bytes(sha256Hash).length > 0, "SHA-256 hash is required");
        require(backupTimestamp > 0, "Backup timestamp is required");

        bytes32 key = backupKey(backupName);

        require(!backups[key].exists, "Backup already registered");

        backups[key] = BackupRecord({
            backupName: backupName,
            backupTimestamp: backupTimestamp,
            sha256Hash: sha256Hash,
            patientCount: patientCount,
            conditionCount: conditionCount,
            storageLocation: storageLocation,
            status: BackupStatus.Eligible,
            rejectionReason: "",
            exists: true
        });

        backupKeys.push(key);

        emit BackupRegistered(
            key,
            backupName,
            backupTimestamp,
            sha256Hash
        );
    }

    function verifyBackupHash(
        string calldata backupName,
        string calldata calculatedHash
    ) external view returns (bool) {
        bytes32 key = backupKey(backupName);

        require(backups[key].exists, "Backup not found");

        return keccak256(bytes(backups[key].sha256Hash))
            == keccak256(bytes(calculatedHash));
    }

    function rejectBackup(
        string calldata backupName,
        string calldata reason
    ) external onlyOwner {
        bytes32 key = backupKey(backupName);

        require(backups[key].exists, "Backup not found");

        backups[key].status = BackupStatus.Rejected;
        backups[key].rejectionReason = reason;

        emit BackupRejected(key, backupName, reason);
    }

    function selectRecoveryPoint(
        string calldata backupName
    ) external onlyOwner {
        bytes32 key = backupKey(backupName);

        require(backups[key].exists, "Backup not found");
        require(
            backups[key].status == BackupStatus.Eligible
                || backups[key].status == BackupStatus.Restored,
            "Backup is not eligible"
        );

        backups[key].status = BackupStatus.Selected;

        emit RecoveryPointSelected(key, backupName);
    }

    function markBackupRestored(
        string calldata backupName
    ) external onlyOwner {
        bytes32 key = backupKey(backupName);

        require(backups[key].exists, "Backup not found");
        require(
            backups[key].status == BackupStatus.Selected,
            "Backup was not selected"
        );

        backups[key].status = BackupStatus.Restored;

        emit BackupRestored(key, backupName);
    }

    function getBackup(
        string calldata backupName
    ) external view returns (BackupRecord memory) {
        bytes32 key = backupKey(backupName);

        require(backups[key].exists, "Backup not found");

        return backups[key];
    }

    function getBackupCount() external view returns (uint256) {
        return backupKeys.length;
    }

    function getBackupNameAt(
        uint256 index
    ) external view returns (string memory) {
        require(index < backupKeys.length, "Index out of range");

        return backups[backupKeys[index]].backupName;
    }

    function findLatestEligibleBefore(
        uint256 compromiseTimestamp
    ) external view returns (BackupRecord memory selectedBackup) {
        uint256 latestTimestamp = 0;
        bool found = false;

        for (uint256 index = 0; index < backupKeys.length; index++) {
            BackupRecord storage candidate =
                backups[backupKeys[index]];

            bool eligible =
                candidate.status == BackupStatus.Eligible
                || candidate.status == BackupStatus.Restored;

            bool beforeCompromise =
                candidate.backupTimestamp < compromiseTimestamp;

            bool newerThanCurrent =
                candidate.backupTimestamp > latestTimestamp;

            if (
                eligible
                && beforeCompromise
                && newerThanCurrent
            ) {
                selectedBackup = candidate;
                latestTimestamp = candidate.backupTimestamp;
                found = true;
            }
        }

        require(
            found,
            "No eligible backup exists before compromise time"
        );
    }
}
