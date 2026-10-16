# Ownership verifier architecture audit (revision 2, NOT ENABLED)

Task: PR193 comment6201691580. Base: 9a7b0735f0ea265854abbf3bfc6cc3c7b897ddf3.

## Outcome and scope

A complete native ownership verifier is NOT implemented. Schema2 remains disabled,
legacy schema1 remains BLOCKED and no native identity/ACL/session assertion is
accepted as authorization. A new pure byte-contract diagnostic is implemented as
an independently testable safe part. It never reads a target file, enumerates a
host, calls native code, invokes Add-Type, acquires a mutex or runs a callback.
It exports no PGDATA, file bytes, credentials or reusable ownership capability.

`Test-GridLabOwnershipBytes` takes ExpectedPlan, independently approved
ExpectedPlanSha256/ExpectedCommit, a dictionary of file byte arrays and an array
of relative directory names. These are caller-provided diagnostic inputs, NOT
locally authenticated evidence. The expected plan is reconstructed with the
existing New-GridLabPlan; exact ordered compact JSON must match before comparing
Get-GridLabFiles/Get-GridLabRecord UTF8 bytes. The hash is the adapter hash before
the plan_sha256 field, not Python sorted JSON or a hash of the final plan file.

Every result has status BLOCKED and execution_authorized/physical_ready false.
Byte-contract MATCHED_UNAUTHENTICATED only means that the supplied byte arrays
match. Missing/malformed intent, independent hash/commit mismatch, extra fields,
changed root/parent/role/run/node/ports, unknown keys, non-byte arrays, changed
files or directory sets reject. Files are capped at65536 bytes, owner.jsonl4096;
the exact five file/five directory set bounds total accepted input. Size checks
occur before byte comparison. A strict scalar/string-array shape check precedes parameter binding and serialization,
rejecting nested ScriptProperty getters and coercion methods. The helper does not deserialize JSON or infer
identity from timestamps. It is not wired into provisioning, staging or recovery.

## Existing interfaces inspected

| Interface | Actual scope | Why it cannot authorize PGDATA |
| --- | --- | --- |
| New-GridLabPlan | Lexical parent, run/node, role, commit, branch and ports; ordered hash | Does not authenticate disk, ACL, caller intent or files |
| Get-GridLabFiles | Expected plan/environment/PostgreSQL/task templates | A template is not a native object identity |
| Assert-GridLabOwned | Path-based journal/tree check, accepts partial and retired states | Reads can race; lacks retained handles, all-file hardlink and ACL checks |
| Assert-GridLabSingleLink | GetFileInformationByHandle on the open journal stream | Add-Type compilation; checks journal only, not every directory/file |
| Add-GridLabRecord | Same exclusive read/write stream for journal validate/append | Mutating retirement/preparation primitive, not a read-only mapping session |
| Invoke-GridLabPreparation | Existing release then task-preparation mutexes, explicit approval | Mutexes serialize cooperating Grid callers, not arbitrary filesystem writers |
| PostgreSQL read-only snapshot | Sanitized metadata and conservative ACL/volume checks | Path observations and serialized claims have no consumer lifetime |

These core functions remain unchanged. In particular do not tighten retirement
to COMMITTED-only: incomplete preparations need preserve-only retirement, not
adoption as a valid PGDATA. The new diagnostic demands ONLY exact PREPARED then
COMMITTED records for mapping bytes; PREPARED-only, either RETIRED sequence,
duplicates, reversed/foreign/torn records, BOM, CRLF or whitespace reject.

## Proposed native session, not an implemented API

A future trusted in-process function could have the conceptual form
`Use-GridLabOwnershipSession(approvedIntent, consumer)`. The verifier owns all
native handles; the consumer can use a private borrowed view only inside this
call. No JSON report, object with an ownership boolean or returned raw path is a
capability. Consumer use after callback return must be structurally impossible;
finally closes handles in reverse order and releases mutexes even when validation
or consumption throws. An arbitrary scriptblock is not a safe consumer API:
a consumer must itself be trusted, reviewed, read-only and unable to export a
live view. A later physical executor needs a separate design and authorization.
There is no consumer invocation or callback support in this patch.

The required sequence is:

1. Accept independently approved intent (including root/parent, run/node, role,
   commit, branch, ports, owner SID and hash), never a second PGDATA path. Rebuild
   the plan using existing canonicalization, compare exact bytes/hash. The sole
   candidate PGDATA is `<reconstructed Plan.root>\postgres\data`.
2. Acquire existing `Global\BybitClusterGridReleaseSwitch` then
   `Global\BybitClusterGridTaskPreparation`, nonblocking, and retain both through
   consumption. Busy/error blocks. Abandonment requires complete fresh validation;
   it is not evidence that a previous writer completed. No new lock namespace.
3. Open and retain identities for the dedicated root, relevant ancestors, every
   expected directory, journal and template. Open-existing only, read access,
   no handle inheritance and no write/delete sharing. Read evidence bytes through
   retained handles, not ReadAllText(path). A pre-existing conflicting writer,
   failed API, unsupported filesystem/identity or ambiguous access blocks.
