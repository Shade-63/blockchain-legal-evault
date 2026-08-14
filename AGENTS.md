# Legal eVault — Agent Instructions

## Mission

Build the Legal eVault prototype according to `PRD.md` and the documents under `docs/`.

The product is a blockchain-backed legal-record integrity and provenance system. Do not turn it into a generic blockchain file-storage application.

## Non-negotiable product boundaries

1. Never store raw legal documents on-chain.
2. Store actual files encrypted off-chain.
3. Store cryptographic proofs and critical lifecycle metadata on-chain.
4. Never silently overwrite a document version.
5. Never claim blockchain proves legal validity or factual truth.
6. Never implement legal advice or automated judicial decisions.
7. Never introduce AI merely for marketing value.
8. Do not add infrastructure that is not required by the current milestone.
9. Prefer simple, testable modules over premature microservices.
10. Use synthetic/demo legal data only.

## Engineering priorities

1. Correctness
2. Security
3. Auditability
4. Testability
5. Simplicity
6. UX polish

## Before coding

- Read `PRD.md`.
- Read `docs/architecture.md`.
- Read `docs/security.md`.
- Read the relevant skill under `.agents/skills/`.
- Inspect the existing repository before creating files.
- Reuse existing code when it is safe and appropriate.
- Do not guess external APIs or blockchain contract interfaces; inspect them.

## Change discipline

- Make small, coherent changes.
- Keep business logic separate from transport/UI code.
- Validate all user-controlled inputs.
- Never commit secrets.
- Never disable security controls just to make a test pass.
- Add/update tests for meaningful behavior.
- Run the relevant test suite after implementation.
- Report what changed and what was verified.

## Definition of done

A feature is not complete because code exists. It is complete when:

- behavior is implemented,
- authorization is enforced,
- errors are handled,
- tests cover critical paths,
- documentation is updated when contracts change,
- the application still starts successfully.

## Scope control

If a requested feature is not in the current milestone:

1. Explain why it is out of scope.
2. Identify the appropriate P1/P2 phase.
3. Do not implement it unless explicitly approved.

## Security stop conditions

Stop and reassess if a requested implementation would:

- expose raw documents publicly,
- put PII on-chain,
- bypass authorization,
- disable TLS/security validation in production code,
- hard-code secrets,
- delete audit history,
- mutate historical document records,
- make unverified legal claims.
