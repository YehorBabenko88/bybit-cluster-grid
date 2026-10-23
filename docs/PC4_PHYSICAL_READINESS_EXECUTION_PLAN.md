# LS5 → PC4 physical readiness — controlled acceptance plan

Status: **PLAN ONLY / NO-GO**. Source candidate: PR #235, exact HEAD `1845ee22e71e1629224cff8a8e65db5ee21a6263`. This document grants **no** permission to execute actors, change accounts/ACLs, clean fixtures, merge, deploy, or touch production data. Physical SID/ACL: **0/10 NOT_RUN**.

## Evidence contract
Each stage records: exact UTC timestamp, machine name, executing SID/elevation, OS/build, source HEAD, reviewed script SHA256, input/expected artifact SHA256, stage ID, status (PASS/FAIL/BLOCKED/NOT_RUN), immutable run ID, operator identity and approval reference. Preserve original command output; sanitize secrets, private IPs and credentials before sharing. `SKIPPED` is **BLOCKED**, never PASS. Synthetic success never implies physical authorization. Retain raw artifacts read-only and produce a separate independently verified SHA256 inventory. A single failed mandatory gate is STOP.

## Stage 0 — GitHub integration (remote/offline; no physical hosts)
- Pin PR #235 exact HEAD and base; independently review the 28 changed files and 11 workflow changes.
- Branch-name `if:` exclusions in unrelated workflows are a P1 integration risk. Restore mandatory general CI on the candidate or provide reviewed equivalently fail-closed checks. Require all mandatory jobs to finish SUCCESS for the **same exact SHA**, not SKIPPED, neutral or cancelled.
- Independently download all six artifact ZIPs, compare GitHub artifact digests, manifest contents, source hashes, JUnit case IDs and inventories. Ensure every artifact binds exact SHA, run ID, attempt and platform.
- Distinguish two Windows-built DLL hashes; select one pinned artifact only after independent custody verification. Do not substitute the older PC4 staged DLL or manifest.
- PASS: all required jobs SUCCESS; independent checks PASS; no unresolved P0/P1. Otherwise BLOCKED.
- STOP: altered head/base, missing or skipped gate, hash mismatch, unreviewed workflow suppression.

## Stage 1 — LS5 read-only survey (operator-run locally, separately authorized)
No SSH from assistant; no changes. Confirm Windows identity/elevation, local time/UTC, OS/build, services and listening sockets for coordinator, PostgreSQL service/PGDATA, available space, network route to PC4 and SSH host key. **Do not** run deployment, account changes, scripts from staging or DB writes. Never collect passwords/private keys.
- PASS: owner signs a topology inventory: LS5 as gateway, PC4 target, required ports, coordinator process identity, host-key fingerprints, approved staging path, filesystem volume and custody assumptions.
- STOP: unexpected service/process identity, conflicting listener, unknown writable ancestor, reparse point, missing authorization.
- Output: LS5_READONLY_SURVEY.json and command transcript; classify unknowns BLOCKED.

## Stage 2 — protected staging design (offline review)
- Specify owner/SID and exact DACL/SACL for every ancestor, target folder and file. Examine inherited ACEs, DELETE_CHILD on parents, WRITE_DAC/WRITE_OWNER, privileges, reparse/junction/hardlinks, writable TEMP/toolchain and TOCTOU.
- Verify deployment identity and independent witness identity; no implicit trust in admin-only observations. Document allowed source→target transfer, atomic receipt, no executable content until custody complete.
- PASS: independent security sign-off on staging threat model and ACL matrix. STOP on missing parent or group-attribute evidence.

## Stage 3 — account provisioning (separate explicit owner approval)
- Approve the plan for GridLabCollector and GridLabStorage SID, Enabled state, logon rights, password handling, role restrictions and cleanup ownership. Current plan **must not** silently enable accounts or change policy.
- Provisioning, if later approved, is a distinct operation with backup and rollback evidence. Do not include credentials in tickets/logs.
- PASS: identity and rights independently verified with separate receipt; STOP on mismatched SID or broad rights.

