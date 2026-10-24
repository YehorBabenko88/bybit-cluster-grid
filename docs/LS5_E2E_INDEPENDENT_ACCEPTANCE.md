# Independent disposable-laboratory E2E acceptance (Issue #243)

**Scope:** review of an isolated Codex lab run; no physical LS5/PC4 connection,
no production SQL, no real Bybit orders, no deployment/merge. Codex self-report
is untrusted producer input, not independent acceptance.

## Architecture and entrypoint discovery

Verified in PR #237 base README: coordinator discovers linear contracts and
assigns symbols; workers advertise CPU/RAM/disk headroom and consume publicTrade
streams; coordinator reassigns when a node disappears; PostgreSQL persists
`candles_1m` and `footprint_1m`. This README is an architectural description,
**not proof of a runnable executable or validated CLI**. Before E2E execution,
independently identify the actual coordinator/agent launch modules, API endpoints,
schema/migrations, DB adapters, spool path, shutdown and restart command in the
pinned integration commit; record exact file path, CLI args, executable SHA256 and
environment. Do not infer entrypoints from a developer narrative.

## Required E2E phases (all ordered, exact run/attempt)

| Phase | Independent oracle / evidence | STOP condition |
|---|---|---|
| Coordinator start | external process PID, bound listener, authenticated health, start log | listener missing or PID/health conflict |
| Agent registration | coordinator roster versus agent self-report; unique node identity | duplicate/stale identity |
| Assignment | coordinator assignment snapshot and agent subscriptions | overlap, missing symbols or unauthorized nodes |
| Synthetic ingestion | deterministic seeded input with input SHA256, no external orders | non-deterministic or real external write |
| PostgreSQL commit | independent read-only SQL queries for rows, schema, transactions | missing/duplicate/partial rows |
| Storage readback | recompute 1m buy/sell, delta, POC and row counts from seed | mismatched sums or POC |
| Shutdown | process exit, drained writes, closed handles, DB consistency | orphan writer, premature ACK |
| Restart | fresh PID/epoch, lease fencing, resume checkpoint | stale lease or replay |
| Recovery readback | independently compare persisted rows and assignment state | loss, duplicate or silent corruption |

## Negative matrix (each needs injection and independent oracle)

| Fault | Expected property |
|---|---|
| Crash / kill -9 | durable committed rows only; no false ACK |
| Timeout | bounded retry and explicit failure |
| Network loss | assignment fencing; no dual owners |
| PostgreSQL restart | retry/reconnect and no partial transaction |
| Corrupted spool | quarantine, checksum rejection, no silent skip |
| Duplicate messages | idempotent keys and exactly-once persisted effects |
| Invalid configuration | fail before side effects; no secret disclosure |
| Descriptor drift / PID reuse | revoke trust, require fresh identity |
| Interrupted journal | ordered intent replay or STOP; never blind cleanup |
| Cleanup boundary | only newly created disposable owned paths |
| Rollback boundary | restore owned fixture only; preserve pre-existing resources |

## Five-stream integration G0/G1

- #238: native ACL observer/custody; prove handle-bound identity, journal crash
  boundaries and negative spoofing.
- #239: bootstrap provenance; prove pinned source/release and fail-closed recovery.
- #240: PostgreSQL 18; prove disposable backup/restore, transactional recovery,
  schema contract and independent readback.
- #241: network; prove deny-by-default, timeout/loss/reconnect, authentication.
- #242: evidence/acceptance; independently verify ZIP bytes, per-entry SHA256,
  JUnit and JSONL semantics, exact HEAD/run/attempt, provenance and all required
  jobs; queued/skipped/absent artifacts cannot PASS.

The offline `installer/ls5_e2e_acceptance.py` inspector accepts untrusted
E2E receipts and verifies ZIP byte/hash consistency and five-PR metadata.
Its output **always** denies lab GO and deployment GO because it cannot
independently establish origin or runtime behavior. Self-consistent ZIPs can
be forged; separate GitHub artifact API ID, run attempt, artifact download,
immutable commit and independent SQL/OS observations are required.

## First lab-run report (as of 2026-10-24)

