# Isolated first boot acceptance



Status: OFFLINE_VERIFIED / HOSTED_E2E_NOT_RUN. Whole system PARTIAL.

Physical PC4 0/10 NOT_RUN. Execute NOT_AUTHORIZED. Cleanup NOT_AUTHORIZED. Deployment NO-GO.



## Frozen composition



`integration/first_boot_sources.json` records exact source PR heads and selected paths.

The review base is PR238 at 7df22d1c5cdc60bcf4e3414dacd35d23fdec7149.

PR227/230 runtime schema changes are absent from that tree: import their reviewed

runtime/test subset, not complete profile trees. PR229 narrow coverage is superseded

by PR230's DDL workflow. PR239ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“242 contribute only disjoint profile files.

Original PR branches remain unchanged. Later source-head drift requires a new review.



## Architecture



```mermaid

flowchart LR

  P[Attested disposable PostgreSQL 18.4] --- C[Real foreground Coordinator]

  C --- A[Real Worker A / private SegmentWAL]

  C --- B[Real Worker B / private SegmentWAL]

  F[Loopback synthetic HTTP + WebSocket] --> A

  F --> B

  A -->|credential + session + generation| C

  B -->|credential + session + generation| C

  C -->|fenced DML| P

  O[Private CI operator pipe] -->|real fleet STOP / validate / RESUME| C

```



No SQLite replacement, mocked HTTP, seeded ACTIVE state or mocked PostgreSQL is used

in E2E. Unit fault injection is separate and labelled OFFLINE_UNIT_ONLY.

The audit hook confines normal Python network/file operations; it is not a kernel

sandbox or a defence against malicious native extensions. GitHub disposable runners

and the attested container are the infrastructure boundary. Dependency versions are

frozen directly; transitive dependencies are recorded, not hash-locked.



## Entry points and evidence



`python -m integration.first_boot` is PLAN_ONLY. Execution requires `--execute-ci`,

Linux GitHub-hosted context, exact repository/head/run/attempt/job, local Docker

attestation, owned tmpfs PGDATA, random nonreserved loopback port and matching cluster

identity before SQL. It cannot authorize execution on PC4 or LS5.



Hosted workflow `full-system-first-boot`: four offline OS/Python combinations,

reused native Windows workflow, disposable `pg18`, required aggregate with downloaded

artifact reinspection. All dependencies must conclude success; skipped is rejected.

The exact primary test and subtest inventory is frozen in integration/first_boot_inventory.json; are independently inventoried. E2E has 26

required cases; any missing stage is BLOCKED and fails JUnit. Receipts bind source

SHA256, head/tree, run/attempt, process exits and all evidence bytes. Consistency is

not independent cryptographic provenance. No physical attestation is produced.



## Fault and readiness matrix



| Scenario | Implementation | Current evidence |

|---|---|---|

| Fresh schema, migrations1ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“48, second preparation | real owner fixture | hosted NOT_RUN |

| App DDL denied / RO DML denied | real distinct roles | hosted NOT_RUN |

| Two concurrent enrollments / replay rejected | real HTTP / private token issuer | hosted NOT_RUN |

| INFRA blocks market and ingest | real runtime gate | hosted NOT_RUN |

| STOP ACK / pilot validation / RESUME ACK | real fleet and workers | hosted NOT_RUN |

| Per-symbol exclusive ownership | real assignments / fencing | hosted NOT_RUN |

| Synthetic WS -> SegmentWAL -> ingest -> candles | real pipeline | hosted NOT_RUN |

| Identical delivery / changed same delivery | immutable receipt boundary | hosted NOT_RUN |

| Worker SIGKILL / new session and heartbeat | owned CI process only | hosted NOT_RUN |

| CONTROL SIGKILL / lease takeover | real election | hosted NOT_RUN |

| PG restart inside same owned container | identity before/after | hosted NOT_RUN |

| Fresh collection after each recovery | new closed minute + LIVE receipts | hosted NOT_RUN |

| Controlled shutdown and resource cleanup | identity-bound children, own root/container | hosted NOT_RUN |

| Worker DB-less heartbeat, endpoint config | unit regressions | LOCAL_PASS |

| Partial provider creation / shutdown pipe failure | explicit unit fault injection | LOCAL_PASS |

| Native handles/ACL/TOCTOU | reused hosted Windows fixtures | hosted pending |

| Physical tokens, source custody, air-gap | not executed | BLOCKED |