4. Establish canonical drive/volume binding and parent-child relation. No UNC,
   mapped/SUBST/short-name/device aliases, reparse/junction, hardlinks or
   case-folded path substitution. OPEN_REPARSE_POINT on a final component does
   not prove ancestors are safe. Pinning a directory does not freeze child
   membership. Reopening the original name and comparing native identity is
   necessary but alone cannot make an arbitrary directory enumeration atomic.
5. Read owner/security descriptors by handle. Require protected canonical non-null
   DACL, approved owner and explicitly understood ACE types/rights; inherited,
   generic-write/all foreign writers, unknown generic bits or failed inspection
   block. Examine delete-child, WRITE_DAC/WRITE_OWNER and ancestor replacement
   rights, not only data-write. Do not silently repair ACLs or assume SYSTEM/admin
   exceptions form an adversarial security boundary. Existing Prepare does NOT
   establish the protected ACL needed by such a verifier.
6. Validate exact tree membership and bytes (including empty PGDATA), journal
   state and no extra streams/resources. Recheck every retained identity, link
   count, attributes, ACL, path relation, membership and journal after the last
   acquisition and immediately before consumption. Any change invalidates the
   whole session. If a stable membership/ACL model cannot be proved for the full
   consumer lifetime, remain BLOCKED rather than rely on a last-millisecond check.
7. Consume only while the same session/handles/mutexes remain valid, then invalidate
   the borrowed view and dispose. No reconnect/retry may reuse an old proof.

The adapter permits drive-letter case and safe Unicode parent components; a
future verifier must define physical-name canonicalization without silently
normalizing another root. Lexical GetFullPath, uppercase drives or case-insensitive
path equality alone cannot prove identity. The fixed ASCII regression plan has
one pinned hash on both PowerShell engines; this does not certify all Unicode or
cross-engine serialization cases. Exact mismatch must remain fail-closed.

## Native API and interop audit

No native bindings are introduced. A vetted prebuilt interop assembly verified
with the bundle could avoid read-only Add-Type compilation, but assembly loading,
dependencies and P/Invoke ABI need independent review. Reflection.Emit is another
in-memory option, not an ownership guarantee; do not add a fallback compiler.

For a future CreateFileW binding use correct unsigned access masks, Unicode,
OPEN_EXISTING and SafeHandle ownership. Directory handles need
FILE_FLAG_BACKUP_SEMANTICS; FILE_FLAG_OPEN_REPARSE_POINT opens the final reparse
object for inspection. FILE_SHARE_READ excludes write/delete sharing while the
handle is open. These flags do not freeze directory membership or make metadata
and ACL checks atomic. Do not enable backup/restore privilege to bypass ACLs.
INVALID_HANDLE_VALUE, sharing violations and errors must block. See Microsoft's
[CreateFileW contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).

The existing journal binding uses BY_HANDLE_FILE_INFORMATION (13 DWORD fields,
52 bytes), returns a Boolean and checks link count/reparse attributes. Future
bindings must check return values and native errors, volume plus file ID, link
count and type for every object; filesystem-dependent limitations must block.
See [GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle).
Handle-based ACL inspection requires correct READ_CONTROL and native allocation
cleanup. GetSecurityInfo returns a DWORD error code, unlike Boolean file-info
APIs; it is not a synchronization primitive. See
[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo).

No native inspection on LS5/LS7 or user-host directories was performed. A privileged
administrator, kernel/filter driver or non-cooperative privileged process is not
contained by a Grid mutex. Read-only Win32 handles plus a final path check cannot
honestly claim isolation from all such actors. The threat model and trusted ACL
administrators must be explicit before enabling positive proof.

## Test evidence and remaining work

60 in-memory fixtures run on PS5.1/7, including an exact canonical match that STILL
blocks ownership. Provider traps reject accidental host/native/compilation calls.
Python tests feed actual PS serializer output into the receiving schema2 API and
confirm it remains rejected on Python3.11/3.12 Windows CI. Serialized native,
ACL, freshness, mutex and TOCTOU assertions also remain rejected. The finished
Windows bundle runs the same fixture with its manifest-covered installer files.

These are byte-contract and fail-closed tests. They do NOT test native handle
retention, real hardlink/junction rejection, real ACL enforcement or adversarial
TOCTOU. Existing mocked diagnostic tests remain intact. Positive native proof
requires a reviewed session/consumer API, trusted ACL preparation, ABI/disposal
and lifetime tests, ancestor/tree mutation race tests and approved disposable
Windows fixtures. No physical execution/readiness is authorized by green CI.

Rollback: revert this source change through review. It creates no installed
resources or data; no cleanup, ACL reset, database downgrade or journal rewrite
is required. Existing preserve-only retirement remains unchanged.

The restricted fixture-only lifetime feasibility prototype is documented in
[NATIVE_OWNERSHIP_SESSION_PROTOTYPE.md](NATIVE_OWNERSHIP_SESSION_PROTOTYPE.md).
It keeps production ownership BLOCKED; it does not complete this architecture's
native ownership/ancestor/consumer requirements or enable schema2.
