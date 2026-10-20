# Offline release candidate — operations draft, NOT deployment approval

This package is for offline source review and synthetic tests only. Physical deployment is NO-GO. No installer, PostgreSQL, initdb/SQL, VM, task/service operation or production/LS5/LS7 access is authorized. Schema2 remains disabled; all12 real guest cases NOT_RUN. A future isolated physical test requires explicit new approval and a reviewed resource-specific plan.

## Review and offline installation plan

1. Compare the delivered archive SHA256 with the separately reported checksum. Review SOURCE/CI manifests and all five exact source heads; reject divergent205/206 overlapping files. Archive hashes are integrity checks, not signatures or operator authorization.
2. Extract source into a new disposable review workspace only. Never overlay an installed Grid path, WAL, release directory, PostgreSQL cluster or another user's workspace. No existing resource is assumed owned by Grid.
3. Use an existing reviewed isolated test Python with hash-pinned test dependencies. `python -B independent_audit/run_offline.py` defaults to PlanOnly and prints the bounded file inventory. `--run-tests` executes only this offline inventory, requires Windows PS5.1/7 and cryptography50.0.2, creates only disposable workspace fixtures/evidence. It does not install dependencies or provision resources. No repository-wide discovery is implied.
4. Check zero skipped/errors/failures, all10 former negative cases as real passing rejections, exact collected identities and JUnit counts. Test results never grant native ownership or deployment authority.
5. A later installer plan must separately specify the dedicated machine/VM, parent/run/node, ports, task identities, binary/manifest provenance, independent principals, ACL/token evidence, supported schema and rollback target. Existing isolated adapter/PGDATA layout incompatibility is deliberately blocked. Do not rewrite historical plans, synthesize ownership receipts, bypass staging policy or enable schema2 to make it fit.

## Removal / uninstall plan

There is no authorized infrastructure removal operation in this package. Retire-and-preserve is different from uninstall. Never infer directory/database/task/service ownership from names, paths, manifests alone or a previous synthetic PASS. Never auto-delete old releases, WAL, journals or databases. A future removal plan needs exact independently verified owned-resource inventory, explicit approval, evidence backup, retention rules and recovery review. If inventory is missing/ambiguous, stop and preserve everything. No uninstall command is supplied.

## Recovery plan

For the offline candidate, preserve the failed test log/JUnit/inventory and use a new disposable workspace; do not repair or clean installed resources. Rebuild the same source composition and verify hashes before rerunning.

For any future interrupted release switch, the reviewed existing `recover-release.ps1` distinguishes prepared and committed journals under the release mutex, checks runtime guard, and uses atomic pointer operations. This is a design reference only: do not invoke it against a machine in this phase. Unknown/torn/foreign journals, failed process/task inventory or unclear ownership must block; never hand-edit pointers or journals to force recovery. Repeated recovery must be idempotent and retain working data.

## Rollback plan

Offline source rollback means abandoning this new candidate workspace and returning review to the pinned common base; do not reset agents' branches, rewrite main or remove another workspace. No runtime state needs rollback because none was activated.

A future physical rollback must use a separately reviewed compatible target and the existing runtime guard, mutex, integrity validation and prepared/committed journal semantics. Preserve atomic pointers and all work data. Never automatically downgrade PostgreSQL migrations or lower ownership/leader fencing. Schema48 index compatibility and historical catalogues must be reviewed against the actual target independently. Important: `rollback-release.ps1` may perform database checks even without `-Apply` (`--check-db` for CONTROL/LegacyRollback); it is therefore NOT an allowed offline command here. Similarly do not invoke switch/recover just because their default is plan-only: they may access installed resources and mutexes.

## Stop conditions and later integration order

Any failed source hash, differing overlap, missing tests, skip/xfail, malformed receipt, real resource reference, unknown identity, schema2 flag or attempted PostgreSQL/installer operation means STOP. Matching SID strings, source labels, public test-key signatures, ACL digests and green CI are not independent physical evidence. The replay model assumes an independent nonrollback anchor; correlated checkpoint+anchor rollback remains undetectable.

Proposed review order:205 exact source→206 exact copied blobs/CI→207 attestation model→204 principal diagnostics→209 deny-only boundary, then the combined offline gates. This is a plan, not permission to merge or deploy. Final authority flags stay false even when the offline candidate is GO.
