# Integration evidence matrix — Agent #4

Scope: read-only, offline, no VM, SQL, service or deployment operations.

| Boundary | Evidence | Confidence | Remaining blocker |
|---|---|---|---|
| VM PlanOnly / attestation | `cross_contracts.py` negative model tests | MODEL_ONLY | No actual VM principal/SID/ACL execution |
| Ownership session / PG adapter | `cross_contracts.py` session equality | MODEL_ONLY | No live adapter integration or journal replay |
| CI completeness | `workflow_attestation.py`, `evidence_manifest.py` | METADATA_ONLY | CI_METADATA_ONLY: trusted GitHub API run provenance and required job execution must be checked for exact SHA |
| Parallel branch paths | `branch_overlap.py` | PATHS_ONLY | Semantic/API conflicts still possible |
| Deployment leakage | `static_safety_scan.py` | HEURISTIC_ONLY | Obfuscated/dynamic operations may evade detection |
| Physical deployment | Synthetic `physical-deployment-harness` CI | NOT_RUN | 12 physical VM cases not executed |

## Hard invariants

- `status=BLOCKED_UNPROVEN`
- `readiness_passed=false`
- `execution_authorized=false`
- `schema_2_enabled=false`
- 12 physical VM cases `NOT_RUN`
- No merge, no LS5/LS7, no production changes

## Independent audit assignments

1. Codex A: Compare actual VM/attestation JSON schema and Python adapter interfaces against model fixtures. Report differences only; no writes to other branches.
2. Codex B: Compare PGDATA ownership journal and authenticated session handoff contracts, including replay/stale-session negative cases. Report only.
3. Codex C: Inspect Actions job conclusions, skipped jobs, SHA provenance and cancellation patterns; no reruns or production interaction.

A green synthetic workflow is not a physical test. A clean path-diff is not an API compatibility guarantee. No audit artifact authorizes deployment.

Metadata checks do not authenticate repository, event, workflow path, run ID or attempt; successful aggregate run conclusions do not prove required jobs executed. Replayed or hand-written dictionaries are not CI execution proof.
