# 3-Minute SIH Demo Script

## Opening — 20 seconds

"A legal document being stored digitally does not automatically mean we can prove that the file presented months later is the exact registered record.

Legal eVault creates a verifiable lifecycle around each legal record."

## Act 1 — Register

Lawyer opens `CASE-2026-00421`.

Upload `Property_Deed.pdf`.

Say:

"The file is encrypted and stored off-chain. Its cryptographic fingerprint is registered as a blockchain-backed record."

Show:
- registered
- version 1
- verified

## Act 2 — Controlled access

Grant Judge:
- VIEW
- expires in 7 days

Show the access record.

## Act 3 — Versioning

Create Version 2.

Say:

"We never silently overwrite Version 1. Every version gets its own cryptographic identity."

Show V1 → V2.

## Act 4 — Tamper detection

Modify a copy of V2.

Run Verify.

Show:

`INTEGRITY FAILURE`

Say:

"The system is not claiming that the blockchain makes a file impossible to copy. It makes unauthorized changes to the registered record detectable."

## Act 5 — Proof

Verify the original V2.

Show:

`VERIFIED`

Open Document Passport and audit timeline.

## Closing — 20 seconds

"Blockchain is not the product. It is the trust layer. Our product is a verifiable legal-record lifecycle: identity, provenance, controlled access, version history and integrity verification."
