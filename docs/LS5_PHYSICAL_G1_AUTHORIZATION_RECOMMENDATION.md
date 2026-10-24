# PHYSICAL_G1_AUTHORIZATION_RECOMMENDATION — BLOCKED

Date: 2026-10-24. Independent GPT-4 acceptance, **no owner authorization**.
**Physical PC4 0/10 NOT_RUN; Execute/Cleanup NOT_AUTHORIZED; Deployment NO-GO.**

## Pinned review inputs

| PR | Exact HEAD | Scope |
|---|---|---|
| #238 | `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149` | native ACL/custody |
| #239 | `c842cf6436320cbfecb8d4a7ba97dcbc4e0f19ee` | bootstrap |
| #240 | `21a805fe8ef4fafc3b187dc95742c1808861c0ac` | PG readiness |
| #241 | `b6139c3a8deaed9a590d2cb91e4daedef12da299` | network |
| #242 | `91d56c4a6db76af68cabcce50fcaeefb88e4b88b` (pre-document) | acceptance |
| #244 | `3808cb9f6ecd2f42d5d0c758145b427a58a010e8` | integration |

#244 is based on #238 HEAD, whereas #239–#242 are parallel from
`e25197b169ef0e5f37b5bd0030ee4a97b13965e2`. No implicit merge
or automatic equivalence of similarly named files is assumed.

Exact Git blob checks: #239 JUnit evidence parser and #240 PG readiness
match #244; #239 trusted bootstrap differs (`d1ab542...` versus
`83c87c6...`), with unresolved active-release COMMIT vs VERSION
semantics. #241 network policy differs (`618d338...` vs `daabde0...`):
the integrated version lacks the 65,536-byte pre-parse bound. #242
independent acceptance differs from integration and must be tested at
its own HEAD. These are source-level compatibility findings, not
proof of physical isolation.

## G0/G1/G2 gates

| Gate | Evidence and authority | STOP | Verdict |
|---|---|---|---|
| G0A LS5 read-only inventory | Explicitly approved observer identity; exact host, process PID+start time, signed executable/release, service/task state, ACL/SDDL and ancestor write/delete/reparse closure | Unknown existing coordinator or writable executable closure | BLOCKED |
| G0B network read-only | Bind address/listener owner for TCP22/8765/55432; Tailscale identity/grants, Windows firewall effective filters, TLS/credential boundaries; no external ingress | wildcard/unowned listener, remote DB, unauthenticated API | BLOCKED |
| G0C PG read-only | Existing PG18 service/PGDATA owner, canonical paths, effective ACL, ports, DB identity and data backup/recovery provenance; no SQL/initdb/changes | unknown PGDATA or credential/source collision | BLOCKED |
| G0D package/custody | exact Git HEAD/tree/source hashes, signed release/toolchain, original ZIP+inner SHA256, trusted journal and independent witness | mismatched receipt, symlink or mutable ancestor | BLOCKED |
| G1 authorization | New written owner permission scoped to GUID fixtures, exact binaries/users/ports/DB, STOP owner, duration and recovery plan; G0 independently approved first | missing explicit authorization, unknown PID/owner, reuse of production port/DB | NOT_AUTHORIZED |
| G1 execution safety | Unique nonproduction Coordinator port and loopback bind, separate disposable DB/storage, allowlisted process tree, no production endpoints/keys, per-stage stop, no automatic cleanup | unexpected listener/credential, PID reuse, descriptor drift, failed journal | NOT_AUTHORIZED |
| G2 independent post-run | Actual process/network/DB observations, 10 native PC4 cases, per-case Win32 errors and ACL/token, exact run/attempt JUnit/JSONL/ZIP SHA, cleanup/rollback independently witnessed | missing, skipped, mocked or producer-only PASS | NOT_RUN |

G0 read-only inspection itself requires separate operator permission. G1
cannot be inherited from G0 or a hosted CI result. Production Apply,
Rollback and cleanup are **separately forbidden** absent owner approval.

## Required evidence before owner may consider G1

