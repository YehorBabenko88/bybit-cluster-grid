# Integration cycle #246 — source audit and native controller boundary

Physical PC4 SID/ACL: **0/10 NOT_RUN**. Execute and Cleanup **NOT_AUTHORIZED**.
Deployment **NO-GO**. Every one of the 20 physical mutating phases remains BLOCKED.

## Exact source comparison

The complete 184-path divergence inventory, including full Git blob IDs and SHA256
for every distinct blob, is [cycle246-compatibility.json](evidence/2026-10-24/cycle246-compatibility.json).
It compares eight exact Git trees against #238, not working directories. #243 is an
Issue. This is a reproducible snapshot; subsequent source-branch changes require a
new comparison. #244 in that snapshot is the incoming baseline, not this commit.

| PR | Pinned incoming HEAD | Integration disposition |
|---|---|---|
|238|`7df22d1c5cdc60bcf4e3414dacd35d23fdec7149`|Observer/ACL fixture baseline retained; integrated native workflow has exact-source receipts and historical branch guards.|
|239|`7bfcb1bb4b592bf459ef2f7f162c84d3890d4788`|Bootstrap module identical to incoming #244. Disposable-release model/workflow differ; retain integration guards and active-release/source distinction.|
|240|`3c605062285db6e69e61fdd260b15210c05f7cbb`|PG18 source preserved; workflow guard integration differences, no production/installed PostgreSQL adoption.|
|241|`3bca624159f5f27fb6ae268140a88087ea588e93`|Parser now identical after selective catch port; extra integration regression cases retained. Workflow differs in historical branch guards.|
|242|`8981fe037f16f485ab778ca1dff6b16e805255da`|Do not copy removal of expected_heads parameter; retain pinned-head acceptance API and stricter integrated workflow.|
|244|`576e77086f645ac9eb3b0d26a43fc967155d24da`|Incoming verified baseline; its previous hosted PASS does not certify the new commit.|
|245|`0892a1c850787d024a782ff3e44286c191529232`|Alternative older tree: copying whole modules would revert JUnit/ZIP protections, start_mode G0 contract, and generic active_release validation. Not merged.|
|246|`684f4c23826072d0813a5fd17898b530a2dab828`|Only RecursionError catch and two deeply nested JSON tests ported. No merge.|

The JSON inventory records exact discrepancies for all other paths, including
branch-exclusive files and workflow policy differences. Different blobs are not
automatically defects or proof of interface compatibility. Runtime physical
interoperability remains untested.

`trusted_root` identifies authenticated source custody; `active_release` identifies
the separately observed installed release. They need not equal the audit/source
HEAD. Bootstrap requires a full commit-format release plus exact observation match
and matching coordinator path. A hardcoded historical VERSION would reject legitimate
future releases. Neither format validation nor a matching digest authenticates custody.

## Confirmed defects and actual failing logs

### P1: nested JSON escapes fail-closed parser

Original two #246 tests passed before the fix on local CPython 3.12: they alone did
not reproduce the exception here. Independent plain-interpreter subprocess tests
use arrays of depth 20,000 and objects of depth 10,000, both below the 65,536-byte
budget, under normal Python and `-O`. All four failed with uncaught RecursionError
before the patch. Catching that exception produces INVALID_POLICY/BLOCKED, never
execution authority. The complete network file has 84 passing cases after the fix.

### P1: source-branch preflight guards and broken acceptance signature

* #239 run [40114516040](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40114516040),
  exact `7bfcb1b…`: six failures, 2,868 passed, 52 skipped, 85 subtests.
  New bootstrap workflow lacks historical publication guards before runs-on.
* #242 run [40114533868](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/40114533868),
  exact `8981fe0…`: seven failures, 2,751 passed, 52 skipped, 197 subtests.
  Six analogous workflow-guard failures plus
  `GateTests::test_cross_pr_g0_g1_fail_closed`: TypeError, unexpected expected_heads.
  The branch removed the parameter but still uses it in the function body.

