# Native Ownership Verifier: adversarial audit and limitations

TaskPR195 comment6219305936; exact base5d01b1277ebb4854f772aa48101f454fc0166202.
This is fixture-only research. No schema2, Grid ownership mapping or execution
permission is introduced. Every report remains BLOCKED / SYNTHETIC_ONLY with both
authorization flags false. No target path API or production installer change.

## Reproduced defects and fixes

| Finding | Reproducer before fix | Minimal correction |
| --- | --- | --- |
| P2: raw file handle lost when registry append/Handle allocation fails | test_file_registration_failure_closes_raw_handle_before_propagating | Close the acquired raw handle on registration failure; poison provider |
| P2: acquired mutex lost when registry or lock-stack registration fails | test_mutex_registration_failure_releases_and_closes_raw_mutex (dict/stack) | Release/close on abort, remove partial record; preserve cleanup uncertainty |
| P2: pre-existing handles adopted/closed by a new session | test_session_refuses_to_adopt_or_close_preexisting_handles | Reject nonempty starting scope without touching its resources |
| P2: expired view poisons a later valid session (also cross-thread) | test_expired_view_close_cannot_poison_a_later_session and cross-thread variant | Session-specific lifetime poison token, invalidated before cleanup; stale tokens cannot poison future epochs |
| Defensive hardening: ACE/SID parsing could inspect SID data beyond the declared ACE | test_ace_sid_bytes_are_bounded_before_decoding | Bound GetAce pointer and size inside the ACL, copy bytes, validate exact ACE/SID lengths before decoding; no native SID traversal beyond ACE |

Independent review also found an evidence false-positive: an ACL helper error
could be counted as an attack rejected by the verifier. Tests now require a valid
baseline, successful mutation and expected rejection cause/no returned data. The
JUnit verifier requires case-specific observed outcomes, not merely uppercase
claims or empty properties.

The listed lifecycle regressions failed on the base behavior, then passed after
fixes. Cleanup now drains session-owned file/probe handles BEFORE mutex release.
Fixed-code diagnostics and current re-entry/poisoning behavior are preserved.
Failures never enable ownership or silently repair an ACL/installed resource.

## Focused native/ABI review

Read/open flags remain GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING,
BACKUP_SEMANTICS|OPEN_REPARSE_POINT. Normal data writes and delete/rename conflicts
are excluded by sharing, but metadata/ACL changes are not thereby atomic.
GetFileInformationByHandle still collects volume serial/file IDs, type/link count
and last-write state by held handle; current names are reopened and compared.
Directory membership uses the same held directory handles with the bounded
FILE_ID_BOTH_DIR_INFO parser. Unsupported or failed APIs block without fallback.

GetSecurityInfo owner/DACL allocations remain checked and freed. ACE pointers and
sizes must fit the reported ACL bytes-in-use and declared ACL size. Supported
allow/deny ACEs must contain a revision1 SID with at most15 subauthorities and
exact length; copying before decoding avoids reading beyond a declared ACE.
Null/unprotected/inherited/noncanonical ACLs, unsupported ACEs/rights and foreign
write/WRITE_DAC/WRITE_OWNER/generic grants block. This is conservative inspection,
not an effective-access theorem for arbitrary Windows tokens/filesystems.

Native mutex names remain fixture GUID Local names, never production Global
mutexes. Abandoned ownership is released and treated as BLOCKED. Registration
abort, close/release failures, nested cleanup order, view expiry/cross-thread use
and callback poisoning have deterministic regressions. A failed OS cleanup cannot
be certified successful; uncertainty is retained even after a bounded retry.

## Real CI attack surface (17 named cases per Python version)

All native actions require the existing hosted-CI opt-in and fresh GUID factory.
Helpers accept a fixture object, never an arbitrary root or junction target.

- A real mount-point junction uses FSCTL_SET_REPARSE_POINT between fixed empty
  directories inside the SAME fixture. Pre-session creation must block the
  consumer. Creation while pinned is either denied by the kernel or detected
  before any borrowed read can return; results distinguish these outcomes.
