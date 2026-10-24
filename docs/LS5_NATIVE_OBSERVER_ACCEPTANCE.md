# Native Windows ACL observer: independent offline acceptance boundary

Baseline PR238: `116bc11bb4c661c8b77be69c64b88f48a529968a`. This implementation updates PR238 only. PR237 and all production entry-point refusals remain unchanged.

**Physical PC4 0/10 NOT_RUN. Execute NOT_AUTHORIZED. Cleanup NOT_AUTHORIZED. Deployment NO-GO.** No LS5/PC4 connection, native observer execution on these hosts, account/policy/service change, secret rotation or physical task activation is authorized. Local compilation and managed synthetic tests do not inspect host ACLs/tokens/files.

Continuation: the frozen inventory now contains 31 hosted observer cases, 42 pure observer policies, 20 separate native transaction fixture cases, 30 pure journal cases and 66 Python tests. The earlier counts below describe the initial observer stage. See [native fixture transaction and cross-PR boundaries](LS5_NATIVE_FIXTURE_TRANSACTION.md) for the executable continuation, artifact inspector and explicit crash/authentication limitations. Production custody/Apply remains BLOCKED.

## Read-only implementation

`NativeAclObserver` is a .NET8 Windows console prototype, not an installer or executor. No descriptor-setting API exists. It requests READ_CONTROL, FILE_READ_ATTRIBUTES and SYNCHRONIZE (plus directory traversal for held parents); it does not request file content access, WRITE_DAC, WRITE_OWNER or DELETE.

1. Accept a deliberately narrow canonical absolute local DOS path: uppercase drive, ASCII components, no UNC/extended caller prefix, aliases, device names, ADS, wildcards or trailing dots/spaces. Unsupported paths fail closed rather than being normalized into another identity.
2. Resolve the initial drive mapping with `QueryDosDeviceW`; require a physical HarddiskVolume device and verify the root handle's `GetFinalPathNameByHandleW(VOLUME_NAME_NT)` is exactly that volume root. This closes the independently found SUBST/nested-root omission. No drive mappings are created by the observer or tests. Managed negative tests cover SUBST/network/mismatched roots.
3. Hold the root handle, then open **one component per call** with `NtCreateFile`, `RootDirectory` set to the retained parent handle, `FILE_OPEN_REPARSE_POINT` and `OBJ_DONT_REPARSE`. Retain the entire chain without FILE_SHARE_DELETE. Reject native status errors; there is no fallback to unsafe pathname lookup or normal reparse traversal. Parent handles must identify directories; every handle must identify an NTFS disk object on the same volume.
4. Read attributes/link count with `GetFileInformationByHandle`, 128-bit file ID and volume identity with `GetFileInformationByHandleEx(FileIdInfo)`. Reject reparses and file hardlink aliases. Recheck the original held handles, not reopened names. This constrains tested rename/replacement attempts; it is not proof that all pre-existing write-capable handles or privileged adversaries are excluded.
5. Read owner, group and DACL from `GetSecurityInfo` **on each handle**. Validate the descriptor, parse SID-based common allow/deny ACEs in their original order, record masks/inheritance/protection and SHA256 of the returned binary descriptor. Null/incomplete DACL, callback/object/unsupported ACEs or unknown structures fail closed. SACL/resource/conditional authorization is not treated as established.
6. Capture the effective **thread token**, falling back to the process token only for ERROR_NO_TOKEN. Duplicate an impersonation token with query access; do not enable privileges or change identity. Capture user SID, elevation, integrity and bounded TOKEN_GROUPS with native attributes. Pointer/count/subauthority bounds are checked before SID reads. Deny-only/disabled groups are preserved; permission arithmetic is delegated to Windows `AccessCheck`.
7. For that captured token only, query specific DACL decisions for DELETE, parent DELETE_CHILD, WRITE_DAC, WRITE_OWNER, WRITE_DATA and APPEND_DATA. `AccessCheck` honors native group/deny/restricted-token semantics for the supported descriptor. Privilege-mediated decisions are explicitly `BLOCKED_PRIVILEGED_ACCESS`. These are **DACL decisions**, not full effective access or proof about arbitrary Users/service tokens.

The full effective-access gate stays `BLOCKED_MIC_ALL_PRINCIPALS_AND_PRIVILEGES_NOT_PROVEN`: MIC/SACL, all relevant external tokens, group membership freshness, privileges, object-manager/driver context and old writers are not established. A current elevated runner token cannot attest to ordinary-user isolation. No software-only defense against a hostile local administrator/kernel/offline disk modification is claimed.

Root volume mapping is checked at acquisition. Privileged namespace changes and expected-volume provenance still require an independently trusted bootstrap/approval manifest; the observer does not approve an arbitrary discovered volume as an installation scope.

