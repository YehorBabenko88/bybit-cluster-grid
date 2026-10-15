# Physical deployment preparation runbook

Status: PREPARATION ONLY. No physical installation, migration, runtime activation or network fault has been performed by this harness. Synthetic success is not evidence of production HA. The reviewed source is PR #188, commit 342112aa17f119c2db971c602c14587227835a98.

## Safety boundary

`physical-deployment-harness.ps1` accepts only PlanOnly. Its Python helper reads bounded JSON or JUnit and writes its report to stdout. There is no executor. Every physical stage remains NOT_RUN, requires explicit operator approval and has `execution_authorized=false` and `physical_ready=false`, including after all synthetic tests pass. Never supply production secrets in evidence. Saving stdout is an operator-approved file write; use a new review directory and do not overwrite existing evidence.

`collect-physical-node.ps1` defaults to PlanOnly and calls no providers. Explicit ReadOnly mode collects local metadata, holds the existing release mutex and invokes the shared Runtime Guard. It refuses LS5/LS7, existing test roots, redirected ancestors, active tasks/processes, unknown process identity and failed inventory. It does not run Python, psql, SSH or Tailscale binaries, connect to PostgreSQL, or probe another machine. Binary metadata is a compatibility hint: Python architecture, database server ownership/version and actual connectivity remain unproven. The supplied address is unverified. A snapshot grants no deployment authority; repeat approved inventory immediately before each separately authorized operation.

Never assume an existing directory, service, database, cluster or WAL belongs to Grid. Existing PostgreSQL services are informational and remain untouched. Never use ports 5432, 55432 or 55433 for a lab cluster. Proposed database names and ports are reservations for review, not proof of isolation. LS5/LS7 and production are excluded even when general account permissions exist.

## Existing mechanisms and gaps

| Component | Reused protection / deployment implication |
| --- | --- |
| install.ps1 | Plan default, guarded preflight, refuses existing tasks, disabled tasks, StartServices refusal. Apply uses fixed ProgramFiles/ProgramData roots; it cannot implement the proposed isolated lab installation. An independently reviewed isolated-root adapter is required before physical installation. |
| preflight.ps1 | Existing commissioning checks remain authoritative. It imports runtime and compileall can write bytecode; the read-only collector does not invoke it. |
| commission-network.ps1 | Existing Tailscale/TCP probes are active and may contact all online peers. Requires a separately reviewed target scope and operator approval; never called automatically. |
| collect-commissioning-inventory.ps1 | Reused informational stdout inventory. Tolerant providers do not establish safety; strict Runtime Guard and strict hardware providers run separately. |
| release-runtime-guard.ps1 | Shared task/process checks, unknown CommandLine rejection and alternative entry point detection. No duplicate guard is implemented. |
| stage-github-release.ps1 | Existing exact-head CI and manifest policy remains intact. Its audit branch allowlist does not accept this new branch; staging remains blocked until separate policy review. |
| switch-release.ps1 | Existing mutex, prepared/committed journal and atomic pointers remain authoritative. No harness call or pointer write. |
| rollback-release.ps1 | Existing schema/manifests/fencing checks remain intact. Even planning can query PostgreSQL; never called automatically here. No automatic schema downgrade. |
| recover-release.ps1 | Existing interrupted-transaction recovery is reused by the future operator plan; no new journal format or competing recovery engine. |

## Plan generation and evidence

Use a reviewed Python 3.12 executable and the exact commit SHA. These examples describe commands for a disposable review workspace; they do not authorize running inventory or deployment on a physical PC.

```powershell
# Read existing, operator-reviewed evidence; stdout only.
& ./installer/physical-deployment-harness.ps1 -EvidencePath ./fleet.json `
  -ReviewedVersion <exact-40-character-sha> -Python <trusted-python.exe>
# Same plan as a human-readable report:
& ./installer/physical-deployment-harness.ps1 -EvidencePath ./fleet.json `
  -ReviewedVersion <exact-40-character-sha> -Python <trusted-python.exe> -Format markdown
```

