# Real Python Windows containment implementation plan

> Execute inline with TDD and independent review. User explicitly authorizes autonomous source/hosted work, not physical G1.

Goal: replace inference from a tiny native probe with actual CPython + unmodified Grid imports/startup under the existing restricted-token/AppContainer/atomic Job boundary, without granting network capabilities.

Design: reuse OwnedChild/OwnedDesktop and native handle helpers via an internal executable-bundle interface. A separate hosted-only main stages a complete measured CPython stdlib/native/dependency/source closure into a fresh GUID AppContainer profile. Immutable paths have package RX; own data/results have separate package RW/low label. Hold file/ancestor identities, DACL and hashes. Explicit ._pth and -I -B -S prevent ambient Python paths/site/PATH. Explicit environment contains no CI/production credentials. No inherited handles. Active-process limit1 prevents orphan subprocesses; suspended atomic Job attachment remains mandatory.

Actual Python attempts own data access, denied external canary reads/writes, forbidden subprocess creation, and network access to a parent-owned loopback sentinel and documentation-only IP. It imports actual grid.coordinator/grid.worker, runs Coordinator.startup expecting denied database connectivity with no leadership, then Worker.run briefly in INFRA_ONLY expecting no assignments/market tasks. These are actual components but NOT Windows E2E/registration or proof of a viable allowed transport. No network exemptions, firewall rules, physical ACL or installed runtime changes.

- [ ] Test-first bounded source bundle builder: collisions, traversal, source drift, symlinks, unknown files, local/self-hosted denial.
- [ ] Native immutable runtime/data staging and existing launcher reuse. Keep fixed native probe checks intact.
- [ ] Actual Python negative driver and independent token/job/process checks. Strict exact-source receipt/JUnit/JSONL.
- [ ] Required hosted Windows5.1/7 x Python3.11/3.12 CI, preserve all historical branch exclusions and existing gates.
- [ ] Independent source/adversarial artifact review; rerun exact-head full CI; publish raw receipts and limitations.

STOP: capability-free AppContainer cannot serve Grid TCP. Do not add broad capabilities or loopback exemptions. Owner signature trust distribution, external durable anti-rollback/freshness, actual reboot custody and physical G0 effective rights remain P0 BLOCKED. In-memory keys or local files alone cannot solve privileged whole-state rollback. All20physical phases retain null argv and false authority.
