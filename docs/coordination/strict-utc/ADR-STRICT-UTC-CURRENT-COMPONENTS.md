# ADR: strict commit UTC is unavailable in the current authority boundary

Date: 2026-11-10. Status: CURRENT-COMPONENT IMPOSSIBILITY ARGUMENT / OWNER REVIEW REQUIRED. Operational decision is unchanged: logical mutations DISABLED, public submit DENY. This is not a replacement time policy, a native positive result or an approval to modify Consul. Executable countermodel and seven model tests accompany this ADR; no Grid/Consul/worker module is imported by them.

## Requirement and exact scope

For each accepted protected logical mutation m with immutable expiry E, require its real consensus-commit instant C(m) < E (strict equality rejects). A known commit fact, knowledge of C(m), and current eligibility to disclose or perform a later effect are distinct. No sender/receiver/ACK/application timestamp substitutes for C(m). Unknown time remains UNKNOWN even if actual committed bytes are known. A public reader denial cannot erase that history.

The claim is scoped to the currently inspected vanilla Consul1.22.2 transaction/session API, its pinned Raft1.7.3 dependency, Grid native index/session transactions and current Unified broker327a3e2/module481724. No qualified bound on actual UTC clock error, quorum/network/scheduling delay or session invalidation completion is supplied. The argument assumes a finite-expiry mutation is actually submitted; always denying is safe but supplies no positive admission. It does NOT claim every conceivable consensus architecture or modified protocol cannot supply a stronger time guarantee.

Model-code branch base Grid2f94 is only an existing negative/local source reference; it is NOT an approved new HA runtime assembly. No runtime file is changed. Fixed profile-v2/lossless T20/N13 identities are untouched. Shared schemas/rights/capture and actual resource/consume/start/publication interfaces remain unapproved or NONE.

## Evidence from current components

