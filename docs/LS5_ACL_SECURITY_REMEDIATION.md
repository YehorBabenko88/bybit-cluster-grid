# LS5 ACL remediation: containment model and operator recovery design

## Decision and scope

**Physical PC4 SID/ACL 0/10 NOT_RUN. Execute NOT_AUTHORIZED. Cleanup NOT_AUTHORIZED. Deployment NO-GO.**
Synthetic PASS is not Physical PASS. No LS5/PC4 connection, host inspection, account change, task activation, SQL, service or physical ACL operation is part of this change.

Base: PR #236, `a7e695d8a937a19e28cebe48668f9927cf2fd9b1`; main inspected at `d537d525296ef34f727996e240ae6c60102c6082`. PR #232 is a separate onboarding design; this change does not amend it. Existing PRs remain untouched. This branch deliberately reuses existing release Runtime Guard, mutex and prepared/committed file transactions. It does not replace their protocols.

The deliverable is a reproducible **offline containment/preparation contract**, early execution blocks, hosted-CI-only GUID ACL layout tests and a physical remediation design. **There is no authorized native ACL Apply or rollback executor.** The remaining P0 host exposure is not fixed merely by merging code. Building a safe native executor requires a separately reviewed handle-based custody protocol and human authorization. Path-based Get-Acl/Set-Acl checks cannot establish TOCTOU safety against concurrent directory replacement, pre-existing write handles or a privileged administrator.

## Root cause, pinned to the base source

Links and line numbers below refer to the unmodified base, not the shifted lines in this PR:

