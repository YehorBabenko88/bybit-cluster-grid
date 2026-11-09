# UNQUALIFIED worker registration v1 — freeze candidate

Status: PROPOSAL / ROOT_FINAL_FREEZE_PENDING / NO_NATIVE_WRITES. Root approved
only the namespace and direction, with additional custody/UNKNOWN constraints.
This package implements pure DATA encoding/schema contracts only. It does not
add a commissioner, native session, permission, storage journal or worker grant.

## Exact closed data and encoding

`intent.schema.json` has exactly nine fields: schema, operation, cluster_id,
cluster_generation, realm_id, node_id, worker_inventory_incarnation_id,
worker_module_sha256, original_registration_request_id. Schema literal is
`unified.authority.unqualified-worker-registration-intent.v1-review1`; operation
is `COMMISSION_UNQUALIFIED_WORKER`. Six identity/request fields are canonical
lowercase UUIDv4. Module SHA is exactly 64 lowercase hexadecimal characters.
Root generates and durably retains the request ID and original bytes BEFORE
any session RPC. The intent contains neither a native SID nor its own digest.

Use unchanged runtime C3 canonical encoding: printable ASCII strings, sorted
object keys, no whitespace/newline, no duplicate keys/numbers/nonfinite values,
depth <=12 and <=16384 encoded bytes. Original intent digest is lowercase
SHA256 of those EXACT bytes. No decoding/re-encoding/rekey on retry. The pure
`contract_data.py` parser requires canonical bytes and the closed schema.

`record.schema.json` has exactly fourteen fields: schema plus the seven bound
identity/module/request fields, original_registration_intent_sha256,
native_session_id, registration_state, admitted_fields, resources_reserved,
effect_permitted. All seven bound fields must equal the retained original.
Record schema literal is
`unified.authority.unqualified-worker-registration.v1-review1`.
The digest must equal SHA256(original intent bytes); the native SID is an actual
Consul-issued canonical lowercase UUID of ANY version, not a caller UUIDv4.
Codec validation alone does not prove that Consul issued it: native session info
and exact lock Session/value joins remain mandatory in future implementation.
State is ALWAYS `UNQUALIFIED`, admitted_fields ALWAYS [], resources_reserved
ALWAYS false and effect_permitted ALWAYS false. No operation in v1 upgrades it
to ACTIVE, changes capacity or issues a qualified capsule/permit.

Node UUID is a Root-selected DECLARED label, not a physical computer identity.
worker_inventory_incarnation_id is A5's module-inventory UUID; reload can change
it within one OS process. It is not PID/creationFILETIME, OwnedAttempt UUID,
clock observation incarnation, native SID or Assignment epoch. Worker module
SHA identifies bytes, not retained-image custody. A5 source pins85b and60c1 are
distinct; no automatic upgrade. Clock max age, uncertainty and the proposed
2.5-second reserve are NOT adopted or encoded here.

## Allocated keys and proposed native boundary

L = `unified/<clusterUUID>/runtime-v1/research-lab-v1/<realmUUID>`.
Only new keys are `L/workers/<nodeUUID>/registration-v1` and that key + `/lock`.
No alias of positive enrollment/policy/ledger/Assignment keys. Node slot is
CREATE-ONLY. Another request, incarnation, module or SID conflicts; even the
same original does not authorize creating another SID. No implicit replace,
delete, adoption, renewal-health claim, logical retirement or rejoin API.

Proposed fixed methods (NONE implemented by this package):

```python
UnqualifiedWorkerCommissioner(authority, generation, realm_id, *, root_custody)
async commission_unqualified_worker(original_intent_bytes, *, leader)
async reconcile_unqualified_worker(original_intent_bytes, *, leader)
```

The exact existing Root custody source/type and its fixed attempt-retention API
must be pinned by Root before this constructor/API can be frozen or native
writes implemented. `root_custody` is NOT a caller callback, JSON, bool, duck
type or new A2 ledger. It must be an actual Root-owned adapter to existing
durable original/attempt custody. A2 must check that fixed source, not accept
method presence as proof. Missing custody denies before session creation.
Root custody must atomically exclude concurrent attempts for the retained
request/node and record attempt-before-session-send, known SID, and
attempt-before-transaction-send. Unknown outcomes survive crash/restart and
must not become a fresh unattempted request on reconstruction.

Commissioner is internal Root-only and native-ACL protected, using the existing
owned Consul authority, current Grid leader and generation. Gateway principal
context, READ_RESEARCH, SUBMIT_RESEARCH and caller JSON roles are NOT admission
to worker/node metadata. Initial inspect/reconcile is ONLY Root-internal with
current leader/generation, original registration bytes and native ACL; no
generic lab13 READ endpoint is added. Reconcile returns readonly observation
DATA, never a lease/capability. It must retain known historical record facts
separately from unknown/absent current lock; no NOT_FOUND/never-committed claim.

