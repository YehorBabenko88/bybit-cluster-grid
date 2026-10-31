# Optional Raft authority for the existing Grid leader

This is source and cloud-lab preparation. Physical deployment, office PCs, real databases, LS5/PC4/ADMINIT services and automatic physical updates are not authorized. Linux Docker results do not qualify native Windows, hosted CI or physical fault domains.

## Decision and alternatives

Retain Grid's FloatingLeader, leader callbacks, PostgreSQL epochs, job CAS and resource-side leases. Add Consul sessions and KV transactions as an explicit, optional independent authority. Do not implement Raft, another scheduler or a SQLite quorum model.

| Candidate | Decision |
| --- | --- |
| PostgreSQL service_leases alone | Retained as a resource fence; rejected as replicated consensus or an independent authority for promoting its own primary. |
| etcd Raft | Sound DCS alternative; its gRPC integration and native Windows qualification add work to this HTTP-oriented runtime. |
| ZooKeeper | Sound consensus service, but adds JVM/service operations and Windows qualification. |
| Windows Failover Clustering | Platform-native alternative requiring a separately planned Windows Server cluster/administration and its own acceptance evidence. No office configuration is permitted here. |
| Consul Raft | Selected minimal adapter: session TTL, persistent KV, atomic session/index transactions, existing HTTP dependency and vendor Windows binaries. Windows production operation remains NOT_RUN. |

Official Consul 2.1.0 release checksums list both linux_amd64 and windows_amd64. Upstream also contains a Windows server container/integration harness; this establishes available source/build artifacts, not support certification for this deployment. Release/license and platform support must be reviewed for the eventual installation. Source references: https://github.com/hashicorp/consul/releases/tag/v2.1.0, https://releases.hashicorp.com/consul/2.1.0/consul_2.1.0_SHA256SUMS, https://github.com/hashicorp/consul/blob/main/Dockerfile-windows and build-support/windows/windows-test.md. No vendor binaries or license terms are repackaged by this patch.

## Interfaces and opt-in

`ConsulConfig` takes explicit endpoints, namespace, ACL token, CA bundle and mutual TLS certificate/key. Production mode rejects HTTP and absent TLS/ACL inputs; the client keeps certificate verification and redirects disabled. Its default HTTP client preserves environment proxy settings. The isolated cloud harness alone injects a direct HTTP client for its manifest-verified internal Docker IPs; it does not bypass Internet egress policy.

```python
from grid.coordination import ConsulConfig, ConsulSessionAuthority, floating_leader_guard
from grid.floating_leader import FloatingLeader

config = ConsulConfig(
    endpoints=("https://consul-1:8501", "https://consul-2:8501", "https://consul-3:8501"),
    namespace="grid/OWNER_PROVISIONED_CLUSTER_GENERATION",
    acl_token=secret_store_token,
    ca_bundle=trusted_ca_path,
    client_certificate=service_certificate_path,
    client_key=protected_private_key_path,
)
authority = ConsulSessionAuthority(config)
leader = FloatingLeader(pool, node_id, coordination=authority)
rollout_guard = floating_leader_guard(leader)
```

There is no automatic activation and no fallback to PostgreSQL-only leadership when a configured DCS fails. A caller omitting coordination retains legacy behavior, which must not be advertised as HA. The current coordinator explicitly constructs the authority from Settings in config.py and supplies it to the existing election instance; ControlCandidate also accepts the explicit authority. This changes the existing startup/loss lifecycle rather than creating a second service launcher. Production activation remains blocked without independent watchdog/fencing qualification.

