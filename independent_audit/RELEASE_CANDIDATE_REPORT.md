# Offline RC checkpoint â€” 2026-10-20

Request: https://github.com/YehorBabenko88/bybit-cluster-grid/issues/203#issuecomment-6274679326

## Two independent decisions

**GO â€” offline release candidate, limited to source review and the bounded offline integration safety inventory.** Five frozen source heads compose without divergent file collisions; all38 selected latest source workflows completed successfully;739 collected offline tests and78 subtests pass; all10 former P2 reproductions are passing regressions, not xfails.

**NO-GO â€” physical deployment.** This is not an installable/activated Windows release or production HA certification. No real VM, guest isolation, native PGDATA ownership, independent principal/ACL/token provenance, trusted time, durable anti-rollback or operator authority has been demonstrated. Schema2 stays disabled;12 physical guest cases NOT_RUN; readiness/execution false. Further physical activity requires new explicit approval and a reviewed isolated plan.

## Frozen heads and CI

Common base: `5d18b2810a8b1b22ce59e46334d35e07f55c46c7`.

|PR|Exact SHA|Latest workflows|
|---|---|---|
|204|`4dcf0dafba4872cce9b5b14745da3471b8aba67a`|8/8 success|
|205|`c97873fbfc1aefc2996688f93564ea0e98259ee7`|7/7 success|
|206|`ed95dbffb71664a22b34e876c9c4da741201a5d0`|8/8 success|
|207|`c12812ba240a27095d0b01d453b25c1653110276`|7/7 success|
|209|`44de8b2efc9d82d641c79be33a051fbe557d3b5a`|8/8 success|

All were already completed on first check; no sleep, dispatch, rerun or service operation was needed. `ci-freeze.json` records every selected run ID, workflow name, URL, matching head SHA and completed-success conclusion. Duplicate push/PR runs do not inflate the38-workflow count. Selected examples:
- [204 principal matrix39304863285](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39304863285)
- [205 preflight39300231629](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39300231629)
- [206 integration39304880881](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39304880881)
- [207 offline39268286345](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39268286345)
- [209 boundary39304865985](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/39304865985)

Four206 artifacts (Ubuntu/Windows xPython3.11/3.12) were downloaded. All four jobs and all returned steps succeeded on exact ed95dbf. Every XML independently matches all28 actual source test names and exact classname;0 skipped/errors/failures. `evidence/ci-receipt-check.json` pins each downloaded XML SHA256. The updated workflow captures collection and reconciles exact IDs, uses head SHA in artifact names, and includes Windows. No combined-candidate GitHub Actions run exists: the aggregate is local only. Per-source green CI is not a remote aggregate build receipt.

## Composition and dependencies

Independent local branch `audit/codex-offline-rc-20261020`, disposable workspace. No Git merge and no agent branch edits. `prepare.py` extracts Git snapshots and overlays only changed files from the five exact heads, aborting on any nonidentical overlap. Result copied into this new branch only. `composition.json` records the full per-PR changed-file inventory.

Only two overlapping paths,205â†”206, currently identical:
- installer/pgdata_cross_contract.py: SHA256 `ff492592757a277661e60d554f73ebbb11b04b7e1f7bee9f0757562ac68392fd`.
- tests/test_pgdata_cross_contract.py: SHA256 `dc76589fe660509c53ecefc957019b8f2448c42bb0ff429ebb1701b4f8dc8192`.

Future divergence must stop integration, never silently overwrite. The runtime/SQL/fencing architecture and base migrations are unchanged. Pinned isolated test-crypto runtime retains cryptography50.0.2; no production dependency change or automatic installation.

Actual PS5.1/7 JSONL producer serialization passes206's canonical reader while205 distinguishes JSONL from its diagnostic envelope. Incompatible schema1 PGDATA (`run/node/pgdata`) versus adapter (`run_node/postgres/data`) remains deliberately blocked.209's versioned diagnostic boundary rejects unsupported raw report shapes rather than manufacturing ownership.204's strict SID/type entry points reject the formerly false-clean inputs.207 remains an in-memory model, not durable protection.

## Offline gate and exact scope

`run_offline.py` defaults to PlanOnly. With explicit `--run-tests`, it executes the union of every test file changed by these five PRs, the complete existing isolated-postgres-offline safety matrix (including PS Windows contracts), the original34 test-key crypto cases, and the independent combined audit. **35 files,739 distinct collected nodes,78 successful subtests;817 JUnit test entries.** All counts are reconciled in `evidence/inventory.json` and `evidence/offline-junit.xml`. This is the complete agreed RC offline integration safety gate, not repository-wide SQL/trading/runtime/physical verification. Database/service/native-handle/real infrastructure suites are outside the authorized inventory, not silently skipped.

