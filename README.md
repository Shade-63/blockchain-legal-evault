# Legal eVault

### SIH260229 — Developing a Blockchain-Based eVault for Legal Records
**Ministry of Law and Justice | Blockchain & Cybersecurity | Software**

---

## 1. Project Overview

### The Problem We Are Solving
In modern legal administrations, digital storage of documents (such as evidence, deeds, pleadings, and orders) is widespread, but simple disk or cloud storage is fundamentally insufficient for maintaining trust:
* **No Tamper Proofing**: Files in conventional cloud servers can be silently modified or deleted by database administrators or intruders without leaving an immutable trail.
* **Lack of Independent Provenance**: It is impossible to verify if a file presented months later is the exact file registered originally, without relying on the integrity of a centralized server.
* **Information Leakage & Version Confusion**: Standard folder sharing often leads to version overlap, accidental overwrites, and the leakage of private case records to unauthorized case stakeholders.

### Our Solution
**Legal eVault** resolves these challenges by combining:
1. **Encrypted, Off-Chain Object Storage**: Actual document files are fully encrypted with per-version isolated keys and stored securely off-chain in object storage (MinIO/S3 compatible).
2. **PostgreSQL Relational Metadata**: Fast, indexed database tables manage relational entities such as cases, participants, audit logs, and access permissions.
3. **Blockchain-Backed Registry**: High-integrity cryptographic proofs (SHA-256 hashes) and permissions are anchored on-chain using smart contracts, providing an immutable record of document state and origin.

### The Core Architectural Principle
> [!IMPORTANT]  
> **The actual legal document (PDF) is NOT stored on the blockchain.**  
> Storing raw documents on-chain violates privacy laws (putting PII on public registers), limits scalability, and incurs prohibitive gas costs. Instead, only a **cryptographic fingerprint (SHA-256 hash)** and **critical permission commitments** are registered on-chain. This guarantees complete confidentiality while enabling public, tamper-evident verification.

---

## 2. Problem Statement Context (SIH)

Under the **Smart India Hackathon (SIH260229)** framework, the Ministry of Law and Justice seeks a system that guarantees the integrity, provenance, and auditable lineage of legal records. 

### Key Challenges Addressed
* **Immutability & Tamper Detection**: Proving that legal evidence has not been altered since upload.
* **Granular Access Control**: Preventing unauthorized access while ensuring relevant stakeholders (Judges, Lawyers, Clients) have authenticated access.
* **Auditability**: Keeping a database-level and blockchain-level record of all lifecycle actions (uploads, views, downloads, grants, revocations).
* **Interoperability & Future Integration**: Building a decoupled architecture that is prepared for integration with eCourts but operates autonomously as a trust framework.

| Current MVP Capabilities | Future Integrations (Planned/Out-of-Scope) |
|---|---|
| Decoupled external case-management sync adapter (`/api/v1/integration/cases/sync`) | Real-time eCourts production integration |
| Local EVM Smart Contract (Hardhat) | Public / Consortium Ethereum L2 networks |
| Local KMS per-version key derivation | Hardware Security Modules (HSM) / Enterprise KMS |
| Demo User Roles (`LAWYER`, `JUDGE`, `CLIENT`) | Institutional SSO / National Digital Identity |

---

## 3. The Trust Flow

```
   User
    │  1. Multipart Upload (PDF + Metadata)
    ▼
FastAPI Backend 
    │  2. Validates PDF structure & magic bytes (%PDF-)
    ├─────────────────────────────────┐
    │ 3. Generates Unique IDs         │ 4. Computes SHA-256 Hash
    ▼                                 ▼
PostgreSQL Database              KMS Key Derivation (HKDF-SHA256)
 (Stores metadata &               (Derives version key)
  audit timelines)                    │
                                      ▼
                                 AES-256-GCM Encryption
                                 (Encrypts PDF bytes)
                                      │
                                      ▼
                                 Object Storage (MinIO)
                                 (Stores encrypted bytes)
                                      │
                                      ▼
                                 Blockchain Adapter (Web3)
                                 (Anchors Version & Permissions)
                                      │
                                      ▼
                                 EVM Smart Contract
                                 (LegalEVaultRegistry)
```

