# LAB network budget contract — proposed integration boundary

Status: deterministic model and simulator only. No socket, subprocess, database,
Windows configuration, physical load or production qualification is authorized
by this model. It is not a new Grid job authority or an activation grant.
**Reservation-only scope:** all byte counters are RESERVED/CHARGED synthetic
bytes. They are not observed transfers and do not prove an actual byte-rate
bound. The manager is not complete: the modeled lifecycle below still needs an authenticated durable meter and a native monotonic I/O adapter.

## Existing authority and source admission

The existing Grid CONTROL authority on LS5 owns one cluster research budget.
The eventual adapter must reuse the existing Grid database transaction and
`replicated_control_state` CAS with the exact `control-plane-leader` owner/epoch
and current lease. Its existing helper has no JSON size bound and permits an
unfenced call: the eventual adapter MUST enforce its own 131,072-byte canonical
state bound and bounded decoder and MUST always pass exact service fence and
expected version. The optional unfenced path is forbidden for network budgets.
If the selected existing Grid mode has no qualified current service lease, the
future adapter must deny budgeting; it must not manufacture an epoch or silently
fall back to unfenced writes. Legacy-mode lease readiness is an integration gate.
There is no separate scheduler, PostgreSQL instance or SQLite
job queue. Migration 50 was checked absent at base
`a70c165d8f1c001a9c79e196157d2bfd27b4e961`; no migration is needed for the proposed
bounded singleton JSON state, and no registry or SQL is changed in this stage.

Full source/activation admission and authenticated node/module capabilities
precede any eventual HTTP or WebSocket hook. Priority is derived from a closed
operation map for an admitted actor, never a request's `HIGH` string. The model
accepts only the six office node IDs; ADMINIT is excluded. Its actor tuples are
synthetic input, not authentication or transferable permission.
The modeled `ssh_control` operation means a managed control-message payload;
it does not meter, launch or prioritize an existing native SSH connection.
Only LS5 may initiate that operation. PC1, PC2, PC3, PC4 and LS7 cannot acquire
it, including by restoring a forged actor/category in saved model state.
External `github_fetch` and `module_update` operations are also LS5-only to
avoid simultaneous worker internet fetches; future worker distribution requires
separately admitted CONTROL-to-worker targets and pinned content.
The model groups non-WebSocket logical management operations in its bounded
`HTTP` resource category. Its counters are model categories, not evidence that
SSH uses HTTP, or that a physical TCP/SSH socket was measured or shaped. The
future adapter must bind every category to an actual closed transport operation.

## Provisional LAB defaults

- Research/history/dataset/update/GitHub/inter-node payload: one cluster token
  bucket, 1 MiB/s and 2 MiB maximum credit, initially zero.
- At most four unresolved HTTP connections cluster-wide, at most two LOW,
  reserving capacity for HIGH. Connection open and byte-read permissions are
  separate. Each read reserves at most 64 KiB before I/O; repeated chunks on one
  existing stream do not spend another HTTP attempt or require a reconnect.
  Failure or an uncertain response never refunds byte credit.
- Separate high-priority application payload allowance of at most 64 KiB/s per
  node, initially zero, with at most 64 KiB credit per node. This is a
  conservative reserved allowance, not measured WAN capacity.
- Managed HTTP opens share one conservative cluster paced bucket, five
  attempts/s, capacity one, initially zero; Bybit cannot escape this bound.
  At most three active public WebSocket connections are modeled, all on LS5
  for an aggregated ten-symbol feed, rather than a connection per instrument.
  WebSocket connects/reconnects share a cluster paced bucket, 20 attempts/minute,
  capacity one, initially zero. Failed attempts consume credit. No private or
  trading endpoints or order capability exist here.
- 128 pending network tickets maximum, at most 96 low-priority tickets and at
  most 16 low/eight high tickets per node. Queue backpressure refuses admission;
  it does not create another unbounded retry queue. High tickets precede low.

