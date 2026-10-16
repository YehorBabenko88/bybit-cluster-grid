# Disposable VM Lab specification — version 1

Base: `c99adbfa47dc0ce286e9dd8f966ba243cfd55b10` (PR197).
Scope: offline design, static metadata validation, future independent-principal test
protocol. **PlanOnly / BLOCKED** always. No VM or principal is created, no hypervisor
is contacted, no inventory is collected, and no executor, PostgreSQL, SQL, service,
network, task, port binding or schema-2 operation exists in this change.

## Trust boundary and architectural decisions

Model A: trusted dedicated lab host/hypervisor, trusted host administrators,
trusted immutable base-image provenance, trusted guest verifier/code, and separate
non-admin guest identities: owner, read-only verifier, adversary. Host management
is outside the guest adversary's control. Non-admin does not imply a different SID;
token user, effective impersonation token, elevation, privileges and groups must be
attested independently. Running three process names under one SID is NOT this model.
Owner and verifier are trusted; hostile owner/same-SID code is outside A.

Model B: hostile host administrator is an architectural STOP. A VM managed by the
adversary does not establish this boundary. A guest administrator can subvert an
in-guest verifier: either exclude that actor or move decisions outside its control.
No local-admin resistance, atomic ACL/namespace snapshot, universal file identity,
production ownership or availability guarantee is claimed. The validator accepts
only A metadata and rejects B configurations; this is not proof A holds.

A VM is a proposed stronger boundary, not already tested isolation. Containers,
extra account names, ACL snapshots and green synthetic CI cannot substitute for
host/image/token/storage/network attestation. Existing PR197/196 ABA and global
kernel exhaustion blockers remain open.

## Versioned plan contract and defaults

`installer/vm_lab_plan.py` accepts only exact schema1 nested objects. The only mode
is PlanOnly; omission, unknown fields and other modes fail closed. There is NO
Execute switch. JSON is at most64KiB UTF-8; duplicate keys, nonfinite values,
malformed/deep JSON, missing fields and type confusion are rejected. Errors do not
print input, credentials or exception payloads. CLI reads bounded stdin and emits
JSON only; valid metadata exits0 with statusBLOCKED, rejected plans exit2.
CLI exit0 means syntax/policy consistency, never readiness or approval to execute.
The example JSON contains synthetic IDs/digests/declared approval only, no real
credentials or signed operator decision. It must never be submitted as real approval.

| Section | Required policy |
| --- | --- |
| Identity | Distinct canonical UUIDv4 lab, VM, disk and host IDs; host ID LAB-HOST-UUID |
| Host | Hyper-V design profile only; trusted_admin=true, inventory_complete=true, nonempty aliases and protected-path inventory; reject LS5/LS7 including case, hyphen, underscore, FQDN spellings |
| Storage | Exact local-drive `X:\GridVmLab\<lab_id>` root, new child `<vm_id>\<disk_id>.vhdx` planned; fresh_disk=true, existing_disk=false; reject overlaps in either direction with declared installed/protected paths, UNC/device/traversal/8.3/ADS/reserved syntax |
| Image | Immutable SHA256 base image plus provenance-document SHA256, approved publisher label and trusted_source=true declarations; no mutable URL, download, parent/differencing disk or imported VM |
| Network | Disconnected, adapters=[], Tailscale=false, SSH=false; no bridge, production credentials, guest production access or guest host-management access |
| Host integration | Empty shared mounts/folders; no clipboard, drag/drop, enhanced session, guest services, device passthrough; no host disk/USB/GPU sharing |
| Accounts | Exactly owner/verifier/adversary, distinct canonical user SIDs (guest RID>=1000) and matching declared token SIDs; all non-admin, unelevated, empty enabled privileges, credentials FreshGuestOnly; no imported credentials |
| Approval | approved=true metadata, distinct requester/approver user SIDs outside guest principals and review-record digest; no self approval |
| Quotas | CPU1–4, RAM1024–8192MiB, guest disk8–80GiB, time1–120minutes; bool/float/overflow/zero refused |
| Disposition | PreserveOnly; schema2=false; imported_credentials=false; no automatic deletion/cleanup/restore or activation |

