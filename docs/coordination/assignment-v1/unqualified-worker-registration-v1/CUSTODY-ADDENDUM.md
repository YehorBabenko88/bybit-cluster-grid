# Custody and one-shot boundary — successor freeze candidate

Status: PROPOSAL, NO NATIVE RPC/WRITES IMPLEMENTED. The original c697 intent and
record schemas/codec/PROPOSAL.md remain byte-identical; A5's c697 identity ACK
does not become an ACK of this addendum. This addendum updates the earlier
pending one-shot/custody-primitive decisions, not the final API freeze.

Root approved registration-private ONE-SHOT mutation calls over the SAME actual
owned httpx client, one fixed existing configuration endpoint, existing bounded
request_timeout, NO redirect/endpoint/transport/application retry. No Core868,
LAN transport or authority/client replacement. Timeout/5xx/oversize/invalid or
otherwise maybesent responses remain UNKNOWN, never implicit rollback/retry.
Stream responses must be bounded before full allocation. A final409 is a
definitive rejection only for a proven single attempt with no earlier unknown;
otherwise UNKNOWN. Actual mutation/lost-response tests remain a later real
disposable Consul stage, not fake issued records or callbacks.

## Actual existing Root custody primitive

Verified actual Root3af Git object `unified_system/journal.py`, 3459 bytes,
SHA256 `9f170cf33f8cdd79baef6fa633d03bebf9eb4b594c54c9cf8dd6c7cb9810bbc3`.
The pinned Unified1f6 support contains the exact same bytes. Actual methods:
`Journal(path)`, `initialize()`, `read()`,
`append(state, receipt, *, expected_sequence=None)`. Outer states OBSERVING and
BLOCKED are existing states. This is SINGLE-WRITER local SQLite/hash-chain,
offline and NONAUTHORIZING, not distributed consensus, Root role, native source
ownership, current native session, permission or proof of an RPC outcome.

Use ONE separate exclusive Root-owned journal file per original registration,
selected by actual Root server configuration/lifecycle, not a request path.
Never mix A4 publication, direct job, generic audit or another original. The
adapter must require the exact fixed Journal class/source, not a callback,
duck-typed journal, JSON role or boolean. Journal itself does not establish file
exclusivity or Root ownership; actual Root exclusive lifecycle remains an
explicit prerequisite before any native RPC. Unknown ownership denies.
No A2 journal/storage engine is introduced or edited by this proposal.

## Closed receipt and budgets

`custody-receipt.schema.json` closes exactly twelve fields: schema,
original_registration_request_id, original_registration_intent_sha256,
original_registration_intent_base64, event, rpc_kind, rpc_attempt_id,
native_session_id, endpoint_sha256, outcome, resources_reserved,
effect_permitted. Literal schema is
`unified.authority.unqualified-worker-registration-custody.v1-review1`.
Exact original/request/digest and canonical base64 must join retained intent;
no self-hash. Both resource/effect flags ALWAYS false. None of these public
data fields establishes authority, known ownership or a successful native write.

Events: ORIGINAL_RETAINED, RPC_ATTEMPTED, RPC_RESULT. RPC kinds: NONE,
SESSION_CREATE, SESSION_INFO, REGISTRATION_TXN, CONSISTENT_READ, SESSION_DESTROY.
Outcomes: NOT_SENT, ATTEMPTED, CONFIRMED, REJECTED, UNKNOWN. Original is first
and exactly once, kind NONE/all RPC/session/endpoint fields null/NOT_SENT.
Each attempt has a fresh retained UUIDv4, hash of ONE fixed configured endpoint
(no token/header/credential in the journal) and ATTEMPTED outcome BEFORE send.
A result joins that exact attempt/kind/endpoint and known session; no orphan or
duplicate result. Session-create attempt/uncertain result has native SID null;
only its actually confirmed creation result may retain the actual new SID.
Native SID is canonical any-version UUID. Later mutation SID must match that
retained SID; no adoption from a caller PID, JSON or local OS owner-loss event.

Proposal budgets: original <=2048 canonical bytes; each receipt <=4096 canonical
bytes; <=64 total verified journal rows; main SQLite file <=1048576 bytes BEFORE
Journal.read. Existing Journal.read's own100000-row ceiling remains unchanged;
adapter rejects >64 rows or >4096-byte receipts before any RPC/append. It does
not claim a new small preallocation bound inside Journal.read. File size limits
the local payload; existing Journal's fixed row cap bounds its own read loop.
Reject symlinks/reparse ancestors, nonordinary/hardlinked file, foreign receipt,
bad hash chain, original mismatch or unknown ownership. Reject -wal/-shm/-journal
sidecars conservatively: preserve for explicit Root recovery, do not erase or
silently initialize/recover a foreign/hot journal. These local checks do not
prove exclusive ownership or physical disk survival under power loss.

