# Windows node onboarding: Discovery → PlanOnly → authorized Apply (design proposal)

Date: 2026-10-23
Status: PROPOSED / REVIEW REQUIRED. This document does not authorize provisioning, deployment, merge, or physical tests.

## Intent and constraints
Make adding Windows machines to Bybit Cluster Grid repeatable without treating network reachability or synthetic checks as security acceptance. Support dynamic node counts and existing coordinator/worker roles. Maintain separate operator authorization for every mutation on a physical host.

Observed PC4/LS5 evidence (2026-10-23): LS5 100.103.160.110 reaches PC4 100.91.48.20 on TCP/5432; pg_isready accepts; server uses PostgreSQL 18, listens on *, ssl=off, HBA has localhost-only SCRAM entries. Remote psql attempt is rejected by HBA for 100.103.160.110. These observations are host-specific, not defaults for other machines. Prior physical SID/ACL tests: 0/10 NOT_RUN; Execute NOT_AUTHORIZED; overall NO-GO.

## Approaches considered
A. Fully automatic installer that discovers and applies changes: rejected because incomplete identity/custody evidence could alter physical systems.
B. Manual runbook per host: safe but error-prone and not scalable.
C. **Chosen proposal:** declarative per-host manifest; read-only discovery; deterministic PlanOnly; separate explicitly authorized, independently verified Apply. No auto-promotion from model/synthetic to physical GO.

## Architecture
1. **Inventory manifest**: stable node ID; intended role; expected Tailscale identity/IP and SSH host key fingerprint; Windows OS/architecture; PostgreSQL intended role (none/local/remote client/server); expected port; allowed client CIDRs as exact /32 or /128 by default; required transport policy; paths; owner approvals. Reject ambiguous, wildcard, duplicate or conflicting identities. Never include credentials.
2. **Discovery (read-only)**: host/OS/service identity, Tailscale connectivity, SSH identity, network profiles, active firewall rule scope, ESET presence/status (not inferred packet verdict), PostgreSQL executable/service/port, effective pg_settings (config_file/hba_file/listen_addresses/ssl), parsed HBA rules, filesystem ownership/DACL/SACL where authorized, reparse/hardlink/custody observations. Missing permissions yield UNKNOWN/BLOCKED, never PASS. No passwords in receipts.
3. **PlanOnly (offline/deterministic)**: compare evidence to intended state; output change plan and explicit risks/dependencies. Preflight gates for exact host identity, timestamp/freshness, signed/hashed evidence, least privilege, rollback capability, existing service collisions, PostgreSQL TLS policy and HBA scope, protected staging custody, and pre-existing policy conflicts. Refuse remote superuser postgres for Grid. Explicitly distinguish network-ready, DB-ready, physical security ready and deployment-ready.
4. **Apply (future, separate authorization)**: no executable mutation path until reviewed implementation and explicit per-node approval. Approval must bind node identity, plan SHA256, operator, expiry and allowed operations; revalidate identity/evidence immediately before each action. Snapshot configuration and ACL, stage atomically, perform narrowly scoped changes, verify and rollback on failure. Never disable ESET, broadly open firewall, use 0.0.0.0/0 HBA, or silently overwrite manual settings. Any credential generation stays local with protected custody.
5. **Acceptance evidence**: immutable-ish run ID, UTC timestamps, node identity and evidence provenance, exact Git HEAD and tool versions, JSONL events, strict JUnit XML, SHA256 manifest covering outputs, explicit NOT_RUN/BLOCKED/FAIL/PASS. Separate synthetic/physical evidence namespaces; a missing, malformed, skipped, or mismatched artifact blocks promotion.
6. **Rollout**: LS5 read-only baseline → PC4 read-only baseline → owner approval of staging/roles/TLS topology → offline PlanOnly tests → separate provisioning approval → independent post-change custody check → separately authorized CollectLocal → 10 physical SID/ACL tests → commissioning decision. No steps combined.

## Interfaces proposed (subject to repository review)
- Discovery input: node manifest and optional existing signed snapshot; output: versioned observation JSON + JSONL evidence.
- PlanOnly input: manifest + observation + policy version; output: deterministic plan JSON, human-readable report, JUnit, SHA256.
- Apply input: approved plan hash + narrowly scoped authorization token/record; output: per-step receipt + rollback journal. Apply must not be invocable by default CI jobs.
- CI: schema validation, offline fixture tests, malformed/hostile inputs, replay/TOCTOU, identity conflicts, HBA and TLS regression cases, artifact validation. Never require or contact physical hosts.

## Test matrix / adversarial cases
- Reachable TCP but HBA rejects: network PASS, database authorization BLOCKED.
- ssl=off when TLS is required: BLOCKED; Tailscale encryption does not satisfy DB TLS policy by itself.
- Duplicate SID/ACE, inherited ACE, DELETE_CHILD on parent, WRITE_DAC/OWNER, reparse/junction/hardlinks: BLOCKED on ambiguous custody.
- Spoofed SSH/Tailscale identity, stale or conflicting snapshots, host key change: BLOCKED.
- Malformed JSON/duplicate keys, missing JUnit or receipt, SHA mismatch, skipped CI: BLOCKED.
- Two concurrent Apply attempts, interrupted writes, partial rollback: fail closed, no GO.
- No database or PostgreSQL role on worker-only node: should not provision PostgreSQL unnecessarily.

## Explicit non-goals
No automatic PostgreSQL HBA edits, TLS enablement, role creation, service changes, firewall edits, ACL edits, Tailscale configuration changes, merge or deployment under this design PR. No physical test authorization.

## Open decisions before implementation
- Choose actual code module locations after examining installer and CI code on relevant PR HEADs, not just default main.
- Confirm which machines are database servers versus clients; whether PostgreSQL TLS is mandatory even inside Tailscale; and who signs physical Apply approvals.
- Review PR #216/#223/#224/#225 integration constraints and current heads before implementation.