The input contract is schema 1, a 32-character lowercase hexadecimal run_id and 1–16 unique nodes. Each node has exactly: id, role, address, windows_major, cpu_logical, ram_bytes, disk_free_bytes, python_version, postgres_major, ssh_available, tailscale_available, runtime_stopped, inventory_complete, test_root, test_root_exists, disposable_cluster_confirmed. See `installer/tests/physical_harness_fixture.py` for synthetic examples, never reuse its fabricated values as physical evidence. Exactly one CONTROL is required. Addresses must be unique literal Tailscale addresses. Minimum planning policy: Windows major 10, 2 logical CPUs, 8 GiB RAM, 35 GiB free disk, Python 3.11/3.12 and PostgreSQL 16. Lab paths end with the unique run ID and node ID; no existing root or adopted cluster is accepted. A true disposable_cluster_confirmed is rejected: this preparation phase must not adopt a pre-existing cluster.

Plans order CONTROL first, then workers and stop at any failed safety check. They include one-node, two-node and full-fleet stages (without duplicate stages), both connectivity directions and unresolved application ports. Do not invent ports; obtain them from reviewed configuration. An approved probe must verify SSH host keys strictly, intended Tailscale identity and a read-only health endpoint. Installed clients do not demonstrate reachable servers.

JUnit conversion requires all reviewed selectors, no errors/failures/skips, consistent counters, unique case IDs and bounded safe XML. It produces eight scoped SYNTHETIC_PASS rows from eleven actual test cases, never physical PASS. Each row identifies the exact source SHA and workflow run ID. CI retains XML, JSON and Markdown together as `physical-synthetic-evidence-<sha>`; preserve these artifacts and the Actions job URLs in the operator record. Do not substitute local synthetic run IDs for GitHub run evidence.

## Readiness matrix

| Gate | Evidence / current status | Approval required |
| --- | --- | --- |
| Source and integrity | Exact-head CI, bundle/release manifests and artifact checksums; rerun per candidate | Before download/staging or pointer mutation |
| Synthetic faults | Reviewed selectors and actual JUnit; CI evidence only | None on disposable hosted CI |
| Windows compatibility | PS 5.1/7 mocked inventory and plan tests; built-bundle gate | None on disposable hosted CI |
| Physical inventory | NOT_RUN; fresh strict snapshot plus ownership/architecture review | Explicit ReadOnly target approval |
| Isolated installation | BLOCKED_FIXED_ROOT_INSTALLER; no executor | Reviewed adapter plus root/ACL/cluster ownership approval |
| One-node commissioning | NOT_RUN | Exact PC, paths, ports, binaries, tasks and operation list |
| Two-node recovery | NOT_RUN | Both target identities and bounded fault scope |
| Multi-node sequencing | NOT_RUN; each prior stage must supply reviewed evidence | Separate approval per additional node/stage |
| Physical readiness | Always false in this tooling | Independent operator acceptance |

## Staged operator procedure (not executed)

1. Review exact source/artifact hashes, complete CI evidence, dependency locks/manifests and all blockers. Approve only named disposable PCs; exclude LS5/LS7 and production. Confirm a rollback owner and stop conditions.
2. Approve read-only inventory on each target. Review CPU/RAM/disk, Windows architecture, Python runtime and package integrity, PostgreSQL 16 server binary provenance, SSH host keys and Tailscale peer identity. Unknown metadata stops the stage.
3. Separately approve creation of a new root and dedicated cluster: new OS process identity/data directory, non-production account/ACL, unused loopback port, empty database and run-specific ownership marker. Record proof before CREATE DATABASE or migrations. A loopback address alone is insufficient. Never connect to an installed cluster to discover ownership.
4. One-node stage: after the isolated-root installation blocker is resolved, approve exact install/migration/task actions. Keep trading, Telegram and automatic startup disabled. Verify durable receipts, WAL replay, schema and manifests using lab data only. Capture evidence and perform the approved rollback rehearsal before advancing.
5. Two-node stage: approve both directions of SSH/Tailscale/health tests, then a bounded worker/coordinator disconnect in the lab. Verify fencing generations, durable ingestion, reconnect and no duplicate live ownership. Resume only after clean evidence.
6. Multi-node stage: add one approved node at a time. Require previous-stage receipts, ownership checks and recovery results before each step. Stop immediately on unknown identity, failed guard, missing evidence, schema conflict, lost durability or unexpected destination.

