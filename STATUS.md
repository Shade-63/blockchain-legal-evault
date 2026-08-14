# Project Status — Legal eVault
## Current Milestone
*   **Milestone 5 — Controlled Access & Audit Trail** (Completed)

## Completed Work
*   **Milestone 0 — Foundation**:
    *   Core directories (`backend/`, `frontend/`, `contracts/`).
    *   System `.gitignore` and warning-free `docker-compose.yml`.
    *   FastAPI backend with liveness and readiness endpoints.
    *   Hardhat smart contract skeleton compilation and deploy test.
    *   React liveness health interface.
*   **Milestone 1 — Identity and Cases**:
    *   **Database Models**: Implemented `User`, `Case`, and `CaseParticipant` tables with Python-side default constructors to guarantee database serialization compatibility.
    *   **Migrations**: Initialized Alembic migrations and successfully applied migration `a5b667de1b35_create_initial_tables.py` for user/case schemas.
    *   **Authentication**: Integrated `bcrypt` password hashing and Bearer JWT tokens (`sub`, `email`, `role`, `exp`). Implemented `/auth/me` with server-side lookup.
    *   **Authorization (BOLA/IDOR protection)**: Enforced strict BOLA controls. Non-case participants receive `404 Not Found` trying to access cases. Case participant management is restricted to case creators / lead lawyers.
    *   **Integration Tests**: Created `backend/tests/run_integration.py` and verified all authentication and case operations against the live containers.
*   **Milestone 2 — Secure Documents**:
    *   **Database Models**: Implemented `Document` and `DocumentVersion` tables including foreign key relationships and default values.
    *   **Migrations**: Created and executed `178be4ecf353_create_document_tables.py` Alembic migration against the real PostgreSQL container database.
    *   **PDF Validation**: Checked files for `.pdf` extension, `application/pdf` MIME type, 10MB size limit, and `%PDF-` magic byte signature (first 5 bytes of stream).
    *   **Cryptography**: Integrated AES-256-GCM authenticated encryption/decryption, storing unified objects as `nonce (12 bytes) + tag (16 bytes) + ciphertext`.
    *   **KMS Abstraction**: Developed `KMSService` providing version-level key isolation via HKDF-SHA256:
        `HKDF-SHA256(master_key, info="legal-evault/document/<doc_id>/version/<ver_id>")`
    *   **S3 Object Storage**: Configured `StorageService` using `boto3` to communicate with the local MinIO container. Supports uploads (validating SDK ETags), downloads, and auto-creation of the `evault-documents` bucket on initialization.
    *   **Consistency Rollbacks**: Implemented try/catch blocks that invoke a compensating delete (`StorageService.delete_object`) in MinIO if the subsequent PostgreSQL transaction fails, preventing orphaned objects.
    *   **Context-Bound Idempotency**: Configured `idempotency_key` unique constraints bound to the case and user context. If a matching key/owner/case retry occurs, the API returns the cached document metadata (`200 OK`). If the key matches but the owner or case context differs, it raises a `409 Conflict`.
    *   **Audit Events**: Emits structural audit logs for `DOCUMENT_CREATED`, `DOCUMENT_VIEWED`, and `DOCUMENT_DOWNLOADED` with user/case attributes, and raises warnings for unauthorized access/download attempts.
    *   **Verification**: Added mock test suite in `tests/test_documents.py` (27/27 total backend tests passing) and live integration runner in `tests/run_integration.py` validating PDF constraints, GCM encryption, rollback cleanup, and idempotency conflicts against live Postgres/MinIO.
*   **Milestone 3 — Blockchain Adapters & Provenance**:
    *   **Smart Contract**: Implemented `LegalEVaultRegistry.sol` under `contracts/contracts/` compiling on version `0.8.24`. Keyed registry mapping by `bytes16 versionId` (supporting identical hashes for distinct versions) and secured registrations strictly to the contract owner (`onlyOwner`).
    *   **Solidity Tests**: Verified authorized writes, unauthorized rejections, event emissions (`VersionRegistered`), and duplicate version ID rejections.
    *   **Database Schema**: Upgraded `document_versions` to include `blockchain_status` (pending/submitted/confirmed/failed), `blockchain_tx_hash`, `blockchain_block_number`, and `blockchain_timestamp`.
    *   **Blockchain Adapter**: Built `BlockchainAdapter` in `backend/app/services/blockchain.py` using `web3` for gas estimations, raw transactions signing, and event receipt polling.
    *   **Concurreny Protection**: Implemented a thread lock to serialize transaction signings from the single gateway wallet, preventing transaction nonce collisions.
    *   **Startup Validation**: Added lifecycle check that verifies chain RPC connectivity, deployed contract bytecodes, and asserts that the configured backend wallet matches the contract owner (`LegalEVaultRegistry.owner()`), failing startup immediately on mismatch.
    *   **Verification Router**: Created `POST /verify` validating file SHA-256 integrity checks against version context mapping, returning `VERIFIED`, `INTEGRITY_FAILURE`, `RECORD_NOT_FOUND`, or `VERIFICATION_UNAVAILABLE`.
    *   **Reconciliation & Recovery**: Created automatic receipt confirmation on metadata reads and lazy sync lookup that recovers block parameters from the chain directly if the API crashed before database updates.
    *   **Test Validations**: 32/32 pytest backend tests and all run_integration checks passed cleanly.
