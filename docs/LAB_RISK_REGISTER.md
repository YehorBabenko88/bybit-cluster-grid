# L0 lab risk register — all physical risks OPEN, deployment NO-GO

Existing PR211 offline CI is VERIFIED_OFFLINE_ONLY; this architecture PROPOSED.
Native evidence UNVERIFIED;12 cases NOT_RUN; durable anti-rollback NOT_IMPLEMENTED.
Severity describes a future physical hazard, not a demonstrated production exploit.

|ID / priority|Risk and boundary|Required evidence / owner|Current STOP condition|
|---|---|---|---|
|R01 P1|host admin controls guests and same-host observers|two external observer custodians, hardware/admin trust review / operator|hostile admin or common reset authority|
|R02 P1|hidden IPv4/IPv6/ICS/NAT/Tailscale/clipboard/drive route|complete independently obtained topology and access paths / network owner+observers|any unknown route or sharing|
|R03 P1|declared SID differs from effective/impersonated token; privilege bypass|token classes, privilege/group attributes, native access evidence / observers|unknown/reused/elevated identities|
|R04 P1|DACL owner/generic/inherited rights, reparse/hardlink/ABA/mapping bypass|held native identities and interval/lifetime proof / verifier owner|sample-only ACL match or unknown writable mapping|
|R05 P1|private data plane cannot reach independent time/anchor safely|separately reviewed nonrouting proof transport and measured freshness / trust owners|transport UNIMPLEMENTED or human-copy timing assumption|
|R06 P1|guest clock/snapshot can rewind replay history|trusted timestamp uncertainty, nonce/epoch, two durable witnesses / time+ledger custodians|source unavailable/drift/stale receipts|
|R07 P1|both witnesses/anchor can be rolled back with host|external reset-resistant custody and recovery evidence / two witness owners|correlated rollback boundary unproved|
|R08 P1|lost ACK/torn durable consume causes duplicate acceptance|CAS/fencing + persist-before-ACK + independently tested crash recovery / ledger owner|ambiguous commit or one witness unavailable|
|R09 P1|PGDATA layout translation invents ownership or hits existing data|versioned new-cluster intent, distinct digests, pinned native consumer session / adapter owner|legacy mismatch or preexisting/unowned resource|
|R10 P1|synthetic signatures/labels/JUnit become physical PASS|approved independent signer custody and raw evidence provenance / observers|test roots, self-asserted status or missing proof|
|R11 P1|unsafe emergency cleanup destroys shared data/WAL/keys|preapproved STOP/removal inventory and immutable audit / operator|ownership/authority unknown; preserve only|
|R12 P2|image/OS/hypervisor/dependency drift changes assumptions|exact media/build/binary/source hashes and offline receipts / release reviewer|UNSPECIFIED build/hash or unreviewed update|
|R13 P2|resource exhaustion or evidence retention silently loses logs|bounded fixtures/quotas, append-only archive restore checks / evidence owner|missing archive, no capacity budget; no real disk-fill|
|R14 P1|operator key compromise/revocation replay or stage creep|external roots/revocation epochs, scoped expiring approvals / separate custodians|revocation/time uncertain or approval reused across stages|

L0/L1 metadata checks do not close these risks. Accepted residual threat assumptions
must be signed before L2; no P1 is waived by this PR. Tests can prove reject logic,
not actual hardware/ACL independence. Any future mitigation must be independently
reviewed at a new exact SHA. See LAB_COMMISSIONING_PLAN_DRAFT for gates and humans'
preparation checklist. No infrastructure command is included or authorized here.