The maximum reserved aggregate payload rate is 1.375 MiB/s (research plus six
64 KiB/s high allowances), before bounded burst credit; this is provisional.
These are application payload/attempt bounds. Existing interactive SSH,
Tailscale and other
OS traffic cannot honestly be claimed shaped by a Python application model.
TLS/DNS/TCP overhead and native interface utilization require later observation;
the physical network has not been qualified. A future HTTP adapter must bound
headers, compressed/raw chunks, decompression output and total response size,
disable unbounded automatic buffering, and charge reads before I/O. All existing
public ingestion/history/update paths must eventually use the adapter; an
unmetered escape path blocks runtime acceptance.

## Persistence, idempotency and uncertainty

All counters, exact integer fractional credits, clock watermarks, cooldowns,
pressure state, bounded pending tickets, per-actor monotonic sequence highwaters
and unresolved connection leases are part of the serialized state. Reopening preserves
them; it does not allocate a fresh burst. A central restart/recovery discards
offline refill by explicitly reanchoring its watermark with zero credit.
Clock rollback latches a fault and issues no permits until explicit recovery.
Large forward jumps cannot mint more than one bounded refill interval.

An actor sequence must be the next sequence; a duplicate still-pending or
unresolved ticket must match its original immutable operation/byte request and
does not consume a second reservation. Older finalized sequence numbers are
rejected rather than accumulated as unbounded tombstones. A later local durable
network meter must record debit-before-read and make a replayed central receipt
unspendable twice. This local state is a meter, never Grid work ownership.

Permit expiry marks uncertainty; it never frees a bulk connection slot or
refunds credit. Only explicit confirmed transport close for the exact permit
can release the slot. Missing or ambiguous close results stop that lane. A new
authority epoch inherits unresolved permits; it cannot overlap them by restart,
lease expiry, or a new identifier. No model receipt is a wire credential.

### Read lifecycle v2: modeled fix, actual transfer bound NOT PROVEN

Stage 1's public-API counterexample accumulated seventy unused 64 KiB read
receipts and allowed delayed first spending. That exact source remains in
commit `97a0c9787df8907334b364912eb4946ea18af85a`; it is not wire-safe.
The v2 model fixes that modeled lifecycle as follows:

- `open(node,module,operation,actor_sequence,now_ms=...)` queues only a closed
  admitted operation. `read(node,module,connection,bytes,actor_sequence,...)`
  binds a chunk to its exact existing transport owner.
- A READ receipt includes immutable actor, connection, actor sequence,
  `read_id`, strictly increasing per-connection `read_sequence`, `issued_ms`,
  and `expires_ms = issued_ms + 500`. There is at most one pending OR
  outstanding read per connection; duplicate identical ticket delivery does
  not create another grant or byte debit.
- `consume_read(node,module,connection,read_id,read_sequence,now_ms=...)`
  checks exact internal state, live connection, next per-connection sequence,
  and first spend strictly before expiry. It transitions ISSUED to IN_FLIGHT.
  A copied JSON receipt is never sufficient authorization.
- `complete_read(...,confirmed_stopped=True,now_ms=...)` retires that read only
  after modeled I/O completion. It never closes or frees the connection.
  Re-consuming a consumed/completed/expired read fails. False or uncertain
  completion invalidates the grant and marks the transport uncertain.
- Expired ISSUED credit is consumed without refund and cannot be first-spent.
  Expired IN_FLIGHT credit invalidates the grant and poisons its transport;
  the connection slot remains occupied until confirmed actual transport close.
  Connection close, uncertainty and restart invalidate pending/outstanding read
  spendability. Restore preserves credit and slot counts but marks old
  connections uncertain; their survival is never assumed from JSON.
- The state schema is v2. Stage 1 saved models are rejected rather than silently
  upgraded into spendable grants. The simulator explicitly confirms old modeled
  transport closure before reopening after restart.