*   **Milestone 4 — Document Versioning & Immutable Lifecycle**:
    *   **Immutability Enforcement**: Created database triggers and SQLAlchemy ORM event listeners to block any mutations (updates/deletes) to core document version content and lineage fields, while allowing updates strictly to blockchain metadata.
    *   **Concurrency Locking**: Utilized pessimistic PostgreSQL row locks (`SELECT FOR UPDATE`) on the parent `Document` row to serialize concurrent version creations, preventing version number drift.
    *   **Sequential Lineage**: Implemented `POST /documents/{document_id}/versions` which calculates sequential version numbers and links `parent_version_id` to the predecessor.
    *   **Idempotency & Isolation**: Configured version upload idempotency (`idempotency_key` + `authenticated user` + `document_id`) preventing context exposures and cross-document duplicates.
    *   **Isolated Integrity Verification**: Verified that verification checks run independently per version, showing that tampering with one version does not affect the integrity verification of others.
    *   **Test Validations**: Created mock tests (37/37 passing) and live integration tests validating SQL/ORM rejections, pessimistic row locks, idempotency conflicts, and blockchain outage tolerance.
*   **Milestone 5 — Controlled Access & Audit Trail**:
    *   **Fine-Grained Version Access**: Supported `VIEW` and `DOWNLOAD` permission scopes, restricting standard users via `404 Not Found` (BOLA hiding) if they have no active grants, and redacting latest version fields when they have access to older versions only.
    *   **Grant Upgrades & Unique Active Grants**: Supported upgrading `VIEW` to `DOWNLOAD` permissions, and enforced a unique active grant per user and version via conditional database indices.
    *   **Revocation Permanence**: Restricted revocation to NULL -> UTC timestamp transitions only, ensuring it can never be altered or reset once committed.
    *   **Database-Enforced Immutable Audit Trail**: Implemented triggers blocking all `UPDATE`/`DELETE` operations on `audit_events` and `document_access_grants` (except `revoked_at` transitions).
    *   **Referential Integrity**: Implemented `ON DELETE RESTRICT` constraints to prevent user deletion when referenced by historical access grants or audit timeline logs.
    *   **Test Validations**: Implemented 10 integration test scenarios verifying triggers, grants, upgrades, expiration, revocation, referential integrity, and version isolation against live databases.
*   **Milestone 6 — Document Passport & Independent Verification** (Completed & Closed):
    *   **Database Migrations**: Generated Alembic migration adding `opaque_verification_id` column to `document_versions` and altering `actor_user_id` to nullable in `audit_events`.
    *   **Passport Endpoints**: Implemented `/documents/{document_id}/passport` with case participant checking, Lead Lawyer overrides, and strict BOLA version omission logic (ensuring unauthorized version history nodes and metadata are completely omitted from the JSON payload, verified directly at the raw text response level).
    *   **Public Verification**: Developed `/verify/public/{opaque_verification_id}` endpoint matching candidate file hashes against blockchain ledger directly without falling back to DB or exposing metadata, implementing sliding window rate limiting and logging anonymous public audit trail events. Included safe startup validation bypass constraints that fail immediately in production environments and never fall back to local database verification checks.
    *   **Configurable QR Verification Target**: Integrated base URL parameter (`PUBLIC_VERIFY_BASE_URL` on backend, falling back to `window.location.origin` in `App.tsx` client) ensuring public verification QRs target configurable domains without exposing internal API endpoints.
    *   **Frontend Interface**: Built premium dark-mode glassmorphic interface with case document index, active access permits management, and a beautiful vertical flowchart timeline matching local PDF file drops.
    *   **External Case Ingestion sync (Milestone 6A)**: Implemented decoupled external case-management sync adapter `/api/v1/integration/cases/sync` mapping case participants and documents.
    *   **On-Chain Permission Commitments (Milestone 6B)**: Extended Solidity registry contract supporting `grantPermission`, `revokePermission`, and `isPermissionActive` checking of salted Keccak-256 permission hashes. Implemented API route access validation requiring active blockchain commitments and strictly blocking unauthorized database mutations with `AUTHORIZATION_INTEGRITY_FAILURE` or `AUTHORIZATION_UNAVAILABLE` on RPC outages.
    *   **Integrated Tests (Milestone 6C)**: Extended the integrated E2E test runner to cover 11 compliance test scenarios (including BOLA checks, database triggers, unauthorized contract callers, concurrent serialization locking, and outage handling), passing cleanly with no regressions.

## Current Task
*   Milestone 6 fully implemented, verified, and closed. Smart India Hackathon (SIH) PS Compliance Review completed and documented.

## Known Issues & Limitations
*   None.

## Next Milestone
*   Ready to proceed to Milestone 7 when approved.
