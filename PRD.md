# Legal eVault — Product Requirements Document

## 1. Product Summary

Legal eVault is a secure, blockchain-backed legal-record management system that preserves the integrity, provenance, version history, access permissions, and audit trail of digital legal records.

The system does **not** store legal documents directly on-chain. Actual files are encrypted and stored off-chain. The blockchain stores tamper-evident proofs and critical lifecycle metadata.

### Core product promise

> We are not merely storing legal documents; we are creating a verifiable history around them.

## 2. Problem

Digital legal records can be copied, modified, replaced, shared with the wrong person, or difficult to trace back to their original submission. Conventional document databases can store files and audit rows, but the integrity of critical records still depends heavily on trusted administrators and database controls.

The system must answer:

- What document was originally registered?
- Who registered it?
- When was it registered?
- Which versions existed?
- Who was permitted to access it?
- Who actually accessed it?
- Has the presented file changed?
- Can an authorized party independently verify the registered record?

## 3. Target Users

### Lawyer
- Create/manage cases
- Upload legal records
- Create new document versions
- Grant/revoke document access
- View document history
- Verify documents

### Judge
- View authorized records
- Verify record integrity
- Inspect provenance and audit history
- Manage/review access where permitted

### Client
- View records explicitly shared with them
- Download permitted records
- Verify document integrity

### System Administrator
- Manage users and system configuration
- No ability to silently rewrite blockchain-backed provenance

## 4. MVP Scope

### P0 — Mandatory

1. Authentication and role-based authorization
2. Case creation
3. Document upload
4. Encrypted off-chain file storage
5. SHA-256 document hashing
6. Blockchain document registration
7. Document retrieval
8. Document versioning
9. Granular document permissions
10. Access grant/revoke
11. Document verification
12. Immutable/append-only lifecycle audit events
13. Document Passport view
14. Tamper-detection demonstration

### P1 — Strong showcase features

1. Time-bound access
2. QR verification
3. Audit timeline visualization
4. API integration boundary
5. Demo seed data

### P2 — Optional innovation layer

1. OCR
2. Document classification
3. PII detection
4. Sensitive-document warnings
5. Redacted derivative documents

## 5. Explicit Non-Goals

Do not build in the MVP:

- A replacement for eCourts or court case-management systems
- Legal advice or case-outcome prediction
- Automated judicial decisions
- Public blockchain document storage
- A custom blockchain
- NFTs, tokens, wallets as a user-facing product
- Full mobile application
- Real government integration
- General-purpose AI chatbot
- Legal truth/authenticity determination

The system verifies **digital integrity and provenance**, not the factual or legal validity of the document's contents.

## 6. Core User Journey

1. User logs in.
2. Lawyer creates a case.
3. Lawyer uploads a PDF.
4. Backend validates the file.
5. Backend calculates SHA-256.
6. Backend encrypts the file.
7. Encrypted file is stored off-chain.
8. Blockchain transaction registers document ID, hash, version and lifecycle metadata.
9. Authorized user can access the document.
10. Lawyer creates a corrected version.
11. Version 1 remains preserved; Version 2 gets a new hash and blockchain record.
12. Lawyer grants a judge time-bound access.
13. Access events are recorded.
14. User submits a file to verification.
15. System calculates its hash and compares it to the registered hash.
16. Matching hash => verified registered version.
17. Mismatch => integrity failure/tamper warning.
18. Document Passport displays provenance and lifecycle history.

## 7. Product Principles

### Principle 1 — Blockchain is a trust layer, not storage
Never put confidential legal files on-chain.

### Principle 2 — Preserve history, not just current state
Do not overwrite document versions.

### Principle 3 — Least privilege
Users get the smallest permission required for the smallest useful period.

### Principle 4 — Explainability
Every security decision shown to a judge must have an understandable explanation.

### Principle 5 — Secure by default
Private files, expired access and unauthorized actions must fail closed.

### Principle 6 — MVP before intelligence
AI must never delay or weaken the core document-integrity workflow.

## 8. Success Criteria

The MVP is successful when a fresh deployment can demonstrate:

- A case can be created.
- A document can be uploaded and encrypted.
- Its hash can be registered on the blockchain.
- A new version can be created without destroying the previous version.
- Access can be granted and revoked.
- An authorized user can retrieve a document.
- An unauthorized user is denied.
- The original document verifies successfully.
- A modified copy fails verification.
- The Document Passport shows the lifecycle.
- The audit trail explains the important events.

## 9. Primary Demo Scenario

Use one fictional case: `CASE-2026-00421 — Sharma vs Kumar`.

Demo sequence:

1. Lawyer uploads `Property_Deed.pdf`.
2. Show registration and Document Passport.
3. Grant judge access.
4. Judge views document.
5. Create Version 2.
6. Show V1 and V2 lineage.
7. Modify a copy of V2.
8. Run verification.
9. Show `INTEGRITY FAILURE`.
10. Verify the original V2.
11. Show `VERIFIED`.
12. Open audit timeline.

## 10. Differentiation

Do not claim generic technologies as innovation.

Blockchain, encryption, IPFS/object storage, RBAC and audit logs are implementation primitives.

The product differentiation is the integrated **trusted document lifecycle**:

- Document Passport
- Cryptographically linked version lineage
- Granular and time-bound sharing
- Independent integrity verification
- Append-only critical lifecycle history
- Optional privacy-aware document intelligence

## 11. Constraints

- Prototype must run locally with reproducible setup.
- Blockchain should be local/private for development.
- Secrets must come from environment variables.
- Legal documents used for demos must be synthetic.
- No real personal identifiers in seed data.
- All critical operations require authorization.
- All tests must pass before demo builds are considered complete.
