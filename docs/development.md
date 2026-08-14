# Development Workflow

## Local environment

Recommended:
- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Docker Desktop
- Hardhat
- Git

## Repository structure

```text
legal-evault/
├── AGENTS.md
├── PRD.md
├── docs/
├── .agents/
├── backend/
├── frontend/
├── contracts/
├── tests/
├── scripts/
└── docker-compose.yml
```

## Environment variables

Example names only:

```text
DATABASE_URL=
JWT_SECRET=
STORAGE_ENDPOINT=
STORAGE_ACCESS_KEY=
STORAGE_SECRET_KEY=
STORAGE_BUCKET=
BLOCKCHAIN_RPC_URL=
BLOCKCHAIN_PRIVATE_KEY=
CONTRACT_ADDRESS=
```

Never commit actual values.

## Git

Use small commits:

```text
feat: add document upload
feat: add sha256 fingerprinting
feat: register document version on chain
feat: add document verification
test: cover access expiry
fix: prevent document IDOR
```

## Before opening a PR

1. Run backend tests.
2. Run frontend tests.
3. Run contract tests.
4. Run lint/type checks.
5. Run security checks.
6. Test clean startup.
7. Verify no secrets are staged.

## Agent workflow

1. Read the PRD and relevant docs.
2. Inspect existing code.
3. State implementation plan.
4. Implement the smallest coherent change.
5. Test.
6. Review security.
7. Summarize changed files and verification.
