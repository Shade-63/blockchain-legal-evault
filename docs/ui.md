# UI Specification

## Design direction

Professional legal-tech interface.

Priorities:
- trust
- clarity
- restrained visual hierarchy
- strong status indicators
- minimal blockchain jargon

Do not make the interface look like a crypto wallet.

## Screens

### 1. Login
- email
- password
- demo role shortcuts only in development

### 2. Dashboard
Show:
- cases
- recent document activity
- verification summary
- pending access items

### 3. Case page
Show:
- case metadata
- participants
- document list
- document verification status
- upload action

### 4. Document Passport
Primary screen.

Show:
- document identity
- case
- owner
- current version
- integrity status
- blockchain registration status
- version lineage
- access grants
- audit timeline
- actions

### 5. Upload
Show:
- file picker
- document title/type
- upload progress
- hashing/registration stages
- final blockchain status

### 6. Verification
Input:
- document
- optional document/version ID

Result:
- VERIFIED
- INTEGRITY FAILURE
- RECORD NOT FOUND
- VERIFICATION UNAVAILABLE

Display:
- expected hash
- received hash
- registered version
- timestamp
- blockchain proof reference

### 7. Access management
Show:
- recipient
- permissions
- start
- expiry
- current status
- revoke action

### 8. Audit timeline
Chronological events:
- actor
- event
- timestamp
- version
- transaction reference where available

## UX rules

- Never expose raw cryptographic strings as the main UX.
- Make verification status understandable.
- Use progressive disclosure for technical proof.
- Explain failures in plain language.
- Never show a green verified state when blockchain verification was unavailable.