| Tailscale/OAuth provisioning / ML training | not faked by this harness | BLOCKED |



Synthetic timestamps and IDs are test-only. Recovery must produce a new canonical

minute and LIVE receipts; existing rows alone cannot prove recovery. Initial partial

ownership minutes may be DEGRADED. Full schema/catalog digest must be unchanged.



## Confirmed fixes and remaining severity



P1: DB-less Worker heartbeat dereferenced `self.db=None`; use actual storage rate.

P1: default reachability ignored configured REST URL; validate and probe configured endpoint.

P2: oversized pytest ID exceeded Windows environment limit; retain payload, bound IDs.

P2: acceptance function omitted expected_heads argument; preserve duplicate-negative test.

P2: publish own container cleanup receipt before fallible inspect, without authorizing SQL.

P2: require fresh cluster proof before cleanup reconnect after PostgreSQL restart.

P2: contain every owned child even when cooperative shutdown pipe fails.

P2: reject stale restart heartbeats and demand new collection after recovery.

P2: pytest9 subtest reports must not inflate primary pass counts.



Remaining P0/P1 deployment blockers: missing independently accepted protected source

and Windows token/custody evidence; existing authorization-boundary reproductions in

`tests/test_pr227_authorization_boundary.py` demonstrate persisted ACTIVE/admin-token

and empty-fleet resume limitations. Their passing tests are defect evidence, not

security acceptance. No physical launch is authorized. Hosted E2E may expose further

runtime integration defects. Do not weaken checks to obtain green CI.



## Future LS5 preflight / PC4 transition



Human authorization is required before any physical observation. First freeze exact

candidate SHA and independently verify a complete downloaded bundle; stop on digest,

identity, ACL/ancestor custody, task, process, schema or role uncertainty. Do not trust

existing ProgramData/Runtime/Fixtures as executable custody. Do not inspect secrets

into logs. Inventory only, no task activation or ACL changes. PC4 requires independently

reviewed protected checkout, dedicated credentials/roles/database, confirmed nonadmin

tokens, observer/STOP separation and approved evidence custody. Air-gap remains unproven.



Rollback of this development work is branch abandonment only; no physical resources

were changed. Hosted failures retain hashed evidence and stop owned children before

owned database removal. Never adopt/delete foreign directories, roles or containers.



Refreshed PR239ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ242 to latest queried heads before publication; added their new

release-model and independent E2E evidence tests. PR242 SHA regex over-escaped\Z

and rejected all valid digests; four positive-path tests reproduced this, fixed

locally without changing source PR242. All acceptance results remain BLOCKED/NO-GO.


## Additional containment gate and fault inventory

If any owned child remains live or uncertain, database cleanup refuses DROP and
retains generated resources inside the disposable container until CI teardown.
Containment proof must be exactly bool true; unknown/truthy substitutes fail closed.
The container is still bounded to this owned hosted run; no foreign resource is adopted.

Additional local tests:53 WAL/spool/storage cases PASS on generated own fixtures;
not E2E. Covers corrupted middle/tail records, checkpoint bounds, ack order, local
hard-capacity simulation, canonical replay and immutable WAL payloads. No real disk
exhaustion, network disruption or SQL was performed locally.

| Requested fault | Evidence boundary |
|---|---|
| Agent/CONTROL crash, PG restart, duplicate, concurrent registration | real hosted E2E pending |
| Out-of-order canonical storage, corrupt spool, bounded disk-full | local unit fixtures PASS; full live pipeline fault BLOCKED |
| API timeout, temporary network loss, DB lock contention | integrated hosted fault injection NOT_RUN |
| Termination during shutdown | unit pipe failure/containment PASS; live timing fault NOT_RUN |
| Partial staging, journal interruption, stale recovery | synthetic release model PASS; Windows fixture pending |
| Invalid config, missing secret, wrong identity, changed digest | offline negative models PASS; actual Windows custody pending |
| ACL drift, executable substitution, malicious evidence | offline/native models; hosted native pending |

## Component entrypoint map