Results:
-739 passed +78 subtests, no ordinary skip, xfail, error or failure.
-10 former negative reproductions selected independently:10 passed,19 unrelated audit cases deselected. `evidence/former10.xml` and former10-inventory.json enumerate them.
-Entire independent combined audit:29 passing ordinary tests; no xfail decorators remain. JUnit regressions retain original malicious XML and add the newly required actual collected-ID input. One nonsecurity control was updated from27 to28 PG source tests; no rejection assertion was weakened.
-Original34 crypto +9 adversarial crypto +27 memory-model tests included, test-key dependency mandatory.
-PS5.1/7 actual pure producer/byte-validation, test-key verifier and memory-model smoke passed. No real installer entry point, host inventory or native fixture was executed.
-PowerShell5.1 parser passed for all installer/test scripts; actionlint passed for the five relevant workflows; audit Python AST and git diff checks passed.

First expanded attempt had5 fixture setup errors because the system pytest temp directory was inaccessible;734 tests already passed. This was an environment failure, not a product regression. Rerun used a new nonexistent GUID path confined to the disposable workspace; no system ACL/temp repair/cleanup was performed. Final clean run above is the gate result. The runner retains this isolation rule.

## Closure of previous ten cases

|Previous issue / owner|Cases|Current result|
|---|---|---|
|205 malformed JSON array unpacking / Agent3|2|fixed blocker results, PASS|
|206 non-ASCII digest serialization / Agent4|1|fixed blocked result, PASS|
|206 invented/substr/partial JUnit coverage / Agent4|3|exact collected set/scope rejection, PASS|
|204 SID numeric overflow / Agent2|1|strict range rejection, PASS|
|204 malformed token/ACL types / Agent2|1|strict shape rejection, PASS|
|209 schema2 alias promotions / Agent5|2|deny scan rejects aliases, PASS|

## Remaining blockers / bounded integration order

Metadata consistency does not authenticate source independence; source labels, SID equality, ACL booleans/digests, public test keys and JUnit cannot grant physical authority. Correlated rollback of all replay state and anchor is still undetectable; existing model explicitly reproduces reuse and stays BLOCKED/NOT_IMPLEMENTED. Trusted clock/key custody/real observer identity, durable ledger/nonrollback anchor, guest token separation, native ACL/PGDATA session, ACL ABA and global kernel exhaustion remain outside proved guarantees. Real guest12 NOT_RUN. Installed release manifests, real database/schema state and real Windows lifecycle are not tested here.

Proposed future review order only:205 exact sourceâ†’206 copy/hash/CIâ†’207â†’204â†’209â†’repeat aggregate offline gates. Keep both shared blobs pinned and both207 workflow edits. Coordinator must re-freeze on any source SHA change. An aggregate remote Windows packaging/CI receipt would be additional evidence before distribution; source CI does not attest this aggregate. None of this authorizes merge or deployment.

The package contains a documentation-only dry-run plan, installation/removal/recovery/rollback draft and source/evidence. No executable infrastructure plan, auto-apply, migration downgrade, resource cleanup or service start exists in the dry-run plan. See `docs/OFFLINE_RC_OPERATIONS_DRAFT.md`; notably rollback-release.ps1 can check the DB even without Apply and must not be invoked in this phase.

Source and package SHA256/aggregate local commit are supplied separately in the artifact manifest and final report. The ZIP is a review artifact, not a signed installer or release activation capability.

## Executed file inventory

- independent_audit/test_combined.py
- tests/test_contract_boundary_audit.py
- tests/test_integration_boundary_validation.py
- tests/test_integration_branch_overlap.py
- tests/test_integration_cross_contracts.py
- tests/test_integration_evidence_gate.py
- tests/test_integration_evidence_manifest.py
- tests/test_integration_job_evidence.py
- tests/test_integration_pg_journal_reader.py
- tests/test_integration_pg_pytest_receipt.py
- tests/test_integration_report.py
- tests/test_integration_static_safety_scan.py
- tests/test_integration_workflow_attestation.py
- tests/test_isolated_ownership_contract.py
- tests/test_isolated_postgres_mapping.py
- tests/test_isolated_postgres_plan.py
- tests/test_isolated_postgres_preflight.py
- tests/test_isolated_postgres_windows_contract.py
- tests/test_ownership_adversarial_model.py
- tests/test_ownership_session_prototype.py
- tests/test_ownership_threat_boundary.py
- tests/test_pgdata_cross_contract.py
- tests/test_vm_attestation_adversarial.py
- tests/test_vm_lab_evidence.py
- tests/test_vm_lab_plan.py
- tests/test_vm_lab_robustness.py
- tests/test_vm_principal_cross_guest_isolation.py
- tests/test_vm_principal_evidence_binding.py
- tests/test_vm_principal_evidence_completeness.py
- tests/test_vm_principal_evidence_consistency.py
- tests/test_vm_principal_negative_cases.py
- tests/test_vm_principal_offline.py
- tests/test_vm_principal_readiness_audit.py
- tests/test_vm_replay_model.py
- tests/test_vm_test_attestation.py
