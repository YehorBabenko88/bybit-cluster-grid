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