No independently obtained complete coordinator→agents→assignment→synthetic
data→storage→shutdown→restart evidence bundle or Codex integration PR has
been identified and validated in this review. All nine E2E phases and eleven
fault injections are **NOT_RUN/UNVERIFIED for independent acceptance**;
do not relabel producer assertions as PASS. Hosted profile Actions remain
queued; no verified complete artifact matrix. **LAB NO-GO (evidence
insufficient)**; G0 BLOCKED, G1 NOT_RUN.

## Future physical gates

G2 reviewed native custody and trusted source recovery; G3 explicit owner
authorization for LS5 read-only inspection; G4 separate owner authorization
for remediation with journal, STOP and independent rollback evidence; G5
separate coordinator/network/database activation approval; G6 separate PC4
preparation and ten real SID/ACL cases. Each requires independent immutable
evidence and fresh authorization. PC4 0/10 NOT_RUN; Execute/Cleanup
NOT_AUTHORIZED; Deployment NO-GO.


## Independent hosted evidence and PR compatibility checkpoint (2026-10-24)

Pinned source HEADs (GitHub PR API): #238 `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149`; #239 `0dd0cea71f9fd8105deaefc6cfccc0dfe793a689`; #240 `bc8cd0c5308af3602adbd420a10cdd6e6d08f2b3`; #241 `152be6404d4764ec1bba041c679a5719746e8dbc`; #242 `d5966963e6671fe3377dcfe408a78f4a20b70f33` (pre-this-note); #244 `38e6ab40928cbdd6a2d6d84cbb05b4628167258f`. Issue #243 is an issue, not a PR/head. All independent branches #238–#242 use base `e25197b169ef0e5f37b5bd0030ee4a97b13965e2`, whereas #244 uses #238 head as its base. Therefore identical filenames in independent PRs and #244 **are not evidence of byte-for-byte equivalence**; compare source hashes and full content before G1.

| PR | Composition overlap with #244 | Independent compatibility status |
| --- | --- | --- |
| #238 native observer | `.github/workflows/ls5-native-observer.yml`, `.gitignore`; native observer sources not listed among #244 changed paths because #244 bases on #238 | CONDITIONAL: parent provenance known, hosted native observer FAIL |
| #239 bootstrap | bootstrap models, CI evidence, trusted bootstrap and docs/workflow | UNVERIFIED: matching paths, exact byte/API/schema comparison pending |
| #240 PostgreSQL | PG readiness models/tests/docs/workflows | UNVERIFIED: PG18 regression JUnit present, physical DB isolation unverified |
| #241 network | offline network policy/tests/docs/workflow and collector script | UNVERIFIED: network runtime isolation and auth unobserved on LS5 |
| #242 QA | acceptance inspectors/tests/docs/workflow | UNVERIFIED: PR #244 incorporates a different snapshot; never treat its hosted success as PR #242 current HEAD success |

**Downloaded and independently hashed hosted ZIPs**, run `40081972021`, attempt `1`: PG/E2E artifact `12556681100` SHA256 `4da78e72ce879fa36bbdc3f4351c86a3ed34120c44ba16a4e2d1fa936d121554`; Windows native artifact `12556576726` SHA256 `12a3fb6c697b2f3d3942e09f46f5c92d9f944fb97a9e4f1007e8a99d80130fe7`. The PG/E2E ZIP contains `ddl-pg18.xml`, `first-boot-evidence/{summary.json,events.jsonl,results.xml,sha256.json}`, child process logs and provider metadata. The summary pins tree `339e2b3aea446f50cbec8a98900ebc7128dd25ae`, 26 required stages, **17 missing**, `core_status=BLOCKED`, `whole_system=PARTIAL`, three child exit codes 0; JUnit declares `tests=26,failures=17`. The Windows ZIP `native-observer.jsonl` reports `TOKEN_SIZE_UNKNOWN`, `host_verified=false`, `physical_attestation=false`. These are producer artifacts with independently confirmed ZIP digests, not independent proof of physical identity. Four offline CI jobs SUCCESS; native 4 FAIL, PG18 job FAIL, required gates FAIL.

**P1:** heartbeat failure attributed to audit `socket.sendmsg(None)` by integration handoff; require a minimal adversarial reproduction on the fixed exact HEAD and proof that non-loopback/unknown peers remain denied. **P1:** native observer `TOKEN_SIZE_UNKNOWN`; fail-closed is correct but native G0 remains BLOCKED. **P1:** partial E2E must not be promoted despite three zero exit codes and 32 passing PG regression cases. **P2:** integration composition has shared paths from #239–#242 with no independent exact-content equivalence proof; require per-file SHA comparison, contract matrix and no skipped/queued gates.