1. Independently collected LS5 G0 baseline for all currently running
   coordinator processes, services and scheduled tasks, including listener
   PID/start time, binary SHA, current ports and release ancestry.
2. Verified network segmentation: reserved production TCP/8765, TCP/55432,
   SSH/22 cannot be reused by the lab; no wildcard bind or unexpected
   remote ingress; auth/TLS peer checks and tailnet grants independently
   observed. Lab must use separately approved free ports.
3. Canonical PGDATA and database identity; disposable test DB and storage
   separate from existing clusters, no inherited DSN or production secrets;
   backup/restore and STOP plan with owner of every object.
4. Exact pinned source, signed package, toolchain/import/DLL closure and
   immutable original SHA manifests, plus verified Windows principal
   effective SID/token/ACL and safe staging ancestry.
5. Per-object GUID fixture ownership, durable intent journal, explicit
   negative rights checks, process fencing, interrupted staging and
   rollback test in disposable environment; no deletion of unknown
   objects or evidence.
6. An explicit owner decision authorizing G1's *specific* commands,
   machine identities, time window and bounded scope, separate from any
   later Execute/Cleanup/CollectLocal/production permissions.

## Independent lab CI evidence vs physical proof

PR244 exact `3808cb9...`: hosted full-system run `40104140684`
11/11 jobs SUCCESS, native run `40104140539` 5/5 jobs SUCCESS.
Artifact `12563529069` GitHub SHA256
`e4b3a0dbe56052865768106032ea6857a0bf4130b307dc05ddc4c758a8e7ee45`;
four native ZIPs `12564525450`, `12564311084`, `12564062262`,
`12563418641` with GitHub SHA256 receipts supplied in QA thread.
The general preflight run `40104140576` FAILED; one Python cell
failed and one was cancelled. No physical G0 source observations or G1
execution artifacts have been accepted. Hosted Linux/Windows CI runners
are **not** LS5/PC4; mock/synthetic/native disposable fixture PASS
is not PHYSICAL_PASS.

## Priority and formal decision

**P0 BLOCKER:** G0 LS5 actual process/network/PGDATA/ACL/release evidence
absent; G1 owner permission absent. Cannot demonstrate noninterference
with running Coordinator LS5 or data and secrets.

**P1:** General preflight failed; active-release contract diverges;
G1 process/DB isolation, native ownership journal, recovery and exact
physical identity remain unproven.

**P2:** Network offline input bound not integrated; exact-byte/source
manifest comparisons and adversarial rehashed evidence tests should
be refreshed before G1.

**Recommendation: `PHYSICAL_G1_AUTHORIZATION_RECOMMENDATION=BLOCKED`.**
No execution permission granted or implied. The owner alone may approve
a future tightly scoped G1 after independent G0 review. No host
commands, merge, deployment, production Apply/Rollback, or cleanup.


## Refreshed exact-head gate checkpoint

PR238 `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149`, PR239 `8f0e2713f6e04000d29a370a6b2b2852a4cec6ff`, PR240 `6e8a2e63b7d250780a7276383bc20c15b820c76e`, PR241 `184a87d778c76a2cd2a0f8a14f4f5ee18bbeedaa`, PR242 `3f17728a44f09558852644df90447a60bcdd1dbb` (before this document update), PR244 `992e0db83c45e1dca35f22c14ccc6b49a13bac32`.

GitHub Actions associated with latest #244 SHA: full-system-first-boot `40109637611`, native observer `40109637610`, preflight `40109637695`, windows-bundle `40109637645`, physical acceptance `40109637894`, physical-deployment-harness `40109637696` all **QUEUED** at observation. No exact-HEAD hosted PASS is available yet. Previous `3808cb9...` 11/11 full-system success cannot be inherited by this new SHA.

Source-level blob comparison at latest heads: #239 JUnit evidence parser and #240 PG readiness match #244 exactly. #239 trusted bootstrap still differs (COMMIT vs VERSION active-release semantics), #241 network validator still differs (65,536-byte policy limit absent from #244). These are unresolved composition checks; no G1 authority follows.

