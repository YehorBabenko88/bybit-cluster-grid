# ADR draft: future PowerShell-layout PGDATA intent V1

**PROPOSED / OFFLINE ONLY. L1 and L2 NO-GO.** This is not the existing Python
schema-1 plan and is not schema-2 execution enablement. Frozen base PR214:
`272ea6c1d011779a83a5d89478e237a6427f66e9`. Owner chose future PowerShell intent;
no directory, ownership, native identity, actual producer or runtime is verified.
No previous PR, producer, adapter, installer, manifest or runtime is changed.

## Decision and scope

New standalone module `installer.pgdata_intent_v1` exposes `validate_bundle` and
`validate_text`. Neither writes files, opens handles, takes a mutex, queries a
token, starts a process, opens a connection, accepts a receipt or mutates history.
There is no executor or runtime integration. Scope is EMPTY_FIXTURE_ONLY; even
future physical experiments must not run PostgreSQL, SQL/initdb or real data.

Contract ID `PGDATA_POWERSHELL_INTENT_V1_DRAFT` is a separate version namespace.
It cannot be passed to schema-1 as an alias or version upgrade. Existing schema-1
still requires `<parent>\<run>\<node>\pgdata` and rejects the PowerShell target.
Historical artifacts/digests are never rewritten. No conversion API is supplied.
Any future consumer/runtime adoption needs a separate reviewed proposal before
changing a producer/adapter. The staging policy remains untouched and unevaluated.

## Closed bundle and byte definitions

`pgdata-intent-v1.example.json` is a synthetic public fixture, not emitted native
evidence. The declared fixture branch is not a staged release. No sample directory
or port is allocated. Unknown fields and non-builtin JSON values are refused.
Bounded shared JSON parsing rejects duplicate keys, nonfinite values, invalid
Unicode, excessive nesting/size and malformed encodings.

| Field | Rule |
|---|---|
| `intent` | Closed fields: contract, parent/root/pgdata, run/node, candidate SHA, phase/scope, root provenance, native statuses, six role intents and four false authority flags |
| `intent_sha256` | Lowercase nonzero SHA256 of UTF-8 canonical JSON: sorted keys, compact separators, ASCII escapes, no trailing LF |
| `producer_plan_utf8` | Raw compact ASCII plan profile with 20 ordered fields, including last `plan_sha256`; never an object silently reserialized as historical evidence |
| producer `plan_sha256` | SHA256 of exact profiled compact producer JSON before adding that final field, no trailing LF; root/run/node/version must agree with intent; fixed false activation/init/tasks and conservative fixed policy/blocker profile |
| `journal_utf8` | Exact canonical ASCII JSONL: ordered schema/plan_sha256/state, LF per record, no BOM/CRLF/extra bytes; plan digest must match producer preimage |
| `journal_sha256` | SHA256 of exact journal UTF-8 bytes including record LFs |
| `receipt_utf8` | New diagnostic V1 envelope, sorted compact canonical ASCII JSON plus exactly one LF; binds intent/producer/journal digests, run/node/root/pgdata, phase, scope, UUIDv4 receipt ID and false flags/status BLOCKED |
| `receipt_sha256` | SHA256 of exact receipt bytes including LF; not the producer journal digest |

PREPARED expects one journal record; COMMITTED expects PREPARED then COMMITTED;
RETIRED expects all three records. These are **metadata phase names only**, never
commands. Interrupted PREPARED state remains BLOCKED, repeated reads do not create
or resume a transaction. Other valid producer lifecycle forms outside this narrow
profile (for example PREPARED then RETIRED without COMMITTED) are deliberately
refused, not repaired or reinterpreted.

The producer profile pins a conservative ASCII subset of the frozen source byte
contract. It is **not a universal PowerShell serializer**, not proof of actual
PowerShell 5.1/7 output, and not provenance authentication. Unsupported serializer
representations are refused rather than normalized. Current producer does not
emit this new intent/receipt bundle. No cross-runtime emitter is added or claimed.
The new diagnostic envelope never substitutes for actual JSONL or schema-1's old
diagnostic envelope. Future cross-language collection needs independent review.

## Literal future path intent

The constrained proposal parent is uppercase `[D-Z]:\GridLab` only. This intentionally
excludes C: and nested parents accepted by some old producer plans; it does not
modify their validity. Run is 32 nonzero lowercase hex; node is uppercase ASCII
1–15 characters, excluding LS5/LS7 and reserved DOS device names. Candidate SHA
is 40 nonzero lowercase hex. Root and target are compared literally:

```
root   = <parent>\<run>_<node>
pgdata = <root>\postgres\data
```