The six guards are checked by test_publication_gate, test_lab_airgap_a,
test_lab_manifest_design, test_lab_witness_design, test_pc4_sid_acl_evidence,
and test_pgdata_intent_v1. Reproduction: checkout each pinned tree in a disposable
workspace, run its Python preflight test command; the #242 individual case above
is sufficient for the API failure. Expected: historical branches excluded and
pinned-head API accepted. Actual: assertions/TypeError. No missing-import or missing
dependency error was found in these two exact failure logs. Their skips are not
integration proof. Source agents should fix their own guards/signature; #244 already
retains both protections, so copying their broken workflows is unnecessary.

## Native controller prototype and its limits

The separate `installer/native-g1-controller-fixture` executable is hosted-CI-only.
It accepts no physical execution/cleanup mode or arbitrary caller target/command.
Platform RSA-PSS/SHA256 checks fixture permits against a separately supplied key pin,
head/run/attempt/nonce, expiry, image digest and held object identities. These are
test keys, **not owner authorization**, and replay storage is in memory.

The fixed child starts suspended with a capability-free AppContainer and is placed
in an unnamed kill-on-close Job with active-process limit one before resume. Held
process/thread handles, creation time, image path and held image file, token SID,
capabilities and elevation are checked. No PID lookup is used for termination or
cleanup. A flushed intent precedes resume. Cleanup is bounded to the created marker
through its original handle after proven exit; root, journal and profile are retained
for disposal of the runner. Unknown/live identity refuses cleanup.

The guardian's external-to-journal anchor remains in the same test process: recovery
is a held-handle barrier test, **not OS-crash recovery or durable anti-rollback**.
The fixed child exits cooperatively; no general Grid shutdown protocol is proved.
Job membership is not evidence of protection from a privileged administrator.

The new required CI checks 19 managed and 8 native cases on PowerShell 5.1/7 and
Python 3.11/3.12. A separate job downloads all four artifacts and verifies exact
case inventory, false physical flags, JUnit, JSONL, SHA256, source blobs and external
head/run/attempt. This detects inconsistent/tampered receipts; it cannot make a
malicious producer into an independent witness. No GITHUB_ACTIONS, GITHUB_SHA or
RUNNER_ENVIRONMENT substitution is used.

## Additional evidence mutation regressions

Two independent mutations of the new receipt were reproduced before correction:
rehashed JSONL with duplicate outcome FAIL/PASS keys, and rehashed JUnit with hidden
PHYSICAL_PASS testcase text. The previous checks accepted both. Canonical JSONL rows
and rejection of structural XML text now refuse both, even after manifest rehash.
These are consistency checks, never proof of an honest producer or physical authority.
The child environment is explicit LOCALAPPDATA/SystemRoot/WINDIR only; no CI credentials inherited.

## P0/P1/P2 and G0/G1 verdict

| Priority | Remaining condition | Verdict |
|---|---|---|
|P0|Physical source/principal/ancestor/PGDATA custody, effective ACL/token facts and independent witnesses incomplete|BLOCKED|
|P0|Owner authorization trust distribution and durable external replay/rollback anchor unimplemented|BLOCKED|
|P0|Capability-free AppContainer blocks Grid loopback; safe transport containment policy unproved|BLOCKED|
|P1|Full controller crash/reboot recovery and bounded complete resource cleanup unproved|BLOCKED|
|P1|Read-only DB/role inventory lacks confirmed trusted credentials; no installed DB queried/adopted|BLOCKED|
|P1|Native prototype compilation and hosted execution require actual exact-head receipts|Pending CI; never inherited from baseline|
|P2|FastAPI on_event deprecation warnings in offline tests|Open maintenance issue; four warnings|

Read-only G0 metadata is not host attestation. Existing PostgreSQL wildcard listeners
and services belong to existing installations, never this disposable run. Unknown
process CommandLine/account/ACL states cannot establish absence or isolation.
The proposed G1 keeps unique run-bound directories/ports, separate future PG18
instance and owner/app/read-only credentials, synthetic data only, and **DENY PC4
PostgreSQL access on every port**. No installed database/service becomes a test resource.
Mutation argv remains null for all 20 phases; cleanup remains RETAIN/BLOCKED.

**G0 verdict: BLOCKED. PHYSICAL_G1_AUTHORIZATION_RECOMMENDATION: BLOCKED.**
Do not request authorization to execute an incomplete controller. Next safe steps
are exact-head hosted verification, independent artifact acceptance, completing
read-only custody evidence, and designing contained transport/external trust anchors.
