# LS5 S0 capability SID investigation — STOP / BLOCKED

Owner decision: investigate read-only; do not change ACLs, create staging
directories, allowlist the SID, or run S0. Observation baseline is PR #244 HEAD
`ef258317f8646cf0d2d3ce1e82ce747d7d9fa8df`, tree
`e508bb83a11955a41f9ad56737d7c233e5916ebb`.

## Observed facts, 29 October 2026

Fresh stock Windows PowerShell 5.1/.NET queries on hostname `LS5` read existing
directory Owner, Group and DACL through `Directory.GetAccessControl`, then parsed
`RawSecurityDescriptor` / `RawAcl`. No SACL, AccessCheck, token creation, logon,
policy change, extraction, ACL setter or filesystem mutation was requested.
The query process did not stage or execute the smoke package. Results are
**metadata observations, not HOST_VERIFIED source custody**. Identical before/after
SDDL is a consistency observation, not a continuous handle or TOCTOU guarantee.
Ordinary OS/shell bookkeeping is not claimed to be a hermetic no-write sandbox.

Full investigated SID:

```text
S-1-15-3-2968813833-811790644-2202111208-3784096404-1081847329-2708967783-1438471679
```

| Existing directory | ACE type | Mask | Raw ACE flags | .NET inheritance / propagation | Inherited |
|---|---|---|---|---|---|
| AppData | AccessAllowed (0) | `0x001f01ff` FullControl | `0x00` | 0 / 0 | false |
| AppData | AccessAllowed (0) | `0x10000000` GenericAll | `0x0b` OI, CI, IO | 3 / 2 | false |
| AppData/Local | AccessAllowed (0) | `0x001f01ff` FullControl | `0x10` ID | 0 / 0 | true |
| AppData/Local | AccessAllowed (0) | `0x10000000` GenericAll | `0x1b` OI, CI, IO, ID | 3 / 2 | true |
| AppData/Roaming | AccessAllowed (0) | `0x001f01ff` FullControl | `0x10` ID | 0 / 0 | true |
| AppData/Roaming | AccessAllowed (0) | `0x10000000` GenericAll | `0x1b` OI, CI, IO, ID | 3 / 2 | true |

OI = object inherit, CI = container inherit, IO = inherit only, ID = inherited.
**Raw ACE_HEADER InheritOnly is 8; .NET PropagationFlags.InheritOnly is 2.**
Owner on all three directories:
`S-1-5-21-12977273-2956189057-260416802-1002`.
Group: `S-1-5-21-12977273-2956189057-260416802-513`.
DACL protection is false on these three. Attribute reads returned Directory,
without ReparsePoint; this is not a pinned no-reparse guarantee.

Exact Owner/Group/DACL SDDL, including unrelated ACEs to avoid a misleading
partial ACL (no SACL was requested):

AppData:

```text
O:S-1-5-21-12977273-2956189057-260416802-1002G:S-1-5-21-12977273-2956189057-260416802-513D:AI(A;OICI;FA;;;S-1-5-21-12977273-2956189057-260416802-1002)(A;OICI;0x1200a9;;;S-1-5-21-12977273-2956189057-260416802-1003)(A;OICIIO;GA;;;S-1-15-3-2968813833-811790644-2202111208-3784096404-1081847329-2708967783-1438471679)(A;;FA;;;S-1-15-3-2968813833-811790644-2202111208-3784096404-1081847329-2708967783-1438471679)(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;FA;;;S-1-5-21-12977273-2956189057-260416802-1002)
```

Local (Roaming has the same observed SDDL):

```text
O:S-1-5-21-12977273-2956189057-260416802-1002G:S-1-5-21-12977273-2956189057-260416802-513D:AI(A;OICIID;0x1200a9;;;S-1-5-21-12977273-2956189057-260416802-1003)(A;ID;FA;;;S-1-15-3-2968813833-811790644-2202111208-3784096404-1081847329-2708967783-1438471679)(A;OICIIOID;GA;;;S-1-15-3-2968813833-811790644-2202111208-3784096404-1081847329-2708967783-1438471679)(A;OICIID;FA;;;S-1-5-21-12977273-2956189057-260416802-1002)(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)
```

## Provenance remains UNKNOWN

