# Protected Source/TEMP staging — design only, NOT PROVISIONED

No ACL, directory owner, account, service, policy or host configuration is changed
by this document or the audit. CollectLocal remains NOT_AUTHORIZED on LS5/PC4.
This is a future owner-reviewed provisioning specification, not an execution recipe.

## Threat boundary and current NO-GO

LS5 reports source staging writable by `LS5\LS-5` and shared TEMP granting Modify
to `CodexSandboxUsers` plus an unresolved SID. Hash/blob equality proves which
bytes were checked at that instant; it does not stop replacement before loading.
An elevated reader compiling from those locations crosses a trust boundary.
Current Source and shared TEMP are therefore NO-GO for an elevated diagnostic.
These are supplied observations, not ACL measurements made by this audit.

The design excludes other ordinary users and sandbox identities. It does not
resist Administrators, SYSTEM, a compromised runner, kernel, or malicious trusted
compiler. If the diagnostic runner is elevated as the same identity considered
untrusted, this design provides no isolation from that identity. Use a separately
approved trusted operator identity; no account creation or enablement is implied.

## Required separation and minimum allow ACEs

All identities below must be exact owner-verified SIDs, never name-only matches.
Owner is the trusted provisioning authority (Administrators or SYSTEM), except
private writable workspaces may be owned by the trusted diagnostic operator.
Protected DACLs must contain only the approved allow entries. No Everyone, Users,
Authenticated Users, sandbox group, unrelated user or unresolved SID grants.

| Location | SYSTEM | Administrators | Trusted diagnostic operator | Other identities |
|---|---|---|---|---|
| Source parent and complete reviewed source tree | Full control | Full control | Read/execute, traverse | None |
| Private TEMP/TMP parent and fresh per-run compiler workspace | Full control | Full control | Modify, traverse | None |
| Separate private output/evidence workspace | Full control | Full control | Modify, traverse | None |

Use object/container inheritance only inside each approved tree. Source must not
be owned by an ordinary source editor or grant the reader write, delete,
WRITE_DAC or WRITE_OWNER. Its parent must not grant an untrusted identity
DELETE_CHILD, rename/replacement or ownership/control over the Source directory.
Account for every ancestor and effective group ACE: merely removing a leaf ACE
does not protect against replacement from above. A private TEMP is writable by
its operator by design; it is not immutable evidence or a Source directory.

## Future custody and validation gates

1. An independently approved provisioning operator creates empty, local fixed-disk
   directories under protected parents with explicit ownership and protected DACLs.
   Do not retrofit an untrusted staging tree or accept an already-populated TEMP.
   No UNC paths, network shares, user-controlled junctions/symlinks/reparse points
   in the trees or ancestor path. Review volume and ancestor custody as well.
2. Copy the exact reviewed source/package from a trusted channel. Pin commit SHA,
   Git blob IDs and SHA256 manifest outside the writable workspace. Protect all
   executed inputs, including the entry script, Inventory.ps1 and LsaRights.cs,
   rather than hashing only the C# file. Retain provenance before and after copy.
3. A trusted reviewer checks owner and full DACL of files/directories/ancestors,
   inherited entries and group membership, absence of reparse traversal, and
   hash equality after protection and immediately before use. Unknown identity,
   unresolved SID, inherited unexpected grant, mismatch, inaccessible descriptor,
   ambiguous path or changed custody => STOP. No automatic ACL repair.
4. Launch only a fresh, approved Windows PowerShell 5.1 x64 process without profiles
   from a trusted working directory. Both process TEMP and TMP must already point
   to the same fresh private workspace before Add-Type/compilation. Confirm the
   actual compiler/toolchain and resolved executables/dependencies are trusted;
   PATH, module search, current directory and profile paths must not substitute
   binaries. Changing TEMP alone cannot secure an untrusted compiler search path.
5. Keep logs/manifests outside TEMP. The runner cannot authenticate its own output
   against compromise of that runner. Preserve source custody through the whole
   run; pre/post hashes alone do not eliminate TOCTOU. An approved precompiled,
   pinned artifact may reduce compilation exposure, but requires a separate code
   change/review; the present collector still uses Add-Type on source.
6. Future cleanup requires independent authorization and explicit owned-file
   inventory. Do not recursively remove unknown contents or automatically change
   shared TEMP/ACLs. Failed or uncertain cleanup remains recorded and blocks reuse.

No staging checks have been physically performed here, and no secure-staging
implementation is claimed. Source/TEMP protection is a prerequisite for any
future run, not a result of hosted mocks. Literal zero host writes remains
incompatible with on-host compilation and possible Windows audit/cache effects.