New-file initialization is allowed only after Root has actually allocated the
exclusive owned file; NEVER initialize an existing foreign/unverified file as
if it were owned. Missing/full/corrupt custody prevents RPC, not a fresh journal
or request. No automatic deletion/repair/rename on corruption/restart.

Outer state ORIGINAL_RETAINED or reported CONFIRMED result is OBSERVING;
attempt/unknown/rejected is BLOCKED. These are local bookkeeping states, not
readiness or admission. Replay derives unresolved attempts from persisted rows:
an attempt without result, or result UNKNOWN, remains unresolved after restart.
SESSION_CREATE and REGISTRATION_TXN each occur at most ONCE for this original.
No new mutation after an unresolved mutation, and no registration after session
cleanup. Read-only reconciliation may record another bounded read attempt; it
does NOT retroactively rewrite the original RPC outcome or authorize retry.
Native committed record facts and transport outcome uncertainty must remain
separate. A known native row is not invalidated/refunded to make the journal
look unattempted. This custody codec stores local reports, not native proof;
actual native reconcile still has to rederive and verify all original/lock
bindings against the sole authority.

## Proposed adapter API and exact mutation sequencing

NOT implemented or frozen runtime API:

```python
RootRegistrationCustody(actual_journal, *, original_intent_bytes)
retain_original()  # synchronous actual append + expected_sequence
begin_rpc(*, rpc_kind, rpc_attempt_id, endpoint_sha256)
finish_rpc(*, rpc_attempt_id, outcome, native_session_id=None)
read_state()  # actual Journal.read + bounded replay; readonly DATA, no permit
```

The actual Root-only commissioner binds this exact owned adapter, exact Journal
source and original, rather than accepting arbitrary record dictionaries or
caller-supplied 'confirmed' results. Root exclusivity/source checks and adapter
implementation remain a separate freeze/review task. `custody_data.py` supplies
only proposed receipt validation/preflight/replay; it is NOT this adapter and
does not itself append records, send RPC or mint private custody proof.

Before EVERY native RPC, including session-info/consistent reads and failure
cleanup, retain its bounded attempt marker using expected_sequence. At every
capacity/retention/source failure, do NOT send. Before session/create, original
and its attempted marker must be durable. Before registration transaction, the
actual returned SID and transaction-attempt marker must be retained. A crash
at either attempted boundary is UNKNOWN; no automatic SID/rekey/retry.

If an RPC returns but result persistence fails, retain the prior attempted
marker and report UNKNOWN without claiming rollback. Failure cleanup may
destroy ONLY an owned known new SID after a provably unsent/definitively rejected
registration; it needs its own durable attempt marker. If that cannot be
retained, do NOT perform a cleanup RPC or pretend durable retirement. Actual
native cleanup may remain unknown; preserve ID/attempt/history and fail closed.
Never destroy a session because a transaction may have committed. No logical
retire/replace/rejoin operation is introduced by this failure-cleanup path.

Session-create policy candidate for Root decision, NOT accepted health/clock
policy: Name derived from retained registration request UUID, TTL10s,
Behavior release, LockDelay0s, NodeChecks[]. No claimed exact expiry instant,
worker health, clock uncertainty/max age, 2.5-second gate or effect lease.

## Verification and remaining freeze

Three NEW local tests use the ACTUAL pinned Journal on owned temporary SQLite:
restart/replay preserves unresolved session attempt and rejects repeated create;
closed receipt/original/budget/grant rejection; foreign valid-chain receipt,
actual hash corruption and oversized file refused. Prior six schema/codec tests
remain required. Nine-test successor qualification is reported separately;
neither six nor native25 predecessor PASS is transferred. No Consul processes,
native sessions, worker/attempt, physical nodes or issued records are created.

Initial new3 missing-custody-codec RED is owner-checkout provenance only. First
WIP9 found an owned test SQLite connection left open at cleanup on Windows;
fixed test connection with closing(), preserved failed log. Final primary raw
source qualification must use exact committed source and fresh clones.

Remaining gates: Root exact receipt/adapter signatures and actual exclusive
ownership/preflight contract, session-create policy, A5 ACK if identity semantics
change (the c697 identity schemas remain byte-identical), Root final freeze SHA.
One-shot boundary and existing Journal primitive are now approved in scoped
design; this DOES NOT authorize native writes before the remaining final freeze.
