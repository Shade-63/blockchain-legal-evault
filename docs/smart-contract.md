# Smart Contract Specification

## Goal

The contract provides a tamper-evident registry for document/version provenance and critical access events.

It is not a document-storage contract.

## Core records

```solidity
DocumentRecord {
    bytes32 documentId;
    bytes32 versionId;
    bytes32 caseId;
    bytes32 documentHash;
    bytes32 parentVersionId;
    uint64 versionNumber;
    uint64 registeredAt;
    address registeredBy;
}
```

Avoid storing human-readable PII.

## Required operations

### registerVersion
Registers a document version and its SHA-256 hash.

Requirements:
- version ID unique
- document hash non-empty
- version number valid
- caller authorized by application/contract model

### grantAccess
Creates a permission record.

Parameters:
- document/version identifier
- grantee identity reference
- permission bitmask or enum
- expiry

### revokeAccess
Marks a grant revoked.

Never delete historical grant state.

### recordEvent
Records a critical lifecycle event.

### verifyVersion
Returns the trusted registered hash for a version.

## Events

Emit events for:

- VersionRegistered
- AccessGranted
- AccessRevoked
- LifecycleEvent

## Contract design rules

- Keep the contract small.
- Avoid storing large strings.
- Avoid storing document contents.
- Avoid unnecessary loops over unbounded arrays.
- Prefer mappings for lookup.
- Emit events for history.
- Add unit tests for authorization and uniqueness.
- Do not expose admin functions that silently rewrite historical records.

## Prototype chain

Use a local/private EVM network during development. The production architecture can migrate to a permissioned consortium network.
