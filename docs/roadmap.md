# Implementation Roadmap

## Milestone 0 — Foundation
Goal: repository and development environment.

Deliver:
- project structure
- environment config
- database connection
- frontend shell
- backend shell
- contract project
- health endpoints
- CI/test baseline

Exit:
- all services start locally

## Milestone 1 — Identity and cases
Deliver:
- registration/login
- roles
- case creation
- participants
- authorization middleware

Exit:
- lawyer can create case
- judge/client cannot access unrelated case

## Milestone 2 — Secure documents
Deliver:
- upload validation
- SHA-256
- AES-GCM encryption
- object storage
- document/version metadata

Exit:
- encrypted file round trip works
- hash is deterministic

## Milestone 3 — Blockchain registry
Deliver:
- contract
- deployment scripts
- registration adapter
- verification adapter
- transaction persistence

Exit:
- document version registered
- trusted hash can be retrieved

## Milestone 4 — Versioning
Deliver:
- new version endpoint
- parent version relation
- immutable version records
- current version pointer

Exit:
- V1 and V2 coexist and verify independently

## Milestone 5 — Access control
Deliver:
- VIEW/DOWNLOAD/SHARE/CREATE_VERSION/VERIFY
- grant
- revoke
- expiry

Exit:
- unauthorized and expired access is denied

## Milestone 6 — Verification and Passport
Deliver:
- verification endpoint/UI
- tamper detection
- Document Passport
- audit timeline

Exit:
- complete 3-minute demo works

## Milestone 7 — Showcase
Deliver:
- QR verification
- polished UI
- demo seed data
- API documentation
- architecture diagram

## Milestone 8 — Optional intelligence
Only after MVP is stable:
- OCR
- PII detection
- document classification
- redaction

## Final hardening
- security review
- dependency audit
- authorization tests
- failure-mode tests
- clean install test
- demo rehearsal