**Decision remains PHYSICAL_G1_AUTHORIZATION_RECOMMENDATION=BLOCKED.** Owner permission absent and LS5 host read-only evidence still missing.


## 7904990 CI dependency correction — independent status checkpoint

PR244 latest HEAD `79049906cb004e324bec5ef4cc53b85381cab83a`. GitHub confirms the three relevant workflow runs `40110021208` (preflight), `40110021224` (full-system-first-boot), `40110021246` (native observer) are **QUEUED** at inspection, without a verified new-HEAD PASS. Integration owner reports separation of seven legacy PG18 transaction/restore probes from generic PG16 unit collection, a reusable mandatory PG18 job, an always-running aggregate gate that rejects SKIPPED/CANCELLED, and PyYAML 6.0.3 pin. These are developer claims pending independent source/hosted artifact verification at this SHA. Previous run `40109637695` and JUnit digest `97e7976261605940aabf1172d11df4bd6651d23f770ada74670d92951fa26026` belong to SHA `992e0db...` only and must not be promoted.

The previously successful full-system run `40104140684` at SHA `3808cb9f6ecd2f42d5d0c758145b427a58a010e8` has GitHub artifact `12563529069` with external SHA256 `e4b3a0dbe56052865768106032ea6857a0bf4130b307dc05ddc4c758a8e7ee45`; its 11/11 jobs were successful, but no physical LS5/PC4 evidence. The latest HEAD has not inherited that PASS.

**Physical recommendation remains BLOCKED** pending independent host G0 and separately approved G1. Do not start LS5/PC4, production Apply/Cleanup or deployment.


## Independent PR245 optimized-Python and G0 review

PR245 Draft exact HEAD `0892a1c850787d024a782ff3e44286c191529232`. Source inspection of `tests/_pg18_database.py` confirms that the per-role credential guard is now an explicit `if type(secret) is not str or len(secret) != 64 or any(...): raise RuntimeError('PG18_INVALID_ROLE_SECRET_NO_MUTATIONS')`, not an `assert`; thus CPython `-O` compilation does not remove the guard. Its test `test_pg18_credential_validation_survives_optimized_python` checks AST shape and source text, **not actual `python -O` execution**. A fully independent negative runtime test must run an invalid secret through a disposable mocked/attested PG18 fixture with optimized Python and assert zero CREATE ROLE/CREATE DATABASE/SET write side effects. Do not perform that test on LS5 or installed PostgreSQL. This is a remaining **P1 acceptance gap**, not evidence that the explicit guard is broken.

The new `integration/physical_program.py` profile requires execute/cleanup/deployment/production_database/schema2 all false, generated GUID-run paths and roles, unique ports 29441–29444 avoiding 8765/55432/5432, loopback binds, no executor, and `BLOCKED` G1. `assess_snapshots` accepts only two fresh <=900s `UNATTESTED_READ_ONLY` observations, never produces host_verified=true, and records collisions. The G0 PowerShell collector defaults to PlanOnly and `-G0Approved` is merely an operator assertion; it is not a cryptographic owner approval. It intentionally does not read environment secret values or connect to PostgreSQL/network endpoints. Therefore its partial observations cannot prove effective firewall/TLS/ACL or production noninterference.

The G1 runbook describes future commands but expressly states no physical executor exists. A user manually executing individual templates would bypass the intended guarded orchestration. STOP until independent handle-bound Windows controller, process/job ownership, signed source closure, disposable DB identity, approved OS-level egress policy, full G0 and separate owner authorization are available. No production Apply/Rollback or cleanup.

Hosted PR244 HEAD `79049906cb004e324bec5ef4cc53b85381cab83a`: preflight `40110021208` SUCCESS, native `40110021246` SUCCESS, full-system E2E `40110021224` still QUEUED at review. This is not a complete hosted acceptance.

**PHYSICAL_G1_AUTHORIZATION_RECOMMENDATION=BLOCKED.**
