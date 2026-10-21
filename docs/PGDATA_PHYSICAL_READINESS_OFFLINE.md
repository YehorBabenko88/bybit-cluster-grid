# PostgreSQL physical readiness — implementation boundary

**Draft / offline only / NO-GO.** This adds a pure planning gate, not a PostgreSQL provisioning or backup implementation. Reference: issue #217. Branch starts at frozen PR #215 HEAD `4d0569d64763eba358c58d47211c5bb0165f78cb`. PR #216 SID/ACL experiment is a separate scope.

## Current architecture
- Existing schema-1: `<drive>\\GridLab\\<run_id>\\<node_id>\\pgdata`.
- PowerShell producer and future PGDATA Intent V1: `<parent>\\<run_id>_<node_id>\\postgres\\data`.
- They are not interchangeable. No mapping/alias, schema-2 activation or historical artifact rewriting is implemented.
- Existing clusters, services, credentials and data must remain untouched.

## Implemented now
`installer.pgdata_physical_readiness_offline.evaluate(packet)` consumes only a closed Python dictionary with contract `PGDATA_PHYSICAL_READINESS_OFFLINE_V1`, a commit identifier, `OFFLINE_REVIEW_ONLY` action and exactly thirteen named evidence categories. Evidence states may only be `UNKNOWN`, `BLOCKED` or `EVIDENCE_PROPOSED`; proposed evidence must carry a syntactically valid nonzero SHA256. Hashes are untrusted claims and do not authenticate native observations. Every output remains `BLOCKED` with all readiness/ownership/execution/schema2 flags false. No filesystem, service, token, SQL or network calls.

The negative regression suite covers missing/extra fields, forged PASS, forged complete evidence, invalid hashes, prohibited action requests and the immutable blockers. CI runs isolated Python tests on Windows/Ubuntu and Python 3.11/3.12; it is not a native host or restore test.

## Future gates (NOT AUTHORIZED)
G0: two independent human reviews, choose one path contract, backup/RPO/RTO policy and immutable provenance. G1: separately authorized native read-only inventory of exact hosts/volumes/PGDATA ancestors, full SIDs/tokens/ACL, reparse points, service identity, ports, cluster collision and binary provenance. G2: separately approved new empty fixture with distinct custodians and observers. G3: independently reviewed executor and explicit authorization for initdb/service operations on disposable targets only. G4: isolated backup/WAL/PITR/restore and integrity rehearsal on a *different* disposable target, never original PGDATA. G5: independent verification of receipts and physical custody. No gate is passed by this module.

## STOP conditions
Any nonempty or unknown target, `PG_VERSION`, pre-existing service/cluster, unverified file ID/ancestor/reparse/ACL/token, WAL gap, missing backup, checksum discrepancy, unknown SID, missing two human reviews or missing separate owner authorization => stop. Do not auto-fix ACLs, remove directories, start services or rewrite migration history.

`grid/migrations.py` uses PostgreSQL advisory locking and schema migration version/name checks, including migration 48 index invariant; this is not backup consistency, PITR proof or safe PGDATA migration. Restore rehearsals must never use existing clusters.

All 12 VM cases and 10 PC4 SID/ACL cases remain NOT_RUN. `execution_authorized=false`, `readiness_passed=false`, `physical_ready=false`, `ownership_verified=false`, `schema2_enabled=false`.
