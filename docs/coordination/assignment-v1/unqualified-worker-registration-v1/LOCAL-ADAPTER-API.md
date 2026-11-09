# Implemented LOCAL Root registration custody

Actual module: `grid.authority_assignment_v1`. This source successor implements
LOCAL custody only. No native RPC, Consul session creation, registration write,
worker enrollment/permit or job/resource/effect grant is implemented or run.

```python
RootRegistrationCustody(actual_journal, *, original_intent_bytes)
retain_original()
begin_rpc(*, rpc_kind, rpc_attempt_id, endpoint_sha256)
finish_rpc(*, rpc_attempt_id, outcome, native_session_id=None)
read_state()
close()
__enter__() / __exit__(...)
```

All methods are synchronous, fixed class methods over the ACTUAL exact
`unified_system.journal.Journal` source SHA9f170cf33f8cdd79baef6fa633d03bebf9eb4b594c54c9cf8dd6c7cb9810bbc3.
No custom Journal/lock/provider/callback or JSON ownership flag is accepted.
Frozen b513 intent/custody predicates are promoted as STATIC runtime code;
runtime does not execute/import mutable docs as a provider. The original docs
schemas/codec are unchanged. Prior12 existing module definitions retain exact
ASTs; no native25 regression PASS is transferred to this local-only source.

Root must supply a fixed server-selected absolute canonical private local
Journal path and own its private ACL/lifecycle. These are explicit prerequisites,
not established merely by the Journal, filelock, node label or constructor.
No public HTTP/Gateway caller path or role grants Root custody/worker rights.

## Actual OS exclusion and file binding

Lock path is derived ONLY from the actual Journal path by appending
`.registration-owner.lock`. Windows uses nonblocking `msvcrt.locking` of byte0;
Linux uses nonblocking `fcntl.flock(LOCK_EX|LOCK_NB)`. The lock descriptor is
retained throughout the adapter lifetime, never inherited through exec, and is
released by close/process exit. It is independent of SQLite transaction locks
so fixed Journal's own new connections can operate. Persistent lockfile is
NEVER unlinked, preventing normal unlink/recreate lock-splitting.

Lock and DB ordinary file identities are bound to open descriptor device/inode,
single link count, canonical path and an exact bounded header containing original
digest and DB identity. Root path ancestors must not be symlink/reparse entries.
Windows requires a fixed local drive. Linux matches actual device major/minor
against mountinfo and accepts only the explicit local filesystem allowlist;
unknown/network types fail closed. This is not permission to alter mounts.

A new DB is created with exclusive OS create ONLY after obtaining the kernel
lock and only that newly allocated file may be initialized. An existing DB
without the matching persistent lock header is refused, including empty or
foreign initialized SQLite. Existing matching file is read, never reinitialized;
bad chain/domain/original/empty history, changed header/path/identity, hardlinks,
reparse/symlink, sidecar entry or exceeded budget prevents append. Unknown/
partial constructor state is preserved for explicit Root recovery, not adopted.

This excludes cooperating Root owner processes using this adapter. It does not
establish a Root credential, native ACL, HA lock, writer lease, qualified worker
or defense against a privileged local process bypassing private ownership and
writing/unlinking files directly. No OS PID is persisted as a worker identity.
Forked/inherited object use and copy/deepcopy/pickle are denied.

## Actual custody sequencing and cleanup

`retain_original` must precede all attempt markers. Actual Journal append uses
expected_sequence, full verified replay and file checks before/after append.
`begin_rpc` only records an attempted phase and does NOT send anything.
`finish_rpc` only records a LOCAL report and is NOT native outcome proof; a
non-SESSION_CREATE supplied SID mismatch is rejected rather than normalized.
No arbitrary record dict is a method input. Retained unknown attempt survives
restart and prevents automatic new create/transaction/rekey or cleanup-as-rollback.
Budgets remain original2048B/receipt4096B/64rows/DB1MiB, no sidecars.

`read_state` returns public readonly-by-convention DATA, with
resources_reserved=False/effect_permitted=False. It is not an opaque capability.
The adapter enforces transitions against the fixed actual Journal, not a caller
modified copy of this dictionary. Actual native RPC sender/source checks and
Root/A5 scoped actual-custody ABI ACK remain prerequisites before native tests.

Use with a context manager; close is idempotent and releases both owned file
descriptors. A close failure is reported, but cannot replace an original body
exception: it is added as an exception note. On constructor failure descriptors
are closed while preserving original failure. No file is deleted or repaired.
Missing/closed/foreign-process ownership rejects access. There is no claim of
exact physical power-loss durability or native confirmed retirement.

## Actual tests and limitations

Three new actual local adapter test methods exercise:

- OWN second process denied nonblocking while parent holds the lifetime lock,
  before any append; same DB records unchanged. A separate OWN process acquires
  after close. Both bounded child processes use the same qualified interpreter
  and exact source, no native RPC.
- Context/error preservation, idempotent close, copy/pickle denial and restart
  with unresolved attempt/no automatic create. A pure close-report fault after
  actually closing owned handles proves original exception retention. A LOCAL
  UNISSUED format-only SID report tests result mismatch rejection; no actual
  Consul SID, worker, job or permission is fabricated/claimed.
- Existing foreign DB, mutated Journal path, actual owned sidecar and actual
  hardlink refuse before append. True OS reparse attack qualification is not
  inferred from source checks or these test cases.

Final twelve-method exact-source qualification includes the prior9 data/local
Journal cases rerun, not9+3 arithmetic. Independent review identified oneP2:
finish_rpc silently ignored a mismatching optional SID. Regression reproduced
the missing rejection then passed after the source fix; original logs retained.
Initial new3 missing-class RED is owner-checkout provenance only. Existing
Windows/Linux workflow runs the new12 driver; hosted/Linux PASS unclaimed.

Root has approved the TARGET data/API/TTL10s release/LockDelay0/NodeChecks[] policy
without health/age/2.5s guarantees. Actual local adapter/exclusive-owner/source
review and Root/A5 actual custody ABI ACK must be captured before executing any
native registration mutation qualification. No Core868 change in this source.
Its owned httpx client currently uses default trust_env=True; Root reproduced
proxy routing on harmless own-loopback GET. A SEPARATE explicit Core successor
and proxy-isolation qualification is required before future registration writes.
Literal loopback URL alone is insufficient; do not treat current environment
inspection as proof that an existing client captured no proxy. No global env,
network/firewall/service/provider changes, deployment or merge. NO-GO.
