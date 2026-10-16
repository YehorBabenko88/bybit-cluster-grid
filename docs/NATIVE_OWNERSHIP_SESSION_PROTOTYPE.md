# Native ownership session prototype: scope, audit and assurance

Task: PR194 comment6218595348. Base8bb58f56cf42c87a0325c7b00d1c5fc8eaaa63b8.
This prototype is SYNTHETIC_ONLY. Every report has status BLOCKED and
execution_authorized=false / physical_ready=false, even when synthetic_result=PASS.
It is not connected to schema2, PGDATA mapping, the adapter, staging or a runtime.

## Code paths and lifetime

- installer/ownership_session.py: in-process session, bounded expected synthetic
  tree, model provider, immutable identity/ACL snapshots and borrowed read view.
- installer/ownership_native_fixture.py: ctypes Win32 bindings plus a factory for
  a NEW GUID test tree on explicit hosted Windows CI. Import does not load Win32
  APIs or create resources. There is no caller-supplied root/path option.
- installer/tests/ownership_session_driver.py: fixed10-case fixture-only driver;
  model is default. No plugin, external callback, arbitrary path or JSON proof CLI.
- installer/tests/test-ownership-session-prototype.ps1: explicit test launcher.
  PS5.1/7 launch trusted Python once. Verification, retained handles and callback
  live in that single Python process; no handle/capability crosses processes.
  This is NOT an in-process PowerShell native bridge or production runtime API.

The session takes a trusted test provider/callback and optional injected race hook.
It acquires a non-reentrant in-process guard, then fixture release/preparation
mutexes in that order. It opens every expected directory/file and retains those
same handles through validation, bounded callback reads and post-callback checks.
The view allows only fixed relative fixture filenames. Reads verify before and
after returning bytes. Cross-thread access and re-entrant reads/session attempts
poison the session, even if the callback catches the error. Only synchronous
same-thread consumers are supported. Callback return values are discarded.

The view is invalidated BEFORE handles close. Captured views cannot read after
return, including after a later successful session. Cleanup reverses acquisition,
drains registered leftover probe/file and mutex resources once after a failure,
and preserves uncertainty as BLOCKED even if a retry succeeds. Failed mutex
release/close keeps the registry entry and released-state for a safe bounded retry.
No retry double-releases a mutex. Callback exceptions and cancellation unwind
resources; reports use fixed codes, never exception text or callback results.
These are trusted Python test callbacks, not a sandbox against Python introspection
or a privileged caller. The provider is also trusted code, never JSON evidence.

## Restricted native fixture policy

new_native_fixture() first requires explicit GRID_OWNERSHIP_NATIVE_FIXTURES=1,
Windows, GITHUB_ACTIONS=true, RUNNER_ENVIRONMENT=github-hosted, RUNNER_OS=Windows,
CI=true and the expected repository. Missing policy markers fail BEFORE native API
loading or fixture creation. The parent is RUNNER_TEMP, absolute and non-UNC.
It creates an atomic new tempfile GUID directory, then only fixed child names and
new exclusive files, never adopts an existing root. Environment flags are a CI
execution policy, NOT cryptographic machine attestation or a production guard.

Only the newly created fixture objects receive protected owner/SYSTEM/Admin DACLs.
The default owner SID comes from the CI process token, not operator input or an
installed Grid identity. No privileges are enabled. No existing directory/ACL,
GridLab root, PostgreSQL, Windows task/service or production WAL is accessed.
Negative mutations modify only this fresh fixture. No recursive cleanup/deletion
operation exists; the disposable runner owns eventual fixture disposal. Atomic
replacement tests replace only the fixture's own newly created synthetic file.
Ordinary write/rename attempts while pinned must fail without altering the tree.

The fixed synthetic files deliberately contain no real adapter plan/PGDATA and
cannot be activated. They model the file/directory shape, not adapter provenance.
The journal uses an unmistakably synthetic constant hash. Existing exact adapter
byte-contract tests and their mandatory BLOCKED outcomes remain unchanged.

## Win32 API audit

Bindings use explicit ctypes argtypes/restype, System32 DLL loading and no compiler,
Add-Type, subprocess or fallback in the native backend. HANDLE width follows the
process ABI; DWORD fields are checked via the 52-byte BY_HANDLE_FILE_INFORMATION.
CreateFileW uses GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING,
FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT and no inherited handle.
Read/write/delete sharing conflicts block; the final reparse object is inspected.
Directory handles need BACKUP_SEMANTICS. These flags do not freeze ACLs, ancestors
or all metadata. See [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).