The public regression now collects the same seventy unused receipts, with no
real I/O, and proves all older first spends rejected; only a current, unexpired
single reservation can be consumed. Model issuance remains bounded by the
research token bucket and per-node HIGH credits. At most seven outstanding
64 KiB reservations exist, giving a conservative additional reservation envelope
of 458,752 bytes over the 2 MiB research burst, before in-flight overhead.
This is a model bound, not an observed transfer or physical socket proof.

**Open P1:** actual authenticated source/actor admission, fenced durable SQL and
local consumption acknowledgment, single-use local meter, native monotonic
read/decompression deadline, compressed/raw/header/total-response caps and no
offline prefetch remain unimplemented. A real adapter must prevent all I/O
after expiry, confirm completion before another read, and conservatively account
for in-flight bytes; server wall-clock fields alone cannot prove that. Root must
approve the server/local-meter/I/O contract before SQL integration or I/O.

## Degradation, outage and recovery

Closed observations include DNS latency/failures, gateway latency, HTTPS
latency, packet loss, TCP failure, Bybit status/rate limit feedback, interface
utilization, pending depth and active bulk permits. Samples are bounded and
their provenance remains synthetic in the simulator.

Three bad observations enter DEGRADED. LOW work is paused immediately on an
explicit authority outage or a rate-limit cooldown. DEGRADED pauses history and
updates; live/health/heartbeat traffic uses only its bounded reserved allowance.
Ten good observations enter RECOVERING with quarter research refill; ten more
good observations restore NORMAL. Any new bad observation returns DEGRADED.

When LS5 is unavailable, no new bulk/history/dataset/update/sync permit is
issued. Already connected live/monitoring can use only its preallocated bounded
node allowance. Any fallback meter recreated without trusted persistent state
starts at zero; a restart cannot refresh that allowance. Recovery is explicit
and gradual, with no refill for elapsed outage time.

Bybit 403 pauses Bybit public HTTP across every node for at least ten minutes;
the model marks its existing HTTP sessions uncertain. The eventual adapter must
actually terminate all owned Bybit HTTP sessions and confirm transport closure
before releasing slots. Internal health traffic is not an exchange session.
429 uses at
least 60 seconds or a larger bounded Retry-After/server reset value. New
feedback can extend but cannot shorten persisted cooldowns. WebSocket failed
attempt pacing remains shared, including during recovery. Exchange guidance is
an upper ceiling, not permission to raise these provisional LAB defaults.

Official [Bybit rate-limit guidance](https://bybit-exchange.github.io/docs/v5/rate-limit)
was checked on 2026-11-05: HTTP defaults are 600 requests per five seconds per
IP; WebSocket attempts are limited to 500 connections per five minutes. It also
requires closing HTTP sessions and waiting at least ten minutes after the IP
403 frequency block. The LAB defaults remain substantially below these limits.

Current status: NOT_WIRED. Existing `archive_download.download_verified`, Bybit
session/discovery, Worker WebSocket and other real network paths are not changed
by this model. Their complete protected integration remains mandatory. A future
DataFirst child must request budgets through the existing closed fenced parent
IPC; environment JSON is not a grant and no second queue authority may appear.

## Review and acceptance gates

1. TDD deterministic state machine and six-node/ten-symbol simulator: byte and
   attempt envelopes, bounded queues, live priority, simulated latency/loss,
   LS5 loss, Bybit outage/cooldown, module restarts, clock rollback and recovery.
2. Root reviews this contract before SQL, routes, capability/authentication,
   local durable meter or ingestion hooks are implemented.
3. Actual disposable PostgreSQL transaction/restart/fence tests; authenticated
   transport and raw bounded HTTP/WS adapter tests; source admission integration.
4. Separate reviewable physical plan and owner confirmation before any office
   change or load. No DNS/firewall/Tailscale/NIC settings, security policy,
   credentials, real orders or Reolink changes belong to this direction.
