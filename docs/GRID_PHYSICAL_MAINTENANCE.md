# Grid physical maintenance and independent evidence

This package prepares read-only observation and offline acceptance. **Physical S0
NO-GO; all20 G1 phases BLOCKED/null argv; Execute/Cleanup NOT_AUTHORIZED;
Deployment NO-GO.** No commands in this document have been run on LS5 or PC4.

## Source and trust boundary

Review base: PR244 `7aed9c1cedb567fd7df82d9e449a54c5cc31b2c4`. This is a separate
branch and PR. Later PR244 diagnostic commits are not silently incorporated.
The collector reuses the existing native `GridS0.TokenObserver` from the original
source-pinned S0 DLL; it never compiles native code on an operator computer.
The independent S0 consumer is `tools/s0_independent_acceptance.py` (requirements
version7, Core20 + Runtime2). No Grid runtime, trading plugin, dotenv reader,
PostgreSQL client, installer executor, remote executor or cleanup executor is
imported by the maintenance collector.

A checksum detects substitution relative to an independently obtained pin; it
is not a signature, owner authorization, executable custody proof or anti-rollback
service. Every source HEAD/tree and artifact digest must come from a separate,
reviewed channel. The collector reports supplied HEAD/tree as expected context;
its source gate stays BLOCKED until its hashes are independently compared with
Git blobs. Never treat caller-supplied SHA as authentication.

## Owner-reported starting state (not fresh observations)

| Host | Report | What the tool can verify | Limit |
|---|---|---|---|
| LS5 | ProgramData Grid tree removed | fixed-path metadata/absence at observation | not exhaustive disk cleanup |
| LS5 | two Grid DBs removed | no SQL is issued | DB catalog gate BLOCKED |
| LS5 | two old firewall rules remain | candidate rules, enabled and disabled, hashed identities | ownership and deletion BLOCKED |
| PC4 | C:\GridLab removed | fixed-path metadata/absence at observation | not other volumes/profiles |
| PC4 | PostgreSQL18 preserved; no Grid DBs reported | service metadata only | no DB access or adoption |
| PC4 | GridS0-G0-TokenObserver must remain | exact task-name classification | always PRESERVE |

Neither a matching name nor an empty list establishes ownership. No auto-removal,
`DROP`, firewall Apply, account action, task disabling or process termination is
implemented. An AccessDenied/API failure is unknown, never absence. Reparse
ancestors stop fixed-path traversal. No descendants are recursively enumerated.
ProgramData/Program Files themselves are never changed.

## Operator sequence (review before any physical use)

Run these from an independently verified protected checkout. A writable checkout,
shared TEMP or untrusted ZIP is a STOP. The developer workstation identity PC5
must not be substituted for LS5. Expected LS5 hostname/account/Tailscale values
remain separate owner records; hostname equality alone is insufficient.

**Offline/default PlanOnly (no observation):**

```powershell
powershell.exe -NoProfile -NonInteractive -File .\installer\maintenance\GridMaintenance.ps1
```

All observation commands below are **templates requiring separate read-only owner
approval**. Replace placeholders using independent source evidence. The flag
`-ReadOnlyApproved` is a local assertion and supplies no cryptographic authority.
No remote connection is made by the tool. Do not run it now under this task.

```powershell
# LS5, reviewed local console; run_id is a fresh UUIDv4, source pins are external.
.\installer\maintenance\GridMaintenance.ps1 -Action Inventory -Node LS5 `
  -Head '<EXACT_HEAD>' -Tree '<EXACT_TREE>' -RunId '<UUIDv4>' -ReadOnlyApproved

# PC4: existing PC4\ls4 in a NON-ELEVATED LOCAL console for token observation.
.\installer\maintenance\GridMaintenance.ps1 -Action Inventory -Node PC4 `
  -Head '<EXACT_HEAD>' -Tree '<EXACT_TREE>' -RunId '<UUIDv4>' -ReadOnlyApproved `
  -ExpectedSid '<independently confirmed full user SID>' `
  -TokenObserverDll '<reviewed original S0Launcher.dll>' `
  -TokenObserverSha256 '<independent original DLL SHA256>'
```

Tokens: current process SID, PID/creation time, integrity, elevation, group
attributes (enabled/deny-only remain distinct) and privilege attributes are read
by the existing native observer. SID identity is compared before serialization;
private SIDs become SHA256 values. No token/logon/account is created. Missing DLL,
missing SID/pin, assembly collision, token API failure or nonlocal DLL yields
BLOCKED. Captured DLL bytes are hashed before loading. The DLL must have an
independent source provenance review; path checks are not handle-bound custody.
Medium IL by itself is **not** proof of a local interactive session. High
Integrity/admin-enabled SSH observations cannot satisfy the local-token gate.

The `pc4` SSH alias can be inspected by the operator with `ssh -G pc4` only after
approval. A future remote inventory via this alias must verify host-key fingerprint,
expected hostname/machine identity and account. There is intentionally no SSH
or SFTP implementation here, no credentials and no host-key policy override.

The collector prints JSON to stdout only. It does not save host evidence files.
Operator-approved redirection is a separate file-writing action into a new,
protected evidence directory. Exit2 denotes BLOCKED, including collected but
unattested observations; PlanOnly exits0. Do not equate an exit0 of a synthetic
test wrapper with physical PASS.

**Offline consumer, on copied/redacted evidence:**

```powershell
python -m tools.grid_physical_maintenance --snapshot '<redacted snapshot.json>' `
  --head '<EXACT_HEAD>' --tree '<EXACT_TREE>' --run-id '<UUIDv4>' --node PC4
```

