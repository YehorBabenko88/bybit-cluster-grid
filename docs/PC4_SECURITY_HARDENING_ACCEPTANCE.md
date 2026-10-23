# PC4 SID/ACL hardening — offline acceptance only

Reviewed PR234: `a55b6025c1f2d18d234d0f69348e2b0d55857358`.
Compatible base: `b0d31eaaa2221da357ef6127fca3f0207c4248e2` on
`audit/codex-pc4-sid-acl-20261021`. Its two additional LSA commits were inspected
and retained by rebasing only the new audit branch. No base/PR234 edits or merge.
This AI review is not independent human or physical acceptance.

## Findings and fixes

| Priority | File / cause | Reproducer and expected result | Remedy / evidence |
|---|---|---|---|
| P1 | TokenFacts.cs: count bounded but array/SID pointers not bounded by returned buffer | A count of one with a truncated array or out-of-buffer SID must reject before dereference. Original parser lacks these checks. | Carry actual returned length, validate array size/alignment offsets, SID header/revision/count/length/pointer ranges, privilege bounds, mandatory-label authority and elevation values. 24 owned-memory cases on PS5.1/7; no host tokens read. |
| P1 | TokenFacts.cs: effective admin membership is not non-admin provenance | Enabled && not deny-only correctly computes effective Administrators membership. But a deny-only/disabled Administrators entry must not turn a filtered admin into ordinary-user evidence. | Keep correct effective-group calculation; native collection additionally rejects any Administrators SID presence. Tests separately exercise enabled, disabled, deny-only and both flags. Independent account/group provenance remains physically unverified. |
| P1 | Invoke-Pc4SidAcl.ps1: Cleanup throw occurred after host/ACL/identity observations; unreachable deletion remained | Cleanup invocation must stop before MachineName, ACLs, credentials, native load or path traversal. | Immutable early CLEANUP_NOT_AUTHORIZED; remove path-based deletion entirely. Execute and direct Actor also immutable NOT_AUTHORIZED. No approval switch can bypass these. |
| P1 | Controller lifecycle: PID reopening and best-effort shutdown swallowed uncertainty | Mock launch failure, wait fault/timeout, wrong identity, missing process and PID replacement must not become success. | Retain original Process.Handle; parent token read uses that handle; ready handshake binds run/role/PID/start time. Record launch intent and unknown launch outcome. Cooperative signal + bounded wait on original object; monotonic ready/go deadlines resist wall-clock rollback; no PID lookup or kill. Unknown exit, nonzero exit and signal errors block completion. Completion/hashes follow shutdown evidence. |
| P1 acceptance | PR234 branch skipped PC4-specific CI, despite other green workflows | A green unrelated workflow cannot prove TokenFacts or lifecycle coverage. | Own branch explicitly enters existing safe PC4 matrix. Inherited infrastructure jobs explicitly exclude it. Strict frozen 58-case hardening inventory, separate JUnit/events, exact HEAD/run/attempt and SHA256 receipts. |
| P2 | Isolated JSONL checking did not bind JUnit, run/head, shutdown and file index | Rehashed replayed/malformed data, wrong SHA/SID, fake PASS, duplicate keys, unknown paths, XML entities, skip/failure and contradictory authorization flags must BLOCK. | New pure `installer/pc4_security_bundle.py` binds the bundle using externally supplied expected values. OFFLINE_FORMAT_PASS always has host_verified/physical_attestation/execute/cleanup false. Hashes authenticate consistency, not the producer or physical machine. |

The former blanket package-pin test conflicts with the explicit hardening task:
four reviewed files (TokenFacts, controller, Actor, package builder) necessarily
change. Its replacement checks the other original files against the same pinned
baseline. Common.ps1, original pure policy tests and the historical physical
runbook remain byte-identical (modulo Git line endings). LSA native collector,
rights model, users, ACLs and services are unchanged.

## Cleanup design and proof obligations — NOT IMPLEMENTED / NOT AUTHORIZED

No deletion API is exposed by this change. `cleanup_plan` is only an offline
model; even all positive inputs return BLOCKED. Synthetic booleans are not host
observations. Required future implementation/review:

1. Independently authenticate run/package/source/manifest receipts and operator
   authorization. Existing directory names, GUIDs and marker files are not proof.
2. Open/pin the entire volume-to-fixture ancestor chain and retain stable volume
   and file identities, never infer custody from a canonical path string.
3. Open children relative to retained parent handles with no reparse traversal;
   reject junctions, mount points, symlinks, hardlink counts other than one,
   unexpected children, identity changes and cross-volume mappings.
4. Prove sharing/custody rules prevent rename, link creation and parent/file ABA
   during validation and deletion. Merely opening a directory does not prove it.
5. Retain the original child process handles and establish termination. PID
   absence/reuse is insufficient. Unknown launch outcome is a permanent block
   until independently resolved. Never kill an uncertain PID.
6. Delete only the exact opened, authorized child object using a reviewed native
   handle-relative operation; never recurse, truncate a file, repair ACLs or
   fall back to Remove-Item. Revalidate identities/link state on the held handles.
7. Commit a crash-resumable receipt before/after each operation, preserve evidence,
   and stop on every unknown/error. Repeated recovery must not adopt new objects.

These Win32/NT sharing, deletion and identity guarantees require separate
adversarial disposable-Windows tests and human review. An administrator can
override local custody; do not promise resistance in the same trust domain.
No current schema, approval boolean or positive model result enables Cleanup.

## Lifecycle limits

`Lifecycle.ps1` is tested through mock Process objects only (10 cases on each
PowerShell). Its identity assumption is the retained object supplied by the
controller; actual CreateProcess/token/custody races are NOT physically proven.
No privileged token is accepted as ordinary-user evidence. No test process was
launched under real user credentials; no account was enabled or modified.
Controller/Actor early throws keep the future flow unreachable pending a new
explicitly reviewed activation change. The old physical runbook is therefore
not executable guidance for this candidate.

## Offline reproduction and CI evidence

Safe commands in the repository (no physical modes):

```powershell
python -m pytest tests/test_pc4_security_bundle.py tests/test_pc4_hardening_acceptance.py lab/pc4/test_failclosed_hardening.py
powershell.exe -NoProfile -NonInteractive -File lab/pc4/Test-TokenBuffers.ps1
pwsh -NoProfile -NonInteractive -File lab/pc4/Test-TokenBuffers.ps1
powershell.exe -NoProfile -NonInteractive -File lab/pc4/Test-Lifecycle.ps1
pwsh -NoProfile -NonInteractive -File lab/pc4/Test-Lifecycle.ps1
```

Token tests compile C# and operate on owned synthetic memory, never call Read,
OpenProcess, GetTokenInformation or observe host tokens. Lifecycle tests create
only mock objects, no child processes. Existing pure policy39 and LSA mock
30+8+PlanOnly1 gates remain. Existing Python inventory464 and separate LSA source4
remain mandatory, alongside hardening58: 526 Python cases per matrix cell.
CI is Windows/Ubuntu × Python3.11/3.12. Windows parses scripts and runs synthetic
tests under PS5.1/7, compiles a disabled offline package and checks each package
file SHA256 against manifest/source HEAD. No package is installed or executed.

Run-specific SHA, Actions IDs, package manifest/DLL and receipt SHA256 belong in
the final PR evidence comment, after all exact-head jobs actually terminate.
Unrelated SKIPPED jobs are not PASS. No previous PR's green result transfers.

| Gate | Status |
|---|---|
| Pure group parsing / buffer and evidence model | PASS only on exact-head CI evidence |
| Compatible base / source scope | PASS after pinned-source and regression checks |
| Real child token and process-identity proof | BLOCKED; NOT_RUN |
| Handle-relative deletion / crash recovery proof | BLOCKED; implementation absent |
| Physical SID/ACL | **0/10 NOT_RUN** |
| Execute | **NOT_AUTHORIZED** |
| Cleanup | **NOT_AUTHORIZED** |
| Deployment | **NO-GO** |

Rollback is repository-only: abandon/revert this audit branch. No infrastructure
was changed, so there is no host rollback, cleanup or account operation to run.
