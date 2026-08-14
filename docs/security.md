# Security & Threat Model

## Assets

1. Legal document contents
2. Encryption keys
3. User credentials
4. Document hashes
5. Access permissions
6. Provenance history
7. Blockchain private keys
8. Database records
9. Object storage

## Threats

### T1 — Unauthorized document access
Mitigation:
- server-side authorization
- document-level permissions
- least privilege
- expiry and revocation

### T2 — Document tampering
Mitigation:
- SHA-256 fingerprint
- trusted blockchain registration
- verification workflow

### T3 — Database audit manipulation
Mitigation:
- critical provenance events anchored to blockchain
- append-only application model

### T4 — File upload attacks
Mitigation:
- size limits
- MIME/content validation
- generated storage keys
- safe file handling
- optional malware scanning

### T5 — Path traversal
Mitigation:
- never use raw filename as storage path
- generated object identifiers

### T6 — Credential theft
Mitigation:
- strong password hashing
- secure sessions/tokens
- rate limiting
- no secrets in logs

### T7 — Blockchain private-key leakage
Mitigation:
- environment secret management for prototype
- never commit keys
- use a dedicated development account
- production KMS/HSM

### T8 — PII leakage
Mitigation:
- no raw documents on-chain
- synthetic data in development
- minimal metadata
- optional PII scanning

### T9 — Replay/duplicate registration
Mitigation:
- unique document/version IDs
- contract uniqueness checks
- idempotency where appropriate

### T10 — Blockchain outage
Mitigation:
- explicit `VERIFICATION_UNAVAILABLE`
- retry/reconciliation mechanism
- never falsely report success

## Security boundaries

The frontend is untrusted.

The API is the authorization boundary.

The blockchain is the integrity/provenance boundary.

Object storage is the confidential-content boundary.

## Important distinction

SHA-256:
- integrity fingerprint
- not encryption

AES-GCM:
- confidentiality + authenticated encryption

Password hashing:
- Argon2id/bcrypt
- not SHA-256

## Production caveat

This prototype is not a certified legal-record system. Production deployment requires formal threat modeling, penetration testing, key management, privacy/legal review, disaster recovery and institutional identity integration.

## Startup Registry Validation Bypass Control (BYPASS_STARTUP_VALIDATION)

To facilitate automated integration tests and simulate registry/RPC infrastructure outages during development, the system provides a `BYPASS_STARTUP_VALIDATION` parameter:

1. **Default State**: Bypassing startup checks is disabled by default (`False`).
2. **Environment Restriction**: Bypassing checks is explicitly blocked in production app environments (`app_env="production"`). If a bypass is requested in production, the application logs a critical security violation and exits immediately with code 1.
3. **Visibility**: When bypassed in development/testing, the application logs a clear warning: `"WARNING: Startup registry validation bypassed. This is ONLY allowed in test/development scenarios."`
4. **No Verification Bypass**: Public verification endpoints (`/verify/public/...`) and authenticated verification endpoints (`/verify`) never bypass the blockchain check or fall back to PostgreSQL database matching. A successful `VERIFIED` state always requires an active, successful on-chain registry lookup. If the blockchain is unreachable, the API returns `VERIFICATION_UNAVAILABLE`.
