# System Architecture

## 1. High-level

```text
React Frontend
      |
      v
FastAPI API
      |
      +-------------------+
      |                   |
      v                   v
PostgreSQL          Object Storage
metadata            encrypted files
      |
      v
Blockchain Adapter
      |
      v
Permissioned/local EVM
smart contracts
```

## 2. Responsibility split

### PostgreSQL
Store:
- users
- cases
- participants
- document metadata
- version metadata
- application-level access state
- audit query/index metadata
- blockchain transaction references

### Object storage
Store:
- encrypted document bytes

### Blockchain
Store:
- document identifier
- case reference where appropriate
- document/version hash
- version relationship
- critical lifecycle timestamps
- critical access/provenance events
- contract-managed access state where required

Do not store:
- raw PDFs
- raw images
- names, addresses or other PII unless explicitly required and privacy-reviewed
- encryption keys

## 3. Document upload flow

```text
Client
  |
  | multipart upload
  v
API
  |
  +--> validate size/type
  |
  +--> generate document ID
  |
  +--> SHA-256 original bytes
  |
  +--> encrypt bytes
  |
  +--> store encrypted object
  |
  +--> persist metadata
  |
  +--> register hash/provenance on blockchain
  |
  v
Response with document passport summary
```

## 4. Verification flow

```text
Candidate file
      |
      v
SHA-256
      |
      v
Resolve registered document/version
      |
      v
Read trusted registered hash
      |
      +---- match ----> VERIFIED
      |
      +---- mismatch -> INTEGRITY FAILURE
```

If the blockchain cannot be queried, return `VERIFICATION_UNAVAILABLE`, not `VERIFIED`.

## 5. Version flow

A logical Document has one or more immutable DocumentVersions.

```text
DOC-001
  |
  +-- V1: hash A
  |
  +-- V2: hash B
  |
  +-- V3: hash C
```

Never update the bytes/hash of an existing version.

## 6. Authorization

Authorization should evaluate:

- authenticated user
- role
- case participation
- document relationship
- explicit permission
- action
- access expiry
- revocation

Example:

```text
can_access(user, document, action, now)
```

must fail closed.

## 7. Failure behavior

### Blockchain unavailable
- Do not mark record blockchain-verified.
- Queue/retry registration only if designed explicitly.
- Surface status clearly.

### Storage unavailable
- Do not create a successful document record unless the system can guarantee consistency.
- Avoid orphaned metadata.

### Database unavailable
- Return controlled error.
- Never expose stack traces.

## 8. Production evolution

Prototype:
- local/private EVM
- MinIO
- PostgreSQL

Future:
- permissioned consortium blockchain
- managed object storage or private content-addressed storage
- HSM/KMS-backed key management
- enterprise identity integration
- court/case-management API integration