No PureWindowsPath normalization, casefold, Unicode normalization, short-name
expansion, slash repair, junction/symlink resolution, traversal removal, URI/UNC/
device-path interpretation or alternate mapping is allowed. Homoglyphs, mixed
layout, swapped IDs, ADS, trailing dots/spaces, case changes and path aliases fail.
Literal agreement does not exclude actual reparse points, aliases or an existing
production directory. Physical ownership cannot be established without later
authorized native evidence. No existence or resource inventory is performed.

Root provenance declares frozen source commit/path and UNVERIFIED status. An
attacker may copy that claim and recompute every unsigned digest. Structural
binding detects inconsistency, not authenticity or safe origin. It is not a
signature, independent provenance, observed path or permission to create it.

## Roles are proposed separation, not actual identities

Six ordered roles: resource_custodian, windows_object_owner,
future_postgres_writer, observer_a, observer_b and stop_authority. Each has a
distinct canonical UUIDv4 principal intent, distinct symbolic custody domain,
optional syntactically valid proposed SID and UNVERIFIED status. Reused non-null
SIDs, principal IDs/custody domains, missing observers and extra role fields are
refused. Null SID means unknown, not a fabricated identity. Distinct strings
cannot prove distinct actual effective tokens, administration or custody.

This is intentionally conservative separation. Object owner may be able to
change DACL; a future PostgreSQL writer needs write rights; observers should not
be writers; STOP authority is not unilateral resume authority. No ACL is created
and no rights are granted. A read/share-read fixture handle prototype can exclude
some new ordinary writes while held; it cannot serve as readiness for a live
PostgreSQL writer or exclude privileged writers/pre-existing mappings. Designing
that phase transition is future work, outside EMPTY_FIXTURE_ONLY.

## Missing proof, replay and trust boundaries

Native reparse, symlink, ancestor, volume, file identity, ACL, token and handle
evidence fields must stay UNVERIFIED. Omitting a slot or claiming VERIFIED/PASS
is invalid. Even a valid bundle returns BLOCKED with NATIVE_EVIDENCE_MISSING and
ownership_verified=false. Other blockers include unverified producer provenance,
unevaluated staging policy, missing durable replay, two human reviews and no
physical authorization. No synthetic flag can clear them.

`seen_receipt_ids` is a bounded optional tuple/list of distinct UUIDv4 IDs. A known
ID is refused even if contents/digests change. Invalid/duplicate history is refused.
The validator does not accept, consume, reserve or persist an ID. Empty/default
history means **no trusted history supplied**, not first use. Two concurrent
calls or a rolled-back/omitted history may both validate metadata. New IDs do not
prove fresh state. Replay result explicitly says CALLER_HISTORY_ONLY_NOT_DURABLE;
anti-rollback remains NOT_IMPLEMENTED. No atomic, durable or cross-process replay
claim is made. A caller must never use metadata_valid as an authorization decision.

Air-gap media, file hashes, timestamps or test signatures establish neither live
freshness nor independent monotonically durable anchors. Correlated rollback of
checkpoint/witness/all anchors is still a hard certification blocker. Host admin,
hostile same-SID code, ACL ABA and surviving mappings remain outside unproven
claims. No VM, host, native SID/token/ACL, PostgreSQL or witness is inspected here.

## Negative matrix and CI

Tests cover literal path ambiguity, old/mixed layout, swapped IDs, journal phase/
byte/digest mismatch, receipt substitution, rehashed unsigned attacks, invalid
role/SID/custody equivalence, missing native evidence, premature readiness,
schema confusion, replayed IDs and untrusted history rollback. Old schema-1 and
cross-contract refusal regressions are retained. The public fixture is synthetic.

Hosted-only CI runs Windows/Ubuntu Python 3.11/3.12, exact checkout SHA, frozen
test inventory, actual collection/call receipts and JUnit zero errors/failures/
skips/xfail. PowerShell 5.1/7 parsing is syntax-only; no producer/installer script
executes. Inherited infrastructure workflows are excluded on this branch without
weakening production gates. There are **432 tests** in the committed inventory,
including 119 new contract/CI checks and the prior 313 pure regression cases.

## Human gates and remaining work

Owner's future layout decision is recorded, not a human architecture/security
review. Two genuine independent submitted reviews remain required. Trust/custody,
real resources, privately verified identity and later native observations remain
unresolved. No signed-off L1 decision or L2 approval is produced. Twelve real VM
cases remain NOT_RUN; all execution_authorized/readiness_passed/physical_ready/
schema2_enabled flags false. A later implementation needing producer/adapter
changes must stop for architecture review; this prototype has no runtime wiring.