`SecurityIdentifier.Translate(NTAccount)` failed with inner
`IdentityNotMappedException`. A bounded read of the 64-bit
`HKLM\SOFTWARE\Microsoft\SecurityManager\CapabilityClasses` subtree visited
seven keys, including its cached values; no matching SID and no enumeration
errors were observed. `AllCachedCapabilities` is a **value**, not necessarily a
subkey. An initial subkey-only probe found nothing and was superseded by this
corrected parent-key/value enumeration.

The exact SID was not found in a narrowly scoped existing Codex sandbox log
search. The existing `cap_sid` metadata contains different SIDs. Neither result
establishes the ACE writer, creation time, capability name, token holders or
absence from other software. No application, Windows component or Codex origin
is attributed. Registry absence and lookup failure are not proof of invalidity.
No broad log/credential/secret collection was performed.

Microsoft documents unresolved capability SIDs as intentional and warns against
blind removal. Its capability cache can omit third-party entries. These facts
explain why a friendly-name lookup is inconclusive; they do not make this
particular grant trusted. [Microsoft capability SID troubleshooting](https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/sids-not-resolve-into-friendly-names).

## Current object, descendants and conditional risk

FullControl without IO applies to the current object, even when the ACE is
inherited. The separate IO GenericAll ACE can propagate to future unprotected
children. Generic-right mapping can produce an effective plus inherit-only pair;
this pattern alone proves neither maliciousness nor safety. The IO flag on one
ACE never cancels a separate effective ACE. Protected child DACLs prevent ordinary
inheritance but do not remove dangerous rights on ancestors.
[ACE inheritance rules](https://learn.microsoft.com/en-us/windows/win32/secauthz/ace-inheritance-rules).

The observed FullControl includes DELETE_CHILD, DELETE, WRITE_DAC and WRITE_OWNER.
For a token to which the grant actually applies, these are a **conditional
replacement/control risk** to the namespace and future staging. Windows allows
file deletion/rename through either the file's delete right or the parent's
delete-child right, subject to its other checks and sharing semantics.
[DeleteFileW rights and sharing](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-deletefilew).

This investigation did NOT establish a usable attacker token, matching enabled
TokenCapabilities, MIC/restricted-token effects, actual effective access, exploit
or compromise. Absence or deny-only status in one operator's TokenGroups cannot
prove that all other accessors lack the capability. TokenCapabilities has a
separate information class. No principal was created or impersonated to test
access. [Token information classes](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class).

## Separate assessment: UserProfile Known Folder parent

Existing `C:\Users\LS-5` has a protected DACL, SYSTEM owner, FullControl for
SYSTEM, Administrators and the user; its other observed capability-style ACE
has only `0x100020` (execute/traverse plus synchronize), not the target SID.
`C:\Users` metadata has no target SID grant either. This is a **candidate design
direction only**, not a safe-root approval or a normal-Windows baseline proof.
The system volume has ordinary inheritance and a TrustedInstaller owner; its
review remains contextual. No clean Windows comparison host was sampled.

S0's current native contract requires fresh roots directly below LocalAppData.
Changing to UserProfile needs an explicit scoped contract, Known Folder
resolution, full stable ancestor identities/security checks, strict fresh child
DACL, source/input/transfer path agreement, Windows negative tests and independent
acceptance. This patch does not change that contract, silently redirect paths,
create a root, or globally trust any capability SID.

## Offline regressions and limits

`tools/s0_ancestor_acl_review.py` is a pure, conservative synthetic snapshot
review. It rejects unknown fields/types/SIDs, unknown ACEs, dangerous unknown
effective/inheritable grants, reparse/unknown ancestry and duplicate identities.
It distinguishes raw flags from .NET propagation flags. Its narrower supported
owner model is not a replacement for native `Inspect` (for example, it does not
implement the contextual OS-root TrustedInstaller exception).

`OFFLINE_MODEL_PASS` always retains host BLOCKED, effective access NOT_EVALUATED,
Execute=false and Cleanup=false. Deny ordering, MIC, actual token membership,
filesystem handle lifetime and Windows inheritance are not simulated AccessCheck.
Existing native guards and physical authorization restrictions are unchanged.
The new tests are added to the mandatory S0 offline inventory with exact JUnit
case verification on Windows/Ubuntu and Python 3.11/3.12.

Independent review found a P2 strictness gap in the initial synthetic model:
reserved masks could yield model PASS. Fifteen failing negative cases reproduced
it before a supported-mask restriction fixed it. Unknown/reserved rights,
MAXIMUM_ALLOWED and ACCESS_SYSTEM_SECURITY are now BLOCKED in this subset.
This never granted host or execution authority. The ancestor rule still focuses
on replacement/control rights; effective create-only or attribute-write grants
without inheritance are not a promise of zero mutation or a complete access check.

Independent technical AI source review agreed that the separate effective grant
requires STOP and predicted the raw ID flags subsequently observed. It performed
no host queries and is not a human review or physical acceptance.

## Evidence and disposition

Local ignored evidence under `.ls5-first-boot-report/` (not secrets):

| Record | SHA-256 |
|---|---|
| `query-capability-readonly-20261029.ps1` | `46196abb30fcb00cdc63c06a6ccc085180691b50756c23c113a25340720b664c` |
| `g0-ls5-capability-raw-20261029.json` | `2f794c54bf979f204d9a24e47d57ec135e46301dc29377635f01966fb306e12e` |
| `g0-ls5-capability-summary-20261029.json` | `9fa9556af8255e60386d263024804de1be2be2e6d8539b2dabc58248fdfacdc3` |

These hashes bind saved observations, not an external authenticated host or
continuous custody. The raw collector script is retained with the evidence for
review; it is not installed on a physical host or invoked by CI.

| Priority | Finding | Disposition |
|---|---|---|
| P0 | LocalAppData ancestor custody fails the current guard; exact capability holders/provenance unknown | S0 Stage/Prepare/Execute BLOCKED; no guard relaxation |
| P1 | Conditional parent replacement/control; no effective-token or stable-handle proof | Keep BLOCKED, no asserted exploit; alternate-parent design requires separate review |
| P2 | Raw versus normalized inheritance flags and subkey-versus-value lookup can mislead diagnostics | Corrected raw query, explicit limits and offline regressions |

G0: **BLOCKED**. Physical S0: **NO-GO**. No physical permission request to execute
is ready. Physical SID/ACL **0/10 NOT_RUN**. Execute/Cleanup **NOT_AUTHORIZED**.
All twenty G1 phases stay **BLOCKED / null argv**. Deployment **NO-GO**.

## Coordinator follow-up: explicit UserProfile design only

Task: [comment 6504282964](https://github.com/YehorBabenko88/bybit-cluster-grid/pull/244#issuecomment-6504282964).
This section and the additional pure tests are a proposal, not a native
implementation or physical authorization. LocalAppData code stays byte-for-byte
unchanged. No canonical artifact is replaced while run `40923824071` is queued.

| Approach | Decision | Reason |
|---|---|---|
| Keep current LocalAppData API | Retain, currently BLOCKED on LS5 | No unsafe fallback or retroactive ACL repair |
| New explicit UserProfile API | Recommended for further review only | Can select a different independently checked ancestry without trusting the capability |
| Arbitrary caller path or automatic retry elsewhere | Reject | Loses Known Folder and owner binding; hides the first safety failure |

### Proposed native API semantics — not implemented

Proposed distinct entry point: `PlanPackageAtUserProfileV1(...)`, later a separately
approved `StagePackageAtUserProfileV1(...)`. Existing `PlanPackage` / `StagePackage`
must not acquire a boolean fallback switch or changed defaults. A versioned parent
proof must accompany ALL package, input, recipient, export, transfer, pair and
runtime root operations. One success must not leave downstream code checking
LocalAppData or accepting caller-chosen roots.

1. Require the observed current primary token's exact SID, Medium integrity,
   non-elevated state, groups and privileges under existing policy. Query and
   reject an impersonating thread, AppContainer or packaged identity; unknown
   API results remain BLOCKED. Do not create, duplicate, log on or impersonate
   a user. Recheck the same token identity at the final mutation boundary.
2. Resolve `FOLDERID_Profile` `{5E6C858F-0E22-4760-9AFE-EA3317B67173}` with
   `SHGetKnownFolderPath`, exactly `KF_FLAG_DONT_VERIFY=0x4000`, `hToken=NULL`.
   Check HRESULT and bounded non-null UTF-16 result; free its CoTaskMem pointer
   on every success/error path. No CREATE, INIT, DEFAULT_PATH, redirection or
   environment-based substitution. NULL means current user, not Default User;
   `hToken=-1` is expressly forbidden. A non-null token has different documented
   access requirements; do not silently request those extra rights as a fallback.
3. Independently query `GetUserProfileDirectoryW` using an owned query-only
   handle to the same current primary token. Bound its size probe/retry, check
   Win32 errors and terminating NUL, require the same canonical path and SID.
   This is a consistency check, not an independently authenticated authority:
   both APIs ultimately depend on the trusted local OS/profile configuration.
4. Reject UNC/device/relative paths, aliases, dot components, alternate volumes,
   non-NTFS/remote filesystems, profile junctions/mount points, package redirection
   and unknown volume mappings. Initially require the verified OS volume only.
   Never infer the path from `$env:USERPROFILE`, a hostname or `C:\Users\<name>`.
5. Hold and inspect every ancestor from that volume root to the resolved profile,
   including each *current-directory* non-inheriting ACE. Compare final paths,
   volume/file identities, owner, full DACL and supported ACE structure before
   and after each boundary; deny reparse and identity/ACL drift. A no-share-delete
   handle is necessary custody evidence, not a general lock on DACL modification.
   Unknown effective DELETE_CHILD, DELETE, WRITE_DAC, WRITE_OWNER, GenericAll or
   GenericWrite remains BLOCKED, including on the candidate parent itself.
6. Propose exactly one fresh UUID leaf immediately below this verified parent.
   Probe nonexistence through that held parent; AccessDenied, collision or any
   ambiguous error BLOCKS. Future native creation must be relative to the held
   parent with create-new semantics and the protected three-principal DACL at
   creation, never create then repair ACL. Pin transaction/root handles, populate
   only validated members, reject reparse/hardlinks, hash through owned handles,
   revalidate all pins, and publish atomically without replacement to the same
   held parent. Do not adopt or delete a partial/existing target after failure.

References: [Known Folder identifiers](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid),
[SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath),
[Known Folder flags](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/ne-shlobj_core-known_folder_flag),
[GetUserProfileDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-getuserprofiledirectoryw).
These APIs are documented; the proposed combination has NOT been executed on
LS5/PC4 or accepted as a working native implementation.

### Existing chain comparison, not a new host attestation

Earlier read-only metadata includes this exact UserProfile Owner/Group/DACL SDDL:

```text
O:SYG:SYD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;S-1-5-21-12977273-2956189057-260416802-1002)(A;;0x100020;;;S-1-15-3-65536-599108337-2355189375-1353122160-3480128286-3345335107-485756383-4087318168-230526575)
```

Its current-directory capability ACE is execute/traverse plus synchronize, with
no inheritance. It is not omitted simply because the DACL is protected. Its
origin is also not asserted; benign mask observation is not general SID trust.

`C:\Users`:

```text
O:SYG:SYD:PAI(A;OICIIO;GXGR;;;WD)(A;;0x1200a9;;;WD)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;0x1200a9;;;BU)(A;OICIIO;GXGR;;;BU)(A;;0x100021;;;S-1-15-3-65536-4045685566-1323397456-4055816110-285687253-194181-4019357623-1925838800-191844675)
```

System volume root `C:\`:

```text
O:S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464G:S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464D:(A;;LC;;;AU)(A;OICIIO;SDGXGWGR;;;AU)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;0x1200a9;;;BU)(A;;0x1000a1;;;S-1-15-3-65536-1888954469-739942743-1668119174-2468466756-4239452838-1296943325-355587736-700089176)
```

Volume-root Authenticated Users has effective ADD_SUBDIRECTORY plus a separate
inherit-only grant; that is not effective DELETE_CHILD on the root. The current
native ancestor rule deliberately distinguishes creation from replacement.
Its contextual TrustedInstaller exception is volume-root-only. The pure model
is more conservative and does not certify this actual chain. No held file IDs,
mount resolution, effective token access or continuous custody was established
by these path-based metadata reads. Do not claim that this profile is ready.

Trust boundary: SYSTEM, Administrators and the exact operator SID remain trusted.
This design does not isolate malicious code already running as that operator,
privileged administrators, kernel drivers or a compromised OS. Fresh protected
child DACLs do not neutralize dangerous *effective* parent rights. Read-only
metadata and synthetic tests establish none of these stronger guarantees.

### Minimal plan and test gates

The offline spike `review_profile_candidate()` only reviews synthetic strings,
ACLs and hypothetical facts; it does NOT call Shell32/Userenv, open handles,
create directories or authorize anything. It requires explicit mode/GUID/flags,
token SID match, same query paths, fixed volume/NTFS, non-mounted profile, fresh
UUID target, single-link non-reparse source and matching parent model identity.
The declared ancestor paths must enumerate every component from the OS volume
to the profile and have the same depth as the ACL model. This is consistency
between hypothetical inputs, not evidence that the OS supplied those facts.
Even model PASS leaves host BLOCKED and Execute/Cleanup false. Existing
`review_snapshot()` remains unchanged; its actual-chain limitations still apply.

Independent review also exposed Unicode device-name aliases (`COM¹/²/³` and
`LPT¹/²/³`, including extensions). Six RED cases isolated the alias rule after
correcting their path-chain fixtures; the model now rejects these as well as
ordinary DOS devices and tilde aliases. Tilde rejection alone is not proof of
long-path identity; the future handle-based final path check is still required.
[Windows naming rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).

- [x] Add targeted negative fixtures first: simplified ACL-only acceptance
  reproduces 25 incompatible proposals as false model PASS.
- [x] Enforce the explicit pure proposal contract; targeted GREEN plus the
  existing capability/ACE regressions. No claim of actual Win32 fault injection.
- [x] Extend the S0 inventory/JUnit expectations for the new cases locally.
- [ ] Independent review of this design and its proposed native API.
- [ ] After that review, implement native resolution, handle lifetime and common
  parent-proof propagation across Bootstrap, Inputs, Transfer, Export, Transport,
  launcher/runtime path validation and command manifests in a separate change.
- [ ] Genuine disposable hosted Windows 5.1/7 negatives: failed HRESULT/size
  probes, SID/primary/thread-token mismatch, unknown capabilities on each ancestor
  and candidate, inheritance/current-dir ACEs, existing-target races, junction,
  symlink, hardlink, alternate volume/profile mount, pre-opened conflicting
  handles, same-file ACL drift and atomic publish crash. No physical mutation.
- [ ] Exact-head offline/native CI and independently verified original package.
- [ ] Separately authorized read-only per-host native Plan, followed by a new
  owner decision on any specific physical Stage; never inferred from test PASS.

Current queued run `40923824071` is not cancelled or rerun for this design. Until
it finishes, retain the existing remote HEAD and publish this proposal/diff for
discussion rather than automatically replacing its artifact or concurrency slot.

### Separate future physical approval contract — all authority absent

Required future fields: exact reviewed HEAD/tree, independently pinned original
ZIP/manifest/source digests, selected explicit API version, LS5/PC4 host identity,
observed local operator SID/token/session, run UUID, expiration, exact parent
volume/file identity and ACL digest, fresh package/input/pair/transfer leaves,
approved literal argv, expected side effects, bounded runtime and STOP/ownership
rules. No secret material belongs in the approval record.

For this proposal every action is `authorized=false`, `argv=null`, expiry unset.
Read-only native observation, public no-key transfer rehearsal, each Stage, input
Prepare and final 300-second Execute require separate explicit scopes and owner
approval after their prerequisites pass. Cleanup is excluded; failure preserves
owned evidence and must not delete/adopt resources. No existing ACL/service/task,
PostgreSQL, SSH, Tailscale or firewall change is part of any proposed scope.

P0: native UserProfile support and independent custody proof absent. P1: no
physical token/handle/transfer approval. P2: model/API distinction is explicit.
S0 **NO-GO**, all20 G1 **BLOCKED/null argv**, Execute/Cleanup **NOT_AUTHORIZED**.

Illustrative future approval record (not read or accepted by current runtime):

```json
{
  "schema": "USER_PROFILE_STAGE_REQUEST_V1_DRAFT",
  "head": null,
  "tree": null,
  "package_sha256": null,
  "source_manifest_sha256": null,
  "host_identity": null,
  "operator_sid": null,
  "run_id": null,
  "parent_identity": null,
  "parent_acl_sha256": null,
  "target": null,
  "expires_utc": null,
  "owner_authentication": null,
  "authorized": false,
  "argv": null,
  "execute": false,
  "cleanup": false,
  "g1_argv": null
}
```

Missing/unknown bindings must BLOCK any future consumer; a valid hash alone or
a model PASS must not fill these fields or grant authorization automatically.