## Stage 4 — package transfer and custody (separate explicit approval)
- Download a **single pinned** CI package from Stage 0, verify ZIP digest before extracting in an approved protected staging area, and compare all files to manifest and exact HEAD.
- Preserve old package separately; never overwrite or execute older staged files as if they were PR #235.
- Record machine-local SHA256 for each of the seven/eight files as applicable, package manifest hash, signer/source provenance, file owner, DACL, link count and file ID. Recheck after transfer.
- PASS: two independent receipts (sender and receiver) agree byte-for-byte; otherwise STOP. No automatic promotion from mock to physical.

## Stage 5 — PlanOnly / independent read-only verification
- Before any execution, verify **deployed** controller's PlanOnly behavior, its exact SHA256 and review record, and that `-Execute` and `-Cleanup` fail closed *before* host observations. No actor launch, DLL native call, fixture creation or credential prompt.
- Obtain independent evidence of process lifetime and cleanup safety. In PR #235, Cleanup is explicitly unimplemented/blocked and Execute explicitly unauthorized: do **not** bypass these guards.
- PASS here means PLAN/READINESS EVIDENCE ONLY, not physical test authorization.

## Stage 6 — physical PC4 10-case SID/ACL (NOT AUTHORIZED)
Prerequisites: stages 0–5 PASS; separate approved change ticket specifying exact run ID, machines, scope, start/end, approvers, test operator, stop conditions and recovery owner; independently reviewed implementation that removes execute block under a separately controlled release, without broadening permissions; no production DB access.
- CollectLocal only after explicit approval and independently pinned binary, then ten cases (Collector/Storage × token, own_write, own_read, foreign_read_denied, foreign_write_denied). Cross-check native Win32 ACCESS_DENIED_5, exact process handle/start time, account SID, canaries and before/after ACL.
- Independent witness validates JUnit, JSONL, SHA256, shutdown receipts and no unaccounted child processes. `physical_attestation=false` cannot become physical PASS.
- STOP: unexpected write, process uncertainty, PID reuse, untrusted path, SID/ACL mismatch, altered HEAD, tampered evidence, missing exit receipt. Mark BLOCKED/FAIL, preserve partial evidence.

## Stage 7 — rollback and cleanup (NOT AUTHORIZED)
- A STOP is not permission to delete. Preserve evidence and stop further launches. Do not kill a process by PID after identity uncertainty.
- Cleanup requires separately reviewed native handle-relative implementation with pinned ancestor/file identity, same-volume, no-reparse, link-count and race proof, confirmed original-process exits, independent approval and rollback rehearsal. Current PR #235 has **no authorized cleanup**.
- Rollback must restore only changes explicitly recorded in approved provisioning/deployment receipts; never modify production data or remove unknown files.

## Stage 8 — expansion beyond PC4
Only after independent LS5+PC4 acceptance, plan PC1/PC2/PC3/LS7 individually. Respect PC1 agent permitted runtime Mon–Sat 15:00–05:00, Sunday 24h; do not schedule out-of-window work. Re-evaluate topology and security boundaries per node; never infer GO for one machine from another.

## Operator handoff checklist
- [ ] Exact SHA pinned; base unchanged; independent source/CI review
- [ ] All required CI SUCCESS (no skipped mandatory jobs)
- [ ] Six ZIPs independently verified and selected deployment ZIP identified
- [ ] LS5 read-only topology and service/process identity evidence signed
- [ ] Staging parent/child SID, owner, DACL/SACL and custody independently signed
- [ ] Account plan and rollback independently approved
- [ ] New package delivered with matching receiver SHA256; old package quarantined
- [ ] PlanOnly and immutable Execute/Cleanup blocks confirmed
- [ ] Independent physical-test authorization **separately** issued
- [ ] Independent evidence reviewer assigned; STOP and rollback rehearsed

**Present verdict:** Stages 0–5 incomplete. Stage 6: 0/10 NOT_RUN. Execute NOT_AUTHORIZED. Cleanup NOT_AUTHORIZED. Deployment NO-GO.