- [`bootstrap.ps1:24`](https://github.com/YehorBabenko88/bybit-cluster-grid/blob/a7e695d8a937a19e28cebe48668f9927cf2fd9b1/installer/bootstrap.ps1#L24) creates Program Files/Data/runtime/log directories with inherited DACL before any secure boundary is established. Archive extraction at line 58, release publication at 62-64, Python copy at 80-89 and venv creation at 112 use that unverified trust boundary. The late `.env` restriction at 245 neither verifies directory custody nor removes unrelated explicit ACEs. These mechanisms explain persistence of inherited directory-write permissions; installation logs would be needed to prove the exact historical execution sequence on LS5.
- [`install.ps1:45`](https://github.com/YehorBabenko88/bybit-cluster-grid/blob/a7e695d8a937a19e28cebe48668f9927cf2fd9b1/installer/install.ps1#L45) creates installer with ordinary inheritance, then copies scripts and writes launchers. SYSTEM/Highest principal at 73 and registration at 116/119 make writable executable inputs a privilege boundary. The preflight Python invocation already occurs before full code/runtime ACL verification. Disabled tasks reduce current exposure but do not make those inputs trusted.
- [`protect-service.ps1:6`](https://github.com/YehorBabenko88/bybit-cluster-grid/blob/a7e695d8a937a19e28cebe48668f9927cf2fd9b1/installer/protect-service.ps1#L6) creates the same inheriting directory; lines 9-10 change service recovery. Lines 14-15 use localized principal names and a broad RX grant without checking native exit codes, preserving other explicit grants. Only DataRoot is targeted; Program Files and the full interpreter/import closure remain unchecked. Bootstrap does not invoke this helper.
- `bootstrap-ml.ps1` creates runtime/ML venv without a protected custody boundary. `stage-github-release.ps1` creates staging/download paths without one. These write paths are now blocked before first side effect. Bootstrap, ML bootstrap and the retired protect-service helper default to PlanOnly; install keeps its existing PlanOnly default. Download explicitly refuses. No old unsafe Apply body can be reached through the new flags.
- Release switch/recovery/rollback already validate manifests and reparse paths and hold their mutex around atomic journal/pointer updates. Their existing Runtime Guard stops running tasks/Python before the first transaction write. **None of these checks establishes owner/DACL/ancestor handle custody.** Those scripts remain unchanged to preserve recovery compatibility, and must not be used for physical remediation before the additional gate is satisfied.

The reported active launcher hash is `F1A1A49C22F71CF5A65BEB3D8512C088805C39AFC96633D93A852F7A360111F6`. It is a baseline equality check, not proof of publisher authenticity or absence of compromise. Six releases and active `9ab1f5b85ec471ea21ec89f1b76740c0b01537b6` are required in this LS5-specific snapshot version; any changed inventory requires explicit model review.

## ACL matrix: supplied observations versus proposed policy

Use SID values, never localized names. The currently reported task identity is SYSTEM (`S-1-5-18`); Administrators is `S-1-5-32-544`; Users is `S-1-5-32-545`. A future service SID must be independently resolved and approved; it is not inferred from a username. Unknown principal, group membership, explicit deny/callback ACE or incomplete object inventory is BLOCKED.

| Scope | Before (owner-supplied facts) | Proposed protected policy | Physical status |
|---|---|---|---|
| ProgramData/Grid and Program Files/Grid boundaries | Inherited Users directory writes; active release also writable | SYSTEM + Administrators Full; inheritance protected; no Users grant; additional approved service RX only | BLOCKED |
| installer, runtime/venv/Scripts, all release/code trees, launchers, version pointer | Writable parent directories despite some RX files | SYSTEM + Administrators Full; approved non-SYSTEM service RX; explicit canonical protected DACL on existing descendants | BLOCKED |
| `.env` / secret configuration | Users read; DSN/Telegram credentials potentially disclosed | SYSTEM + Administrators Full; approved non-SYSTEM service Read only; no Users read; protected backups/evidence | BLOCKED; credential rotation required separately |
| spool, logs, backups | Inherited Users directory write | SYSTEM + Administrators Full; approved service Modify only within approved data scope | BLOCKED; preserve WAL and existing data |
| deploy, ml-artifacts, packages, DLL/import inputs | Writable, may feed code/deserialization | Treat as executable inputs, service RX; writer exception requires a new safe consumption contract | BLOCKED |
| C:\ProgramData and C:\Program Files | Ancestor permissions reported/incomplete | Inspect custody and DELETE_CHILD semantics; **never modify these system directories** | BLOCKED if containment impossible |
| Other accounts/tasks/services | grid_pg_test / PowerGridForecastTask purpose unknown | No mutation, no ownership assumptions; resolve impact with owner before approval | BLOCKED |

Profiles differ for non-SYSTEM service identities; SYSTEM inherently has Full in this model. This is not a claim of least privilege for SYSTEM. Do not elevate another app/service account to owner/admin, remove an unclassified service grant, or let a data writer replace executable inputs. Actual required data rights and group memberships need operator confirmation.

## Snapshot/journal boundary

`python -m installer.ls5_acl_remediation` and `installer/ls5-acl-remediation.ps1` default to PlanOnly/BLOCKED. Python optionally reads **a synthetic JSON file only** with `--snapshot <file> --expected-head <40-hex>`. It never queries a host, invokes PowerShell/native APIs or writes a snapshot/journal to disk. Invalid JSON, duplicate keys, uncertain identity, missing mandatory paths, wrong file kinds, unknown ACLs, source changes or unsafe links cannot produce PASS. The default PowerShell wrapper has no host provider calls; Apply and Rollback unconditionally refuse.

A complete synthetic input may produce `OFFLINE_MODEL_PASS`, always `host_verified=false` and all authority flags false. Evidence assertion booleans are untrusted model inputs. Opaque original SDDL strings are preserved for modelling; this Python code does **not** parse Windows security descriptors or bind SDDL to the separate ACE list. No physical ACL inference may be made from them. Directory link-count assertions likewise are model assumptions, not a native Windows directory identity implementation.

`prepare/advance` model ordered original-SDDL preservation and partial progress in memory. Advancement validates every immutable plan field, typed cursor/state and false authority flags against the regenerated plan, including its committed shortcut. `COMMITTED_MODEL_ONLY` does not mean ACLs changed. There is no durable transaction storage, trusted anti-rollback or write receipt. Recovery always BLOCKED, even if snapshot hashes match; restoring an originally vulnerable DACL can reopen a P0.

## Required physical remediation sequence - NOT AUTHORIZED

The following is an operator design, not an instruction to run on LS5 now. Do not run bootstrap, installer, release switch, ACL apply, rollback, coordinator or physical harness from this branch.

| Gate | Future evidence / STOP rule | Current result |
|---|---|---|
| R0 Authorization | Separate signed maintenance scope, operator identity, resources and STOP authority. Unknown account/task ownership unresolved -> STOP. | BLOCKED |
| R1 Protected observer | Independently protected source/toolchain, exact SHA and signature/hash closure. Do not execute Python/PowerShell modules from current writable Grid paths. | BLOCKED |
| R2 Quiescence | Read-only complete tasks/actions/principals, processes with full command lines/identities, open-handle and external writer model. Hold existing release mutex and independently prevent competing task/bootstrap/update starts for whole transaction. Failed inventory/cleanup -> STOP; no automatic restart. | BLOCKED |
| R3 Custody | Enumerate both Grid roots, ancestors and **every descendant of all six releases**, staging/.previous/.replaced/fallback paths, launcher targets, source, env, backups, interpreter/base Python, pyvenv.cfg, .pth/sitecustomize, site-packages, working directory and DLL search inputs. Resolve real SID, owner, DACL/ACE flags, effective group rights, file volume/ID, hardlink count, reparse tags and trusted source hashes. Unknown path, missing closure, parent delete/replace ability or existing untrusted handles -> STOP. | BLOCKED |
| R4 Preserve | Protected off-tree evidence and original full descriptor/identity/hash inventory. Avoid recording env contents/credentials; privileged encrypted backup policy required. Preserve WAL/data. Validate restore identities without overwriting data. | BLOCKED |
| R5 Native transaction | Separately reviewed handle-based, no-reparse acquisition from trusted ancestors, stable identity and exclusive replacement protection; verify descriptor by handle immediately before/after write. Journal prepared/committed with recoverable per-object receipts in protected custody. No automatic take-ownership, inherited-global reset or modification outside allowlisted Grid objects. | BLOCKED; executor absent |
| R6 Rebuild / secret response | ACL restriction does not clean poisoned modules/DLLs or revoke existing handles. Reconstruct executable closure from independently trusted artifacts in a newly protected root; retain original evidence. Owner separately authorizes credential revocation/rotation (PostgreSQL DSN and Telegram), without credential arguments/logs/artifacts or automatic Telegram activation. | BLOCKED |
| R7 Verify | Independent observer rechecks complete effective access, children/ancestors/reparse/identities and unrelated-resource invariants; token tests need their own separate authorization. Synthetic or hosted elevated-runner checks cannot approve this gate. | BLOCKED |
| R8 Activation | New explicit authorization, runtime/schema/collection/trading gates. Tasks remain disabled; no migration, trading, Telegram or deployment implicit in ACL work. | NO-GO |

Existing Runtime Guard must be rechecked directly before the first physical transaction write **while its existing release mutex is held**. The future ACL executor additionally requires whole-transaction native custody; a passing process scan is not equivalent. A snapshot digest detects model input changes only; it cannot close that race.

STOP on API/access errors, missing CommandLine, identity/PID reuse, active or unknown Grid task/process, other writer, reparse/junction/hardlink, source mismatch, descriptor drift, manifest uncertainty, role/account ambiguity, unclassified grant, evidence write failure, rollback failure or loss of exclusive custody. Do not fix STOP by disabling checks.

## Rollback / interrupted repair design

Leave all tasks disabled and retain data and journals. Capture pre-change descriptor including owner/group/DACL, and any required audit metadata only under explicit authorization. Each receipt must bind volume/file identity, exact original/post-write descriptor, ordered operation, run ID, source HEAD and trusted custodian. On partial failure do not continue to activation. Revalidate native handle identities, ancestors, currently installed descriptor and post-write hash against receipts. If anything changed, BLOCKED/manual forensic review; never recurse into substituted paths or restore to a replacement file.

Only separately approved per-object restoration is permissible. Restoring Users writes/readable secrets is **not an acceptable ready state**: leave execution blocked, document reopened exposure and choose containment/rebuild instead. No `icacls /reset`, system-root ACL change, automatic deletion, account disable/delete, unrelated task change, database rollback or secret export. `recover-release.ps1` recovers its release journal only; it is not an ACL rollback implementation. Old release activation would re-enter the same unsafe boundary and is not a remediation.

## Tests and evidence

- Frozen offline pytest inventory: `tests/fixtures/ls5_acl_inventory.json`; 130 tests, exact node IDs and JUnit names required. No skipped/xfail/errors/failures accepted.
- Python matrix: Ubuntu/Windows x 3.11/3.12. Exact PR head checkout; git blob vs working source comparison (line-ending normalization only); SHA256 source inventory. JSONL and JUnit bind exact HEAD, Actions run ID/attempt and false physical/authority flags.
- PowerShell 5.1/7 pure PlanOnly tests: 14 each; installer AST parse without execution. Locally safe command: `powershell.exe -NoProfile -File installer/tests/test-ls5-acl-compat.ps1` (or `pwsh`). These never observe LS5 ACLs/users/tasks.
- Hosted-CI structural ACL suite: 16 cases per shell; only new GUID fixture under RUNNER_TEMP with explicit repository/job/hosted-runner guards. Reproduces directory-only inherited writes, leaf RX ambiguity, env read, idempotence, new-release inheritance, fault-before-write, fixture-only SDDL roundtrip, junction/symlink/hardlink rejection and out-of-scope refusal. No users created, no ordinary-user tokens tested, no physical attestation, no cleanup. Path-based ACL operations here are fixture demonstrations **not a production executor or TOCTOU proof**. Missing symlink capability fails CI rather than skipping.
- Required CI aggregate rejects skipped/failed/missing matrix jobs. No inherited general CI gate is removed. New receipts include SHA256 for source and JUnit/JSONL, verified independently after download. JUnit alone is not a cryptographic signature; repository/runner/workflow compromise is outside this model.
- Independent review found required-file-kind bypass and forged model journal authority; 13 RED regression cases reproduced before minimal fixes. Follow-up review required expected error codes in native negative cases so unrelated provider errors cannot count as PASS. Full native host guarantees remain unproven.

## Remaining severity and acceptance

**P0 open on LS5:** supplied code/runtime/ancestor write exposure and env read exposure. Disabled tasks are containment only; host not inspected or repaired. Secret disclosure cannot be undone with ACLs.

**P1 BLOCKED:** native handle-custody/TOCTOU executor and durable recovery receipts; independent effective-token/parent DELETE_CHILD verification; trusted rebuild/interpreter closure; identity/purpose of grid_pg_test and PowerGridForecastTask; human maintenance/credential response authorization. No assumptions of exclusive ownership.

**P2:** future service/data-writer contract, authenticated evidence storage/retention and recovery operational rehearsal. These do not justify weakening P0/P1 gates.

Offline containment model/test readiness depends on exact-HEAD CI results reported in the PR. **Physical repair, Execute, Cleanup, Deployment: NO-GO.** This work does not promote L1/L2 or the PC4 physical harness.

### General CI compatibility follow-up

The first exact-HEAD run exposed a stale assertion demanding the PC4 skip conditions which PR236 deliberately removed, and a shallow checkout lacking the pinned historical PC4 tree. The regression now asserts hosted general CI remains enabled for those ten workflows; preflight fetches full history. The new ACL workflow preserves all earlier isolated planning/review branch exclusions.

Windows bundle previously invoked the production ML bootstrap and therefore failed after the new unconditional safety block. It now exercises the same retained dependency/lock/recovery algorithm through `installer/tests/invoke-ml-owned-ci.ps1`, exclusively in a newly minted hosted-runner GUID root. The helper refuses non-hosted/wrong-repository/wrong-job use, never creates/adopts an arbitrary root, verifies a run/attempt/HEAD ownership marker, and rejects reparse children. The runner/checkout are trusted CI inputs; this fixture is not an adversarial handle-custody executor and confers no production capability. Existing ML install/idempotence/truncated interpreter/missing pip/concurrent lock checks are retained; no production guard is relaxed.

The existing installer-Apply CI fixture now first asserts the real entry point rejects with the ACL error, then tests retained registration logic in a newly owned copy with all Scheduler providers mocked. Its hosted-only guard precedes identity/file operations. This does not enable production Apply or weaken the production refusal.

Final adversarial type checks reproduced and rejected eight additional model failures: SID subauthority overflow/noncanonical/Unicode forms, illegal/control Windows path characters, and nested bool/float aliases in journal flags. Canonical JSON digests now bind immutable nested journal values with their JSON types. These are offline model fixes, not native identity proof.