---

## 4. Key Features (Implemented)

1. **Authentication & Role-Based Access**: Uses `bcrypt` password hashing and secure JSON Web Tokens (JWT) conveying claims (`sub`, `email`, `role`, `status`). Supported roles: `LAWYER`, `JUDGE`, `CLIENT`, `ADMIN`.
2. **Case Management**: Allows creation of cases and association of users with cases as `CaseParticipant` records. Enforces strict **Broken Object Level Authorization (BOLA)**: users who are not case participants receive `404 Not Found` when requesting case details.
3. **Secure Document Upload**: Validates upload inputs: rejects files >10MB, non-PDF extensions, non-PDF MIME types, or files missing the `%PDF-` magic byte signature.
4. **Encrypted Document Storage**: Encrypts PDFs using AES-256-GCM before writing to storage. Decrypted files are only served in-memory as streams.
5. **KMS Version-Key Isolation**: Employs HKDF-SHA256 to derive a unique encryption key for every document version: `HKDF-SHA256(master_key, info="legal-evault/document/{doc_id}/version/{ver_id}")`.
6. **Compensating Consistency Rollbacks**: Prevents orphan storage files. If a database transaction fails during document creation, the uploaded storage object is deleted automatically.
7. **Context-Bound Idempotency**: Handled via `X-Idempotency-Key` header. Safe client retries converge on the same document record if the caller/case match, or raise `409 Conflict` if contexts differ.
8. **Blockchain Provenance Registry**: Anchors version records (`documentId`, `versionId`, `sha256Hash`, block metadata) into the `LegalEVaultRegistry` contract.
9. **Fine-Grained Permissions**: Permits `VIEW` (metadata only) vs `DOWNLOAD` (allows decryption stream) roles per document version. Standard participants have no visibility unless granted.
10. **Permission Expiration & Revocation**: Enforces temporary access periods via database triggers. Revocation commits directly to the blockchain and updates database states permanently (cannot be undone or modified).
11. **Immutable Audit Trail**: Intercepts database actions using PostgreSQL triggers, blocking all updates/deletes to `audit_events` and `document_access_grants`.
12. **On-Chain Permission Commitments**: Stores salted permission hashes on the blockchain. Grants are denied immediately if the database state fails to match the on-chain commitment (`AUTHORIZATION_INTEGRITY_FAILURE`).
13. **Document Passport**: Serves as a centralized evidence record, containing case context, blockchain receipts, version history lineage, and active grants.
14. **QR / Opaque-ID Public Verification**: Resolves random verification UUIDs (`opaque_verification_id`) and queries the blockchain directly to verify candidate file drops, bypassing local databases completely.
15. **Startup Registry Validation**: Verifies RPC connections, contract code match, and wallet ownership on application boot, failing startup immediately if settings are mismatched.

---

## 5. Why Blockchain?

Conventional systems rely on the assumption that database administrators, host systems, or cloud operators are fully honest. In legal contexts, this is a dangerous assumption.

### What Blockchain Contributes
* **Immutable Truth Anchor**: Registration timestamps, transaction hashes, and document signatures are locked onto a consensus network. No database admin can modify them to cover up alterations.
* **Tamper Evidence**: If a file is altered, its candidate hash will fail to match the immutable hash registered in the smart contract.
* **Independent Verification**: Anyone with a public QR code can verify a document's signature against the blockchain registry without needing access to the private database or the files themselves.

### What Blockchain DOES NOT Store
* **No Raw PDFs**: Documents remain encrypted off-chain.
* **No Keys/Passwords**: Private encryption keys and master secrets are kept completely off-chain.
* **No PII**: Only raw 16-byte UUIDs and 32-byte hashes are committed on-chain.

---

## 6. System Architecture