- Rename attempts target the owned fixture root or its owned data/postgres
  ancestors while their handles remain pinned. No RUNNER_TEMP/drive/foreign
  ancestor is renamed. Denial and detection are recorded separately.
- A protected DACL gains a foreign generic-write ACE during callback. Reads must
  block. The ABA experiment restores the original DACL before the next read and
  explicitly records whether the transient change escaped snapshots.
- A hardlink race attempts a new link only inside the same fixture. Creation and
  subsequent blocking are distinguished from an actual sharing denial.
- A second thread holds an unexpected, atomically CREATE_NEW marker during a
  borrowed read. DELETE_ON_CLOSE removes only that newly created marker, never a
  pre-existing file; there is no recursive cleanup. Namespace changes must block.
- Four real opened handles exercise a bounded quota failure and full cleanup.
  Global OS handle exhaustion is deliberately NOT attempted and is reported
  BLOCKED_UNPROVEN, never inferred from the quota test.
- Injected close/release failures surround REAL fixture handles, proving registry
  drainage, not claiming a naturally occurring kernel failure was reproduced.
- A test thread exits owning our GUID mutex while a known anchor handle keeps it
  alive. The session must observe abandoned state, release its acquired ownership,
  and refuse the consumer. Other threads'/processes' mutexes are never altered.
- Expired native views cannot poison a new session. Real acquired handles/mutexes
  are closed when controlled registry allocation failures abort their adoption.

## Explicit CI evidence accounting

The previous17 native tests remain mandatory, zero skips, under Python3.11/3.12.
Existing PS5.1/7 native launchers and bundled-Python tests remain unchanged.
The new adversarial suite enumerates exactly17 additional test identities. Its
JUnit verifier rejects failure/error, missing/duplicate/unknown cases and silent
skips. Only the two privilege-dependent junction cases and the forbidden global
exhaustion case may be BLOCKED_UNPROVEN with an explicit marker. Those are NOT
counted as tested kernel passes. All tested/unproven outcomes and observed ABA
limits are exported as sanitized JSON/JUnit artifacts tied to exact commit SHA.

Local runs perform ONLY model/parser/policy/static checks; native modules import
inertly and all real attack tests skip without explicit CI policy. No fake CI
markers or local native calls are used to obtain green tests. A privilege-blocked
junction test has deterministic reparse model coverage from the prior prototype,
which does NOT substitute for an unexecuted real attack.

## ABA and residual blockers

The deterministic model demonstrates that ACL replace/restore between snapshots
can yield synthetic PASS while status remains BLOCKED. Native CI records the
actual outcome; green assertions for that measurement are NOT a claim that ABA
was excluded. Sharing locks do not freeze DACL state or all namespace metadata.
An administrator, kernel/filter driver, mount change or malicious same-process
Python code is outside the present guarantee. Repeated before/after snapshots
cannot prove that nothing transient happened between them.

Fixture-root pinning does not authenticate the whole ancestor chain, arbitrary
existing directories, aliases or deployed adapter plans. No production provenance,
atomic consumer capability, direct PowerShell native bridge or effective target
ACL policy has been established. The Win32 volume/file-ID representation is
observed in these fixtures, not a universal cross-filesystem identity guarantee.
Heap-wide/global handle exhaustion, process kill and every kernel error cannot
be safely manufactured here; tests separate injected failures from kernel facts.

The callback/provider are trusted test code, not a sandbox against reflection,
raw-handle tampering or introspection. The session API exposes only borrowed read
operations, invalidates them before returning and keeps ownership BLOCKED.
No positive authorization may be based on this prototype's green CI.

Rollback is a reviewed source revert. No production state/schema/service/release
changes exist to undo; no automatic data cleanup or migration rollback is needed.
Exact final SHA, workflow IDs, tested/unproven counts and observed kernel outcomes
are maintained in the Draft PR evidence report.

API references used in the focused audit:
[FSCTL_SET_REPARSE_POINT](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_set_reparse_point),
[REPARSE_DATA_BUFFER](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_reparse_data_buffer),
[GetAce](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getace).
Junction privilege availability is measured in CI; no privileges are enabled or
policy bypassed to manufacture a successful attack.