## Protocol and authority

Exit 0 means an observation completed. Every report still says `status=BLOCKED`, `host_verified=false`, `physical_attestation=false`, and Apply/Execute/Cleanup false. Rejected/uncertain input returns exit2 plus a structured constant reason. Error text does not echo credentials or arbitrary command-line strings.

`--session` is a read-only test observation session: emit a HELD snapshot, retain handles, accept only `recheck` on stdin within20 seconds, then compare identity/descriptor/right snapshots and release handles in reverse order. EOF, timeout, drift or unsupported command refuses. It is not a transaction protocol or physical authorization gate.

`--test-fault` only injects refusal at TOKEN_OPEN, TOKEN_QUERY, IDENTITY, DESCRIPTOR, ACCESS_CHECK or PRIVILEGE boundaries. Such reports explicitly set `fault_injection=true`. These tests exercise rejection paths on the native observation flow; they are not evidence that an OS privilege was actually removed or a native API actually malfunctioned. No injection can enable a success/Apply path.

## Tests and CI contract

- 40 managed synthetic cases: aliases, file types/IDs, links, group flags, token-buffer bounds, descriptor/identity/rights drift and drive-root mapping. These never invoke the native observation APIs.
- 28 hosted GUID fixture cases per shell/runtime cell, including six explicitly labelled injected refusals. Native cases cover owner/group/ACE reads, captured-token DACL decisions, group deny precedence, WRITE_OWNER, owner WRITE_DAC, parent DELETE_CHILD, missing READ_CONTROL, missing objects, junction/symlink/hardlink refusal, live rename exclusion and deterministic descriptor drift while handles remain held.
- 32 Python source/evidence negative tests: fake authority, altered run/HEAD, missing token/rights, forged token digest, malformed ACE/SID/types, links, missing chain, false exits and SKIP.

The new workflow builds with warnings as errors on GitHub-hosted Windows and runs PowerShell5.1/7 x Python3.11/3.12. Every native fixture is freshly created under RUNNER_TEMP with a GUID; no existing installation is adopted, no users created, no tasks/services touched, no recursive cleanup performed. ACL changes are fixture setup only. Remaining fixtures expire with the disposable runner.

Pinned checkout uses exact PR HEAD and full history. A frozen inventory binds managed/native/Python case IDs; live pytest reports reject skips/xfail/errors/failures. JUnit, JSONL, source Git-blob SHA256, binary closure SHA256, run ID/attempt and HEAD are checked before artifacts are published. The required aggregate rejects missing/failed/skipped matrix jobs. No inherited general workflow is disabled. Historical planning branch exclusions remain intact.

Receipts and SHA256 are tamper-detection evidence within the trusted GitHub workflow/runner context, not signed physical attestation, protected-journal authentication or durable anti-rollback. Independently downloaded artifact validation and actual job terminal results are reported in the PR; this document does not predeclare CI PASS.

## Findings and unresolved gates

P2 fixed: original workflow accepted expected native exit2 but leaked it as final step status; complete assertions now precede explicit success. No failure is turned into success by ignoring its result.

P2 fixed after independent read-only AI review: trusting a DOS drive mapping could omit physical ancestors. Root mapping/final-path checks and negative managed cases now reject that representation. This is not a human review.

P1 BLOCKED: complete effective rights for all untrusted principals; actual ordinary-user tokens; existing writers; complete Python/DLL/source closure; independently protected bootstrap; full native mutation custody; authenticated durable journal, trusted anti-rollback and safe recovery. Descriptor or data changes after the final read are not excluded. File contents are not hashed by this metadata-only observer.

P0 supplied LS5 code/secret exposure remains physically unremediated. Observer acceptance never changes the physical repair or deployment decision.

## Primary API contracts

- [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile) and [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes): relative opens and reparse behavior. Cross-version acceptance of the chosen user-mode combination is tested on the hosted image only; unsupported calls refuse.
- [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo): handle-based descriptor reads.
- [AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck) and [DACL evaluation](https://learn.microsoft.com/en-us/windows/win32/secauthz/how-dacls-control-access-to-an-object): token/ACE ordering and requested-access semantics.
- [Impersonation tokens](https://learn.microsoft.com/en-us/windows/win32/secauthz/impersonation-tokens): thread versus process identity.
- [GetFinalPathNameByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew): final native volume path observation.

Follow-up independent review also found a redirected-output drain ordering defect and missing evidence parity checks (zero/duplicate IDs, same volume, directory ancestors and parent DELETE_CHILD). Seven RED regressions reproduced these issues before fixes. Recheck now drains asynchronously before exit waits; receipts reject structural contradictions.