```mermaid
graph TD
    subgraph Client Layer
        React[React / TypeScript Frontend]
        VerifyPortal[Public Verification Page]
    end

    subgraph API Gateway
        FastAPI[FastAPI Backend Router]
    end

    subgraph Confidential Storage & DB
        Postgres[(PostgreSQL Database)]
        MinIO[(MinIO Object Storage)]
    end

    subgraph Trust & Provenance Layer
        BCAdapter[Blockchain Adapter]
        Hardhat[Hardhat EVM Localhost]
        Registry[LegalEVaultRegistry Contract]
    end

    React -->|HTTP / JWT| FastAPI
    VerifyPortal -->|HTTP / Rate-Limited| FastAPI
    
    FastAPI -->|SQL / Models| Postgres
    FastAPI -->|AES-256-GCM / AWS SDK| MinIO
    FastAPI -->|JSON-RPC / Web3.py| BCAdapter
    
    BCAdapter -->|Local Host RPC| Hardhat
    Hardhat -->|Solidity Mappings| Registry
```

---

## 7. Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Frontend** | React / TypeScript / Vite | React 19 / Vite 8 | Dark-mode glassmorphic client interface |
| **Backend** | FastAPI | 0.112.0 | Async Python REST API and Gateway |
| **Database** | PostgreSQL | 16-alpine | Storage for users, cases, metadata, and audit records |
| **Migrations** | Alembic | 1.13.2 | Database schema versioning |
| **Object Storage** | MinIO | Latest | Local S3-compatible encrypted object storage |
| **Blockchain** | Hardhat Local Node | 2.22.9 | Local EVM simulation environment |
| **Smart Contracts**| Solidity | 0.8.24 | Provenance registry contract |
| **Web3 client** | Web3.py | 6.20.0 | Python blockchain interaction adapter |
| **Cryptography** | Cryptography (PyCA) | 43.0.0 | AES-256-GCM encryption & HKDF-SHA256 |
| **Linter** | Oxlint | 1.75.0 | High-performance frontend code analysis |
| **Testing** | pytest | 8.3.2 | Automated integration and unit test suite |

---

## 8. Directory Structure

```text
.
├── .agents/                 # AI development guidelines, skills, and plans
├── docs/                    # Complete architectural and design documentation
├── contracts/               # Hardhat smart contract development workspace
│   ├── contracts/           # Solidity source code (LegalEVaultRegistry.sol)
│   ├── scripts/             # Smart contract deployment scripts
│   └── test/                # Hardhat smart contract mocha/chai tests
├── backend/                 # FastAPI backend application
│   ├── alembic/             # Database migrations history and configurations
│   ├── app/                 # Backend codebase
│   │   ├── models/          # SQLAlchemy Database Models
│   │   ├── routers/         # API Endpoint controllers (health, auth, cases, etc.)
│   │   ├── schemas/         # Pydantic schema validation structures
│   │   └── services/        # Service adapters (storage, blockchain, kms, crypto)
│   └── tests/               # Backend pytest unit and E2E integration tests
├── frontend/                # React Vite TypeScript frontend workspace
│   ├── src/                 # Client source code (App.tsx, index.css, main.tsx)
│   └── package.json         # Package configuration and dependency control
├── docker-compose.yml       # Docker environment compose definitions
├── PRD.md                   # Product Requirements Document
├── STATUS.md                # System feature status and development logging
└── .env.example             # Global environment configuration template
```

---

## 9. Prerequisites

* **Git**: To manage repository assets.
* **Docker Desktop**: Required to orchestrate PostgreSQL and MinIO.
* **Python**: Version `3.11.x` is required for the backend workspace.
* **Node.js**: Version `18.x` or `20.x` with `npm` for contracts and frontend workspaces.

---

## 10. Local Setup Guide

Follow this guide to spin up the complete development environment from a fresh clone.

### Step 1: Start Docker Infrastructure
Launch the local database and S3 object storage instances:
```bash
docker-compose up -d
```
Verify that the containers `evault-postgres` and `evault-minio` are running:
```bash
docker ps
```