## Fault recipes and approval boundaries

Run the exact synthetic selectors from `SCENARIOS` in `installer/physical_deployment_harness.py`. CI prohibits IP sockets and asyncpg connections and runs the fault process tree inside a fresh network namespace on a disposable GitHub-hosted Linux runner. These tests use fake DB writers and temporary files, not PostgreSQL or installed releases.

| Scenario | Synthetic boundary | Future physical rehearsal (explicit approval, disposable lab only) |
| --- | --- | --- |
| Worker crash/restart | OS WAL lock released after child crash; committed append retained | Kill only the recorded lab worker PID, restart reviewed binary; verify replay/receipt and exclusive ownership |
| Coordinator disconnect | WAL retained until durable receipt | Stop only lab coordinator endpoint; bounded timeout, restore, compare durable records |
| Network interruption | Socket/ACK disconnect and retry | Application-level lab proxy fault only; never disable NIC/Tailscale/SSH or firewall production |
| WAL checkpoint failure | Checkpoint publish failure retains unacked record | Inject file-operation failure inside owned lab fixture; preserve WAL for review |
| Disk full | Inject ENOSPC on fixture append, reopen previous record | Inject bounded filesystem adapter failure; never exhaust a real volume |
| Duplicate task | Reconciliation does not duplicate live task | Replay a synthetic lab command with same identity, inspect generation and deduplication |
| PostgreSQL interruption | Fake writer outage drains WAL after recovery | Fault only approved dedicated lab DB connection; never stop installed PostgreSQL |
| Interrupted switch/rollback | Synthetic interrupted replace recovery and repeated crash rollback | Fault-inject owned lab transaction, inspect prepared/committed journal, recover twice and verify idempotence |

No forced reboot, real disk exhaustion, production WAL replay, host network interruption or service stop is part of this harness. Physical evidence must include exact SHA, run ID, process/resource identity, injected boundary, expected invariant, observed counts/checksums and restoration result. Synthetic substitutes do not prove physical behavior.

## Rollback and stop checklist

- Stop progression immediately; do not retry writes against unknown ownership or failed guards.
- Keep all production resources untouched and preserve lab WAL, manifests, pointers and transaction journal. No automatic cleanup or deletion.
- Obtain fresh Runtime Guard and mutex checks immediately before any separately approved release operation. Never bypass fencing or schema checks.
- Review prepared/committed state with existing recovery tooling. Approve only exact lab pointer recovery; repeat recovery and confirm stable pointers/manifests.
- Roll back binaries only when existing compatibility checks permit. Schema 48 is not automatically downgraded; historical rollback remains subject to version-aware legacy validation and its documented restrictions.
- Restore only the approved lab processes/connectivity. Verify no stale worker writes, duplicate assignment or missing durable receipt before resuming.
- Cleanup requires separate explicit approval, verified absolute owned paths and retained evidence. Never delete an existing installation, shared service, database or WAL by name alone.

## Verification commands

On disposable CI or a reviewed synthetic workspace only:

```powershell
python -m pytest -q tests/test_physical_deployment_harness.py tests/test_physical_failure_boundaries.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-physical-inventory.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File installer/tests/test-physical-harness.ps1 -Python <trusted-python.exe>
pwsh -NoProfile -File installer/tests/test-physical-inventory.ps1
pwsh -NoProfile -File installer/tests/test-physical-harness.ps1 -Python <trusted-python.exe>
```

The dedicated workflow tests PS 5.1/7 and all eight fault scenarios. Existing Windows packaging also runs the mocked inventory and plan tests from the built bundle using bundled Python. Existing Runtime Guard, LegacyRollback, commissioning, composed contracts and isolated PostgreSQL CI gates remain mandatory. A green workflow is a scoped preparation result, not permission to deploy.