1. [Consul1.22.2 transaction verbs and request/response fields](https://github.com/hashicorp/consul/blob/v1.22.2/api/txn.go) contain session/index/CAS/absence operations and returned values/indices; no KV UTC-before-deadline predicate or trusted consensus commit-time certificate is exposed. A timestamp supplied as Value is caller data.
2. [State transaction implementation](https://github.com/hashicorp/consul/blob/v1.22.2/agent/consul/state/txn.go) applies the operations in its state transaction. [Session predicate](https://github.com/hashicorp/consul/blob/v1.22.2/agent/consul/state/kvs.go) compares the stored lock session; matching session and index do not compare a policy row's expires_utc against real UTC.
3. [TTL implementation](https://github.com/hashicorp/consul/blob/v1.22.2/agent/consul/session_ttl.go) uses a timer/grace multiplier and then submits a separate session-destroy operation through Raft, with retries. Its documented contract provides no expiry-completion upper bound. Invalidating before a transaction in consensus order can fence it; merely reaching a local deadline does not establish that order.
4. [Transaction endpoint](https://github.com/hashicorp/consul/blob/v1.22.2/agent/consul/txn_endpoint.go) authorizes/submits operations and returns their result. Time spent handling a request is not its consensus instant. [Consul go.mod](https://github.com/hashicorp/consul/blob/v1.22.2/go.mod) pins Raft1.7.3; [Raft API](https://github.com/hashicorp/raft/blob/v1.7.3/api.go) supplies asynchronous apply/result behavior, not a qualified UTC expiry condition for this KV transaction.
5. Actual Unified `gateway_research_identity.py` at327a3e2, SHA256481724cd2efca312773fa4152d1c223b46ced6529d96b2d74f452cdf57932d7f, requires profile expiry_semantics=NATIVE_SESSION_INVALIDATION_NOT_UTC_AT_COMMIT. Local UTC+monotonic checks and final capture validation bound local eligibility; they neither alter a previously submitted Raft transaction nor implement the newly required strict semantics. Rewriting that label would change P/S/N13/D, not add enforcement.

Source tags are inspection pins, not a certified executable environment. Artifact receipts retain source retrieval hashes where available; the model does not execute upstream code. Earlier failed attempts to locate optional FSM source paths are not evidence of absence. This argument relies on the actual inspected public KV/session boundary and state/TTL implementations above, not on those404 paths.

## Counterexample with even perfectly observed local UTC

Take real UTC coordinates purely as model symbols: last local check/send at1, immutable expiry5, native session invalidation only at10. Generation/leader/session/index/current policy bytes and expected ledger/CAS remain unchanged. They need not change merely because a policy timestamp passes. Session being present at6 is permitted, including when a policy expires earlier than its native session. No clock skew is needed.

Execution A: quorum commit at2, state application at6, reply observed at7.

Execution B: quorum commit at6, state application at6, reply observed at7.

Native value/index/session/receipt bytes and all client-visible checks/observations can be identical. Client precheck at1 passes in both; native session/index predicates pass in both; response-side current reader check at7 denies in both. A is before expiry; B is not. Moving client checks closer to send only moves the last finite check: an unconstrained remaining network/quorum/scheduling delay can cross E afterward. A finite local timeout does not cancel a Raft operation already accepted by a server. A separate expiration/watchdog mutation may itself be delayed and ordered after m.

The model abstracts event scheduling and unchanged native predicates. Its author-supplied C values are ground truth of the constructed executions, not discovered timestamps, native logs or a minted certificate. For native session revocation-before-m, the model rejects; for delayed revocation-after-m, it accepts a late mutation. Thus session fencing can be correct in consensus order while the stronger UTC deadline is not guaranteed. This does not allege split-brain, broken Raft safety or two simultaneous valid leaders.

Indistinguishability is at the submitted transaction boundary and, with delayed reply in A, the complete modeled client observation. Any client-only policy using those same observations cannot prevent B's state change after send. Post-reply rejection, compensating cancellation and refusing an external effect do not retroactively remove that mutation. No automatic quota rollback or retry is permissible.

## Why common substitutions do not discharge the requirement

* ACK/observation time is later than a commit, not its instant. With an independently trusted bounded UTC observation one could sometimes prove an upper bound for a previously committed operation, but that is extra evidence, not equality. Observing too late remains ambiguous and cannot prevent an already late commit. Current qualified evidence is absent.
* Apply time differs from quorum replication and leader commit-index advancement. The operator must pin which consensus commit definition is required before any new protocol is approved; the counterexample can put all possible commit events after expiry in the late execution. A known state receipt proves accepted state, not a precise instant for those events.
* TTL, heartbeat, process quiescence and lease/index revisions establish other facts. A low TTL or2.5s budget cannot supply an upper bound absent clock/error/quorum scheduling assumptions and an enforcement mechanism at the chosen event.
* A separate replicated time marker/revoke is still another ordered operation that may be delayed. Index-before-expiration-marker establishes order, not UTC-before-E. Writing a signed local timestamp into the same transaction certifies only the timestamp's own specified observation, not later consensus commit.
* Checking wall time independently during deterministic FSM replay risks different decisions unless an explicit deterministic certified-time protocol is supplied. Current vanilla KV ops do not offer that hook. Adding a leader local pre-append check still leaves a later quorum delay.

## Formal scoped conclusion

Assume (a) at least one finite-expiry mutation can be submitted, (b) the only native acceptance predicates are the current state/index/session/CAS predicates, (c) no proven upper bound forces quorum commit or ordered revocation before E, and (d) there is no commit-bound trusted UTC predicate/certificate enforced by the authority. An admissible scheduling delay after the last precheck, while native predicates remain unchanged, permits C(m)>=E with successful native state mutation. Therefore those components and assumptions do not provide both nontrivial positive admission and the required universal strict UTC safety. Disabled admission is the current safe policy. This is a current-interface argument, not a universal impossibility of time-aware consensus.

## A separately versioned strict-protocol decision would need

Do not implement this list as a purported working protocol. These are prerequisites for a new owner-reviewed architecture, remaining within the ONE existing authority (no second election):

* Exact commit/linearization event and its relationship to durable log replication, leader learning and domain-state application, including failover/replay/restore.
* A trusted real-UTC uncertainty model, evidence provenance and failure policy, with rollback/suspension/leap/error and resource contention bounds. Current OS wall/monotonic readings and NTP presence are not a proof.
* A deterministic authority-enforced mechanism tying that event to an expiry upper bound, including quorum/replica certificates and serialization/durability semantics if the architecture uses them. A native-source/protocol extension would require explicit approval, not a client or JSON workaround.
* Rejection/UNKNOWN behavior when assumptions fail; no late state admission, automatic refund, original replacement or old-policy conversion. How any proposed pre-expiry proof remains valid through quorum delay and actual application must be demonstrated, not assumed.
* Bounded model/protocol proof and actual independently reviewed native/security/time-fault acceptance before a positive disposable job. No such approved mechanism exists in current source.

Option2 is not selected. Operator must approve any separate architectural revision. Until then commit UTC knowledge remains UNKNOWN, known native history remains retained under current access rules, logical mutations/public submit stay disabled, and actual positive resource/start/publication/scientific-read APIs remain blocked.

## Executable technical result and scope

Run with stdlib only:

`python -I -B tests/coordination/strict_utc/test_countermodel.py`

`python -I -B docs/coordination/strict-utc/countermodel.py`

Seven tests cover identical observations with early/late commits, retained known commit with public denial, strict equality boundary, revocation order, finite margin delay, commit/apply/ACK distinction and the disabled zero-send contract. These are MODEL_ONLY results. They neither instantiate a Consul cluster nor prove current native behavior empirically. No sockets, native sessions, worker/Job, services, office nodes, protected diagnostic, browser or provider is called. Original test-first missing-model failure is retained separately; it ran zero tests with one setup error, not seven failing runtime contracts.

Safe source-preparation can continue on agreed owned negative handlers/schema/custody paths with A5 while preserving this gate. No new shared rights/ABI, runtime assembly or actual positive admission is conferred by this model or ADR. Native positive RPC/private commissioner remains prohibited until Root's serial strict-time/security gates are actually satisfied.
