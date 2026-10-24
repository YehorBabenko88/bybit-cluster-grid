# LS5 + PC4 Physical Program Implementation Plan

> For agentic workers: use superpowers:executing-plans; no infrastructure execution.

**Goal:** G0 observation tooling and independently reviewable G1 plan, never authorization.
**Architecture:** separate opt-in metadata-only PowerShell observer; pure Python schema,
profile and evidence validators; read-only GitHub compatibility watch. Existing
installer, runtime guard, CI-only first boot and physical harness remain unchanged.
**Tech Stack:** Python3.11/3.12, PowerShell5.1/7, stdlib, existing bounded JSON parser.
**Spec:** user attachment22879a08-39e2-48de-8ff3-2118e5ed1edf.

## Global constraints

G0 only under confirmed owner access. No remote execution this session. G1/G2 are
NOT_AUTHORIZED. No services/tasks/ACL/users/DB changes, process starts/stops or cleanup
on physical hosts. No runtime authority from snapshot, hash, AI review or offline PASS.
Source branch: integration/full-system-first-boot-20261024 / PR244 only.

## Review focus

- Unknown provider/CommandLine/ACL must remain BLOCKED; no empty inventory PASS.
- Secret values, raw command lines, host/user identifiers never enter output.
- Parent paths, port conflicts, stale observations and replayed run IDs must block.
- GitHub missing/truncated/errors/skipped CI never imply compatibility.
- G1 approval data cannot cause execution: no executor is exposed.

## Tasks

- [x] Add failing Python tests for strict profile, snapshot identity/freshness,
  immutable authorization flags, port/root containment and stale evidence.
- [x] Implement pure contract and machine-readable profile/schema; rerun tests.
- [x] Add PowerShell fixture tests with mocked providers for opt-in observer,
  provider faults, unknown processes, reparse/ACL and secret redaction.
- [x] Implement metadata-only observer without command execution/network/SQL.
- [x] Add failing compatibility-watch tests for drift, hash disagreement, missing CI,
  workflow-only success, truncated/malformed snapshots; implement bounded GH reader.
- [x] Freeze current PR input hashes and document all reviewed source differences.
- [x] Add dedicated offline CI with PS5.1/7 fixture execution only on hosted runners.
- [x] Document exact executable G0 commands and per-stage G1 command templates with
  STOP/rollback and explicit unsupported runtime executor blockers.
- [x] Verify local offline tests, PS AST, compileall, actionlint and exact checkout;
  commit/push PR244 and publish actual Actions state and unresolved G0/G1 gates.

Validation:834 offline primary tests+138 subtests passed; PS5.1/7 mocked G0 cases7each.
Physical observation/execution remains NOT_RUN; hosted native/E2E failed at initial
HEAD38e6ab4 and requires follow-up after sendmsg regression + API diagnostics.
