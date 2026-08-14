# API Contract

Base path: `/api/v1`

## Auth

### POST `/auth/register`
Create a demo user.

### POST `/auth/login`
Return authentication token/session.

### GET `/auth/me`
Return current user.

## Cases

### POST `/cases`
Create a case.

Request:
```json
{
  "case_number": "CIV-2026-00421",
  "title": "Sharma vs Kumar",
  "description": "Synthetic demonstration case"
}
```

### GET `/cases`
List cases visible to current user.

### GET `/cases/{case_id}`
Return case and participants.

### POST `/cases/{case_id}/participants`
Add authorized participant.

## Documents

### POST `/cases/{case_id}/documents`
Multipart upload.

Required:
- file
- title
- document_type

Response should include:
- document_id
- version_id
- version_number
- sha256_hash
- blockchain_status
- blockchain_tx_hash
- passport summary

### GET `/documents/{document_id}`
Return Document Passport summary.

### GET `/documents/{document_id}/versions`
Return version history.

### GET `/documents/{document_id}/versions/{version_id}`
Return version metadata.

### GET `/documents/{document_id}/download`
Return a secure download for an authorized user.

## Versions

### POST `/documents/{document_id}/versions`
Upload a new version.

Rules:
- preserve old version
- compute new hash
- encrypt and store new file
- register new version
- update current_version_id

## Access

### POST `/documents/{document_id}/access`
Grant access.

Request:
```json
{
  "user_id": "uuid",
  "permissions": ["VIEW", "DOWNLOAD"],
  "expires_at": "2026-08-30T23:59:59Z"
}
```

### POST `/documents/{document_id}/access/{grant_id}/revoke`
Revoke access.

### GET `/documents/{document_id}/access`
List grants visible to authorized actors.

## Verification

### POST `/verify`
Multipart upload.

Optional identifiers:
- document_id
- version_id

Response statuses:
- VERIFIED
- INTEGRITY_FAILURE
- RECORD_NOT_FOUND
- VERIFICATION_UNAVAILABLE

Never return VERIFIED if the trusted registry cannot be checked.

## Audit

### GET `/documents/{document_id}/audit`
Return authorized audit timeline.

## Health

### GET `/health`
Return application health.

### GET `/health/dependencies`
Return dependency readiness for database, storage and blockchain.

## Error shape

Use a stable structure:

```json
{
  "error": {
    "code": "DOCUMENT_ACCESS_DENIED",
    "message": "You do not have permission to access this document.",
    "request_id": "..."
  }
}
```

Do not expose stack traces, SQL, object keys, secrets or internal exceptions.