| Component | Actual entry / dependency | Isolated mode and acceptance |
|---|---|---|
| Coordinator | run_coordinator.py / grid.coordinator.app / app-role PG | harness Uvicorn loopback; actual leader health and fenced DML |
| Worker | run_worker.py / grid.worker.Worker / credentials + WAL | own process/env/directory; no DB credentials |
| Enrollment/API | grid.coordinator routes / enrollment + fleet | real token issue + HTTP; OAuth path remains BLOCKED |
| Schema | grid.schema_preparation / grid.schema_contract | separate owner preparation; runtime DDL denied |
| Collection/storage | grid.worker / grid.storage / grid.segment_wal | actual loopback feed, WAL, receipts, canonical PG readback |
| Legacy spool | grid.spool | own-file unit cases; not substituted for live SegmentWAL |
| Scientific/ML | Coordinator background modules / optional ML env | background startup real; ML training dependencies BLOCKED |
| Assignment | Coordinator rebalance / collection_ownership | exact two symbols; no simultaneous assignment; persisted generation |
| Windows launch | installer/coordinator-launcher.ps1 + Scheduled Tasks | source/AST only locally; task execution BLOCKED |
| Network | installer/ls5_network_offline.py / Tailscale/SSH contracts | synthetic offline diagnostics; real provisioning BLOCKED |
| Releases | installer/switch-release.ps1, recover-release.ps1, rollback-release.ps1 | synthetic hosted RuntimeGuard/LegacyRollback; physical BLOCKED |
| Native custody | installer/native-acl-observer + transaction fixture | hosted GUID fixtures; production Apply remains blocked |
| Trusted source | installer/trusted_bootstrap.py | offline contract only; no physical custody attestation |


The required pg18 job also runs all32 exact-inventory PostgreSQL schema/runtime tests
before first boot, with zero skips. The DDL receipt previously tried git show for
paths deleted relative to its old baseline, impossible on composed source trees;
a generated-repository regression verifies explicit deleted_paths alongside hashes.

## First actual hosted attempt (exact38e6ab4)

Run40081972021 completed FAILURE. All4 offline OS/Python cells SUCCESS. All32 actual
PostgreSQL18 contract tests PASS (JUnit errors/failures/skips0). Real Coordinator PID11516
and Workers11523/11524 started in disposable hosted Linux, migration preparation and
real enrollment passed, then heartbeat failed before two-real-workers readiness.
Audit hook incorrectly rejected connected socket.sendmsg with destination None;
regression now resolves actual loopback peer and still rejects external/unknown peers.
All3 observed process exits were0 and owned cleanup passed. No full E2E PASS:17 required
stages missing. Native4 cells failed TOKEN_SIZE_UNKNOWN before ordinary observation;
new bounded numeric API diagnostics retain the refusal and await hosted evidence.
PG artifact12556681100 digest4da78e72ce879fa36bbdc3f4351c86a3ed34120c44ba16a4e2d1fa936d121554.
Physical readiness is unchanged: BLOCKED/NO-GO. This does not attest LS5 or PC4.

Hosted native attempt802f921 confirmed sizing probe TokenElevation20 returns false,
ERROR_BAD_LENGTH24 and required4. Scalar policy now accepts only false+size4+error122
or24, requires real subsequent read success/used4 and rejects values outside0/1.
Other token structures/access failures remain refused. Nine new pure managed cases
are frozen in the native inventory; local .NET SDK is absent, so these cases await
hosted compilation/execution rather than being claimed locally passed. No native
security calls ran locally. Manual G0 source commands avoid Git status/diff against
untrusted configuration because clean filters may execute external code.

Hosted780362f native ordinary observation and all51 managed cases PASS, but rename
case returned rename_win32=0 with session failure. Metadata-only leaf handles do not
participate in the sharing accounting needed to refuse DELETE opens. Observer now
requests read-data/list-directory access (no reading/writing content, no DELETE) so
sharing checks apply; denial remains BLOCKED. Rename assertion is not weakened. Five
additional frozen managed cases cover the read-only access mask and exact no-BOM
session protocol. Parent writes explicit UTF8 bytes; reader rejects EOF/BOM/whitespace.
This needs hosted validation and never enables physical Apply/Execute/Cleanup.
Reference: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-iochecklinkshareaccess

Hosted780362f E2E reached14/26 stages (heartbeat, infra and fleet stop), then pilot
validation refused. Harness now waits for all actual zero-activity/operator-stopped
worker snapshots after global STOP ACK, preserving every production validation guard.
The next hosted run must prove this removes the timing gap; no full PASS claimed.

