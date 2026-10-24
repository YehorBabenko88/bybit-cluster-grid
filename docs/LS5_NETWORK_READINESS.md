# LS5 network readiness — offline contract and future read-only operator preflight

Baseline: Draft PR #237 exact HEAD `e25197b169ef0e5f37b5bd0030ee4a97b13965e2`. This change is network policy/test-only. **Physical PC4 0/10 NOT_RUN; Execute NOT_AUTHORIZED; Deployment NO-GO.**

## Repository findings and limitations
- `grid/config.py`: coordinator URL defaults to `http://127.0.0.1:8765`; `grid_shared_token` and `enrollment_token` default empty. Do not treat a default or a config field as proof of actual LS5 deployment.
- `grid/coordinator.py`: `auth()` checks `x-grid-token` against configured secret, rejects empty configured token; many agent routes also require `x-node-credential`. A code-level token check does **not** establish TLS, secret custody, complete route authentication, or runtime ingress filtering. Review every route, including diagnostics and WebSocket paths, before GO.
- The user reports a historical `uvicorn --host 0.0.0.0` launch. This is a **reported deployment condition**, not independently observed on LS5. Wildcard binding may expose 8765 on LAN/public adapters if Windows firewall or upstream rules permit it.
- The user reports Tailscale IPs LS5 100.103.160.110, PC4 100.91.48.20, LS7 100.112.25.75. PC1/PC2/PC3 tailnet IPs and current grants **UNKNOWN**. Historical SSH LS5→PC4 is not current proof.

## Connection matrix — proposed, deny by default
| Source | Destination | Transport/port | Requirement | Status |
|---|---|---|---|---|
| LS5 | PC4 | Tailscale TCP/22 | controlled SSH administration, pinned host identity | historical only / BLOCKED |
| PC4 | LS5 | Tailscale TCP/22 | only if independently authorized operator diagnostics need it | historical reachability not proof / BLOCKED |
| PC4 | LS5 | Tailscale TCP/8765 | agent→coordinator, authenticated HTTPS/mTLS or reviewed TLS termination | BLOCKED |
| LS7, PC1, PC2, PC3 | LS5 | Tailscale TCP/8765 | agent API only for nodes actually running agents; node-scoped credentials | BLOCKED |
| LS5 | LS7, PC1, PC2, PC3 | Tailscale TCP/22 | SSH only for specifically approved managed nodes; otherwise DENY | BLOCKED |
| LS7, PC1, PC2, PC3 | LS5 | Tailscale TCP/22 | no default grant; separate admin justification | DENY pending approval |
| any remote node | LS5 | TCP/55432 | direct PostgreSQL | DENY; prefer local loopback DB and approved service boundary |
| any node | any other worker | TCP/8765 or 55432 | lateral movement | DENY |
| internet/LAN/non-tailnet | LS5 | TCP/22,8765,55432 | unauthorized ingress | DENY |
| LS5 | external Bybit/archive | TCP/443 | optional outbound application dependency; destination/DNS review required | BLOCKED |

This is a **proposed policy**, not an assertion that these flows currently exist. Any necessary worker-to-worker traffic must be separately justified and tested.

## Secure target
1. Coordinator API bound to LS5 Tailscale address (100.103.160.110) behind a reviewed TLS endpoint, or loopback behind an authenticated TLS reverse proxy bound to the tailnet interface. Binding `0.0.0.0:8765` is a P0 exposure risk until verified firewall policy, interfaces and endpoint authentication. A Tailscale address alone does not encrypt application traffic *outside* the tailnet; TLS and peer identity remain explicit design requirements.
2. Windows inbound firewall default deny; explicit TCP/8765 allow from authorized tailnet peer IPs **only** to the correct local address/profile and program, with explicit block/deny for LAN/public ingress. TCP/55432 loopback only; no broad remote DB rule. Prefer identity-aware Tailscale grants/tags and least-privilege SSH ACL. Tailscale policy and host firewall are independent controls; neither substitutes for API auth.
3. SSH: public-key-only, approved local principals, pinned host keys/certificates, no password or shared privileged accounts, restricted administrative origin, audit and revocation. Do not alter sshd or keys in this task.
4. API: review all FastAPI routes for consistent auth; scoped node credentials and bootstrap/enrollment revocation, rate limits, TLS verification and certificate SAN matching, private-key ACL, secure secret storage/rotation and log redaction. Never embed secrets in GitHub workflow, tests or evidence.
5. DNS/IPv6: confirm whether IPv6 listeners and non-Tailscale adapters exist. Inspect firewall scope/profile and listening process identity, not just port-open results. Confirm no unintended public NAT/port-forwarding.