GetFileInformationByHandle supplies volume serial, file ID, attributes, link count,
size and last-write stamp. All objects must retain initial IDs on one volume,
correct type and link count1, with no reparse attribute. The current name is
reopened and compared with the held identity; file bytes are read from the held
handle, not the reopened path. Errors/unknown IDs block. See
[GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle).

Directory membership is enumerated through retained directory handles using
GetFileInformationByHandleEx FileIdBothDirectoryRestartInfo then
FileIdBothDirectoryInfo. Only ERROR_NO_MORE_FILES ends enumeration; unsupported
APIs/errors, oversized pages, invalid offsets/UTF16, aliases or extra members block.
No path-based scandir follows a replaced directory. The bounded parser follows
FILE_ID_BOTH_DIR_INFO offsets/alignment and is tested with corrupted buffers.
See [API](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)
and [record layout](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_both_dir_info).

GetSecurityInfo reads owner/DACL by the retained handle. Its DWORD error semantics
differ from Boolean file APIs. Null, unprotected/inherited, noncanonical, unknown
ACE/rights and foreign write/delete/WRITE_DAC/WRITE_OWNER/generic-write/all grants
block. Native allocations are freed with checked LocalFree; descriptors/pointers
never escape. ACL comparisons include owner, protection and exact ordered ACEs.
See [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo).

Native mutexes are Local\\GridOwnershipPrototype_<uniqueGUID>_release/preparation,
NEVER the installed Grid Global mutex names. WaitForSingleObject is nonblocking.
Timeout/error blocks; WAIT_ABANDONED also blocks and granted ownership is released.
Close/release failure remains uncertain and cannot become PASS. The model tests
unsupported API errors and forced failures; real kernel failures cannot be safely
manufactured on a user PC. See
[WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject).

## Tests and coverage boundaries

Model tests force replacement, reparse, hardlink, ACL, byte mutation, extra tree
members and handle closure at acquisition, verification, pre-consumer, pre-read,
post-read and post-consumer boundaries. They cover partial/retired/foreign/torn/
duplicate journals, unsupported operations, mutex contention, read/session reentry,
expired and cross-thread views, callback exception/cancellation, generic rights,
cleanup uncertainty and sanitized errors. These exercise actual session transitions
and callbacks rather than accepting more serialized assertions.

The opt-in native CI suite requires ALL17 tests, zero skips, on Python3.11/3.12:
held identities/volume and view expiry; write/rename denial while pinned; pre-session
replacement/hardlink/ACL/extra member; ACL mutation after verification; callback
exception; five partial/invalid journals; premature handle closure; contention of
each fixture mutex held by another thread. Both PS5.1/7 run the fixture driver.
Finished-bundle PS5.1 runs the driver with bundled Python and native backend.
Locally ONLY model/byte/static tests run; native fixtures are intentionally skipped.

## Remaining blockers and non-claims

1. This is a fresh-fixture lifetime feasibility prototype, NOT ownership of an
   existing adapter directory. No schema2 or production consumer is enabled.
2. The fixture parent/whole ancestor namespace is not a production pinned chain;
   mapped-drive/short-name/volume-GUID provenance and all stream/extended-resource
   handling require further review before any real target could be accepted.
3. Sharing flags and repeated snapshots do not make ACL/namespace changes atomic.
   A privileged writer can change and restore metadata between checks (ABA).
   Those adversaries, filter drivers, mount changes and malicious same-process
   code are NOT excluded. The prototype must not be promoted on green CI alone.
4. Real junction/reparse races and all failed Win32 return paths are tested through
   the model, not certified by actual adversarial native fixtures. Passing model
   tests do not prove actual kernel behavior. Protected ACL policy for an approved
   real host and atomic consumer membership remain unproven.
5. ctypes/PS launcher compatibility is tested on CI Windows/Python versions only.
   No direct PowerShell P/Invoke API, signed production bridge, target provenance,
   authentication protocol, installer integration or deployment readiness exists.
6. Cleanup uncertainty leaves the provider poisoned. The prototype never deletes
   data, repairs installed ACLs or restarts a service to hide a failed check.

Rollback is a reviewed source revert; there is no installed state or migration to
undo. Do not activate or clean a real target in response to prototype results.
Exact final SHA, workflow IDs and test counts are recorded in the Draft PR body.

Adversarial follow-up and lifecycle fixes:
[NATIVE_OWNERSHIP_ADVERSARIAL_AUDIT.md](NATIVE_OWNERSHIP_ADVERSARIAL_AUDIT.md).
Its tested kernel observations and explicitly unproven/ABA outcomes must be kept
separate; no schema2 or production ownership capability is enabled.
