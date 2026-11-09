# Unqualified commissioner — source preparation, no execution release

Separate owner successor from exact2f94. Existing RootPR68, Core3dd, local
custody source, and intent819/recorda5d/receipt2fada schemas remain unchanged.
No native registration write, sender RPC, fake issued record, worker resource,
lease grant, physical machine or service operation has been executed here.

## Implemented source and exact API

Module: `grid.authority_assignment_v1`.

```python
UnqualifiedWorkerCommissioner(authority, generation, realm_id, *, root_custody)
async commission_unqualified_worker(original_intent_bytes, *, leader)
async reconcile_unqualified_worker(original_intent_bytes, *, leader)
```

PUBLIC METHODS CURRENTLY UNCONDITIONALLY RAISE
`SOURCE_PREPARATION_ONLY_EXECUTION_GATE_CLOSED` after local source/original
validation, BEFORE attempt append or RPC. No boolean, environment variable,
JSON role, provider, callback, private-path input or constructor option enables
them. Do NOT invoke private prepared routines to evade that gate. Gate removal
is a separate reviewed source successor, not implicit permission from this PR.

Exact actual ConsulSessionAuthority and RootRegistrationCustody only. Constructor
pins actual Core3dd source and captures actual owned client/config identities.
Requires isolated_lab, all literal loopback endpoints with explicit ports,
owned exact AsyncClient/AsyncHTTPTransport, trust_env=False, open client,
no redirects/auth/proxy mounts/event hooks and configured transport retries0.
Event hooks are excluded so callbacks cannot pre-read an unbounded body before
the sender's own bound or act as a provider. An arbitrary injected client is
not admitted. Same authority key, original/intent/custody and OS ownership are
rechecked. Root-only private allocation/ACL/exclusive lifecycle remains an
explicit operational prerequisite, not proven by local Journal or Python type.
Root must not concurrently reconfigure/close any of those objects in-flight.

## Prepared fixed native implementation — NOT executed

There is ONE stream call site. It selects ONE captured configured endpoint and
only fixed Consul paths for the five frozen RPC kinds; no arbitrary URL, header,
KV key or payload API. Every call first persists a fixed actual custody attempt
with endpoint hash, then checks ownership again. No Core._request wrapper or
endpoint/application retry. request_timeout covers stream+read, redirects false;
Accept-Encoding identity, reject compression/oversized Content-Length, accumulate
<=65536 raw body bytes in8192-byte yields, reject deep/duplicate/noninteger JSON.
This bounds sender accumulation, not every SDK/network-internal allocation.

Prepared flow retains original first, obtains consistent unfiltered generation,
leader, registration and lock in one four-get-or-empty native txn, validates
actual retained Core leader object/deadline and native generation/lock raw/
Session/index, then creates actual new native session with retained request Name,
TTL10s/release/LockDelay0/NodeChecks[]. Actual info ID/Name/TTL/Behavior/LockDelay
must match before metadata transaction. Native SID canonical any UUID version,
distinct from the leader; UUID or module label alone is never issuance proof.

Create-only seven-op txn: generation index; leader index+Session; absence of both
allocated registration keys; CAS0 permanent UNQUALIFIED record; lock with same
exact value and actual new session. Full plan measured <=64ops/32768bytes before
send. No positive enrollment/ledger/Assignment/storage keys are written. Record
always UNQUALIFIED/admitted[]/reservedfalse/effectfalse, no ACTIVE transition,
health/freshness/2.5s/time-at-Raft-commit claim or index-as-Assignment epoch.

Complete native200 txn result is required before retaining a known commit;
malformed/oversize/timeout/5xx/cancellation/maybesent result remains UNKNOWN.
Single409 is classified REJECTED only with bounded valid native operation-index/
error entries and no earlier mutation attempt permitted by custody. No rollback
or new SID/rekey/auto txn on unknown. Known commit is preserved even when later
observation/source retention fails. No automatic mutation continuation after
restart; existing mutation history selects readonly reconciliation only.