Hosted297fcb7 proved56 managed cases PASS and held-leaf rename now denied withWin32=32.
Session recheck still failed SESSION_COMMAND_INVALID. The observer now uses an explicit
strict UTF8 StreamReader on the redirected pipe with standard BOM decoding, rejects
other detected encodings, and validates exact decoded command. A57th pure in-memory
wire case verifies BOM decoding; the policy still rejects a BOM in decoded text.
No command text is logged and no file/share/authority guard is relaxed. Full Windows
fixture acceptance awaits the next run.

Hosted297fcb7 reached22/26 stages: live synthetic PostgreSQL persistence, immutable
receipts, duplicate checks, Worker crash/restart and CONTROL crash/recovery passed.
PostgreSQL-restart recovery polling aborted on the first expected private status
refusal during leader loss. Read-only status now returns pending only for that exact
refusal within existing deadlines; EOF/protocol/process errors remain fatal, mutation
commands are not retried, and fresh post-recovery data remains mandatory. Transient
asyncpg setup/closed-connection errors are preserved in the artifact; no driver or
production fencing behavior is silently changed by this harness correction.

### Independent bootstrap evidence parser regression

QA identified a source differential with PR239 blob
`f21dfb30553da0a8e079744d580dd7a474d9073b`. Seven independent synthetic
inputs reproduced false PASS before the fix: duplicate testcase identity, missing
classname/name, and non-whitespace root/suite/case text or case tail. The
composition now restores that exact parser blob: ambiguous inputs fail before
creating a receipt. All19 targeted receipt tests pass locally. This does not
authenticate a physical run or authorize execution.

The separate PR239 active-release contract has also drifted from this
composition: PR244 pins the historical release while upstream accepts an
explicit40-character COMMIT and derives expected source paths from it. Do not
automatically generalize or execute that physical bootstrap policy; reconciliation
requires a reviewed exact release/source inventory. It remains a G1 blocker.

### Actual PG restart fixture defect (9efa0b9)

Hosted run40090215672 again reached22/26 stages with32 PostgreSQL tests passing.
The official container made postgres its lifetime process; pg_ctl restart stopped
it and --rm removed the container/tmpfs. Subsequent connection-refused and cleanup
inspect failures are fixture lifecycle failures, not established Grid recovery
defects. CI now uses a fixed, attested bash/sleep lifetime holder plus Docker --init;
PostgreSQL still runs via the image entrypoint and is genuinely restarted with pg_ctl.
Image identity, entrypoint, command, init, labels, tmpfs, loopback port and cluster
identity must all match. Five mocked negative/creation tests reproduced the omission
and now pass. Recovery also requires a changed actual pg_postmaster_start_time in
the same attested cluster and fresh pipeline data. No persistent host volumes added.
Docker semantics: https://docs.docker.com/engine/storage/tmpfs/ and
https://docs.docker.com/engine/containers/multi-service_container/ .

The Windows9efa0b9 pwsh3.12 cell passed57 managed cases and all31 observer GUID cases,
then the separate transaction fixture failed FIXTURE_CUSTODY_CHANGED. Exact stage
and synthetic descriptor comparison diagnostics are added without relaxing equality.
No local native execution occurred and no transaction safety PASS is claimed.

### Exact native descriptor diagnostic (106a6c5)

Direct hosted Windows job120863476956 failed commit-native-readback with all three
identities equal and only descriptor bytes different. The SD control word changed
from0x9004 to0x9404: SE_DACL_AUTO_INHERITED was set by the API path. Newly-created
GUID fixtures now request protected+auto-inherited DACL flags at creation, before
binding the journal. Equality/owner/group/ACE/control checks remain exact; a Python
negative test changes the control bit and requires rejection. Existing arbitrary
ACL restoration is not covered or authorized by this controlled fixture contract.
The original failed native receipt is retained. The fix remains pending actual CI.
Microsoft flag definitions: https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-string-format .

### PG restart confirmed, controlled restart remains blocked (106a6c5)

Run40091003818 passed23/26 stages,32 PG18 tests and all four offline matrix cells.
Postmaster start changed11:46:57.079249→11:52:02.914463 UTC with cluster ID
7700199545428189241 unchanged, followed by fresh canonical data and LIVE receipts.
PostgreSQL recovery and owned container cleanup both passed. The later full normal
shutdown/restart failed to produce the required fresh minute within the deadline;
worker logs show substantial stale micro-WAL replay/quarantine backlog and bounded
drain timeouts. This is not yet attributed to a production defect. Additional
read-only count/status diagnostics retain queue/replay state and the named timeout;
no deadline, replay acknowledgement or fencing check is relaxed.