## Offline policy evaluator
`installer/ls5_network_offline.py` is pure JSON processing: no sockets, subprocess, filesystem, registry, Tailscale or SSH. It rejects wildcard binds, wrong ports, public IPs, direct remote PostgreSQL, lateral SSH, duplicate flows, invalid JSON, malformed/duplicate keys and false/missing security assertions. Even a valid policy yields `status=BLOCKED`, `host_verified=false`, `physical_ready=false`, `execution_authorized=false`. The fixture models **intent only**; all positive security flags are unverified assertions.

## Future operator-executed read-only physical preflight — NOT AUTHORIZED HERE
Separate operator authorization and change window required even for read-only observation. Capture timestamp, exact node, command/identity, output SHA256, privacy-redacted receipts and independent witness. STOP on any inconsistent identity, unexpected listener or inability to collect native facts.

1. On LS5, locally inspect `Get-NetTCPConnection -State Listen` for 22/8765/55432, process IDs and executable identity; `Get-NetIPConfiguration` and `Get-NetAdapter`; read `Get-NetFirewallRule`, associated address/port/program/profile filters. **Do not add/remove rules or restart services.**
2. Read Tailscale status and effective policy using approved admin tooling; record peer identities/tags/grants, not only IPs. Inspect SSH server configuration and authorized principals/host key fingerprints without exposing private keys.
3. Inspect effective coordinator launch arguments, config source and TLS termination. Check all API endpoints for unauthenticated reachability **using only approved synthetic negative requests in an isolated bench**, not against production without authorization.
4. Confirm PostgreSQL `listen_addresses`, `pg_hba.conf` and firewall scope **read-only**, without connecting to DB or modifying service. Distinguish isolated lab ports from planned 55432.
5. Independently verify certificates, SAN, expiry, trust anchors, key protection and rotation; verify that agent URLs use HTTPS with peer validation, and node credentials are scoped/revocable. Record evidence without secrets.
6. Only after review, separately authorize minimal reachability probes in a defined source→destination matrix; no SSH logins, API mutations, service start or port scans as part of this document.

## Network GO gate
- **PASS (future):** complete signed/independently reviewed native listener/firewall/Tailscale/SSH/TLS/API evidence; least-privilege matrix; all authorized paths verified and all denied paths negatively tested from representative sources; no secrets in artifacts; independent operator approval.
- **FAIL:** wildcard externally reachable API, unprotected administrative route, open remote PostgreSQL, unknown SSH principals, wrong TLS identity, unauthorized peer or firewall allow-all, leaked secrets, any lateral path outside matrix.
- **BLOCKED:** missing node IP, no current host evidence, stale historical SSH test, synthetic PASS only, incomplete route inventory, unresolved TLS/auth, skipped CI or physical authorization absent.
- STOP/rollback: this PR makes **no physical changes**, so there is no host rollback. Any future authorized firewall change must have out-of-band access and independently approved recovery plan before implementation.

P0: reported wildcard listener + unverified firewall/TLS boundary; potential exposed API and direct DB if network policy permissive (not confirmed exploit). P1: unknown live ACL/SSH identities, incomplete route authentication and cert/secret inventory. P2: missing evidence provenance and node IP inventory. No physical GO.