An all-complete synthetic snapshot can yield `OFFLINE_MODEL_PASS`. Physical is
always BLOCKED. Missing/FAIL/UNKNOWN/SKIPPED/incomplete types, substitutions,
ambiguous JSON and unknown top-level fields cannot yield model PASS. Timestamp
is observational wall-clock metadata, not trusted time or freshness authority.

## Independent stages and required approval

`Inventory -> PlanOnly -> Preflight -> Stage -> Prepare -> Execute -> Evidence`.
Inventory/Preflight/Evidence currently only observe local metadata. Stage,
Prepare, Execute and Cleanup always return BLOCKED with null mutation argv,
including when an assertion flag is supplied. There is no hidden fall-through
into the production installer.

A future action request must bind **action, exact HEAD/tree, independent host
identity, operator SID, UUID run, individually enumerated resources, issue/expiry
time and single-use nonce**. An independently authenticated owner signature,
trusted expiry, durable replay/anti-rollback store, crash recovery and reviewed
handle-bound executor are prerequisites. These are NOT implemented by a request
JSON or an in-memory set. Each stage needs a different explicit grant. No current
flag, hosted test result, checksum or this document grants one.

## Minimal hosted PS5 handoff investigation

`HandoffProbe.cs` is compiled only on genuine GitHub-hosted Windows. It runs
through the original restricted-token/atomic owned-Job parent (unchanged90s),
which owns all descendants and closes only its own unnamed Job. A copied runtime
fixture entry calls the reproducer instead of issuing Core20/Runtime2 receipts;
the copy and original have separate hashes. Production source/package bytes are
unchanged. Hosted flags are checked; LS5/PC4 are explicitly rejected.

1. Stage a fresh GUID package with the original native guard.
2. Acquire/release full source custody and hash closure; persist bounded stages.
3. Start one fresh PS5.1/PS7 shell, with original30s child watchdog.
4. Verify original source ZIP and load its original DLL.
5. Call `RunAtUserProfileV1` with `-I -S -B -c "raise SystemExit(0)"`,5s native
   child budget, no Grid CLI/config/DB/network.
6. Persist native handoff return, owned Job/token observations and exit outcome.

If source succeeds and the minimal body also stalls, the Grid Prepare application
body is not needed to reproduce. If minimal returns and real Prepare fails,
inspect application/IO and console/pipe handoff next; neither outcome proves a
WFP or ACL cause. A timeout remains BLOCKED. Source-hash, handoff, shell creation,
child execution and watchdog stages must be read from original JSONL, not invented.
Diagnostic success never replaces mandatory cold-first Prepare or the raw
Core20/Runtime2 receipts. No deadline increase, retry masking or warmup before
the mandatory test is permitted. Real PID ownership remains with original held
handles/Jobs; there is no global PID-kill or process-name cleanup.

## CI and original evidence

Dedicated workflow `grid-physical-maintenance.yml`:

- offline: Ubuntu/Windows x Python3.11/3.12; existing506+39 S0 inventory plus the
  separately frozen maintenance inventory, zero skips/xfail/failure/errors;
- native: PS5.1/7 x control Python3.11/3.12; portable embedded Python3.12;
- actual original cold-first/native Core20+Runtime2 gates retained; diagnostic
  reproducer runs only after mandatory portable failure;
- required aggregate requires both complete matrices SUCCESS; SKIPPED is failure.

PS mocked output has19 individually named cases, a separate JUnit and JSON
receipt. Python receipts bind JUnit/JSONL SHA256, exact HEAD/tree/run/attempt and
source Git blobs. The stdlib independent consumer requires external expected
inventory, source pins and original outerZIP digest; these cannot be taken from
the bundle itself as their own trust anchor. Missing artifacts => BLOCKED.
Original S0 ZIPs use the existing stricter S0 independent verifier; all four
native cells and the aggregate must succeed at the same exact HEAD before a
candidate can be submitted for independent acceptance. CI consistency is never
physical acceptance or owner authorization.

## STOP and recovery checklist

STOP on host/SID mismatch, unexpected elevation, unknown source/package digest,
unknown/reparse path, incomplete API results, malformed evidence, unknown resource
ownership or any failure/skip. Preserve the PC4 diagnostic task and all existing
services/DBs/accounts/firewall rules. No rollback is needed for an observation:
the collector changed none of these. Retain original evidence; do not "clean up"
an unknown object. Any future remediation requires a separate owner-approved,
resource-specific plan, pre-change evidence and tested rollback.

Remaining P0: PS5 Prepare root cause/native exact-head acceptance, protected
physical source custody, owner-authenticated approvals and durable replay,
physical local-token acceptance. P1: no SQL catalog confirmation, no route/SSH
host-key attestation or effective firewall proof, fixed-path inventory is not
exhaustive cleanup verification. P2: metadata is point-in-time, wall time is
untrusted, SID digests are pseudonyms and remain potentially identifying.


### First hosted maintenance run:41113467110 (HEAD12164b78)

All four offline jobs and both PS7 native jobs succeeded; both PS5 native jobs
failed, with aggregate pending at observation. Original PS5 artifacts prove the
mandatory failure was **cold loader Plan30s**, before Core20/Runtime2, rather than
proof of a new Prepare failure. Do not inherit a later stage from another HEAD.
The separate minimal probe failed before executing native code: it mistakenly
used the production1MiB mutable-file helper for larger package DLL/ZIP payloads.

The diagnostic-only package writer now keeps a single exclusive CREATE_NEW
handle and parent custody, writes chunks <=1MiB, and retains per-member64MiB and
sourceZIP512MiB limits. The production1MiB helper and Win32 write bound are
unchanged. Missing hosting gate, wrong types, oversized payloads, hardlinks and
partial-write faults are covered by pure fake APIs. This fixes the reproducer,
not the PS5 cold loader or physical readiness.
