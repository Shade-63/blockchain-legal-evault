# Acceptance & Demo Test Scenarios

## Happy path

### A1 — Upload
Given an authenticated lawyer in a case,
when they upload a valid PDF,
then the system stores it encrypted, calculates SHA-256, registers the version, and returns a passport.

### A2 — Verify original
Given the exact registered bytes,
verification returns `VERIFIED`.

### A3 — Version
Given V1,
when a lawyer uploads a corrected file,
then V2 is created and V1 remains unchanged.

### A4 — Access
Given a judge has VIEW permission,
the judge can retrieve the document.

### A5 — Revoke
Given the judge's grant is revoked,
the judge cannot retrieve the document.

### A6 — Expiry
Given an expired grant,
the user cannot retrieve the document.

## Negative paths

### N1 — Tampering
Modify one byte in a registered file.
Expected: `INTEGRITY_FAILURE`.

### N2 — Wrong document
Verify a completely unrelated file against DOC-001.
Expected: `INTEGRITY_FAILURE` or `RECORD_NOT_FOUND` depending on request semantics.

### N3 — Unauthorized access
Client A attempts to access Client B's document.
Expected: 403.

### N4 — Blockchain unavailable
Verification is attempted while the blockchain adapter is unavailable.
Expected: `VERIFICATION_UNAVAILABLE`, never `VERIFIED`.

### N5 — Invalid upload
Upload unsupported or oversized file.
Expected: controlled validation error.

### N6 — Historical mutation
Attempt to change V1's hash.
Expected: impossible through application API.

## Security checks

- SQL injection inputs
- path traversal filenames
- oversized upload
- invalid MIME type
- expired JWT/session
- missing authorization header
- IDOR against document IDs
- unauthorized version creation
- unauthorized access grant
- secrets in logs