Reconcile joins native record to EXACT original AND the SID durably retained
by the fixed original's custody; absent SID => UNKNOWN, mismatch => CONFLICT,
never payload adoption. Permanent row must not itself be leased. Known historical
record is separate from missing/unknown lock/current info. No absent=>NOT_FOUND
or never-committed assertion. Current-as-of-read requires matching lock/value/SID
and actual native info policy read; it is observation DATA, not worker health or
permission. Read-only operations remain Root-only/current leader+generation and
native ACL protected, never generic READ_RESEARCH node disclosure.

Failure cleanup only the known new SID created THIS call, AFTER actual matching
session info, NO unresolved RPC attempts, and registration proven not sent or
single-definitively rejected. No cleanup through lost client/custody/source;
cleanup itself needs retained attempt. It NEVER destroys a possibly committed
registration session or adopts a SID from another process/local OS failure.
Logical retirement/replacement/rejoin remain unsupported separate contracts.

`UnqualifiedRegistrationObservation` is public frozen DATA with outcome,
original_registration_intent_sha256, mutation_status, session_observation,
resources_reserved=False/effect_permitted=False. Not receipt/capability/Root role.
No second broker, consensus cluster, queue or distributed SQLite authority.

## Current local verification and prepared future matrix

Five new LOCAL/structural methods: closed public gate/no send/attempt; actual
injected client and hostname endpoint refusal; rebound/closed/mismatched original
refusal; UNISSUED closed fourteen-field metadata builder and missing/mismatched
durable SID joins; one stream call site/no retry wrapper/redirects false. Actual
owned local Journal/kernel lock is used, but no server fixture starts and no
native RPC is made. Prior13 local/data methods rerun in the new18 driver; no
proxy2, native25, broker26, Root21/145 or physical PASS transfers.

Initial selected5 RED41a0a67e is owner-checkout missing-class provenance only.
Source review found a future-execution P2 durable-SID adoption gap; source join
fixed and pure FORMAT_ONLY negative regression added, not a native SID acceptance
claim. Malformed result/error shape checks tightened before execution review.
Current code paths beyond the closed gate have NOT been exercised on Consul.

`prepared_native_acceptance.py` contains public-API assertions only, no fixture
or bootstrap; direct script execution aborts before any RPC. It is NOT run.
Future actual own3-voter/default-deny ACL matrix requires explicit release:

| Future owned-native case | Required evidence | Current status |
| --- | --- | --- |
| New record+lock/real session, same-original readback | exact original/SID/raw/index7op txn, flagsfalse | NOT_RUN |
| Competing node slot/original/incarnation | no replacement/adoption, actual atomic rejection | NOT_RUN |
| Real restricted ACL/principal research token | denied/no disclosure/no registration | NOT_RUN |
| Native session-create lost response | one request, UNKNOWN/no new SID/no scan | NOT_RUN |
| Txn commit response lost/cancelled | actual row retained, UNKNOWN then readonly reconcile/no rollback | NOT_RUN |
| Leader/generation/session change at txn boundary | server check failure/no slot change | NOT_RUN |
| One-of-three partition and recovery | no cached success/unknown preserved/no mutation retry | NOT_RUN |
| Process restart/journal attempt/full/corrupt/source loss | retained original/UNKNOWN, no automatic new SID/txn | NOT_RUN |
| Large/compressed/deep/malformed/409 response boundary | bounded real transport/error classification, no destructive cleanup | NOT_RUN |

Remaining blockers: exact sender/source/API and native response-shape review;
Root/A5 final scoped commissioner ABI ACK; explicit isolated native execution
release; real above matrix+independent A8 verification. Entry activation must
serialize both operations for their full lifecycle including cleanup. Existing
Core/local-custody/broker ACKs do NOT approve these new native paths. Public
gate stays closed after review alone. Hosted/Linux/native writes NOT qualified,
production/physical/publicsubmit/effects NO-GO. No deployment/merge.