**G0 physical read-only acceptance:** separately authorized local observer only; exact host identity and executable/process/service/task provenance, PID/start-time, protected ACL/SDDL and ancestor rights, existing coordinator 8765 listener and PID, port/bind/firewall/Tailscale inventory, PG18 service/PGDATA/DSN isolation, credential-redacted evidence, and immutable baseline receipts. STOP if any fact unknown; no firewall, SSH, service, ACL or DB changes.

**G1 authorization checklist:** explicit owner-signed scope, unique process and DB namespace, reserved-port exclusion, independent trusted package/toolchain/manifest, pre-start evidence of original LS5 coordinator, PC4 worker identity and token custody, network auth and non-wildcard binding, separate disposable DB, no production DSN, fault-injection boundary, operator STOP control, bounded shutdown, process ownership and recovery journal. G1 Execute/Cleanup are separately NOT_AUTHORIZED; a successful G0 does not authorize G1. No remote commands, Apply, Rollback, merge or deployment are authorized by this document.

**Negative evidence acceptance:** mutate exact HEAD, tree, run ID, attempt, source hashes, JUnit counts/statuses, JSONL event inventory, ZIP member bytes/names, manifest hashes and archive digest independently; reject producer-only PASS, missing stages, duplicate or unknown entries, skipped/queued gates, non-owned cleanup and missing original process/network/DB evidence. Preserve original artifact bytes and compare to the trusted GitHub artifact digest. Passing synthetic mutation checks does not prove complete E2E or host custody.

**Independent verdict: CI FIRST_BOOT FAIL / LAB NO-GO; physical LS5→PC4 G0 BLOCKED, G1 NOT_AUTHORIZED, PC4 0/10 NOT_RUN, deployment NO-GO.**


## Source differential review, refreshed heads (2026-10-24)

#238 `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149`; #239 `41404048275adb610eac881550e2fa30dc54b326`; #240 `e908a9aa557efa6fb515cbaacb364757e5f283f8`; #241 `b97c9d2ba0bccf40e6a85861dddeade40dfde3b9`; #242 pre-update `6a0b1469b6c0562b06be28993235d4e1c778ce55`; #244 `780362f39246498a85ca268ece4fb274b11d5745`.

GitHub blob SHA direct comparison:
- #240/#244 `installer/ls5_pg_readiness.py`: both `233b5ac01f2b1d17be6f3e82c63b78cf4b464067` (same).
- #241/#244 `installer/ls5_network_offline.py`: both `daabde0da4a95adbae893b7f979ea322453c7bd7` (same).
- #239/#244 `installer/trusted_bootstrap.py`: `d1ab542d522f27ac351802f5fade5255b3ade3c2` vs `83c87c64de0fa049113b298f459ad4e004da9798` (different).
- #239/#244 `installer/ls5_bootstrap_ci_evidence.py`: `f21dfb30553da0a8e079744d580dd7a474d9073b` vs `6edd5e2933e4ce5bd12ff4de5a510d9336fc39e5` (different).
- #242/#244 `installer/ls5_e2e_acceptance.py`: `723d2462c3c39c778c19541fbc0c59db461fbfc1` vs `2091a4a13a119ee5dc8811d3378e1896ca5ebd48` (different).
- #242/#244 `installer/ls5_physical_acceptance.py`: `cb182a788256632ae3582d8b136982094ad980fe` vs `ba3b255bd66f14d41100660025cbdfbd21b6f494` (different).

**Confirmed P1 source-level parser differential:** PR #239's `installer/ls5_bootstrap_ci_evidence.py` rejects non-whitespace JUnit root/suite/case text/tails and duplicate/missing `(classname,name)` testcase identities; PR #244's exact file lacks these checks. Minimal reproducer: JUnit `<testsuite tests="2" failures="0" errors="0" skipped="0"><testcase classname="C" name="N"/><testcase classname="C" name="N"/></testsuite>` plus valid LS5_EXACT_HEAD and output path: #244 producer proceeds to `PASS` receipt while #239 rejects duplicate identities. A suite with injected non-whitespace structural text is likewise not rejected by #244. This is source-level differential; execute in an isolated harness before claiming runtime repro. Notify integration owner; do not modify their PR.

