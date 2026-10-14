# LS5 safe commissioning implementation plan

**Goal:** prepare repeatable Windows checks and explicitly gated installation without changing live machines.
**Architecture:** retain CONTROL election/runtime and migration 47. A read-only one-shot checker validates dependencies, release identity and database readiness; existing scripts gain safe defaults and stronger ownership checks. No new service architecture.
**Spec:** user request 2026-10-14; new branch from PR181 `061e28c6b3062a545997b319a05870b07d164f63`, which includes composed PR180 `a79ee1234b082f84dae9226a0b8cdfa0025a0249`.

Constraints: no deployment, permanent task start, trading, Telegram, old-install removal, non-Grid PostgreSQL mutation or secret logging. Source/user branches remain unchanged. Native worktree unavailable in projectless chat; isolated git worktree used.

- [ ] Reproduce unsafe manifest data path/restart behavior in mocked PowerShell fixture; constrain ownership paths and reparse points, make unchanged config a no-op and retain explicit apply/restart gates.
- [ ] Reproduce install default side effects with mocked OS providers; default plan-only, explicit apply, disabled tasks unless separately requested, refuse active/existing tasks and standalone archive writer. Preserve old installations.
- [ ] Add read-only Python preflight with stable secret-free diagnostic codes, bounded dependency checks, immutable release verification, DB migration/retention/runtime checks and optional bounded health smoke; unit and disposable PostgreSQL tests.
- [ ] Verify PR181 clean-schema retention initialization and migration47 idempotence with real disposable PostgreSQL; no database writes during checker runs.
- [ ] Audit existing bootstrap/provision/recovery launchers, role boundaries and dependencies; document unsafe legacy entrypoints and rollback blockers rather than execute them.
- [ ] Run Linux 3.11/3.12 full PostgreSQL and pinned three-repository contracts; Windows mocked installer/config fixtures on PS7/5.1 plus existing matrices.
- [ ] Publish separate Draft PR based on PR181; inspect exact-head Actions and fix genuine failures. Deliver LS5 read-only observations and exact phased commands, with activation requiring separate confirmation.

Review focus: forged ownership data path, junction/symlink parent, prior active gate, failed dependency/DB exception containing DSN/password, existing scheduled task replaced, and legacy rollback target without fencing. Each is tested or explicitly blocks commissioning.
