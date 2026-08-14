// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

contract LegalEVaultRegistry {
    address public owner;

    struct VersionRecord {
        bytes16 documentId;
        bytes16 versionId;
        bytes32 sha256Hash;
        uint256 blockNumber;
        uint256 timestamp;
        address registeredBy;
        bool isRegistered;
    }

    // Primary Identity: mapping of 16-byte versionId UUID to its provenance record
    mapping(bytes16 => VersionRecord) public registry;

    event VersionRegistered(
        bytes16 indexed versionId,
        bytes16 indexed documentId,
        bytes32 indexed sha256Hash,
        address registeredBy,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not the authorized registrar");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Registers the provenance fingerprint of a document version.
     * @param versionId The 16-byte raw UUID representation of the document version.
     * @param documentId The 16-byte raw UUID representation of the parent document.
     * @param sha256Hash The 32-byte cryptographic integrity hash of the file bytes.
     */
    function registerVersion(
        bytes16 versionId,
        bytes16 documentId,
        bytes32 sha256Hash
    ) external onlyOwner {
        require(versionId != bytes16(0), "Version ID cannot be empty");
        require(documentId != bytes16(0), "Document ID cannot be empty");
        require(sha256Hash != bytes32(0), "Hash cannot be empty");
        require(!registry[versionId].isRegistered, "Version already registered");

        registry[versionId] = VersionRecord({
            documentId: documentId,
            versionId: versionId,
            sha256Hash: sha256Hash,
            blockNumber: block.number,
            timestamp: block.timestamp,
            registeredBy: msg.sender,
            isRegistered: true
        });

        emit VersionRegistered(versionId, documentId, sha256Hash, msg.sender, block.timestamp);
    }

    enum CommitmentStatus {
        None,       // 0: Absent / Unregistered
        Active,     // 1: Active authorized grant
        Revoked     // 2: Revoked grant
    }

    // Mapping from versionId to commitmentHash to status
    mapping(bytes16 => mapping(bytes32 => CommitmentStatus)) public permissionRegistry;

    event PermissionGranted(bytes16 indexed versionId, bytes32 indexed commitmentHash);
    event PermissionRevoked(bytes16 indexed versionId, bytes32 indexed commitmentHash);

    function grantPermission(bytes16 versionId, bytes32 commitmentHash) external onlyOwner {
        require(versionId != bytes16(0), "Version ID cannot be empty");
        require(commitmentHash != bytes32(0), "Commitment hash cannot be empty");
        require(permissionRegistry[versionId][commitmentHash] != CommitmentStatus.Revoked, "Cannot reactivate revoked commitment");
        require(permissionRegistry[versionId][commitmentHash] != CommitmentStatus.Active, "Commitment is already active");

        permissionRegistry[versionId][commitmentHash] = CommitmentStatus.Active;
        emit PermissionGranted(versionId, commitmentHash);
    }

    function revokePermission(bytes16 versionId, bytes32 commitmentHash) external onlyOwner {
        require(versionId != bytes16(0), "Version ID cannot be empty");
        require(commitmentHash != bytes32(0), "Commitment hash cannot be empty");
        require(permissionRegistry[versionId][commitmentHash] == CommitmentStatus.Active, "Commitment is not active");

        permissionRegistry[versionId][commitmentHash] = CommitmentStatus.Revoked;
        emit PermissionRevoked(versionId, commitmentHash);
    }

    function isPermissionActive(bytes16 versionId, bytes32 commitmentHash) external view returns (bool) {
        return permissionRegistry[versionId][commitmentHash] == CommitmentStatus.Active;
    }
}