These are **declarations**. UUID shape does not prove freshness, path comparison does
not prove absence of reparse aliases or storage overlap, inventory_complete does not
prove exhaustive inventory, SHA256 does not authenticate the image publisher, and
approval fields do not authenticate a human decision or bind its signature to this
exact plan. A declaration pretending to be true can pass metadata checks but STILL
cannot pass readiness. Independent out-of-band attestation is mandatory and is not
implemented. No path is resolved or opened by the validator; no host API is called.
Actual protected resources beyond declared inventory, aliases, mounts, filesystems,
prior handles/mappings and reserved resources remain unproven and BLOCKED.

Disks in this design are newly materialized standalone copies into a new exclusive
lab directory, with no writable host base/shared/differencing backing. Immutable
base media is trusted read input for a separately reviewed provisioner only. This
PR neither creates nor validates actual VHDX files. Quotas do not prove host free
capacity or enforce a running guest budget. PreserveOnly does not authorize any
stop/delete command at timeout; operator must approve future containment separately.

## Future different-principal harness protocol — NOT IMPLEMENTED EXECUTOR

A separately approved operator would first attest host/hypervisor identity and
administration, verify image signature/provenance/digest, reserve fresh storage,
review effective ACL/ancestors and inspect actual device/network isolation. Reject
any uncertainty and preserve resources/evidence; never adopt or clean installed Grid.
No production Tailscale/SSH keys, tokens, secrets, database or WAL enters the guest.

Provisioning and temporary guest-test account creation require NEW approval and
implementation review. Owner/verifier/adversary must have distinct actual token
user SIDs. Capture token SID, effective impersonation context, groups/elevation and
privilege state from a trusted observer. Verify verifier is not impersonating the
adversary and commands really run under the adversary token. Account display names
or caller-provided token_sid fields are insufficient. This PR never changes tokens,
creates accounts, enables privileges or obtains passwords.

Prepare only a new guest GUID fixture; no production data or installed paths. Owner
sets independently approved explicit ACL: verifier read only, adversary no write,
delete, WRITE_DAC or WRITE_OWNER. Controls must prove adversary process actually
ran with the intended distinct token and attempted the intended operation. If it
never ran, test is NOT_RUN; access error before the attack is not a denied attack.
No exploit payloads, hostile-admin experiment or privilege enablement is authorized.

| Required case | Future evidence and safety assertion | Current state |
| --- | --- | --- |
| write | Actual different-token file/data/child write denied; verify unchanged fixture bytes | NOT_RUN / BLOCKED_UNPROVEN |
| delete | Delete and delete-child attempts denied, fixture preserved | NOT_RUN / BLOCKED_UNPROVEN |
| write_dac | WRITE_DAC acquisition and mutation denied from adversary token | NOT_RUN / BLOCKED_UNPROVEN |
| write_owner | WRITE_OWNER acquisition/owner change denied | NOT_RUN / BLOCKED_UNPROVEN |
| acl_mutation | DACL mutation attempt denied; uncertainty blocks verifier | NOT_RUN / BLOCKED_UNPROVEN |
| acl_aba | Attempt change/restore schedule; sampled detection never establishes general prevention | NOT_RUN / BLOCKED_UNPROVEN |
| inherited_acl | Unexpected/inherited writer ACE rejected without automatic repair | NOT_RUN / BLOCKED_UNPROVEN |
| junction | Junction/reparse substitution attempted inside guest fixture before/during verification; record actual mutation/denial | NOT_RUN / BLOCKED_UNPROVEN |
| ancestor | Guest-fixture ancestor rename/substitution before/during pinning; no access to host ancestors | NOT_RUN / BLOCKED_UNPROVEN |
| existing_mapping | Deliberate earlier writer handle/mapping proves its lifecycle is excluded or blocks; ACL change alone cannot revoke it | NOT_RUN / BLOCKED_UNPROVEN |
| privileges | Observe effective token/elevation/groups/privileges; privileged adversary blocks A; no exploitation | NOT_RUN / BLOCKED_UNPROVEN |
| distinct_token | Independently attest three different effective token user SIDs, not process names | NOT_RUN / BLOCKED_UNPROVEN |