Create a NEW owned native session distinct from leader/principal sessions;
retain its actual ID in Root custody before any registration transaction.
TTL/session-create policy is still a freeze decision: no TTL value or local
deadline here asserts worker health, resource freshness or UTC-at-commit.
Proposed transaction checks current generation index, leader index + Session,
absence of both allocated keys, then CAS0 registration and lock with the actual
new session and EXACT SAME canonical record value. Session info must join ID;
the native lock operation validates that SID at the transaction boundary.
Every actual full plan must be measured <=64 operations/32768 encoded bytes
before send, including all custody-approved native predicates. No standalone
registration index is an Assignment revision, resource fence or lease epoch.

## Mutation retry boundary — explicit freeze decision

Core868 `ConsulSessionAuthority._request` retries endpoints after timeout,
HTTP error or 5xx for ALL methods. Its last409 therefore is not necessarily a
definitive single-send rejection: a previous attempt may have committed. A
session/create retry can also create an earlier unknown SID. This is harmless
to this package's NO-RPC pure tests and is not a defect claim against the
existing539 read-only negative handler, but cannot be ignored for new writes.

Propose a registration-private ONE-SHOT mutation call using the SAME existing
owned actual httpx client/transport, ONE configured Consul endpoint and existing
request_timeout, with NO endpoint retry. Do not edit Core, LAN transport or
create another client/election/authority. Root must explicitly approve this
boundary. Consistent reads may reuse the existing endpoint-failover reader.
If one-shot provenance cannot be established, a409 after a retry is UNKNOWN,
not permission to destroy a possibly committed session or start again.

## UNKNOWN and cleanup matrix

| Stage / observed event | Honest result | Allowed cleanup / next action |
| --- | --- | --- |
| Original/attempt retention or current leader/gen preflight fails before RPC | NOT_SENT | No SID/RPC; retain audit; no fabricated attempt |
| Session create definitely not sent | NOT_SENT | No SID; explicit Root custody decision only, never implicit retry |
| Session create may have been sent, response lost/timeout/5xx | UNKNOWN_SESSION_CREATION | Preserve original + attempted latch; no new SID, name scan, adoption or rekey |
| Actual new SID known, durable SID retention fails before any txn send | REGISTRATION_NOT_SENT | Bounded destroy ONLY that owned known SID; failed destruction remains UNKNOWN; do not erase known SID |
| Txn-attempt retention fails before any txn send | REGISTRATION_NOT_SENT | Same owned-SID-only cleanup; retain original/audit |
| One proven first txn send returns definitive409 and no earlier send exists | REJECTED | May destroy ONLY known new SID; preserve rejected original and outcome |
| Txn may have been sent, response lost/5xx/invalid or ambiguous/retried409 | UNKNOWN_TRANSACTION | No automatic invalidation-as-rollback/newSID/rekey/retry/refund; reconcile same original |
| Structurally valid native committed txn confirmed, later read/custody write fails | COMMITTED_FACT / OBSERVATION_UNKNOWN | Preserve possible/known committed facts; NO destructive rollback; no effect grant |
| Record matches original but lock/session is absent/unknown on later read | KNOWN_UNQUALIFIED_RECORD / CURRENT_SESSION_ABSENT_OR_UNKNOWN | Keep historical row and original; no recreate/adopt/replacement or grant |
| Read lacks quorum or source/current leader/generation cannot be verified | UNKNOWN / unavailable | No cached success or node disclosure; preserve custody and historical facts |
| New incarnation/request/module encounters occupied node slot | CONFLICT | Never replace/delete/adopt or reinterpret old original |
| A5 local OS owner dies/restarts | NO_AUTHORITY_TRANSITION | No A2 session destroy/job change/hold refund from OS evidence alone |

Destroying a known session after a provably unsent or definitively rejected
registration is failure cleanup, not a logical retire/replace/rejoin API.
Those operations require a separate closed contract with exact old raw/index,
native SID and lock Session checks, unknown recovery and history preservation.
Do not infer safe retirement from a TTL, process observation or arbitrary JSON.

## Pure verification and review gates

Six pure contract methods cover acyclic closed original/canonical bytes,
duplicate/noncanonical/numeric rejection, exact original-record digest/identity
joins, native UUID any-version versus UUID4 labels, no upgrades/resources and
only the allocated key pair. They create no session, KV, positive records,
capacity observation or effect. Independent source qualification is separate;
no539 native25 PASS count is transferred to this proposal. Initial RED7b07e57c
was six missing-codec FileNotFoundError cases in the owner checkout, NOT a full
fresh primary source-qualified RED. Preserve that limited provenance.

Freeze checklist: Root exact schema/API SHA, actual Root custody source/type,
one-shot mutation boundary and native session-create policy; A5 ACK of exact
identity-field separation. Until these are explicit, NO native registration
write implementation, no worker proof and no public API. Existing Grid remains
sole authority; all job/resource/publication/effect gates remain closed.
