# PGDATA cross-contract read-only boundary

This module is a **metadata diagnostic**, not an ownership proof or a deployment approval.

## Input boundaries

- `plan` is validated using the existing schema-1 offline plan validator. Unsupported schema-2 is rejected.
- `adapter` supplies `run_id`, `node_id`, `postgres_port` and `root` metadata. Adapter path layout is checked lexically using `PureWindowsPath`.
- `journal` is a **plain diagnostic dictionary**, not a parsed or verified ownership journal. Its string claims must be exact built-in `str` values; non-string and behavioral objects are rejected before comparisons.
- Neither adapter nor journal claims can turn a result into READY.

## Deliberate permanent blockers

`PHYSICAL_OWNERSHIP_UNVERIFIED` means the code did not inspect the actual directory, native file identity, SID, ACL, reparse/junction target, session journal, signature or lifecycle. `SCHEMA1_ADAPTER_MAPPING_BLOCKED` means schema-1 remains incompatible with the adapter mapping. Both blockers persist even when metadata fields match.

All responses must retain `status=BLOCKED`, `readiness_passed=false`, `execution_authorized=false`, `physical_ready=false`, `ownership_verified=false`, `schema2_enabled=false`. No filesystem, SQL, process, service or network operations are performed.

## CI ownership

`tests/test_pgdata_cross_contract.py` is discovered by the repository-wide preflight pytest matrix (Python 3.11/3.12). The explicitly enumerated offline test lists in `.github/workflows/isolated-postgres-offline.yml` do not currently include it. The integration/CI owner should add it to both Linux and Windows offline invocations after coordination. A green offline job alone does not establish coverage of this module.

## Non-goals

No physical PGDATA provisioning, PostgreSQL execution, ownership session verification, authorization, schema-2 activation or deployment. Never infer those properties from a successful metadata comparison.


## Actual GridLab PowerShell producer (Codex audit F1)

The real PowerShell producer writes UTF-8 (without BOM) newline-terminated
\`owner.jsonl\` rows, with exact ordered fields
\`{"schema":1,"plan_sha256":"<adapter-intent SHA-256>","state":"PREPARED"}\`.
Subsequent states are \`COMMITTED\` and optionally \`RETIRED\` in the canonical
sequence. It has no \`run_id\`, \`node_id\`, \`status\`, \`pgdata\`,
\`readiness_passed\`, or \`execution_authorized\` journal fields.

The argument historically named \`journal\` in \`check_pgdata_contract\`
is a **synthetic diagnostic envelope**, *not* this PowerShell journal.
\`inspect_producer_journal_format\` recognizes canonical JSONL syntax or
returns a fixed rejection reason, but intentionally returns
\`JOURNAL_PRODUCER_JSONL_NOT_DIAGNOSTIC_ENVELOPE\` even on a canonical producer
journal. A correct format is not proof of digest source, session ownership, ACL,
host identity, lifecycle activation, or authenticity. Adapter-intent digest
\`plan_sha256\` is not the separate PostgreSQL-plan digest.

PowerShell's root template is
\`<GridLab parent>\\<run_id>_<node_id>\` and its PGDATA template is
\`<root>\\postgres\\data\`. Schema-1 PostgreSQL validation instead requires
\`<drive>\\GridLab\\<run_id>\\<node_id>\\pgdata\`. **Do not automatically
rewrite or equate these paths**. The permanent
\`SCHEMA1_ADAPTER_MAPPING_BLOCKED\` and physical-ownership blockers remain.

The dedicated offline CI lists and agent #4 integration-evidence workflow
must explicitly execute these pytest-style tests; merely using
\`unittest discover\` does not collect them. Preflight broad pytest already
collects the file on both Python 3.11 and 3.12. A dedicated zero-skip
exact-SHA JUnit receipt remains a dependency for joint integration.
