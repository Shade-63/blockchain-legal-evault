# Data Model

## User

- id: UUID
- email
- password_hash
- display_name
- role: LAWYER | JUDGE | CLIENT | ADMIN
- status
- created_at
- updated_at

## Case

- id: UUID
- case_number
- title
- description
- status
- created_by
- created_at
- updated_at

## CaseParticipant

- id
- case_id
- user_id
- role
- joined_at

## Document

- id: UUID
- case_id
- title
- document_type
- owner_user_id
- current_version_id
- classification
- created_at
- updated_at

## DocumentVersion

- id: UUID
- document_id
- version_number
- object_key
- sha256_hash
- file_size
- mime_type
- created_by
- parent_version_id
- blockchain_tx_hash
- blockchain_record_id
- created_at

## AccessGrant

- id
- document_id
- grantee_user_id
- permissions
- granted_by
- starts_at
- expires_at
- revoked_at
- created_at

Permissions should be a controlled set:
- VIEW
- DOWNLOAD
- SHARE
- CREATE_VERSION
- VERIFY

## AuditEvent

- id
- case_id
- document_id
- version_id
- actor_user_id
- event_type
- event_metadata_json
- blockchain_tx_hash
- created_at

Event types:
- CASE_CREATED
- DOCUMENT_CREATED
- DOCUMENT_REGISTERED
- VERSION_CREATED
- ACCESS_GRANTED
- ACCESS_REVOKED
- DOCUMENT_VIEWED
- DOCUMENT_DOWNLOADED
- DOCUMENT_VERIFIED
- VERIFICATION_FAILED
- DERIVATIVE_CREATED

## BlockchainRecord

- id
- document_version_id
- chain_name
- contract_address
- transaction_hash
- block_number
- record_identifier
- registered_hash
- registered_at
- status

## Important invariants

1. DocumentVersion hash is immutable.
2. DocumentVersion version_number is unique per Document.
3. A document cannot have two current versions.
4. Revoked access cannot be treated as active.
5. Expired access cannot be treated as active.
6. Blockchain registration must reference the exact version hash.
7. Verification must compare against a trusted registered hash.
