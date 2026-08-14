# Architecture Decision Record

## ADR-001 — Off-chain encrypted documents

Decision:
Store document bytes off-chain and encrypted.

Reason:
Legal records may contain sensitive data. Blockchain is unsuitable for raw confidential document storage.

## ADR-002 — SHA-256 for document fingerprint

Decision:
Use SHA-256 for deterministic file integrity fingerprints.

Reason:
Widely supported, simple to explain, appropriate for integrity comparison.

## ADR-003 — Version records are immutable

Decision:
Never mutate an existing DocumentVersion.

Reason:
Legal provenance requires preservation of historical state.

## ADR-004 — Local/private EVM for prototype

Decision:
Use a local/private EVM network for development and demo.

Reason:
Fast, reproducible and avoids public-chain cost/privacy issues.

## ADR-005 — PostgreSQL remains authoritative for application metadata

Decision:
Use PostgreSQL for operational metadata while blockchain provides critical provenance anchoring.

Reason:
Blockchains are poor general-purpose application databases.

## ADR-006 — AI is optional

Decision:
AI features are P2.

Reason:
The core problem is integrity/provenance/access. AI must not distract from or destabilize the MVP.

## ADR-007 — No claim of legal authenticity

Decision:
The product describes verification as digital integrity/provenance verification.

Reason:
Cryptographic matching cannot establish whether the contents are factually true or legally valid.
