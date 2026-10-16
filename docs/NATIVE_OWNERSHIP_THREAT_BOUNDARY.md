# Native ownership: threat boundary and architectural decision

Baseline: PR196, commit `3d7a1157a8fca244d7309b34eab2cd59b284b08b`.
This follow-up is read-only evidence tooling. No ownership capability, executor,
new privilege, adapter target, schema-2, provisioning command or activation is added.
The matrix generator performs no filesystem/native/network probes.

## Explicit threat models

**A — cooperative non-admin processes in a separately approved, pre-provisioned
exclusive lab subtree.** The policy, principals and entire relevant ancestor chain
must be independently approved. Other principals must not have data-write, delete,
child-create, WRITE_DAC or WRITE_OWNER rights. The verifier identity, its code,
callbacks, provider, OS and filesystem must be trusted. No hostile code may run
under the owner/verifier SID. A non-elevated process under that same SID is NOT
isolated by a DACL granting that SID full control: it can often change the ACL.
Existing writable handles/mappings and privileged writers must be excluded by
provisioning, not assumed absent from a successful open. These prerequisites have
NOT been attested by the prototype. Selecting A in the report is no approval or
proof that prerequisites hold. Decision: **BLOCKED_PROVISIONING_UNPROVEN**.

**B — hostile local administrator or equivalent privileged concurrent writer.**
Do not claim an in-process Python verifier, discretionary ACL, named mutex or
periodic snapshot protects against control of the same OS. Privilege can permit
ownership/ACL changes, process interference, replacement of trusted code or false
evidence. Ordinary sharing semantics can still deny a particular open; this does
not make a local administrator unable to subvert the verifier. Decision:
**STOP_OS_BOUNDARY_REQUIRED**. Do not enable schema-2 or promote snapshots into
an authorization capability under B.

## Guarantee / observation / assumption matrix

All rows remain **BLOCKED for ownership/readiness**. API contracts below are
conditional documented semantics, not independently proven security guarantees.

| Property | Conditional API contract / A | Actual baseline evidence | B / unproven scope |
| --- | --- | --- | --- |
| Win32 handles, share=READ | Successful opens restrict incompatible ordinary data-write/delete opens while held; handle refers to an opened object | Pinned junction, hardlink and owned ancestor rename attempts denied | No namespace-wide lock; security descriptor writes are not data-write sharing; existing mappings, provider/process integrity not proven |
| ACL | DACL restricts access according to token and rights; separately provisioned different-SID policy may restrict ordinary processes | Foreign generic-write ACL mutation rejected at next read | Owner/same-SID changes and privileges defeat proposed trust boundary; no effective-token or policy attestation |
| File identity | Compares current volume serial and 64-bit file index via open handles | Fixture identity replacement rejected by existing tests | Not durable provenance, global uniqueness, content immutability or alias exclusion; filesystem-dependent, IDs may be reused |
| Junction/reparse | OPEN_REPARSE_POINT and sampled type/identity rejection apply to opened fixture objects | Created junction before session rejected; pinned creation denied | Does not authenticate every traversed ancestor; unsupported filesystems and transient changes remain unproven |
| Ancestors/namespace | Held fixture directory handles restrict tested ordinary rename operations | root/data/postgres rename attempts denied; concurrent marker detected | Ancestors outside GUID fixture and alternate aliases not attested; no atomic namespace snapshot |
| Privileged writer | Explicitly excluded from A; mutex coordinates only cooperating callers | No privilege escalation or hostile-admin resistance test performed | STOP under B; same-OS admin resistance unsupported |
| ACL/namespace ABA, exhaustion | Before/after snapshots can only detect differences still visible at samples | ACL change+restore UNDETECTED on BOTH baseline Python versions; bounded quota cleanup exercised | Atomicity absent; actual global kernel exhaustion BLOCKED_UNPROVEN; injected cleanup faults do not prove all kernel failures |

Baseline evidence: [run38930170514](https://github.com/YehorBabenko88/bybit-cluster-grid/actions/runs/38930170514),
artifacts `ownership-adversarial-3.11-1` and `ownership-adversarial-3.12-1`.
Each records 16 expectation tests passed and 1 BLOCKED_UNPROVEN. The ABA test
passing means it faithfully measured a missing protection, not that ABA was prevented.
The evidence includes real operations by fixture code, NOT a separate unprivileged
user token; it does not prove principal separation for A or admin resistance for B.

## Fail-closed evidence accounting

JUnit accounting still demands the exact 17 native cases and case-specific observed
outcomes. It now refuses a PASS for global kernel exhaustion: the mandatory explicit
BLOCKED_UNPROVEN result and bounded-quota observation must remain. All skipped cases
are excluded from tested_cases. That count means executed expectation tests only,
never verified security guarantees. Each case has security_outcome OBSERVED_ONLY,
LIMIT_REPRODUCED or UNPROVEN. The report always has verified_safety_cases=0,
readiness_passed=false and unresolved risks ACL_NAMESPACE_ABA/GLOBAL_KERNEL_EXHAUSTION.
Even ACL_ABA_DETECTED_THIS_RUN cannot clear the historical counterexample or prove
absence of all ABA schedules. Previous zero-skip 17-case native suite stays intact.
PS5.1/7 validate both static threat models, while Python3.11/3.12 run negative model
and evidence regressions. Real native cases run only in fresh hosted-CI GUID fixtures.
CI SUCCESS means assertions and honest accounting passed; it is not readiness PASS.

## Separately approved lab provisioning plan (not executable)

1. Operator reviews A versus B and approves a dedicated disposable host/VM, budget,
   resource ownership and policy. Never adopt an existing Grid directory or service.
2. Independently provision dedicated identities and a new exclusive subtree; review
   full ancestors, group membership, owner privileges, effective ACLs, existing
   handles/mappings, filesystem assumptions and trusted software. This PR performs none.
3. Approve and record attestation, lifecycle and resource-specific cleanup separately;
   PlanOnly/ReadOnly remains default, no implicit reuse or deletion.
4. Execute separately approved different-token negative tests in disposable lab only.
   Model/fixture results cannot substitute for this missing principal-separation proof.
5. Re-review security objective before any executor, adapter binding or schema-2 work.

## STOP decision and VM alternatives

If B is required, stop same-OS ownership authorization work. Use a disposable VM
with a trusted host/hypervisor and management plane outside the adversary's control;
keep Grid data and verifier inside that boundary, avoid host writable shared folders,
host disks, privileged passthrough and production network access. A hostile guest
administrator still controls a verifier INSIDE that guest: move integrity decisions
outside its control or do not grant that actor guest-admin rights. A hostile host
administrator is NOT contained by a VM it manages. For that adversary use a separately
administered machine/trust domain (or explicitly exclude it). Containers or another
same-OS account alone do not establish a host-admin boundary. Availability against
host power/storage control is outside this design. No VM is created by this PR.

## Sources and limits

- [CreateFileW sharing and reparse semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
- [File security and access rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights): WRITE_DAC/WRITE_OWNER differ from writing file data.
- [GetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle): filesystem/identity limitations.
- [Object ownership](https://learn.microsoft.com/en-us/windows/win32/secauthz/owner-of-a-new-object): owner access policy.
- [Taking ownership](https://learn.microsoft.com/en-us/windows/win32/secauthz/taking-object-ownership-in-c--): privileged ownership change.

VM recommendations are architectural boundary requirements inferred from the threat
model, not tested deployment capabilities. No claim of full local-admin isolation,
atomic snapshots, universal file-ID properties or production HA is made.
Rollback is a reviewed source revert only; no production state was changed.
