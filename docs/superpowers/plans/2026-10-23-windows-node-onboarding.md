# Windows Node Onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic, fail-closed Windows node discovery and planning, with no physical mutations without a separate per-host approval.

**Architecture:** Build an offline manifest/observation validator and PlanOnly evaluator first, independent of physical machines. Integrate with the protected-staging chain only after exact HEAD and contract review. Apply is a later independently authorized milestone, not an extension of PlanOnly success.

**Tech Stack:** Python stdlib, PowerShell for read-only Windows discovery, pytest, JSON Schema as already used by relevant staging PRs, JUnit XML and SHA256 receipts.

**Spec:** docs/superpowers/specs/2026-10-23-windows-node-onboarding-design.md

## Global Constraints
- Physical SID/ACL tests PC4 0/10 NOT_RUN; Execute NOT_AUTHORIZED; Grid Deployment NO-GO.
- Never modify Tailscale, Windows Firewall, ESET, PostgreSQL, ACL, services, secrets, or physical host during Discovery/PlanOnly.
- Never merge or deploy automatically. No remote PostgreSQL superuser usage by Grid.
- Missing, stale, conflicting, or unauthenticated evidence => BLOCKED.
- Do not accept synthetic PASS as physical acceptance.
- Existing PR dependency chain: #216 base planning/pgdata-intent-v1-20261021; #223 on #216; #224 on #223; #225 on #224. Review exact HEADs before changing their modules.
- All changes in new draft branches, no modification to existing PR #216/#223/#224/#225.

## Review Focus
1. Duplicate JSON keys or malformed identity fields: reject instead of last-value-wins.
2. Host identity changed after discovery: block PlanOnly and Apply.
3. TCP readiness success but PostgreSQL HBA rejects: separate network PASS and auth BLOCKED.
4. ssl=off despite required PostgreSQL TLS: BLOCKED, even when Tailscale transport exists.
5. JUnit skipped/missing, receipts mismatched, synthetic evidence offered as physical: BLOCKED.

---

### Task 1: Inventory and exact dependency audit

**Files:**
- Create: docs/windows-onboarding/dependency-inventory.md
- Test: no runtime test; compare exact branch HEAD and changed paths with GitHub PR metadata.

**Interfaces:**
- Consumes: #216/#223/#224/#225 PR metadata and changed file list.
- Produces: dependency inventory with exact refs, ownership boundaries, and chosen isolated implementation base.

- [ ] Record exact HEAD SHA and base SHA for each PR and note changed files relevant to installer, staging, and CI.
- [ ] Identify existing schemas, scripts, test runners, and policy contracts by reading actual files from the correct refs.
- [ ] Confirm there is no overlapping writer of new onboarding modules; record blocked integration points.
- [ ] Commit inventory and verify no physical-system interaction occurred.

### Task 2: Offline manifest validation (TDD)

**Files:** Determine exact paths from Task 1; prefer a dedicated small module and dedicated tests.

**Interfaces:**
- Consumes: manifest JSON with schema_version, node_id, expected identity, role, intended PostgreSQL role, allowed /32 or /128 peers, and policy.
- Produces: structured PASS/BLOCKED with reason codes; never writes host settings.

- [ ] Write tests for valid minimal node, duplicate JSON keys, wildcard CIDR, malformed SID/hostname, duplicate identity, and missing required fields.
- [ ] Run tests and confirm RED for missing validator.
- [ ] Implement strict offline validator, with explicit allowlist of schema keys and canonical identity.
- [ ] Run targeted tests GREEN and full existing suite; commit with test evidence.

### Task 3: Observation normalization and PlanOnly (TDD)

**Files:** New focused observation parser, plan evaluator and tests, based on Task 1 inventory.

**Interfaces:**
- Consumes: validated manifest, observations, provenance and freshness metadata.
- Produces: deterministic plan with per-check PASS/BLOCKED/FAIL/NOT_RUN, never executable instructions by default.

- [ ] Write failing fixtures for LS5→PC4 case: TCP/5432 PASS, pg_isready PASS, HBA auth BLOCKED, ssl=off BLOCKED under required-TLS policy.
- [ ] Write failing tests for unknown/partial ACL, stale evidence, identity mismatch, conflicting sources and worker with no PostgreSQL requirement.
- [ ] Implement PlanOnly evaluator; never promote UNKNOWN or synthetic to physical GO.
- [ ] Verify targeted and full tests; commit.

### Task 4: Read-only Windows discovery adapters (TDD)

**Files:** Read-only PowerShell modules plus parsing tests, exact paths determined in Task 1.

**Interfaces:**
- Consumes: target local machine only; explicit authorized remote collection is out of scope.
- Produces: typed observations without secrets; errors are data with UNKNOWN/BLOCKED.

- [ ] Write offline tests for parsing missing executable/service, localized Windows output, ESET present without asserted packet drops, firewall scope, PostgreSQL effective config, and HBA rules.
- [ ] Confirm RED, implement read-only discovery with no service restart or network mutation.
- [ ] Verify PowerShell syntax on a Windows CI runner and offline fixture tests on Linux; commit.

### Task 5: Evidence and CI gate (TDD)

**Files:** Dedicated receipt writer/validator, CI workflow, tests.

**Interfaces:**
- Consumes: plan and observations.
- Produces: JSONL, strict JUnit XML, SHA256 manifest, explicit exact HEAD and run kind.

- [ ] Write failing tests for missing/malformed artifacts, wrong SHA, skipped workflows, replayed evidence and synthetic-to-physical promotion.
- [ ] Implement fail-closed validator and generate deterministic artifacts.
- [ ] Run targeted/full suites and verify Windows/Linux Actions on exact commit; commit.

### Task 6: Integration and independent acceptance

**Files:** Documentation and integration glue only after reviewing #225 exact contracts.

- [ ] Verify no weakening of S1–S7 protected staging, custody, privilege and TOCTOU constraints.
- [ ] Independently review test inventory and red/green proof; record P0/P1/P2.
- [ ] Create a **new Draft PR**, explicitly stating whether stacked on #225 or independent of it, with HEAD, CI run IDs and limitations.
- [ ] Leave Apply unimplemented until separate design, owner approval, rollback validation and physical custody authorization.

## Completion criteria
- Offline Discovery/PlanOnly is deterministic, tested and fails closed.
- No remote/physical execution occurred; no credentials in evidence.
- All claimed CI PASS refer to real runs on exact HEAD; otherwise report NOT_RUN/BLOCKED.
- Draft PR only, no merge. Physical tests remain 0/10 NOT_RUN and deployment NO-GO.