**P2 contract drift:** PR #239 `trusted_bootstrap.py` validates `active_release` as 40-hex commit, PR #244 compares it to `VERSION`. Requires owner decision about release version semantics, fixtures and trusted manifest; a blob mismatch alone does not establish unsafe deployment.

All other shared paths remain pending exact-blob comparison. **No physical GO.**


## Independently opened hosted run 40088816153 — raw ZIP checkpoint

Archive artifact `12558810048`, GitHub digest and independently calculated local SHA256 both `46308f0514488247dcdb2ac5e4b354cfcc3cb5d530a942356fa3f04ebdd1a21e`; 14 ZIP members, no duplicate names. Source head `297fcb7cd12c2d1eaf819242abd3267fa7bd5ee0`; run `40088816153`, attempt `1`; summary tree `7cc26c9bddeb67b8bd5ddee048d5044f8b4f02f2` (producer-reported tree; independently compare to GitHub tree before source provenance promotion). Internal first-boot manifest file digests all match their corresponding actual ZIP member bytes; all 26 JSONL events carry matching head/run/attempt; JUnit 26 cases, 4 failures, 0 errors, 0 skipped; 22 JSONL statuses `ISOLATED_E2E_PASS`, 4 `BLOCKED`. The four blocked stages are `postgres-restart-recovery`, `persisted-state-restart`, `controlled-shutdown`, `catalog-unchanged`. PostgreSQL 18 JUnit contains 32 cases, 0 failures/errors/skips. No physical execution: `0/10 NOT_RUN`, `Execute/Cleanup NOT_AUTHORIZED`.

Eight independent *copied-archive* mutations (summary HEAD, run, attempt, tree; JUnit failure count; JSONL forged event; manifest inventory; PG XML byte change) were rejected by a local checker pinned to the original archive SHA256 and summary context. **Limitation:** because these tests preserve the original externally trusted archive SHA256, they primarily demonstrate digest-based tamper detection, not resistance to a malicious producer who can recompute all internal hashes. No physical proof or lab GO can follow from these checks.

**Verdict: hosted CI FAILURE, E2E BLOCKED (22/26), G0 BLOCKED, G1 NOT_AUTHORIZED, Deployment NO-GO.** Future acceptance requires independently witnessed PostgreSQL restart/recovery and full stage completion on a new exact HEAD/run/attempt; no host connection authorized.


## New integration HEAD checkpoint — queued/skipped are not PASS

GitHub PR API: #238 `7df22d1c5cdc60bcf4e3414dacd35d23fdec7149`, #239 `4fad7f6f8430c36c893511c32a623b74a8539881`, #240 `9e5b392c4499127402eafe489f98cdb3c27855fa`, #241 `f8fe36f55451806bd9f7c6f71817fc4154815689`, #242 `2a7391b131e34032350f3b250b24f84cfeac6e52` (before this update), #244 `9efa0b947ea7f588437bb562da6f2b3729283709`.

At inspection, GitHub reports workflow runs for #244 latest SHA including queued and skipped; no independent complete required E2E evidence has been accepted for this SHA. The prior 22/26 report belongs exclusively to SHA `297fcb7cd12c2d1eaf819242abd3267fa7bd5ee0`, run `40088816153`, and must never be re-used as new HEAD acceptance.

Fresh Git blob comparison on latest heads: #240 `installer/ls5_pg_readiness.py` and #241 `installer/ls5_network_offline.py` are byte-identical to #244 (`233b5ac01f2b1d17be6f3e82c63b78cf4b464067` and `daabde0da4a95adbae893b7f979ea322453c7bd7`). #239 `installer/trusted_bootstrap.py` differs (`d1ab542d522f27ac351802f5fade5255b3ade3c2` vs `83c87c64de0fa049113b298f459ad4e004da9798`); #239 `installer/ls5_bootstrap_ci_evidence.py` differs (`f21dfb30553da0a8e079744d580dd7a474d9073b` vs `6edd5e2933e4ce5bd12ff4de5a510d9336fc39e5`). Previously identified source-level duplicate-JUnit-identity/structural-text regression persists in #244. Required negative CI proof remains pending. **Current exact HEAD: BLOCKED / NO-GO.**