### Step 2: Set Up Backend Environment
Navigate to the backend directory, create a virtual environment, and install dependencies:
```bash
cd backend
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Create your backend configuration `.env` file from the example:
```bash
cp .env.example .env
```
*(The default settings in `.env` are configured to connect to your local Docker containers and Hardhat wallet immediately.)*

### Step 3: Run Alembic Database Migrations
Apply the relational schema versions onto PostgreSQL:
```bash
alembic upgrade head
```

### Step 4: Compile and Deploy Smart Contracts
Open a separate terminal window and navigate to the contracts directory:
```bash
cd contracts
npm install
npm run compile
```

Start the local Hardhat EVM node:
```bash
npx hardhat node
```
*(Leave this node running to process block transactions and mining requests.)*

Open another terminal and deploy the registry contract to the localhost node:
```bash
cd contracts
npx hardhat run scripts/deploy.js --network localhost
```
Observe the deployment output. It will log a line such as:
`LegalEVaultRegistry deployed to: 0x5FbDB2315678afecb367f032d93F642f64180aa3`

If the address differs from the default `0x5FbDB2315678afecb367f032d93F642f64180aa3`, update the `CONTRACT_ADDRESS` variable inside your `backend/.env` file.

### Step 5: Start FastAPI Backend
Return to your backend terminal window (with the virtual environment active) and run:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
*(FastAPI performs blockchain handshake validation on startup. If it starts successfully, your environment is correctly connected to the Hardhat node.)*

### Step 6: Start Frontend Application
Open another terminal, navigate to the frontend folder, install dependencies, and run Vite:
```bash
cd frontend
npm install
npm run dev
```

The terminal will print the client URL:
`  ➜  Local:   http://localhost:5173/`

Open `http://localhost:5173/` in your browser.

---

## 11. Environment Variables

Configure these keys inside your `backend/.env` file:

| Variable | Purpose | Example / Default | Secret? |
|---|---|---|---|
| `APP_ENV` | Application environment state | `development` | No |
| `DEBUG` | Enables debug responses | `true` | No |
| `JWT_SECRET` | Secret key used for signing session JWT tokens | `super_secure_jwt_secret_key_for_evault_development` | **Yes** (Generate new key in prod) |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://postgres:postgres@localhost:5432/evault` | **Yes** |
| `STORAGE_ENDPOINT` | Local storage endpoint URL | `http://localhost:9000` | No |
| `STORAGE_ACCESS_KEY` | Access key for storage | `minioadmin` | **Yes** |
| `STORAGE_SECRET_KEY` | Secret key for storage | `minioadmin` | **Yes** |
| `STORAGE_BUCKET` | Destination S3 bucket name | `evault-documents` | No |
| `BLOCKCHAIN_RPC_URL` | Local Hardhat RPC node url | `http://localhost:8545` | No |
| `BLOCKCHAIN_PRIVATE_KEY` | Private key for transaction registrar | `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80` | **Yes** (Hardhat local Account #0 key) |
| `CONTRACT_ADDRESS` | Deployed smart contract address | `0x5FbDB2315678afecb367f032d93F642f64180aa3` | No |
| `PUBLIC_VERIFY_BASE_URL` | Public routing domain for QRs | `http://localhost:5173` | No |
| `BYPASS_STARTUP_VALIDATION`| Skip blockchain check on startup | `false` | No |

> [!WARNING]  
> The private key `0xac0974bec39...` is a widely known, deterministic testing key generated by Hardhat. It is completely safe for local development, but **must never be used with real funds or on public production networks.**

---

## 12. Running Tests

Ensure that your Docker infrastructure (`docker-compose`) and Hardhat local node are running before launching integration tests.

### Backend Pytest (Unit & Integration)
Navigate to the `backend/` directory, activate the virtual environment, and run:
```bash
# Run tests ignoring the custom Hardhat/web3 global pytest namespace clashes
python -m pytest tests/ -v -p no:ethereum
```

### Backend E2E Integration Script
Run the automated validation script that steps through case creation, uploading, mutability triggers, access control, and public verification:
```bash
python tests/run_integration.py
```

### Smart Contract Solidity Tests
Navigate to the `contracts/` directory and run:
```bash
npm run test
```

### Frontend Code Build & Lint Checks
Navigate to the `frontend/` directory and run:
```bash
# Verify TypeScript compile targets
npm run build

# Run high-performance linter (oxlint)
npm run lint
```

---

## 13. Manual MVP Demo Scenario

Use this step-by-step checklist to verify all implemented components of the MVP:

1. **Sign Up & Log In as Lawyer**:
   * Navigate to `http://localhost:5173/` and register a new account with the **LAWYER** role. Log in.
2. **Create a Case**:
   * On the dashboard, click **Create Case**. Enter case details (e.g. Case Number: `CIV-2026-00999`, Title: `"Land Title Dispute"`).
3. **Register Case Participants**:
   * Log out. Register a new account with the **CLIENT** role. Copy this Client's User UUID from their profile.
   * Log out. Register a new account with the **JUDGE** role. Copy this Judge's User UUID.
   * Log back in as the Lawyer. In the Case Details view, add the Client and the Judge as participants.
4. **Upload Document Version 1 (V1)**:
   * Under the case view, select **Upload Document**. Drop a sample PDF file.
   * On submit, the system hashes the PDF locally, encrypts it with a derived key, uploads it to MinIO, and anchors its hash on the blockchain.
   * Check the document timeline: the version status will transition from `pending` to `submitted`, and then to `confirmed` with transaction details.
5. **Inspect the Document Passport**:
   * Click on the uploaded document. The **Evidence Passport** drawer opens at the bottom.
   * Observe the vertical flow chart containing the registered V1 cryptographic hash, blockchain block number, and transaction receipt.
6. **Verify Original File Copy**:
   * Under the V1 timeline item, locate the **Verify File Copy** dropzone.
   * Drop the **exact same PDF** you uploaded. The panel should report `VERIFIED`.
7. **Verify a Modified Copy (Tamper Detection)**:
   * Open the PDF on your computer, append a single space or character, and save.
   * Drop this altered PDF copy into the dropzone. The panel will report `INTEGRITY_FAILURE` (document content mismatch).
8. **Commit Version 2 (V2)**:
   * In the Passport drawer, click the **Commit Revision** tab (accessible only to the Lawyer).
   * Upload an updated PDF (representing an amended pleading).
   * Verify that both Version 1 and Version 2 appear in the timeline with independent hashes and block records.
9. **Verify Fine-Grained Access Boundaries**:
   * Log out of the Lawyer account. Log in as the **Client**.
   * Navigate to the Case view. Select the case.
   * Note that the document list is empty! Even though the Client is a case participant, standard users cannot view documents without explicit version grants.
10. **Grant Client Access**:
    * Log back in as the **Lawyer**. Select the document.
    * Go to the **Access Controls** tab. Select the Client's UUID, set permission to `VIEW`, and click **Grant Access**.
    * Log back in as the **Client**. The document is now visible, and the Client can open the Passport. However, the **Download** button is disabled because their permission is restricted to `VIEW`.
11. **Upgrade Permission**:
    * Log back in as the **Lawyer**. Re-grant access to the Client, selecting `DOWNLOAD`.
    * Log in as the **Client**. The Client can now download and read the decrypted PDF.
12. **Revoke Access**:
    * As the **Lawyer**, click **Revoke** next to the Client's active grant.
    * The revocation is signed on-chain and marked in the DB. The Client is instantly blocked from accessing or downloading the file.
13. **Inspect the Audit Trail**:
    * As the **Lawyer**, navigate to the **Enforced Audit Trail** tab in the Document Passport.
    * Confirm that actions like `DOCUMENT_VERSION_CREATED`, `ACCESS_GRANTED`, `DOCUMENT_DOWNLOADED`, and `ACCESS_REVOKED` are immutably logged with actor references and timestamps.
14. **Run Public QR Verification**:
    * In the Lawyer view, note the QR code and the **Open Portal Page** verification link under the version timeline.
    * Click the link to open the public (non-authenticated) verification portal.
    * Drop the original PDF file. The portal verifies the file hash directly against the blockchain registry and returns `VERIFIED`. Drop a tampered copy, and it returns `INTEGRITY_FAILURE`.

---

## 14. API Endpoint Index

The complete interactive documentation is available locally at `http://127.0.0.1:8000/docs` when the backend server is running.

### Authentication
* `POST /api/v1/auth/register`: Create a new user account.
* `POST /api/v1/auth/login`: Authenticate and receive a JWT access token.
* `GET /api/v1/auth/me`: Retrieve profile metadata of the current authenticated user.

### Cases
* `POST /api/v1/cases`: Create a new case file (restricted to `LAWYER` role).
* `GET /api/v1/cases`: List all cases where the current user is registered as a participant.
* `GET /api/v1/cases/{case_id}`: Retrieve case metadata and participant details (BOLA restricted).
* `POST /api/v1/cases/{case_id}/participants`: Add user as a case participant (restricted to Lead Lawyer).

### Documents & Versioning
* `POST /api/v1/cases/{case_id}/documents`: Upload initial document file (V1) under a case.
* `GET /api/v1/cases/{case_id}/documents`: List all documents belonging to a case.
* `GET /api/v1/documents/{document_id}`: Retrieve document details and version passport.
* `POST /api/v1/documents/{document_id}/versions`: Commit a new file revision version (restricted to `LAWYER`).
* `GET /api/v1/documents/{document_id}/versions`: Get complete version history list.
* `GET /api/v1/documents/{document_id}/versions/{version_id}`: Retrieve detailed metadata for a specific version.
* `GET /api/v1/documents/{document_id}/versions/{version_id}/download`: Decrypt and download a specific file version.

### Access Control & Audit
* `POST /api/v1/documents/{document_id}/versions/{version_id}/access`: Grant `VIEW` or `DOWNLOAD` access to a case participant.
* `GET /api/v1/documents/{document_id}/access`: List active access grants.
* `POST /api/v1/documents/{document_id}/access/{grant_id}/revoke`: Revoke an active access grant.
* `GET /api/v1/documents/{document_id}/audit`: Retrieve the complete timeline of audit events for a document.

### Verification & Health
* `POST /api/v1/verify`: Authenticated document integrity validation.
* `POST /api/v1/verify/public/{opaque_verification_id}`: Rate-limited, unauthenticated public verification via opaque ID routing.
* `GET /health`: Liveness uptime check.
* `GET /health/dependencies`: Detailed readiness status of Postgres, MinIO, and Hardhat nodes.

---

## 15. Security Model & Boundaries

```
[ UNTRUSTED FRONTEND ]  ==> [ API AUTHORIZATION BOUNDARY ] ==> [ CONFIDENTIAL BOUNDARY ]
  (Browser Interface)       (FastAPI: Role & BOLA Validation)     (MinIO S3 / AES-GCM)
                                          │
                                          ▼
                             [ INTEGRITY / PROVENANCE BOUNDARY ]
                                  (EVM Smart Contract)
```

* **Frontend Boundary**: All client-side parameters are treated as untrusted. Access decisions, permissions, and cryptographic key derivations are managed or enforced at the API gateway layer.
* **Confidentiality Boundary**: Legal document files are stored encrypted on-chain. Decryption keys are derived on the fly inside the API server via KMS functions and are never written to disk or storage.
* **Integrity Boundary (Postgres Triggers)**: Relational database rules block attempts to update or delete audit events, document versions, and access grants. A compromised database shell cannot alter historical transaction records without causing consistency mismatches.
* **On-Chain Consistency Mapping**: Active document access checks require a matching cryptographic hash in the blockchain ledger. Injecting a fake "authorized" access row into the Postgres database yields an immediately rejected `AUTHORIZATION_INTEGRITY_FAILURE` because the on-chain registry lacks the corresponding commitment hash.

---

## 16. Roles & Permissions Matrix

| Operations | Lawyer (Lead) | Lawyer (Participant) | Judge | Client | Public (Portal) |
|---|---|---|---|---|---|
| **Create Case** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **Manage Case Participants** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **Upload Initial Document** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **Commit Document Revision** | ✅ Yes | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **View Passport Metadata** | ✅ Yes (Absolute) | ⚠️ Only Granted Ver. | ⚠️ Only Granted Ver. | ⚠️ Only Granted Ver. | ❌ No |
| **Download PDF File** | ✅ Yes (Absolute) | ⚠️ Only Granted Ver. | ⚠️ Only Granted Ver. | ⚠️ Only Granted Ver. | ❌ No |
| **Grant Access Permissions** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **Revoke Access Permits** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **Inspect Case Audit Trail** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **Verify File Copies** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes (Via Opaque ID) |

---

## 17. Document Passport Flow

The Document Passport is a unified verification interface for legal records:

1. **Document Identity**: Returns global UUIDs, case tracking identifiers, and title metadata.
2. **Lineage Line**: Displays version lineage (V1 → V2 → V3). Standard case participants only see versions they have explicit grants for.
3. **On-Chain Anchor**: Features direct links to Ethereum tx hashes and block registries.
4. **QR Portal Target**: Generates a public verification URL wrapped in a QR code. The URL targets an opaque token (`opaque_verification_id`), protecting private UUID configurations.
5. **Local Verification**: Enables drag-and-drop comparison to immediately verify if a local copy matches the registered blockchain hash.

---

## 18. Troubleshooting Guide

### 1. Docker Daemon Not Running
* **Symptom**: `docker-compose up` fails or returns `docker daemon is not running`.
* **Fix**: Start Docker Desktop on your system and ensure the VM has fully booted before launching containers.

### 2. FastAPI Startup Fails (Registry Validation Mismatch)
* **Symptom**: Backend console outputs `CRITICAL: Startup Registry Validation Failed: ...` and exits.
* **Fix**: Your configured `CONTRACT_ADDRESS` or `BLOCKCHAIN_PRIVATE_KEY` in `backend/.env` does not match the deployed smart contract status on Hardhat. Verify your deployment address, redeploy using `npx hardhat run scripts/deploy.js`, and update `.env`.

### 3. Hardhat Node Restarted (EVM State Loss)
* **Symptom**: Verification requests return `RECORD_NOT_FOUND` even though the database reports the version is confirmed.
* **Fix**: Restarting the Hardhat node wipes the local blockchain memory. You must redeploy the smart contract, update `CONTRACT_ADDRESS` in `.env`, and restart FastAPI.

### 4. Database Schema/Migration Errors
* **Symptom**: Server outputs SQL column errors or missing table exceptions.
* **Fix**: Apply outstanding migrations:
  ```bash
  cd backend
  alembic upgrade head
  ```

### 5. public_verification_url QR Targeting Wrong Domain
* **Symptom**: QR code link resolves to the wrong host port.
* **Fix**: Verify and update the `PUBLIC_VERIFY_BASE_URL` variable inside your `backend/.env` file to point to your frontend client host address (e.g. `http://localhost:5173`).

---

## 19. Team Development Guide

If you are contributing code changes, follow these guidelines:

* **Backend Changes**: Keep API router logic (`backend/app/routers/`) clean of raw database connections; route interactions through SQLAlchemy session dependencies.
* **Database Updates**: Define SQLAlchemy models in `backend/app/models/` and always generate database migrations using Alembic:
  ```bash
  alembic revision --autogenerate -m "description_of_changes"
  ```
* **Smart Contract Changes**: Put Solidity changes inside `contracts/contracts/`. Always run compile and test tasks before updating backend adapters:
  ```bash
  npm run compile
  npm run test
  ```
* **Documentation**: Document API changes inside `docs/api.md` and keep architectural diagrams updated in `docs/architecture.md`.

---

## 20. SIH Presentation Context

This prototype maps directly to the functional requirements of **SIH260229**:

| SIH Requirement | Current Implementation | Status |
|---|---|---|
| **E-Vault Security** | Per-version encryption key isolation (HKDF-SHA256) and AES-256-GCM authenticated encryption | ✅ Completed |
| **Failsafe Audit trail** | Immutable database triggers blocking updates/deletes to audit events and access grants | ✅ Completed |
| **On-Chain Integrity** | SHA-256 integrity signatures anchored on EVM contracts | ✅ Completed |
| **Stakeholder Sharing** | Granular VIEW/DOWNLOAD access grants with UTC expiration and immutable revocation | ✅ Completed |
| **Independent Verification** | Anonymous QR portal using rate-limited opaque id lookup | ✅ Completed |

---

## 21. License & Disclaimer

### License
License: Not yet specified.

### Disclaimer
> [!CAUTION]  
> This project is a prototype developed for the Smart India Hackathon (SIH). It is designed to demonstrate secure legal-record provenance, integrity verification, access control, and auditing. It does not establish legal validity, authenticity in the legal sense, or factual correctness of any document. It must not be used to store real-world legal records without formal threat modeling, penetration testing, infrastructure hardening, and legal/compliance review.