* `await acquire(owner)` returns `ConsulLease(owner, session_id, token)` or None for contention. The token is the lock's committed Raft ModifyIndex, not a PID, wall clock, PostgreSQL epoch or invented counter.
* `await renew(lease)` and `await validate(lease)` return strict booleans. Validation requires a consistent read binding the exact Session, ModifyIndex, owner and namespace. Only the exact locally issued lease is accepted; reconstructed/foreign-instance leases do not acquire observer authority. Validation rechecks the captured conservative deadline and local session binding after the consistent read, so a delayed response or concurrent release cannot extend authority. No stale-read option is exposed. Failures and local TTL deadlines deny authority; renewal never resurrects an expired local lease.
* `await release(lease)` destroys only a session created by that authority instance. It releases the persistent lock and never deletes its key.
* `await write_control(lease, name, payload)` performs an atomic Consul transaction checking the lock session and index before writing bounded canonical control state. An old owner cannot publish after takeover, even if a client-side validation raced with reassignment.
* `await read_control(name)` uses a consistent read and returns the durable owner/token/session/payload envelope. Callers must bind this evidence to their own domain identities and expected checkpoint.
* `floating_leader_guard(leader)` yields an async callback returning the existing PG `{'owner': ..., 'epoch': ...}` only while both the exact DCS lease and live PG service_leases owner/epoch/expiry remain current. This PG epoch and the separate Consul ModifyIndex must not be conflated.

FloatingLeader obtains the DCS session before campaigning for the existing PG lease, validates it after the PG commit, renews both, and clears local leadership on either failure. Shutdown retains existing cleanup-before-release ordering. Resource mutations still need their existing transactional epoch/job-token fences. Network loss cannot instantaneously stop an already executing process; callers must validate at protected boundaries and targets must reject superseded tokens.

## PostgreSQL promotion boundary

A DCS lock does not fence a PostgreSQL primary or make two databases one transaction. Promotion must independently verify hard fencing of the old primary, exact current candidate/session/token, replay through a trusted durable acknowledged LSN and candidate recovery state, then recheck immediately before promotion. The PG HA controller owns that protocol. A stale service row on an isolated old primary must never authorize a new primary without independent hard fencing. Unknown fencing, quorum loss and incomplete replay deny promotion.

The DCS's protected placement record demonstrates durable assignment and fenced reassignment; it is not proof that every domain job's checkpoints/results have been replayed. Grid's existing CAS/retry/checkpoint mechanisms remain the job owner.

## Five-voter cloud evidence and limits

The explicit lab scripts use the cloud-local unix Docker socket, a unique internal network, immutable image digests, owned labels/IDs, no host ports and no restart policies. Fault injection touches only those container namespaces. The manifest and evidence stay outside production roots.

The real Consul 2.1.0 image digest is `sha256:259fd02f2544fe1aa03fa49efd3b105c8dd67106d710a72f5e898110266356f7`. Tests retained all five configured Raft voters while abruptly losing the current leader and then another voter; quorum-backed control writes and reads succeeded with four and then three live voters. A real two-versus-three partition preserved intra-minority traffic and blocked minority/majority communication in owned network namespaces. The minority could not renew or publish, majority TTL takeover received a higher token, old writes remained rejected after healing, and a successor placement was persisted. All five voters and namespace firewall rules were restored.

This demonstrates the tested Raft scenarios in one disposable cloud host, not physical two-host-loss tolerance, full-system availability, Windows service recovery, vendor platform support or production TLS/ACL qualification. Five voters require five independent intended fault domains; three votes are a majority. Losing more than two voters must deny writes. Production gossip encryption, mTLS for peer/client traffic, default-deny ACLs scoped to the cluster KV prefix and intended session node prefixes, restricted peer ports, durable disks, backups, monitoring, clock/runtime health and native Windows qualification remain mandatory deployment gates.

Snapshots/restores need explicit recovery fencing: stop/fence old actors and provision a new owner-controlled cluster-generation namespace before accepting restored state. Do not assume a restored Raft index is globally monotone across a disaster restore or reuse an old session/token as fresh authority.

Lab commands require the explicit `--execute-isolated-cloud-lab` flag. `provision.py` creates only its owned resources; `verify.py` performs fault injection and restores those resources; `verify_floating.py` uses only a named cloud-local grid_test schema to verify dual-fence integration. None is a physical deployment command.

## Actual coordinator wiring and fail-closed lifecycle

The current `grid.coordinator.startup` now calls `coordinator_authority(settings, external_fence_verifier=...)` before database or singleton startup. It passes the configured authority to the existing FloatingLeader. The original singleton services (refresh/rebalance, Telegram, retention, maintenance, ML and science) start through its gain callback and are cancelled/closed through its loss callback. Retention schema creation completes before the maintenance/retention tasks race to use it. Existing ingestion and job protocols are retained.

