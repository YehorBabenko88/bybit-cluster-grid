# DDL-free runtime implementation plan

**Goal:** Separate trusted schema preparation from restricted DML runtime without physical operations.

**Architecture:** One explicit preparation command owns all baseline, migration and supplementary DDL inside a serialized transaction. A protected owner-written schema seal binds source catalogue and structural catalog fingerprint; runtime verifies it read-only, its migration registry and its own restricted privileges before any singleton starts. Existing schema without this seal is BLOCKED, never implicitly adopted. No migration SQL changes or automatic downgrade.

**Tech Stack:** asyncpg, PostgreSQL 18, pytest, Windows PowerShell parsers, GitHub-hosted disposable Docker CI.

- [ ] Reproduce startup and lazy fleet/runtime/rollout DDL with offline regression tests.
- [ ] Implement explicit preparation and fail-closed runtime verification; remove hidden runtime DDL calls, isolate legacy maintenance import.
- [ ] Test malformed seal, partial/unknown registries, restricted roles, drift, concurrent preparation and startup on disposable PostgreSQL 18 only in CI.
- [ ] Document startup graph, trusted-source/security boundaries and future operator commands with PASS/FAIL/BLOCKED gates.
- [ ] Run offline/Windows/Linux checks, independent review, create separate Draft PR and inspect every exact-HEAD CI job.

Physical SID/ACL 0/10 NOT_RUN. Execute NOT_AUTHORIZED. No local PostgreSQL connections.