Future attestation needs exact code/plan/image digests, lab/VM/session identity,
trusted observer identity and signed approval, actual token evidence, API result and
mutation postcondition per case, timestamps, artifact hashes and provenance. Do not
store credentials, live environment dumps or raw tokens. Unavailable prerequisites
mean BLOCKED_UNPROVEN, never PASS. A fresh attested execution report schema and
verifier must be designed/reviewed before accepting such evidence. Current parser
accepts NO supplied execution/PASS cases; catalogue is fixed, with every case
NOT_RUN/BLOCKED_UNPROVEN, verified_safety_cases0, readiness_passed=false and both
execution_authorized/physical_ready=false. Static/model/hosted GUID fixture CI is
NOT evidence these guest principal tests ran. Historical native tests stay unchanged.

## Approval sequence, stop conditions and preserve-only rollback

1. Review this design and threat objective, dedicated trusted host choice, resource
   budget and independent operator authority. Metadata approval alone grants nothing.
2. Separately review a future provisioner and attest real host/image/storage/isolation;
   refuse LS5/LS7, existing Grid resources, unknown ownership, overlap or unavailable evidence.
3. Obtain explicit provisioning approval bound to the reviewed immutable plan; later
   guest test execution needs separate approval. Neither is provided by this PR.
4. Stop on untrusted host admin/image, same SID/elevated actor, unverified signature,
   stale or inconsistent inventory, any share/production network/credential, unexpected
   ACE/alias/mapping, missing negative case, time/resource uncertainty or unhandled fault.
5. Preserve all resources and sanitized evidence after partial setup/failure. No
   automatic deletion, service shutdown, disk detachment, release switch or rollback.
   Containment, power-off and eventual disposal each need an independently approved
   scoped operator procedure. Never assume a directory belongs exclusively to Grid.

For THIS PR, rollback is a reviewed source revert only. No runtime or resource exists
to tear down. Schema2, adapter paths and physical deployment stay blocked.

## Verification and audit limits

Python3.11/3.12 run pure config/evidence regressions; PS5.1/7 validate blocked output
and malformed JSON refusal. Existing pinned Actions/native fixtures are preserved.
Tests cover missing/unknown fields, duplicate/nonfinite JSON, unsafe paths/host aliases,
networks, device integration, reused IDs/disks, image/approval declarations, accounts,
quotas and fabricated PASS input. CI success means the static contract holds, not VM
isolation, token independence, guest attacks, authenticated approval or production HA.

Review focus: no subprocess/native/host I/O in validator, no executor mode or readiness
promotion; all default/refusal paths preserve isolation assumptions as unproven.
The only file reads in the PS compatibility test are the checked-in synthetic example;
it starts Python solely to validate metadata, never any Grid runtime or hypervisor.


## Independent security review

Review found a policy-consistency defect before publication: a guest SID ending in
RID500 could claim administrator=false. Four RED regressions reproduced acceptance
of built-in/reserved RIDs; guest roles now require RID>=1000. This rejects a known
contradiction, not proof of non-admin membership. A custom RID>=1000 can still belong
to Administrators; actual token/group attestation remains mandatory and BLOCKED.
The empty enabled-privilege declaration is a deliberately strict design profile;
compatibility with real guest token defaults is unproven. Do not change privileges
or relax policy automatically to make a future test pass; review any required
privilege allowlist independently before provisioning.

Primary references: [Hyper-V security planning](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/plan/plan-hyper-v-security-in-windows-server)
and [Enhanced session resource sharing](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/enhanced-session-mode).
These describe conditional platform behavior, not attestation of this proposed lab.