The coordinated run path renews independently of a slow asynchronous initializer, cancels partial initialization on loss/cancellation, revalidates both fences before `ready=True`, and confirms cleanup before releasing the lease. Cleanup failure/timeout sets permanent `requires_fencing`, clears readiness/leadership and stops campaigning. It does not assume unknown writers stopped. Legacy run behavior remains for single-primary compatibility and must never be represented as this HA mode.

The actual HTTP middleware denies every endpoint except liveness `/health` and `/ready` until current coordinated readiness and fresh dual-fence validation. `/ready` checks the fresh guard. `app.state.grid_lease_guard` supplies the existing PG owner/epoch to rollout callers, bound to the separate current Consul session/token. Protected PG reads/campaign/renew operations are deadline-bounded. The actual cloud entrypoint probe starts the real existing singleton services, requires no ERROR log records, verifies ready HTTP200, revokes its own DCS session and observes HTTP503 plus confirmed service cleanup.

Explicit Settings/environment fields are:

* `GRID_COORDINATION_MODE=legacy|consul` (default legacy); `GRID_HA_REQUIRED` rejects legacy fallback.
* `GRID_CONTROL_NODE_ID`; `GRID_LEADER_LEASE_SECONDS`; `GRID_LEADER_RENEW_SECONDS`; `GRID_LEADER_CLEANUP_TIMEOUT_SECONDS`.
* `CONSUL_ENDPOINTS` (JSON array), `CONSUL_NAMESPACE`, `CONSUL_ACL_TOKEN` (secret), `CONSUL_CA_BUNDLE`, `CONSUL_CLIENT_CERTIFICATE`, `CONSUL_CLIENT_KEY`, `CONSUL_TTL_SECONDS`, `CONSUL_REQUEST_TIMEOUT`.
* `GRID_COORDINATION_ISOLATED_LAB` is false by default. Only explicit controlled cloud fixtures use plaintext lab endpoints; it is not a physical deployment permission or HA attestation.

Production Consul startup, and any `GRID_HA_REQUIRED` startup, is blocked unless an owner-trusted `app.state.external_fence_verifier` verifies the independent writer watchdog/fencing capability. No boolean/environment flag is accepted as that proof. An independent OS/process watchdog backend is **NOT_IMPLEMENTED / NOT_QUALIFIED** in this patch. The asynchronous renewal loop and PG `supervise_writer` run on the same event loop and do not prove containment when that event loop stalls. Accordingly current production physical HA readiness is **BLOCKED**, even though the source wiring and disposable cloud lifecycle/consensus scenarios pass. An actual independently monitored, exact-writer-bound failure action remains a prerequisite; an arbitrary callback returning true does not constitute deployment evidence.

## Final preparation checkpoint and evidence scope

Shared Grid regression after the runtime and PG/update-owner fixes: **1183 passed, 12 Windows-only skipped, 46 subtests** in the final shared run. Local tests do not substitute for hosted exact-head Windows qualification.

The initial real five-voter fault matrix completed successfully. Later repeats preserved successful one/two voter-loss and minority-takeover observations but did not issue a final success receipt: an owned restarted endpoint was not yet ready, and a subsequent restored-five check exceeded its recovery budget while Docker reassigned ephemeral addresses. Those failed attempts remain preserved rather than rewritten as passes. The harness now derives refreshed endpoints only from the same immutable container IDs/image/labels/internal network, preserves previous manifests, and has a bounded recovery wait. No final new complete fault-matrix success is claimed for those repeats.

Current final-code probes separately pass real Consul + isolated PostgreSQL coupling, stale server transaction rejection (HTTP409), monotone PG and DCS successor fences, and actual coordinator startup/readiness/session-loss cleanup. The entrypoint probe uses its own fresh cloud database with public schema, because the existing application schema audit explicitly targets public; a search_path-only fixture otherwise produces a real diagnostic failure. The shared grid_test database and other owners' fixtures remain untouched.

Production HA status remains BLOCKED by the independently verified OS/process watchdog and native/physical/security qualification gates described above. ADMINIT remains a future separately authorized acceptance target; no connection, installation, services or physical test was performed.
